from django.db.models import Count
from drf_spectacular.utils import extend_schema_field
from rest_framework import serializers

from apps.catalogo.models import StatusVariacao, Variacao
from apps.fornecedores.services import listar_cadencias_com_defaults
from apps.sincronizacao.models import Execucao, StatusExecucao

from .constants import CAMPOS_POR_FORNECEDOR, Fornecedor
from .mascaramento import mascarar_credenciais
from .models import Instancia
from .tiny_oauth import montar_url_callback

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
            "token_emitido_em",
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
            "token_emitido_em",
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
        return montar_url_callback(obj.slug)

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


class ProdutosDetalheContagemSerializer(serializers.Serializer):
    total = serializers.IntegerField()
    cadastrados = serializers.IntegerField()
    aguardando = serializers.IntegerField()
    com_erro = serializers.IntegerField()


class FornecedorDetalheSerializer(serializers.Serializer):
    fornecedor = serializers.ChoiceField(choices=Fornecedor.choices)
    cor = serializers.ChoiceField(choices=CORES_FORNECEDOR)
    ultima_execucao_em = serializers.DateTimeField(allow_null=True)
    ultima_execucao_status = serializers.ChoiceField(choices=StatusExecucao.choices, allow_null=True)
    produtos_total = serializers.IntegerField()
    credencial_configurada = serializers.BooleanField()
    credencial_ativa = serializers.BooleanField()


class CadenciaDetalheSerializer(serializers.Serializer):
    fornecedor = serializers.ChoiceField(choices=Fornecedor.choices)
    intervalo_minutos = serializers.IntegerField()
    ativo = serializers.BooleanField()
    proxima_execucao_em = serializers.DateTimeField(allow_null=True)


class ExecucaoResumidaSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    fornecedor = serializers.ChoiceField(choices=Fornecedor.choices)
    tipo = serializers.CharField()
    status = serializers.CharField()
    iniciada_em = serializers.DateTimeField()
    finalizada_em = serializers.DateTimeField(allow_null=True)
    duracao_segundos = serializers.FloatField(allow_null=True)
    total_lidos = serializers.IntegerField()
    total_novos = serializers.IntegerField()
    total_atualizados = serializers.IntegerField()
    total_erros = serializers.IntegerField()
    mensagem_erro = serializers.CharField()


class InstanciaDetalheSerializer(InstanciaSerializer):
    """
    Serializer do `retrieve` (passo 10) — só usado para 1 instância por vez,
    por isso faz contagens diretas em vez do aparato de Subquery/Prefetch de
    `listagem.py` (que existe para evitar N+1 numa lista de N linhas).
    """

    produtos = serializers.SerializerMethodField()
    fornecedores = serializers.SerializerMethodField()
    cadencias = serializers.SerializerMethodField()
    ultimas_execucoes = serializers.SerializerMethodField()

    class Meta(InstanciaSerializer.Meta):
        fields = InstanciaSerializer.Meta.fields + [
            "produtos",
            "fornecedores",
            "cadencias",
            "ultimas_execucoes",
        ]

    @extend_schema_field(ProdutosDetalheContagemSerializer)
    def get_produtos(self, obj):
        contagens = (
            Variacao.objects.filter(produto__instancia=obj)
            .values("status")
            .annotate(total=Count("id"))
        )
        por_status = {linha["status"]: linha["total"] for linha in contagens}
        return {
            "total": sum(por_status.values()),
            "cadastrados": por_status.get(StatusVariacao.CADASTRADO, 0),
            "aguardando": por_status.get(StatusVariacao.AGUARDANDO, 0),
            "com_erro": por_status.get(StatusVariacao.ERRO, 0),
        }

    @extend_schema_field(FornecedorDetalheSerializer(many=True))
    def get_fornecedores(self, obj):
        credenciais = {c.fornecedor: c for c in obj.credenciais_fornecedor.all()}
        produtos_por_fornecedor = {
            linha["produto__fornecedor"]: linha["total"]
            for linha in (
                Variacao.objects.filter(produto__instancia=obj)
                .values("produto__fornecedor")
                .annotate(total=Count("id"))
            )
        }

        resultado = []
        for valor, _rotulo in Fornecedor.choices:
            credencial = credenciais.get(valor)
            ultima_execucao = (
                Execucao.objects.filter(instancia=obj, fornecedor=valor).order_by("-iniciada_em").first()
            )
            resultado.append(
                {
                    "fornecedor": valor,
                    "cor": _cor_fornecedor(
                        ultima_execucao.status if ultima_execucao else None,
                        bool(credencial and credencial.ativo),
                    ),
                    "ultima_execucao_em": ultima_execucao.iniciada_em if ultima_execucao else None,
                    "ultima_execucao_status": ultima_execucao.status if ultima_execucao else None,
                    "produtos_total": produtos_por_fornecedor.get(valor, 0),
                    "credencial_configurada": bool(credencial and credencial.credenciais),
                    "credencial_ativa": bool(credencial and credencial.ativo),
                }
            )
        return resultado

    @extend_schema_field(CadenciaDetalheSerializer(many=True))
    def get_cadencias(self, obj):
        return listar_cadencias_com_defaults(obj)

    @extend_schema_field(ExecucaoResumidaSerializer(many=True))
    def get_ultimas_execucoes(self, obj):
        execucoes = Execucao.objects.filter(instancia=obj).order_by("-iniciada_em")[:10]
        return [
            {
                "id": execucao.id,
                "fornecedor": execucao.fornecedor,
                "tipo": execucao.tipo,
                "status": execucao.status,
                "iniciada_em": execucao.iniciada_em,
                "finalizada_em": execucao.finalizada_em,
                "duracao_segundos": execucao.duracao_segundos,
                "total_lidos": execucao.total_lidos,
                "total_novos": execucao.total_novos,
                "total_atualizados": execucao.total_atualizados,
                "total_erros": execucao.total_erros,
                "mensagem_erro": execucao.mensagem_erro,
            }
            for execucao in execucoes
        ]


class CredencialFornecedorRespostaSerializer(serializers.Serializer):
    """Saída de GET/PUT — nunca inclui um valor sensível completo (ver mascaramento.py)."""

    fornecedor = serializers.ChoiceField(choices=Fornecedor.choices)
    ativo = serializers.BooleanField()
    configurado = serializers.BooleanField()
    campos_mascarados = serializers.DictField()
    criado_em = serializers.DateTimeField(allow_null=True)

    @staticmethod
    def montar(fornecedor, credencial):
        credenciais = credencial.credenciais if credencial else {}
        return {
            "fornecedor": fornecedor,
            "ativo": bool(credencial and credencial.ativo),
            "configurado": bool(credencial and credencial.credenciais),
            "campos_mascarados": mascarar_credenciais(fornecedor, credenciais),
            "criado_em": credencial.criado_em if credencial else None,
        }


class CredencialFornecedorEntradaSerializer(serializers.Serializer):
    """Corpo do PUT .../credenciais/<fornecedor>/ — nunca ecoa o que recebeu."""

    credenciais = serializers.DictField(child=serializers.CharField(allow_blank=True))
    ativo = serializers.BooleanField(default=True)

    def __init__(self, *args, fornecedor=None, **kwargs):
        self._fornecedor = fornecedor
        super().__init__(*args, **kwargs)

    def validate_credenciais(self, valor):
        campos = CAMPOS_POR_FORNECEDOR.get(self._fornecedor)
        if campos is None:
            raise serializers.ValidationError(f"Fornecedor '{self._fornecedor}' desconhecido.")

        obrigatorias = {chave for chave, regras in campos.items() if regras["obrigatorio"]}
        aceitas = set(campos.keys())
        recebidas = set(valor.keys())

        faltando = obrigatorias - recebidas
        if faltando:
            raise serializers.ValidationError(f"Campos obrigatórios faltando: {sorted(faltando)}.")

        desconhecidas = recebidas - aceitas
        if desconhecidas:
            raise serializers.ValidationError(f"Campos desconhecidos para este fornecedor: {sorted(desconhecidas)}.")

        vazias = {chave for chave in obrigatorias if not valor.get(chave)}
        if vazias:
            raise serializers.ValidationError(f"Campos obrigatórios não podem ficar vazios: {sorted(vazias)}.")

        return valor


class CadenciaFornecedorSerializer(serializers.Serializer):
    fornecedor = serializers.ChoiceField(choices=Fornecedor.choices, read_only=True)
    intervalo_minutos = serializers.IntegerField(min_value=1, required=False)
    ativo = serializers.BooleanField(required=False)
    proxima_execucao_em = serializers.DateTimeField(read_only=True, allow_null=True)


class ConfiguracoesInstanciaSerializer(serializers.ModelSerializer):
    """
    Configurações operacionais do Tiny da instância — os dois campos que hoje
    só o Django Admin edita. É deliberadamente estreito: nenhum campo sensível
    (slug, cnpj, client_id/secret, tokens, status) está nos `fields`, então um
    PATCH/PUT por esta rota não tem como tocá-los — chaves extras no corpo são
    ignoradas pelo DRF.

    As validações vêm do próprio model: `tiny_origem_padrao` herda os
    MinValueValidator(0)/MaxValueValidator(8) e `tiny_unidade_medida_padrao`
    herda max_length=10.
    """

    class Meta:
        model = Instancia
        fields = ["tiny_origem_padrao", "tiny_unidade_medida_padrao"]


class SincronizarRespostaSerializer(serializers.Serializer):
    execucao_id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=StatusExecucao.choices)


class AutorizarRespostaSerializer(serializers.Serializer):
    """
    Corpo real da action `autorizar` — documentado à parte porque, sem
    `@extend_schema_field`/`@extend_schema`, o drf-spectacular inferia o
    schema de retorno a partir do `serializer_class` do ViewSet (Instancia),
    que não bate com o que a view de fato devolve.
    """

    url_autorizacao = serializers.URLField()
    redirect_uri = serializers.URLField()
