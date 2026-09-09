from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sincronizacao", "0005_retentativa_lote"),
    ]

    operations = [
        migrations.AddField(
            model_name="retentativalote",
            name="parada_solicitada",
            field=models.BooleanField(
                default=False,
                help_text="Solicitação cooperativa para parar antes do próximo item.",
            ),
        ),
    ]
