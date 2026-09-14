from unittest.mock import Mock, patch

from django.test import SimpleTestCase, override_settings

from ..tiny_client import TINY_V3_RATE_LIMIT_FALLBACK, TinyApiClient
from ..tiny_throttle import MARGEM_SEGURANCA, RateLimiterCompartilhado


class LockFalso:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class RedisFalso:
    def __init__(self, clock):
        self.clock = clock
        self.cooldown_expira_em = None
        self.janela = []

    def lock(self, _chave, timeout=None):
        return LockFalso()

    def pttl(self, _chave):
        if self.cooldown_expira_em is None:
            return -2
        return int(max(0, self.cooldown_expira_em - self.clock()) * 1000)

    def set(self, _chave, _valor, px):
        expiracao = self.clock() + px / 1000
        if self.cooldown_expira_em is None or expiracao > self.cooldown_expira_em:
            self.cooldown_expira_em = expiracao

    def zremrangebyscore(self, _chave, _inicio, fim):
        self.janela = [tempo for tempo in self.janela if tempo >= fim]

    def zcard(self, _chave):
        return len(self.janela)

    def zadd(self, _chave, valores):
        self.janela.extend(valores.values())

    def expire(self, *_args):
        pass

    def zrange(self, _chave, _inicio, _fim, withscores=False):
        if not self.janela or not withscores:
            return []
        return [("slot", min(self.janela))]


class Relogio:
    def __init__(self):
        self.agora = 1_000_000.0
        self.esperas = []

    def now(self):
        return self.agora

    def sleep(self, segundos):
        self.esperas.append(segundos)
        self.agora += segundos


class InstanciaFalsa:
    slug = "ekk-brindes"
    access_token = "token-nao-real"
    rate_limit_por_minuto = None


def resposta(status=200, headers=None):
    resultado = Mock()
    resultado.status_code = status
    resultado.headers = headers or {}
    resultado.json.return_value = {}
    resultado.text = ""
    return resultado


class TinyRateLimitUnitTests(SimpleTestCase):
    @override_settings(TINY_API_BASE_URL="https://tiny.invalid")
    def test_limite_none_usa_fallback_30_sem_persistir(self):
        cliente = TinyApiClient(InstanciaFalsa(), limiter=Mock())
        self.assertEqual(cliente._limite_para_o_limiter(), TINY_V3_RATE_LIMIT_FALLBACK)
        self.assertIsNone(cliente.instancia.rate_limit_por_minuto)

    def test_margem_efetiva_continua_em_80_por_cento(self):
        relogio = Relogio()
        redis = RedisFalso(relogio.now)
        limiter = RateLimiterCompartilhado(
            "ekk-brindes", cliente=redis, sleep_fn=relogio.sleep, clock_fn=relogio.now
        )
        for _ in range(24):
            limiter.aguardar_vaga(30)
        self.assertEqual(redis.zcard("tiny:ratelimit:ekk-brindes"), int(30 * MARGEM_SEGURANCA))

    @override_settings(TINY_API_BASE_URL="https://tiny.invalid")
    @patch("apps.instancias.tiny_client.requests.request")
    def test_limite_real_descoberto_substitui_fallback(self, request):
        request.return_value = resposta(200, {"x-limit-api": "120"})
        limiter = Mock()
        cliente = TinyApiClient(
            InstanciaFalsa(), limiter=limiter, sleep_fn=lambda _: None, somente_leitura=True
        )
        cliente.get("/produtos")
        self.assertEqual(limiter.aguardar_vaga.call_args.args, (30,))
        self.assertEqual(cliente._limite_para_o_limiter(), 120)

    def test_outra_chamada_respeita_cooldown_compartilhado(self):
        relogio = Relogio()
        redis = RedisFalso(relogio.now)
        primeiro = RateLimiterCompartilhado(
            "ekk-brindes", cliente=redis, sleep_fn=relogio.sleep, clock_fn=relogio.now
        )
        segundo = RateLimiterCompartilhado(
            "ekk-brindes", cliente=redis, sleep_fn=relogio.sleep, clock_fn=relogio.now
        )
        primeiro.registrar_cooldown(5)
        segundo.aguardar_vaga(None)
        self.assertGreaterEqual(relogio.esperas[0], 5)

    @override_settings(TINY_API_BASE_URL="https://tiny.invalid")
    @patch("apps.instancias.tiny_client.requests.request")
    def test_retry_after_e_cria_cooldown_compartilhado(self, request):
        request.side_effect = [resposta(429, {"Retry-After": "5"}), resposta(200)]
        limiter = Mock()
        cliente = TinyApiClient(InstanciaFalsa(), limiter=limiter, sleep_fn=lambda _: None)
        cliente.get("/produtos")
        limiter.registrar_cooldown.assert_called_once_with(5.0)
        self.assertEqual(request.call_count, 2)
