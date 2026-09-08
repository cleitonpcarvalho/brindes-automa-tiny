"""
Suporte para UM teste canário manual de `PUT /produtos/{id}` no Tiny.

NÃO é o backfill em lote. Roda para um único produto, monta um payload
DEFENSIVO (reenvia todo campo gravável que o GET devolveu, para sobreviver
tanto a um PUT parcial quanto a uma substituição total) e altera apenas:

  1. `descricaoComplementar`  <- `Produto.descricao` do espelho local;
  2. `fornecedores`           <- acrescenta o `tiny_fornecedor_id` do par
                                 (instância, fornecedor), sem duplicar e sem
                                 mexer nos fornecedores já existentes.

Sem `--executar`: só GET + monta e imprime o payload que SERIA enviado.
Com `--executar`: GET antes -> PUT -> GET depois -> diff campo a campo.

A semântica de update da API v3 (parcial x substituição total, e o
comportamento do array `fornecedores` no PUT) NÃO é documentada — este
comando existe justamente para observá-la com segurança num produto.
"""

import json

from django.core.management.base import BaseCommand, CommandError

from apps.instancias.constants import Fornecedor
from apps.instancias.models import Instancia
from apps.instancias.tiny_client import TinyApiClient

from ...models import Variacao
from ...tiny_sync import tiny_fornecedor_id_de

# ---------------------------------------------------------------------------
# Campos GRAVÁVEIS de AtualizarProdutoRequestModel (schema oficial v3).
# Só o que está aqui vai no PUT — nada mais. Read-only / endpoint separado /
# fora do modelo de update ficam DE FORA por construção:
#   id, situacao, tipo, tipoVariacao, produtoPai, variacoes, kit, producao,
#   codigoListaServicos, anexos (endpoint próprio), precos.precoCustoMedio,
#   estoque.quantidade (saldo via POST /estoque/{id}), dimensoes.quantidadeVolumes,
#   dimensoes.embalagem (nada a preservar quando id é nulo).
# ---------------------------------------------------------------------------
CAMPOS_TOPO_GRAVAVEIS = (
    "sku",
    "descricao",
    "unidade",
    "unidadePorCaixa",
    "ncm",
    "gtin",
    "garantia",
    "observacoes",
    "codigoEspecificadorSubstituicaoTributaria",
)
SUBCAMPOS_PRECOS = ("preco", "precoPromocional", "precoCusto")
SUBCAMPOS_DIMENSOES = ("largura", "altura", "comprimento", "diametro", "pesoLiquido", "pesoBruto")
SUBCAMPOS_ESTOQUE = ("controlar", "sobEncomenda", "diasPreparacao", "localizacao", "minimo", "maximo")
SUBCAMPOS_TRIBUTACAO = ("gtinEmbalagem", "valorIPIFixo", "classeIPI")
SUBCAMPOS_SEO = ("titulo", "descricao", "keywords", "linkVideo", "slug")

# Campos destacados no diff pós-PUT.
CAMPOS_DIFF = (
    "sku",
    "descricao",
    "descricaoComplementar",
    "fornecedores",
    "ncm",
    "origem",
    "precos",
    "estoque",
    "dimensoes",
    "anexos",
    "situacao",
)
# Os únicos que PODEM mudar; qualquer outra alteração é inesperada.
CAMPOS_ESPERADOS_MUDAR = ("descricaoComplementar", "fornecedores")


def montar_fornecedores(atuais, *, tiny_fornecedor_id, codigo_produto_no_fornecedor):
    """
    Preserva TODOS os fornecedores atuais e acrescenta o nosso apenas se ele
    ainda não estiver na lista (nunca duplica). O nosso entra com
    `padrao=true` só quando nenhum outro já é padrão; senão, `padrao=false`.
    Lista vazia -> o nosso entra como `padrao=true`.

    Cada item é normalizado para o formato do REQUEST
    (`FornecedorProdutoRequestModel`: id, codigoProdutoNoFornecedor, padrao).
    Um fornecedor existente sem `id` utilizável aborta o comando — não dá
    para round-tripá-lo e não se pode perdê-lo silenciosamente.
    """
    alvo = int(tiny_fornecedor_id)
    preservados = []
    ja_existe = False
    ha_padrao = False
    for item in atuais or []:
        if not isinstance(item, dict):
            continue
        bruto_id = item.get("id")
        if not bruto_id:
            raise CommandError(
                f"Fornecedor já associado ao produto sem 'id' utilizável no GET ({item!r}) — "
                "abortado para não removê-lo sem querer no PUT."
            )
        normalizado = {
            "id": int(bruto_id),
            "codigoProdutoNoFornecedor": item.get("codigoProdutoNoFornecedor") or "",
            "padrao": bool(item.get("padrao")),
        }
        preservados.append(normalizado)
        if normalizado["id"] == alvo:
            ja_existe = True
        if normalizado["padrao"]:
            ha_padrao = True

    if not ja_existe:
        preservados.append(
            {
                "id": alvo,
                "codigoProdutoNoFornecedor": codigo_produto_no_fornecedor,
                "padrao": not ha_padrao,
            }
        )
    return preservados


def _copiar_subobjeto(payload, detalhe, chave, subchaves):
    sub = detalhe.get(chave)
    if not isinstance(sub, dict):
        return
    graveis = {k: sub[k] for k in subchaves if k in sub and sub[k] is not None}
    if graveis:
        payload[chave] = graveis


def montar_payload_canario(detalhe, *, descricao_complementar, fornecedores):
    """
    Monta o corpo do `PUT /produtos/{id}` a partir do GET (`detalhe`):
    reenvia todo campo GRAVÁVEL presente, e sobrepõe apenas
    `descricaoComplementar` e `fornecedores`.
    """
    payload = {}
    for chave in CAMPOS_TOPO_GRAVAVEIS:
        if chave in detalhe and detalhe[chave] is not None:
            payload[chave] = detalhe[chave]

    # `origem`: o GET devolve string ("0"); o schema pede integer.
    origem = detalhe.get("origem")
    if origem is not None and str(origem).strip() != "":
        payload["origem"] = int(origem)

    _copiar_subobjeto(payload, detalhe, "precos", SUBCAMPOS_PRECOS)
    _copiar_subobjeto(payload, detalhe, "dimensoes", SUBCAMPOS_DIMENSOES)
    _copiar_subobjeto(payload, detalhe, "estoque", SUBCAMPOS_ESTOQUE)
    _copiar_subobjeto(payload, detalhe, "tributacao", SUBCAMPOS_TRIBUTACAO)

    for chave in ("marca", "categoria"):
        sub = detalhe.get(chave)
        if isinstance(sub, dict) and sub.get("id"):
            payload[chave] = {"id": int(sub["id"])}

    seo = detalhe.get("seo")
    if isinstance(seo, dict):
        seo_gravavel = {k: seo[k] for k in SUBCAMPOS_SEO if seo.get(k)}
        if seo_gravavel:
            payload["seo"] = seo_gravavel

    # --- os DOIS únicos deltas intencionais ---
    payload["descricaoComplementar"] = descricao_complementar
    payload["fornecedores"] = fornecedores
    return payload


def _norm(valor):
    return json.dumps(valor, sort_keys=True, ensure_ascii=False, default=str)


def comparar_campos(antes, depois):
    """Uma linha por campo de `CAMPOS_DIFF`, comparação profunda (JSON normalizado)."""
    linhas = []
    for campo in CAMPOS_DIFF:
        a = antes.get(campo)
        b = depois.get(campo)
        linhas.append(
            {
                "campo": campo,
                "igual": _norm(a) == _norm(b),
                "esperado_mudar": campo in CAMPOS_ESPERADOS_MUDAR,
                "antes": a,
                "depois": b,
            }
        )
    return linhas


class Command(BaseCommand):
    help = (
        "Teste canário de PUT /produtos/{id} no Tiny para UM produto: sem --executar "
        "só monta e imprime o payload; com --executar faz GET -> PUT -> GET e imprime "
        "o diff campo a campo. Altera só descricaoComplementar e fornecedores."
    )

    def add_arguments(self, parser):
        parser.add_argument("--instancia", required=True, help="slug da Instancia")
        parser.add_argument("--tiny-id", required=True, type=int, help="id do produto no Tiny")
        parser.add_argument("--sku", required=True, help="SKU do produto (conferido contra o GET)")
        parser.add_argument(
            "--fornecedor", required=True, choices=[f.value for f in Fornecedor]
        )
        parser.add_argument(
            "--executar",
            action="store_true",
            help="Sem esta flag: só GET + payload (nenhum PUT). Com ela: GET -> PUT -> GET + diff.",
        )

    def handle(self, *args, **options):
        w = self.stdout.write
        executar = options["executar"]
        sku = options["sku"]
        tiny_id = options["tiny_id"]
        fornecedor = options["fornecedor"]

        instancia = self._obter_instancia(options["instancia"])
        if not instancia.access_token:
            raise CommandError(f"Instância '{instancia.slug}' não está conectada ao Tiny.")

        tiny_fornecedor_id = tiny_fornecedor_id_de(instancia, fornecedor)
        if not tiny_fornecedor_id:
            raise CommandError(
                f"Sem 'ID do fornecedor no Tiny' configurado para {fornecedor} nesta instância "
                "(Instância › Fornecedores). Configure antes de rodar o canário."
            )

        variacao = (
            Variacao.objects.select_related("produto")
            .filter(produto__instancia=instancia, produto__fornecedor=fornecedor, sku=sku)
            .first()
        )
        if variacao is None:
            raise CommandError(
                f"SKU {sku!r} não encontrado no espelho para o fornecedor {fornecedor} desta instância."
            )
        descricao_complementar = variacao.produto.descricao or ""
        if not descricao_complementar.strip():
            w(self.style.WARNING(
                f"Produto.descricao do espelho está VAZIO para {sku!r} — o PUT enviaria "
                "descricaoComplementar em branco. Confira o espelho antes de --executar."
            ))

        cliente = TinyApiClient(instancia, somente_leitura=not executar)

        # -- GET antes ---------------------------------------------------
        antes = cliente.obter_produto(tiny_id)
        sku_no_tiny = str(antes.get("sku") or "")
        if sku_no_tiny != sku:
            raise CommandError(
                f"O produto tiny_id={tiny_id} tem sku={sku_no_tiny!r}, esperado {sku!r} — "
                "abortado por segurança (produto errado)."
            )

        fornecedores = montar_fornecedores(
            antes.get("fornecedores"),
            tiny_fornecedor_id=tiny_fornecedor_id,
            codigo_produto_no_fornecedor=sku,
        )
        payload = montar_payload_canario(
            antes, descricao_complementar=descricao_complementar, fornecedores=fornecedores
        )

        w("")
        w(self.style.MIGRATE_HEADING(f"Payload que {'SERÁ' if executar else 'SERIA'} enviado ao PUT /produtos/{tiny_id}:"))
        w(json.dumps(payload, ensure_ascii=False, indent=2))
        w("")
        w(f"  fornecedores atuais no Tiny: {antes.get('fornecedores') or []}")
        w(f"  fornecedores no payload ...: {fornecedores}")

        if not executar:
            w("")
            w(self.style.WARNING("DRY-RUN — nenhum PUT foi feito. Rode de novo com --executar para aplicar."))
            return

        # -- PUT -------------------------------------------------------
        cliente.atualizar_produto(tiny_id, payload)
        w("")
        w(self.style.SUCCESS("PUT enviado (HTTP 204 = sucesso)."))

        # -- GET depois + diff --------------------------------------------
        depois = cliente.obter_produto(tiny_id)
        self._imprimir_diff(comparar_campos(antes, depois))

    # -- saída ----------------------------------------------------------

    def _imprimir_diff(self, linhas):
        w = self.stdout.write
        w("")
        w(self.style.MIGRATE_HEADING("Diff campo a campo (GET antes -> GET depois):"))
        inesperados = 0
        esperados_sem_mudanca = []
        for linha in linhas:
            campo = linha["campo"]
            if linha["igual"]:
                w(f"  =  {campo:<22} inalterado")
                if linha["esperado_mudar"]:
                    esperados_sem_mudanca.append(campo)
                continue
            antes_txt = _norm(linha["antes"])
            depois_txt = _norm(linha["depois"])
            if linha["esperado_mudar"]:
                w(self.style.SUCCESS(f"  ~  {campo:<22} alterado (esperado)"))
            else:
                inesperados += 1
                w(self.style.ERROR(f"  !! {campo:<22} ALTERADO — INESPERADO"))
            w(f"       antes : {antes_txt}")
            w(f"       depois: {depois_txt}")

        w("")
        if inesperados:
            w(self.style.ERROR(
                f"{inesperados} campo(s) mudaram sem ser esperado — NÃO seguir para o lote; "
                "revisar a montagem do payload e a semântica do PUT."
            ))
        else:
            w(self.style.SUCCESS("Nenhuma alteração inesperada — só descricaoComplementar/fornecedores mudaram."))
        for campo in esperados_sem_mudanca:
            w(self.style.WARNING(f"Atenção: {campo!r} era esperado mudar e ficou igual — verificar."))

    def _obter_instancia(self, slug):
        try:
            return Instancia.objects.get(slug=slug)
        except Instancia.DoesNotExist:
            raise CommandError(f"Instância com slug '{slug}' não encontrada.") from None
