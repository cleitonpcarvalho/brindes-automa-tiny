# Imagem de produção. Backend, worker e beat compartilham a imagem final —
# worker/beat só sobrescrevem o CMD com `command:` no stack.yml.
#
# `base` é o estágio reaproveitado pelo docker-compose.yml de dev (build
# com `target: base`) — dependências via Poetry, código montado por bind
# mount, roda como root com `runserver` (hot reload). Produção continua a
# partir dele até o estágio `final`, sem bind mount, sem dev tooling.
#
# O venv fica em /opt/venv, fora de /app, de propósito: o dev monta
# ./backend por cima de /app (bind mount) — se o venv estivesse dentro de
# /app, o mount escondia os pacotes instalados e nada no PATH funcionava.

FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    POETRY_VIRTUALENVS_CREATE=false \
    POETRY_NO_INTERACTION=1 \
    VIRTUAL_ENV=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

RUN python -m venv /opt/venv && /usr/local/bin/pip install --no-cache-dir "poetry==2.2.1"

WORKDIR /app

COPY pyproject.toml poetry.lock ./
RUN poetry install --no-root --only main

COPY . .

EXPOSE 8000
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]


FROM base AS builder

# collectstatic só lê settings, não conecta no banco/Redis — os valores
# abaixo existem apenas para satisfazer as variáveis obrigatórias do
# settings.py durante o build; nunca chegam à imagem final nem são usados
# em runtime (lá quem manda são as variáveis reais da stack).
RUN DJANGO_SECRET_KEY=build-time-placeholder \
    FERNET_KEY=build-time-placeholder \
    POSTGRES_DB=build POSTGRES_USER=build POSTGRES_PASSWORD=build \
    python manage.py collectstatic --noinput


FROM python:3.12-slim AS final

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/opt/venv/bin:$PATH"

RUN groupadd --system app && useradd --system --gid app --home /app app

WORKDIR /app
COPY --from=builder --chown=app:app /opt/venv /opt/venv
COPY --from=builder --chown=app:app /app /app

USER app

EXPOSE 8000

# GUNICORN_WORKERS/GUNICORN_TIMEOUT vêm do ambiente do container em runtime
# (não do Compose) — forma shell do CMD para que ${...} seja expandido pelo
# /bin/sh na hora de subir, com um valor padrão sensato caso não seja definida.
CMD gunicorn config.wsgi:application \
    --bind 0.0.0.0:8000 \
    --workers ${GUNICORN_WORKERS:-3} \
    --timeout ${GUNICORN_TIMEOUT:-60} \
    --access-logfile - \
    --error-logfile -
