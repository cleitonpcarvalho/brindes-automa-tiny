from rest_framework import serializers

from .models import AtualizacaoVariacaoFornecedor


class AtualizacaoVariacaoFornecedorSerializer(serializers.ModelSerializer):
    class Meta:
        model = AtualizacaoVariacaoFornecedor
        fields = [
            "id",
            "variacao",
            "fornecedor",
            "status",
            "erro",
            "criado_em",
            "iniciado_em",
            "finalizado_em",
        ]
        read_only_fields = fields
