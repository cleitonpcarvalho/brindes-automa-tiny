"""Locks de sessão para operações externas por instância e fornecedor."""

import hashlib
from contextlib import contextmanager

from django.db import connection


def _lock_key(instancia_id, fornecedor):
    """Converte a chave lógica em um bigint estável aceito pelo PostgreSQL."""
    bruto = f"fornecedor:{instancia_id}:{fornecedor}".encode()
    return int.from_bytes(hashlib.blake2b(bruto, digest_size=8).digest(), "big", signed=True)


@contextmanager
def lock_fornecedor(instancia_id, fornecedor):
    """Adquire lock PostgreSQL por par e o libera mesmo após erro.

    É um advisory lock de sessão, não um lock transacional: a conexão fica
    aberta durante a chamada externa, mas nenhuma transação fica aberta. O
    PostgreSQL libera a trava automaticamente se o processo morrer.
    """
    if connection.vendor != "postgresql":
        raise RuntimeError("lock_fornecedor exige PostgreSQL")

    chave = _lock_key(instancia_id, fornecedor)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [chave])
        adquirida = bool(cursor.fetchone()[0])
    try:
        yield adquirida
    finally:
        if adquirida:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [chave])
