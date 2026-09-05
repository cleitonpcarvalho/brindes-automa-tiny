from unittest.mock import Mock, patch

from django.core.exceptions import ImproperlyConfigured
from django.test import TestCase, override_settings

from ..models import Instancia
from ..tiny_client import TinyApiClient, TinyApiError, TinyApiValidationError


def _instancia(**kwargs):
    dados = {"nome": "Loja API", "access_token": "token-abc"}
    dados.update(kwargs)
    return Instancia.objects.create(**dados)


def _resposta(status_code=200, headers=None, corpo=None):
    resposta = Mock()
    resposta.status_code = status_code
    resposta.headers = headers or {}
    resposta.json.return_value = corpo if corpo is not None else {}
    resposta.text = str(corpo or "")
    return resposta


class LimiterFalso:
    """Stub do RateLimiterCompartilhado — os testes deste arquivo não precisam de Redis de verdade."""

    def __init__(self):
        self.chamadas = []

    def aguardar_vaga(self, limite_por_minuto):
        self.chamadas.append(limite_por_minuto)


class LeituraDoLimiteDaContaTests(TestCase):
    @override_settings(TINY_API_BASE_URL="https://api.tiny.example")
    @patch("apps.instancias.tiny_client.requests.request")
    def test_le_x_limit_api_e_guarda_na_instancia(self, mock_request):
        instancia = _instancia()
        mock_request.return_value = _resposta(200, {"x-limit-api": "120"})

        cliente = TinyApiClient(instancia, sleep_fn=lambda s: None, limiter=LimiterFalso())
        cliente.get("/produtos")

        instancia.refresh_from_db()
        self.assertEqual(instancia.rate_limit_por_minuto, 120)

    @override_settings(TINY_API_BASE_URL="https://api.tiny.example")
    @patch("apps.instancias.tiny_client.requests.request")
    def test_resposta_sem_header_nao_apaga_o_valor_ja_conhecido(self, mock_request):
        instancia = _instancia(rate_limit_por_minuto=90)
        mock_request.return_value = _resposta(200, {})

        cliente = TinyApiClient(instancia, sleep_fn=lambda s: None, limiter=LimiterFalso())
        cliente.get("/produtos")

        instancia.refresh_from_db()
        self.assertEqual(instancia.rate_limit_por_minuto, 90)

    def test_sem_base_url_configurada_recusa_chamar(self):
        instancia = _instancia()
        cliente = TinyApiClient(instancia, base_url="", limiter=LimiterFalso())
        with self.assertRaises(ImproperlyConfigured):
            cliente.get("/produtos")

    @override_settings(TINY_API_BASE_URL="https://erp.tiny.com.br/public-api/v3")
    def test_base_url_padrao_vem_das_settings(self):
        instancia = _instancia()
        cliente = TinyApiClient(instancia, limiter=LimiterFalso())
        self.assertEqual(cliente.base_url, "https://erp.tiny.com.br/public-api/v3")


class TodaChamadaPassaPeloLimiterTests(TestCase):
    @override_settings(TINY_API_BASE_URL="https://api.tiny.example")
    @patch("apps.instancias.tiny_client.requests.request")
    def test_get_e_post_consultam_o_limiter_com_o_limite_atual_da_instancia(self, mock_request):
        instancia = _instancia(rate_limit_por_minuto=42)
        mock_request.return_value = _resposta(200, {})
        limiter = LimiterFalso()

        cliente = TinyApiClient(instancia, sleep_fn=lambda s: None, limiter=limiter)
        cliente.get("/produtos")
        cliente.post("/produtos", json={})

        self.assertEqual(limiter.chamadas, [42, 42])


class Trata429Tests(TestCase):
    @override_settings(TINY_API_BASE_URL="https://api.tiny.example")
    @patch("apps.instancias.tiny_client.requests.request")
    def test_respeita_retry_after_quando_presente(self, mock_request):
        instancia = _instancia()
        mock_request.side_effect = [
            _resposta(429, {"Retry-After": "5"}),
            _resposta(200, {}),
        ]

        esperas = []
        cliente = TinyApiClient(instancia, sleep_fn=lambda s: esperas.append(s), limiter=LimiterFalso())
        resposta = cliente.get("/produtos")

        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(esperas, [5.0])

    @override_settings(TINY_API_BASE_URL="https://api.tiny.example")
    @patch("apps.instancias.tiny_client.requests.request")
    def test_backoff_exponencial_sem_retry_after(self, mock_request):
        instancia = _instancia()
        mock_request.side_effect = [
            _resposta(429, {}),
            _resposta(429, {}),
            _resposta(200, {}),
        ]

        esperas = []
        cliente = TinyApiClient(instancia, sleep_fn=lambda s: esperas.append(s), limiter=LimiterFalso())
        cliente.get("/produtos")

        self.assertEqual(esperas, [1.0, 2.0])  # dobra a cada tentativa

    @override_settings(TINY_API_BASE_URL="https://api.tiny.example")
    @patch("apps.instancias.tiny_client.requests.request")
    def test_429_persistente_levanta_erro_apos_maximo_de_tentativas(self, mock_request):
        instancia = _instancia()
        mock_request.return_value = _resposta(429, {})

        cliente = TinyApiClient(instancia, sleep_fn=lambda s: None, limiter=LimiterFalso())
        with self.assertRaises(TinyApiError):
            cliente.get("/produtos")


class DominioProdutosTests(TestCase):
    @override_settings(TINY_API_BASE_URL="https://api.tiny.example")
    @patch("apps.instancias.tiny_client.requests.request")
    def test_buscar_produto_por_sku_encontrado(self, mock_request):
        instancia = _instancia()
        mock_request.return_value = _resposta(200, {}, {"itens": [{"id": 555, "sku": "ABC-1"}]})

        cliente = TinyApiClient(instancia, sleep_fn=lambda s: None, limiter=LimiterFalso())
        resultado = cliente.buscar_produto_por_sku("ABC-1")

        self.assertEqual(resultado["id"], 555)
        _, kwargs = mock_request.call_args
        self.assertEqual(kwargs["params"], {"codigo": "ABC-1", "limit": 1})

    @override_settings(TINY_API_BASE_URL="https://api.tiny.example")
    @patch("apps.instancias.tiny_client.requests.request")
    def test_buscar_produto_por_sku_nao_encontrado(self, mock_request):
        instancia = _instancia()
        mock_request.return_value = _resposta(200, {}, {"itens": []})

        cliente = TinyApiClient(instancia, sleep_fn=lambda s: None, limiter=LimiterFalso())
        self.assertIsNone(cliente.buscar_produto_por_sku("NAO-EXISTE"))

    @override_settings(TINY_API_BASE_URL="https://api.tiny.example")
    @patch("apps.instancias.tiny_client.requests.request")
    def test_criar_produto_com_sucesso_devolve_id(self, mock_request):
        instancia = _instancia()
        mock_request.return_value = _resposta(200, {}, {"id": 999, "codigo": "ABC-1"})

        cliente = TinyApiClient(instancia, sleep_fn=lambda s: None, limiter=LimiterFalso())
        resultado = cliente.criar_produto({"sku": "ABC-1", "tipo": "S", "descricao": "Produto"})

        self.assertEqual(resultado["id"], 999)

    @override_settings(TINY_API_BASE_URL="https://api.tiny.example")
    @patch("apps.instancias.tiny_client.requests.request")
    def test_criar_produto_com_erro_levanta_validationerror_com_detalhes(self, mock_request):
        instancia = _instancia()
        mock_request.return_value = _resposta(
            400,
            {},
            {
                "mensagem": "Ocorreram erros de validação",
                "detalhes": [{"campo": "ncm", "mensagem": "O campo NCM é obrigatório"}],
            },
        )

        cliente = TinyApiClient(instancia, sleep_fn=lambda s: None, limiter=LimiterFalso())
        with self.assertRaises(TinyApiValidationError) as ctx:
            cliente.criar_produto({"sku": "ABC-1"})

        self.assertTrue(ctx.exception.menciona_ncm())

    @override_settings(TINY_API_BASE_URL="https://api.tiny.example")
    @patch("apps.instancias.tiny_client.requests.request")
    def test_atualizar_estoque_envia_tipo_balanco(self, mock_request):
        instancia = _instancia()
        mock_request.return_value = _resposta(200, {}, {"idLancamento": 1})

        cliente = TinyApiClient(instancia, sleep_fn=lambda s: None, limiter=LimiterFalso())
        cliente.atualizar_estoque(999, quantidade=42, preco_unitario=10)

        _, kwargs = mock_request.call_args
        self.assertEqual(kwargs["json"]["tipo"], "B")
        self.assertEqual(kwargs["json"]["quantidade"], 42.0)
