import logging

from celery import shared_task
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.instancias.models import Instancia
from apps.sincronizacao.models import Execucao, StatusExecucao

from .models import CadenciaFornecedor

logger = logging.getLogger(__name__)


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
        # A sincronização automática também é espelho-apenas: este comando não
        # escreve no Tiny em nenhum modo. O passo de cadastro no Tiny é um
        # comando separado (cadastrar_produtos_tiny), disparado à parte.
        call_command(
            "importar_fornecedor", instancia.slug, fornecedor, tipo="incremental", mirror_only=True
        )
    except CommandError as exc:
        logger.info("sincronização de %s/%s pulada: %s", instancia.slug, fornecedor, exc)


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
