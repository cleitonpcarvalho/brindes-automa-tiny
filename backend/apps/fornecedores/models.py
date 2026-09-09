from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q

from apps.instancias.constants import Fornecedor
from apps.instancias.models import Instancia


class ConfiguracaoFornecedor(models.Model):
    """
    Configuração não sensível por fornecedor (não é credencial — isso fica
    em CredencialFornecedor). Hoje existe só para a pendência da Spot: as
    imagens vêm apenas como nome de arquivo, sem host nem caminho. Fica
    vazio até o fornecedor confirmar a URL base — enquanto vazio, o
    normalizador da Spot (apps/fornecedores/spot.py) não monta nenhuma URL
    de imagem.
    """

    fornecedor = models.CharField(max_length=20, choices=Fornecedor.choices, unique=True)
    url_base_imagens = models.URLField(
        blank=True,
        help_text="Usado para montar a URL de imagens quando o fornecedor devolve só o nome "
        "do arquivo (hoje: Spot). Vazio = imagem não é montada.",
    )
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Configuração de fornecedor"
        verbose_name_plural = "Configurações de fornecedor"

    def __str__(self):
        return self.get_fornecedor_display()


class CadenciaFornecedor(models.Model):
    """
    De quanto em quanto tempo sincronizar um fornecedor para uma instância.
    Configurável por (instancia, fornecedor) — não fixo no código — e lido
    pelo tick do Celery Beat (apps/fornecedores/tasks.py).
    """

    # Regra do cliente: xbz tem limite de 24 chamadas/dia, então nunca pode
    # sincronizar mais que 1x/hora. Isso é uma trava rígida (mínimo), não um
    # valor sugerido — os demais fornecedores também nascem com 60min de
    # cadência por padrão, mas podem ser configurados para qualquer coisa.
    CADENCIA_MINIMA_XBZ_MINUTOS = 60

    instancia = models.ForeignKey(
        Instancia, on_delete=models.CASCADE, related_name="cadencias_fornecedor"
    )
    fornecedor = models.CharField(max_length=20, choices=Fornecedor.choices)
    intervalo_minutos = models.PositiveIntegerField(default=60)
    proxima_execucao_em = models.DateTimeField(null=True, blank=True)
    # Nasce DESLIGADA: nenhuma sincronização automática começa sem o usuário
    # ativar explicitamente a cadência pela interface. Cadências já
    # existentes no banco não são afetadas por esta mudança de default.
    ativo = models.BooleanField(default=False)
    # Segundo opt-in, também DESLIGADO por padrão: com `ativo` a cadência só
    # atualiza o ESPELHO local; com `propagar_tiny` ligado, logo após cada
    # importação de espelho bem-sucedida o sistema também reflete ao Tiny o
    # que ficou fora de sincronia — cadastra os produtos novos elegíveis,
    # empurra estoque/custo/descrição que mudaram e reenvia imagens trocadas
    # (reaproveitando os mesmos serviços do cadastro manual, sem escrever
    # nada além do necessário). Enquanto desligado, o comportamento é
    # idêntico ao de hoje: nenhuma escrita automática no Tiny.
    propagar_tiny = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Cadência de sincronização"
        verbose_name_plural = "Cadências de sincronização"
        constraints = [
            models.UniqueConstraint(
                fields=["instancia", "fornecedor"], name="unica_cadencia_por_instancia_fornecedor"
            )
        ]

    def __str__(self):
        return f"{self.instancia} · {self.get_fornecedor_display()} · {self.intervalo_minutos}min"

    def clean(self):
        if self.fornecedor == Fornecedor.XBZ and self.intervalo_minutos < self.CADENCIA_MINIMA_XBZ_MINUTOS:
            raise ValidationError(
                f"xbz não pode sincronizar com intervalo menor que "
                f"{self.CADENCIA_MINIMA_XBZ_MINUTOS} minutos (limite de 24 chamadas/dia)."
            )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class StatusAtualizacaoVariacao(models.TextChoices):
    RODANDO = "rodando", "Rodando"
    SUCESSO = "sucesso", "Sucesso"
    ERRO = "erro", "Erro"
    INTERROMPIDO = "interrompido", "Interrompido"


class AtualizacaoVariacaoFornecedor(models.Model):
    """Operação assíncrona de atualização de uma única variação do fornecedor."""

    instancia = models.ForeignKey(
        Instancia, on_delete=models.CASCADE, related_name="atualizacoes_variacao_fornecedor"
    )
    variacao = models.ForeignKey(
        "catalogo.Variacao", on_delete=models.CASCADE, related_name="atualizacoes_fornecedor"
    )
    fornecedor = models.CharField(max_length=20, choices=Fornecedor.choices)
    status = models.CharField(
        max_length=20,
        choices=StatusAtualizacaoVariacao.choices,
        default=StatusAtualizacaoVariacao.RODANDO,
    )
    celery_task_id = models.CharField(max_length=255, blank=True, default="")
    erro = models.TextField(blank=True, default="")
    criado_em = models.DateTimeField(auto_now_add=True)
    iniciado_em = models.DateTimeField(null=True, blank=True)
    finalizado_em = models.DateTimeField(null=True, blank=True)
    heartbeat_em = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-criado_em"]
        indexes = [
            models.Index(fields=["variacao", "-criado_em"]),
            models.Index(fields=["status", "heartbeat_em"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["variacao"],
                condition=Q(status=StatusAtualizacaoVariacao.RODANDO),
                name="uma_atualizacao_fornecedor_rodando_por_variacao",
            )
        ]

    def __str__(self):
        return f"Atualização do fornecedor #{self.pk} · variação {self.variacao_id} · {self.status}"
