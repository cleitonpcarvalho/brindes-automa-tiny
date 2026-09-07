import logging
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

from apps.instancias.models import Instancia
from apps.instancias.tiny_client import TinyApiClient
from apps.sincronizacao.models import (
    Execucao,
    LogItem,
    NivelLog,
    StatusExecucao,
    TipoExecucao,
)

from . import tiny_sync
from .models import StatusVariacao, Variacao
from .tiny_sync import (
    HEARTBEAT_TIMEOUT_SEGUNDOS,
    PARADA_LEASE_PERDIDA,
    PARADA_PAUSA,
    ControladorSincronizacao,
    EventosSincronizacao,
    ResultadoSincronizacao,
    executar_sincronizacao_tiny,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Controlador: heartbeat + detecção cooperativa de pausa / perda de lease
# ---------------------------------------------------------------------------


class _ControladorLease(ControladorSincronizacao):
    """
    Chamado ANTES de cada produto pelo orquestrador:
      - se o `lease_token` no banco não é mais o meu -> outra retomada
        assumiu a Execucao; PARO já, sem tocar em nada (o novo dono cuida);
      - se `pausa_solicitada` (ou status já `pausando`) -> PARO após a
        unidade atual; a task encerra em `pausado`;
      - senão -> bato o heartbeat e sigo.
    """

    def __init__(self, execucao_id: int, token: str):
        self.execucao_id = execucao_id
        self.token = token

    def checar(self) -> str | None:
        linha = (
            Execucao.objects.filter(pk=self.execucao_id)
            .values("lease_token", "pausa_solicitada", "status")
            .first()
        )
        if linha is None or linha["lease_token"] != self.token:
            return PARADA_LEASE_PERDIDA
        if linha["pausa_solicitada"] or linha["status"] in (
            StatusExecucao.PAUSANDO,
            StatusExecucao.PAUSADO,
        ):
            return PARADA_PAUSA
        Execucao.objects.filter(pk=self.execucao_id, lease_token=self.token).update(
            heartbeat_em=timezone.now()
        )
        return None


# ---------------------------------------------------------------------------
# Sink de progresso: Execucao / LogItem
# ---------------------------------------------------------------------------


class _EventosExecucao(EventosSincronizacao):
    def __init__(self, execucao: Execucao):
        self.execucao = execucao

    def _log(self, nivel, mensagem, *, variacao=None, **detalhe):
        LogItem.objects.create(
            execucao=self.execucao,
            nivel=nivel,
            mensagem=mensagem[:500],
            variacao=variacao,
            detalhe=detalhe,
        )

    def inicio(self, *, total_fila):
        self._log(
            NivelLog.INFO,
            "Sincronização com o Tiny iniciada",
            fornecedor=self.execucao.fornecedor,
            fila=total_fila,
        )

    def variacao_criada(self, variacao, tiny_id):
        self._log(
            NivelLog.INFO, f"SKU {variacao.sku} criado no Tiny", variacao=variacao, tiny_id=str(tiny_id)
        )

    def variacao_vinculada(self, variacao, tiny_id):
        self._log(
            NivelLog.INFO,
            f"SKU {variacao.sku} vinculado a produto existente no Tiny",
            variacao=variacao,
            tiny_id=str(tiny_id),
        )

    def variacao_bloqueada(self, variacao, motivo):
        self._log(NivelLog.AVISO, f"SKU {variacao.sku} bloqueado", variacao=variacao, motivo=motivo)

    def variacao_erro(self, variacao, exc):
        self._log(
            NivelLog.ERRO, f"Falha ao sincronizar SKU {variacao.sku}", variacao=variacao, erro=str(exc)
        )

    def imagens(self, variacao, resultado):
        r = resultado.get("resultado")
        if r == tiny_sync.IMG_ENVIADA:
            self._log(
                NivelLog.INFO,
                f"Imagens do SKU {variacao.sku} enviadas ao Tiny",
                variacao=variacao,
                quantidade=len(resultado.get("desejadas") or []),
            )
        elif r == tiny_sync.IMG_RECONCILIADA:
            self._log(
                NivelLog.INFO,
                f"Imagens do SKU {variacao.sku} já estavam no Tiny — marcador reconciliado",
                variacao=variacao,
            )
        elif r == "erro":
            self._log(
                NivelLog.ERRO,
                f"Falha ao sincronizar imagens do SKU {variacao.sku}",
                variacao=variacao,
                erro=resultado.get("erro", ""),
            )


# ---------------------------------------------------------------------------
# Contadores de progresso — SEMPRE recomputados da verdade do banco (nunca
# acumulados), para a retomada continuar exata sem depender de memória.
# ---------------------------------------------------------------------------


def _atualizar_contadores(execucao: Execucao) -> None:
    do_fornecedor = Variacao.objects.filter(
        produto__instancia_id=execucao.instancia_id, produto__fornecedor=execucao.fornecedor
    )
    cadastrados = do_fornecedor.filter(status=StatusVariacao.CADASTRADO).exclude(tiny_id="").count()
    erros = do_fornecedor.filter(status=StatusVariacao.ERRO).count()
    pendentes = do_fornecedor.filter(status=StatusVariacao.PENDENTE).count()
    execucao.total_cadastrados = cadastrados
    execucao.total_novos = cadastrados
    execucao.total_erros = erros
    execucao.total_ignorados = pendentes  # ainda pendentes (bloqueados ou não feitos)
    execucao.total_lidos = cadastrados + erros + pendentes  # universo cadastrável do fornecedor


# ---------------------------------------------------------------------------
# Task principal
# ---------------------------------------------------------------------------


@shared_task
def cadastrar_produtos_tiny_task(execucao_id, lease_token=None):
    """
    Sincronização em massa de UM fornecedor com o Tiny, em background.

    A view (start OU retomada) já pôs a Execucao em `rodando`, gerou um
    `lease_token` novo e o passou aqui. Esta task:
      - valida o lease de forma atômica (aborta calada se não é mais dela);
      - roda o orquestrador compartilhado (`apps.catalogo.tiny_sync`);
      - bate heartbeat antes de cada produto e para cooperativamente se
        houver pedido de pausa;
      - encerra em `pausado` (retomável), `sucesso`/`parcial` (fila
        esvaziada) ou `falha` (erro inesperado) — nunca fica presa em
        `rodando`.
    """
    execucao = Execucao.objects.select_related("instancia").get(pk=execucao_id)
    token = lease_token or execucao.lease_token
    agora = timezone.now()

    # -- claim atômico do lease -------------------------------------------
    with transaction.atomic():
        atual = Execucao.objects.select_for_update().get(pk=execucao_id)
        if atual.status != StatusExecucao.RODANDO or (token and atual.lease_token != token):
            logger.info(
                "task de execucao %s abortada no claim: status=%s lease diferente=%s",
                execucao_id,
                atual.status,
                token and atual.lease_token != token,
            )
            return
        token = atual.lease_token
        Execucao.objects.filter(pk=execucao_id).update(heartbeat_em=agora)

    instancia = execucao.instancia
    resultado: ResultadoSincronizacao | None = None
    try:
        if not instancia.access_token:
            raise RuntimeError(f"Instância '{instancia.slug}' não está conectada ao Tiny.")
        cliente = TinyApiClient(instancia, somente_leitura=False)
        resultado = executar_sincronizacao_tiny(
            instancia,
            execucao.fornecedor,
            cliente=cliente,
            eventos=_EventosExecucao(execucao),
            controlador=_ControladorLease(execucao_id, token),
        )
    except Exception as exc:
        logger.exception(
            "sincronização com o Tiny de %s/%s falhou", instancia.slug, execucao.fornecedor
        )
        _finalizar(execucao_id, token, motivo_falha=str(exc))
        return

    if resultado.interrompida_por == PARADA_LEASE_PERDIDA:
        logger.info("execucao %s: lease perdido, encerrando sem tocar no estado", execucao_id)
        return
    if resultado.interrompida_por == PARADA_PAUSA:
        _finalizar(execucao_id, token, pausar=True)
        return
    _finalizar(execucao_id, token)


def _finalizar(execucao_id, token, *, pausar: bool = False, motivo_falha: str | None = None) -> None:
    """
    Fecha a Execucao respeitando o lease: se outra retomada já assumiu
    (token diferente), NÃO sobrescreve nada.
    """
    with transaction.atomic():
        execucao = Execucao.objects.select_for_update().get(pk=execucao_id)
        if token and execucao.lease_token != token:
            logger.info("execucao %s: lease trocou antes do fechamento, não sobrescreve", execucao_id)
            return

        _atualizar_contadores(execucao)
        execucao.heartbeat_em = timezone.now()
        execucao.pausa_solicitada = False

        if motivo_falha is not None:
            execucao.status = StatusExecucao.FALHA
            execucao.mensagem_erro = motivo_falha
            execucao.finalizada_em = timezone.now()
            mensagem, nivel = "Sincronização interrompida por erro inesperado", NivelLog.ERRO
        elif pausar:
            execucao.status = StatusExecucao.PAUSADO
            execucao.finalizada_em = None
            mensagem, nivel = "Sincronização pausada — pode ser retomada", NivelLog.INFO
        else:
            execucao.finalizada_em = timezone.now()
            concluiu_tudo = execucao.total_erros == 0 and execucao.total_ignorados == 0
            execucao.status = StatusExecucao.SUCESSO if concluiu_tudo else StatusExecucao.PARCIAL
            mensagem, nivel = "Sincronização com o Tiny concluída", NivelLog.INFO

        execucao.save()
        LogItem.objects.create(
            execucao=execucao,
            nivel=nivel,
            mensagem=mensagem,
            detalhe={
                "status": execucao.status,
                "cadastrados": execucao.total_cadastrados,
                "erros": execucao.total_erros,
                "pendentes": execucao.total_ignorados,
                **({"erro": motivo_falha} if motivo_falha else {}),
            },
        )


# ---------------------------------------------------------------------------
# Reaper: reconhece execuções travadas (worker morto) como `interrompido`
# ---------------------------------------------------------------------------


@shared_task
def reconciliar_execucoes_travadas():
    """
    Tick do Celery Beat: uma Execucao `rodando`/`pausando` sem heartbeat
    recente é uma task que morreu (worker reiniciou/OOM). Marca como
    `interrompido` — estado retomável, sem perder logs nem contadores e
    sem criar Execucao nova. A troca é condicional (não pisa numa execução
    que voltou a bater heartbeat no meio do tick).
    """
    limite = timezone.now() - timedelta(seconds=HEARTBEAT_TIMEOUT_SEGUNDOS)
    candidatas = Execucao.objects.filter(
        tipo=TipoExecucao.CADASTRO_TINY,
        status__in=(StatusExecucao.RODANDO, StatusExecucao.PAUSANDO),
        heartbeat_em__lt=limite,
    ).values_list("pk", flat=True)

    reconhecidas = 0
    for pk in list(candidatas):
        atualizadas = Execucao.objects.filter(
            pk=pk,
            status__in=(StatusExecucao.RODANDO, StatusExecucao.PAUSANDO),
            heartbeat_em__lt=limite,
        ).update(status=StatusExecucao.INTERROMPIDO)
        if atualizadas:
            reconhecidas += 1
            LogItem.objects.create(
                execucao_id=pk,
                nivel=NivelLog.AVISO,
                mensagem="Execução reconhecida como interrompida (heartbeat expirado)",
                detalhe={"timeout_segundos": HEARTBEAT_TIMEOUT_SEGUNDOS},
            )
    if reconhecidas:
        logger.warning("%s execução(ões) de cadastro Tiny reconhecidas como interrompidas", reconhecidas)
    return reconhecidas
