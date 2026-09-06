from rest_framework import serializers

from .models import Execucao, LogItem


class ExecucaoSerializer(serializers.ModelSerializer):
    """
    Uma linha do histórico da aba "Execuções" do detalhe da instância.

    Só leitura. `fornecedor`, `tipo` e `status` são CharField com choices no
    model, então o ModelSerializer já os expõe como enums. `duracao_segundos`
    vem da property do model (derivada de finalizada_em - iniciada_em; nula
    enquanto a execução não terminou). `total_logs` é anotado no queryset da
    view para não gerar N+1.
    """

    duracao_segundos = serializers.FloatField(read_only=True, allow_null=True)
    total_logs = serializers.IntegerField(read_only=True)

    class Meta:
        model = Execucao
        fields = [
            "id",
            "fornecedor",
            "tipo",
            "status",
            "iniciada_em",
            "finalizada_em",
            "duracao_segundos",
            "total_lidos",
            "total_novos",
            "total_atualizados",
            "total_cadastrados",
            "total_ignorados",
            "total_erros",
            "mensagem_erro",
            "total_logs",
        ]


class LogItemSerializer(serializers.ModelSerializer):
    """Uma linha de log de UMA execução — leitura, para o modal de detalhes."""

    variacao_sku = serializers.SerializerMethodField()

    class Meta:
        model = LogItem
        fields = ["id", "nivel", "mensagem", "detalhe", "criado_em", "variacao_sku"]

    def get_variacao_sku(self, obj) -> str | None:
        # variacao é SET_NULL: pode ter sido apagada depois de o log ser gravado.
        return obj.variacao.sku if obj.variacao_id else None
