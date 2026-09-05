import secrets
from datetime import timedelta

from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .listagem import (
    aplicar_busca,
    aplicar_filtro_status,
    aplicar_ordenacao_problema_primeiro,
    queryset_listagem,
)
from .models import Instancia
from .pagination import InstanciaPagination
from .serializers import InstanciaListagemSerializer, InstanciaSerializer
from .tiny_oauth import TinyOAuthError, montar_url_autorizacao, trocar_code_por_token

# Validade curta do state gerado a cada URL de autorização — o usuário
# normalmente autoriza em segundos/poucos minutos; 10 minutos dá folga sem
# deixar um state velho utilizável por muito tempo.
VALIDADE_OAUTH_STATE = timedelta(minutes=10)


@extend_schema_view(
    list=extend_schema(
        parameters=[
            OpenApiParameter("busca", str, required=False, description="Busca por nome ou CNPJ."),
            OpenApiParameter(
                "status", str, enum=list(Instancia.Status.values), required=False,
                description="Filtra por status exato.",
            ),
        ]
    )
)
class InstanciaViewSet(viewsets.ModelViewSet):
    """
    `list` (passo 8) aceita `?busca=` (nome ou cnpj), `?status=` e pagina com
    `InstanciaPagination`; instâncias com problema (erro, depois não
    conectado) vêm primeiro. Os demais actions usam o queryset simples.
    """

    queryset = Instancia.objects.all().order_by("nome")
    serializer_class = InstanciaSerializer
    pagination_class = InstanciaPagination
    lookup_field = "slug"
    lookup_value_regex = "[^/]+"
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def get_serializer_class(self):
        if self.action == "list":
            return InstanciaListagemSerializer
        return InstanciaSerializer

    def get_queryset(self):
        if self.action != "list":
            return Instancia.objects.all().order_by("nome")

        queryset = queryset_listagem()
        params = self.request.query_params
        queryset = aplicar_busca(queryset, params.get("busca"))
        queryset = aplicar_filtro_status(queryset, params.get("status"))
        return aplicar_ordenacao_problema_primeiro(queryset)

    @action(detail=True, methods=["get"])
    def autorizar(self, request, slug=None):
        """Gera um state novo e devolve a URL de autorização do Tiny para o usuário abrir."""
        instancia = self.get_object()

        if not instancia.client_id or not instancia.client_secret:
            return Response(
                {"detail": "Configure client_id e client_secret antes de autorizar."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        instancia.oauth_state = secrets.token_urlsafe(32)
        instancia.oauth_state_expira_em = timezone.now() + VALIDADE_OAUTH_STATE
        instancia.save(update_fields=["oauth_state", "oauth_state_expira_em", "atualizado_em"])

        redirect_uri = _url_callback(request, instancia.slug)
        url_autorizacao = montar_url_autorizacao(
            instancia.client_id, redirect_uri, instancia.oauth_state
        )
        return Response({"url_autorizacao": url_autorizacao, "redirect_uri": redirect_uri})

    @action(detail=True, methods=["post"])
    def desconectar(self, request, slug=None):
        """Limpa os tokens e volta para nao_conectado. Não libera o slug (ja_foi_autorizada fica True)."""
        instancia = self.get_object()
        instancia.access_token = ""
        instancia.refresh_token = ""
        instancia.token_emitido_em = None
        instancia.token_expira_em = None
        instancia.refresh_expira_em = None
        instancia.oauth_state = ""
        instancia.oauth_state_expira_em = None
        instancia.status = Instancia.Status.NAO_CONECTADO
        instancia.tentativas_falha = 0
        instancia.ultimo_erro = ""
        instancia.save()
        serializer = self.get_serializer(instancia)
        return Response(serializer.data)


class TinyOAuthCallbackView(APIView):
    """
    Recebe `code` e `state` de volta do Tiny. Sempre valida o state antes de
    qualquer outra coisa — ausente ou divergente é rejeitado mesmo com o
    slug correto — e o consome (limpa) na primeira validação, com sucesso
    ou não, para que não possa ser reaproveitado.

    Única rota pública da API (passo 5: todo o resto exige token) — quem
    chama aqui é o navegador redirecionado pelo Tiny, sem nenhum token
    nosso, então a proteção real já é o state.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, slug):
        instancia = get_object_or_404(Instancia, slug=slug)

        state_recebido = request.query_params.get("state", "")
        if not self._state_valido(instancia, state_recebido):
            return Response(
                {"detail": "state ausente, inválido ou expirado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        instancia.oauth_state = ""
        instancia.oauth_state_expira_em = None
        instancia.save(update_fields=["oauth_state", "oauth_state_expira_em", "atualizado_em"])

        code = request.query_params.get("code")
        if not code:
            return Response({"detail": "code ausente."}, status=status.HTTP_400_BAD_REQUEST)

        redirect_uri = _url_callback(request, slug)

        try:
            corpo = trocar_code_por_token(
                instancia.client_id, instancia.client_secret, code, redirect_uri
            )
        except TinyOAuthError as exc:
            instancia.status = Instancia.Status.ERRO
            instancia.ultimo_erro = str(exc)
            instancia.save(update_fields=["status", "ultimo_erro", "atualizado_em"])
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        instancia.aplicar_tokens(
            access_token=corpo["access_token"],
            refresh_token=corpo["refresh_token"],
            expires_in=int(corpo["expires_in"]),
            refresh_expires_in=int(corpo["refresh_expires_in"]),
        )

        serializer = InstanciaSerializer(instancia, context={"request": request})
        return Response(serializer.data)

    @staticmethod
    def _state_valido(instancia, state_recebido):
        if not state_recebido or not instancia.oauth_state:
            return False
        if not secrets.compare_digest(state_recebido, instancia.oauth_state):
            return False
        if instancia.oauth_state_expira_em and instancia.oauth_state_expira_em < timezone.now():
            return False
        return True


def _url_callback(request, slug):
    caminho = reverse("tiny-oauth-callback", kwargs={"slug": slug})
    return request.build_absolute_uri(caminho)
