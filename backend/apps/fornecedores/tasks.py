import logging

from celery import shared_task
from django.core.management import call_command
from django.core.management.base import CommandError
from django.db.models import Q
from django.utils import timezone

from apps.instancias.models import Instancia
from apps.sincronizacao.models import Execucao, StatusExecucao

from .models import (
    AtualizacaoVariacaoFornecedor,
    CadenciaFornecedor,
    StatusAtualizacaoVariacao,
)

logger = logging.getLogger(__name__)

ATUALIZACAO_FORNECEDOR_STALE_SEGUNDOS = 1800


@shared_task
def atualizar_variacao_fornecedor_task(operacao_id):
    """Executa uma atualização individual fora do ciclo HTTP."""
    operacao = AtualizacaoVariacaoFornecedor.objects.select_related(
        "instancia", "variacao", "variacao__produto"
    ).filter(pk=operacao_id).first()
    if operacao is None or operacao.status != StatusAtualizacaoVariacao.RODANDO:
        return

    agora = timezone.now()
    AtualizacaoVariacaoFornecedor.objects.filter(
        pk=operacao_id, status=StatusAtualizacaoVariacao.RODANDO
    ).update(iniciado_em=agora, heartbeat_em=agora)

    try:
        from .services import atualizar_variacao_do_fornecedor

        atualizar_variacao_do_fornecedor(operacao.instancia, operacao.variacao)
    except Exception as exc:
        logger.exception("atualização individual %s falhou", operacao_id)
        AtualizacaoVariacaoFornecedor.objects.filter(
            pk=operacao_id, status=StatusAtualizacaoVariacao.RODANDO
        ).update(
        status=StatusAtualizacaoVariacao.ERRO,
            erro=str(exc),
            finalizado_em=timezone.now(),
            heartbeat_em=timezone.now(),
        )
        return

    agora = timezone.now()
    AtualizacaoVariacaoFornecedor.objects.filter(
        pk=operacao_id, status=StatusAtualizacaoVariacao.RODANDO
    ).update(
        status=StatusAtualizacaoVariacao.SUCESSO,
        erro="",
        finalizado_em=agora,
        heartbeat_em=agora,
    )


@shared_task
def reconciliar_atualizacoes_fornecedor_stale():
    """Libera operações cujo worker morreu antes de concluir."""
    limite = timezone.now() - timezone.timedelta(seconds=ATUALIZACAO_FORNECEDOR_STALE_SEGUNDOS)
    return AtualizacaoVariacaoFornecedor.objects.filter(
        status=StatusAtualizacaoVariacao.RODANDO,
    ).filter(Q(heartbeat_em__lt=limite) | Q(heartbeat_em__isnull=True)).update(
        status=StatusAtualizacaoVariacao.INTERROMPIDO,
        erro="A task Celery não enviou heartbeat dentro do prazo; operação interrompida.",
        finalizado_em=timezone.now(),
    )


@shared_task
def verificar_e_disparar_sincronizacoes():
    """
    Tick do Celery Beat (a cada 5 minutos): não sincroniza nada diretamente
    — só decide, a partir de CadenciaFornecedor, quem já venceu, e agenda
    a tarefa real. A cadência de cada (instância, fornecedor) vem do banco,
    nunca fixa aqui.
    """
    agora = timezone.now()
    cadencias = CadenciaFornecedor.objects.filter(ativo=True).select_related("instancia")

    for cadencia in cadencias:
        if cadencia.proxima_execucao_em and cadencia.proxima_execucao_em > agora:
            continue
        sincronizar_fornecedor_task.delay(cadencia.instancia_id, cadencia.fornecedor)
        cadencia.proxima_execucao_em = agora + timezone.timedelta(minutes=cadencia.intervalo_minutos)
        cadencia.save(update_fields=["proxima_execucao_em"])


@shared_task
def sincronizar_fornecedor_task(instancia_id, fornecedor):
    """
    Executa `importar_fornecedor` para (instancia, fornecedor). Para a xbz,
    a trava de "no máximo 1x/dia" já vive no próprio comando — aqui só
    tratamos isso como um skip esperado, não como falha da tarefa.

    Pula (não falha) se há uma sincronização de produtos com o Tiny ATIVA
    para o mesmo fornecedor — reimportar o espelho no meio mudaria a
    elegibilidade do lote. Pausado não bloqueia.
    """
    from apps.catalogo.tiny_sync import cadastro_tiny_bloqueia_espelho

    instancia = Instancia.objects.get(pk=instancia_id)
    if cadastro_tiny_bloqueia_espelho(instancia, fornecedor):
        logger.info(
            "sincronização de espelho de %s/%s pulada: cadastro Tiny ativo",
            instancia.slug,
            fornecedor,
        )
        return
    try:
        # A importação de espelho é sempre espelho-apenas: este comando não
        # escreve no Tiny em nenhum modo.
        call_command(
            "importar_fornecedor", instancia.slug, fornecedor, tipo="incremental", mirror_only=True
        )
    except CommandError as exc:
        logger.info("sincronização de %s/%s pulada: %s", instancia.slug, fornecedor, exc)
        return

    # Espelho atualizado. Se a cadência do par pediu explicitamente a
    # propagação ao Tiny (segundo opt-in, desligado por padrão), reflete
    # agora — numa task separada e isolada — o que ficou fora de sincronia.
    if CadenciaFornecedor.objects.filter(
        instancia_id=instancia_id, fornecedor=fornecedor, ativo=True, propagar_tiny=True
    ).exists():
        from apps.catalogo.tasks import propagar_fornecedor_tiny_task

        propagar_fornecedor_tiny_task.delay(instancia_id, fornecedor)


@shared_task
def executar_sincronizacao_manual_task(execucao_id):
    """
    Disparo manual (passo 10): a view já criou a Execucao (status=rodando) e
    devolveu o id ao usuário antes de enfileirar — aqui só roda o mesmo
    comando de sempre, reaproveitando essa Execucao (`--execucao-id`) em vez
    de criar uma nova. O comando já marca a Execucao como falha em qualquer
    erro previsto (ver importar_fornecedor.py); este try/except é só uma
    rede de segurança para o caso de o próprio call_command explodir antes
    disso (ex.: argumento inválido).
    """
    execucao = Execucao.objects.select_related("instancia").get(pk=execucao_id)
    try:
        call_command(
            "importar_fornecedor",
            execucao.instancia.slug,
            execucao.fornecedor,
            tipo=execucao.tipo,
            execucao_id=execucao.id,
            mirror_only=True,
        )
    except Exception as exc:
        logger.exception(
            "sincronização manual de %s/%s falhou", execucao.instancia.slug, execucao.fornecedor
        )
        execucao.refresh_from_db()
        if execucao.status == StatusExecucao.RODANDO:
            execucao.status = StatusExecucao.FALHA
            execucao.mensagem_erro = str(exc)
            execucao.finalizada_em = timezone.now()
            execucao.save()
