from decimal import Decimal

from django.test import TestCase

from apps.instancias.models import Instancia

from ..models import Produto, Variacao
from ..tiny_sync import identidade_tiny


class IdentidadeTinyTests(TestCase):
    def _variacao(self, fornecedor, sku, *, composto=None):
        instancia = Instancia.objects.create(nome="Loja", access_token="token")
        produto = Produto.objects.create(
            instancia=instancia, fornecedor=fornecedor, codigo_pai="P1", nome="Produto"
        )
        return Variacao.objects.create(
            produto=produto,
            sku=sku,
            nome="Variação",
            preco=Decimal("1.00"),
            estoque=1,
            atributos={"codigo_composto": composto} if composto else {},
            payload_bruto={"CodigoComposto": composto} if composto else {},
        )

    def test_xbz_publica_codigo_composto_e_preserva_sku_interno(self):
        variacao = self._variacao("xbz", "X167827", composto="08002-DOU")
        self.assertEqual(identidade_tiny(variacao), "08002-DOU")
        self.assertEqual(variacao.sku, "X167827")

    def test_xbz_usa_atributo_normalizado_como_fonte_unica(self):
        variacao = self._variacao("xbz", "X167827", composto="08002-DOU")
        variacao.payload_bruto = {"CodigoComposto": "VALOR-ANTIGO"}
        self.assertEqual(identidade_tiny(variacao), "08002-DOU")

    def test_xbz_nao_publica_valor_apenas_do_payload_bruto(self):
        variacao = self._variacao("xbz", "X167827")
        variacao.payload_bruto = {"CodigoComposto": "08002-DOU"}
        with self.assertRaisesRegex(RuntimeError, "sem CodigoComposto"):
            identidade_tiny(variacao)

    def test_outros_fornecedores_publicam_sku(self):
        variacao = self._variacao("asia", "BL026-BG", composto="IGNORADO")
        self.assertEqual(identidade_tiny(variacao), "BL026-BG")

    def test_xbz_sem_codigo_bloqueia(self):
        variacao = self._variacao("xbz", "X167827")
        with self.assertRaisesRegex(RuntimeError, "sem CodigoComposto"):
            identidade_tiny(variacao)
