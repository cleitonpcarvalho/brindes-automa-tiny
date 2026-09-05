from django.core.exceptions import ValidationError
from django.db import models

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
    ativo = models.BooleanField(default=True)
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
