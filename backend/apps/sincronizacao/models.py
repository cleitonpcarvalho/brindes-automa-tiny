from django.db import models

from apps.catalogo.models import Variacao
from apps.instancias.constants import Fornecedor
from apps.instancias.models import Instancia


class TipoExecucao(models.TextChoices):
    CARGA_INICIAL = "carga_inicial", "Carga inicial"
    INCREMENTAL = "incremental", "Incremental"


class StatusExecucao(models.TextChoices):
    RODANDO = "rodando", "Rodando"
    SUCESSO = "sucesso", "Sucesso"
    FALHA = "falha", "Falha"
    PARCIAL = "parcial", "Parcial"


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

    class Meta:
        verbose_name = "Execução"
        verbose_name_plural = "Execuções"
        ordering = ["-iniciada_em"]
        indexes = [
            models.Index(fields=["instancia", "fornecedor", "-iniciada_em"]),
        ]

    def __str__(self):
        return f"{self.instancia} · {self.fornecedor} · {self.iniciada_em:%Y-%m-%d %H:%M}"


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
