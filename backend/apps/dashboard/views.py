from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework.response import Response
from rest_framework.views import APIView

from . import services
from .serializers import AlertaSerializer, ExecucaoAtividadeSerializer, ResumoSerializer


class ResumoView(APIView):
    """Os quatro números do topo do dashboard."""

    @extend_schema(
        parameters=[
            OpenApiParameter(
                "periodo",
                str,
                enum=list(services.PERIODOS_VALIDOS),
                required=False,
                description="Janela para 'produtos sincronizados'. Padrão: hoje.",
            )
        ],
        responses=ResumoSerializer,
    )
    def get(self, request):
        periodo = request.query_params.get("periodo", "hoje")
        return Response(services.calcular_resumo(periodo))


class AlertasView(APIView):
    """O que precisa de atenção agora — derivado do estado atual, nada persistido."""

    @extend_schema(responses=AlertaSerializer(many=True))
    def get(self, request):
        return Response(services.calcular_alertas())


class AtividadeView(APIView):
    """As últimas execuções de todas as instâncias."""

    @extend_schema(
        parameters=[OpenApiParameter("limit", int, required=False, description="Padrão 20, máx. 100.")],
        responses=ExecucaoAtividadeSerializer(many=True),
    )
    def get(self, request):
        try:
            limit = int(request.query_params.get("limit", 20))
        except ValueError:
            limit = 20
        limit = max(1, min(limit, 100))
        return Response(services.calcular_atividade(limit))
