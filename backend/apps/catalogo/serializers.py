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


class VariacaoDetalheSerializer(serializers.ModelSerializer):
    """
    Detalhe de UMA variação (SKU) do espelho local — a tela
    `/instancias/<slug>/produtos/<id>`. Somente leitura.

    Junta, achatados via `source`, os campos do Produto-pai e todos os
    campos úteis da própria Variacao (dimensões, pesos, atributos
    normalizados, marcadores de sincronização, timestamps). NÃO expõe
    `payload_bruto` (cru do fornecedor, volumoso) — nada sensível vive aqui
    (credenciais/tokens ficam em CredencialFornecedor/Instancia).

    A tela se adapta ao que existir: campos vazios/nulos são "—" ou
    omitidos no frontend; cada fornecedor preenche um subconjunto diferente.
    """

    fornecedor = serializers.ChoiceField(
        source="produto.fornecedor", choices=Fornecedor.choices, read_only=True
    )
    fornecedor_rotulo = serializers.CharField(
        source="produto.get_fornecedor_display", read_only=True
    )
    produto_id = serializers.IntegerField(source="produto.id", read_only=True)
    produto_codigo_pai = serializers.CharField(source="produto.codigo_pai", read_only=True)
    produto_nome = serializers.CharField(source="produto.nome", read_only=True)
    produto_descricao = serializers.CharField(source="produto.descricao", read_only=True)
    produto_categorias = serializers.JSONField(source="produto.categorias", read_only=True)
    produto_imagens = serializers.JSONField(source="produto.imagens", read_only=True)
    produto_atributos = serializers.JSONField(source="produto.atributos", read_only=True)
    produto_descontinuado = serializers.BooleanField(
        source="produto.descontinuado", read_only=True
    )
    produto_atualizado_em_fornecedor = serializers.DateTimeField(
        source="produto.atualizado_em_fornecedor", read_only=True, allow_null=True
    )
    status_rotulo = serializers.CharField(source="get_status_display", read_only=True)

    class Meta:
        model = Variacao
        fields = [
            "id",
            "fornecedor",
            "fornecedor_rotulo",
            "produto_id",
            "produto_codigo_pai",
            "produto_nome",
            "produto_descricao",
            "produto_categorias",
            "produto_imagens",
            "produto_atributos",
            "produto_descontinuado",
            "produto_atualizado_em_fornecedor",
            "sku",
            "nome",
            "ncm",
            "preco",
            "estoque",
            "cor",
            "tamanho",
            "capacidade",
            "largura",
            "altura",
            "comprimento",
            "diametro",
            "peso_liquido",
            "peso_bruto",
            "imagens",
            "atributos",
            "status",
            "status_rotulo",
            "tiny_id",
            "ultimo_erro",
            "cadastrado_em",
            "criado_em",
            "atualizado_em",
            "estoque_tiny_sincronizado",
            "preco_custo_tiny_sincronizado",
            "dados_tiny_sincronizados_em",
            "imagens_tiny_sincronizadas",
            "hash_conteudo",
        ]
