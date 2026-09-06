from rest_framework import serializers

from apps.instancias.constants import Fornecedor

from .models import Variacao


class VariacaoEspelhoSerializer(serializers.ModelSerializer):
    """
    Uma linha da aba "Produtos" do detalhe da instância.

    A unidade é a Variacao — o SKU. É ela, não o Produto-pai, que vira um
    produto no Tiny (regra de negócio nº 1, ver apps.catalogo.models.Variacao),
    então cada linha aqui é uma unidade cadastrável independente. Os campos do
    Produto-pai (fornecedor, código-pai, nome) vêm achatados só para leitura,
    via `source`, sem duplicar a entidade.
    """

    fornecedor = serializers.ChoiceField(
        source="produto.fornecedor", choices=Fornecedor.choices, read_only=True
    )
    produto_codigo_pai = serializers.CharField(source="produto.codigo_pai", read_only=True)
    produto_nome = serializers.CharField(source="produto.nome", read_only=True)
    produto_descontinuado = serializers.BooleanField(
        source="produto.descontinuado", read_only=True
    )
    # `status` é a situação da variação em relação ao Tiny (pendente,
    # aguardando reposição, cadastrado, descontinuado, erro); o rótulo legível
    # acompanha para a UI não precisar reimplementar o mapa de choices.
    status_rotulo = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Variacao
        fields = [
            "id",
            "fornecedor",
            "produto_codigo_pai",
            "produto_nome",
            "produto_descontinuado",
            "sku",
            "nome",
            "cor",
            "tamanho",
            "capacidade",
            "preco",
            "estoque",
            "status",
            "status_rotulo",
            "tiny_id",
            "estoque_tiny_sincronizado",
            "ultimo_erro",
            "cadastrado_em",
            "atualizado_em",
        ]
