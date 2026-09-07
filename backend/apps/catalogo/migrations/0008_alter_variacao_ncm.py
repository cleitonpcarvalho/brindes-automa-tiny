# Só atualiza o help_text de Variacao.ncm: a Spot passou a mapear o NCM a
# partir do Taric de 8 dígitos (apps/fornecedores/spot.py:_ncm_do_taric).
# Nenhuma mudança de schema — a coluna continua CharField(max_length=20).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalogo', '0007_variacao_imagens_tiny_sincronizadas'),
    ]

    operations = [
        migrations.AlterField(
            model_name='variacao',
            name='ncm',
            field=models.CharField(blank=True, help_text="NCM brasileiro. Na Spot o campo de origem é o 'Taric': o normalizador (apps/fornecedores/spot.py, _ncm_do_taric) aproveita só quando ele tem 8 dígitos (~95,5% da amostra) e nunca trunca os códigos CN10/TARIC da UE de 9-10 dígitos; o valor cru fica sempre em atributos['taric']. Backfill dos registros antigos: backfill_ncm_spot.", max_length=20),
        ),
    ]
