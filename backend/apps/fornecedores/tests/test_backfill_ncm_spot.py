from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.catalogo.models import Produto, StatusVariacao, Variacao
from apps.instancias.models import Instancia


def _opcional(taric="9608.10.00", **extra):
    op = {
        "Sku": "11110-105",
        "WebSku": "11110-105",
        "ProdReference": "11110",
        "ColorCode": "105",
        "Price1": 1.99,
    }
    if taric is not None:
        op["Taric"] = taric
    op.update(extra)
    return op


class BackfillNcmSpotTests(TestCase):
    def setUp(self):
        self.instancia = Instancia.objects.create(nome="Loja Spot")
        self.produto = Produto.objects.create(
            instancia=self.instancia,
            fornecedor="spot",
            codigo_pai="11110",
            nome="11110. Caneta",
            payload_bruto={"ProdReference": "11110", "Name": "11110. Caneta"},
        )

    def _variacao(self, **campos):
        defaults = dict(
            produto=self.produto,
            sku="11110-105",
            nome="11110. Caneta",
            ncm="",
            preco="1.99",
            estoque=10,
            cor="Vermelho",
            imagens=[],
            payload_bruto=_opcional(),
        )
        defaults.update(campos)
        return Variacao.objects.create(**defaults)

    def _run(self, *args):
        out = StringIO()
        call_command("backfill_ncm_spot", *args, stdout=out, stderr=StringIO())
        return out.getvalue()

    def test_preenche_ncm_a_partir_do_taric_de_8_digitos(self):
        variacao = self._variacao()
        self._run()
        variacao.refresh_from_db()
        self.assertEqual(variacao.ncm, "96081000")

    def test_taric_pontuado_vira_ncm_so_digitos(self):
        variacao = self._variacao(payload_bruto=_opcional(taric="4202.92.00"))
        self._run()
        variacao.refresh_from_db()
        self.assertEqual(variacao.ncm, "42029200")

    def test_taric_com_ponto_final(self):
        variacao = self._variacao(payload_bruto=_opcional(taric="5603.13.40."))
        self._run()
        variacao.refresh_from_db()
        self.assertEqual(variacao.ncm, "56031340")

    def test_taric_de_9_digitos_nao_preenche(self):
        variacao = self._variacao(payload_bruto=_opcional(taric="621600000"))
        saida = self._run()
        variacao.refresh_from_db()
        self.assertEqual(variacao.ncm, "")
        self.assertIn("seguem sem NCM", saida)

    def test_taric_de_10_digitos_nao_preenche(self):
        variacao = self._variacao(payload_bruto=_opcional(taric="9608109900"))
        self._run()
        variacao.refresh_from_db()
        self.assertEqual(variacao.ncm, "")

    def test_taric_ausente_nao_preenche(self):
        variacao = self._variacao(payload_bruto=_opcional(taric=None))
        self._run()
        variacao.refresh_from_db()
        self.assertEqual(variacao.ncm, "")

    def test_dry_run_nao_grava(self):
        variacao = self._variacao()
        saida = self._run("--dry-run")
        variacao.refresh_from_db()
        self.assertEqual(variacao.ncm, "")
        self.assertIn("DRY-RUN", saida)

    def test_cai_para_taric_do_produto_quando_opcional_nao_tem(self):
        self.produto.payload_bruto = {"ProdReference": "11110", "Taric": "9608.10.00"}
        self.produto.save()
        variacao = self._variacao(payload_bruto=_opcional(taric=None))
        self._run()
        variacao.refresh_from_db()
        self.assertEqual(variacao.ncm, "96081000")

    def test_variacao_ja_com_ncm_correto_conta_como_inalterada(self):
        self._variacao(ncm="96081000")
        saida = self._run()
        self.assertIn("Atualizadas: 0", saida)

    def test_so_toca_em_variacoes_da_spot(self):
        outro = Produto.objects.create(
            instancia=self.instancia,
            fornecedor="asia",
            codigo_pai="A-1",
            nome="Produto Asia",
            payload_bruto={},
        )
        v_asia = Variacao.objects.create(
            produto=outro,
            sku="MC511",
            nome="Produto Asia",
            ncm="4202.92.00",
            preco="2.00",
            estoque=5,
            payload_bruto={"ncm": "4202.92.00"},
        )
        self._variacao()
        self._run()
        v_asia.refresh_from_db()
        self.assertEqual(v_asia.ncm, "4202.92.00")

    def test_filtro_por_instancia(self):
        outra_instancia = Instancia.objects.create(nome="Outra Loja")
        outro_produto = Produto.objects.create(
            instancia=outra_instancia,
            fornecedor="spot",
            codigo_pai="11110",
            nome="11110. Caneta",
            payload_bruto={"ProdReference": "11110"},
        )
        v_outra = Variacao.objects.create(
            produto=outro_produto,
            sku="11110-105",
            nome="11110. Caneta",
            ncm="",
            preco="1.99",
            estoque=10,
            payload_bruto=_opcional(),
        )
        v_alvo = self._variacao()

        self._run("--instancia", self.instancia.slug)

        v_alvo.refresh_from_db()
        v_outra.refresh_from_db()
        self.assertEqual(v_alvo.ncm, "96081000")
        self.assertEqual(v_outra.ncm, "")

    def test_nao_altera_nenhum_outro_dado_da_variacao(self):
        variacao = self._variacao(
            status=StatusVariacao.CADASTRADO,
            tiny_id="99887766",
            estoque=7,
            preco="4.50",
            cor="Azul",
            imagens=["https://spot.example/11110_105.jpg"],
            imagens_tiny_sincronizadas=["https://spot.example/11110_105.jpg"],
            estoque_tiny_sincronizado=7,
            preco_tiny_sincronizado="4.50",
        )
        campos = [
            "status",
            "tiny_id",
            "estoque",
            "preco",
            "cor",
            "imagens",
            "imagens_tiny_sincronizadas",
            "estoque_tiny_sincronizado",
            "preco_tiny_sincronizado",
            "hash_conteudo",
            "payload_bruto",
            "atributos",
            "cadastrado_em",
        ]
        antes = Variacao.objects.values(*campos).get(pk=variacao.pk)

        self._run()

        depois = Variacao.objects.values(*campos).get(pk=variacao.pk)
        self.assertEqual(antes, depois)
        variacao.refresh_from_db()
        self.assertEqual(variacao.ncm, "96081000")
