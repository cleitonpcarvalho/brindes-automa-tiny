"""
Constantes compartilhadas entre apps (instancias, catalogo, sincronizacao).

Vivem aqui porque CredencialFornecedor (app instancias) já precisa dessas
choices, e catalogo/sincronizacao apenas reaproveitam — evita um app extra
só para constantes e evita import circular (instancias não depende de
catalogo nem de sincronizacao).
"""

from django.db import models


class Fornecedor(models.TextChoices):
    XBZ = "xbz", "XBZ"
    ASIA = "asia", "Asia Import"
    SOMARCAS = "somarcas", "Só Marcas"
    SPOT = "spot", "Spot Gifts"


# Chaves aceitas em CredencialFornecedor.credenciais por fornecedor (passo 10),
# confirmadas contra o que cada normalizador de fato lê (apps/fornecedores/
# {xbz,asia,somarcas,spot}.py) — não contra a especificação original, que em
# algum ponto citava "client_id" para a spot por engano (o código só usa
# access_key). "sensivel" decide se o campo volta mascarado nas respostas da
# API (ver apps/instancias/mascaramento.py): CNPJ e usuário são identificadores
# que o operador precisa conferir, não segredos — só token/senha/chaves de API
# são mascarados.
CAMPOS_POR_FORNECEDOR = {
    Fornecedor.XBZ: {
        "cnpj": {"obrigatorio": True, "sensivel": False},
        "token": {"obrigatorio": True, "sensivel": True},
    },
    Fornecedor.ASIA: {
        "api_key": {"obrigatorio": True, "sensivel": True},
        "secret_key": {"obrigatorio": True, "sensivel": True},
    },
    Fornecedor.SOMARCAS: {
        "usuario": {"obrigatorio": True, "sensivel": False},
        "senha": {"obrigatorio": True, "sensivel": True},
        "estado": {"obrigatorio": False, "sensivel": False},
    },
    Fornecedor.SPOT: {
        "access_key": {"obrigatorio": True, "sensivel": True},
    },
}
