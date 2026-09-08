# Regra definitiva de preço (cliente, 2026-09-08): o valor do fornecedor é
# CUSTO; a venda no Tiny fica zerada. O marcador antigo `preco_tiny_sincronizado`
# rastreava o preço de VENDA publicado — semântica agora incorreta. Renomeado
# (RenameField preserva os dados) para `preco_custo_tiny_sincronizado`, e
# adicionado `dados_tiny_sincronizados_em` (idempotência do backfill).

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('catalogo', '0008_alter_variacao_ncm'),
    ]

    operations = [
        migrations.RenameField(
            model_name='variacao',
            old_name='preco_tiny_sincronizado',
            new_name='preco_custo_tiny_sincronizado',
        ),
        migrations.AlterField(
            model_name='variacao',
            name='preco_custo_tiny_sincronizado',
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text=(
                    'Último `precos.precoCusto` efetivamente publicado no cadastro do '
                    'produto no Tiny — igual ao `preco` do fornecedor no momento da '
                    'publicação. Enquanto for diferente de `preco` (ou nulo), o custo no '
                    'Tiny está desatualizado (comando `corrigir_dados_produto_tiny`). Regra '
                    'definitiva (confirmada pelo cliente em 2026-09-08): o valor do '
                    'fornecedor é CUSTO; o preço de VENDA no Tiny fica sempre zerado. '
                    'Era `preco_tiny_sincronizado`.'
                ),
                max_digits=10,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name='variacao',
            name='dados_tiny_sincronizados_em',
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text=(
                    'Última vez que `corrigir_dados_produto_tiny` confirmou no Tiny o '
                    'pacote da regra definitiva deste SKU (descricaoComplementar = '
                    'Produto.descricao, fornecedores, precoCusto = preco, '
                    'preco/precoPromocional = 0). Nulo = ainda não corrigido. Marcador '
                    'de idempotência/retomada do backfill.'
                ),
            ),
        ),
    ]
