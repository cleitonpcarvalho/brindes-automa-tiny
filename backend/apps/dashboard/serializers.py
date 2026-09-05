"""
Serializers só para forma/documentação (drf-spectacular) — os dados vêm
prontos de apps.dashboard.services como dicts, nunca de um ModelSerializer.
"""

from rest_framework import serializers

from apps.instancias.constants import Fornecedor


class InstanciaResumidaSerializer(serializers.Serializer):
    slug = serializers.CharField()
    nome = serializers.CharField()


class InstanciasContagemSerializer(serializers.Serializer):
    ativas = serializers.IntegerField()
    total = serializers.IntegerField()


class ProdutosSincronizadosSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    periodo_anterior = serializers.IntegerField()
    diferenca = serializers.IntegerField()


class ExecucoesContagemSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    sucesso = serializers.IntegerField()


class AlertasContagemSerializer(serializers.Serializer):
    abertos = serializers.IntegerField()
    requerem_acao = serializers.IntegerField()


class ResumoSerializer(serializers.Serializer):
    periodo = serializers.ChoiceField(choices=["hoje", "7d", "30d"])
    instancias = InstanciasContagemSerializer()
    produtos_sincronizados = ProdutosSincronizadosSerializer()
    execucoes_24h = ExecucoesContagemSerializer()
    alertas = AlertasContagemSerializer()


class AcaoSugeridaSerializer(serializers.Serializer):
    tipo = serializers.CharField()
    rotulo = serializers.CharField()


class AlertaSerializer(serializers.Serializer):
    id = serializers.CharField()
    severidade = serializers.ChoiceField(choices=["critica", "atencao"])
    tipo = serializers.CharField()
    instancia = InstanciaResumidaSerializer()
    fornecedor = serializers.ChoiceField(choices=Fornecedor.choices, allow_null=True)
    mensagem = serializers.CharField()
    momento = serializers.DateTimeField()
    acao_sugerida = AcaoSugeridaSerializer()


class ExecucaoAtividadeSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    instancia = InstanciaResumidaSerializer()
    fornecedor = serializers.ChoiceField(choices=Fornecedor.choices)
    tipo = serializers.CharField()
    status = serializers.CharField()
    iniciada_em = serializers.DateTimeField()
    finalizada_em = serializers.DateTimeField(allow_null=True)
    duracao_segundos = serializers.FloatField(allow_null=True)
    total_lidos = serializers.IntegerField()
    total_novos = serializers.IntegerField()
    total_atualizados = serializers.IntegerField()
    total_cadastrados = serializers.IntegerField()
    total_ignorados = serializers.IntegerField()
    total_erros = serializers.IntegerField()
