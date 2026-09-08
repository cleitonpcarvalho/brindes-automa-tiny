from django.contrib import admin

from .models import CredencialFornecedor, Instancia


class CredencialFornecedorInline(admin.TabularInline):
    model = CredencialFornecedor
    extra = 0
    fields = ("fornecedor", "ativo", "tiny_fornecedor_id", "criado_em")
    readonly_fields = ("criado_em",)
    # `credenciais` fica de fora do inline de propósito: é criptografado e
    # não deve aparecer em texto plano numa listagem lateral. `tiny_fornecedor_id`
    # entra: não é segredo e é o caminho de configuração manual mais rápido.


@admin.register(Instancia)
class InstanciaAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "slug",
        "status",
        "tentativas_falha",
        "rate_limit_por_minuto",
        "token_expira_em",
        "atualizado_em",
    )
    list_filter = ("status",)
    search_fields = ("nome", "slug")
    readonly_fields = (
        "slug",
        "ja_foi_autorizada",
        "criado_em",
        "atualizado_em",
        "token_emitido_em",
        "token_expira_em",
        "refresh_expira_em",
        "rate_limit_por_minuto",
        "oauth_state",
        "oauth_state_expira_em",
    )
    fieldsets = (
        (None, {"fields": ("nome", "slug", "status", "ja_foi_autorizada")}),
        (
            "Credenciais OAuth do Tiny",
            {
                "fields": (
                    "client_id",
                    "client_secret",
                    "access_token",
                    "refresh_token",
                    "token_emitido_em",
                    "token_expira_em",
                    "refresh_expira_em",
                )
            },
        ),
        ("Autorização em andamento", {"fields": ("oauth_state", "oauth_state_expira_em")}),
        ("Rate limit do Tiny", {"fields": ("rate_limit_por_minuto",)}),
        (
            "Padrões para cadastro no Tiny",
            {
                "fields": ("tiny_origem_padrao", "tiny_unidade_medida_padrao"),
                "description": "Sem valor padrão fixo no sistema — configure antes de "
                "rodar o cadastro de produtos (comando cadastrar_produtos_tiny).",
            },
        ),
        ("Falhas", {"fields": ("tentativas_falha", "ultimo_erro")}),
        ("Auditoria", {"fields": ("criado_em", "atualizado_em")}),
    )
    inlines = [CredencialFornecedorInline]


@admin.register(CredencialFornecedor)
class CredencialFornecedorAdmin(admin.ModelAdmin):
    list_display = ("instancia", "fornecedor", "ativo", "tiny_fornecedor_id", "criado_em")
    list_filter = ("fornecedor", "ativo")
    search_fields = ("instancia__nome", "instancia__slug")
    readonly_fields = ("criado_em",)
