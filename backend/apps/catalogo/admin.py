from django.contrib import admin

from .models import Produto, ProdutoTiny, Variacao


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


@admin.register(ProdutoTiny)
class ProdutoTinyAdmin(admin.ModelAdmin):
    """Espelho somente leitura do catálogo do Tiny — nunca editar aqui."""

    list_display = (
        "tiny_id",
        "sku",
        "descricao",
        "situacao",
        "tipo",
        "gtin",
        "ncm",
        "tem_detalhe",
        "sincronizado_em",
    )
    list_filter = ("instancia", "situacao", "tipo", "tem_detalhe")
    search_fields = ("sku", "descricao", "gtin", "ncm", "tiny_id")
    readonly_fields = [f.name for f in ProdutoTiny._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False
