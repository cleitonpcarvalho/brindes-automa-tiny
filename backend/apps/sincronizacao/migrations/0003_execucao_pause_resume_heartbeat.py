# Pause/resume + heartbeat/lease da sincronização em massa com o Tiny:
# novos campos heartbeat_em/lease_token/pausa_solicitada + novos StatusExecucao
# (pausando/pausado/interrompido). Aditivo; nenhuma linha existente é alterada.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('sincronizacao', '0002_alter_execucao_tipo'),
    ]

    operations = [
        migrations.AddField(
            model_name='execucao',
            name='heartbeat_em',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='execucao',
            name='lease_token',
            field=models.CharField(blank=True, default='', max_length=36),
        ),
        migrations.AddField(
            model_name='execucao',
            name='pausa_solicitada',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='execucao',
            name='status',
            field=models.CharField(choices=[('rodando', 'Rodando'), ('pausando', 'Pausando'), ('pausado', 'Pausado'), ('sucesso', 'Sucesso'), ('falha', 'Falha'), ('parcial', 'Parcial'), ('interrompido', 'Interrompido')], default='rodando', max_length=20),
        ),
    ]
