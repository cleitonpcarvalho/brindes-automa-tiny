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


class LogItem(models.Model):
    """Uma linha de log de uma execução, opcionalmente ligada a uma variação."""

    execucao = models.ForeignKey(Execucao, on_delete=models.CASCADE, related_name="logs")
    variacao = models.ForeignKey(
        Variacao, on_delete=models.SET_NULL, null=True, blank=True, related_name="logs"
    )
    nivel = models.CharField(max_length=10, choices=NivelLog.choices, default=NivelLog.INFO)
    mensagem = models.CharField(max_length=500)
    detalhe = models.JSONField(default=dict, blank=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Log de execução"
        verbose_name_plural = "Logs de execução"
        ordering = ["criado_em"]
        indexes = [
            models.Index(fields=["execucao", "nivel"]),
        ]

    def __str__(self):
        return f"[{self.nivel}] {self.mensagem}"
