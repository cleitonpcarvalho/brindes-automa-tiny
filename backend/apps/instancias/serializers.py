from django.urls import reverse
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.sincronizacao.models import StatusExecucao

from .constants import Fornecedor
from .models import Instancia

CORES_FORNECEDOR = ("ok", "atencao", "erro", "nao_configurado")


class InstanciaSerializer(serializers.ModelSerializer):
    """
    Nunca inclui client_secret, access_token ou refresh_token — só
    indicadores (se está preenchido, quando expira, qual o status).
    """

    client_secret = serializers.CharField(write_only=True, required=False, allow_blank=False)
    access_token_preenchido = serializers.SerializerMethodField()
    refresh_token_preenchido = serializers.SerializerMethodField()
    url_callback = serializers.SerializerMethodField()

    class Meta:
        model = Instancia
        fields = [
            "id",
            "nome",
            "cnpj",
            "slug",
            "client_id",
            "client_secret",
            "status",
            "tentativas_falha",
            "ultimo_erro",
            "access_token_preenchido",
            "refresh_token_preenchido",
            "token_expira_em",
            "refresh_expira_em",
            "rate_limit_por_minuto",
            "tiny_origem_padrao",
            "tiny_unidade_medida_padrao",
            "url_callback",
            "criado_em",
            "atualizado_em",
        ]
        read_only_fields = [
            "id",
            "slug",
            "status",
            "tentativas_falha",
            "ultimo_erro",
            "token_expira_em",
            "refresh_expira_em",
            "rate_limit_por_minuto",
            "criado_em",
            "atualizado_em",
        ]
        extra_kwargs = {"client_id": {"required": False}}

    def get_access_token_preenchido(self, obj):
        return bool(obj.access_token)

    def get_refresh_token_preenchido(self, obj):
        return bool(obj.refresh_token)

    def get_url_callback(self, obj):
        caminho = reverse("tiny-oauth-callback", kwargs={"slug": obj.slug})
        request = self.context.get("request")
        return request.build_absolute_uri(caminho) if request else caminho

    def validate(self, dados):
        # client_id/client_secret só são obrigatórios ao CRIAR — em um PATCH
        # (self.instance já existe) qualquer subconjunto de campos é válido.
        if self.instance is None:
            faltando = [c for c in ("client_id", "client_secret") if not dados.get(c)]
            if faltando:
                raise serializers.ValidationError(
                    {campo: "Obrigatório ao criar a instância." for campo in faltando}
                )
        return dados


class FornecedoresStatusSerializer(serializers.Serializer):
    """Uma cor por fornecedor — ver InstanciaListagemSerializer.get_fornecedores."""

    xbz = serializers.ChoiceField(choices=CORES_FORNECEDOR)
    asia = serializers.ChoiceField(choices=CORES_FORNECEDOR)
    somarcas = serializers.ChoiceField(choices=CORES_FORNECEDOR)
    spot = serializers.ChoiceField(choices=CORES_FORNECEDOR)


class ProdutosContagemSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    cadastrados = serializers.IntegerField()


class UltimaSincronizacaoSerializer(serializers.Serializer):
    em = serializers.DateTimeField(allow_null=True)
    fornecedor = serializers.ChoiceField(choices=Fornecedor.choices, allow_null=True)


def _cor_fornecedor(status_execucao, credencial_ativa):
    if not credencial_ativa or status_execucao is None:
        return "nao_configurado"
    return {
        StatusExecucao.SUCESSO: "ok",
        StatusExecucao.PARCIAL: "atencao",
        StatusExecucao.RODANDO: "atencao",
        StatusExecucao.FALHA: "erro",
    }.get(status_execucao, "nao_configurado")


class InstanciaListagemSerializer(InstanciaSerializer):
    """
    Serializer da listagem (passo 8): acrescenta métricas agregadas por
    linha. Só usado com o queryset de `apps.instancias.listagem.
    queryset_listagem` — os campos extras lêem anotações e o prefetch de
    credenciais montados lá, sem disparar consulta nova por linha.
    """

    fornecedores = serializers.SerializerMethodField()
    produtos = serializers.SerializerMethodField()
    ultima_sincronizacao = serializers.SerializerMethodField()

    class Meta(InstanciaSerializer.Meta):
        fields = InstanciaSerializer.Meta.fields + ["fornecedores", "produtos", "ultima_sincronizacao"]

    @extend_schema_field(FornecedoresStatusSerializer)
    def get_fornecedores(self, obj):
        credenciais_ativas = {
            credencial.fornecedor for credencial in obj.credenciais_fornecedor.all() if credencial.ativo
        }
        return {
            valor: _cor_fornecedor(getattr(obj, f"status_execucao_{valor}"), valor in credenciais_ativas)
            for valor, _rotulo in Fornecedor.choices
        }

    @extend_schema_field(ProdutosContagemSerializer)
    def get_produtos(self, obj):
        return {"total": obj.produtos_total, "cadastrados": obj.produtos_cadastrados}

    @extend_schema_field(UltimaSincronizacaoSerializer)
    def get_ultima_sincronizacao(self, obj):
        return {"em": obj.ultima_sincronizacao_em, "fornecedor": obj.ultima_sincronizacao_fornecedor}
