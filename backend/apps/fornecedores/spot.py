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

    Duas pendências abertas com o fornecedor, deixadas preparadas e NÃO
    resolvidas por conta própria:
      - NCM: o único campo fiscal disponível é o Taric, não confirmado
        como equivalente ao NCM brasileiro. `ncm` fica sempre vazio para
        este fornecedor (o Taric vai só em `atributos`, para não se perder).
      - Imagens: vêm só como nome de arquivo (ex.: "11112_115.jpg"), sem
        host nem caminho. Só são montadas em URL se
        `configuracao["url_base_imagens"]` estiver preenchido (ver
        ConfiguracaoFornecedor); enquanto vazio, a variação fica sem imagem.

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

            nome_arquivo_imagem = opcional.get("MainImage") or produto_bruto.get("MainImage")
            imagens = self._montar_imagens(nome_arquivo_imagem, url_base_imagens)

            taric = produto_bruto.get("Taric", "")
            produto.variacoes.append(
                VariacaoNormalizada(
                    sku=sku,
                    nome=produto_bruto.get("Name", ""),
                    ncm="",  # pendente — ver docstring da classe
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

    @staticmethod
    def _montar_imagens(nome_arquivo, url_base):
        if not nome_arquivo or not url_base:
            return []
        return [url_base.rstrip("/") + "/" + nome_arquivo.lstrip("/")]


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
