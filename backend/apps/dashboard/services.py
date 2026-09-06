"""
Cálculo dos números e alertas do dashboard (passo 8).

Nada aqui é persistido: alertas são sempre derivados do estado atual de
Instancia/Execucao/Variacao a cada chamada — não existe tabela de alertas.
"""

from datetime import timedelta

from django.db.models import Count, F, Max, Q, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.catalogo.models import StatusVariacao, Variacao
from apps.instancias.constants import Fornecedor
from apps.instancias.models import Instancia
from apps.sincronizacao.models import Execucao, StatusExecucao

# "Acima de um limiar" (pedido do passo 8, sem número definido) — 10
# variações com erro num mesmo (instância, fornecedor) é o corte adotado.
LIMIAR_VARIACOES_COM_ERRO = 10

PERIODOS_VALIDOS = ("hoje", "7d", "30d")


def _inicio_do_dia_local(momento):
    local = timezone.localtime(momento)
    return local.replace(hour=0, minute=0, second=0, microsecond=0)


def _janela_produtos_sincronizados(periodo, agora):
    """
    "hoje" usa limites de dia-calendário local (bate com a redação literal
    "hoje ... vs ontem"); 7d/30d usam janelas corridas de N dias, comparadas
    com os N dias imediatamente anteriores. Só este número do resumo muda
    com `periodo` — instâncias/execuções-24h/alertas são sempre o estado
    atual (ver calcular_resumo).
    """
    if periodo == "7d":
        inicio_atual = agora - timedelta(days=7)
        inicio_anterior = inicio_atual - timedelta(days=7)
    elif periodo == "30d":
        inicio_atual = agora - timedelta(days=30)
        inicio_anterior = inicio_atual - timedelta(days=30)
    else:
        inicio_atual = _inicio_do_dia_local(agora)
        inicio_anterior = inicio_atual - timedelta(days=1)
    return inicio_anterior, inicio_atual


def _soma_produtos_sincronizados(desde, ate=None):
    """"Produtos sincronizados" = variações novas + atualizadas nas execuções do período
    (não `total_lidos`, que inclui itens sem mudança nenhuma)."""
    qs = Execucao.objects.filter(iniciada_em__gte=desde)
    if ate is not None:
        qs = qs.filter(iniciada_em__lt=ate)
    agregado = qs.aggregate(total=Coalesce(Sum(F("total_novos") + F("total_atualizados")), 0))
    return agregado["total"]


def calcular_resumo(periodo="hoje"):
    if periodo not in PERIODOS_VALIDOS:
        periodo = "hoje"
    agora = timezone.now()

    instancias_total = Instancia.objects.count()
    instancias_ativas = Instancia.objects.filter(status=Instancia.Status.CONECTADO).count()

    inicio_anterior, inicio_atual = _janela_produtos_sincronizados(periodo, agora)
    produtos_atual = _soma_produtos_sincronizados(inicio_atual)
    produtos_anterior = _soma_produtos_sincronizados(inicio_anterior, inicio_atual)

    desde_24h = agora - timedelta(hours=24)
    execucoes_24h_qs = Execucao.objects.filter(iniciada_em__gte=desde_24h)
    execucoes_24h_total = execucoes_24h_qs.count()
    execucoes_24h_sucesso = execucoes_24h_qs.filter(status=StatusExecucao.SUCESSO).count()

    alertas = calcular_alertas()
    alertas_criticos = sum(1 for alerta in alertas if alerta["severidade"] == "critica")

    return {
        "periodo": periodo,
        "instancias": {"ativas": instancias_ativas, "total": instancias_total},
        "produtos_sincronizados": {
            "total": produtos_atual,
            "periodo_anterior": produtos_anterior,
            "diferenca": produtos_atual - produtos_anterior,
        },
        "execucoes_24h": {"total": execucoes_24h_total, "sucesso": execucoes_24h_sucesso},
        "alertas": {"abertos": len(alertas), "requerem_acao": alertas_criticos},
    }


def _ref_instancia(instancia):
    return {"slug": instancia.slug, "nome": instancia.nome}


def _ultimas_execucoes_por_fornecedor():
    """
    Última Execucao de cada par (instância, fornecedor) — 2 queries no total
    (agrupamento + busca das linhas), não uma por instância/fornecedor.
    """
    grupos = list(
        Execucao.objects.values("instancia_id", "fornecedor").annotate(
            ultima_iniciada_em=Max("iniciada_em")
        )
    )
    if not grupos:
        return Execucao.objects.none()

    condicao = Q()
    for grupo in grupos:
        condicao |= Q(
            instancia_id=grupo["instancia_id"],
            fornecedor=grupo["fornecedor"],
            iniciada_em=grupo["ultima_iniciada_em"],
        )
    return Execucao.objects.filter(condicao).select_related("instancia")


def calcular_alertas():
    agora = timezone.now()
    alertas = []

    instancias_token_expirado = list(
        Instancia.objects.filter(refresh_expira_em__isnull=False, refresh_expira_em__lte=agora)
    )
    for instancia in instancias_token_expirado:
        alertas.append(
            {
                "id": f"token-expirado-{instancia.slug}",
                "severidade": "critica",
                "tipo": "token_expirado",
                "instancia": _ref_instancia(instancia),
                "fornecedor": None,
                "mensagem": f"Token do Tiny expirou em {instancia.nome} — é necessário reautorizar.",
                "momento": instancia.refresh_expira_em,
                "acao_sugerida": {"tipo": "reautorizar", "rotulo": "Reautorizar"},
            }
        )

    ids_com_token_expirado = {instancia.id for instancia in instancias_token_expirado}
    instancias_falhas = Instancia.objects.filter(
        tentativas_falha__gte=Instancia.MAX_TENTATIVAS_FALHA_RENOVACAO
    ).exclude(id__in=ids_com_token_expirado)
    for instancia in instancias_falhas:
        alertas.append(
            {
                "id": f"falhas-renovacao-{instancia.slug}",
                "severidade": "critica",
                "tipo": "falhas_renovacao",
                "instancia": _ref_instancia(instancia),
                "fornecedor": None,
                "mensagem": (
                    f"{instancia.nome} teve {instancia.tentativas_falha} falhas seguidas "
                    "ao renovar o token do Tiny."
                ),
                "momento": instancia.atualizado_em,
                "acao_sugerida": {"tipo": "ver_detalhes", "rotulo": "Ver detalhes"},
            }
        )

    for execucao in _ultimas_execucoes_por_fornecedor():
        if execucao.status != StatusExecucao.FALHA:
            continue
        if "limite" in execucao.mensagem_erro.lower():
            alertas.append(
                {
                    "id": f"limite-diario-{execucao.id}",
                    "severidade": "critica",
                    "tipo": "limite_diario",
                    "instancia": _ref_instancia(execucao.instancia),
                    "fornecedor": execucao.fornecedor,
                    "mensagem": (
                        f"{execucao.get_fornecedor_display()} atingiu o limite diário de "
                        f"chamadas em {execucao.instancia.nome}."
                    ),
                    "momento": execucao.iniciada_em,
                    "acao_sugerida": {"tipo": "ver_detalhes", "rotulo": "Ver detalhes"},
                }
            )
        else:
            alertas.append(
                {
                    "id": f"execucao-falhou-{execucao.id}",
                    "severidade": "atencao",
                    "tipo": "execucao_falhou",
                    "instancia": _ref_instancia(execucao.instancia),
                    "fornecedor": execucao.fornecedor,
                    "mensagem": (
                        f"Última sincronização de {execucao.get_fornecedor_display()} falhou "
                        f"em {execucao.instancia.nome}"
                        + (f": {execucao.mensagem_erro}" if execucao.mensagem_erro else ".")
                    ),
                    "momento": execucao.iniciada_em,
                    "acao_sugerida": {"tipo": "ver_detalhes", "rotulo": "Ver detalhes"},
                }
            )

    contagens_erro = (
        Variacao.objects.filter(status=StatusVariacao.ERRO)
        .values(
            "produto__instancia_id",
            "produto__instancia__nome",
            "produto__instancia__slug",
            "produto__fornecedor",
        )
        .annotate(total=Count("id"), ultimo_erro_em=Max("atualizado_em"))
        .filter(total__gt=LIMIAR_VARIACOES_COM_ERRO)
    )
    nomes_fornecedor = dict(Fornecedor.choices)
    for linha in contagens_erro:
        fornecedor = linha["produto__fornecedor"]
        alertas.append(
            {
                "id": f"variacoes-erro-{linha['produto__instancia_id']}-{fornecedor}",
                "severidade": "atencao",
                "tipo": "variacoes_com_erro",
                "instancia": {
                    "slug": linha["produto__instancia__slug"],
                    "nome": linha["produto__instancia__nome"],
                },
                "fornecedor": fornecedor,
                "mensagem": (
                    f"{linha['total']} produtos de {nomes_fornecedor.get(fornecedor, fornecedor)} "
                    f"falharam ao cadastrar em {linha['produto__instancia__nome']}."
                ),
                "momento": linha["ultimo_erro_em"],
                "acao_sugerida": {"tipo": "ver_produtos", "rotulo": "Ver produtos"},
            }
        )

    alertas.sort(key=lambda alerta: alerta["momento"], reverse=True)
    return alertas


def calcular_atividade(limit=20):
    execucoes = Execucao.objects.select_related("instancia").order_by("-iniciada_em")[:limit]

    resultado = []
    for execucao in execucoes:
        resultado.append(
            {
                "id": execucao.id,
                "instancia": _ref_instancia(execucao.instancia),
                "fornecedor": execucao.fornecedor,
                "tipo": execucao.tipo,
                "status": execucao.status,
                "iniciada_em": execucao.iniciada_em,
                "finalizada_em": execucao.finalizada_em,
                "duracao_segundos": execucao.duracao_segundos,
                "total_lidos": execucao.total_lidos,
                "total_novos": execucao.total_novos,
                "total_atualizados": execucao.total_atualizados,
                "total_cadastrados": execucao.total_cadastrados,
                "total_ignorados": execucao.total_ignorados,
                "total_erros": execucao.total_erros,
            }
        )
    return resultado
