"""
`auditar_correspondencia_somarcas_tiny <slug>` — auditoria SOMENTE LEITURA
da correspondência entre o espelho da Só Marcas (Variacao/Produto) e o
espelho do Tiny (ProdutoTiny).

Os testes provam que o comando:
  - mede totais, match por SKU e match por NCM + descrição normalizada;
  - separa match inequívoco (1 candidato) de ambíguo (>1) e de sem match;
  - normaliza só formatação trivial (caixa/acento/pontuação/espaço) e NÃO
    faz fuzzy matching;
  - não grava, não atualiza e não apaga nada.
"""

from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.instancias.constants import Fornecedor
from apps.instancias.models import Instancia

from ..management.commands import auditar_correspondencia_somarcas_tiny as cmd
from ..models import Produto, ProdutoTiny, Variacao


class NormalizarDescricaoTests(TestCase):
    def test_trata_caixa_acento_pontuacao_e_espaco(self):
        n = cmd.normalizar_descricao
        base = n("Garrafa Térmica 500ml")
        self.assertEqual(base, "garrafa termica 500ml")
        self.assertEqual(n("garrafa termica  500ml"), base)  # espaço duplo
        self.assertEqual(n("GARRAFA TÉRMICA 500ML"), base)  # caixa
        self.assertEqual(n("Garrafa Térmica - 500ml."), base)  # pontuação
        self.assertEqual(n("  Garrafa   Térmica 500ml  "), base)  # pontas

    def test_nao_faz_fuzzy(self):
        n = cmd.normalizar_descricao
        # sinônimo / palavra a mais continua sendo string diferente
        self.assertNotEqual(n("Garrafa Térmica 500ml"), n("Garrafa Térmica 500 ml preta"))
        self.assertNotEqual(n("Caneca"), n("Canecas"))

    def test_vazio(self):
        self.assertEqual(cmd.normalizar_descricao(""), "")
        self.assertEqual(cmd.normalizar_descricao(None), "")


class AuditoriaTests(TestCase):
    def setUp(self):
        self.instancia = Instancia.objects.create(nome="EKK Brindes")
        self.produto = Produto.objects.create(
            instancia=self.instancia,
            fornecedor=Fornecedor.SOMARCAS,
            codigo_pai="PAI",
            nome="pai",
        )
        # outra instância + outro fornecedor: têm de ser ignorados
        self.outra_instancia = Instancia.objects.create(nome="Outra")
        self.produto_xbz = Produto.objects.create(
            instancia=self.instancia, fornecedor=Fornecedor.XBZ, codigo_pai="X", nome="x"
        )

    def _variacao(self, sku, nome, ncm, produto=None):
        return Variacao.objects.create(
            produto=produto or self.produto,
            sku=sku,
            nome=nome,
            ncm=ncm,
            preco=Decimal("10.00"),
            estoque=5,
        )

    def _tiny(self, tiny_id, sku, descricao, ncm, instancia=None):
        return ProdutoTiny.objects.create(
            instancia=instancia or self.instancia,
            tiny_id=tiny_id,
            sku=sku,
            descricao=descricao,
            ncm=ncm,
        )

    def _rodar(self, *args):
        out = StringIO()
        call_command(
            "auditar_correspondencia_somarcas_tiny", self.instancia.slug, *args, stdout=out
        )
        return out.getvalue()

    def test_instancia_inexistente_recusa(self):
        with self.assertRaises(CommandError):
            call_command("auditar_correspondencia_somarcas_tiny", "nao-existe", stdout=StringIO())

    def test_totais_contam_so_o_fornecedor_e_a_instancia_certos(self):
        self._variacao("A-1", "Caneca Branca", "39241000")
        self._variacao("A-2", "Caneca Preta", "39241000")
        self._variacao("X-1", "Item XBZ", "39241000", produto=self.produto_xbz)  # outro fornecedor
        self._tiny(1, "T-1", "Qualquer", "39241000")
        self._tiny(2, "T-2", "Outra", "39241000")
        self._tiny(9, "T-9", "Da outra instância", "39241000", instancia=self.outra_instancia)

        saida = self._rodar()
        self.assertIn("1. Variações Só Marcas ................... 2", saida)
        self.assertIn("2. Produtos Tiny (espelho) .............. 2", saida)

    def test_match_por_sku_exato(self):
        self._variacao("SKU-IGUAL", "Nada a ver", "111")
        self._variacao("SKU-SO-FORN", "Nada a ver", "111")
        self._tiny(1, "SKU-IGUAL", "Descricao Tiny", "999")
        self._tiny(2, "SKU-TINY-SO", "Outra", "999")

        saida = self._rodar()
        self.assertIn("3. Variações com SKU idêntico a algum Tiny  1", saida)
        self.assertIn("SKUs distintos em comum ............... 1", saida)

    def test_match_inequivoco_por_ncm_mais_descricao_normalizada(self):
        self._variacao("F-1", "Garrafa Térmica 500ml", "96170010")
        # mesmo NCM, descrição só com diferença de formatação -> match exato, 1 candidato
        self._tiny(10, "T-10", "GARRAFA TÉRMICA - 500ML.", "96170010")
        # ruído: mesmo NCM, descrição diferente de verdade
        self._tiny(11, "T-11", "Copo Plástico", "96170010")

        saida = self._rodar("--amostra", "5")
        self.assertIn("4. Variações com match exato (>=1 candidato) 1", saida)
        self.assertIn("5.   ...com exatamente 1 candidato Tiny ... 1", saida)
        self.assertIn("6.   ...com mais de 1 candidato (ambíguo) . 0", saida)
        self.assertIn("7. Variações sem match exato ............. 0", saida)
        # amostra de match inequívoco mostra os dois lados
        self.assertIn("SKU forn ...: F-1", saida)
        self.assertIn("tiny_id ....: 10", saida)
        self.assertIn("desc Tiny ..: GARRAFA TÉRMICA - 500ML.", saida)

    def test_ambiguidade_quando_ha_mais_de_um_candidato(self):
        self._variacao("F-1", "Caneca Cerâmica", "69120000")
        self._tiny(20, "T-20", "caneca ceramica", "69120000")
        self._tiny(21, "T-21", "Caneca Cerâmica!", "69120000")

        saida = self._rodar()
        self.assertIn("5.   ...com exatamente 1 candidato Tiny ... 0", saida)
        self.assertIn("6.   ...com mais de 1 candidato (ambíguo) . 1", saida)

    def test_ncm_diferente_nao_casa_mesmo_com_descricao_igual(self):
        self._variacao("F-1", "Mochila Executiva", "42021200")
        self._tiny(30, "T-30", "Mochila Executiva", "42029200")  # NCM diferente

        saida = self._rodar()
        self.assertIn("7. Variações sem match exato ............. 1", saida)
        self.assertIn("SKU forn ...: F-1", saida)

    def test_nao_faz_fuzzy_matching(self):
        self._variacao("F-1", "Squeeze 750ml", "39241000")
        self._tiny(40, "T-40", "Squeeze 750ml Azul", "39241000")  # palavra a mais

        saida = self._rodar()
        self.assertIn("7. Variações sem match exato ............. 1", saida)

    def test_distribuicao_de_ncm(self):
        self._variacao("F-1", "A", "39241000")
        self._variacao("F-2", "B", "39241000")
        self._variacao("F-3", "C", "42021200")
        self._tiny(1, "T-1", "X", "39241000")

        saida = self._rodar("--top-ncm", "5")
        self.assertIn("8. NCMs mais frequentes", saida)
        # NCM 39241000: 2 na Só Marcas, 1 no Tiny
        linha = next(l for l in saida.splitlines() if "39241000" in l)
        self.assertRegex(linha, r"39241000\s+2\s+1")

    def test_amostra_sem_match(self):
        self._variacao("SEM-1", "Produto Só Fornecedor", "11111111")
        saida = self._rodar()
        self.assertIn("10. Amostra de 30 casos sem match", saida)
        self.assertIn("SKU forn ...: SEM-1", saida)
        self.assertIn("desc norm ..: 'produto so fornecedor'", saida)

    def test_e_estritamente_read_only(self):
        self._variacao("F-1", "Garrafa Térmica 500ml", "96170010")
        self._tiny(10, "T-10", "garrafa termica 500ml", "96170010")

        antes = self._snapshot()
        self._rodar()
        self.assertEqual(self._snapshot(), antes)

    def _snapshot(self):
        return {
            "variacoes": list(
                Variacao.objects.order_by("pk").values_list("pk", "sku", "nome", "ncm", "atualizado_em")
            ),
            "produtos": list(
                Produto.objects.order_by("pk").values_list("pk", "nome", "atualizado_em")
            ),
            "tiny": list(
                ProdutoTiny.objects.order_by("pk").values_list(
                    "pk", "sku", "descricao", "ncm", "hash_conteudo", "atualizado_em"
                )
            ),
            "instancias": list(
                Instancia.objects.order_by("pk").values_list("pk", "slug", "atualizado_em")
            ),
        }
