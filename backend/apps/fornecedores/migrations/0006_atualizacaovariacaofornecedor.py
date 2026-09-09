# Generated manually for the asynchronous individual supplier refresh.
from django.db import migrations, models
import django.db.models.deletion
from django.db.models import Q


class Migration(migrations.Migration):
    dependencies = [
        ("catalogo", "0009_renomeia_preco_sincronizado_para_custo_e_marcador_dados"),
        ("fornecedores", "0005_cadenciafornecedor_propagar_tiny"),
        ("instancias", "0007_credencialfornecedor_tiny_fornecedor_id"),
    ]

    operations = [
        migrations.CreateModel(
            name="AtualizacaoVariacaoFornecedor",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("fornecedor", models.CharField(choices=[("xbz", "XBZ"), ("asia", "Asia Import"), ("somarcas", "Só Marcas"), ("spot", "Spot Gifts")], max_length=20)),
                ("status", models.CharField(choices=[("rodando", "Rodando"), ("sucesso", "Sucesso"), ("erro", "Erro"), ("interrompido", "Interrompido")], default="rodando", max_length=20)),
                ("celery_task_id", models.CharField(blank=True, default="", max_length=255)),
                ("erro", models.TextField(blank=True, default="")),
                ("criado_em", models.DateTimeField(auto_now_add=True)),
                ("iniciado_em", models.DateTimeField(blank=True, null=True)),
                ("finalizado_em", models.DateTimeField(blank=True, null=True)),
                ("heartbeat_em", models.DateTimeField(blank=True, null=True)),
                ("instancia", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="atualizacoes_variacao_fornecedor", to="instancias.instancia")),
                ("variacao", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="atualizacoes_fornecedor", to="catalogo.variacao")),
            ],
            options={
                "ordering": ["-criado_em"],
                "indexes": [
                    models.Index(fields=["variacao", "-criado_em"], name="fornecedore_variaca_b0d803_idx"),
                    models.Index(fields=["status", "heartbeat_em"], name="fornecedore_status_1cef9a_idx"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="atualizacaovariacaofornecedor",
            constraint=models.UniqueConstraint(condition=Q(status="rodando"), fields=("variacao",), name="uma_atualizacao_fornecedor_rodando_por_variacao"),
        ),
    ]
