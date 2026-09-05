"""
Healthcheck de infraestrutura (usado pelo HEALTHCHECK do Swarm, não pelo
frontend nem por nenhum cliente da API) — verifica banco e Redis, não
autentica, não passa pelo DRF.
"""

import redis
from django.conf import settings
from django.db import connection
from django.http import JsonResponse


def health(request):
    checks = {"database": False, "redis": False}

    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
        checks["database"] = True
    except Exception:
        pass

    try:
        redis.Redis.from_url(settings.REDIS_URL, socket_connect_timeout=2).ping()
        checks["redis"] = True
    except Exception:
        pass

    saudavel = all(checks.values())
    return JsonResponse(
        {"status": "ok" if saudavel else "error", "checks": checks},
        status=200 if saudavel else 503,
    )
