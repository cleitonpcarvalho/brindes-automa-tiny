from django.db import models

from apps.catalogo.models import Variacao
from apps.instancias.constants import Fornecedor
from apps.instancias.models import Instancia


class TipoExecucao(models.TextChoices):
    CARGA_INICIAL = "carga_inicial", "Carga inicial"
    INCREMENTAL = "incremental", "Incremental"
    # Sincronização de produtos com o Tiny (criação/vínculo + imagens),
    # disparada pela interface. Não é ingestão de fornecedor.
    CADASTRO_TINY = "cadastro_tiny", "Cadastro no Tiny"


class StatusExecucao(models.TextChoices):
    RODANDO = "rodando", "Rodando"
    # Pausa cooperativa da sincronização em massa com o Tiny: PAUSANDO = a
    # task ainda está terminando a unidade de trabalho atual e vai encerrar;
    # PAUSADO = encerrou por pausa e pode ser retomada (mesma Execucao).
    PAUSANDO = "pausando", "Pausando"
    PAUSADO = "pausado", "Pausado"
    SUCESSO = "sucesso", "Sucesso"
    FALHA = "falha", "Falha"
    PARCIAL = "parcial", "Parcial"
    # A task ficou sem heartbeat (worker morreu/reiniciou). Não é falha
    # definitiva — é retomável, com toda a idempotência do fluxo.
    INTERROMPIDO = "interrompido", "Interrompido"


# Estados "abertos": existe trabalho em andamento ou pausado para aquele
# (instância, fornecedor) — não se pode iniciar outra Execucao do mesmo par.
STATUS_EXECUCAO_ABERTOS = (
    StatusExecucao.RODANDO,
    StatusExecucao.PAUSANDO,
    StatusExecucao.PAUSADO,
    StatusExecucao.INTERROMPIDO,
)
# Estados em que uma task está (ou deveria estar) ativa — bloqueiam também a
# sincronização de espelho do mesmo fornecedor.
STATUS_EXECUCAO_ATIVOS = (StatusExecucao.RODANDO, StatusExecucao.PAUSANDO)


class Execucao(models.Model):
    """Uma rodada de sincronização de um fornecedor para uma instância."""

    instancia = models.ForeignKey(Instancia, on_delete=models.CASCADE, related_name="execucoes")
    fornecedor = models.CharField(max_length=20, choices=Fornecedor.choices)
    tipo = models.CharField(max_length=20, choices=TipoExecucao.choices)

    iniciada_em = models.DateTimeField(auto_now_add=True)
    finalizada_em = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=StatusExecucao.choices, default=StatusExecucao.RODANDO
    )

    total_lidos = models.PositiveIntegerField(default=0)
    total_novos = models.PositiveIntegerField(default=0)
    total_atualizados = models.PositiveIntegerField(default=0)
    total_cadastrados = models.PositiveIntegerField(default=0)
    total_ignorados = models.PositiveIntegerField(default=0)
    total_erros = models.PositiveIntegerField(default=0)
    mensagem_erro = models.TextField(blank=True)

    # -- Pause/resume + heartbeat (só a sincronização em massa com o Tiny) --
    # Sinalizador cooperativo: a task o lê ANTES de cada produto e, se
    # verdadeiro, termina a unidade atual e encerra em `pausado`.
    pausa_solicitada = models.BooleanField(default=False)
    # Token do "dono" atual da execução. Cada start/retomada gera um novo;
    # a task só escreve enquanto `lease_token` no banco == o seu. Um zumbi
    # de uma retomada anterior perde o lease e para sozinho.
    lease_token = models.CharField(max_length=36, blank=True, default="")
    # Última prova de vida da task. Se `status=rodando`/`pausando` e este
    # timestamp está velho além do timeout, a execução está travada
    # (worker morreu) e é reconhecida como `interrompido`.
    heartbeat_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Execução"
        verbose_name_plural = "Execuções"
        ordering = ["-iniciada_em"]
        indexes = [
            models.Index(fields=["instancia", "fornecedor", "-iniciada_em"]),
        ]

    def __str__(self):
        return f"{self.instancia} · {self.fornecedor} · {self.iniciada_em:%Y-%m-%d %H:%M}"

    @property
    def duracao_segundos(self):
        if not self.finalizada_em:
            return None
        return (self.finalizada_em - self.iniciada_em).total_seconds()


class NivelLog(models.TextChoices):
    INFO = "info", "Info"
    AVISO = "aviso", "Aviso"
    ERRO = "erro", "Erro"


class EventoLog(models.TextChoices):
    """
    Tipo estruturado do log — o que a auditoria por SKU usa em vez de
    interpretar o texto de `mensagem`. `geral` = log da execução como um
    todo (início, pausa, conclusão, ingestão de espelho); os demais são
    resultados de UM produto/SKU (sempre com `variacao` preenchida).
    """

    GERAL = "geral", "Log geral da execução"
    CRIADO = "criado", "Cadastrado no Tiny"
    VINCULADO = "vinculado", "Já existente no Tiny (vinculado)"
    BLOQUEADO = "bloqueado", "Ignorado / bloqueado"
    ERRO = "erro", "Erro ao cadastrar"
    IMAGENS = "imagens", "Imagens sincronizadas"
    IMAGENS_ERRO = "imagens_erro", "Falha ao sincronizar imagens"


# Eventos que representam o desfecho de um SKU numa execução (uma linha da
# tabela de auditoria). `imagens*` é informação acessória do mesmo SKU.
EVENTOS_DESFECHO = (
    EventoLog.CRIADO,
    EventoLog.VINCULADO,
    EventoLog.BLOQUEADO,
    EventoLog.ERRO,
)


class LogItem(models.Model):
    """Uma linha de log de uma execução, opcionalmente ligada a uma variação."""

    execucao = models.ForeignKey(Execucao, on_delete=models.CASCADE, related_name="logs")
    variacao = models.ForeignKey(
        Variacao, on_delete=models.SET_NULL, null=True, blank=True, related_name="logs"
    )
    nivel = models.CharField(max_length=10, choices=NivelLog.choices, default=NivelLog.INFO)
    evento = models.CharField(
        max_length=20, choices=EventoLog.choices, default=EventoLog.GERAL, db_index=True
    )
    mensagem = models.CharField(max_length=500)
    detalhe = models.JSONField(default=dict, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Log de execução"
        verbose_name_plural = "Logs de execução"
        ordering = ["criado_em"]
        indexes = [
            models.Index(fields=["execucao", "nivel"]),
            models.Index(fields=["execucao", "evento"]),
            models.Index(fields=["execucao", "variacao"]),
        ]

    def __str__(self):
        return f"[{self.nivel}] {self.mensagem}"


class StatusRetentativaLote(models.TextChoices):
    RODANDO = "rodando", "Rodando"
    CONCLUIDO = "concluido", "Concluído"
    # Worker morreu (sem heartbeat) — não é falha definitiva: rodar de novo é
    # idempotente (pula os SKUs já cadastrados) e continua de onde parou.
    INTERROMPIDO = "interrompido", "Interrompido"


class RetentativaLote(models.Model):
    """
    Um job de "tentar novamente em lote" os SKUs com ERRO de UMA `Execucao` de
    cadastro no Tiny.

    RASTREIA só progresso + lease/heartbeat. As NOVAS tentativas de cada SKU
    são gravadas como `LogItem` na `Execucao` ORIGINAL (mesmo padrão do retry
    individual — histórico preservado, nada é apagado). O job processa os SKUs
    SEQUENCIALMENTE, cada um por `cadastrar_variacao_individual` ->
    `_processar_variacao` (a MESMA regra do cadastro em massa e do retry
    individual — nenhuma regra copiada).

    Concorrência: no máximo um job `rodando` por `Execucao` (checado no start,
    sob `select_for_update` da Instancia); `select_for_update` por `Variacao`
    dentro do job serializa contra o retry individual do mesmo SKU.

    Idempotência: `variacao_ids` é a fila fixa (snapshot do start); ao chegar
    num SKU que já está `cadastrado` (retry individual, rodada anterior), o job
    PULA (`ignorados`), não recadastra.
    """

    execucao = models.ForeignKey(
        Execucao, on_delete=models.CASCADE, related_name="retentativas_lote"
    )
    variacao_ids = models.JSONField(
        default=list,
        blank=True,
        help_text="variacao_id dos SKUs a retentar — snapshot resolvido no start. Fila fixa.",
    )
    selecao_todos = models.BooleanField(
        default=False, help_text="True = o operador pediu 'todos os erros da execução'."
    )

    status = models.CharField(
        max_length=20,
        choices=StatusRetentativaLote.choices,
        default=StatusRetentativaLote.RODANDO,
    )
    lease_token = models.CharField(max_length=36, blank=True, default="")
    heartbeat_em = models.DateTimeField(null=True, blank=True)
    parada_solicitada = models.BooleanField(
        default=False,
        help_text="Solicitação cooperativa para parar antes do próximo item.",
    )

    total = models.PositiveIntegerField(default=0)
    processados = models.PositiveIntegerField(default=0)
    sucessos = models.PositiveIntegerField(default=0)
    erros = models.PositiveIntegerField(default=0)
    ignorados = models.PositiveIntegerField(
        default=0, help_text="SKU que já estava cadastrado quando o lote chegou nele."
    )

    criado_em = models.DateTimeField(auto_now_add=True)
    finalizado_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name = "Retentativa em lote"
        verbose_name_plural = "Retentativas em lote"
        ordering = ["-criado_em"]
        indexes = [models.Index(fields=["execucao", "-criado_em"])]

    def __str__(self):
        return f"Retentativa em lote #{self.pk} · execução {self.execucao_id} · {self.status}"
