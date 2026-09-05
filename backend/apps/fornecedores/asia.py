import requests

from apps.instancias.constants import Fornecedor

from .base import (
    DimensoesNormalizadas,
    FornecedorBase,
    ProdutoNormalizado,
    VariacaoNormalizada,
    parse_numero_br,
    to_decimal,
)


class AsiaFornecedor(FornecedorBase):
    """
    A asia já entrega o produto-pai com o array `variacoes` aninhado — não
    precisa de agrupamento manual como a xbz. O NCM só existe dentro da
    variação, nunca no produto-pai.

    Atenção: o código do produto-pai às vezes termina em "P" (ex.:
    "MC511P") enquanto a variação correspondente usa o mesmo código sem o
    "P" (ex.: "MC511") — são campos distintos (`referencia` do produto x
    `referencia` da variação) e NUNCA devem ser derivados um do outro por
    manipulação de string. Sempre usar o valor literal que a API mandou em
    cada nível.
    """

    codigo = Fornecedor.ASIA
    URL = "https://api.asiaimport.com.br/"
    TIMEOUT = 120
    POR_PAGINA = 100

    def buscar(self, credenciais):
        pagina = 1
        total_paginas = 1
        produtos_brutos = []
        while pagina <= total_paginas:
            resposta = requests.post(
                self.URL,
                files={
                    "api_key": (None, credenciais["api_key"]),
                    "secret_key": (None, credenciais["secret_key"]),
                    "funcao": (None, "listarProdutos2"),
                    "pagina": (None, str(pagina)),
                    "por_pagina": (None, str(self.POR_PAGINA)),
                },
                timeout=self.TIMEOUT,
            )
            resposta.raise_for_status()
            dados = resposta.json()
            total_paginas = dados.get("total_paginas") or pagina
            produtos_brutos.extend(dados.get("produtos", []))
            pagina += 1
        return produtos_brutos

    def normalizar(self, payload_bruto):
        produtos_normalizados = []
        for produto_bruto in payload_bruto:
            # Dimensões/peso só existem no nível do produto-pai (nunca por
            # variação) — cada variação herda a mesma medida do pai, porque
            # a asia não diferencia isso por cor.
            dimensoes = _dimensoes_do_produto(produto_bruto)

            variacoes = [
                VariacaoNormalizada(
                    sku=variacao_bruta["referencia"],
                    nome=variacao_bruta.get("nome", produto_bruto.get("nome", "")),
                    ncm=variacao_bruta.get("ncm", ""),
                    preco=to_decimal(variacao_bruta.get("preco")),
                    estoque=int(variacao_bruta.get("qtd_estoque") or 0),
                    cor=self._extrair_cor(variacao_bruta),
                    imagens=[variacao_bruta["imagem"]] if variacao_bruta.get("imagem") else [],
                    atributos=variacao_bruta.get("atributos") or {},
                    dimensoes=dimensoes,
                    payload_bruto=variacao_bruta,
                )
                for variacao_bruta in produto_bruto.get("variacoes", [])
            ]

            categorias = produto_bruto.get("categorias") or {}
            imagem_produto = produto_bruto.get("imagem")
            galeria = produto_bruto.get("galeria") or []
            imagens = ([imagem_produto] if imagem_produto else []) + list(galeria)

            produtos_normalizados.append(
                ProdutoNormalizado(
                    codigo_pai=produto_bruto["referencia"],
                    nome=produto_bruto.get("nome", ""),
                    descricao=produto_bruto.get("descricao", ""),
                    categorias=list(categorias.values()) if isinstance(categorias, dict) else list(categorias),
                    imagens=imagens,
                    atributos=produto_bruto.get("propriedades") or {},
                    payload_bruto=produto_bruto,
                    variacoes=variacoes,
                )
            )
        return produtos_normalizados

    @staticmethod
    def _extrair_cor(variacao_bruta):
        cor = (variacao_bruta.get("atributos") or {}).get("cor")
        if isinstance(cor, dict):
            return cor.get("value", "")
        return cor or ""


def _dimensoes_do_produto(produto_bruto) -> DimensoesNormalizadas:
    """
    Confirmado contra samples/asia/: `altura`/`largura`/`comprimento` já
    vêm em CENTÍMETROS (mesma ordem de grandeza da string livre em
    `propriedades["dimensao-produto"]`, que traz o sufixo "cm" explícito) —
    sem conversão. `peso` já vem em QUILOGRAMAS (bate exatamente com
    `propriedades["peso-do-produto"]`, ex.: peso=0.868 == "0,868kg") — sem
    conversão. A asia não informa diâmetro nem peso bruto separado.
    """
    peso = parse_numero_br(produto_bruto.get("peso"))
    return DimensoesNormalizadas(
        largura=parse_numero_br(produto_bruto.get("largura")) or None,
        altura=parse_numero_br(produto_bruto.get("altura")) or None,
        comprimento=parse_numero_br(produto_bruto.get("comprimento")) or None,
        peso_liquido=peso or None,
    )
