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


class XbzFornecedor(FornecedorBase):
    """
    A xbz devolve o catálogo inteiro numa única chamada, como uma lista
    plana — uma linha por cor. Não existe endpoint de "produto pai": o
    agrupamento é feito aqui, por CodigoAmigavel. Cada linha vira uma
    Variacao identificada por CodigoXbz.

    Limite de 24 chamadas/dia compartilhado com o cliente final — por isso
    buscar() faz exatamente UMA chamada, sem paginação e sem retry
    automático. Repetir a chamada é decisão de quem chama este cliente
    (ver checagem em management/commands/importar_fornecedor.py).
    """

    codigo = Fornecedor.XBZ
    URL = "https://api.minhaxbz.com.br:5001/api/clientes/GetListaDeProdutos"
    TIMEOUT = 120

    def buscar(self, credenciais):
        resposta = requests.get(
            self.URL,
            params={"cnpj": credenciais["cnpj"], "token": credenciais["token"]},
            timeout=self.TIMEOUT,
        )
        if resposta.status_code == 401:
            raise ValueError("xbz: 401 - credencial inválida (cnpj/token).")
        if resposta.status_code == 403:
            raise ValueError("xbz: 403 - limite diário de chamadas atingido.")
        if resposta.status_code == 500:
            raise ValueError("xbz: 500 - erro interno do fornecedor.")
        resposta.raise_for_status()
        return resposta.json()

    def normalizar(self, payload_bruto):
        produtos = {}
        for linha in payload_bruto:
            codigo_pai = linha["CodigoAmigavel"]
            produto = produtos.get(codigo_pai)
            if produto is None:
                # Nome/descrição do produto-pai vêm da primeira linha do
                # grupo — a xbz não manda um nome "genérico" à parte, e o
                # nome muda ligeiramente por cor (ex.: "...AZUL" vs
                # "...BOLINHAS"). É uma escolha documentada, não um dado
                # que a API garanta ser estável entre cores.
                imagem = linha.get("ImageLink")
                produto = ProdutoNormalizado(
                    codigo_pai=codigo_pai,
                    nome=linha.get("Nome", "").strip(),
                    descricao=linha.get("Descricao", ""),
                    imagens=[imagem] if imagem else [],
                    payload_bruto={"linhas": []},
                )
                produtos[codigo_pai] = produto
            produto.payload_bruto["linhas"].append(linha)

            imagem_variacao = linha.get("ImageLink")
            produto.variacoes.append(
                VariacaoNormalizada(
                    sku=linha["CodigoXbz"],
                    nome=linha.get("Nome", "").strip(),
                    ncm=linha.get("Ncm", ""),
                    preco=to_decimal(linha.get("PrecoVenda")),
                    estoque=int(linha.get("QuantidadeDisponivel") or 0),
                    cor=linha.get("CorWebPrincipal", ""),
                    imagens=[imagem_variacao] if imagem_variacao else [],
                    atributos={
                        "codigo_composto": linha.get("CodigoComposto", ""),
                        "cor_secundaria": linha.get("CorWebSecundaria", ""),
                    },
                    dimensoes=_dimensoes_da_linha(linha),
                    payload_bruto=linha,
                )
            )
        return list(produtos.values())


def _dimensoes_da_linha(linha) -> DimensoesNormalizadas:
    """
    Confirmado contra samples/xbz/: Altura/Largura/Profundidade já vêm em
    CENTÍMETROS (ex.: uma garrafa térmica de 350ml com Altura=20.0 — só faz
    sentido em cm) — não precisam de conversão. Peso vem em GRAMAS (ex.:
    a mesma garrafa com Peso=274.0 — 274kg seria absurdo) — convertido para
    kg (÷1000) porque é essa a unidade que o Tiny usa. "Profundidade" da
    xbz mapeia para "comprimento" do Tiny (mesmo conceito: a 3ª dimensão
    ortogonal, sem um par exato "profundidade" no schema do Tiny).
    """
    # "or None" trata 0.0 como "não informado" — muitos registros da xbz
    # vêm com Altura/Largura/Profundidade zeradas quando não medidas, e
    # zero não é uma dimensão real para nenhum produto físico.
    peso_g = parse_numero_br(linha.get("Peso"))
    return DimensoesNormalizadas(
        largura=parse_numero_br(linha.get("Largura")) or None,
        altura=parse_numero_br(linha.get("Altura")) or None,
        comprimento=parse_numero_br(linha.get("Profundidade")) or None,
        peso_liquido=(peso_g / 1000) if peso_g else None,
    )
