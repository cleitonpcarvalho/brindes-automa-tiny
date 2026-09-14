from decimal import Decimal
from unittest.mock import Mock, patch

from django.test import SimpleTestCase

from apps.instancias.constants import Fornecedor
from apps.instancias.models import Instancia

from ..models import Produto, StatusVariacao, Variacao
from ..tiny_sync import (
    _atualizar_variacao_vinculada,
    marcar_cadastrada,
    montar_payload_produto,
)


class EstoqueTinyNormalizacaoUnitTests(SimpleTestCase):
    def _variacao(self, estoque):
        instancia = Instancia(
            nome="Instância de teste",
            tiny_origem_padrao=0,
            tiny_unidade_medida_padrao="UN",
        )
        produto = Produto(
            instancia=instancia,
            fornecedor=Fornecedor.ASIA,
            codigo_pai="PAI-1",
            nome="Produto de teste",
        )
        variacao = Variacao(
            produto=produto,
            sku="SKU-1",
            nome="Variação de teste",
            preco=Decimal("10.00"),
            estoque=estoque,
            status=StatusVariacao.CADASTRADO,
            tiny_id="123",
        )
        return instancia, variacao

    def test_estoque_positivo_e_preservado_para_publicacao(self):
        self.assertEqual(Variacao(estoque=12).estoque_para_tiny, 12)

    def test_estoque_zero_e_publicado_como_zero(self):
        self.assertEqual(Variacao(estoque=0).estoque_para_tiny, 0)

    def test_estoque_negativo_e_publicado_como_zero(self):
        self.assertEqual(Variacao(estoque=-9).estoque_para_tiny, 0)

    def test_payload_inicial_usa_estoque_normalizado(self):
        for bruto, esperado in ((12, 12), (0, 0), (-9, 0)):
            with self.subTest(estoque=bruto):
                instancia, variacao = self._variacao(bruto)
                payload = montar_payload_produto(variacao, instancia)
                self.assertEqual(payload["estoque"]["inicial"], float(esperado))

    @patch.object(Variacao, "save")
    def test_marcador_da_criacao_guarda_o_estoque_efetivamente_publicado(self, save):
        _, variacao = self._variacao(-1)

        marcar_cadastrada(variacao, "123", preco_custo_publicado=variacao.preco)

        self.assertEqual(variacao.estoque, -1)
        self.assertEqual(variacao.estoque_tiny_sincronizado, 0)
        save.assert_called_once()

    @patch("apps.catalogo.tiny_sync.tiny_fornecedor_id_de", return_value=1)
    @patch("apps.catalogo.tiny_dados_produto.montar_payload_atualizacao", return_value={})
    @patch.object(Variacao, "save")
    def test_atualizacao_vinculada_publica_estoque_normalizado(self, save, _payload, _fornecedor):
        instancia, variacao = self._variacao(-1)
        cliente = Mock()
        cliente.obter_produto.return_value = {"id": 123, "sku": "SKU-1", "fornecedores": []}

        _atualizar_variacao_vinculada(cliente, instancia, variacao)

        cliente.atualizar_estoque.assert_called_once_with(
            123, quantidade=0, preco_unitario=Decimal("10.00")
        )
        self.assertEqual(variacao.estoque_tiny_sincronizado, 0)
        save.assert_called_once()

    def test_queryset_de_pendencia_compara_estoque_normalizado(self):
        query = Variacao.filtrar_estoque_tiny_pendente(Variacao.objects.all()).query
        sql, params = query.sql_with_params()

        self.assertIn("CASE WHEN", sql)
        self.assertIn(0, params)
