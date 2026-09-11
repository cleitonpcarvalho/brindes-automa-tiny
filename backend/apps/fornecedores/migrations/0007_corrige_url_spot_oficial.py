from django.db import migrations


URL_BASE_SPOT_ANTIGA = "https://www.spotgifts.com.br/fotos/produtos"
URL_BASE_SPOT_OFICIAL = "https://cdnbr.spotgifts.com.br/products/1000x1000/"


def corrigir_url_spot(apps, schema_editor):
    ConfiguracaoFornecedor = apps.get_model("fornecedores", "ConfiguracaoFornecedor")
    ConfiguracaoFornecedor.objects.filter(
        fornecedor="spot",
        url_base_imagens=URL_BASE_SPOT_ANTIGA,
    ).update(url_base_imagens=URL_BASE_SPOT_OFICIAL)


class Migration(migrations.Migration):
    dependencies = [
        ("fornecedores", "0006_atualizacaovariacaofornecedor"),
    ]

    operations = [
        migrations.RunPython(corrigir_url_spot, migrations.RunPython.noop),
    ]
