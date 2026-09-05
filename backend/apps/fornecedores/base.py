"""
Contrato comum aos quatro fornecedores.

Cada fornecedor implementa `buscar()` (fala com a API externa e devolve o
payload bruto, sem transformar nada) e `normalizar()` (converte esse
payload — em qualquer formato de origem — sempre na mesma forma canônica:
uma lista de ProdutoNormalizado, cada um com sua lista de
VariacaoNormalizada). O comando de importação (management command
`importar_fornecedor`) só conhece essa forma canônica — não sabe nada
sobre XBZ, Asia, Só Marcas ou Spot especificamente.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation

from django.utils import timezone


def to_decimal(valor) -> Decimal:
    """Converte um valor numérico bruto do fornecedor (str/int/float) em Decimal."""
    if valor is None or valor == "":
        return Decimal("0")
    if isinstance(valor, Decimal):
        return valor
    texto = str(valor).strip().replace(",", ".")
    try:
        return Decimal(texto)
    except InvalidOperation:
        return Decimal("0")


def parse_data(valor, formato: str):
    """Faz parse de uma data em texto no formato informado; devolve datetime com timezone (ou None)."""
    if not valor:
        return None
    try:
        ingenua = datetime.strptime(valor, formato)
    except (ValueError, TypeError):
        return None
    return timezone.make_aware(ingenua) if timezone.is_naive(ingenua) else ingenua


def parse_numero_br(valor) -> float | None:
    """Converte um número em formato brasileiro (vírgula decimal) numa string para float."""
    if valor is None or valor == "":
        return None
    if isinstance(valor, (int, float)):
        return float(valor)
    texto = str(valor).strip().replace(",", ".")
    try:
        return float(texto)
    except ValueError:
        return None


@dataclass
class DimensoesNormalizadas:
    """
    Sempre normalizado para o par de unidades que o Tiny usa na prática
    (mesma convenção da própria tela de cadastro de produto do Tiny, não
    documentada no schema da API): centímetros para medidas lineares,
    quilogramas para peso. Cada fornecedor entrega isso de um jeito
    diferente — a conversão fica documentada em cada normalizador
    (apps/fornecedores/{xbz,asia,somarcas,spot}.py).
    """

    largura: float | None = None
    altura: float | None = None
    comprimento: float | None = None
    diametro: float | None = None
    peso_liquido: float | None = None
    peso_bruto: float | None = None

    def vazio(self) -> bool:
        return all(
            v is None
            for v in (self.largura, self.altura, self.comprimento, self.diametro, self.peso_liquido, self.peso_bruto)
        )


@dataclass
class VariacaoNormalizada:
    sku: str
    nome: str
    preco: Decimal
    estoque: int = 0
    ncm: str = ""
    cor: str = ""
    tamanho: str = ""
    capacidade: str = ""
    imagens: list = field(default_factory=list)
    atributos: dict = field(default_factory=dict)
    dimensoes: DimensoesNormalizadas = field(default_factory=DimensoesNormalizadas)
    payload_bruto: dict = field(default_factory=dict)


@dataclass
class ProdutoNormalizado:
    codigo_pai: str
    nome: str
    descricao: str = ""
    categorias: list = field(default_factory=list)
    imagens: list = field(default_factory=list)
    atributos: dict = field(default_factory=dict)
    atualizado_em_fornecedor: object = None  # datetime | None
    payload_bruto: dict = field(default_factory=dict)
    variacoes: list = field(default_factory=list)  # list[VariacaoNormalizada]


class FornecedorBase(ABC):
    """Classe abstrata que todo cliente/normalizador de fornecedor implementa."""

    codigo: str

    def __init__(self, configuracao: dict | None = None):
        # Configuração não sensível por fornecedor (ex.: url_base_imagens da
        # Spot). Credenciais NUNCA passam por aqui — elas vão como
        # argumento de buscar(), vindas de CredencialFornecedor.
        self.configuracao = configuracao or {}

    @abstractmethod
    def buscar(self, credenciais: dict):
        """Busca o payload bruto na API do fornecedor. Só faz chamadas de rede aqui."""

    @abstractmethod
    def normalizar(self, payload_bruto) -> list[ProdutoNormalizado]:
        """Converte o payload bruto na forma canônica. Não faz nenhuma chamada de rede."""
