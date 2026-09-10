"""
Regras de negócio da sincronização de produtos com o Tiny/Olist.

FONTE ÚNICA da lógica — usada por:
  - o management command `cadastrar_produtos_tiny` (decisão + criação/vínculo);
  - o management command `sincronizar_imagens_tiny` (idempotência de imagens);
  - o management command `sincronizar_com_tiny` (orquestra os dois);
  - a task Celery `cadastrar_produtos_tiny_task` (sincronização em massa
    disparada pela interface);
  - o endpoint de estimativa/preview.

Não há I/O de apresentação aqui (nem `stdout`, nem `LogItem`): quem chama
decide como reportar, passando um `EventosSincronizacao`. Assim CLI e task
compartilham exatamente as mesmas proteções e o mesmo caminho de código.

Proteções (idênticas às validadas no piloto — ver README):
  - correspondência com o Tiny SÓ por SKU EXATO (`buscar_produto_por_sku`);
    nunca por nome/NCM/descrição/fuzzy, nunca consulta `ProdutoTiny`;
  - `estoque <= 0` / status `aguardando` -> BLOQUEADO;
  - regra P@ (produto descontinuado) -> BLOQUEADO;
  - mesmo SKU em mais de um fornecedor na instância -> BLOQUEADO;
  - SKU já existe no Tiny e a Variacao não tem vínculo confirmado ->
    BLOQUEADO (exceto XBZ, que reconcilia composto e legado sem criar);
  - resposta ambígua do POST -> reconsulta por SKU exato; sem confirmação,
    NÃO marca como cadastrado;
  - imagens: idempotência por `Variacao.imagens_tiny_sincronizadas` (marcador
    das URLs ORIGINAIS do fornecedor), nunca por igualdade de URL;
  - produtos dos demais fornecedores só são alterados por `tiny_id` ou
    vínculo explicitamente confirmado; a reconciliação automática é XBZ;
  - um erro individual gera evento e NÃO interrompe o lote.
"""

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import Count, Q
from django.utils import timezone

from apps.instancias.constants import Fornecedor
from apps.instancias.models import CredencialFornecedor
from apps.instancias.tiny_client import TinyApiClient
from apps.sincronizacao.models import (
    STATUS_EXECUCAO_ABERTOS,
    STATUS_EXECUCAO_ATIVOS,
    Execucao,
    StatusExecucao,
    TipoExecucao,
)

from .models import StatusVariacao, Variacao

# Teto de anexos (imagens) por produto — escolha nossa, não do cliente
# (documentado no README). Mora aqui; o command re-exporta por compat.
MAX_ANEXOS_POR_PRODUTO = 5

# -- Heartbeat / lease da sincronização em massa ---------------------------
#
# A task bate o heartbeat da Execucao ANTES de cada produto. Uma Execucao
# `rodando`/`pausando` cujo `heartbeat_em` está mais velho que este timeout
# é considerada travada (worker morreu) e vira `interrompido`.
#
# 10 minutos é conservador de propósito: no pior caso patológico (um único
# produto preso em tempestade de 429 — até 5 retentativas com backoff, ~2
# min, mais a espera do rate-limiter compartilhado, ~1 min, por chamada; 2
# chamadas Tiny por produto na fase 1) um produto legítimo leva ~6 min. 10
# min dá ~1,6x de margem sobre esse pior caso e ~cem vezes o caso típico
# (produto = poucos segundos). Um worker realmente morto é reconhecido em
# no máximo 10 min.
HEARTBEAT_TIMEOUT_SEGUNDOS = 600


def heartbeat_expirado(heartbeat_em, agora, *, timeout_segundos: int = HEARTBEAT_TIMEOUT_SEGUNDOS) -> bool:
    """`True` se `heartbeat_em` é nulo ou mais velho que o timeout."""
    if heartbeat_em is None:
        return True
    return (agora - heartbeat_em).total_seconds() > timeout_segundos


# Motivos pelos quais o orquestrador para antes de esvaziar a fila.
PARADA_PAUSA = "pausa"
PARADA_LEASE_PERDIDA = "lease_perdida"

# Estados de UI da sincronização de um fornecedor com o Tiny.
ESTADO_PRONTO = "pronto"
ESTADO_SINCRONIZANDO = "sincronizando"
ESTADO_PAUSANDO = "pausando"
ESTADO_PAUSADO = "pausado"
ESTADO_INTERROMPIDO = "interrompido"
ESTADO_CONCLUIDO = "concluido"
ESTADO_PARCIAL = "parcial"


def execucao_cadastro_tiny_aberta(instancia, fornecedor):
    """A Execucao de cadastro Tiny 'aberta' (rodando/pausando/pausado/interrompido) do par, ou None."""
    return (
        Execucao.objects.filter(
            instancia=instancia,
            fornecedor=fornecedor,
            tipo=TipoExecucao.CADASTRO_TINY,
            status__in=STATUS_EXECUCAO_ABERTOS,
        )
        .order_by("-iniciada_em")
        .first()
    )


def cadastro_tiny_bloqueia_espelho(instancia, fornecedor, *, agora=None) -> bool:
    """
    True se há um cadastro Tiny ATIVO (rodando/pausando com heartbeat vivo)
    para o par — nesse caso a importação/atualização do espelho do MESMO
    fornecedor não deve ocorrer. Um `rodando` com heartbeat expirado é
    considerado travado e NÃO bloqueia (será reconhecido como interrompido).
    """
    agora = agora or timezone.now()
    for execucao in Execucao.objects.filter(
        instancia=instancia,
        fornecedor=fornecedor,
        tipo=TipoExecucao.CADASTRO_TINY,
        status__in=STATUS_EXECUCAO_ATIVOS,
    ):
        if not heartbeat_expirado(execucao.heartbeat_em, agora):
            return True
    return False


def estado_cadastro_tiny(execucao, *, agora=None) -> str:
    """
    Estado de UI derivado da Execucao de cadastro Tiny mais recente do par
    (pode ser None). Faz a checagem de heartbeat em tempo de leitura: um
    `rodando`/`pausando` sem heartbeat recente já aparece como
    `interrompido` mesmo antes do reaper rodar.
    """
    if execucao is None:
        return ESTADO_PRONTO
    agora = agora or timezone.now()
    status = execucao.status
    if status in STATUS_EXECUCAO_ATIVOS and heartbeat_expirado(execucao.heartbeat_em, agora):
        return ESTADO_INTERROMPIDO
    return {
        StatusExecucao.RODANDO: ESTADO_SINCRONIZANDO,
        StatusExecucao.PAUSANDO: ESTADO_PAUSANDO,
        StatusExecucao.PAUSADO: ESTADO_PAUSADO,
        StatusExecucao.INTERROMPIDO: ESTADO_INTERROMPIDO,
        StatusExecucao.SUCESSO: ESTADO_CONCLUIDO,
        StatusExecucao.PARCIAL: ESTADO_PARCIAL,
        StatusExecucao.FALHA: ESTADO_PARCIAL,
    }.get(status, ESTADO_PRONTO)

# Ações neutras (sem texto de UI). Cada chamador rotula como quiser.
ACAO_CRIAR = "criar"
ACAO_VINCULAR = "vincular"
ACAO_ATUALIZAR_EXISTENTE = "atualizar_existente"
ACAO_BLOQUEADO = "bloqueado"
ACAO_JA_CADASTRADO = "ja_cadastrado"

# Motivo do bloqueio quando o par (instância, fornecedor) não tem o id do
# contato-fornecedor no Tiny configurado. Mensagem única — a UI/preview e a
# auditoria por SKU mostram exatamente este texto.
MOTIVO_SEM_TINY_FORNECEDOR_ID = (
    "Fornecedor no Tiny não configurado para este fornecedor nesta instância — "
    "informe o \"ID do fornecedor no Tiny\" em Instância › Fornecedores antes de cadastrar."
)


def tiny_fornecedor_id_de(instancia, fornecedor) -> int | None:
    """
    Id do contato-fornecedor no Tiny para o par (instância, fornecedor), ou
    None se não houver `CredencialFornecedor` ou o campo estiver vazio.

    Chamado UMA vez por rodada/execução (nunca por SKU) — ver
    `executar_sincronizacao_tiny` e o command `cadastrar_produtos_tiny`.
    """
    return (
        CredencialFornecedor.objects.filter(instancia=instancia, fornecedor=fornecedor)
        .values_list("tiny_fornecedor_id", flat=True)
        .first()
    )


class TinySyncError(RuntimeError):
    """Falha ao sincronizar UMA variação (não interrompe o lote)."""


class IdentidadeTinyError(TinySyncError):
    """A variação não tem um código válido para ser publicado no Tiny."""


def identidade_tiny(variacao) -> str:
    """
    Identidade externa do produto no Tiny.

    `Variacao.sku` continua sendo a identidade interna/original. Só a XBZ
    possui uma identidade externa diferente: o `codigo_composto` dos
    atributos normalizados. O payload bruto é histórico da importação, não
    uma segunda fonte de verdade para publicação.
    """
    interno = (variacao.sku or "").strip()
    if variacao.produto.fornecedor != Fornecedor.XBZ:
        if not interno:
            raise IdentidadeTinyError("SKU vazio no espelho")
        return interno

    composto = (variacao.atributos or {}).get("codigo_composto")
    composto = str(composto or "").strip()
    if not composto:
        raise IdentidadeTinyError(
            f"XBZ {interno!r} sem CodigoComposto — cadastro no Tiny bloqueado"
        )
    return composto


def sku_tiny_para_exibicao(variacao) -> str:
    """Retorna o SKU Tiny destinado às telas e respostas de leitura.

    A identidade usada pelo sincronizador continua sendo ``identidade_tiny``.
    Para XBZ, porém, a fonte semântica do valor exibido é deliberadamente o
    atributo normalizado ``codigo_composto``; ``Variacao.sku`` jamais é um
    fallback de apresentação nesse caso.
    """
    if not variacao:
        return ""
    if variacao.produto.fornecedor == Fornecedor.XBZ:
        atributos = variacao.atributos or {}
        return str(atributos.get("codigo_composto") or "").strip()
    try:
        return identidade_tiny(variacao)
    except IdentidadeTinyError:
        return ""


@dataclass
class Decisao:
    acao: str
    motivo: str
    tiny_existente: dict | None = None
    payload: dict | None = None


# ---------------------------------------------------------------------------
# Seleção de variações
# ---------------------------------------------------------------------------


def colisoes_cross_fornecedor(instancia) -> dict[str, list[str]]:
    """
    `{identidade_tiny: [fornecedores]}` para identidades que aparecem em mais
    de um fornecedor
    nesta instância — esses nunca são cadastrados automaticamente (não dá
    para saber a qual produto o SKU do Tiny corresponderia).
    """
    mapa: dict[str, list[str]] = {}
    for variacao in Variacao.objects.filter(produto__instancia=instancia).select_related("produto"):
        try:
            codigo = identidade_tiny(variacao)
        except IdentidadeTinyError:
            continue
        mapa.setdefault(codigo, []).append(variacao.produto.fornecedor)
    return {codigo: sorted(set(forns)) for codigo, forns in mapa.items()
            if len(forns) > 1}


def colisoes_identidade_tiny(instancia, identidade, *, excluir_variacao_id=None) -> list[Variacao]:
    """Variações locais que usam a mesma identidade Tiny exata."""
    resultado = []
    qs = Variacao.objects.filter(produto__instancia=instancia).select_related("produto")
    if excluir_variacao_id:
        qs = qs.exclude(pk=excluir_variacao_id)
    for outra in qs:
        try:
            if identidade_tiny(outra) == identidade:
                resultado.append(outra)
        except IdentidadeTinyError:
            continue
    return resultado


def fila_cadastro(instancia, *, fornecedor=None, skus=None, limite=None):
    """
    Fila do management command `cadastrar_produtos_tiny`: quando `skus` é
    dado, processa exatamente esses (status ignorado, permite retry de ERRO);
    senão, só os `pendente`.
    """
    qs = Variacao.objects.filter(produto__instancia=instancia).select_related("produto")
    if fornecedor:
        qs = qs.filter(produto__fornecedor=fornecedor)
    if skus:
        qs = qs.filter(sku__in=skus)
    else:
        qs = qs.filter(status=StatusVariacao.PENDENTE)
    qs = qs.order_by("produto__fornecedor", "sku", "id")
    if limite:
        qs = qs[:limite]
    return list(qs)


def fila_cadastro_massa(instancia, fornecedor, *, limite=None, incluir_imagens_pendentes=True):
    """
    Fila da sincronização em massa (task/UI): de UM fornecedor.

      - `pendente` E `erro`: reexecução retenta o que falhou;
      - `cadastrado` com `tiny_id` cujo envio de imagens ainda NÃO teve
        sucesso (`imagens_tiny_sincronizadas` vazio e há imagem no espelho):
        a retomada precisa vê-las para concluir a ETAPA DE IMAGENS do SKU —
        `avaliar_variacao` devolve `ja_cadastrado` e o produto NÃO é
        recriado; só as imagens são (re)enviadas. Assim uma falha de imagem
        não fica perdida até um `sincronizar_imagens_tiny` avulso.

    Nunca inclui `aguardando`/`descontinuado` (a avaliação as bloquearia).
    `incluir_imagens_pendentes=False` volta ao recorte "só o que seria
    criado/vinculado" — usado pela estimativa (preview).
    """
    pendente_ou_erro = Q(status__in=[StatusVariacao.PENDENTE, StatusVariacao.ERRO])
    if incluir_imagens_pendentes:
        imagens_pendentes = (
            Q(status=StatusVariacao.CADASTRADO)
            & ~Q(tiny_id__isnull=True)
            & ~Q(tiny_id="")
            & ~Q(imagens=[])
            & Q(imagens_tiny_sincronizadas=[])
        )
        filtro = pendente_ou_erro | imagens_pendentes
    else:
        filtro = pendente_ou_erro
    qs = (
        Variacao.objects.filter(produto__instancia=instancia, produto__fornecedor=fornecedor)
        .filter(filtro)
        .select_related("produto")
        .order_by("produto__codigo_pai", "sku", "id")
    )
    if limite:
        qs = qs[:limite]
    return list(qs)


def fila_imagens(instancia, *, fornecedor=None, skus=None, limite=None):
    """
    Fila da fase de imagens — a mesma do command `sincronizar_imagens_tiny`:
    variações `cadastrado` com `tiny_id` e com imagem no espelho. A
    idempotência real (marcador / contagem no Tiny) é resolvida em
    `sincronizar_imagens_variacao`.
    """
    qs = (
        Variacao.objects.filter(
            produto__instancia=instancia, status=StatusVariacao.CADASTRADO
        )
        .exclude(tiny_id__isnull=True)
        .exclude(tiny_id="")
        .exclude(imagens=[])
        .select_related("produto")
        .order_by("produto__fornecedor", "produto__codigo_pai", "sku", "id")
    )
    if fornecedor:
        qs = qs.filter(produto__fornecedor=fornecedor)
    if skus:
        qs = qs.filter(sku__in=skus)
    if limite:
        qs = qs[:limite]
    return list(qs)


# ---------------------------------------------------------------------------
# Decisão por variação
# ---------------------------------------------------------------------------


def bloqueio_local(variacao, colisoes_por_sku, *, permitir_sem_estoque=False) -> str | None:
    """
    Motivo de bloqueio determinável SEM falar com o Tiny (para o preview e
    como 1ª etapa da avaliação real). `None` = passou nas proteções locais.
    """
    try:
        sku = identidade_tiny(variacao)
    except IdentidadeTinyError as exc:
        return str(exc)
    if variacao.status == StatusVariacao.DESCONTINUADO or (
        variacao.produto_id and variacao.produto.descontinuado
    ):
        return "regra P@ / produto descontinuado — nunca vai ao Tiny"
    if not permitir_sem_estoque and (variacao.estoque <= 0 or variacao.status == StatusVariacao.AGUARDANDO):
        return f"estoque <= 0 (estoque={variacao.estoque}) — aguarda reposição"
    if sku in colisoes_por_sku:
        forns = ", ".join(colisoes_por_sku[sku])
        return f"mesmo SKU em mais de um fornecedor nesta instância: {forns}"
    return None


def avaliar_variacao(
    cliente, instancia, variacao, colisoes_por_sku, *, vincular_skus=(), tiny_fornecedor_id=None,
    atualizar_cadastrada=False,
) -> Decisao:
    """
    Decisão completa (inclui o GET por SKU exato no Tiny). Chamada tanto pelo
    command quanto pela task — mesma implementação, mesmas proteções.

    `tiny_fornecedor_id`: id do contato-fornecedor no Tiny para o par
    (instância, fornecedor), resolvido UMA vez pelo chamador. Sem ele, criar
    um produto novo fica BLOQUEADO (uma variação já `cadastrado` não é
    afetada — só segue para a etapa de imagens).
    """
    vincular_skus = set(vincular_skus or ())
    tem_vinculo = bool((variacao.tiny_id or "").strip())
    # Atualizar um vínculo pode zerar estoque. Identidade, P@ e colisões
    # continuam obrigatórios, também quando a única etapa pendente é imagem.
    motivo_local = bloqueio_local(variacao, colisoes_por_sku, permitir_sem_estoque=tem_vinculo)
    if motivo_local:
        return Decisao(ACAO_BLOQUEADO, motivo_local)
    # Um vínculo existente nunca volta para busca/CREATE, mesmo após erro de PUT.
    if tem_vinculo:
        if variacao.status == StatusVariacao.CADASTRADO and not atualizar_cadastrada:
            return Decisao(ACAO_JA_CADASTRADO, f"já vinculada (tiny_id={variacao.tiny_id})")
        return Decisao(ACAO_ATUALIZAR_EXISTENTE, f"atualizar vínculo tiny_id={variacao.tiny_id}",
                       tiny_existente={"id": variacao.tiny_id})
    sku = identidade_tiny(variacao)

    if not tiny_fornecedor_id:
        return Decisao(ACAO_BLOQUEADO, MOTIVO_SEM_TINY_FORNECEDOR_ID)

    if variacao.produto.fornecedor == Fornecedor.XBZ:
        # O espelho XBZ mantém o código X... localmente, mas o Tiny pode
        # conter esse SKU legado antes de o código composto ter sido adotado.
        # As duas consultas são exatas e precisam ser feitas antes de qualquer
        # POST para impedir a criação de um segundo produto.
        existente_composto = cliente.buscar_produto_por_sku(sku)
        existente_legado = None
        if variacao.sku != sku:
            existente_legado = cliente.buscar_produto_por_sku(variacao.sku)
        if existente_composto and existente_legado:
            return Decisao(
                ACAO_BLOQUEADO,
                "conflito XBZ: os SKUs Tiny "
                f"{sku!r} (id={existente_composto.get('id')}) e "
                f"{variacao.sku!r} (id={existente_legado.get('id')}) "
                "já existem no Tiny; reconciliação manual obrigatória",
            )
        existente = existente_composto or existente_legado
        if existente:
            return Decisao(
                ACAO_ATUALIZAR_EXISTENTE,
                "produto XBZ existente encontrado por SKU exato; será atualizado "
                f"sem criar outro (tiny_id={existente.get('id')})",
                tiny_existente=existente,
            )
    else:
        existente = cliente.buscar_produto_por_sku(sku)  # GET — permitido no dry-run

    if existente:
        if sku in vincular_skus or variacao.sku in vincular_skus:
            return Decisao(
                ACAO_VINCULAR,
                f"vínculo confirmado pelo operador (--vincular-skus); tiny_id={existente.get('id')}",
                tiny_existente=existente,
            )
        return Decisao(
            ACAO_BLOQUEADO,
            f"SKU já existe no Tiny (id={existente.get('id')}) e não possui vínculo confirmado — "
            f"revisar manualmente e, se for nosso, reprocessar com --vincular-skus",
            tiny_existente=existente,
        )

    return Decisao(
        ACAO_CRIAR,
        "SKU não existe no Tiny",
        payload=montar_payload_produto(variacao, instancia, tiny_fornecedor_id=tiny_fornecedor_id),
    )


# ---------------------------------------------------------------------------
# Escrita no Tiny + persistência local
# ---------------------------------------------------------------------------


def criar_produto_no_tiny(cliente, variacao, payload) -> str:
    """
    POST /produtos e devolve o `tiny_id` confirmado. Se a resposta for
    ambígua, reconsulta pelo SKU EXATO; sem confirmação inequívoca,
    levanta `TinySyncError` (a variação NÃO é marcada como cadastrada).
    """
    resultado = cliente.criar_produto(payload)
    tiny_id = _id_do_resultado(resultado)
    if not tiny_id:
        confirmado = cliente.buscar_produto_por_sku(identidade_tiny(variacao))
        tiny_id = _id_do_resultado(confirmado) if confirmado else None
    if not tiny_id:
        raise TinySyncError(
            "POST /produtos não devolveu um id utilizável e a reconsulta por SKU não "
            f"confirmou — NÃO marcado como cadastrado. Resposta: {resultado!r}"
        )
    return str(tiny_id)


def marcar_cadastrada(variacao, tiny_id, *, preco_custo_publicado):
    variacao.tiny_id = str(tiny_id)
    variacao.status = StatusVariacao.CADASTRADO
    variacao.cadastrado_em = timezone.now()
    variacao.ultimo_erro = ""
    campos = ["tiny_id", "status", "cadastrado_em", "ultimo_erro", "atualizado_em"]
    if preco_custo_publicado is not None:
        # CRIAÇÃO (não VINCULAÇÃO): o POST /produtos já leva o pacote da regra
        # definitiva (descricaoComplementar, precos {0/0/custo}, fornecedor
        # padrão) E o estoque inicial (= `variacao.estoque`) — então marca os
        # três marcadores como publicados, para a propagação automática não
        # reenviar logo em seguida um Balanço/PUT redundante. Numa VINCULAÇÃO
        # o produto preexistente no Tiny não passou pela nossa regra:
        # `preco_custo_publicado` vem None e os marcadores ficam nulos, para o
        # passo de correção de dados/estoque ajustá-lo depois.
        variacao.preco_custo_tiny_sincronizado = preco_custo_publicado
        variacao.dados_tiny_sincronizados_em = timezone.now()
        variacao.estoque_tiny_sincronizado = variacao.estoque
        campos.append("preco_custo_tiny_sincronizado")
        campos.append("dados_tiny_sincronizados_em")
        campos.append("estoque_tiny_sincronizado")
    variacao.save(update_fields=campos)


def marcar_erro(variacao, mensagem):
    variacao.status = StatusVariacao.ERRO
    variacao.ultimo_erro = str(mensagem)
    variacao.save(update_fields=["status", "ultimo_erro", "atualizado_em"])


# ---------------------------------------------------------------------------
# Imagens (idempotência validada — ver sincronizar_imagens_tiny)
# ---------------------------------------------------------------------------


def imagens_utilizaveis(variacao) -> list[str]:
    """URLs REAIS do espelho: strings não vazias, sem duplicata, na ordem, teto 5."""
    vistas: set[str] = set()
    urls: list[str] = []
    for item in variacao.imagens or []:
        if isinstance(item, str) and item.strip() and item.strip() not in vistas:
            urls.append(item.strip())
            vistas.add(item.strip())
    return urls[:MAX_ANEXOS_POR_PRODUTO]


# resultados possíveis de `sincronizar_imagens_variacao`
IMG_SEM_IMAGEM = "sem_imagem"
IMG_JA_OK = "ja_ok"          # marcador local já cobre — nada feito, sem GET
IMG_RECONCILIADA = "reconciliada"  # Tiny já tinha o suficiente — só marcou local
IMG_PENDENTE = "pendente"    # precisa de PUT (só acontece em modo só-reconciliar)
IMG_ENVIADA = "enviada"      # PUT executado


def sincronizar_imagens_variacao(cliente, variacao, *, so_reconciliar=False, dry_run=False) -> dict:
    """
    Sincroniza as imagens de UMA variação já cadastrada. Idempotente:
      1. marcador local já cobre todas as URLs desejadas -> nada (sem GET);
      2. GET dos anexos: Tiny já tem QUANTIDADE >= desejada -> só reconcilia
         o marcador com as URLs ORIGINAIS (ex.: MC511 corrigido à mão);
      3. senão -> PUT com a lista completa e marca todas como sincronizadas.

    `so_reconciliar`: nunca faz PUT (para o caso MC511 sem risco de duplicar).
    `dry_run`: nenhuma escrita (local ou Tiny) — o `cliente` deve estar em
    modo somente-leitura; devolve o que faria.
    """
    desejadas = imagens_utilizaveis(variacao)
    if not desejadas:
        return {"resultado": IMG_SEM_IMAGEM, "desejadas": [], "atuais": None}

    if set(desejadas).issubset(set(variacao.imagens_tiny_sincronizadas or [])):
        return {"resultado": IMG_JA_OK, "desejadas": desejadas, "atuais": None}

    atuais = cliente.anexos_do_produto(int(variacao.tiny_id))  # GET
    if len(atuais) >= len(desejadas):
        _marcar_imagens_sincronizadas(variacao, desejadas, dry_run=dry_run)
        return {"resultado": IMG_RECONCILIADA, "desejadas": desejadas, "atuais": len(atuais)}

    if so_reconciliar:
        return {"resultado": IMG_PENDENTE, "desejadas": desejadas, "atuais": len(atuais)}

    if not dry_run:
        cliente.sincronizar_anexos_produto(int(variacao.tiny_id), desejadas)
        _marcar_imagens_sincronizadas(variacao, desejadas, dry_run=False)
    return {"resultado": IMG_ENVIADA, "desejadas": desejadas, "atuais": len(atuais)}


def _marcar_imagens_sincronizadas(variacao, urls_originais, *, dry_run):
    if dry_run:
        return
    variacao.imagens_tiny_sincronizadas = sorted(set(urls_originais))[:MAX_ANEXOS_POR_PRODUTO]
    variacao.ultimo_erro = ""
    variacao.save(update_fields=["imagens_tiny_sincronizadas", "ultimo_erro", "atualizado_em"])


def registrar_erro_imagem(variacao, mensagem):
    """Falha ao sincronizar imagem NÃO mexe em `status`/`tiny_id` — só grava o erro."""
    variacao.ultimo_erro = str(mensagem)
    variacao.save(update_fields=["ultimo_erro", "atualizado_em"])


# ---------------------------------------------------------------------------
# Estimativa (preview) — sem falar com o Tiny
# ---------------------------------------------------------------------------


def estimar_cadastro(instancia, fornecedor) -> dict:
    """
    Números para a tela de confirmação, SEM nenhuma chamada ao Tiny:
      - `elegiveis`: passariam nas proteções LOCAIS e seriam avaliadas
        (teto — a checagem "SKU já existe no Tiny" só ocorre na execução);
      - `bloqueadas_local`: reprovadas por estoque/P@/SKU/colisão;
      - `ja_cadastradas`: já têm vínculo (status cadastrado);
      - `sem_estoque` / `descontinuadas`: recorte informativo.
    """
    colisoes_por_sku = colisoes_cross_fornecedor(instancia)
    fila = fila_cadastro_massa(instancia, fornecedor, incluir_imagens_pendentes=False)
    elegiveis = bloqueadas = 0
    for variacao in fila:
        if bloqueio_local(variacao, colisoes_por_sku):
            bloqueadas += 1
        else:
            elegiveis += 1

    por_status = {
        linha["status"]: linha["total"]
        for linha in (
            Variacao.objects.filter(
                produto__instancia=instancia, produto__fornecedor=fornecedor
            )
            .values("status")
            .annotate(total=Count("id"))
        )
    }
    return {
        "fornecedor": fornecedor,
        "elegiveis": elegiveis,
        "bloqueadas_local": bloqueadas,
        "ja_cadastradas": por_status.get(StatusVariacao.CADASTRADO, 0),
        "sem_estoque": por_status.get(StatusVariacao.AGUARDANDO, 0),
        "descontinuadas": por_status.get(StatusVariacao.DESCONTINUADO, 0),
        "total_espelho": sum(por_status.values()),
    }


# ---------------------------------------------------------------------------
# Orquestrador (create -> confirma -> imagens), por fornecedor
# ---------------------------------------------------------------------------


class EventosSincronizacao:
    """Callbacks de progresso. Base no-op; a CLI escreve stdout, a task grava LogItem."""

    def inicio(self, *, total_fila: int) -> None: ...
    def variacao_avaliada(self, variacao, decisao: Decisao) -> None: ...
    def variacao_criada(self, variacao, tiny_id: str) -> None: ...
    def variacao_vinculada(self, variacao, tiny_id) -> None: ...
    def variacao_bloqueada(self, variacao, motivo: str) -> None: ...
    def variacao_ja_cadastrada(self, variacao) -> None: ...
    def variacao_erro(self, variacao, exc: Exception) -> None: ...
    def imagens(self, variacao, resultado: dict) -> None: ...
    def fim(self, resultado: "ResultadoSincronizacao") -> None: ...


class ControladorSincronizacao:
    """
    Deixa quem chama abortar o orquestrador de forma COOPERATIVA — a
    verificação acontece só entre unidades de trabalho, nunca no meio de
    uma. Base no-op; a task Celery usa uma subclasse que checa
    pausa/lease no banco e bate o heartbeat.
    """

    def checar(self) -> str | None:
        """`None` = seguir; `PARADA_PAUSA` / `PARADA_LEASE_PERDIDA` = parar já."""
        return None


@dataclass
class ResultadoSincronizacao:
    fila: int = 0
    criadas: int = 0
    vinculadas: int = 0
    bloqueadas: int = 0
    ja_cadastradas: int = 0
    erros: int = 0
    imagens_enviadas: int = 0
    imagens_reconciliadas: int = 0
    imagens_ja_ok: int = 0
    imagens_sem: int = 0
    imagens_erros: int = 0
    #: motivo pelo qual parou antes de esvaziar a fila (pausa / lease perdida),
    #: ou None quando processou tudo.
    interrompida_por: str | None = None

    def _contabilizar_imagem(self, resultado: dict) -> None:
        r = resultado.get("resultado")
        if r == IMG_ENVIADA:
            self.imagens_enviadas += 1
        elif r == IMG_RECONCILIADA:
            self.imagens_reconciliadas += 1
        elif r == IMG_JA_OK:
            self.imagens_ja_ok += 1
        elif r == IMG_SEM_IMAGEM:
            self.imagens_sem += 1


def executar_sincronizacao_tiny(
    instancia,
    fornecedor,
    *,
    cliente: TinyApiClient | None = None,
    dry_run: bool = False,
    limite: int | None = None,
    vincular_skus=(),
    eventos: EventosSincronizacao | None = None,
    controlador: ControladorSincronizacao | None = None,
) -> ResultadoSincronizacao:
    """
    Sincroniza UM fornecedor de UMA instância com o Tiny, SEQUENCIALMENTE
    por SKU. Para cada variação da fila, na ordem:
      1. avalia (proteções locais + GET por SKU exato);
      2. cria / vincula no Tiny quando elegível (ou reconhece já cadastrada);
      3. se ficou com `tiny_id`, sincroniza IMEDIATAMENTE as imagens desse
         mesmo SKU (idempotente pelo marcador local);
      4. só então avança para o próximo SKU.

    Assim um produto criado nunca fica no Tiny sem imagem por causa de uma
    pausa: a etapa de imagens faz parte da mesma unidade de trabalho.

    Um erro individual (criação OU imagem) gera evento e NÃO interrompe o
    lote. Falha de imagem NÃO altera `status`/`tiny_id` e NÃO marca as
    imagens como sincronizadas — na retomada o SKU volta à fila só para a
    etapa de imagens (a avaliação devolve `ja_cadastrado`, sem recriar).
    Reexecução é idempotente: variações já cadastradas com imagem OK saem
    da fila.

    `controlador.checar()` é consultado ANTES de cada SKU (nunca no meio de
    um — nem entre o cadastro e as imagens dele): devolvendo um motivo, o
    orquestrador para imediatamente e `resultado.interrompida_por` fica
    preenchido — a fila é reconstruída do banco na retomada, sem depender de
    posição em memória.
    """
    eventos = eventos or EventosSincronizacao()
    controlador = controlador or ControladorSincronizacao()
    vincular_skus = set(vincular_skus or ())
    if cliente is None:
        cliente = TinyApiClient(instancia, somente_leitura=dry_run)

    colisoes = colisoes_cross_fornecedor(instancia)
    # Resolvido UMA vez por rodada (nunca por SKU). Sem ele, `avaliar_variacao`
    # bloqueia toda criação nova deste fornecedor.
    tiny_fornecedor_id = tiny_fornecedor_id_de(instancia, fornecedor)
    fila = fila_cadastro_massa(instancia, fornecedor, limite=limite)
    resultado = ResultadoSincronizacao(fila=len(fila))
    eventos.inicio(total_fila=len(fila))

    for variacao in fila:
        parada = controlador.checar()
        if parada:
            resultado.interrompida_por = parada
            eventos.fim(resultado)
            return resultado

        _processar_variacao(
            cliente,
            instancia,
            variacao,
            colisoes,
            tiny_fornecedor_id=tiny_fornecedor_id,
            vincular_skus=vincular_skus,
            resultado=resultado,
            eventos=eventos,
            dry_run=dry_run,
        )

    eventos.fim(resultado)
    return resultado


def _processar_variacao(
    cliente,
    instancia,
    variacao,
    colisoes,
    *,
    tiny_fornecedor_id,
    vincular_skus,
    resultado: "ResultadoSincronizacao",
    eventos: "EventosSincronizacao",
    dry_run: bool,
    atualizar_cadastrada=False,
    sincronizar_imagens=True,
) -> None:
    """
    UMA unidade de trabalho do cadastro no Tiny: avalia (proteções locais +
    GET por SKU exato) -> cria / vincula / bloqueia / reconhece já cadastrada
    -> se ficou com `tiny_id`, sincroniza IMEDIATAMENTE as imagens do MESMO
    SKU. Muta `resultado` e dispara `eventos`; nunca levanta.

    É a MESMA função usada pelo cadastro em massa
    (`executar_sincronizacao_tiny`, no loop) e pelo cadastro individual
    (`cadastrar_variacao_individual`) — sem duplicar nenhuma regra.
    """
    try:
        decisao = avaliar_variacao(
            cliente,
            instancia,
            variacao,
            colisoes,
            vincular_skus=vincular_skus,
            tiny_fornecedor_id=tiny_fornecedor_id,
            atualizar_cadastrada=atualizar_cadastrada,
        )
    except Exception as exc:  # falha na avaliação (ex.: GET explodiu)
        resultado.erros += 1
        if not dry_run:
            marcar_erro(variacao, str(exc))
        eventos.variacao_erro(variacao, exc)
        return

    eventos.variacao_avaliada(variacao, decisao)

    if decisao.acao == ACAO_BLOQUEADO:
        resultado.bloqueadas += 1
        eventos.variacao_bloqueada(variacao, decisao.motivo)
        return
    if decisao.acao == ACAO_JA_CADASTRADO:
        resultado.ja_cadastradas += 1
        eventos.variacao_ja_cadastrada(variacao)
        # SKU já vinculado que voltou à fila só para concluir a etapa de
        # imagens (envio anterior falhou / nunca rodou). Nada é recriado.
        if sincronizar_imagens:
            _sincronizar_imagens_do_sku(cliente, variacao, resultado, eventos, dry_run=dry_run)
        return

    if dry_run:
        if decisao.acao == ACAO_CRIAR:
            resultado.criadas += 1
        elif decisao.acao in (ACAO_VINCULAR, ACAO_ATUALIZAR_EXISTENTE):
            resultado.vinculadas += 1
        return

    try:
        if decisao.acao == ACAO_CRIAR:
            tiny_id = criar_produto_no_tiny(cliente, variacao, decisao.payload)
            marcar_cadastrada(
                variacao, tiny_id, preco_custo_publicado=_preco_custo_publicado(variacao)
            )
            resultado.criadas += 1
            eventos.variacao_criada(variacao, tiny_id)
        elif decisao.acao == ACAO_VINCULAR:
            marcar_cadastrada(
                variacao, decisao.tiny_existente["id"], preco_custo_publicado=None
            )
            resultado.vinculadas += 1
            eventos.variacao_vinculada(variacao, decisao.tiny_existente["id"])
        elif decisao.acao == ACAO_ATUALIZAR_EXISTENTE:
            if not variacao.tiny_id:
                # Guarda a autoridade do ID antes do PUT. Falha parcial será
                # retomada por este ID; nunca volta para criação.
                variacao.tiny_id = str(decisao.tiny_existente["id"])
                variacao.save(update_fields=["tiny_id", "atualizado_em"])
            _atualizar_variacao_vinculada(cliente, instancia, variacao)
            resultado.vinculadas += 1
            eventos.variacao_vinculada(variacao, decisao.tiny_existente["id"])
    except Exception as exc:  # uma variação ruim não trava o lote
        resultado.erros += 1
        marcar_erro(variacao, str(exc))
        eventos.variacao_erro(variacao, exc)
        return

    # Etapa de imagens do MESMO SKU, imediatamente após o cadastro/vínculo
    # bem-sucedido. Faz parte da unidade de trabalho: no cadastro em massa uma
    # pausa só é atendida DEPOIS disto, no `controlador.checar()` do próximo SKU.
    if sincronizar_imagens:
        _sincronizar_imagens_do_sku(cliente, variacao, resultado, eventos, dry_run=dry_run)


def cadastrar_variacao_individual(
    instancia,
    variacao,
    *,
    cliente: TinyApiClient | None = None,
    eventos: EventosSincronizacao | None = None,
    atualizar_cadastrada=False,
) -> ResultadoSincronizacao:
    """
    Cadastra UMA variação (SKU) no Tiny pelo MESMO caminho de código do
    cadastro em massa — `_processar_variacao` — com todas as proteções
    (SKU exato, estoque<=0, regra P@, colisão cross-fornecedor, SKU já no
    Tiny), o MESMO payload (venda 0, `precoCusto` = `Variacao.preco`,
    `descricaoComplementar`, fornecedor) e a MESMA etapa sequencial de
    imagens logo após criar.

    Diferenças do fluxo em massa: processa só esta variação, NÃO cria
    `Execucao`, NÃO permite `--vincular-skus` (só XBZ possui reconciliação
    automática por composto/legado) e NÃO tem dry-run (quem
    chama já decidiu escrever).

    Devolve o `ResultadoSincronizacao` (contadores) — quem chama traduz
    para a resposta. `eventos` (opcional) capta motivo de bloqueio / erro.
    """
    eventos = eventos or EventosSincronizacao()
    if cliente is None:
        cliente = TinyApiClient(instancia, somente_leitura=False)

    fornecedor = variacao.produto.fornecedor
    colisoes = colisoes_cross_fornecedor(instancia)
    tiny_fornecedor_id = tiny_fornecedor_id_de(instancia, fornecedor)
    resultado = ResultadoSincronizacao(fila=1)

    _processar_variacao(
        cliente,
        instancia,
        variacao,
        colisoes,
        tiny_fornecedor_id=tiny_fornecedor_id,
        vincular_skus=set(),
        resultado=resultado,
        eventos=eventos,
        dry_run=False,
        atualizar_cadastrada=atualizar_cadastrada,
    )
    return resultado


def atualizar_variacao_individual(
    instancia,
    variacao,
    *,
    cliente: TinyApiClient | None = None,
    eventos: EventosSincronizacao | None = None,
) -> ResultadoSincronizacao:
    """Atualiza uma variação já vinculada no Tiny, ou cadastra-a se pendente."""
    return cadastrar_variacao_individual(
        instancia, variacao, cliente=cliente, eventos=eventos, atualizar_cadastrada=True
    )


def _atualizar_variacao_vinculada(cliente, instancia, variacao):
    """Atualiza o produto já identificado por ``variacao.tiny_id``."""

    from .tiny_dados_produto import DadosProdutoError, montar_payload_atualizacao

    detalhe = cliente.obter_produto(int(variacao.tiny_id))
    sku_no_tiny = str(detalhe.get("sku") or "")
    identidade = identidade_tiny(variacao)
    aceitos = {identidade, variacao.sku}
    if sku_no_tiny not in aceitos:
        raise DadosProdutoError(
            f"SKU do Tiny ({sku_no_tiny!r}) não corresponde à variação ({identidade!r}); atualização abortada."
        )
    fornecedor_id = tiny_fornecedor_id_de(instancia, variacao.produto.fornecedor)
    if not fornecedor_id:
        raise DadosProdutoError(MOTIVO_SEM_TINY_FORNECEDOR_ID)
    payload = montar_payload_atualizacao(
        detalhe,
        variacao=variacao,
        tiny_fornecedor_id=fornecedor_id,
        sku_atual_esperado=sku_no_tiny,
    )
    cliente.atualizar_produto(int(variacao.tiny_id), payload)
    cliente.atualizar_estoque(
        int(variacao.tiny_id),
        quantidade=variacao.estoque,
        preco_unitario=variacao.preco_custo_tiny,
    )
    variacao.preco_custo_tiny_sincronizado = variacao.preco
    variacao.estoque_tiny_sincronizado = variacao.estoque
    variacao.dados_tiny_sincronizados_em = timezone.now()
    variacao.ultimo_erro = ""
    variacao.status = StatusVariacao.CADASTRADO
    variacao.cadastrado_em = variacao.cadastrado_em or timezone.now()
    variacao.save(update_fields=[
        "preco_custo_tiny_sincronizado", "estoque_tiny_sincronizado",
        "dados_tiny_sincronizados_em", "ultimo_erro", "atualizado_em", "status", "cadastrado_em",
    ])


def _sincronizar_imagens_do_sku(cliente, variacao, resultado, eventos, *, dry_run: bool) -> None:
    """
    Sincroniza as imagens de UM SKU logo após ele ter sido cadastrado/
    vinculado. Reaproveita `sincronizar_imagens_variacao` (mesma idempotência
    do command `sincronizar_imagens_tiny`). Uma falha aqui:
      - é contabilizada (`resultado.imagens_erros`) e vira evento estruturado
        (`IMAGENS_ERRO`) na auditoria do SKU;
      - grava só `ultimo_erro` — NÃO mexe em `status`/`tiny_id`, então o
        produto não é recriado numa retomada;
      - NÃO marca as imagens como sincronizadas (o marcador continua vazio),
        então a retomada tenta de novo.
    """
    if dry_run:
        return
    if not (variacao.tiny_id or "").strip():
        return
    try:
        r = sincronizar_imagens_variacao(cliente, variacao)
    except Exception as exc:
        resultado.imagens_erros += 1
        registrar_erro_imagem(variacao, str(exc))
        eventos.imagens(variacao, {"resultado": "erro", "erro": str(exc)})
        return
    resultado._contabilizar_imagem(r)
    eventos.imagens(variacao, r)


def _preco_custo_publicado(variacao) -> Decimal:
    """O payload de criação levou `precos.precoCusto` = este valor (= Variacao.preco)."""
    return variacao.preco_custo_tiny


# ---------------------------------------------------------------------------
# Payload de criação (contrato v3 — inalterado; ver README / piloto)
# ---------------------------------------------------------------------------


def montar_payload_produto(variacao, instancia, *, tiny_fornecedor_id=None) -> dict:
    # Regra definitiva do cliente (2026-09-08): o valor do fornecedor é CUSTO
    # (`precos.precoCusto`); o preço de VENDA no Tiny fica sempre zerado.
    # `descricaoComplementar` vem de `Produto.descricao` do espelho.
    payload = {
        "sku": identidade_tiny(variacao),
        "descricao": variacao.nome,
        "descricaoComplementar": (variacao.produto.descricao or "") if variacao.produto_id else "",
        "tipo": "S",
        "unidade": instancia.tiny_unidade_medida_padrao,
        "origem": instancia.tiny_origem_padrao,
        "ncm": variacao.ncm or None,
        "precos": {
            "preco": float(variacao.preco_venda_tiny),      # 0
            "precoPromocional": 0,
            "precoCusto": float(variacao.preco_custo_tiny),  # = Variacao.preco
        },
        "estoque": {"controlar": True, "inicial": float(variacao.estoque)},
    }
    dimensoes = _montar_dimensoes(variacao)
    if dimensoes:
        payload["dimensoes"] = dimensoes
    garantia = (variacao.atributos or {}).get("garantia_do_produto")
    if garantia:
        payload["garantia"] = garantia
    if tiny_fornecedor_id is not None:
        # Vínculo com o contato-fornecedor no Tiny desta instância. O código
        # do produto no fornecedor é sempre o SKU EXATO da variação (a chave
        # operacional única de todo o fluxo), nunca o código do produto-pai.
        payload["fornecedores"] = [
            {
                "id": int(tiny_fornecedor_id),
                "padrao": True,
                "codigoProdutoNoFornecedor": identidade_tiny(variacao),
            }
        ]
    return payload


def _montar_dimensoes(variacao):
    campos = {
        "largura": variacao.largura,
        "altura": variacao.altura,
        "comprimento": variacao.comprimento,
        "diametro": variacao.diametro,
        "pesoLiquido": variacao.peso_liquido,
        "pesoBruto": variacao.peso_bruto,
    }
    preenchidos = {k: v for k, v in campos.items() if v is not None}
    return preenchidos or None


def _id_do_resultado(resultado):
    if not isinstance(resultado, dict):
        return None
    if _id_valido(resultado.get("id")):
        return resultado["id"]
    for wrapper in ("produto", "data", "retorno", "registro"):
        sub = resultado.get(wrapper)
        if isinstance(sub, dict) and _id_valido(sub.get("id")):
            return sub["id"]
    return None


def _id_valido(valor):
    if valor is None:
        return False
    texto = str(valor).strip()
    return bool(texto) and texto.lower() not in ("0", "none", "null", "")
