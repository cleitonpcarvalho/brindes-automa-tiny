import uuid

from django.test import TestCase

from ..tiny_throttle import RateLimiterCompartilhado, cliente_redis


class RelogioCompartilhado:
    """Simula o tempo passando igualmente para dois processos diferentes."""

    def __init__(self):
        self.t = 1_000_000.0

    def agora(self):
        return self.t

    def dormir(self, segundos):
        self.t += segundos


class ThrottleCompartilhadoEntreProcessosTests(TestCase):
    """
    Regra: o limite do Tiny é por CONTA, não por processo. Dois
    `RateLimiterCompartilhado` distintos (simulando o servidor Django e um
    worker do Celery) apontando para o mesmo slug precisam enxergar e
    respeitar o MESMO teto combinado — nunca 80% cada um separadamente.
    """

    def setUp(self):
        self.slug = f"teste-throttle-{uuid.uuid4().hex[:8]}"
        self.redis = cliente_redis()
        self.addCleanup(self._limpar_redis)

    def _limpar_redis(self):
        self.redis.delete(f"tiny:ratelimit:{self.slug}")
        self.redis.delete(f"tiny:ratelimit-lock:{self.slug}")

    def _limiter(self, relogio):
        return RateLimiterCompartilhado(
            self.slug, cliente=self.redis, sleep_fn=relogio.dormir, clock_fn=relogio.agora
        )

    def test_dois_processos_dividem_o_mesmo_teto_efetivo(self):
        relogio = RelogioCompartilhado()
        processo_django = self._limiter(relogio)
        processo_worker = self._limiter(relogio)

        limite = 10  # teto efetivo = 8 (80%)

        for _ in range(4):
            processo_django.aguardar_vaga(limite)
        for _ in range(4):
            processo_worker.aguardar_vaga(limite)

        # 4 + 4 = 8 = exatamente o teto: nenhuma das 8 primeiras esperou
        self.assertEqual(relogio.t, 1_000_000.0)

        # a 9ª chamada combinada, não importa de qual processo, precisa esperar
        processo_django.aguardar_vaga(limite)
        self.assertGreater(relogio.t, 1_000_000.0)

    def test_janela_libera_espaco_depois_de_60_segundos(self):
        relogio = RelogioCompartilhado()
        processo_a = self._limiter(relogio)
        processo_b = self._limiter(relogio)

        limite = 2  # teto efetivo = 1 (80% de 2, arredondado para baixo com mínimo 1)

        processo_a.aguardar_vaga(limite)  # ocupa a única vaga
        tempo_antes = relogio.t

        processo_b.aguardar_vaga(limite)  # precisa esperar a vaga expirar da janela

        self.assertGreaterEqual(relogio.t - tempo_antes, 59)

    def test_sem_limite_conhecido_nao_bloqueia_nenhum_processo(self):
        relogio = RelogioCompartilhado()
        processo_a = self._limiter(relogio)
        processo_b = self._limiter(relogio)

        for _ in range(100):
            processo_a.aguardar_vaga(None)
            processo_b.aguardar_vaga(None)

        self.assertEqual(relogio.t, 1_000_000.0)
