from datetime import timedelta

from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction
from django.utils import timezone
from django.utils.text import slugify

from .constants import Fornecedor
from .fields import EncryptedJSONField, EncryptedTextField


# Palavras reservadas por rotas estáticas do frontend (ex.: /instancias/novo é
# o wizard de criação) — uma instância com slug igual a uma dessas ficaria
# permanentemente inacessível pela tela de detalhe. Tratadas como "já
# existentes" para cair no mesmo sufixo numérico usado para colisão de nome.
_SLUGS_RESERVADOS = {"novo", "nova"}


def _gerar_slug_unico(nome, *, excluir_pk=None):
    base = slugify(nome, allow_unicode=False) or "instancia"
    slug = base
    contador = 2
    qs = Instancia.objects.all()
    if excluir_pk is not None:
        qs = qs.exclude(pk=excluir_pk)
    while slug in _SLUGS_RESERVADOS or qs.filter(slug=slug).exists():
        slug = f"{base}-{contador}"
        contador += 1
    return slug


class Instancia(models.Model):
    """Uma conta do Tiny. Cada instância é isolada das demais."""

    # Renovação proativa (passo 4): a partir de que fração do tempo de vida
    # do access_token o comando de renovação já tenta renovar, em vez de
    # esperar o token expirar de fato.
    LIMIAR_RENOVACAO_PROATIVA = 0.7

    # Regra do cliente: 3 falhas seguidas de renovação = para de tentar e
    # exige autorização manual.
    MAX_TENTATIVAS_FALHA_RENOVACAO = 3

    class Status(models.TextChoices):
        NAO_CONECTADO = "nao_conectado", "Não conectado"
        CONECTADO = "conectado", "Conectado"
        ERRO = "erro", "Erro"

    nome = models.CharField(max_length=150)
    cnpj = models.CharField(
        max_length=18,
        blank=True,
        help_text="CNPJ do cliente, formato livre (ex.: 12.345.678/0001-90). "
        "Usado na busca da listagem de instâncias (passo 8).",
    )
    slug = models.SlugField(
        max_length=160,
        unique=True,
        blank=True,
        help_text="Gerado automaticamente a partir do nome na criação. Fica imutável a "
        "partir do momento em que o access_token é preenchido pela primeira vez — não "
        "quando o status muda, e não volta a ser editável depois de um desconectar.",
    )

    client_id = models.CharField(max_length=255, blank=True)
    client_secret = EncryptedTextField(blank=True)
    access_token = EncryptedTextField(blank=True)
    refresh_token = EncryptedTextField(blank=True)
    token_emitido_em = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Quando o access_token atual foi emitido — usado para calcular a "
        "fração do tempo de vida já decorrida (renovação proativa a 70%).",
    )
    token_expira_em = models.DateTimeField(null=True, blank=True)
    refresh_expira_em = models.DateTimeField(null=True, blank=True)

    # Marcador permanente: vira True na primeira vez que aplicar_tokens() é
    # chamado e NUNCA volta a False (nem ao desconectar) — é o que trava o
    # slug, não o status nem o access_token estar preenchido "agora" (que
    # fica vazio de novo depois de um desconectar).
    ja_foi_autorizada = models.BooleanField(default=False)

    oauth_state = models.CharField(
        max_length=64,
        blank=True,
        help_text="State de uso único da última URL de autorização gerada. Consumido "
        "(limpo) assim que o callback é validado, com sucesso ou não.",
    )
    oauth_state_expira_em = models.DateTimeField(null=True, blank=True)

    rate_limit_por_minuto = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Último valor visto no header x-limit-api do Tiny (limite é por conta).",
    )

    # Valores padrão para campos que o Tiny exige mas nenhum fornecedor
    # entrega (origem da mercadoria, unidade de medida). Deliberadamente
    # sem valor-padrão fixo no código — nulo/vazio até alguém configurar
    # pela API ou pelo admin; o comando de cadastro recusa rodar para uma
    # instância sem isso definido.
    tiny_origem_padrao = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(8)],
        help_text="Código de origem da mercadoria (tabela de origem da legislação "
        "fiscal — NF-e): 0 = nacional, 1 = estrangeira, importação direta, 2 a 8 = "
        "demais casos da tabela. Sem valor padrão fixo — configure antes de "
        "cadastrar produtos.",
    )
    tiny_unidade_medida_padrao = models.CharField(
        max_length=10,
        blank=True,
        help_text="Unidade de medida padrão (ex.: UN, PC, CX). Sem valor padrão fixo — "
        "configure antes de cadastrar produtos.",
    )

    status = models.CharField(
        max_length=20, choices=Status.choices, default=Status.NAO_CONECTADO
    )
    tentativas_falha = models.PositiveIntegerField(default=0)
    ultimo_erro = models.TextField(blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Instância"
        verbose_name_plural = "Instâncias"
        ordering = ["nome"]

    def __str__(self):
        return self.nome

    def clean(self):
        if self.pk:
            anterior = (
                Instancia.objects.filter(pk=self.pk)
                .values_list("slug", "ja_foi_autorizada")
                .first()
            )
            if anterior and anterior[1] and anterior[0] != self.slug:
                raise ValidationError(
                    "O slug não pode mais ser alterado: esta instância já foi autorizada "
                    "pelo menos uma vez (independente do status atual)."
                )

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = _gerar_slug_unico(self.nome)
        else:
            self.clean()
        super().save(*args, **kwargs)

    def aplicar_tokens(self, *, access_token, refresh_token, expires_in, refresh_expires_in):
        """
        Grava um novo par de tokens (troca de code ou renovação). O Keycloak
        rotaciona o refresh_token a cada renovação e invalida o anterior —
        por isso os dois são sempre gravados juntos, na mesma transação.
        """
        agora = timezone.now()
        with transaction.atomic():
            self.access_token = access_token
            self.refresh_token = refresh_token
            self.token_emitido_em = agora
            self.token_expira_em = agora + timedelta(seconds=expires_in)
            self.refresh_expira_em = agora + timedelta(seconds=refresh_expires_in)
            self.status = self.Status.CONECTADO
            self.tentativas_falha = 0
            self.ultimo_erro = ""
            self.ja_foi_autorizada = True
            self.save()

    def registrar_falha_renovacao(self, mensagem):
        """
        Regra do cliente: falha na renovação incrementa tentativas_falha e
        grava ultimo_erro; na 3ª falha seguida, muda o status para erro,
        para de tentar (o comando só varre status=conectado) e exige nova
        autorização manual.
        """
        self.tentativas_falha += 1
        self.ultimo_erro = mensagem
        campos = ["tentativas_falha", "ultimo_erro", "atualizado_em"]
        if self.tentativas_falha >= self.MAX_TENTATIVAS_FALHA_RENOVACAO:
            self.status = self.Status.ERRO
            campos.append("status")
        self.save(update_fields=campos)

    def marcar_para_reautorizacao(self, mensagem):
        """Refresh token expirado: não adianta tentar renovar, exige nova autorização direto."""
        self.status = self.Status.ERRO
        self.ultimo_erro = mensagem
        self.save(update_fields=["status", "ultimo_erro", "atualizado_em"])

    def precisa_renovar_token(self, agora=None):
        """Regra do cliente: renovar proativamente ao atingir 70% do tempo de vida do access_token."""
        agora = agora or timezone.now()
        if not self.token_expira_em or not self.token_emitido_em:
            return False
        vida_util = (self.token_expira_em - self.token_emitido_em).total_seconds()
        if vida_util <= 0:
            return False
        decorrido = (agora - self.token_emitido_em).total_seconds()
        return (decorrido / vida_util) >= self.LIMIAR_RENOVACAO_PROATIVA

    def refresh_token_expirado(self, agora=None):
        agora = agora or timezone.now()
        return bool(self.refresh_expira_em and self.refresh_expira_em <= agora)


# Alias em nível de módulo só para o drf-spectacular conseguir resolver
# `ENUM_NAME_OVERRIDES["StatusEnum"]` (config/settings.py) — o loader dele
# (deep_import_string) resolve MODULO.ATRIBUTO ou MODULO.CLASSE.ATRIBUTO, mas
# não um nível a mais de classe aninhada como Instancia.Status.choices.
STATUS_INSTANCIA_CHOICES = Instancia.Status.choices


class CredencialFornecedor(models.Model):
    """
    Credenciais e identificadores de um fornecedor para uma instância. Cada
    fornecedor tem um conjunto de chaves diferente (ver samples/RELATORIO.md),
    por isso `credenciais` é um JSON livre em vez de colunas fixas.

    `tiny_fornecedor_id` NÃO é credencial (não é segredo, não é mascarado): é
    o id do contato/fornecedor correspondente NO Tiny **desta instância** —
    cada instância é uma conta Tiny diferente, então esse id é sempre
    específico do par (instância, fornecedor) e nunca fixo no código.
    """

    instancia = models.ForeignKey(
        Instancia, on_delete=models.CASCADE, related_name="credenciais_fornecedor"
    )
    fornecedor = models.CharField(max_length=20, choices=Fornecedor.choices)
    credenciais = EncryptedJSONField(
        default=dict,
        blank=True,
        help_text="Ex.: xbz={cnpj, token}; asia={api_key, secret_key}; "
        "somarcas={usuario, senha, estado}; spot={access_key}.",
    )
    tiny_fornecedor_id = models.BigIntegerField(
        null=True,
        blank=True,
        help_text="Id do contato/fornecedor correspondente no Tiny desta instância "
        "(payload de criação de produto: fornecedores[].id). Específico por "
        "(instância, fornecedor) — nunca fixo no código. Enquanto nulo, o cadastro "
        "de novos produtos desse fornecedor no Tiny fica bloqueado.",
    )
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Credencial de fornecedor"
        verbose_name_plural = "Credenciais de fornecedor"
        constraints = [
            models.UniqueConstraint(
                fields=["instancia", "fornecedor"], name="unico_fornecedor_por_instancia"
            )
        ]

    def __str__(self):
        return f"{self.instancia} · {self.get_fornecedor_display()}"
