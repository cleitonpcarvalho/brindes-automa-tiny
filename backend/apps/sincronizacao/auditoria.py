"""
Camada de leitura/auditoria sobre os `LogItem` de uma `Execucao` — usada
pelos endpoints da tela de detalhe de execução.

NÃO altera nada: concilia logs já gravados com o estado atual do espelho. O vínculo com a
`Variacao` é o FK `LogItem.variacao` (estruturado); o tipo do desfecho é o
campo `LogItem.evento` (estruturado). Nenhuma interpretação de texto livre.
"""

from django.db.models import Case, CharField, Count, F, Q, Subquery, Value, When

from apps.catalogo.models import StatusVariacao
from apps.catalogo.tiny_sync import sku_tiny_para_exibicao

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
    qs = _com_resultado_atual(LogItem.objects.filter(
        id__in=Subquery(_ids_ultimo_desfecho_por_variacao(execucao))
    )).select_related("variacao", "variacao__produto")

    eventos = RESULTADO_FILTROS.get(resultado)
    if eventos:
        qs = qs.filter(resultado_atual__in=eventos)

    busca = (busca or "").strip()
    if busca:
        qs = qs.filter(
            Q(variacao__sku__icontains=busca)
            | Q(variacao__atributos__codigo_composto__icontains=busca,
                variacao__produto__fornecedor="xbz")
            | Q(variacao__nome__icontains=busca)
            | Q(variacao__produto__nome__icontains=busca)
            | Q(variacao__produto__codigo_pai__icontains=busca)
        )

    return qs.order_by("variacao__sku", "id")


def _com_resultado_atual(qs):
    """Projeção de leitura única para linhas, filtros e contadores.

    LogItem conserva o desfecho histórico. Um cadastro confirmado no espelho
    resolve erros/bloqueios antigos; uma falha atual de sincronização continua
    visível mesmo quando já há tiny_id. Sem evidência atual, preserva o log.
    """
    cadastrado = Q(variacao__status=StatusVariacao.CADASTRADO) & Q(
        variacao__tiny_id__isnull=False
    ) & ~Q(variacao__tiny_id="")
    return qs.annotate(resultado_atual=Case(
        When(cadastrado & ~Q(evento__in=(EventoLog.CRIADO, EventoLog.VINCULADO)),
             then=Value(EventoLog.VINCULADO)),
        When(variacao__status=StatusVariacao.ERRO, then=Value(EventoLog.ERRO)),
        default=F("evento"), output_field=CharField(),
    ))


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
    # A listagem já trouxe a projeção na mesma consulta da variação. Só
    # respostas de retry que passam um LogItem avulso precisam desta consulta.
    sem_projecao = [log.pk for log in logs if not hasattr(log, "resultado_atual")]
    resultados = dict(_com_resultado_atual(LogItem.objects.filter(pk__in=sem_projecao))
                      .values_list("pk", "resultado_atual")) if sem_projecao else {}
    linhas = []
    for log in logs:
        variacao = log.variacao
        produto = variacao.produto if variacao else None
        detalhe = log.detalhe if isinstance(log.detalhe, dict) else {}
        resultado = getattr(log, "resultado_atual", resultados.get(log.pk))
        tiny_id = (variacao.tiny_id if variacao else None) or detalhe.get("tiny_id") or ""
        detalhe_atual = _detalhe_curto(log)
        if resultado == EventoLog.ERRO and variacao and variacao.status == StatusVariacao.ERRO:
            detalhe_atual = variacao.ultimo_erro or detalhe_atual
        elif resultado != log.evento:
            detalhe_atual = "Cadastro confirmado posteriormente; tentativa original preservada no histórico."
        linhas.append(
            {
                "log_id": log.id,
                "variacao_id": log.variacao_id,
                "sku": variacao.sku if variacao else "",
                "codigo_fornecedor": variacao.sku if variacao else "",
                "sku_tiny": _identidade_tiny_segura(variacao),
                "produto_nome": (produto.nome if produto else "") or (variacao.nome if variacao else ""),
                "resultado": resultado,
                "resultado_historico": log.evento,
                "detalhe_historico": _detalhe_curto(log),
                "status_atual": variacao.status if variacao else None,
                "reconciliado": resultado != log.evento,
                "tiny_id": str(tiny_id),
                "mensagem": log.mensagem,
                "detalhe_curto": detalhe_atual,
                "imagens": imagens.get(log.variacao_id),
                "criado_em": log.criado_em,
            }
        )
    return linhas


def _identidade_tiny_segura(variacao):
    return sku_tiny_para_exibicao(variacao)


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
        linhas_de_auditoria(execucao)
        .values_list("resultado_atual")
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
