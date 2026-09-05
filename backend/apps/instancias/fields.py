"""
Campos de modelo reutilizáveis que criptografam o valor em repouso com
Fernet (criptografia simétrica autenticada da lib `cryptography`).

Usados por Instancia (client_secret, access_token, refresh_token) e por
CredencialFornecedor (credenciais), porque nenhum desses valores pode ficar
em texto puro no banco.
"""

import json
from functools import lru_cache

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import models


@lru_cache(maxsize=1)
def _fernet() -> Fernet:
    chave = getattr(settings, "FERNET_KEY", None)
    if not chave:
        raise ImproperlyConfigured(
            "FERNET_KEY não configurada no ambiente — necessária para "
            "criptografar/descriptografar credenciais."
        )
    if isinstance(chave, str):
        chave = chave.encode("utf-8")
    return Fernet(chave)


class EncryptedFieldMixin:
    """
    Cifra o valor antes de gravar no banco e decifra ao ler de volta.
    Subclasses só precisam implementar `_serializar`/`_desserializar` para
    definir como o valor Python vira string (e volta).
    """

    def _serializar(self, valor):
        raise NotImplementedError

    def _desserializar(self, texto):
        raise NotImplementedError

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or value == "":
            return value
        texto_plano = self._serializar(value)
        token = _fernet().encrypt(texto_plano.encode("utf-8"))
        return token.decode("utf-8")

    def from_db_value(self, value, expression, connection):
        if value is None or value == "":
            return value
        try:
            texto_plano = _fernet().decrypt(value.encode("utf-8")).decode("utf-8")
        except InvalidToken as exc:
            raise ImproperlyConfigured(
                "Não foi possível descriptografar um valor cifrado — "
                "verifique se FERNET_KEY é a mesma usada para gravá-lo."
            ) from exc
        return self._desserializar(texto_plano)


class EncryptedTextField(EncryptedFieldMixin, models.TextField):
    """Texto simples criptografado em repouso (ex.: tokens do Tiny)."""

    def _serializar(self, valor):
        return str(valor)

    def _desserializar(self, texto):
        return texto


class EncryptedJSONField(EncryptedFieldMixin, models.TextField):
    """
    JSON criptografado em repouso. A coluna no banco é TEXT (o conteúdo
    cifrado não é JSON válido), mas o valor em Python é sempre dict/list.
    """

    description = "JSON criptografado em repouso"

    def _serializar(self, valor):
        return json.dumps(valor)

    def _desserializar(self, texto):
        return json.loads(texto)

    def to_python(self, value):
        if value is None or isinstance(value, (dict, list)):
            return value
        try:
            return json.loads(value)
        except (TypeError, ValueError):
            return value
