import importlib

from django.test import TestCase
from django.apps import apps

from apps.fornecedores.models import ConfiguracaoFornecedor


MIGRATION = importlib.import_module(
    "apps.fornecedores.migrations.0007_corrige_url_spot_oficial"
)


class ConfiguracaoSpotMigrationTests(TestCase):
    def test_url_antiga_da_spot_e_corrigida_idempotentemente(self):
        ConfiguracaoFornecedor.objects.create(
            fornecedor="spot",
            url_base_imagens=MIGRATION.URL_BASE_SPOT_ANTIGA,
        )

        MIGRATION.corrigir_url_spot(apps, None)
        MIGRATION.corrigir_url_spot(apps, None)

        self.assertEqual(
            ConfiguracaoFornecedor.objects.get(fornecedor="spot").url_base_imagens,
            MIGRATION.URL_BASE_SPOT_OFICIAL,
        )

    def test_configuracao_personalizada_da_spot_nao_e_sobrescrita(self):
        personalizada = "https://cdn.exemplo.local/spot/"
        ConfiguracaoFornecedor.objects.create(
            fornecedor="spot",
            url_base_imagens=personalizada,
        )

        MIGRATION.corrigir_url_spot(apps, None)

        self.assertEqual(
            ConfiguracaoFornecedor.objects.get(fornecedor="spot").url_base_imagens,
            personalizada,
        )
