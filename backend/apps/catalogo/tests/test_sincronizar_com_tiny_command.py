from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from apps.instancias.models import Instancia

from ..models import Produto, StatusVariacao, Variacao


def _instancia():
    return Instancia.objects.create(
        nome="Loja Cmd", access_token="t", tiny_origem_padrao=0, tiny_unidade_medida_padrao="UN"
    )


def _variacao(instancia, sku, **kwargs):
    produto = Produto.objects.create(
        instancia=instancia, fornecedor="xbz", codigo_pai=f"pai-{sku}", nome=sku
    )
    dados = {"produto": produto, "sku": sku, "nome": sku, "preco": Decimal("1.00"), "estoque": 3}
    dados.update(kwargs)
    return Variacao.objects.create(**dados)


class SincronizarComTinyCommandTests(TestCase):
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_orquestra_criacao_pelo_command(self, _mb, mock_criar):
        inst = _instancia()
        v = _variacao(inst, "CMD-1")
        mock_criar.return_value = {"id": 5, "sku": "CMD-1"}

        out = StringIO()
        call_command("sincronizar_com_tiny", inst.slug, "xbz", stdout=out)

        v.refresh_from_db()
        self.assertEqual(v.status, StatusVariacao.CADASTRADO)
        self.assertIn("criadas: 1", out.getvalue())

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_dry_run_nao_cria(self, _mb, mock_criar):
        inst = _instancia()
        v = _variacao(inst, "CMD-DRY")

        out = StringIO()
        call_command("sincronizar_com_tiny", inst.slug, "xbz", "--dry-run", stdout=out)

        v.refresh_from_db()
        mock_criar.assert_not_called()
        self.assertEqual(v.status, StatusVariacao.PENDENTE)
        self.assertIn("(dry-run)", out.getvalue())

    def test_preview_nao_toca_no_tiny(self):
        inst = _instancia()
        _variacao(inst, "P-1")
        _variacao(inst, "P-2", estoque=0)

        out = StringIO()
        with patch("apps.instancias.tiny_client.TinyApiClient") as mock_cliente:
            call_command("sincronizar_com_tiny", inst.slug, "xbz", "--preview", stdout=out)
        mock_cliente.assert_not_called()
        self.assertIn("elegiveis ..... 1", out.getvalue())
