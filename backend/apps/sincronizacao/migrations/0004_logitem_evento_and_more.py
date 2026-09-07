# Campo estruturado `LogItem.evento` para a tela de auditoria por SKU — em
# vez de interpretar o texto de `mensagem` em tempo de request.
#
# RETROCOMPATÍVEL: a coluna nasce com default 'geral'. O `RunPython`
# classifica os LogItems JÁ existentes a partir dos padrões de mensagem que
# ESTE código gera (determinísticos, não texto livre do usuário) + do
# `variacao_id`. Cobre a execução real da Asia que está pausada:
#   - "SKU <x> criado no Tiny"                    -> criado   (~421 linhas)
#   - "Falha ao sincronizar SKU <x>" (nivel erro) -> erro     (~6 linhas)
#   - "SKU <x> bloqueado"                         -> bloqueado
#   - "Imagens do SKU <x> ..." / "Falha ... imagens" -> imagens / imagens_erro
#   - início / pausa / conclusão / logs de importação de espelho -> geral
# Nada é apagado; nenhum LogItem perde texto/detalhe. Reverse: no-op.

from django.db import migrations, models


def classificar_logs_existentes(apps, schema_editor):
    LogItem = apps.get_model("sincronizacao", "LogItem")
    por_sku = LogItem.objects.filter(variacao__isnull=False)

    por_sku.filter(nivel="erro", mensagem__startswith="Falha ao sincronizar SKU").update(evento="erro")
    por_sku.filter(nivel="erro", mensagem__startswith="Falha ao sincronizar imagens do SKU").update(
        evento="imagens_erro"
    )
    por_sku.filter(mensagem__endswith="criado no Tiny").update(evento="criado")
    por_sku.filter(mensagem__contains="vinculado a produto existente").update(evento="vinculado")
    por_sku.filter(mensagem__endswith="bloqueado").update(evento="bloqueado")
    por_sku.filter(mensagem__startswith="Imagens do SKU", evento="geral").update(evento="imagens")
    # o que sobrou (com ou sem variacao) permanece 'geral'


class Migration(migrations.Migration):

    dependencies = [
        ('catalogo', '0008_alter_variacao_ncm'),
        ('sincronizacao', '0003_execucao_pause_resume_heartbeat'),
    ]

    operations = [
        migrations.AddField(
            model_name='logitem',
            name='evento',
            field=models.CharField(choices=[('geral', 'Log geral da execução'), ('criado', 'Cadastrado no Tiny'), ('vinculado', 'Já existente no Tiny (vinculado)'), ('bloqueado', 'Ignorado / bloqueado'), ('erro', 'Erro ao cadastrar'), ('imagens', 'Imagens sincronizadas'), ('imagens_erro', 'Falha ao sincronizar imagens')], db_index=True, default='geral', max_length=20),
        ),
        migrations.AddIndex(
            model_name='logitem',
            index=models.Index(fields=['execucao', 'evento'], name='sincronizac_execuca_4aa12d_idx'),
        ),
        migrations.AddIndex(
            model_name='logitem',
            index=models.Index(fields=['execucao', 'variacao'], name='sincronizac_execuca_b47a36_idx'),
        ),
        migrations.RunPython(classificar_logs_existentes, migrations.RunPython.noop),
    ]
