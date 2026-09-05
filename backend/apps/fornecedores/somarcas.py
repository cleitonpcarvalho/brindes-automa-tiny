import base64
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

# "32x14,5x5,5 mm (AxLxP)" — único formato de dimensão que a Só Marcas
# rotula de forma inequívoca (eixo + unidade explícitos). Confirmado
# contra a amostra real: bate em 100% dos 1278 registros capturados.
_PADRAO_DIMENSOES_EMBALAGEM = re.compile(
    r"^\s*([\d,\.]+)\s*x\s*([\d,\.]+)\s*x\s*([\d,\.]+)\s*mm\s*\(AxLxP\)\s*$", re.IGNORECASE
)
# "147 g" — também bate em 100% da amostra.
_PADRAO_PESO_EMBALAGEM = re.compile(r"^\s*([\d,\.]+)\s*(g|kg)\s*$", re.IGNORECASE)


class SomarcasFornecedor(FornecedorBase):
    """
    Confirmado contra a amostra real (samples/somarcas/), não contra a
    especificação original: a Só Marcas não tem um campo de "produto-pai".
    Cada `codigo` já é uma variação de cor — exatamente como o cliente
    descreveu. O campo `produtos_similares` até lista códigos
    relacionados, mas é uma string livre formatada para exibição no site
    (ex.: ";AS-00611|#333b3b|3459|...|GARRAFA...;AS-00610|#FFFFFF|..."), não
    uma chave normalizada — não a usamos para agrupar, para não inventar
    uma relação de produto-pai que a API não afirma de forma confiável.

    Por isso, aqui, codigo_pai == sku: cada produto normalizado tem
    exatamente uma variação.
    """

    codigo = Fornecedor.SOMARCAS
    URL = "https://www.somarcas.com.br/api-lista-preco-revenda-v1-0-0.php"
    TIMEOUT = 120
    FORMATO_DATA = "%Y-%m-%d %H:%M:%S"

    def buscar(self, credenciais):
        token = base64.b64encode(
            f"{credenciais['usuario']}:{credenciais['senha']}".encode("utf-8")
        ).decode("ascii")
        resposta = requests.get(
            self.URL,
            headers={"Authorization": f"Basic {token}"},
            params={"estado": credenciais.get("estado", "")},
            timeout=self.TIMEOUT,
        )
        resposta.raise_for_status()
        return resposta.json()

    def normalizar(self, payload_bruto):
        produtos_normalizados = []
        for item in payload_bruto:
            codigo = item["codigo"]
            categorias = [c for c in (item.get("matriz_de_categorias") or "").split("|") if c]
            fotos_adicionais = [f for f in (item.get("matriz_de_fotos_adicionais") or "").split("|") if f]
            imagem_principal = item.get("url_foto")
            imagens = ([imagem_principal] if imagem_principal else []) + fotos_adicionais
            atualizado_em = parse_data(item.get("data_ultima_atualizacao"), self.FORMATO_DATA)

            variacao = VariacaoNormalizada(
                sku=codigo,
                nome=item.get("titulo", ""),
                ncm=item.get("ncm", ""),
                # Regra do cliente: "o preço gravado é o preço do fornecedor, sem
                # margem". A Só Marcas devolve 4 combinações (com/sem gravação x
                # com/sem impostos); no passo 3 este código assumia
                # sem-gravação/sem-impostos. CONFIRMADO PELO CLIENTE em
                # 2026-09-04 (passo 5): o campo correto é "com gravação" e "com
                # impostos" — preco_com_gravacao_com_impostos.
                preco=to_decimal(item.get("preco_com_gravacao_com_impostos")),
                estoque=int(item.get("estoque") or 0),
                imagens=imagens,
                atributos={
                    "tipo_gravacao": item.get("tipo_gravacao", ""),
                    "dimensoes_do_produto": item.get("dimensoes_do_produto", ""),
                    "embalagem_do_produto": item.get("embalagem_do_produto", ""),
                    "garantia_do_produto": item.get("garantia_do_produto", ""),
                    "ipi": item.get("ipi"),
                    "quantidade_minima_sugerida": item.get("quantidade_minima_sugerida"),
                },
                dimensoes=_dimensoes_do_item(item),
                payload_bruto=item,
            )
            produtos_normalizados.append(
                ProdutoNormalizado(
                    codigo_pai=codigo,
                    nome=item.get("titulo", ""),
                    descricao=item.get("descricao", ""),
                    categorias=categorias,
                    imagens=imagens,
                    atualizado_em_fornecedor=atualizado_em,
                    payload_bruto=item,
                    variacoes=[variacao],
                )
            )
        return produtos_normalizados


def _dimensoes_do_item(item) -> DimensoesNormalizadas:
    """
    A Só Marcas expõe dimensão/peso só como texto livre. Só mapeamos o que
    tem eixo e unidade explícitos:
      - `dimensoes_da_embalagem` no formato "AxLxP mm" — SEMPRE rotulado
        (confirmado: 1278/1278 na amostra) — convertido de mm para cm (÷10)
        e mapeado como peso BRUTO (é dimensão da embalagem, não do produto
        isolado).
      - `peso_da_embalagem` no formato "N g" — idem, convertido para kg
        (÷1000), mapeado como peso bruto.
    `dimensoes_do_produto` (ex.: "24,5x7cm", "21x6,5Øcm", "32x14,5x5,5cm")
    é DELIBERADAMENTE deixado de fora: não tem eixos rotulados, varia entre
    2 e 3 números por produto, e às vezes tem prefixos como "Aberto:" —
    mapear isso para largura/altura/comprimento seria adivinhar qual número
    é qual eixo, o que não temos como confirmar.
    """
    dimensoes = DimensoesNormalizadas()

    bruto_embalagem = _match_dimensoes_embalagem(item.get("dimensoes_da_embalagem"))
    if bruto_embalagem:
        altura_mm, largura_mm, profundidade_mm = bruto_embalagem
        dimensoes.altura = altura_mm / 10
        dimensoes.largura = largura_mm / 10
        dimensoes.comprimento = profundidade_mm / 10

    peso_bruto = _match_peso_embalagem(item.get("peso_da_embalagem"))
    if peso_bruto is not None:
        dimensoes.peso_bruto = peso_bruto

    return dimensoes


def _match_dimensoes_embalagem(valor):
    if not valor:
        return None
    m = _PADRAO_DIMENSOES_EMBALAGEM.match(valor.strip())
    if not m:
        return None
    numeros = [parse_numero_br(g) for g in m.groups()]
    if any(n is None or n == 0 for n in numeros):
        return None  # "0x0x0 mm (AxLxP)" = não informado, não uma medida real
    return numeros


def _match_peso_embalagem(valor):
    if not valor:
        return None
    m = _PADRAO_PESO_EMBALAGEM.match(valor.strip())
    if not m:
        return None
    numero = parse_numero_br(m.group(1))
    if not numero:
        return None
    unidade = m.group(2).lower()
    return numero / 1000 if unidade == "g" else numero
