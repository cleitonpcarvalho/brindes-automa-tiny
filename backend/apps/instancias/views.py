import secrets
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Q
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.utils import timezone
from drf_spectacular.utils import OpenApiParameter, extend_schema, extend_schema_view
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.catalogo.models import StatusVariacao, Variacao
from apps.catalogo.serializers import VariacaoEspelhoSerializer
from apps.fornecedores.models import CadenciaFornecedor
from apps.fornecedores.services import (
    checar_limite_diario_xbz,
    listar_cadencias_com_defaults,
    obter_credencial_ativa,
)
from apps.fornecedores.tasks import executar_sincronizacao_manual_task
from apps.sincronizacao.models import Execucao, NivelLog, StatusExecucao, TipoExecucao
from apps.sincronizacao.serializers import ExecucaoSerializer, LogItemSerializer

from .constants import CAMPOS_POR_FORNECEDOR, Fornecedor
from .listagem import (
    aplicar_busca,
    aplicar_filtro_status,
    aplicar_ordenacao_problema_primeiro,
    queryset_listagem,
)
from .models import CredencialFornecedor, Instancia
from .pagination import (
    ExecucaoPagination,
    InstanciaPagination,
    LogItemPagination,
    ProdutoEspelhoPagination,
)
from .serializers import (
    AutorizarRespostaSerializer,
    CadenciaFornecedorSerializer,
    ConfiguracoesInstanciaSerializer,
    CredencialFornecedorEntradaSerializer,
    CredencialFornecedorRespostaSerializer,
    InstanciaDetalheSerializer,
    InstanciaListagemSerializer,
    InstanciaSerializer,
    SincronizarRespostaSerializer,
)
from .tiny_oauth import TinyOAuthError, montar_url_autorizacao, montar_url_callback, trocar_code_por_token

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
        if self.action == "retrieve":
            return InstanciaDetalheSerializer
        return InstanciaSerializer

    def get_queryset(self):
        if self.action != "list":
            return Instancia.objects.all().order_by("nome")

        queryset = queryset_listagem()
        params = self.request.query_params
        queryset = aplicar_busca(queryset, params.get("busca"))
        queryset = aplicar_filtro_status(queryset, params.get("status"))
        return aplicar_ordenacao_problema_primeiro(queryset)

    @extend_schema(responses=AutorizarRespostaSerializer)
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

        redirect_uri = montar_url_callback(instancia.slug)
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

    Passo 10: como quem chega aqui é o navegador (não a SPA via AJAX — o
    clique em "Autorizar no ERP" é uma navegação de página inteira para o
    Tiny), a resposta é sempre um redirect (302) de volta para o frontend,
    nunca JSON — não existe "retomar o wizard client-side" depois dessa
    navegação. Sucesso volta para a aba Fornecedores do detalhe da
    instância (que cumpre o papel do "passo 4" do wizard); qualquer falha
    (state inválido/expirado, code ausente, erro do Tiny) volta para o
    wizard no passo de autorização, para o usuário tentar de novo. O único
    caso que continua sendo JSON é o slug inexistente (404) — não é parte
    do fluxo normal do wizard, é uma URL malformada.
    """

    authentication_classes = []
    permission_classes = [AllowAny]

    def get(self, request, slug):
        instancia = get_object_or_404(Instancia, slug=slug)

        state_recebido = request.query_params.get("state", "")
        if not self._state_valido(instancia, state_recebido):
            return self._redirecionar_erro(slug)

        instancia.oauth_state = ""
        instancia.oauth_state_expira_em = None
        instancia.save(update_fields=["oauth_state", "oauth_state_expira_em", "atualizado_em"])

        code = request.query_params.get("code")
        if not code:
            return self._redirecionar_erro(slug)

        redirect_uri = montar_url_callback(slug)

        try:
            corpo = trocar_code_por_token(
                instancia.client_id, instancia.client_secret, code, redirect_uri
            )
        except TinyOAuthError as exc:
            instancia.status = Instancia.Status.ERRO
            instancia.ultimo_erro = str(exc)
            instancia.save(update_fields=["status", "ultimo_erro", "atualizado_em"])
            return self._redirecionar_erro(slug)

        instancia.aplicar_tokens(
            access_token=corpo["access_token"],
            refresh_token=corpo["refresh_token"],
            expires_in=int(corpo["expires_in"]),
            refresh_expires_in=int(corpo["refresh_expires_in"]),
        )

        base = settings.FRONTEND_BASE_URL.rstrip("/")
        return HttpResponseRedirect(f"{base}/instancias/{slug}?autorizado=1")

    @staticmethod
    def _redirecionar_erro(slug):
        base = settings.FRONTEND_BASE_URL.rstrip("/")
        return HttpResponseRedirect(f"{base}/instancias/novo?slug={slug}&erro=1")

    @staticmethod
    def _state_valido(instancia, state_recebido):
        if not state_recebido or not instancia.oauth_state:
            return False
        if not secrets.compare_digest(state_recebido, instancia.oauth_state):
            return False
        if instancia.oauth_state_expira_em and instancia.oauth_state_expira_em < timezone.now():
            return False
        return True


def _obter_instancia_ou_404(slug):
    return get_object_or_404(Instancia, slug=slug)


class CredenciaisFornecedorView(APIView):
    """GET .../credenciais/ — lista os 4 fornecedores, sempre, mesmo sem credencial configurada."""

    @extend_schema(responses=CredencialFornecedorRespostaSerializer(many=True))
    def get(self, request, slug):
        instancia = _obter_instancia_ou_404(slug)
        credenciais = {c.fornecedor: c for c in instancia.credenciais_fornecedor.all()}
        dados = [
            CredencialFornecedorRespostaSerializer.montar(valor, credenciais.get(valor))
            for valor, _rotulo in Fornecedor.choices
        ]
        return Response(CredencialFornecedorRespostaSerializer(dados, many=True).data)


class CredencialFornecedorDetailView(APIView):
    """PUT .../credenciais/<fornecedor>/ — upsert; nunca ecoa a credencial recebida."""

    @extend_schema(
        request=CredencialFornecedorEntradaSerializer, responses=CredencialFornecedorRespostaSerializer
    )
    def put(self, request, slug, fornecedor):
        instancia = _obter_instancia_ou_404(slug)
        if fornecedor not in CAMPOS_POR_FORNECEDOR:
            return Response({"detail": f"Fornecedor '{fornecedor}' desconhecido."}, status=status.HTTP_404_NOT_FOUND)

        entrada = CredencialFornecedorEntradaSerializer(data=request.data, fornecedor=fornecedor)
        entrada.is_valid(raise_exception=True)

        credencial, _criada = CredencialFornecedor.objects.update_or_create(
            instancia=instancia,
            fornecedor=fornecedor,
            defaults={
                "credenciais": entrada.validated_data["credenciais"],
                "ativo": entrada.validated_data.get("ativo", True),
            },
        )

        dados = CredencialFornecedorRespostaSerializer.montar(fornecedor, credencial)
        return Response(CredencialFornecedorRespostaSerializer(dados).data)


class CadenciasFornecedorView(APIView):
    """GET .../cadencias/ — lista as 4, com defaults quando ainda não configurada."""

    @extend_schema(responses=CadenciaFornecedorSerializer(many=True))
    def get(self, request, slug):
        instancia = _obter_instancia_ou_404(slug)
        dados = listar_cadencias_com_defaults(instancia)
        return Response(CadenciaFornecedorSerializer(dados, many=True).data)


class CadenciaFornecedorDetailView(APIView):
    """PATCH .../cadencias/<fornecedor>/ — upsert de intervalo/ativo, com a regra de mínimo da xbz."""

    @extend_schema(request=CadenciaFornecedorSerializer, responses=CadenciaFornecedorSerializer)
    def patch(self, request, slug, fornecedor):
        instancia = _obter_instancia_ou_404(slug)
        if fornecedor not in CAMPOS_POR_FORNECEDOR:
            return Response({"detail": f"Fornecedor '{fornecedor}' desconhecido."}, status=status.HTTP_404_NOT_FOUND)

        entrada = CadenciaFornecedorSerializer(data=request.data, partial=True)
        entrada.is_valid(raise_exception=True)

        # Busca sem criar: só grava depois de validar (full_clean, abaixo) —
        # um PATCH inválido (ex.: xbz < 60min) não pode deixar pra trás uma
        # CadenciaFornecedor "default" que não existia antes da tentativa.
        cadencia = CadenciaFornecedor.objects.filter(instancia=instancia, fornecedor=fornecedor).first()
        if cadencia is None:
            cadencia = CadenciaFornecedor(instancia=instancia, fornecedor=fornecedor)

        if "intervalo_minutos" in entrada.validated_data:
            cadencia.intervalo_minutos = entrada.validated_data["intervalo_minutos"]
        if "ativo" in entrada.validated_data:
            cadencia.ativo = entrada.validated_data["ativo"]

        try:
            cadencia.full_clean()
        except DjangoValidationError as exc:  # ex.: xbz com intervalo_minutos < 60
            mensagens = getattr(exc, "messages", [str(exc)])
            return Response({"detail": " ".join(mensagens)}, status=status.HTTP_400_BAD_REQUEST)

        cadencia.save()
        return Response(
            CadenciaFornecedorSerializer(
                {
                    "fornecedor": fornecedor,
                    "intervalo_minutos": cadencia.intervalo_minutos,
                    "ativo": cadencia.ativo,
                    "proxima_execucao_em": cadencia.proxima_execucao_em,
                }
            ).data
        )


class SincronizarFornecedorView(APIView):
    """
    POST .../fornecedores/<fornecedor>/sincronizar/ — dispara a sincronização
    manual (passo 10). As mesmas checagens de negócio do comando CLI
    (credencial ativa, limite diário da xbz) rodam aqui de forma síncrona,
    ANTES de criar a Execucao e enfileirar, para poder devolver um erro
    imediato em vez de um execucao_id que nunca vai sair de "rodando".
    """

    @extend_schema(request=None, responses=SincronizarRespostaSerializer)
    def post(self, request, slug, fornecedor):
        instancia = _obter_instancia_ou_404(slug)
        if fornecedor not in CAMPOS_POR_FORNECEDOR:
            return Response({"detail": f"Fornecedor '{fornecedor}' desconhecido."}, status=status.HTTP_404_NOT_FOUND)

        try:
            obter_credencial_ativa(instancia, fornecedor)
            checar_limite_diario_xbz(instancia, fornecedor)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        ja_rodando = Execucao.objects.filter(
            instancia=instancia, fornecedor=fornecedor, status=StatusExecucao.RODANDO
        ).exists()
        if ja_rodando:
            return Response(
                {"detail": "Já existe uma sincronização em andamento para este fornecedor."},
                status=status.HTTP_409_CONFLICT,
            )

        execucao = Execucao.objects.create(
            instancia=instancia, fornecedor=fornecedor, tipo=TipoExecucao.INCREMENTAL
        )
        executar_sincronizacao_manual_task.delay(execucao.id)
        return Response(
            {"execucao_id": execucao.id, "status": execucao.status}, status=status.HTTP_202_ACCEPTED
        )


@extend_schema_view(
    get=extend_schema(
        parameters=[
            OpenApiParameter(
                "busca",
                str,
                required=False,
                description="Busca textual em SKU, código-pai, nome da variação e nome do produto.",
            ),
            OpenApiParameter(
                "fornecedor",
                str,
                enum=list(Fornecedor.values),
                required=False,
                description="Filtra por fornecedor do produto-pai.",
            ),
            OpenApiParameter(
                "status",
                str,
                enum=list(StatusVariacao.values),
                required=False,
                description="Filtra pela situação da variação em relação ao Tiny.",
            ),
        ]
    )
)
class ProdutosEspelhoView(generics.ListAPIView):
    """
    GET /api/instancias/<slug>/produtos/ — listagem paginada das variações
    (SKUs) do espelho local PostgreSQL desta instância.

    Somente consulta: não dispara sincronização, não fala com fornecedor
    nem com o Tiny. Cada linha é uma Variacao (a unidade cadastrável no
    Tiny — regra nº 1), com os campos do Produto-pai anexados via
    `select_related` para não gerar N+1.

    O queryset é sempre `produto__instancia == <slug>` — não existe forma de
    pedir/filtrar variações de outra instância por esta rota.
    """

    serializer_class = VariacaoEspelhoSerializer
    pagination_class = ProdutoEspelhoPagination

    def get_queryset(self):
        instancia = get_object_or_404(Instancia, slug=self.kwargs["slug"])
        queryset = (
            Variacao.objects.filter(produto__instancia=instancia)
            .select_related("produto")
            .order_by("produto__codigo_pai", "sku")
        )

        params = self.request.query_params

        busca = (params.get("busca") or "").strip()
        if busca:
            queryset = queryset.filter(
                Q(sku__icontains=busca)
                | Q(produto__codigo_pai__icontains=busca)
                | Q(nome__icontains=busca)
                | Q(produto__nome__icontains=busca)
            )

        # Filtros silenciosamente ignorados quando o valor não é uma choice
        # válida — mesma política da listagem de instâncias (listagem.py).
        fornecedor = params.get("fornecedor")
        if fornecedor in Fornecedor.values:
            queryset = queryset.filter(produto__fornecedor=fornecedor)

        status_variacao = params.get("status")
        if status_variacao in StatusVariacao.values:
            queryset = queryset.filter(status=status_variacao)

        return queryset


@extend_schema_view(
    get=extend_schema(
        parameters=[
            OpenApiParameter(
                "fornecedor",
                str,
                enum=list(Fornecedor.values),
                required=False,
                description="Filtra por fornecedor da execução.",
            ),
            OpenApiParameter(
                "status",
                str,
                enum=list(StatusExecucao.values),
                required=False,
                description="Filtra pelo status da execução.",
            ),
        ]
    )
)
class ExecucoesInstanciaView(generics.ListAPIView):
    """
    GET /api/instancias/<slug>/execucoes/ — histórico paginado das execuções
    (rodadas de sincronização) desta instância, da mais recente para a mais
    antiga.

    Somente leitura/observabilidade: não inicia, cancela nem reprocessa nada.
    O queryset é sempre `instancia == <slug>`; `total_logs` é anotado para
    não gerar N+1 ao contar os logs de cada linha.
    """

    serializer_class = ExecucaoSerializer
    pagination_class = ExecucaoPagination

    def get_queryset(self):
        instancia = get_object_or_404(Instancia, slug=self.kwargs["slug"])
        queryset = (
            Execucao.objects.filter(instancia=instancia)
            .annotate(total_logs=Count("logs"))
            .order_by("-iniciada_em", "-id")
        )

        params = self.request.query_params

        # Filtros silenciosamente ignorados quando o valor não é choice válida
        # — mesma política dos outros endpoints da instância.
        fornecedor = params.get("fornecedor")
        if fornecedor in Fornecedor.values:
            queryset = queryset.filter(fornecedor=fornecedor)

        status_execucao = params.get("status")
        if status_execucao in StatusExecucao.values:
            queryset = queryset.filter(status=status_execucao)

        return queryset


@extend_schema_view(
    get=extend_schema(
        parameters=[
            OpenApiParameter(
                "nivel",
                str,
                enum=list(NivelLog.values),
                required=False,
                description="Filtra as linhas de log por nível.",
            ),
        ]
    )
)
class ExecucaoLogsView(generics.ListAPIView):
    """
    GET /api/instancias/<slug>/execucoes/<execucao_id>/logs/ — linhas de log
    de UMA execução, em ordem cronológica. Leitura apenas.

    Isolamento: a execução é resolvida por (id E instancia__slug) — pedir o
    id de uma execução de outra instância devolve 404, não os logs dela.
    """

    serializer_class = LogItemSerializer
    pagination_class = LogItemPagination

    def get_queryset(self):
        execucao = get_object_or_404(
            Execucao,
            id=self.kwargs["execucao_id"],
            instancia__slug=self.kwargs["slug"],
        )
        queryset = execucao.logs.select_related("variacao").order_by("criado_em", "id")

        nivel = self.request.query_params.get("nivel")
        if nivel in NivelLog.values:
            queryset = queryset.filter(nivel=nivel)

        return queryset


class ConfiguracoesInstanciaView(generics.RetrieveUpdateAPIView):
    """
    GET / PATCH / PUT /api/instancias/<slug>/configuracoes/

    Lê e grava só as configurações operacionais do Tiny da instância
    (`tiny_origem_padrao`, `tiny_unidade_medida_padrao`) — os campos que
    antes só o Django Admin editava. A superfície é o
    `ConfiguracoesInstanciaSerializer`, que só conhece esses dois campos;
    qualquer outra chave enviada é ignorada. Nenhuma ação de
    sincronização/Tiny: só persiste.

    Isolamento: resolve exatamente uma instância pelo slug da URL; não há
    parâmetro que alcance outra.
    """

    serializer_class = ConfiguracoesInstanciaSerializer
    queryset = Instancia.objects.all()
    lookup_field = "slug"
    http_method_names = ["get", "patch", "put", "head", "options"]
