from apps.instancias.constants import Fornecedor

from .asia import AsiaFornecedor
from .somarcas import SomarcasFornecedor
from .spot import SpotFornecedor
from .xbz import XbzFornecedor

REGISTRY = {
    Fornecedor.XBZ: XbzFornecedor,
    Fornecedor.ASIA: AsiaFornecedor,
    Fornecedor.SOMARCAS: SomarcasFornecedor,
    Fornecedor.SPOT: SpotFornecedor,
}


def obter_cliente(fornecedor: str, *, configuracao: dict | None = None):
    try:
        classe = REGISTRY[fornecedor]
    except KeyError:
        raise ValueError(f"Fornecedor desconhecido: {fornecedor!r}") from None
    return classe(configuracao=configuracao)
