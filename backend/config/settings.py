"""
Configurações do Django. Tudo o que muda entre ambientes ou é sensível
vem de variável de ambiente — nenhum valor sensível é escrito aqui.
"""

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def env(chave, padrao=None, obrigatoria=False):
    valor = os.environ.get(chave, padrao)
    if obrigatoria and (valor is None or valor == ""):
        raise RuntimeError(f"Variável de ambiente obrigatória não definida: {chave}")
    return valor


def env_bool(chave, padrao=False):
    valor = os.environ.get(chave)
    if valor is None:
        return padrao
    return valor.strip().lower() in ("1", "true", "sim", "yes")


def env_list(chave, padrao=""):
    valor = env(chave, padrao) or ""
    return [item.strip() for item in valor.split(",") if item.strip()]


SECRET_KEY = env("DJANGO_SECRET_KEY", obrigatoria=True)
DEBUG = env_bool("DJANGO_DEBUG", False)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")

# Chave simétrica (Fernet) usada para criptografar credenciais em repouso.
# Ver apps/instancias/fields.py.
FERNET_KEY = env("FERNET_KEY", obrigatoria=True)

# OAuth2/Keycloak do Tiny. TOKEN_URL veio da especificação do cliente;
# AUTHORIZE_URL foi inferido do padrão do Keycloak (mesmo realm, troca
# "token" por "auth") — confirmar antes de produção. Ambos configuráveis
# por env para não exigir mudança de código se a inferência estiver errada.
TINY_OAUTH_TOKEN_URL = env(
    "TINY_OAUTH_TOKEN_URL",
    "https://accounts.tiny.com.br/realms/tiny/protocol/openid-connect/token",
)
TINY_OAUTH_AUTHORIZE_URL = env(
    "TINY_OAUTH_AUTHORIZE_URL",
    "https://accounts.tiny.com.br/realms/tiny/protocol/openid-connect/auth",
)

# API "de negócio" do Tiny (produtos, estoque, etc). Confirmada contra a
# referência oficial (https://api-docs.erp.olist.com/api-reference/produtos/criar-produto.md)
# no passo 6 — o spec declara "servers: https://api.tiny.com.br/public-api/v3".
# O passo 5 tinha usado erp.tiny.com.br por instrução explícita da época;
# corrigido aqui para a URL que o próprio spec oficial declara.
TINY_API_BASE_URL = env("TINY_API_BASE_URL", "https://api.tiny.com.br/public-api/v3")

# Redis: broker/result-backend do Celery (db 0) e store do throttle
# compartilhado do TinyApiClient (db 1) — mesma instância, DBs lógicos
# separados para não misturar chaves.
REDIS_URL = env("REDIS_URL", "redis://redis:6379")
CELERY_BROKER_URL = f"{REDIS_URL}/0"
CELERY_RESULT_BACKEND = f"{REDIS_URL}/0"
CELERY_TIMEZONE = "America/Sao_Paulo"
CELERY_TASK_TRACK_STARTED = True
TINY_THROTTLE_REDIS_URL = f"{REDIS_URL}/1"

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",
    "rest_framework",
    "rest_framework.authtoken",
    "drf_spectacular",
    "apps.contas",
    "apps.instancias",
    "apps.catalogo",
    "apps.sincronizacao",
    "apps.fornecedores",
    "apps.dashboard",
]

# Passo 8: e-mail único como identificador de autenticação — substitui o
# auth.User padrão (username) por apps.contas.Usuario.
AUTH_USER_MODEL = "contas.Usuario"

# Passo 5: toda a API exige autenticação por token, exceto o callback do
# Tiny e os endpoints de login (que sobrescrevem authentication/permission
# classes explicitamente) porque quem chama ainda não tem um token nosso.
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
}

SPECTACULAR_SETTINGS = {
    "TITLE": "brindes-automa-tiny API",
    "DESCRIPTION": "Espelho de catálogo dos fornecedores e sincronização com o Tiny.",
    "VERSION": "1.0.0",
    "SERVE_PERMISSIONS": ["rest_framework.permissions.AllowAny"],
    # Vários serializers (dashboard, listagem de instâncias) têm um campo
    # "fornecedor"/"xbz"/"asia"/etc. reaproveitando as mesmas choices —
    # sem isso, o drf-spectacular nomeia o enum gerado de forma inconsistente
    # entre eles (ex.: "AsiaEnum") em vez de reconhecer que é o mesmo enum.
    "ENUM_NAME_OVERRIDES": {
        "FornecedorEnum": "apps.instancias.constants.Fornecedor.choices",
        "CorFornecedorEnum": "apps.instancias.serializers.CORES_FORNECEDOR",
    },
}

# Passo 7: o frontend (Next.js) roda numa origem diferente. Só precisa
# valer para o próprio app — nenhuma lista aberta ("allow all").
CORS_ALLOWED_ORIGINS = env_list("CORS_ALLOWED_ORIGINS", "http://localhost:3000")
CORS_ALLOW_CREDENTIALS = True

# Passo 9: atrás do Traefik, que termina o TLS — sem isso o Django vê a
# requisição como HTTP puro (Referer/Origin dizem https, request.is_secure()
# diria false) e rejeita POSTs do admin com "CSRF verification failed".
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
CSRF_TRUSTED_ORIGINS = env_list(
    "DJANGO_CSRF_TRUSTED_ORIGINS", "https://sync-api.automasoluct.com.br"
)

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": env("POSTGRES_DB", obrigatoria=True),
        "USER": env("POSTGRES_USER", obrigatoria=True),
        "PASSWORD": env("POSTGRES_PASSWORD", obrigatoria=True),
        "HOST": env("POSTGRES_HOST", "db"),
        "PORT": env("POSTGRES_PORT", "5432"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "pt-br"
TIME_ZONE = "America/Sao_Paulo"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
# Coletado no build da imagem (ver Dockerfile) e servido pelo WhiteNoise —
# não há nginx/servidor de estáticos separado nesta stack.
STATIC_ROOT = BASE_DIR / "staticfiles"
STORAGES = {
    "default": {"BACKEND": "django.core.files.storage.FileSystemStorage"},
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
