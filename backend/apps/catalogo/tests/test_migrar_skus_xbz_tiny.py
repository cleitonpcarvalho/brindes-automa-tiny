from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from apps.instancias.models import CredencialFornecedor, Instancia

from ..models import Produto, StatusVariacao, Variacao


def _detalhe(sku, *, fornecedor_codigo=None, custo=1, corrigido=False):
    return {
        "id": 924252038,
        "sku": sku,
        "descricao": "Produto",
        "descricaoComplementar": "",
        "origem": "0",
        "ncm": "",
        "precos": {"preco": 0 if corrigido else 10,
                   "precoPromocional": 0 if corrigido else 4,
                   "precoCusto": custo},
        "estoque": {"controlar": True},
        "dimensoes": {},
        "fornecedores": ([{"id": 752133514, "codigoProdutoNoFornecedor": fornecedor_codigo}]
                         if fornecedor_codigo else []),
    }


class MigrarSkusXbzTests(TestCase):
    def setUp(self):
        self.instancia = Instancia.objects.create(nome="Loja", access_token="token")
        CredencialFornecedor.objects.create(
            instancia=self.instancia, fornecedor="xbz", tiny_fornecedor_id=752133514
        )
        produto = Produto.objects.create(
            instancia=self.instancia, fornecedor="xbz", codigo_pai="08002", nome="Produto",
            descricao="Descrição complementar",
        )
        self.variacao = Variacao.objects.create(
            produto=produto, sku="X167827", nome="Produto", preco=Decimal("3.50"), estoque=2,
            status=StatusVariacao.CADASTRADO, tiny_id="924252038",
            payload_bruto={"CodigoComposto": "08002-DOU"},
            atributos={"codigo_composto": "08002-DOU"},
        )

    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto")
    def test_dry_run_nao_faz_put(self, put, obter, buscar):
        obter.return_value = _detalhe("X167827")
        out = StringIO()
        call_command("migrar_skus_xbz_tiny", "--instancia", self.instancia.slug, stdout=out)
        put.assert_not_called()
        self.assertIn("SERIA ATUALIZADO", out.getvalue())

    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto")
    def test_execucao_atualiza_e_confirma_sem_mudar_sku_interno(self, put, obter, buscar):
        obter.side_effect = [_detalhe("X167827"), _detalhe("08002-DOU", fornecedor_codigo="08002-DOU", custo=3.5, corrigido=True)]
        call_command("migrar_skus_xbz_tiny", "--instancia", self.instancia.slug, "--executar")
        put.assert_called_once()
        payload = put.call_args.args[1]
        self.assertEqual(payload["sku"], "08002-DOU")
        self.assertEqual(payload["fornecedores"][0]["codigoProdutoNoFornecedor"], "08002-DOU")
        self.variacao.refresh_from_db()
        self.assertEqual(self.variacao.sku, "X167827")
        self.assertEqual(self.variacao.tiny_id, "924252038")
