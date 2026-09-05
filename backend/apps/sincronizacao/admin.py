from django.contrib import admin

from .models import Execucao, LogItem


class LogItemInline(admin.TabularInline):
    model = LogItem
    extra = 0
    fields = ("criado_em", "nivel", "mensagem", "variacao")
    readonly_fields = ("criado_em",)


@admin.register(Execucao)
class ExecucaoAdmin(admin.ModelAdmin):
    list_display = (
        "instancia",
        "fornecedor",
        "tipo",
        "status",
        "iniciada_em",
        "finalizada_em",
        "total_lidos",
        "total_cadastrados",
        "total_erros",
    )
    list_filter = ("fornecedor", "tipo", "status", "instancia")
    readonly_fields = ("iniciada_em",)
    inlines = [LogItemInline]


@admin.register(LogItem)
class LogItemAdmin(admin.ModelAdmin):
    list_display = ("execucao", "nivel", "mensagem", "variacao", "criado_em")
    list_filter = ("nivel", "execucao__fornecedor")
    search_fields = ("mensagem",)
    readonly_fields = ("criado_em",)
