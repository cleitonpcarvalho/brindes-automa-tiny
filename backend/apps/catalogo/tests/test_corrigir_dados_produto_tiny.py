"""
`corrigir_dados_produto_tiny` — backfill da regra definitiva nos produtos já
cadastrados no Tiny. NÃO cria produto, NÃO toca anexos/saldo, idempotente.
"""

from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.instancias.models import CredencialFornecedor, Instancia

from ..models import Produto, StatusVariacao, Variacao

TINY_FORN_ID = 752133514


def _get(tiny_id, sku, *, fornecedores=None):
    return {
        "id": tiny_id,
        "sku": sku,
        "descricao": f"Título {sku}",
        "descricaoComplementar": "",
        "situacao": "A",
        "tipo": "S",
        "unidade": "UN",
        "ncm": "4820.20.00",
        "origem": "0",
        "gtin": "",
        "garantia": "",
        "observacoes": "",
        "marca": None,
        "categoria": None,
        "seo": None,
        "dimensoes": {"largura": 5.3, "altura": 8, "comprimento": 1.2, "diametro": 0,
                      "pesoLiquido": 0.025, "pesoBruto": 0, "quantidadeVolumes": 0},
        "precos": {"preco": 3.6, "precoPromocional": 0, "precoCusto": 0, "precoCustoMedio": 0},
        "estoque": {"controlar": True, "sobEncomenda": False, "diasPreparacao": 0,
                    "localizacao": "", "minimo": 0, "maximo": 0, "quantidade": 1518},
        "tributacao": {"gtinEmbalagem": "", "valorIPIFixo": 0, "classeIPI": ""},
        "fornecedores": fornecedores if fornecedores is not None else [],
        "anexos": [{"id": 42, "url": "https://s3/a.jpg", "externo": False}],
        "variacoes": [], "kit": [], "producao": None,
    }


class _Base(TestCase):
    def setUp(self):
        self.instancia = Instancia.objects.create(nome="Loja", access_token="tok")
        CredencialFornecedor.objects.create(
            instancia=self.instancia, fornecedor="asia", tiny_fornecedor_id=TINY_FORN_ID
        )

    def _variacao(self, sku, *, fornecedor="asia", tiny_id="900", preco="3.60",
                  descricao="Descrição rica do produto.", **extra):
        produto = Produto.objects.create(
            instancia=self.instancia, fornecedor=fornecedor, codigo_pai=sku, nome=sku,
            descricao=descricao,
        )
        return Variacao.objects.create(
            produto=produto, sku=sku, nome=sku, preco=Decimal(preco), estoque=10,
            status=StatusVariacao.CADASTRADO, tiny_id=tiny_id, **extra,
        )

    def _rodar(self, *extra, fornecedor="asia"):
        out, err = StringIO(), StringIO()
        call_command(
            "corrigir_dados_produto_tiny",
            "--instancia", self.instancia.slug, "--fornecedor", fornecedor,
            *extra, stdout=out, stderr=err,
        )
        return out.getvalue() + err.getvalue()


class DryRunTests(_Base):
    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    def test_dry_run_nao_escreve_nem_avanca_marcadores(self, mock_get, mock_put):
        v = self._variacao("A-1", tiny_id="901")
        mock_get.return_value = _get(901, "A-1")

        saida = self._rodar("--dry-run")

        mock_put.assert_not_called()
        self.assertIn("processados: 1 | atualizados: 1", saida)
        v.refresh_from_db()
        self.assertIsNone(v.dados_tiny_sincronizados_em)
        self.assertIsNone(v.preco_custo_tiny_sincronizado)

    def test_dry_run_e_executar_juntos_e_erro(self):
        with self.assertRaises(CommandError):
            self._rodar("--dry-run", "--executar")

    def test_sem_tiny_fornecedor_id_e_erro(self):
        CredencialFornecedor.objects.filter(instancia=self.instancia).update(tiny_fornecedor_id=None)
        self._variacao("A-1")
        with self.assertRaises(CommandError):
            self._rodar("--dry-run")


class ExecutarTests(_Base):
    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto", return_value={})
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    def test_altera_somente_campos_esperados_e_avanca_marcadores(self, mock_get, mock_put):
        v = self._variacao("A-1", tiny_id="901", preco="3.60", descricao="Descrição rica.")
        mock_get.return_value = _get(901, "A-1")

        saida = self._rodar("--executar")

        mock_put.assert_called_once()
        produto_id, payload = mock_put.call_args[0]
        self.assertEqual(produto_id, 901)
        # regra definitiva
        self.assertEqual(payload["descricaoComplementar"], "Descrição rica.")
        self.assertEqual(payload["precos"], {"preco": 0.0, "precoPromocional": 0, "precoCusto": 3.6})
        self.assertEqual(payload["fornecedores"], [
            {"id": TINY_FORN_ID, "codigoProdutoNoFornecedor": "A-1", "padrao": True}
        ])
        # preservados / nunca enviados
        self.assertEqual(payload["ncm"], "4820.20.00")
        self.assertEqual(payload["descricao"], "Título A-1")  # título intocado
        self.assertNotIn("id", payload)
        self.assertNotIn("anexos", payload)
        self.assertNotIn("quantidade", payload["estoque"])
        self.assertNotIn("quantidadeVolumes", payload["dimensoes"])

        v.refresh_from_db()
        self.assertEqual(v.preco_custo_tiny_sincronizado, Decimal("3.60"))
        self.assertIsNotNone(v.dados_tiny_sincronizados_em)
        self.assertIn("atualizados: 1", saida)

    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto", return_value={})
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    def test_fornecedores_existentes_sao_preservados(self, mock_get, mock_put):
        self._variacao("A-1", tiny_id="901")
        mock_get.return_value = _get(901, "A-1", fornecedores=[{"id": 999, "padrao": True}])

        self._rodar("--executar")

        payload = mock_put.call_args[0][1]
        self.assertEqual(payload["fornecedores"], [
            {"id": 999, "codigoProdutoNoFornecedor": "", "padrao": True},
            {"id": TINY_FORN_ID, "codigoProdutoNoFornecedor": "A-1", "padrao": False},
        ])

    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto", return_value={})
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    def test_sku_divergente_no_tiny_e_ignorado_sem_put(self, mock_get, mock_put):
        self._variacao("A-1", tiny_id="901")
        mock_get.return_value = _get(901, "OUTRO-SKU")  # tiny_id aponta para outro produto

        saida = self._rodar("--executar")

        mock_put.assert_not_called()
        self.assertIn("ignorados: 1", saida)

    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto", return_value={})
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    def test_variacao_sem_tiny_id_e_ignorada(self, mock_get, mock_put):
        self._variacao("A-1", tiny_id="")
        saida = self._rodar("--executar", "--sku", "A-1")
        mock_put.assert_not_called()
        mock_get.assert_not_called()
        self.assertIn("IGNORADO — sem tiny_id confirmado", saida)
        self.assertIn("ignorados: 1", saida)

    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    def test_erro_em_um_produto_nao_para_o_lote(self, mock_get, mock_put):
        self._variacao("A-1", tiny_id="901")
        ruim = self._variacao("A-2", tiny_id="902")
        self._variacao("A-3", tiny_id="903")
        mock_get.side_effect = lambda pid: _get(pid, {901: "A-1", 902: "A-2", 903: "A-3"}[pid])

        def put(pid, payload):
            if pid == 902:
                raise RuntimeError("Tiny recusou")
            return {}

        mock_put.side_effect = put

        saida = self._rodar("--executar")

        self.assertIn("atualizados: 2", saida)
        self.assertIn("erros: 1", saida)
        ruim.refresh_from_db()
        self.assertIn("PUT falhou", ruim.ultimo_erro)
        self.assertIsNone(ruim.dados_tiny_sincronizados_em)

    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto", return_value={})
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    def test_idempotente_segunda_rodada_fila_vazia(self, mock_get, mock_put):
        self._variacao("A-1", tiny_id="901")
        mock_get.return_value = _get(901, "A-1")

        self._rodar("--executar")
        self.assertEqual(mock_put.call_count, 1)

        saida = self._rodar("--executar")
        self.assertEqual(mock_put.call_count, 1)  # nada de novo
        self.assertIn("Nada a corrigir", saida)

    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto", return_value={})
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    def test_custo_que_mudou_volta_para_a_fila(self, mock_get, mock_put):
        v = self._variacao("A-1", tiny_id="901", preco="3.60")
        mock_get.return_value = _get(901, "A-1")
        self._rodar("--executar")

        Variacao.objects.filter(pk=v.pk).update(preco=Decimal("4.90"))  # fornecedor mudou o preço
        mock_get.return_value = _get(901, "A-1")
        self._rodar("--executar")

        self.assertEqual(mock_put.call_count, 2)
        self.assertEqual(mock_put.call_args[0][1]["precos"]["precoCusto"], 4.9)

    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto", return_value={})
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    def test_so_toca_no_fornecedor_informado(self, mock_get, mock_put):
        self._variacao("A-1", fornecedor="asia", tiny_id="901")
        self._variacao("X-1", fornecedor="xbz", tiny_id="801")
        CredencialFornecedor.objects.create(
            instancia=self.instancia, fornecedor="xbz", tiny_fornecedor_id=111
        )
        mock_get.side_effect = lambda pid: _get(pid, {901: "A-1", 801: "X-1"}[pid])

        self._rodar("--executar", fornecedor="asia")

        self.assertEqual(mock_put.call_count, 1)
        self.assertEqual(mock_put.call_args[0][0], 901)
