"""
Camada de leitura/auditoria sobre os `LogItem` de uma `Execucao` — usada
pelos endpoints da tela de detalhe de execução.

NÃO altera nada: só agrupa e classifica logs já gravados. O vínculo com a
`Variacao` é o FK `LogItem.variacao` (estruturado); o tipo do desfecho é o
campo `LogItem.evento` (estruturado). Nenhuma interpretação de texto livre.
"""

from django.db.models import Count, Q, Subquery

from apps.catalogo.tiny_sync import IdentidadeTinyError, identidade_tiny

from .models import EVENTOS_DESFECHO, EventoLog, LogItem

# filtro da UI -> conjunto de eventos de desfecho
RESULTADO_FILTROS = {
    "cadastrados": (EventoLog.CRIADO, EventoLog.VINCULADO),
    "erros": (EventoLog.ERRO,),
    "bloqueados": (EventoLog.BLOQUEADO,),
}


def _ids_ultimo_desfecho_por_variacao(execucao):
    """
    Para cada Variacao com ao menos um log de desfecho nesta execução, o id
    do desfecho MAIS RECENTE (numa retomada um SKU pode ter ido de `erro`
    para `criado` — vale o último).
    """
    return (
        LogItem.objects.filter(
            execucao=execucao, variacao__isnull=False, evento__in=EVENTOS_DESFECHO
        )
        .order_by("variacao_id", "-criado_em", "-id")
        .distinct("variacao_id")
        .values("id")
    )


def linhas_de_auditoria(execucao, *, busca: str = "", resultado: str = ""):
    """
    Queryset de `LogItem` — UMA linha por SKU (o desfecho mais recente),
    já com `variacao`/`produto` via select_related, para a tabela paginada.
    """
    qs = LogItem.objects.filter(
        id__in=Subquery(_ids_ultimo_desfecho_por_variacao(execucao))
    ).select_related("variacao", "variacao__produto")

    eventos = RESULTADO_FILTROS.get(resultado)
    if eventos:
        qs = qs.filter(evento__in=eventos)

    busca = (busca or "").strip()
    if busca:
        qs = qs.filter(
            Q(variacao__sku__icontains=busca)
            | Q(variacao__nome__icontains=busca)
            | Q(variacao__produto__nome__icontains=busca)
            | Q(variacao__produto__codigo_pai__icontains=busca)
        )

    return qs.order_by("variacao__sku", "id")


def _imagens_por_variacao(execucao, variacao_ids):
    """{variacao_id: 'ok' | 'erro'} — status do log de imagem mais recente do SKU."""
    if not variacao_ids:
        return {}
    resultado: dict[int, str] = {}
    for log in (
        LogItem.objects.filter(
            execucao=execucao,
            variacao_id__in=variacao_ids,
            evento__in=(EventoLog.IMAGENS, EventoLog.IMAGENS_ERRO),
        )
        .order_by("variacao_id", "-criado_em", "-id")
        .distinct("variacao_id")
        .values("variacao_id", "evento")
    ):
        resultado[log["variacao_id"]] = "erro" if log["evento"] == EventoLog.IMAGENS_ERRO else "ok"
    return resultado


def montar_linhas(execucao, logs):
    """Serializa uma página de linhas (list[LogItem]) para o endpoint."""
    imagens = _imagens_por_variacao(execucao, [log.variacao_id for log in logs])
    linhas = []
    for log in logs:
        variacao = log.variacao
        produto = variacao.produto if variacao else None
        detalhe = log.detalhe if isinstance(log.detalhe, dict) else {}
        tiny_id = detalhe.get("tiny_id") or ""
        if not tiny_id and log.evento in (EventoLog.CRIADO, EventoLog.VINCULADO) and variacao:
            tiny_id = variacao.tiny_id or ""
        linhas.append(
            {
                "log_id": log.id,
                "variacao_id": log.variacao_id,
                "sku": variacao.sku if variacao else "",
                "codigo_fornecedor": variacao.sku if variacao else "",
                "sku_tiny": _identidade_tiny_segura(variacao),
                "produto_nome": (produto.nome if produto else "") or (variacao.nome if variacao else ""),
                "resultado": log.evento,
                "tiny_id": str(tiny_id),
                "mensagem": log.mensagem,
                "detalhe_curto": _detalhe_curto(log),
                "imagens": imagens.get(log.variacao_id),
                "criado_em": log.criado_em,
            }
        )
    return linhas


def _identidade_tiny_segura(variacao):
    if not variacao:
        return ""
    try:
        return identidade_tiny(variacao)
    except IdentidadeTinyError:
        return ""


def _detalhe_curto(log) -> str:
    """Mensagem humana curta para a coluna 'Detalhe/erro' (sem JSON)."""
    detalhe = log.detalhe if isinstance(log.detalhe, dict) else {}
    if log.evento == EventoLog.ERRO:
        return str(detalhe.get("erro") or log.mensagem)
    if log.evento == EventoLog.BLOQUEADO:
        return str(detalhe.get("motivo") or "")
    return ""


def resumo_auditoria(execucao) -> dict:
    """Contagem de SKUs por resultado nesta execução (para as abas de filtro)."""
    contagem = dict(
        LogItem.objects.filter(id__in=Subquery(_ids_ultimo_desfecho_por_variacao(execucao)))
        .values_list("evento")
        .order_by()
        .annotate(n=Count("id"))
    )
    cadastrados = contagem.get(EventoLog.CRIADO, 0)
    vinculados = contagem.get(EventoLog.VINCULADO, 0)
    return {
        "total": sum(contagem.values()),
        "cadastrados": cadastrados,
        "vinculados": vinculados,
        "cadastrados_e_vinculados": cadastrados + vinculados,
        "bloqueados": contagem.get(EventoLog.BLOQUEADO, 0),
        "erros": contagem.get(EventoLog.ERRO, 0),
    }


def logs_gerais(execucao):
    """
    Logs que NÃO são de um SKU específico (início, pausa, conclusão, falha,
    ingestão de espelho) — a seção secundária "Logs técnicos".
    """
    return execucao.logs.filter(
        Q(evento=EventoLog.GERAL) | Q(variacao__isnull=True)
    ).order_by("criado_em", "id")


def logs_da_variacao(execucao, variacao_id):
    """Todos os logs de UM SKU nesta execução — para o expand técnico da linha."""
    return (
        execucao.logs.filter(variacao_id=variacao_id)
        .select_related("variacao")
        .order_by("criado_em", "id")
    )
