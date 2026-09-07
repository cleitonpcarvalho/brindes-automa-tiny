# Nova opção de TipoExecucao: "cadastro_tiny" (sincronização de produtos com
# o Tiny, disparada pela interface). Só muda as choices — a coluna continua
# CharField(max_length=20); nenhuma linha existente é alterada.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sincronizacao', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='execucao',
            name='tipo',
            field=models.CharField(choices=[('carga_inicial', 'Carga inicial'), ('incremental', 'Incremental'), ('cadastro_tiny', 'Cadastro no Tiny')], max_length=20),
        ),
    ]
