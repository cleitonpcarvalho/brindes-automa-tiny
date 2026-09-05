import hashlib
import json

from django.db import models

from apps.instancias.constants import Fornecedor
from apps.instancias.models import Instancia


def calcular_hash_conteudo(payload_bruto):
    """
    Hash estável do payload bruto, para detectar mudança sem comparar JSON
    inteiro. Público (não `_hash_conteudo`) porque o comando de importação
    (apps/fornecedores) precisa calcular o mesmo hash de um payload novo
    para decidir se uma Variacao mudou antes de gravar.
    """
    serializado = json.dumps(payload_bruto, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.sha256(serializado.encode("utf-8")).hexdigest()


class Produto(models.Model):
    """
    Produto-pai: o agrupador de variações de um fornecedor. Não é cadastrado
    no Tiny diretamente — quem vira produto no Tiny é a Variacao (ver regra
    de negócio nº 1, comentada em Variacao).
    """

    # Regra do cliente (XBZ): produtos cujo codigo_pai começa com "P@" estão
    # saindo de linha e nunca devem ser cadastrados no Tiny. É um prefixo,
    # não "contém @ em qualquer posição" — na amostra de referência
    # (samples/xbz/produtos_*.json) o filtro por prefixo bate 661 registros
    # em 279 produtos-pai distintos; um filtro ingênuo por "contém @" pegaria
    # 876, então a distinção importa.
    PREFIXO_XBZ_SAINDO_DE_LINHA = "P@"

    instancia = models.ForeignKey(Instancia, on_delete=models.CASCADE, related_name="produtos")
    fornecedor = models.CharField(max_length=20, choices=Fornecedor.choices)
    codigo_pai = models.CharField(
        max_length=64,
        help_text="Código do produto-pai no fornecedor "
        "(CodigoAmigavel na xbz, referencia na asia, ProdReference na spot).",
    )
    nome = models.CharField(max_length=500)
    descricao = models.TextField(blank=True)
    categorias = models.JSONField(default=list, blank=True)
    imagens = models.JSONField(default=list, blank=True)
    atributos = models.JSONField(default=dict, blank=True)

    ativo = models.BooleanField(default=True)
    descontinuado = models.BooleanField(
        default=False,
        help_text="Descarte permanente (ex.: regra do prefixo P@ da xbz). "
        "Diferente de 'estoque zero' (ver Variacao.status).",
    )
    atualizado_em_fornecedor = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Só preenchido quando o fornecedor informa data de atualização "
        "(hoje, apenas a Spot manda isso — ver samples/RELATORIO.md).",
    )

    payload_bruto = models.JSONField(default=dict, blank=True)
    hash_conteudo = models.CharField(max_length=64, blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Produto"
        verbose_name_plural = "Produtos"
        constraints = [
            models.UniqueConstraint(
                fields=["instancia", "fornecedor", "codigo_pai"],
                name="unico_produto_por_instancia_fornecedor_codigo_pai",
            )
        ]
        indexes = [
            models.Index(fields=["fornecedor", "codigo_pai"]),
        ]

    def __str__(self):
        return f"[{self.fornecedor}] {self.codigo_pai} · {self.nome}"

    def esta_saindo_de_linha(self):
        """Regra do cliente: prefixo "P@" no codigo_pai da xbz = saindo de linha."""
        return self.fornecedor == Fornecedor.XBZ and self.codigo_pai.startswith(
            self.PREFIXO_XBZ_SAINDO_DE_LINHA
        )

    def save(self, *args, **kwargs):
        if self.esta_saindo_de_linha():
            self.descontinuado = True
        if self.payload_bruto:
            self.hash_conteudo = calcular_hash_conteudo(self.payload_bruto)
        super().save(*args, **kwargs)


class StatusVariacao(models.TextChoices):
    PENDENTE = "pendente", "Pendente"
    AGUARDANDO = "aguardando", "Aguardando reposição"
    CADASTRADO = "cadastrado", "Cadastrado no Tiny"
    DESCONTINUADO = "descontinuado", "Descontinuado"
    ERRO = "erro", "Erro ao cadastrar"


class Variacao(models.Model):
    """
    O SKU. É esta entidade — não o Produto — que vira um produto no Tiny.

    Regra do cliente nº 1: cada cor ou tamanho é uma Variacao própria e vira
    um produto separado no Tiny (pedido explícito do cliente). Por isso não
    existe "produto com variações" no sentido do Tiny — cada linha aqui é
    uma unidade cadastrável independente, com seu próprio ciclo de vida
    (status, tiny_id, cadastrado_em) e seu próprio SKU único dentro do
    produto-pai.
    """

    produto = models.ForeignKey(Produto, on_delete=models.CASCADE, related_name="variacoes")
    sku = models.CharField(max_length=64)
    nome = models.CharField(max_length=500)
    ncm = models.CharField(
        max_length=20,
        blank=True,
        help_text="NCM brasileiro. Na Spot, o único campo fiscal disponível é o "
        "'Taric', que NÃO é confirmado como equivalente ao NCM — o normalizador "
        "da Spot (apps/fornecedores/spot.py) deixa este campo vazio e guarda o "
        "Taric em atributos, sem inventar conversão (ver pendências no README).",
    )
    preco = models.DecimalField(max_digits=10, decimal_places=2)
    estoque = models.IntegerField(default=0)

    cor = models.CharField(max_length=100, blank=True)
    tamanho = models.CharField(max_length=100, blank=True)
    capacidade = models.CharField(max_length=100, blank=True)

    # Dimensões normalizadas para o par de unidades que o Tiny usa (cm/kg —
    # ver apps/fornecedores/base.py:DimensoesNormalizadas para a conversão
    # de cada fornecedor). Nulo = fornecedor não informou de forma confiável.
    largura = models.FloatField(null=True, blank=True, help_text="Centímetros.")
    altura = models.FloatField(null=True, blank=True, help_text="Centímetros.")
    comprimento = models.FloatField(null=True, blank=True, help_text="Centímetros.")
    diametro = models.FloatField(null=True, blank=True, help_text="Centímetros.")
    peso_liquido = models.FloatField(null=True, blank=True, help_text="Quilogramas.")
    peso_bruto = models.FloatField(null=True, blank=True, help_text="Quilogramas.")

    imagens = models.JSONField(default=list, blank=True)
    atributos = models.JSONField(default=dict, blank=True)
    payload_bruto = models.JSONField(default=dict, blank=True)
    hash_conteudo = models.CharField(max_length=64, blank=True)

    status = models.CharField(
        max_length=20, choices=StatusVariacao.choices, default=StatusVariacao.PENDENTE
    )
    tiny_id = models.CharField(max_length=64, null=True, blank=True)
    ultimo_erro = models.TextField(blank=True)
    cadastrado_em = models.DateTimeField(null=True, blank=True)
    estoque_tiny_sincronizado = models.IntegerField(
        null=True,
        blank=True,
        help_text="Último valor de estoque efetivamente enviado ao Tiny. Enquanto for "
        "diferente de `estoque` (ou nulo), o comando de atualização de estoque "
        "considera esta variação pendente de sincronização.",
    )

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Variação"
        verbose_name_plural = "Variações"
        constraints = [
            models.UniqueConstraint(fields=["produto", "sku"], name="unico_sku_por_produto")
        ]
        indexes = [
            models.Index(fields=["status"]),
            models.Index(fields=["sku"]),
        ]

    def __str__(self):
        return f"{self.sku} · {self.nome}"

    @property
    def preco_venda_tiny(self):
        """
        Regra do cliente nº 4: o preço cadastrado no Tiny é sempre o preço do
        fornecedor, sem margem. Este alias existe para que qualquer código
        futuro que precise "o preço a mandar pro Tiny" tenha um único ponto
        de verdade — se um dia entrar markup, é aqui que ele seria aplicado,
        e o teste desta regra quebraria de propósito para forçar a decisão
        consciente.
        """
        return self.preco

    def aplicar_regra_de_estoque(self):
        """
        Regra do cliente nº 3: variação com estoque zero no fornecedor não é
        cadastrada no Tiny, mas fica no espelho como 'aguardando', para ser
        cadastrada quando houver reposição. Isso é diferente da regra nº 2
        (descontinuado), que é descarte permanente e nunca é revertida aqui.
        """
        if self.status == StatusVariacao.DESCONTINUADO:
            return
        if self.estoque <= 0:
            if self.status == StatusVariacao.PENDENTE:
                self.status = StatusVariacao.AGUARDANDO
        else:
            if self.status == StatusVariacao.AGUARDANDO:
                self.status = StatusVariacao.PENDENTE

    def save(self, *args, **kwargs):
        if self.produto_id and self.produto.descontinuado:
            self.status = StatusVariacao.DESCONTINUADO
        self.aplicar_regra_de_estoque()
        if self.payload_bruto:
            self.hash_conteudo = calcular_hash_conteudo(self.payload_bruto)
        super().save(*args, **kwargs)
