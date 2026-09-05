from django.apps import AppConfig


class FornecedoresConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.fornecedores"
    label = "fornecedores"
    verbose_name = "Fornecedores"

    def ready(self):
        from . import signals  # noqa: F401
