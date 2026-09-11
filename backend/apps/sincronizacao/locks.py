"""Locks de sessão para operações externas por instância e fornecedor."""

import hashlib
from contextlib import contextmanager

from django.db import connection


def _lock_key(instancia_id, fornecedor):
    """Converte a chave lógica em um bigint estável aceito pelo PostgreSQL."""
    bruto = f"fornecedor:{instancia_id}:{fornecedor}".encode()
    return int.from_bytes(hashlib.blake2b(bruto, digest_size=8).digest(), "big", signed=True)


def _lock_key_instancia_tiny(instancia_id):
    """Chave estável da conta Tiny de uma instância, separada do lock de importação."""
    bruto = f"tiny-instancia:{instancia_id}".encode()
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


@contextmanager
def lock_instancia_tiny(instancia_id):
    """Exclusividade de escrita na conta Tiny de uma instância.

    É deliberadamente separado de ``lock_fornecedor``: imports podem continuar
    paralelos entre fornecedores, enquanto qualquer escrita no Tiny da mesma
    instância é serializada. O lock de sessão é liberado no ``finally`` e pelo
    PostgreSQL quando a conexão do worker morre.
    """
    if connection.vendor != "postgresql":
        raise RuntimeError("lock_instancia_tiny exige PostgreSQL")

    chave = _lock_key_instancia_tiny(instancia_id)
    with connection.cursor() as cursor:
        cursor.execute("SELECT pg_try_advisory_lock(%s)", [chave])
        adquirida = bool(cursor.fetchone()[0])
    try:
        yield adquirida
    finally:
        if adquirida:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_advisory_unlock(%s)", [chave])
