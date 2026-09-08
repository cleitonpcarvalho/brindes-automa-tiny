import logging
import time
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.instancias.models import Instancia
from apps.instancias.tiny_client import TinyApiClient
from apps.sincronizacao.models import (
    EventoLog,
    Execucao,
    LogItem,
    NivelLog,
    RetentativaLote,
    StatusExecucao,
    StatusRetentativaLote,
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
    cadastrar_variacao_individual,
    executar_sincronizacao_tiny,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Contadores de progresso — SEMPRE recomputados da verdade do banco (3
# COUNTs por fornecedor), nunca acumulados em memória: assim a retomada
# continua exata e o número na tela é sempre o estado real.
# ---------------------------------------------------------------------------


def _contadores_da_fila(instancia_id, fornecedor) -> dict:
    do_fornecedor = Variacao.objects.filter(
        produto__instancia_id=instancia_id, produto__fornecedor=fornecedor
    )
    cadastrados = do_fornecedor.filter(status=StatusVariacao.CADASTRADO).exclude(tiny_id="").count()
    erros = do_fornecedor.filter(status=StatusVariacao.ERRO).count()
    pendentes = do_fornecedor.filter(status=StatusVariacao.PENDENTE).count()
    return {
        "total_cadastrados": cadastrados,
        "total_novos": cadastrados,
        "total_erros": erros,
        # `total_ignorados` = variações ainda `pendente` do fornecedor.
        # DURANTE a execução são "a fazer" (a maioria ainda não chegou a ser
        # avaliada); só DEPOIS de uma rodada COMPLETA elas são os
        # "bloqueados" de fato. A UI escolhe o rótulo pelo estado.
        "total_ignorados": pendentes,
        "total_lidos": cadastrados + erros + pendentes,  # universo cadastrável
    }


def _persistir_contadores(execucao_id, token, *, agora=None) -> int:
    """Grava os contadores atuais na Execucao, sob o lease. Devolve linhas afetadas."""
    execucao = Execucao.objects.filter(pk=execucao_id).values("instancia_id", "fornecedor").first()
    if execucao is None:
        return 0
    campos = _contadores_da_fila(execucao["instancia_id"], execucao["fornecedor"])
    campos["heartbeat_em"] = agora or timezone.now()
    return Execucao.objects.filter(pk=execucao_id, lease_token=token).update(**campos)


# ---------------------------------------------------------------------------
# Controlador: heartbeat + progresso incremental + pausa / perda de lease
# ---------------------------------------------------------------------------


class _ControladorLease(ControladorSincronizacao):
    """
    Chamado ANTES de cada produto pelo orquestrador:
      - se o `lease_token` no banco não é mais o meu -> outra retomada
        assumiu a Execucao; PARO já, sem tocar em nada (o novo dono cuida);
      - se `pausa_solicitada` (ou status já `pausando`) -> PARO após a
        unidade atual;
      - senão -> bato o heartbeat e, a cada
        `PROGRESSO_A_CADA_SEGUNDOS`/`PROGRESSO_A_CADA_PRODUTOS`, recomputo os
        contadores (3 COUNTs) e persisto junto — a mesma `UPDATE ... WHERE
        lease_token=?` do heartbeat, então progresso e lease/heartbeat nunca
        se atrapalham. A verificação de pausa acontece ANTES disso, então a
        pausa continua instantânea.
    """

    # 5s deixa a tela (polling de 4s) no máximo ~9s atrás do real; 3 COUNTs
    # a cada 5s numa rodada de horas é desprezível. O teto por produtos
    # cobre o caso raro de muitos produtos rápidos seguidos.
    PROGRESSO_A_CADA_SEGUNDOS = 5.0
    PROGRESSO_A_CADA_PRODUTOS = 40

    def __init__(self, execucao_id: int, token: str):
        self.execucao_id = execucao_id
        self.token = token
        self._produtos_desde_progresso = 0
        self._ultimo_progresso = time.monotonic()

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

        self._produtos_desde_progresso += 1
        agora_mono = time.monotonic()
        vencido = (
            agora_mono - self._ultimo_progresso >= self.PROGRESSO_A_CADA_SEGUNDOS
            or self._produtos_desde_progresso >= self.PROGRESSO_A_CADA_PRODUTOS
        )
        if vencido:
            _persistir_contadores(self.execucao_id, self.token)
            self._produtos_desde_progresso = 0
            self._ultimo_progresso = agora_mono
        else:
            Execucao.objects.filter(pk=self.execucao_id, lease_token=self.token).update(
                heartbeat_em=timezone.now()
            )
        return None


# ---------------------------------------------------------------------------
# Sink de progresso: Execucao / LogItem
# ---------------------------------------------------------------------------


class EventosExecucao(EventosSincronizacao):
    """
    Sink de eventos que grava o histórico de UMA `Execucao` como `LogItem`s
    (o que a tela de auditoria lê). Usado pela task de cadastro em massa e,
    para uma tentativa individual a partir da tela de execução, pela view
    `RetentarVariacaoExecucaoView` — os MESMOS `LogItem`s, na MESMA `Execucao`,
    só que APPEND (nunca sobrescreve o log do erro original).
    """

    def __init__(self, execucao: Execucao):
        self.execucao = execucao

    def _log(self, nivel, mensagem, *, evento=EventoLog.GERAL, variacao=None, **detalhe):
        LogItem.objects.create(
            execucao=self.execucao,
            nivel=nivel,
            evento=evento,
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
            NivelLog.INFO,
            f"SKU {variacao.sku} criado no Tiny",
            evento=EventoLog.CRIADO,
            variacao=variacao,
            tiny_id=str(tiny_id),
        )

    def variacao_vinculada(self, variacao, tiny_id):
        self._log(
            NivelLog.INFO,
            f"SKU {variacao.sku} vinculado a produto existente no Tiny",
            evento=EventoLog.VINCULADO,
            variacao=variacao,
            tiny_id=str(tiny_id),
        )

    def variacao_bloqueada(self, variacao, motivo):
        self._log(
            NivelLog.AVISO,
            f"SKU {variacao.sku} bloqueado",
            evento=EventoLog.BLOQUEADO,
            variacao=variacao,
            motivo=motivo,
        )

    def variacao_erro(self, variacao, exc):
        self._log(
            NivelLog.ERRO,
            f"Falha ao sincronizar SKU {variacao.sku}",
            evento=EventoLog.ERRO,
            variacao=variacao,
            erro=str(exc),
        )

    def imagens(self, variacao, resultado):
        r = resultado.get("resultado")
        if r == tiny_sync.IMG_ENVIADA:
            self._log(
                NivelLog.INFO,
                f"Imagens do SKU {variacao.sku} enviadas ao Tiny",
                evento=EventoLog.IMAGENS,
                variacao=variacao,
                quantidade=len(resultado.get("desejadas") or []),
            )
        elif r == tiny_sync.IMG_RECONCILIADA:
            self._log(
                NivelLog.INFO,
                f"Imagens do SKU {variacao.sku} já estavam no Tiny — marcador reconciliado",
                evento=EventoLog.IMAGENS,
                variacao=variacao,
            )
        elif r == "erro":
            self._log(
                NivelLog.ERRO,
                f"Falha ao sincronizar imagens do SKU {variacao.sku}",
                evento=EventoLog.IMAGENS_ERRO,
                variacao=variacao,
                erro=resultado.get("erro", ""),
            )


def _atualizar_contadores(execucao: Execucao) -> None:
    """Recomputa os contadores da verdade do banco NO objeto (para o save do _finalizar)."""
    for campo, valor in _contadores_da_fila(execucao.instancia_id, execucao.fornecedor).items():
        setattr(execucao, campo, valor)


def recomputar_contadores_execucao(execucao: Execucao) -> None:
    """
    Recomputa e PERSISTE os contadores (`total_*`) de uma Execucao a partir da
    verdade do banco — a MESMA fonte (`_contadores_da_fila`) usada na
    finalização do cadastro em massa. Usado quando uma tentativa individual
    bem-sucedida muda o estado de um SKU (ERRO -> CADASTRADO) e o resumo da
    execução no topo da tela precisa acompanhar. NÃO toca em nenhum `LogItem`
    (o histórico do erro original continua intacto).
    """
    _atualizar_contadores(execucao)
    execucao.save(update_fields=[
        "total_lidos", "total_novos", "total_cadastrados", "total_erros", "total_ignorados"
    ])


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

    # Progresso imediato: numa retomada, a tela mostra o baseline (ex.: "421
    # cadastrados") já na 1ª atualização, sem esperar o 1º ciclo do controlador.
    _persistir_contadores(execucao_id, token, agora=agora)

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
            eventos=EventosExecucao(execucao),
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
    _finalizar(execucao_id, token, imagens_com_erro=resultado.imagens_erros)


def _finalizar(
    execucao_id,
    token,
    *,
    pausar: bool = False,
    motivo_falha: str | None = None,
    imagens_com_erro: int = 0,
) -> None:
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
            # Imagens que falharam não mudam o status da Variacao (o produto
            # está cadastrado), mas a rodada não ficou 100% — então é parcial.
            concluiu_tudo = (
                execucao.total_erros == 0
                and execucao.total_ignorados == 0
                and imagens_com_erro == 0
            )
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


# ---------------------------------------------------------------------------
# Retentativa em LOTE dos SKUs com erro de uma Execucao
# ---------------------------------------------------------------------------


class EventosRetentativa(EventosExecucao):
    """
    Sink das tentativas (individual OU em lote): grava os `LogItem` na
    `Execucao` ORIGINAL — APPEND, nunca sobrescreve o log do erro original.

    Um BLOQUEIO NÃO vira `LogItem`: não deve reclassificar o desfecho do SKU
    (ele continua contando na aba "Erros"); o motivo volta só na resposta.
    Um ERRO vira `LogItem` ERRO com a MENSAGEM NOVA.
    """

    def __init__(self, execucao):
        super().__init__(execucao)
        self.motivo_bloqueio = None
        self.erro = None

    def variacao_bloqueada(self, variacao, motivo):
        self.motivo_bloqueio = motivo

    def variacao_erro(self, variacao, exc):
        super().variacao_erro(variacao, exc)
        self.erro = str(exc)


@shared_task
def retentar_lote_task(retentativa_id, lease_token=None):
    """
    Processa um `RetentativaLote`: para cada `variacao_id` da fila (snapshot),
    SEQUENCIALMENTE, passa pelo MESMO fluxo do retry individual
    (`cadastrar_variacao_individual` -> `_processar_variacao`), gravando os
    `LogItem` na `Execucao` original. Um SKU que já está cadastrado é PULADO
    (idempotência). Erro num SKU NÃO interrompe os demais. Bate heartbeat e
    checa o lease antes de cada SKU (retomada: se o worker morre, o reaper
    marca `interrompido` e rodar de novo continua de onde parou).
    """
    lote = (
        RetentativaLote.objects.select_related("execucao", "execucao__instancia")
        .get(pk=retentativa_id)
    )
    token = lease_token or lote.lease_token

    with transaction.atomic():
        atual = RetentativaLote.objects.select_for_update().get(pk=retentativa_id)
        if atual.status != StatusRetentativaLote.RODANDO or (token and atual.lease_token != token):
            logger.info("retentar_lote_task %s abortada no claim (status=%s)", retentativa_id, atual.status)
            return
        token = atual.lease_token
        RetentativaLote.objects.filter(pk=retentativa_id).update(heartbeat_em=timezone.now())

    execucao = lote.execucao
    instancia = execucao.instancia
    if not instancia.access_token:
        _finalizar_lote(retentativa_id, token, aviso="instância não está conectada ao Tiny")
        return

    # Um cliente para todo o lote: o RateLimiterCompartilhado e o teto visto na
    # sessão (x-limit-api) valem entre SKUs; teto conservador de partida.
    cliente = TinyApiClient(instancia, somente_leitura=False, rate_limit_fallback=60)
    eventos = EventosRetentativa(execucao)

    for variacao_id in list(lote.variacao_ids):
        linha = (
            RetentativaLote.objects.filter(pk=retentativa_id)
            .values("lease_token", "status")
            .first()
        )
        if linha is None or linha["lease_token"] != token:
            logger.info("retentar_lote_task %s: lease perdido, encerrando sem tocar no estado", retentativa_id)
            return
        RetentativaLote.objects.filter(pk=retentativa_id, lease_token=token).update(
            heartbeat_em=timezone.now()
        )

        try:
            _retentar_um_do_lote(retentativa_id, execucao, instancia, variacao_id, cliente, eventos)
        except Exception:  # nunca deixa um SKU derrubar o lote inteiro
            logger.exception("retentar_lote_task %s: SKU %s explodiu fora do fluxo", retentativa_id, variacao_id)
            RetentativaLote.objects.filter(pk=retentativa_id).update(
                processados=F("processados") + 1, erros=F("erros") + 1
            )

    _finalizar_lote(retentativa_id, token)


def _retentar_um_do_lote(retentativa_id, execucao, instancia, variacao_id, cliente, eventos):
    with transaction.atomic():
        variacao = (
            Variacao.objects.select_for_update()
            .select_related("produto")
            .filter(pk=variacao_id, produto__instancia=instancia)
            .first()
        )
        if variacao is None:  # removida do espelho / de outra instância
            RetentativaLote.objects.filter(pk=retentativa_id).update(
                processados=F("processados") + 1, ignorados=F("ignorados") + 1
            )
            return

        if (variacao.tiny_id or "").strip() or variacao.status == StatusVariacao.CADASTRADO:
            # idempotência: já foi cadastrado (retry individual, rodada anterior…)
            RetentativaLote.objects.filter(pk=retentativa_id).update(
                processados=F("processados") + 1, ignorados=F("ignorados") + 1
            )
            return

        LogItem.objects.create(
            execucao=execucao,
            nivel=NivelLog.INFO,
            evento=EventoLog.GERAL,
            mensagem=(f"Nova tentativa de cadastro do SKU {variacao.sku} "
                      f"(retentativa em lote #{retentativa_id})")[:500],
            variacao=variacao,
            detalhe={"origem": "retentativa_lote", "retentativa_id": retentativa_id},
        )
        resultado = cadastrar_variacao_individual(
            instancia, variacao, cliente=cliente, eventos=eventos
        )

    campos = {"processados": F("processados") + 1}
    if resultado.criadas or resultado.vinculadas:
        campos["sucessos"] = F("sucessos") + 1
        recomputar_contadores_execucao(execucao)  # mantém o resumo do topo em dia
    else:  # bloqueado ou erro -> continua como erro
        campos["erros"] = F("erros") + 1
    RetentativaLote.objects.filter(pk=retentativa_id).update(**campos)


def _finalizar_lote(retentativa_id, token, *, aviso=None):
    with transaction.atomic():
        lote = RetentativaLote.objects.select_for_update().select_related("execucao").get(pk=retentativa_id)
        if token and lote.lease_token != token:
            logger.info("retentar_lote_task %s: lease trocou antes do fechamento", retentativa_id)
            return
        recomputar_contadores_execucao(lote.execucao)
        lote.status = StatusRetentativaLote.CONCLUIDO
        lote.heartbeat_em = timezone.now()
        lote.finalizado_em = timezone.now()
        lote.save(update_fields=["status", "heartbeat_em", "finalizado_em"])
        LogItem.objects.create(
            execucao=lote.execucao,
            nivel=NivelLog.INFO,
            evento=EventoLog.GERAL,
            mensagem=(f"Retentativa em lote #{retentativa_id} concluída: {lote.sucessos} "
                      f"cadastrado(s), {lote.erros} com erro, {lote.ignorados} já cadastrado(s)")[:500],
            detalhe={
                "origem": "retentativa_lote",
                "retentativa_id": retentativa_id,
                "sucessos": lote.sucessos,
                "erros": lote.erros,
                "ignorados": lote.ignorados,
                **({"aviso": aviso} if aviso else {}),
            },
        )


@shared_task
def reconciliar_retentativas_lote_travadas():
    """
    Tick do Celery Beat: um `RetentativaLote` `rodando` sem heartbeat recente é
    um job cujo worker morreu. Marca como `interrompido` (retomável — rodar de
    novo é idempotente). Condicional (não pisa num job que voltou a bater
    heartbeat no meio do tick).
    """
    limite = timezone.now() - timedelta(seconds=HEARTBEAT_TIMEOUT_SEGUNDOS)
    reconhecidas = 0
    for pk in list(
        RetentativaLote.objects.filter(
            status=StatusRetentativaLote.RODANDO, heartbeat_em__lt=limite
        ).values_list("pk", flat=True)
    ):
        if RetentativaLote.objects.filter(
            pk=pk, status=StatusRetentativaLote.RODANDO, heartbeat_em__lt=limite
        ).update(status=StatusRetentativaLote.INTERROMPIDO):
            reconhecidas += 1
    if reconhecidas:
        logger.warning("%s retentativa(s) em lote reconhecida(s) como interrompida(s)", reconhecidas)
    return reconhecidas
