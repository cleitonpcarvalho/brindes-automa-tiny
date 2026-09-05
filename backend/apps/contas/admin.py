from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from .models import Usuario


@admin.register(Usuario)
class UsuarioAdmin(DjangoUserAdmin):
    ordering = ("email",)
    list_display = ("email", "nome", "is_staff", "is_active", "criado_em")
    list_filter = ("is_staff", "is_active")
    search_fields = ("email", "nome")
    readonly_fields = ("criado_em", "last_login")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Informações pessoais", {"fields": ("nome",)}),
        (
            "Permissões",
            {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")},
        ),
        ("Datas", {"fields": ("last_login", "criado_em")}),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "nome", "password1", "password2"),
            },
        ),
    )
