"""
`sincronizar_preco_tiny <slug>` — mantém o PREÇO DE VENDA (precos.preco) do
produto no Tiny sincronizado com `Variacao.preco` (preço do fornecedor,
sem margem). Distinto do `precoUnitario` do movimento de estoque.
"""

from decimal import Decimal
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.instancias.models import Instancia

from ..models import Produto, StatusVariacao, Variacao


def _instancia():
    return Instancia.objects.create(nome="Loja Preço", access_token="tok")


def _cadastrada(instancia, sku, *, preco, preco_sinc, tiny_id="100", fornecedor="xbz"):
    produto = Produto.objects.create(
        instancia=instancia, fornecedor=fornecedor, codigo_pai=f"pai-{sku}", nome=sku
    )
    return Variacao.objects.create(
        produto=produto,
        sku=sku,
        nome=sku,
        preco=Decimal(preco),
        estoque=5,
        status=StatusVariacao.CADASTRADO,
        tiny_id=tiny_id,
        preco_tiny_sincronizado=None if preco_sinc is None else Decimal(preco_sinc),
    )


class FilaTests(TestCase):
    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_preco_venda")
    def test_so_processa_o_que_esta_fora_de_sincronia(self, mock_put):
        instancia = _instancia()
        muda = _cadastrada(instancia, "MUDOU", preco="12.00", preco_sinc="10.00")
        _cadastrada(instancia, "IGUAL", preco="10.00", preco_sinc="10.00")
        nova = _cadastrada(instancia, "NOVA", preco="9.00", preco_sinc=None)
        mock_put.return_value = {"id": 100}

        call_command("sincronizar_preco_tiny", instancia.slug)

        enviados = sorted(c.args[0] for c in mock_put.call_args_list)
        self.assertEqual(mock_put.call_count, 2)
        muda.refresh_from_db()
        nova.refresh_from_db()
        self.assertEqual(muda.preco_tiny_sincronizado, Decimal("12.00"))
        self.assertEqual(nova.preco_tiny_sincronizado, Decimal("9.00"))

    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_preco_venda")
    def test_ignora_quem_nao_esta_cadastrado_ou_sem_tiny_id(self, mock_put):
        instancia = _instancia()
        v = _cadastrada(instancia, "SEM-ID", preco="5.00", preco_sinc=None, tiny_id="")
        v.status = StatusVariacao.PENDENTE
        v.save(update_fields=["status"])

        call_command("sincronizar_preco_tiny", instancia.slug)
        mock_put.assert_not_called()

    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_preco_venda")
    def test_filtro_por_fornecedor_e_skus(self, mock_put):
        instancia = _instancia()
        _cadastrada(instancia, "A-1", preco="2.00", preco_sinc=None, fornecedor="asia")
        _cadastrada(instancia, "A-2", preco="3.00", preco_sinc=None, fornecedor="asia")
        _cadastrada(instancia, "X-1", preco="4.00", preco_sinc=None, fornecedor="xbz")
        mock_put.return_value = {"id": 100}

        call_command("sincronizar_preco_tiny", instancia.slug, "--fornecedor", "asia", "--skus", "A-1")

        self.assertEqual([c.args[0] for c in mock_put.call_args_list], [100])
        # confirma que foi a variação certa: só uma chamada, preço 2.00
        self.assertEqual(mock_put.call_args.kwargs["preco"], Decimal("2.00"))


class PrecoDeVendaTests(TestCase):
    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_preco_venda")
    def test_envia_o_preco_do_fornecedor_sem_margem(self, mock_put):
        instancia = _instancia()
        _cadastrada(instancia, "P", preco="47.53", preco_sinc="30.00", tiny_id="777")
        mock_put.return_value = {"id": 777}

        call_command("sincronizar_preco_tiny", instancia.slug)

        mock_put.assert_called_once_with(777, preco=Decimal("47.53"))

    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_preco_venda")
    def test_falha_nao_avanca_o_marcador_e_nao_trava_o_lote(self, mock_put):
        instancia = _instancia()
        ruim = _cadastrada(instancia, "RUIM", preco="1.00", preco_sinc=None, tiny_id="1")
        bom = _cadastrada(instancia, "BOM", preco="2.00", preco_sinc=None, tiny_id="2")

        def efeito(id_produto, *, preco):
            if id_produto == 1:
                raise RuntimeError("Tiny recusou")
            return {"id": id_produto}

        mock_put.side_effect = efeito
        call_command("sincronizar_preco_tiny", instancia.slug)

        ruim.refresh_from_db()
        bom.refresh_from_db()
        self.assertIsNone(ruim.preco_tiny_sincronizado)
        self.assertIn("Tiny recusou", ruim.ultimo_erro)
        self.assertEqual(bom.preco_tiny_sincronizado, Decimal("2.00"))


class DryRunTests(TestCase):
    @override_settings(TINY_API_BASE_URL="https://api.tiny.example")
    @patch("apps.instancias.tiny_client.requests.request")
    def test_dry_run_nao_faz_nenhuma_chamada_nem_altera_banco(self, mock_request):
        instancia = _instancia()
        v = _cadastrada(instancia, "DRY", preco="20.00", preco_sinc="10.00", tiny_id="55")

        out = StringIO()
        call_command("sincronizar_preco_tiny", instancia.slug, "--dry-run", stdout=out)

        mock_request.assert_not_called()
        self.assertIn("10.00 -> 20.00", out.getvalue())
        v.refresh_from_db()
        self.assertEqual(v.preco_tiny_sincronizado, Decimal("10.00"))  # inalterado


class ClienteAtualizarPrecoTests(TestCase):
    @override_settings(TINY_API_BASE_URL="https://api.tiny.example")
    @patch("apps.instancias.tiny_client.requests.request")
    def test_usa_endpoint_especifico_de_preco_com_corpo_minimo(self, mock_request):
        from apps.instancias.tiny_client import TinyApiClient

        instancia = _instancia()
        chamadas = []

        def handler(metodo, url, **kw):
            chamadas.append((metodo, url, kw.get("json")))
            r = Mock(status_code=200, headers={}, text="")
            r.json.return_value = {"ok": True}
            return r

        mock_request.side_effect = handler
        cliente = TinyApiClient(instancia, sleep_fn=lambda s: None)
        cliente.atualizar_preco_venda(55, preco=Decimal("25.50"))

        self.assertEqual(len(chamadas), 1)  # sem GET do produto inteiro
        metodo, url, corpo = chamadas[0]
        self.assertEqual(metodo, "PUT")
        self.assertTrue(url.endswith("/produtos/55/preco"))
        self.assertEqual(corpo, {"preco": 25.5})  # só o preço de venda

    @override_settings(TINY_API_BASE_URL="https://api.tiny.example")
    @patch("apps.instancias.tiny_client.requests.request")
    def test_cliente_somente_leitura_bloqueia_o_put_de_preco(self, mock_request):
        from apps.instancias.tiny_client import TinyApiClient, TinyEscritaBloqueadaError

        instancia = _instancia()
        cliente = TinyApiClient(instancia, sleep_fn=lambda s: None, somente_leitura=True)
        with self.assertRaises(TinyEscritaBloqueadaError):
            cliente.atualizar_preco_venda(55, preco=Decimal("1.00"))
        mock_request.assert_not_called()
