"""
Controle de taxa compartilhado entre processos, via Redis.

Antes do passo 5, o throttle do TinyApiClient vivia em memória, num
`deque` por instância *de processo Python*. Isso funcionava enquanto só o
servidor Django chamava o Tiny. A partir do momento em que o worker do
Celery passou a rodar em paralelo (mesma conta do Tiny, mesmo
`x-limit-api` — o limite é por conta, não por processo/aplicativo
nosso), cada processo contaria suas próprias chamadas separadamente e,
juntos, estourariam o teto real da conta do cliente sem que nenhum dos
dois percebesse.

A janela deslizante agora vive num sorted set do Redis (score = timestamp
da chamada), com um lock por instância (`redis.lock`) protegendo só o
trecho "verificar espaço e reservar uma vaga" — o processo NUNCA dorme
segurando o lock, para não travar os outros enquanto espera.
"""

import time
import uuid
import math

import redis
from django.conf import settings

JANELA_SEGUNDOS = 60
MARGEM_SEGURANCA = 0.8
TIMEOUT_LOCK_SEGUNDOS = 10
ESPERA_MINIMA_SEGUNDOS = 0.05
CHAVE_COOLDOWN = "tiny:ratelimit-cooldown:{slug}"


def cliente_redis():
    return redis.Redis.from_url(settings.TINY_THROTTLE_REDIS_URL, decode_responses=True)


class RateLimiterCompartilhado:
    """Uma instância por Instancia (identificada pelo slug) — mas o estado real está no Redis."""

    def __init__(self, instancia_slug, cliente=None, sleep_fn=time.sleep, clock_fn=time.time):
        self.slug = instancia_slug
        self.redis = cliente or cliente_redis()
        self._sleep = sleep_fn
        self._clock = clock_fn
        self._chave_janela = f"tiny:ratelimit:{instancia_slug}"
        self._chave_lock = f"tiny:ratelimit-lock:{instancia_slug}"
        self._chave_cooldown = CHAVE_COOLDOWN.format(slug=instancia_slug)

    def aguardar_vaga(self, limite_por_minuto):
        """Bloqueia até haver espaço, incluindo cooldown compartilhado de 429."""
        teto = max(1, int(limite_por_minuto * MARGEM_SEGURANCA)) if limite_por_minuto else None

        while True:
            cooldown = self._cooldown_restante()
            if cooldown > 0:
                self._sleep(cooldown)
                continue
            if teto is None:
                return
            espera = self._tentar_reservar_vaga(teto)
            if espera is None:
                return
            self._sleep(max(espera, ESPERA_MINIMA_SEGUNDOS))

    def registrar_cooldown(self, segundos):
        """Publica um cooldown de 429 para todos os processos da instância."""
        milissegundos = max(1_000, math.ceil(float(segundos) * 1_000))
        lock = self.redis.lock(self._chave_lock, timeout=TIMEOUT_LOCK_SEGUNDOS)
        with lock:
            atual = self.redis.pttl(self._chave_cooldown)
            if atual < milissegundos:
                self.redis.set(self._chave_cooldown, "1", px=milissegundos)

    def _cooldown_restante(self):
        restante = self.redis.pttl(self._chave_cooldown)
        if restante <= 0:
            return 0
        return restante / 1_000

    def _tentar_reservar_vaga(self, teto):
        """Retorna None se conseguiu reservar a vaga; senão, quantos segundos esperar."""
        lock = self.redis.lock(self._chave_lock, timeout=TIMEOUT_LOCK_SEGUNDOS)
        with lock:
            agora = self._clock()
            self.redis.zremrangebyscore(self._chave_janela, 0, agora - JANELA_SEGUNDOS)
            contagem = self.redis.zcard(self._chave_janela)
            if contagem < teto:
                self.redis.zadd(self._chave_janela, {str(uuid.uuid4()): agora})
                self.redis.expire(self._chave_janela, JANELA_SEGUNDOS * 2)
                return None
            mais_antiga = self.redis.zrange(self._chave_janela, 0, 0, withscores=True)
            if not mais_antiga:
                return ESPERA_MINIMA_SEGUNDOS
            return JANELA_SEGUNDOS - (agora - mais_antiga[0][1])
