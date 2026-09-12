"""
Queryset da listagem de instâncias (passo 8).

Regra dura do passo: nenhuma métrica por linha pode disparar uma consulta
por linha. Toda métrica por fornecedor/produto vem de `Subquery` (uma só
consulta SQL, com subconsultas correlacionadas resolvidas pelo Postgres) e
as credenciais por fornecedor vêm de `Prefetch` (uma consulta para a página
inteira, não uma por instância).
"""

from django.db.models import Case, Count, IntegerField, OuterRef, Prefetch, Q, Subquery, When
from django.db.models.functions import Coalesce

from apps.catalogo.models import StatusVariacao, Variacao
from apps.sincronizacao.models import Execucao

from .constants import Fornecedor
from .models import CredencialFornecedor, Instancia


def _status_execucao_subquery(fornecedor):
    """Status da última Execucao daquele fornecedor para a instância da linha."""
    return Subquery(
        Execucao.objects.filter(instancia=OuterRef("pk"), fornecedor=fornecedor)
        .order_by("-iniciada_em")
        .values("status")[:1]
    )


def _contagem_variacoes_subquery(status=None, fornecedor=None, estoque_gt_zero=False, imagens_pendentes=False):
    """
    Contagem de Variacao da instância da linha, opcionalmente filtrada por
    status. Agregação feita dentro da própria subquery (`.values(...)
    .annotate(Count(...))`) para não sofrer o fan-out clássico de somar dois
    Count() sobre o mesmo relacionamento num único .annotate() do queryset
    principal.
    """
    qs = Variacao.objects.filter(produto__instancia=OuterRef("pk"))
    if status is not None:
        qs = qs.filter(status=status)
    if fornecedor is not None:
        qs = qs.filter(produto__fornecedor=fornecedor)
    if estoque_gt_zero:
        qs = qs.filter(estoque__gt=0)
    if imagens_pendentes:
        qs = qs.filter(
            status=StatusVariacao.CADASTRADO,
            tiny_id__isnull=False,
            imagens_tiny_sincronizadas=[],
        ).exclude(tiny_id="").exclude(imagens=[])
    qs = qs.order_by().values("produto__instancia").annotate(total=Count("id")).values("total")
    return Coalesce(Subquery(qs, output_field=IntegerField()), 0)


def queryset_listagem():
    ultima_execucao = Execucao.objects.filter(instancia=OuterRef("pk")).order_by("-iniciada_em")

    queryset = Instancia.objects.annotate(
        produtos_total=_contagem_variacoes_subquery(),
        produtos_cadastrados=_contagem_variacoes_subquery(StatusVariacao.CADASTRADO),
        ultima_sincronizacao_em=Subquery(ultima_execucao.values("iniciada_em")[:1]),
        ultima_sincronizacao_fornecedor=Subquery(ultima_execucao.values("fornecedor")[:1]),
    )
    for valor, _rotulo in Fornecedor.choices:
        queryset = queryset.annotate(**{f"status_execucao_{valor}": _status_execucao_subquery(valor)})
        queryset = queryset.annotate(
            **{
                f"erros_atuais_{valor}": _contagem_variacoes_subquery(
                    StatusVariacao.ERRO, fornecedor=valor
                ),
                f"pendentes_atuais_{valor}": _contagem_variacoes_subquery(
                    StatusVariacao.PENDENTE, fornecedor=valor, estoque_gt_zero=True
                ),
                f"imagens_pendentes_atuais_{valor}": _contagem_variacoes_subquery(
                    fornecedor=valor, imagens_pendentes=True
                ),
            }
        )

    queryset = queryset.prefetch_related(
        Prefetch(
            "credenciais_fornecedor",
            queryset=CredencialFornecedor.objects.only("id", "instancia_id", "fornecedor", "ativo"),
        )
    )
    return queryset


def aplicar_busca(queryset, busca):
    """Busca por nome OU cnpj (pedido do passo 8)."""
    if not busca:
        return queryset
    return queryset.filter(Q(nome__icontains=busca) | Q(cnpj__icontains=busca))


def aplicar_filtro_status(queryset, status_valor):
    if not status_valor:
        return queryset
    return queryset.filter(status=status_valor)


def aplicar_ordenacao_problema_primeiro(queryset):
    """
    "Instâncias com problema primeiro": erro antes de não-conectado antes de
    conectado (definição adotada para "problema" — sem essa ordem no design,
    foi a leitura mais literal do pedido). Empate por nome.
    """
    prioridade = Case(
        When(status=Instancia.Status.ERRO, then=0),
        When(status=Instancia.Status.NAO_CONECTADO, then=1),
        default=2,
        output_field=IntegerField(),
    )
    return queryset.annotate(_prioridade_status=prioridade).order_by("_prioridade_status", "nome")
