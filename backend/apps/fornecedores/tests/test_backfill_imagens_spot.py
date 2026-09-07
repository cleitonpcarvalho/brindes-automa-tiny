from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.catalogo.models import Produto, StatusVariacao, Variacao
from apps.fornecedores.models import ConfiguracaoFornecedor
from apps.instancias.models import Instancia

BASE = "https://www.spotgifts.com.br/fotos/produtos"


def _opcional(**extra):
    op = {
        "Sku": "11110-105",
        "WebSku": "11110-105",
        "ProdReference": "11110",
        "ColorCode": "105",
        "Price1": 1.99,
        "AllImageList": "11110_105-logo.jpg, 11110_105.jpg",
    }
    op.update(extra)
    return op


class BackfillImagensSpotTests(TestCase):
    def setUp(self):
        self.instancia = Instancia.objects.create(nome="Loja Spot")
        # a migration 0004 já cria a linha 'spot' — garante o valor esperado.
        self.config, _ = ConfiguracaoFornecedor.objects.update_or_create(
            fornecedor="spot", defaults={"url_base_imagens": BASE}
        )
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
        call_command("backfill_imagens_spot", *args, stdout=out, stderr=StringIO())
        return out.getvalue()

    def test_preenche_imagens_a_partir_do_payload_salvo(self):
        variacao = self._variacao()
        self._run()
        variacao.refresh_from_db()
        self.assertEqual(
            variacao.imagens,
            [f"{BASE}/11110_105.jpg", f"{BASE}/11110_105-logo.jpg"],
        )

    def test_dry_run_nao_grava(self):
        variacao = self._variacao()
        saida = self._run("--dry-run")
        variacao.refresh_from_db()
        self.assertEqual(variacao.imagens, [])
        self.assertIn("DRY-RUN", saida)

    def test_sem_url_base_configurada_falha(self):
        self.config.url_base_imagens = ""
        self.config.save()
        self._variacao()
        with self.assertRaises(CommandError):
            self._run()

    def test_variacao_ja_correta_conta_como_inalterada(self):
        self._variacao(imagens=[f"{BASE}/11110_105.jpg", f"{BASE}/11110_105-logo.jpg"])
        saida = self._run()
        self.assertIn("inalteradas: 1", saida)
        self.assertIn("Atualizadas: 0", saida)

    def test_variacao_sem_payload_bruto_e_pulada(self):
        variacao = self._variacao(payload_bruto={})
        saida = self._run()
        variacao.refresh_from_db()
        self.assertEqual(variacao.imagens, [])
        self.assertIn("sem payload_bruto: 1", saida)

    def test_nao_altera_nenhum_outro_dado_da_variacao(self):
        variacao = self._variacao(
            status=StatusVariacao.CADASTRADO,
            tiny_id="99887766",
            estoque=7,
            preco="4.50",
            ncm="96081000",
            cor="Azul",
            estoque_tiny_sincronizado=7,
            preco_tiny_sincronizado="4.50",
        )
        antes = Variacao.objects.values(
            "status",
            "tiny_id",
            "estoque",
            "preco",
            "ncm",
            "cor",
            "hash_conteudo",
            "payload_bruto",
            "estoque_tiny_sincronizado",
            "preco_tiny_sincronizado",
        ).get(pk=variacao.pk)

        self._run()

        depois = Variacao.objects.values(*antes.keys()).get(pk=variacao.pk)
        self.assertEqual(antes, depois)
        variacao.refresh_from_db()
        self.assertEqual(
            variacao.imagens,
            [f"{BASE}/11110_105.jpg", f"{BASE}/11110_105-logo.jpg"],
        )

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
            preco="2.00",
            estoque=5,
            imagens=["https://asia.example/mc511.jpg"],
            payload_bruto={"imagem": "https://asia.example/mc511.jpg"},
        )
        self._variacao()
        self._run()
        v_asia.refresh_from_db()
        self.assertEqual(v_asia.imagens, ["https://asia.example/mc511.jpg"])

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
            preco="1.99",
            estoque=10,
            imagens=[],
            payload_bruto=_opcional(),
        )
        v_alvo = self._variacao()

        self._run("--instancia", self.instancia.slug)

        v_alvo.refresh_from_db()
        v_outra.refresh_from_db()
        self.assertEqual(len(v_alvo.imagens), 2)
        self.assertEqual(v_outra.imagens, [])
