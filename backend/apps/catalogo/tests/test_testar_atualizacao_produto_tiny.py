"""
`testar_atualizacao_produto_tiny` — canário manual de `PUT /produtos/{id}`
(NÃO é o backfill em lote). Payload = regra definitiva via
`tiny_dados_produto.montar_payload_atualizacao`.
"""

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.instancias.models import CredencialFornecedor, Instancia

from ..models import Produto, Variacao
from .test_tiny_dados_produto import DESC_COMPL, GET_BL026


class ComandoCanarioTests(TestCase):
    def setUp(self):
        self.instancia = Instancia.objects.create(nome="Loja Canário", access_token="tok")
        produto = Produto.objects.create(
            instancia=self.instancia, fornecedor="asia", codigo_pai="BL026", nome="Mini Caderno",
            descricao=DESC_COMPL,
        )
        Variacao.objects.create(
            produto=produto, sku="BL026-BG", nome="Mini Caderno - Bege", preco="3.60", estoque=1518
        )
        CredencialFornecedor.objects.create(
            instancia=self.instancia, fornecedor="asia", tiny_fornecedor_id=752133514
        )

    def _rodar(self, *extra):
        out = StringIO()
        call_command(
            "testar_atualizacao_produto_tiny",
            "--instancia", self.instancia.slug,
            "--tiny-id", "924267500",
            "--sku", "BL026-BG",
            "--fornecedor", "asia",
            *extra,
            stdout=out,
        )
        return out.getvalue()

    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto", return_value=GET_BL026)
    def test_sem_executar_so_faz_get_e_imprime_o_payload(self, mock_get, mock_put):
        saida = self._rodar()

        mock_get.assert_called_once_with(924267500)
        mock_put.assert_not_called()
        self.assertIn("DRY-RUN", saida)
        self.assertIn('"descricaoComplementar"', saida)
        self.assertIn(DESC_COMPL, saida)
        self.assertIn('"precoCusto": 3.6', saida)

    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto", return_value={})
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    def test_executar_faz_put_defensivo_e_diff_sem_surpresa(self, mock_get, mock_put):
        depois = {
            **GET_BL026,
            "descricaoComplementar": DESC_COMPL,
            "precos": {"preco": 0, "precoPromocional": 0, "precoCusto": 3.6, "precoCustoMedio": 0},
            "fornecedores": [{"id": 752133514, "nome": "Asia", "codigoProdutoNoFornecedor": "BL026-BG"}],
        }
        mock_get.side_effect = [GET_BL026, depois]

        saida = self._rodar("--executar")

        mock_put.assert_called_once()
        produto_id, payload = mock_put.call_args[0]
        self.assertEqual(produto_id, 924267500)
        self.assertNotIn("id", payload)
        self.assertNotIn("anexos", payload)
        self.assertNotIn("quantidade", payload["estoque"])
        self.assertEqual(payload["precos"], {"preco": 0.0, "precoPromocional": 0, "precoCusto": 3.6})
        self.assertEqual(payload["fornecedores"], [
            {"id": 752133514, "codigoProdutoNoFornecedor": "BL026-BG", "padrao": True}
        ])
        self.assertIn("alterado (esperado)", saida)
        self.assertIn("Nenhuma alteração inesperada", saida)

    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto", return_value={})
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    def test_executar_destaca_alteracao_inesperada(self, mock_get, mock_put):
        depois = {
            **GET_BL026,
            "descricaoComplementar": DESC_COMPL,
            "precos": {"preco": 0, "precoPromocional": 0, "precoCusto": 3.6, "precoCustoMedio": 0},
            "fornecedores": [{"id": 752133514, "codigoProdutoNoFornecedor": "BL026-BG"}],
            "estoque": {**GET_BL026["estoque"], "quantidade": 0},  # saldo sumiu!
            "ncm": "0000.00.00",  # NCM mudou!
        }
        mock_get.side_effect = [GET_BL026, depois]

        saida = self._rodar("--executar")

        self.assertIn("INESPERADO", saida)
        self.assertIn("NÃO seguir para o lote", saida)

    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    def test_aborta_se_o_sku_do_tiny_nao_bate(self, mock_get):
        mock_get.return_value = {**GET_BL026, "sku": "OUTRO-SKU"}
        with self.assertRaises(CommandError):
            self._rodar()

    def test_aborta_sem_tiny_fornecedor_id_configurado(self):
        CredencialFornecedor.objects.filter(instancia=self.instancia, fornecedor="asia").update(
            tiny_fornecedor_id=None
        )
        with self.assertRaises(CommandError):
            self._rodar()
