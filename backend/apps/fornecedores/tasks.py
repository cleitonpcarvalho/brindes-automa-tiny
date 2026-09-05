import logging

from celery import shared_task
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.instancias.models import Instancia

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
    """
    instancia = Instancia.objects.get(pk=instancia_id)
    try:
        call_command("importar_fornecedor", instancia.slug, fornecedor, tipo="incremental")
    except CommandError as exc:
        logger.info("sincronização de %s/%s pulada: %s", instancia.slug, fornecedor, exc)
