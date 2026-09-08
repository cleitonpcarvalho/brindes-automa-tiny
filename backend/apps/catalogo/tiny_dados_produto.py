"""
Regra DEFINITIVA dos dados de um produto no Tiny (confirmada pelo cliente em
2026-09-08) e a montagem do payload de ATUALIZAÇÃO (`PUT /produtos/{id}`).

  1. `descricaoComplementar` = `Produto.descricao` do espelho;
  2. `precos.precoCusto`     = `Variacao.preco` (valor do fornecedor = CUSTO);
  3. `precos.preco`          = 0  (venda SEMPRE zerada);
  4. `precos.precoPromocional` = 0;
  5. `fornecedores`          = fornecedor Tiny configurado do par, PRESERVANDO
                               os fornecedores já existentes (nunca duplica).

O payload é DEFENSIVO: reenvia todo campo GRAVÁVEL que o GET devolveu, para
sobreviver tanto a um PUT parcial quanto a uma substituição total (semântica
do v3 não documentada — ver canário BL026-BG, já validado em produção).

Nunca entram no PUT (read-only / endpoint próprio / fora do
`AtualizarProdutoRequestModel`): `id`, `situacao`, `tipo`, `tipoVariacao`,
`produtoPai`, `variacoes`, `kit`, `producao`, `codigoListaServicos`,
`anexos` (imagens: `PUT /produtos/{id}/anexos`), `precos.precoCustoMedio`,
`estoque.quantidade` (saldo: `POST /estoque/{id}`),
`dimensoes.quantidadeVolumes`, `dimensoes.embalagem`.

Este módulo NÃO fala com o Tiny nem com o banco — só transforma dicts. Quem
chama (o command de backfill / o canário / a sync de custo) faz o GET, o PUT
e a persistência do marcador.
"""

import json

# Campos escalares graváveis do topo de AtualizarProdutoRequestModel.
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

# Campos destacados no diff pós-PUT (canário / --executar).
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
# Só estes PODEM mudar após o PUT — qualquer outra alteração é inesperada.
CAMPOS_ESPERADOS_MUDAR = ("descricaoComplementar", "fornecedores", "precos")


class DadosProdutoError(RuntimeError):
    """Falha ao preparar os dados de UM produto (não deve parar o lote)."""


def montar_fornecedores(atuais, *, tiny_fornecedor_id, codigo_produto_no_fornecedor):
    """
    Preserva TODOS os fornecedores atuais e acrescenta o nosso apenas se ele
    ainda não estiver na lista (nunca duplica). O nosso entra `padrao=true`
    só quando nenhum outro já é padrão; senão `padrao=false`. Lista vazia ->
    o nosso entra `padrao=true`.

    Cada item vira o formato do REQUEST (`FornecedorProdutoRequestModel`:
    id, codigoProdutoNoFornecedor, padrao). Um fornecedor existente sem `id`
    utilizável levanta `DadosProdutoError` — não dá para round-tripá-lo e não
    se pode removê-lo silenciosamente.
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
            raise DadosProdutoError(
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


def montar_payload_atualizacao(detalhe, *, variacao, tiny_fornecedor_id):
    """
    Corpo do `PUT /produtos/{id}` para UMA variação já cadastrada, a partir
    do GET (`detalhe`). Reenvia todo campo gravável presente e SOBREPÕE só o
    que a regra definitiva manda:
      - descricaoComplementar <- variacao.produto.descricao
      - precos                <- {preco: 0, precoPromocional: 0, precoCusto: Variacao.preco}
      - fornecedores          <- merge com os existentes (montar_fornecedores)

    Confere o SKU (o `detalhe` tem que ser o do produto certo) — sem fuzzy.
    """
    sku_no_tiny = str(detalhe.get("sku") or "")
    if sku_no_tiny != variacao.sku:
        raise DadosProdutoError(
            f"SKU do GET ({sku_no_tiny!r}) != SKU do espelho ({variacao.sku!r}) — abortado."
        )

    payload = {}
    for chave in CAMPOS_TOPO_GRAVAVEIS:
        if chave in detalhe and detalhe[chave] is not None:
            payload[chave] = detalhe[chave]

    # `origem`: o GET devolve string ("0"); o schema pede integer.
    origem = detalhe.get("origem")
    if origem is not None and str(origem).strip() != "":
        payload["origem"] = int(origem)

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

    # --- regra definitiva: os únicos deltas intencionais ---
    payload["descricaoComplementar"] = (variacao.produto.descricao or "") if variacao.produto_id else ""
    payload["precos"] = {
        "preco": float(variacao.preco_venda_tiny),          # 0
        "precoPromocional": 0,
        "precoCusto": float(variacao.preco_custo_tiny),      # = Variacao.preco
    }
    payload["fornecedores"] = montar_fornecedores(
        detalhe.get("fornecedores"),
        tiny_fornecedor_id=tiny_fornecedor_id,
        codigo_produto_no_fornecedor=variacao.sku,
    )
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
