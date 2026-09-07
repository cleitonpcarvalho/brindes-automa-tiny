# Configura a URL base oficial das imagens da Spot (confirmada por
# amostragem em 2026-09-07: os arquivos de `AllImageList`/`MainImage` são
# servidos em https://www.spotgifts.com.br/fotos/produtos/<arquivo>).
#
# A partir daqui o normalizador da Spot passa a montar `Variacao.imagens`.
# As variações Spot JÁ importadas não mudam sozinhas (o hash do payload não
# muda) — use o comando `backfill_imagens_spot` para preenchê-las.

from django.db import migrations

URL_BASE_SPOT = "https://www.spotgifts.com.br/fotos/produtos"


def definir_url_base(apps, schema_editor):
    ConfiguracaoFornecedor = apps.get_model("fornecedores", "ConfiguracaoFornecedor")
    ConfiguracaoFornecedor.objects.update_or_create(
        fornecedor="spot",
        defaults={"url_base_imagens": URL_BASE_SPOT},
    )


def limpar_url_base(apps, schema_editor):
    ConfiguracaoFornecedor = apps.get_model("fornecedores", "ConfiguracaoFornecedor")
    ConfiguracaoFornecedor.objects.filter(
        fornecedor="spot", url_base_imagens=URL_BASE_SPOT
    ).update(url_base_imagens="")


class Migration(migrations.Migration):

    dependencies = [
        ("fornecedores", "0003_alter_cadenciafornecedor_ativo"),
    ]

    operations = [
        migrations.RunPython(definir_url_base, limpar_url_base),
    ]
