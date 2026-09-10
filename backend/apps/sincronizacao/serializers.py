from rest_framework import serializers

from .models import EventoLog, Execucao, LogItem, RetentativaLote


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
    """Uma linha de log de UMA execução — leitura, para os logs técnicos."""

    variacao_sku = serializers.SerializerMethodField()

    class Meta:
        model = LogItem
        fields = ["id", "nivel", "evento", "mensagem", "detalhe", "criado_em", "variacao_sku", "variacao"]

    def get_variacao_sku(self, obj) -> str | None:
        # variacao é SET_NULL: pode ter sido apagada depois de o log ser gravado.
        return obj.variacao.sku if obj.variacao_id else None


class AuditoriaResumoSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    cadastrados = serializers.IntegerField()
    vinculados = serializers.IntegerField()
    cadastrados_e_vinculados = serializers.IntegerField()
    bloqueados = serializers.IntegerField()
    erros = serializers.IntegerField()


class ExecucaoDetalheSerializer(serializers.Serializer):
    """
    Resumo da execução no topo da tela de detalhe/auditoria. `progresso` e
    `estado` só fazem sentido pleno para `tipo=cadastro_tiny` (pause/resume);
    para importações de espelho vêm derivados do status.
    """

    id = serializers.IntegerField()
    fornecedor = serializers.CharField()
    tipo = serializers.CharField()
    status = serializers.CharField()
    estado = serializers.CharField()
    iniciada_em = serializers.DateTimeField()
    finalizada_em = serializers.DateTimeField(allow_null=True)
    duracao_segundos = serializers.FloatField(allow_null=True)
    total_lidos = serializers.IntegerField()
    total_cadastrados = serializers.IntegerField()
    total_erros = serializers.IntegerField()
    total_ignorados = serializers.IntegerField()
    progresso = serializers.FloatField()
    mensagem_erro = serializers.CharField(allow_blank=True)
    auditoria = AuditoriaResumoSerializer()
    logs_gerais_total = serializers.IntegerField()
    contadores_registrados = serializers.DictField(child=serializers.IntegerField())


class RetentativaLoteSerializer(serializers.ModelSerializer):
    """
    Estado de um job de retentativa em lote — usado pelo polling de progresso
    da UI. Só leitura; `variacao_ids` não é exposto (pode ter centenas de ids).
    """

    class Meta:
        model = RetentativaLote
        fields = [
            "id",
            "status",
            "selecao_todos",
            "total",
            "processados",
            "sucessos",
            "erros",
            "ignorados",
            "parada_solicitada",
            "criado_em",
            "finalizado_em",
        ]


class ExecucaoProdutoSerializer(serializers.Serializer):
    """Uma linha da tabela de auditoria — o desfecho de UM SKU nesta execução."""

    log_id = serializers.IntegerField()
    variacao_id = serializers.IntegerField(allow_null=True)
    sku = serializers.CharField()
    codigo_fornecedor = serializers.CharField()
    sku_tiny = serializers.CharField()
    produto_nome = serializers.CharField()
    resultado = serializers.ChoiceField(choices=EventoLog.choices)
    resultado_historico = serializers.ChoiceField(choices=EventoLog.choices)
    detalhe_historico = serializers.CharField(allow_blank=True)
    status_atual = serializers.CharField(allow_null=True)
    reconciliado = serializers.BooleanField()
    tiny_id = serializers.CharField(allow_blank=True)
    mensagem = serializers.CharField()
    detalhe_curto = serializers.CharField(allow_blank=True)
    imagens = serializers.ChoiceField(choices=["ok", "erro"], allow_null=True)
    criado_em = serializers.DateTimeField()
