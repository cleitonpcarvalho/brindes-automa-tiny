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
