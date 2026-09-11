import re

import requests

from apps.instancias.constants import Fornecedor

from .base import (
    DimensoesNormalizadas,
    FornecedorBase,
    ProdutoNormalizado,
    VariacaoNormalizada,
    parse_data,
    parse_numero_br,
    to_decimal,
)

# "ø7 x 129 mm" — diâmetro seguido do comprimento, ambos em mm. É o único
# formato de `CombinedSizes` com eixo explícito (o símbolo "ø" marca
# diâmetro sem ambiguidade). Cobre ~27% da amostra real.
_PADRAO_DIAMETRO_COMPRIMENTO = re.compile(
    r"^\s*[øØ]\s*([\d,\.]+)\s*x\s*([\d,\.]+)\s*mm", re.IGNORECASE
)

# Teto de imagens por variação enviadas ao espelho (e, adiante, ao Tiny —
# `imagens_utilizaveis` também corta em 5). Escolha nossa, não do cliente.
MAX_IMAGENS_POR_VARIACAO = 5

_SO_DIGITOS = re.compile(r"\D")


def _ncm_do_taric(valor) -> str:
    """
    Converte o campo `Taric` da Spot num NCM brasileiro — SÓ quando é seguro.

    A amostra real (3.709 SKUs) mostra que o `Taric` da Spot é uma mistura:
    ~95,5% são códigos de 8 dígitos (formato de NCM: "9608.10.00" /
    "96081000" / "9608.10.00." — só muda a pontuação), mas ~4,5% são
    códigos CN10/TARIC da UE de 9-10 dígitos ("9608109900", "4202929190")
    que NÃO são NCM e cujos 8 primeiros dígitos também não formam um NCM
    válido.

    Regra: remove tudo que não é dígito e devolve o resultado APENAS se
    sobrarem exatamente 8 dígitos. Qualquer outra coisa (9, 10, 7 dígitos,
    vazio, None) -> "" — nunca trunca, nunca adivinha. O valor cru continua
    guardado em `Variacao.atributos["taric"]` para rastreabilidade.
    """
    digitos = _SO_DIGITOS.sub("", str(valor or ""))
    return digitos if len(digitos) == 8 else ""

# Nome de foto de catálogo da Spot: "<ref>_<cor>" com sufixos opcionais
# ("-a", "-c", "-logo", "-box"...). NÃO casa de propósito com as imagens
# técnicas, cujo stem tem mais de um "_": marcação ("11110_1_1_1.png"),
# componente ("11110_105_C1.png"), localização ("11110_105_C1_L1.png").
_PADRAO_NOME_FOTO = re.compile(r"^\d+_[A-Za-z0-9]+(?:-[A-Za-z0-9]+)*$")
_EXTENSOES_FOTO = (".jpg", ".jpeg", ".png", ".webp")
# Sufixos que NÃO são a foto limpa do produto: mockup com logo, foto da
# caixa / saco / pouch, foto de ambiente.
_SUFIXOS_NAO_LIMPOS = frozenset({"logo", "box", "pouch", "bag", "amb"})


def _nomes_de_imagem_spot(opcional: dict, produto_bruto: dict) -> list[str]:
    """Nomes de arquivo candidatos, na ordem em que a Spot os entrega."""
    bruto = opcional.get("AllImageList") or produto_bruto.get("AllImageList") or ""
    nomes = [n.strip() for n in bruto.split(",") if n and n.strip()]
    for campo in ("OptionalImage1", "OptionalImage2"):
        valor = opcional.get(campo) or produto_bruto.get(campo) or ""
        nomes.extend(n.strip() for n in valor.split(",") if n and n.strip())
    if not nomes:
        principal = (opcional.get("MainImage") or produto_bruto.get("MainImage") or "").strip()
        nomes = [principal] if principal else []
    return nomes


def _prioridade_imagem_spot(nome: str, referencia: str, cor: str) -> int:
    """
    Chave de ordenação (menor = mais relevante para ESTA variação). Só é
    chamada depois de o nome passar por `_PADRAO_NOME_FOTO`.
    """
    stem = nome.rsplit(".", 1)[0]
    ref, _, resto = stem.partition("_")
    partes = resto.split("-")
    cor_arquivo = partes[0]
    sufixos = [s for s in partes[1:] if s]
    mesma_ref = bool(referencia) and ref == referencia
    mesma_cor = bool(cor) and cor_arquivo == cor
    limpa = not any(s in _SUFIXOS_NAO_LIMPOS for s in sufixos)
    tem_sufixo = bool(sufixos)
    if not mesma_ref:
        return 5
    if mesma_cor and not tem_sufixo:
        return 0
    if mesma_cor and limpa:
        return 1
    if limpa and not tem_sufixo:
        return 2
    if mesma_cor:
        return 3
    return 4


def imagens_spot_da_variacao(opcional: dict, produto_bruto: dict, url_base: str) -> list[str]:
    """
    URLs absolutas de imagem de uma variação Spot, a partir do nome de
    arquivo (`AllImageList`, ou `MainImage` como fallback) + `url_base`
    (`ConfiguracaoFornecedor.url_base_imagens`).

    - fotos limpas da cor da variação primeiro; mockup com logo / foto de
      caixa por último; nomes de campo técnico nunca entram;
    - dedupe por URL, no máximo `MAX_IMAGENS_POR_VARIACAO`;
    - `url_base` vazio -> lista vazia (comportamento atual preservado).

    Pura: usada tanto por `SpotFornecedor.normalizar` quanto pelo comando
    `backfill_imagens_spot` (que a alimenta com o `payload_bruto` salvo).
    """
    if not url_base:
        return []
    referencia = str(
        opcional.get("ProdReference") or produto_bruto.get("ProdReference") or ""
    ).strip()
    cor = str(opcional.get("ColorCode") or "").strip()

    candidatos = [
        nome
        for nome in _nomes_de_imagem_spot(opcional, produto_bruto)
        if nome.lower().endswith(_EXTENSOES_FOTO)
        and _PADRAO_NOME_FOTO.match(nome.rsplit(".", 1)[0])
    ]
    # sort estável: dentro da mesma prioridade, mantém a ordem do fornecedor.
    candidatos.sort(key=lambda nome: _prioridade_imagem_spot(nome, referencia, cor))

    prefixo = url_base.rstrip("/") + "/"
    urls: list[str] = []
    for nome in candidatos:
        url = prefixo + nome.lstrip("/")
        if url not in urls:
            urls.append(url)
    return urls[:MAX_IMAGENS_POR_VARIACAO]


class SpotFornecedor(FornecedorBase):
    """
    A Spot não devolve tudo numa chamada: `products` é o produto-base (sem
    SKU), `optionalsComplete` é o nível de SKU com preço, e `stocks` traz a
    quantidade por SKU. Confirmado na amostra real: o join entre
    optionalsComplete e stocks por Sku é 1:1 sem órfãos, e o join entre
    optionalsComplete e products por ProdReference também — mesmo assim,
    usamos WebSku como fallback do lado do estoque, exatamente como pedido
    ("o join é por Sku e WebSku"), para o caso de algum SKU só bater por
    WebSku.

    NCM: o único campo fiscal da Spot é o `Taric`. A amostra real mostra
    que ~95,5% dos SKUs trazem nele um código de 8 dígitos (formato de NCM,
    só varia a pontuação) e ~4,5% trazem código CN10/TARIC da UE de 9-10
    dígitos, que não é NCM. `_ncm_do_taric` aproveita só os de 8 dígitos
    (nunca trunca os demais) -> `Variacao.ncm`. O `Taric` cru fica sempre
    em `atributos["taric"]`, inclusive nos casos sem NCM, para
    rastreabilidade e para cobrar o dado do fornecedor depois.

    Imagens: a API devolve só o nome do arquivo (ex.: "11112_115.jpg"), sem
    host. A URL é montada com `configuracao["url_base_imagens"]`
    (ConfiguracaoFornecedor) — enquanto vazio, a variação fica sem imagem.
    A fonte é `AllImageList` (lista separada por vírgula, no nível do
    `optionalsComplete`, com o mesmo conteúdo para todas as cores do
    produto); se vier vazia, cai para `MainImage`. A foto limpa da cor da
    variação (`<ref>_<cor>.jpg`, sem sufixo) vem primeiro; mockups com logo
    e fotos de caixa/saco (`-logo`, `-box`, `-pouch`, ...) vão para o fim.
    Campos técnicos (`Area*Image`, `Component*Image`, `Location*Image`) NÃO
    entram — não são lidos e o padrão de nome de arquivo os exclui. Máximo
    de `MAX_IMAGENS_POR_VARIACAO` (5) por variação. Ver
    `imagens_spot_da_variacao`.

    Dimensões/peso (passo 6): `CombinedSizes` é uma string livre e
    inconsistente ("55 x 22 x 12 mm", "ø7 x 129 mm", "250 x 80 mm",
    "330 x 480 x 180 mm | Placa: 50 x 20 mm", "Tamanhos: P, M, G..."). Só
    mapeamos o padrão "ø<N> x <N> mm" (diâmetro + comprimento), porque é o
    único com eixo explicitamente rotulado — os demais formatos (3 números
    soltos, 2 números sem diâmetro) exigiriam adivinhar qual número é
    largura/altura/comprimento, o que não fazemos. `Weight` foi descartado
    de propósito: 295 dos 1247 produtos da amostra real têm `Weight=1`
    (quase 24%, um valor repetido demais pra ser medição real) e pelo
    menos um caso confirmado (mochila com Weight=1 mas caixa de 10
    unidades pesando 8,92kg) mostra que é um placeholder de "não medido",
    não peso de verdade — mandar isso pro Tiny seria pior que não mandar
    nada.
    """

    codigo = Fornecedor.SPOT
    BASE_URL = "https://ws.spotgifts.com.br/api/v1SSL"
    TIMEOUT = 120
    FORMATO_DATA = "%m/%d/%Y %H:%M:%S"

    def buscar(self, credenciais):
        token = self._autenticar(credenciais["access_key"])
        try:
            products = self._get("products", token)["Products"]
            optionals = self._get("optionalsComplete", token)["OptionalsComplete"]
            stocks = self._get("stocks", token)["Stocks"]
        finally:
            self._encerrar_sessao(token)
        return {"products": products, "optionals": optionals, "stocks": stocks}

    def _autenticar(self, access_key):
        resposta = requests.get(
            f"{self.BASE_URL}/AuthenticateClient",
            params={"accessKey": access_key},
            timeout=self.TIMEOUT,
        )
        resposta.raise_for_status()
        dados = resposta.json()
        if dados.get("ErrorCode"):
            raise ValueError(f"spot: falha na autenticação - {dados.get('ErrorMessage')}")
        token = dados.get("Token")
        if not token:
            raise ValueError("spot: autenticação sem Token na resposta.")
        return token

    def _get(self, caminho, token):
        resposta = requests.get(
            f"{self.BASE_URL}/{caminho}",
            params={"token": token, "lang": "PT"},
            timeout=self.TIMEOUT,
        )
        resposta.raise_for_status()
        return resposta.json()

    def _encerrar_sessao(self, token):
        requests.get(f"{self.BASE_URL}/CloseSession", params={"token": token}, timeout=self.TIMEOUT)

    def normalizar(self, payload_bruto):
        url_base_imagens = self.configuracao.get("url_base_imagens", "")

        produtos_por_referencia = {p["ProdReference"]: p for p in payload_bruto["products"]}
        estoque_por_sku = {s["Sku"]: s.get("Quantity", 0) for s in payload_bruto["stocks"]}
        estoque_por_websku = {s["WebSku"]: s.get("Quantity", 0) for s in payload_bruto["stocks"]}

        produtos_normalizados = {}
        for opcional in payload_bruto["optionals"]:
            referencia = opcional["ProdReference"]
            produto_bruto = produtos_por_referencia.get(referencia, {})
            produto = produtos_normalizados.get(referencia)
            if produto is None:
                produto = ProdutoNormalizado(
                    codigo_pai=referencia,
                    nome=produto_bruto.get("Name", ""),
                    descricao=produto_bruto.get("Description", ""),
                    categorias=[c for c in (produto_bruto.get("Type"), produto_bruto.get("SubType")) if c],
                    atualizado_em_fornecedor=parse_data(produto_bruto.get("UpdateDate"), self.FORMATO_DATA),
                    payload_bruto=produto_bruto,
                )
                produtos_normalizados[referencia] = produto

            sku = opcional["Sku"]
            estoque = estoque_por_sku.get(sku)
            if estoque is None:
                estoque = estoque_por_websku.get(opcional.get("WebSku"), 0)

            imagens = imagens_spot_da_variacao(opcional, produto_bruto, url_base_imagens)

            taric = opcional.get("Taric") or produto_bruto.get("Taric") or ""
            produto.variacoes.append(
                VariacaoNormalizada(
                    sku=sku,
                    nome=produto_bruto.get("Name", ""),
                    # NCM só quando o Taric tem 8 dígitos (ver _ncm_do_taric);
                    # o Taric cru fica em `atributos` para os demais casos.
                    ncm=_ncm_do_taric(taric),
                    preco=to_decimal(opcional.get("Price1")),
                    estoque=int(estoque or 0),
                    cor=opcional.get("ColorDesc1", ""),
                    imagens=imagens,
                    atributos={"taric": taric} if taric else {},
                    dimensoes=_dimensoes_do_produto(produto_bruto),
                    payload_bruto=opcional,
                )
            )
        return list(produtos_normalizados.values())


def _dimensoes_do_produto(produto_bruto) -> DimensoesNormalizadas:
    match = _PADRAO_DIAMETRO_COMPRIMENTO.match(produto_bruto.get("CombinedSizes") or "")
    if not match:
        return DimensoesNormalizadas()
    diametro_mm = parse_numero_br(match.group(1))
    comprimento_mm = parse_numero_br(match.group(2))
    return DimensoesNormalizadas(
        diametro=(diametro_mm / 10) if diametro_mm else None,
        comprimento=(comprimento_mm / 10) if comprimento_mm else None,
    )
