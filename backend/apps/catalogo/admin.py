from django.contrib import admin

from .models import Produto, Variacao


class VariacaoInline(admin.TabularInline):
    model = Variacao
    extra = 0
    fields = ("sku", "nome", "cor", "tamanho", "preco", "estoque", "status", "tiny_id")
    readonly_fields = ("cadastrado_em",)
    show_change_link = True


@admin.register(Produto)
class ProdutoAdmin(admin.ModelAdmin):
    list_display = (
        "codigo_pai",
        "nome",
        "fornecedor",
        "instancia",
        "ativo",
        "descontinuado",
        "atualizado_em",
    )
    list_filter = ("fornecedor", "ativo", "descontinuado", "instancia")
    search_fields = ("codigo_pai", "nome")
    readonly_fields = ("hash_conteudo", "criado_em", "atualizado_em")
    inlines = [VariacaoInline]


@admin.register(Variacao)
class VariacaoAdmin(admin.ModelAdmin):
    list_display = (
        "sku",
        "nome",
        "produto",
        "status",
        "preco",
        "estoque",
        "tiny_id",
        "atualizado_em",
    )
    list_filter = ("status", "produto__fornecedor")
    search_fields = ("sku", "nome", "tiny_id")
    readonly_fields = ("hash_conteudo", "criado_em", "atualizado_em", "cadastrado_em")
