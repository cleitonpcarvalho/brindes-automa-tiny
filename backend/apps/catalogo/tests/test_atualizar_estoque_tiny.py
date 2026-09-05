from decimal import Decimal
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from apps.instancias.models import Instancia

from ..models import Produto, StatusVariacao, Variacao


def _instancia_pronta(**kwargs):
    dados = {"nome": "Loja Estoque", "access_token": "token-valido"}
    dados.update(kwargs)
    return Instancia.objects.create(**dados)


def _variacao_cadastrada(instancia, sku, **kwargs):
    produto = Produto.objects.create(
        instancia=instancia, fornecedor="xbz", codigo_pai=f"pai-{sku}", nome=f"Produto {sku}"
    )
    dados = {
        "produto": produto,
        "sku": sku,
        "nome": f"Variação {sku}",
        "preco": Decimal("10.00"),
        "estoque": 5,
        "status": StatusVariacao.CADASTRADO,
        "tiny_id": "123",
    }
    dados.update(kwargs)
    return Variacao.objects.create(**dados)


class AtualizacaoDeEstoqueTests(TestCase):
    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_estoque")
    def test_estoque_nunca_sincronizado_e_enviado(self, mock_atualizar):
        instancia = _instancia_pronta()
        variacao = _variacao_cadastrada(instancia, "SKU-1", estoque=42, estoque_tiny_sincronizado=None)

        call_command("atualizar_estoque_tiny", instancia.slug)

        mock_atualizar.assert_called_once_with(123, quantidade=42, preco_unitario=Decimal("10.00"))
        variacao.refresh_from_db()
        self.assertEqual(variacao.estoque_tiny_sincronizado, 42)

    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_estoque")
    def test_estoque_ja_sincronizado_e_igual_nao_e_reenviado(self, mock_atualizar):
        instancia = _instancia_pronta()
        _variacao_cadastrada(instancia, "SKU-2", estoque=10, estoque_tiny_sincronizado=10)

        call_command("atualizar_estoque_tiny", instancia.slug)

        mock_atualizar.assert_not_called()

    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_estoque")
    def test_estoque_mudou_desde_a_ultima_sincronizacao_e_reenviado(self, mock_atualizar):
        instancia = _instancia_pronta()
        variacao = _variacao_cadastrada(instancia, "SKU-3", estoque=99, estoque_tiny_sincronizado=10)

        call_command("atualizar_estoque_tiny", instancia.slug)

        mock_atualizar.assert_called_once()
        variacao.refresh_from_db()
        self.assertEqual(variacao.estoque_tiny_sincronizado, 99)

    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_estoque")
    def test_variacao_pendente_nao_e_considerada(self, mock_atualizar):
        instancia = _instancia_pronta()
        _variacao_cadastrada(
            instancia, "SKU-4", status=StatusVariacao.PENDENTE, estoque=5, estoque_tiny_sincronizado=None
        )

        call_command("atualizar_estoque_tiny", instancia.slug)

        mock_atualizar.assert_not_called()

    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_estoque")
    def test_falha_registra_erro_mas_mantem_status_cadastrado(self, mock_atualizar):
        instancia = _instancia_pronta()
        variacao = _variacao_cadastrada(instancia, "SKU-5", estoque=7, estoque_tiny_sincronizado=None)
        mock_atualizar.side_effect = Exception("Tiny fora do ar")

        call_command("atualizar_estoque_tiny", instancia.slug)

        variacao.refresh_from_db()
        self.assertEqual(variacao.status, StatusVariacao.CADASTRADO)  # NÃO vira erro
        self.assertIn("Tiny fora do ar", variacao.ultimo_erro)
        self.assertIsNone(variacao.estoque_tiny_sincronizado)  # não avançou -> tenta de novo depois

    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_estoque")
    def test_uma_falha_nao_impede_a_atualizacao_das_demais(self, mock_atualizar):
        instancia = _instancia_pronta()
        v1 = _variacao_cadastrada(
            instancia, "SKU-RUIM", estoque=1, estoque_tiny_sincronizado=None, tiny_id="111"
        )
        v2 = _variacao_cadastrada(
            instancia, "SKU-BOM", estoque=2, estoque_tiny_sincronizado=None, tiny_id="222"
        )

        def side_effect(tiny_id, *, quantidade, preco_unitario):
            if tiny_id == int(v1.tiny_id):
                raise Exception("falhou")
            return {"idLancamento": 1}

        mock_atualizar.side_effect = side_effect

        call_command("atualizar_estoque_tiny", instancia.slug)

        v1.refresh_from_db()
        v2.refresh_from_db()
        self.assertIsNone(v1.estoque_tiny_sincronizado)
        self.assertEqual(v2.estoque_tiny_sincronizado, 2)
