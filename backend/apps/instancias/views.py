import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
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
from apps.catalogo.serializers import VariacaoDetalheSerializer, VariacaoEspelhoSerializer
from apps.fornecedores.models import (
    AtualizacaoVariacaoFornecedor,
    CadenciaFornecedor,
    StatusAtualizacaoVariacao,
)
from apps.fornecedores.serializers import AtualizacaoVariacaoFornecedorSerializer
from apps.fornecedores.tasks import (
    ATUALIZACAO_FORNECEDOR_STALE_SEGUNDOS,
    atualizar_variacao_fornecedor_task,
)
from apps.fornecedores.services import (
    checar_limite_diario_xbz,
    listar_cadencias_com_defaults,
    obter_credencial_ativa,
)
from apps.catalogo.tasks import (
    EventosRetentativa,
    _reconciliar_retentativa_lote_stale,
    cadastrar_produtos_tiny_task,
    recomputar_contadores_execucao,
    retentar_lote_task,
)
from apps.catalogo.tiny_sync import (
    EventosSincronizacao,
    cadastrar_variacao_individual,
    atualizar_variacao_individual,
    cadastro_tiny_bloqueia_espelho,
    estado_cadastro_tiny,
    estimar_cadastro,
    execucao_cadastro_tiny_aberta,
    heartbeat_expirado,
)
from apps.fornecedores.tasks import executar_sincronizacao_manual_task
from apps.sincronizacao import auditoria
from apps.sincronizacao.models import (
    EVENTOS_DESFECHO,
    STATUS_EXECUCAO_ABERTOS,
    EventoLog,
    Execucao,
    LogItem,
    NivelLog,
    RetentativaLote,
    StatusExecucao,
    StatusRetentativaLote,
    TipoExecucao,
)
from apps.sincronizacao.serializers import (
    ExecucaoDetalheSerializer,
    ExecucaoProdutoSerializer,
    ExecucaoSerializer,
    LogItemSerializer,
    RetentativaLoteSerializer,
)

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
    ExecucaoProdutoPagination,
    InstanciaPagination,
    LogItemPagination,
    ProdutoEspelhoPagination,
)
from .serializers import (
    AutorizarRespostaSerializer,
    CadastroTinyPreviewSerializer,
    CadenciaFornecedorSerializer,
    ConfiguracoesInstanciaSerializer,
    CredencialFornecedorEntradaSerializer,
    CredencialFornecedorRespostaSerializer,
    InstanciaDetalheSerializer,
    InstanciaListagemSerializer,
    InstanciaSerializer,
    SincronizarRespostaSerializer,
    TinyFornecedorIdEntradaSerializer,
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


class TinyFornecedorIdView(APIView):
    """
    PUT .../fornecedores/<fornecedor>/tiny-fornecedor-id/ — define ou limpa
    (`null`) o id do contato-fornecedor correspondente no Tiny desta
    instância. Separado do endpoint de credenciais de propósito: não é
    segredo e um PUT de credenciais nunca deve tocá-lo (e vice-versa).
    """

    @extend_schema(
        request=TinyFornecedorIdEntradaSerializer, responses=CredencialFornecedorRespostaSerializer
    )
    def put(self, request, slug, fornecedor):
        instancia = _obter_instancia_ou_404(slug)
        if fornecedor not in CAMPOS_POR_FORNECEDOR:
            return Response(
                {"detail": f"Fornecedor '{fornecedor}' desconhecido."}, status=status.HTTP_404_NOT_FOUND
            )

        entrada = TinyFornecedorIdEntradaSerializer(data=request.data)
        entrada.is_valid(raise_exception=True)

        # `defaults` só toca `tiny_fornecedor_id` — `credenciais`/`ativo` de uma
        # linha já existente ficam intactos.
        credencial, _criada = CredencialFornecedor.objects.update_or_create(
            instancia=instancia,
            fornecedor=fornecedor,
            defaults={"tiny_fornecedor_id": entrada.validated_data["tiny_fornecedor_id"]},
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
        if "propagar_tiny" in entrada.validated_data:
            cadencia.propagar_tiny = entrada.validated_data["propagar_tiny"]

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
                    "propagar_tiny": cadencia.propagar_tiny,
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

        execucoes_do_fornecedor = Execucao.objects.filter(
            instancia=instancia, fornecedor=fornecedor
        )
        if execucoes_do_fornecedor.filter(status=StatusExecucao.RODANDO).exists():
            return Response(
                {"detail": "Já existe uma sincronização em andamento para este fornecedor."},
                status=status.HTTP_409_CONFLICT,
            )
        # A importação/atualização do espelho não pode rodar enquanto o
        # cadastro Tiny do MESMO fornecedor está ativo (mudaria a
        # elegibilidade no meio do lote). Pausado NÃO bloqueia.
        if cadastro_tiny_bloqueia_espelho(instancia, fornecedor):
            return Response(
                {"detail": "Sincronização de produtos com o Tiny em andamento para este fornecedor — "
                 "pause-a antes de reimportar o espelho."},
                status=status.HTTP_409_CONFLICT,
            )

        # A 1ª rodada de um fornecedor nesta instância é a carga inicial; as
        # seguintes são incrementais. Só rótulo — o pipeline de importação
        # (mirror-only) é o mesmo nos dois casos (a API do fornecedor sempre
        # devolve o catálogo inteiro e o upsert por hash pula o que não mudou).
        tipo = (
            TipoExecucao.CARGA_INICIAL
            if not execucoes_do_fornecedor.exists()
            else TipoExecucao.INCREMENTAL
        )
        execucao = Execucao.objects.create(
            instancia=instancia, fornecedor=fornecedor, tipo=tipo
        )
        executar_sincronizacao_manual_task.delay(execucao.id)
        return Response(
            {"execucao_id": execucao.id, "status": execucao.status}, status=status.HTTP_202_ACCEPTED
        )


def _pronta_para_cadastro_tiny(instancia, fornecedor):
    """(pronta, motivo) — mesmas checagens do management command, sem tocar no Tiny."""
    if not instancia.access_token:
        return False, "A instância não está conectada ao Tiny."
    faltando = []
    if instancia.tiny_origem_padrao is None:
        faltando.append("origem padrão")
    if not instancia.tiny_unidade_medida_padrao:
        faltando.append("unidade de medida padrão")
    if faltando:
        return False, f"Configure a {' e a '.join(faltando)} do Tiny antes de cadastrar."
    tem_id = (
        CredencialFornecedor.objects.filter(instancia=instancia, fornecedor=fornecedor)
        .exclude(tiny_fornecedor_id__isnull=True)
        .exists()
    )
    if not tem_id:
        return False, (
            f"Configure o \"ID do fornecedor no Tiny\" de {dict(Fornecedor.choices).get(fornecedor, fornecedor)} "
            "em Instância › Fornecedores antes de cadastrar."
        )
    return True, ""


class CadastroTinyPreviewView(APIView):
    """
    GET .../fornecedores/<fornecedor>/cadastro-tiny/preview/ — estimativa
    para a tela de confirmação do "Sincronizar com Tiny". SÓ consulta o
    espelho local; NENHUMA chamada ao Tiny.
    """

    @extend_schema(responses=CadastroTinyPreviewSerializer)
    def get(self, request, slug, fornecedor):
        instancia = _obter_instancia_ou_404(slug)
        if fornecedor not in CAMPOS_POR_FORNECEDOR:
            return Response(
                {"detail": f"Fornecedor '{fornecedor}' desconhecido."}, status=status.HTTP_404_NOT_FOUND
            )

        estimativa = estimar_cadastro(instancia, fornecedor)
        pronta, motivo = _pronta_para_cadastro_tiny(instancia, fornecedor)
        aberta = execucao_cadastro_tiny_aberta(instancia, fornecedor)
        return Response(
            CadastroTinyPreviewSerializer(
                {
                    **estimativa,
                    "pronta_para_cadastro": pronta,
                    "motivo_nao_pronta": motivo,
                    "sincronizacao_em_andamento": aberta is not None,
                }
            ).data
        )


def _iniciar_execucao_cadastro_tiny(instancia, fornecedor):
    """
    Cria uma Execucao de cadastro Tiny e enfileira a task. Retorna
    (execucao, token). Chamado dentro de uma transação com o par travado.
    """
    token = uuid.uuid4().hex
    execucao = Execucao.objects.create(
        instancia=instancia,
        fornecedor=fornecedor,
        tipo=TipoExecucao.CADASTRO_TINY,
        lease_token=token,
        heartbeat_em=timezone.now(),
    )
    return execucao, token


class CadastrarProdutosTinyView(APIView):
    """
    POST .../fornecedores/<fornecedor>/cadastro-tiny/ — agenda a
    sincronização em massa de produtos deste fornecedor com o Tiny.

    Cria a `Execucao` (tipo `cadastro_tiny`, status `rodando`) com um
    `lease_token` novo, enfileira a task e devolve o `execucao_id` na hora.
    O processamento roda em background com pause/resume e heartbeat.

    Concorrência: sob `select_for_update` do par (instância, fornecedor).
    Se JÁ existe uma Execucao de cadastro Tiny "aberta" (rodando, pausando,
    pausado ou interrompido) para o par, devolve 409 — a interface deve
    oferecer Pausar/Retomar, não iniciar outra. Também 409 se há uma
    importação de espelho do fornecedor rodando.
    """

    @extend_schema(request=None, responses=SincronizarRespostaSerializer)
    def post(self, request, slug, fornecedor):
        instancia = _obter_instancia_ou_404(slug)
        if fornecedor not in CAMPOS_POR_FORNECEDOR:
            return Response(
                {"detail": f"Fornecedor '{fornecedor}' desconhecido."}, status=status.HTTP_404_NOT_FOUND
            )

        pronta, motivo = _pronta_para_cadastro_tiny(instancia, fornecedor)
        if not pronta:
            return Response({"detail": motivo}, status=status.HTTP_400_BAD_REQUEST)

        conflito = None
        execucao = None
        with transaction.atomic():
            _travar_instancia(instancia)
            if execucao_cadastro_tiny_aberta(instancia, fornecedor) is not None:
                conflito = (
                    "Já existe uma sincronização com o Tiny aberta para este fornecedor "
                    "(em andamento, pausada ou interrompida). Use Pausar/Retomar."
                )
            elif Execucao.objects.filter(
                instancia=instancia, fornecedor=fornecedor, status=StatusExecucao.RODANDO
            ).exists():
                conflito = "Já existe uma importação de espelho em andamento para este fornecedor."
            else:
                execucao, _token = _iniciar_execucao_cadastro_tiny(instancia, fornecedor)

        if conflito:
            return Response({"detail": conflito}, status=status.HTTP_409_CONFLICT)

        cadastrar_produtos_tiny_task.delay(execucao.id, execucao.lease_token)
        return Response(
            {"execucao_id": execucao.id, "status": execucao.status},
            status=status.HTTP_202_ACCEPTED,
        )


def _travar_instancia(instancia):
    """
    `SELECT ... FOR UPDATE` na linha da Instancia — serializa TODAS as
    operações de start/pausar/retomar de cadastro Tiny dessa instância
    (são todas rápidas, só DB). Garante que "iniciar XBZ" e um segundo
    "iniciar XBZ" concorrentes não criem duas Execucao, e que dois
    "retomar" concorrentes só resultem em uma task.
    """
    Instancia.objects.select_for_update().get(pk=instancia.pk)


class PausarCadastroTinyView(APIView):
    """
    POST .../fornecedores/<fornecedor>/cadastro-tiny/pausar/ — pede a pausa
    COOPERATIVA da execução em andamento. Não mata a task: marca
    `pausa_solicitada` e status `pausando`; a task detecta antes do próximo
    produto, termina a unidade atual e encerra em `pausado`.
    """

    @extend_schema(request=None, responses=SincronizarRespostaSerializer)
    def post(self, request, slug, fornecedor):
        instancia = _obter_instancia_ou_404(slug)
        if fornecedor not in CAMPOS_POR_FORNECEDOR:
            return Response(
                {"detail": f"Fornecedor '{fornecedor}' desconhecido."}, status=status.HTTP_404_NOT_FOUND
            )
        with transaction.atomic():
            _travar_instancia(instancia)
            execucao = (
                Execucao.objects.filter(
                    instancia=instancia,
                    fornecedor=fornecedor,
                    tipo=TipoExecucao.CADASTRO_TINY,
                    status=StatusExecucao.RODANDO,
                )
                .order_by("-iniciada_em")
                .first()
            )
            if execucao is None:
                return Response(
                    {"detail": "Não há sincronização em andamento para pausar."},
                    status=status.HTTP_409_CONFLICT,
                )
            execucao.status = StatusExecucao.PAUSANDO
            execucao.pausa_solicitada = True
            execucao.save(update_fields=["status", "pausa_solicitada"])
        return Response(
            {"execucao_id": execucao.id, "status": execucao.status}, status=status.HTTP_202_ACCEPTED
        )


class RetomarCadastroTinyView(APIView):
    """
    POST .../fornecedores/<fornecedor>/cadastro-tiny/retomar/ — retoma a
    MESMA Execucao pausada/interrompida (ou uma `rodando` com heartbeat
    expirado). Gera um `lease_token` novo (um eventual zumbi da rodada
    anterior perde o lease e para), volta a `rodando` e enfileira a task.
    A fila é reconstruída do banco (idempotência): produtos já cadastrados
    não voltam, imagens já sincronizadas não são reenviadas.

    Corrida de dois "retomar" simultâneos: sob `select_for_update`, só o
    primeiro encontra a Execucao num estado retomável; o segundo a vê já
    `rodando` (heartbeat fresco) e devolve 409.
    """

    @extend_schema(request=None, responses=SincronizarRespostaSerializer)
    def post(self, request, slug, fornecedor):
        instancia = _obter_instancia_ou_404(slug)
        if fornecedor not in CAMPOS_POR_FORNECEDOR:
            return Response(
                {"detail": f"Fornecedor '{fornecedor}' desconhecido."}, status=status.HTTP_404_NOT_FOUND
            )
        agora = timezone.now()
        conflito = None
        execucao = None
        token = None
        with transaction.atomic():
            _travar_instancia(instancia)
            execucao = (
                Execucao.objects.filter(
                    instancia=instancia,
                    fornecedor=fornecedor,
                    tipo=TipoExecucao.CADASTRO_TINY,
                    status__in=STATUS_EXECUCAO_ABERTOS,
                )
                .order_by("-iniciada_em")
                .first()
            )
            retomavel = execucao is not None and (
                execucao.status in (StatusExecucao.PAUSADO, StatusExecucao.INTERROMPIDO)
                or (
                    execucao.status in (StatusExecucao.RODANDO, StatusExecucao.PAUSANDO)
                    and heartbeat_expirado(execucao.heartbeat_em, agora)
                )
            )
            if not retomavel:
                if execucao is not None and execucao.status in (
                    StatusExecucao.RODANDO,
                    StatusExecucao.PAUSANDO,
                ):
                    conflito = "A sincronização já está em andamento."
                else:
                    conflito = "Não há sincronização pausada ou interrompida para retomar."
                execucao = None
            else:
                token = uuid.uuid4().hex
                execucao.status = StatusExecucao.RODANDO
                execucao.pausa_solicitada = False
                execucao.lease_token = token
                execucao.heartbeat_em = agora
                execucao.finalizada_em = None
                execucao.mensagem_erro = ""
                execucao.save(
                    update_fields=[
                        "status",
                        "pausa_solicitada",
                        "lease_token",
                        "heartbeat_em",
                        "finalizada_em",
                        "mensagem_erro",
                    ]
                )

        if conflito:
            return Response({"detail": conflito}, status=status.HTTP_409_CONFLICT)

        cadastrar_produtos_tiny_task.delay(execucao.id, token)
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


class VariacaoDetalheView(generics.RetrieveAPIView):
    """
    GET /api/instancias/<slug>/produtos/<variacao_id>/ — detalhe somente
    leitura de UMA variação (SKU) do espelho local desta instância.

    Não dispara sincronização, não fala com fornecedor nem com o Tiny.

    Isolamento: a variação é resolvida por (id E produto__instancia__slug)
    numa consulta só — pedir o id de uma variação de outra instância
    devolve 404, nunca os dados dela. O Produto-pai vem no mesmo hit via
    `select_related`.
    """

    serializer_class = VariacaoDetalheSerializer

    def get_object(self):
        return get_object_or_404(
            Variacao.objects.select_related("produto", "produto__instancia"),
            id=self.kwargs["variacao_id"],
            produto__instancia__slug=self.kwargs["slug"],
        )


class AtualizarVariacaoFornecedorView(APIView):
    """Enfileira a atualização individual; a rede nunca roda no ciclo HTTP."""

    @extend_schema(request=None, responses=AtualizacaoVariacaoFornecedorSerializer)
    def post(self, request, slug, variacao_id):
        instancia = _obter_instancia_ou_404(slug)
        with transaction.atomic():
            variacao = get_object_or_404(
                Variacao.objects.select_for_update().select_related("produto"),
                pk=variacao_id,
                produto__instancia=instancia,
            )
            limite = timezone.now() - timezone.timedelta(
                seconds=ATUALIZACAO_FORNECEDOR_STALE_SEGUNDOS
            )
            AtualizacaoVariacaoFornecedor.objects.filter(
                variacao=variacao,
                status=StatusAtualizacaoVariacao.RODANDO,
            ).filter(Q(heartbeat_em__lt=limite) | Q(heartbeat_em__isnull=True)).update(
                status=StatusAtualizacaoVariacao.INTERROMPIDO,
                erro="A operação anterior ficou stale e foi interrompida automaticamente.",
                finalizado_em=timezone.now(),
            )
            if AtualizacaoVariacaoFornecedor.objects.filter(
                variacao=variacao, status=StatusAtualizacaoVariacao.RODANDO
            ).exists():
                return Response(
                    {"detail": "Já existe uma atualização do fornecedor em andamento para esta variação."},
                    status=status.HTTP_409_CONFLICT,
                )
            operacao = AtualizacaoVariacaoFornecedor.objects.create(
                instancia=instancia,
                variacao=variacao,
                fornecedor=variacao.produto.fornecedor,
                heartbeat_em=timezone.now(),
            )

            def enfileirar():
                resultado = atualizar_variacao_fornecedor_task.delay(operacao.id)
                task_id = getattr(resultado, "id", "")
                if isinstance(task_id, str) and task_id:
                    AtualizacaoVariacaoFornecedor.objects.filter(pk=operacao.id).update(
                        celery_task_id=task_id
                    )

            transaction.on_commit(enfileirar)
        return Response(
            AtualizacaoVariacaoFornecedorSerializer(operacao).data,
            status=status.HTTP_202_ACCEPTED,
        )


class StatusAtualizarVariacaoFornecedorView(APIView):
    """Consulta o estado persistido de uma atualização individual."""

    @extend_schema(request=None, responses=AtualizacaoVariacaoFornecedorSerializer)
    def get(self, request, slug, variacao_id, operacao_id):
        operacao = get_object_or_404(
            AtualizacaoVariacaoFornecedor.objects.select_related("instancia"),
            pk=operacao_id,
            variacao_id=variacao_id,
            instancia__slug=slug,
        )
        limite = timezone.now() - timezone.timedelta(
            seconds=ATUALIZACAO_FORNECEDOR_STALE_SEGUNDOS
        )
        if operacao.status == StatusAtualizacaoVariacao.RODANDO and (
            operacao.heartbeat_em is None or operacao.heartbeat_em < limite
        ):
            AtualizacaoVariacaoFornecedor.objects.filter(
                pk=operacao.pk, status=StatusAtualizacaoVariacao.RODANDO
            ).update(
                status=StatusAtualizacaoVariacao.INTERROMPIDO,
                erro="A task Celery não enviou heartbeat dentro do prazo; operação interrompida.",
                finalizado_em=timezone.now(),
            )
            operacao.refresh_from_db()
        return Response(AtualizacaoVariacaoFornecedorSerializer(operacao).data)


class AtualizarVariacaoTinyView(APIView):
    """Cadastra ou atualiza somente uma variação no Tiny."""

    @extend_schema(request=None, responses=VariacaoDetalheSerializer)
    def post(self, request, slug, variacao_id):
        instancia = _obter_instancia_ou_404(slug)
        with transaction.atomic():
            variacao = get_object_or_404(
                Variacao.objects.select_for_update().select_related("produto"),
                pk=variacao_id,
                produto__instancia=instancia,
            )
            fornecedor = variacao.produto.fornecedor
            pronta, motivo = _pronta_para_cadastro_tiny(instancia, fornecedor)
            if not pronta:
                return Response({"detail": motivo}, status=status.HTTP_400_BAD_REQUEST)
            if cadastro_tiny_bloqueia_espelho(instancia, fornecedor):
                return Response(
                    {"detail": "Há uma sincronização em massa deste fornecedor com o Tiny em andamento."},
                    status=status.HTTP_409_CONFLICT,
                )
            try:
                atualizar_variacao_individual(instancia, variacao)
            except Exception as exc:
                return Response({"detail": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
            variacao.refresh_from_db()
        return Response(VariacaoDetalheSerializer(variacao).data)


class _ColetorResultadoVariacao(EventosSincronizacao):
    """Capta o motivo do bloqueio / a mensagem de erro do cadastro de UMA variação."""

    def __init__(self):
        self.motivo_bloqueio = None
        self.erro = None

    def variacao_bloqueada(self, variacao, motivo):
        self.motivo_bloqueio = motivo

    def variacao_erro(self, variacao, exc):
        self.erro = str(exc)


class CadastrarVariacaoTinyView(APIView):
    """
    POST /api/instancias/<slug>/produtos/<variacao_id>/cadastro-tiny/ — cadastra
    SÓ esta variação (SKU) no Tiny.

    Usa EXATAMENTE o caminho validado do cadastro em massa
    (`apps.catalogo.tiny_sync.cadastrar_variacao_individual` ->
    `_processar_variacao`): mesmas proteções (SKU exato, estoque<=0, regra P@,
    colisão cross-fornecedor, SKU já existente no Tiny -> bloqueado, nunca
    vinculado), mesmo payload (venda 0, `precoCusto` = `Variacao.preco`,
    `descricaoComplementar` = `Produto.descricao`, fornecedor Tiny + código +
    `padrao=true`) e a MESMA etapa sequencial de imagens logo após criar.

    NÃO cria `Execucao` e NÃO interfere no fluxo em massa. Isolamento
    multi-tenant: a variação é resolvida por (id E produto__instancia).
    Concorrência / clique duplo: `select_for_update` na linha da Variacao —
    um 2º pedido do MESMO SKU espera o 1º e então vê `cadastrado` (409).
    """

    @extend_schema(request=None, responses=VariacaoEspelhoSerializer)
    def post(self, request, slug, variacao_id):
        instancia = _obter_instancia_ou_404(slug)
        variacao = get_object_or_404(
            Variacao.objects.select_related("produto"),
            pk=variacao_id,
            produto__instancia=instancia,
        )
        fornecedor = variacao.produto.fornecedor

        pronta, motivo = _pronta_para_cadastro_tiny(instancia, fornecedor)
        if not pronta:
            return Response({"detail": motivo}, status=status.HTTP_400_BAD_REQUEST)

        if cadastro_tiny_bloqueia_espelho(instancia, fornecedor):
            return Response(
                {"detail": "Há uma sincronização em massa deste fornecedor com o Tiny em "
                 "andamento — aguarde ela terminar para enviar SKUs avulsos."},
                status=status.HTTP_409_CONFLICT,
            )

        with transaction.atomic():
            travada = (
                Variacao.objects.select_for_update()
                .select_related("produto")
                .get(pk=variacao.pk)
            )
            if (travada.tiny_id or "").strip() or travada.status == StatusVariacao.CADASTRADO:
                return Response(
                    {"detail": f"O SKU {travada.sku} já está cadastrado no Tiny "
                     f"(tiny_id={travada.tiny_id})."},
                    status=status.HTTP_409_CONFLICT,
                )

            coletor = _ColetorResultadoVariacao()
            resultado = cadastrar_variacao_individual(instancia, travada, eventos=coletor)
            travada.refresh_from_db()

        if resultado.criadas or resultado.vinculadas:
            # Sucesso — a linha volta com status/tiny_id/ultimo_erro atualizados
            # (se as imagens falharam, `ultimo_erro` carrega o aviso e o produto
            # continua cadastrado, igual ao fluxo em massa).
            return Response(VariacaoEspelhoSerializer(travada).data, status=status.HTTP_200_OK)
        if resultado.bloqueadas:
            return Response(
                {"detail": coletor.motivo_bloqueio or "Cadastro bloqueado pelas regras de negócio."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return Response(
            {"detail": coletor.erro or travada.ultimo_erro or "Falha ao cadastrar o SKU no Tiny."},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


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
        # `escopo=gerais` -> só os logs técnicos da execução (início, pausa,
        # conclusão, ingestão de espelho); é a seção secundária da tela de
        # auditoria, separada da tabela de produtos.
        if self.request.query_params.get("escopo") == "gerais":
            queryset = auditoria.logs_gerais(execucao)
        else:
            queryset = execucao.logs.select_related("variacao").order_by("criado_em", "id")

        nivel = self.request.query_params.get("nivel")
        if nivel in NivelLog.values:
            queryset = queryset.filter(nivel=nivel)

        return queryset


def _obter_execucao_ou_404(slug, execucao_id):
    return get_object_or_404(
        Execucao.objects.select_related("instancia"),
        id=execucao_id,
        instancia__slug=slug,
    )


def _progresso_execucao(execucao) -> float:
    lidos = execucao.total_lidos or 0
    processados = (execucao.total_cadastrados or 0) + (execucao.total_erros or 0)
    if lidos <= 0:
        return 1.0 if execucao.finalizada_em else 0.0
    return round(min(processados / lidos, 1.0), 4)


class ExecucaoDetalheView(APIView):
    """
    GET /api/instancias/<slug>/execucoes/<execucao_id>/ — resumo da execução
    para o topo da tela de auditoria (fornecedor, status/estado, início,
    duração, contadores, progresso, contagem por resultado).

    Só leitura. Isolamento por (id E instancia__slug). Se estiver rodando,
    a UI acompanha via o mesmo polling do detalhe da instância (sem polling
    novo dedicado a esta tela).
    """

    @extend_schema(responses=ExecucaoDetalheSerializer)
    def get(self, request, slug, execucao_id):
        execucao = _obter_execucao_ou_404(slug, execucao_id)
        estado = (
            estado_cadastro_tiny(execucao)
            if execucao.tipo == TipoExecucao.CADASTRO_TINY
            else execucao.status
        )
        dados = {
            "id": execucao.id,
            "fornecedor": execucao.fornecedor,
            "tipo": execucao.tipo,
            "status": execucao.status,
            "estado": estado,
            "iniciada_em": execucao.iniciada_em,
            "finalizada_em": execucao.finalizada_em,
            "duracao_segundos": execucao.duracao_segundos,
            "total_lidos": execucao.total_lidos,
            "total_cadastrados": execucao.total_cadastrados,
            "total_erros": execucao.total_erros,
            "total_ignorados": execucao.total_ignorados,
            "progresso": _progresso_execucao(execucao),
            "mensagem_erro": execucao.mensagem_erro,
            "auditoria": auditoria.resumo_auditoria(execucao),
            "logs_gerais_total": auditoria.logs_gerais(execucao).count(),
        }
        return Response(ExecucaoDetalheSerializer(dados).data)


@extend_schema_view(
    get=extend_schema(
        parameters=[
            OpenApiParameter("busca", str, required=False, description="Busca em SKU / nome do produto."),
            OpenApiParameter(
                "resultado", str, required=False,
                enum=["todos", "cadastrados", "erros", "bloqueados"],
                description="Filtra pelo desfecho do SKU nesta execução.",
            ),
        ]
    )
)
class ExecucaoProdutosView(generics.ListAPIView):
    """
    GET /api/instancias/<slug>/execucoes/<execucao_id>/produtos/ — a tabela
    de auditoria: UMA linha por SKU (o desfecho mais recente dele nesta
    execução), paginada no servidor. Cada linha traz `variacao_id` para
    abrir a tela de produto que já existe.
    """

    serializer_class = ExecucaoProdutoSerializer
    pagination_class = ExecucaoProdutoPagination

    def get_queryset(self):
        execucao = _obter_execucao_ou_404(self.kwargs["slug"], self.kwargs["execucao_id"])
        self._execucao = execucao
        return auditoria.linhas_de_auditoria(
            execucao,
            busca=self.request.query_params.get("busca", ""),
            resultado=self.request.query_params.get("resultado", ""),
        )

    def paginate_queryset(self, queryset):
        pagina = super().paginate_queryset(queryset)
        # serializa a página (LogItem -> dict) com os enriquecimentos (Tiny
        # id / imagens / detalhe curto)
        return auditoria.montar_linhas(self._execucao, list(pagina)) if pagina is not None else None


class ExecucaoProdutoLogsView(generics.ListAPIView):
    """
    GET /api/instancias/<slug>/execucoes/<execucao_id>/produtos/<variacao_id>/
    — todos os logs (técnicos, com detalhe/JSON) de UM SKU nesta execução.
    Usado pelo "ver mensagem técnica completa" da linha.
    """

    serializer_class = LogItemSerializer
    pagination_class = LogItemPagination

    def get_queryset(self):
        execucao = _obter_execucao_ou_404(self.kwargs["slug"], self.kwargs["execucao_id"])
        return auditoria.logs_da_variacao(execucao, self.kwargs["variacao_id"])


class RetentarVariacaoExecucaoView(APIView):
    """
    POST /api/instancias/<slug>/execucoes/<execucao_id>/produtos/<variacao_id>/retentar/
    — "Tentar novamente" um SKU que ficou com ERRO numa execução de cadastro
    no Tiny.

    Reusa EXATAMENTE `cadastrar_variacao_individual` -> `_processar_variacao`
    (SKU exato, estoque<=0, regra P@, colisão, SKU já no Tiny, payload da
    regra definitiva, etapa de imagens) — NENHUMA segunda lógica de Tiny.

    Histórico: os `LogItem`s da tentativa são APPENDADOS na `Execucao`
    original; o log do erro original fica intacto. A tabela de auditoria
    (último desfecho por SKU) e o `resumo_auditoria` se ajustam sozinhos; em
    sucesso, os `Execucao.total_*` são recomputados da verdade do banco.

    Isolamento: execução por (id E instancia__slug); variação por
    (id E produto__instancia == execucao.instancia). Concorrência: 409 se há
    sincronização em massa ATIVA do fornecedor; `select_for_update` na linha
    da Variacao serializa cliques simultâneos do MESMO SKU.
    """

    @extend_schema(request=None, responses=ExecucaoProdutoSerializer)
    def post(self, request, slug, execucao_id, variacao_id):
        execucao = _obter_execucao_ou_404(slug, execucao_id)
        if execucao.tipo != TipoExecucao.CADASTRO_TINY:
            return Response(
                {"detail": "Só execuções de cadastro no Tiny têm 'tentar novamente'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instancia = execucao.instancia
        variacao = get_object_or_404(
            Variacao.objects.select_related("produto"),
            pk=variacao_id,
            produto__instancia=instancia,
        )
        fornecedor = variacao.produto.fornecedor

        if (variacao.tiny_id or "").strip() or variacao.status == StatusVariacao.CADASTRADO:
            return Response(
                {"detail": f"O SKU {variacao.sku} já está cadastrado no Tiny "
                 f"(tiny_id={variacao.tiny_id})."},
                status=status.HTTP_409_CONFLICT,
            )

        ultimo_desfecho = (
            LogItem.objects.filter(
                execucao=execucao, variacao=variacao, evento__in=EVENTOS_DESFECHO
            )
            .order_by("-criado_em", "-id")
            .values_list("evento", flat=True)
            .first()
        )
        if ultimo_desfecho != EventoLog.ERRO:
            return Response(
                {"detail": "Este SKU não está com erro nesta execução."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )

        pronta, motivo = _pronta_para_cadastro_tiny(instancia, fornecedor)
        if not pronta:
            return Response({"detail": motivo}, status=status.HTTP_400_BAD_REQUEST)

        if cadastro_tiny_bloqueia_espelho(instancia, fornecedor):
            return Response(
                {"detail": "Há uma sincronização em massa deste fornecedor com o Tiny em "
                 "andamento — aguarde ela terminar para tentar SKUs avulsos."},
                status=status.HTTP_409_CONFLICT,
            )

        with transaction.atomic():
            travada = (
                Variacao.objects.select_for_update()
                .select_related("produto")
                .get(pk=variacao.pk)
            )
            if (travada.tiny_id or "").strip() or travada.status == StatusVariacao.CADASTRADO:
                return Response(
                    {"detail": f"O SKU {travada.sku} já está cadastrado no Tiny "
                     f"(tiny_id={travada.tiny_id})."},
                    status=status.HTTP_409_CONFLICT,
                )

            LogItem.objects.create(
                execucao=execucao,
                nivel=NivelLog.INFO,
                evento=EventoLog.GERAL,
                mensagem=(f"Nova tentativa de cadastro do SKU {travada.sku} "
                          "(individual, a partir da tela de execução)")[:500],
                variacao=travada,
                detalhe={"origem": "retentativa_individual"},
            )
            eventos = EventosRetentativa(execucao)
            resultado = cadastrar_variacao_individual(instancia, travada, eventos=eventos)
            travada.refresh_from_db()

            if resultado.criadas or resultado.vinculadas:
                recomputar_contadores_execucao(execucao)

        if resultado.criadas or resultado.vinculadas:
            desfecho = (
                LogItem.objects.filter(
                    execucao=execucao, variacao=travada, evento__in=EVENTOS_DESFECHO
                )
                .select_related("variacao", "variacao__produto")
                .order_by("-criado_em", "-id")
                .first()
            )
            linha = auditoria.montar_linhas(execucao, [desfecho])[0]
            return Response(ExecucaoProdutoSerializer(linha).data, status=status.HTTP_200_OK)

        if resultado.bloqueadas:
            return Response(
                {"detail": eventos.motivo_bloqueio or "Cadastro bloqueado pelas regras de negócio."},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        return Response(
            {"detail": eventos.erro or travada.ultimo_erro or "Falha ao recadastrar o SKU no Tiny."},
            status=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


def _variacao_ids_com_erro(execucao, *, busca=""):
    """variacao_id dos SKUs cujo ÚLTIMO desfecho nesta execução é ERRO (mesma
    fonte da aba 'Erros' da tela)."""
    return list(
        auditoria.linhas_de_auditoria(execucao, busca=busca, resultado="erros")
        .values_list("variacao_id", flat=True)
    )


class RetentarLoteExecucaoView(APIView):
    """
    Retentativa EM LOTE dos SKUs com erro de uma execução de cadastro no Tiny.

    POST .../execucoes/<execucao_id>/retentar-lote/ — enfileira UM job Celery
    (`retentar_lote_task`). Corpo:
      `{"variacao_ids": [1,2,3]}`  -> exatamente esses (só os que de fato são
                                     erro nesta execução são aceitos);
      `{"todos": true}`            -> TODOS os SKUs com erro da execução,
                                     resolvidos no servidor (opcional `busca`
                                     para casar o filtro visível na UI).
    O navegador faz UMA requisição; o job processa os SKUs sequencialmente.

    GET .../execucoes/<execucao_id>/retentar-lote/ — estado do job MAIS RECENTE
    (polling de progresso): status/total/processados/sucessos/erros/ignorados.

    Cada SKU passa pelo MESMO fluxo do retry individual
    (`cadastrar_variacao_individual` -> `_processar_variacao`); os `LogItem`s
    vão para a `Execucao` original; o log do erro original nunca é tocado.

    Segurança: execução por (id E instancia__slug); só SKUs da instância da
    execução entram na fila; 409 se há sincronização em massa ATIVA do
    fornecedor OU um job de lote já `rodando` para a execução.
    """

    @extend_schema(responses=RetentativaLoteSerializer)
    def get(self, request, slug, execucao_id):
        execucao = _obter_execucao_ou_404(slug, execucao_id)
        lote = execucao.retentativas_lote.order_by("-criado_em").first()
        if lote is None:
            return Response(
                {"detail": "Nenhuma retentativa em lote para esta execução."},
                status=status.HTTP_404_NOT_FOUND,
            )
        if lote.status == StatusRetentativaLote.RODANDO and heartbeat_expirado(
            lote.heartbeat_em, timezone.now()
        ):
            _reconciliar_retentativa_lote_stale(lote.id)
            lote.refresh_from_db()
        return Response(RetentativaLoteSerializer(lote).data)

    @extend_schema(request=None, responses=RetentativaLoteSerializer)
    def post(self, request, slug, execucao_id):
        execucao = _obter_execucao_ou_404(slug, execucao_id)
        if execucao.tipo != TipoExecucao.CADASTRO_TINY:
            return Response(
                {"detail": "Só execuções de cadastro no Tiny têm retentativa em lote."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        instancia = execucao.instancia
        fornecedor = execucao.fornecedor

        pronta, motivo = _pronta_para_cadastro_tiny(instancia, fornecedor)
        if not pronta:
            return Response({"detail": motivo}, status=status.HTTP_400_BAD_REQUEST)
        if cadastro_tiny_bloqueia_espelho(instancia, fornecedor):
            return Response(
                {"detail": "Há uma sincronização em massa deste fornecedor com o Tiny em "
                 "andamento — aguarde ela terminar."},
                status=status.HTTP_409_CONFLICT,
            )

        erro_ids = _variacao_ids_com_erro(execucao, busca=str(request.data.get("busca") or ""))
        todos = bool(request.data.get("todos"))
        if todos:
            alvos = erro_ids
        else:
            pedidos = request.data.get("variacao_ids")
            if not isinstance(pedidos, list) or not all(isinstance(x, int) for x in pedidos):
                return Response(
                    {"detail": "Informe `variacao_ids` (lista de inteiros) ou `todos: true`."},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            # só os que REALMENTE são erro nesta execução (isolamento + coerência)
            erro_set = set(erro_ids)
            alvos = [vid for vid in pedidos if vid in erro_set]
        if not alvos:
            return Response(
                {"detail": "Nenhum SKU com erro válido selecionado."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        with transaction.atomic():
            _travar_instancia(instancia)
            ativo = (
                execucao.retentativas_lote.filter(status=StatusRetentativaLote.RODANDO)
                .order_by("-criado_em")
                .first()
            )
            if ativo and not heartbeat_expirado(ativo.heartbeat_em, timezone.now()):
                return Response(
                    {"detail": "Já existe uma retentativa em lote em andamento para esta execução."},
                    status=status.HTTP_409_CONFLICT,
                )
            token = uuid.uuid4().hex
            lote = RetentativaLote.objects.create(
                execucao=execucao,
                variacao_ids=list(alvos),
                selecao_todos=todos,
                total=len(alvos),
                lease_token=token,
                heartbeat_em=timezone.now(),
            )

        retentar_lote_task.delay(lote.id, token)
        return Response(RetentativaLoteSerializer(lote).data, status=status.HTTP_202_ACCEPTED)


class PararRetentativaLoteView(APIView):
    """Solicita a parada cooperativa da retentativa em lote mais recente."""

    @extend_schema(request=None, responses=RetentativaLoteSerializer)
    def post(self, request, slug, execucao_id):
        execucao = _obter_execucao_ou_404(slug, execucao_id)
        with transaction.atomic():
            _travar_instancia(execucao.instancia)
            lote = execucao.retentativas_lote.order_by("-criado_em").first()
            if lote is None:
                return Response(
                    {"detail": "Nenhuma retentativa em lote para esta execução."},
                    status=status.HTTP_404_NOT_FOUND,
                )
            if lote.status != StatusRetentativaLote.RODANDO:
                return Response(
                    {"detail": "A retentativa em lote não está em andamento."},
                    status=status.HTTP_409_CONFLICT,
                )
            if heartbeat_expirado(lote.heartbeat_em, timezone.now()):
                _reconciliar_retentativa_lote_stale(lote.id)
                lote.refresh_from_db()
                return Response(RetentativaLoteSerializer(lote).data)
            lote.parada_solicitada = True
            lote.save(update_fields=["parada_solicitada"])
        return Response(RetentativaLoteSerializer(lote).data, status=status.HTTP_202_ACCEPTED)


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
