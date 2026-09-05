from django.contrib import admin

from .models import CadenciaFornecedor, ConfiguracaoFornecedor


@admin.register(ConfiguracaoFornecedor)
class ConfiguracaoFornecedorAdmin(admin.ModelAdmin):
    list_display = ("fornecedor", "url_base_imagens", "atualizado_em")
    list_filter = ("fornecedor",)


@admin.register(CadenciaFornecedor)
class CadenciaFornecedorAdmin(admin.ModelAdmin):
    list_display = (
        "instancia",
        "fornecedor",
        "intervalo_minutos",
        "proxima_execucao_em",
        "ativo",
    )
    list_filter = ("fornecedor", "ativo")
    search_fields = ("instancia__nome", "instancia__slug")
    readonly_fields = ("proxima_execucao_em", "criado_em", "atualizado_em")
