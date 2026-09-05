from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase

from apps.fornecedores.asia import AsiaFornecedor

from .fixtures import ASIA_META_PAGINACAO, ASIA_PRODUTO_MC511P


class NormalizarAsiaTests(TestCase):
    """
    Usa um recorte real de samples/asia/ — produto "MC511P" com uma única
    variação "MC511" — para cobrir o caso documentado do sufixo "P": o
    código do produto-pai (referencia) e o da variação nunca devem ser
    derivados um do outro por manipulação de string.
    """

    def test_produto_com_sufixo_p_e_variacao_sem_sufixo_sao_preservados_literalmente(self):
        produtos = AsiaFornecedor().normalizar([ASIA_PRODUTO_MC511P])
        self.assertEqual(len(produtos), 1)
        produto = produtos[0]
        self.assertEqual(produto.codigo_pai, "MC511P")
        self.assertEqual(len(produto.variacoes), 1)
        self.assertEqual(produto.variacoes[0].sku, "MC511")
        # confirma que ambos vieram do campo `referencia` de cada nível,
        # lido literalmente — não de uma derivação por slice/strip de string
        # (que aqui até "funcionaria" por coincidência, mas não é garantia
        # da API; ver AsiaFornecedor.normalizar)
        self.assertEqual(produto.codigo_pai, ASIA_PRODUTO_MC511P["referencia"])
        self.assertEqual(
            produto.variacoes[0].sku, ASIA_PRODUTO_MC511P["variacoes"][0]["referencia"]
        )

    def test_dimensoes_e_peso_do_produto_pai_sao_herdadas_pela_variacao_sem_conversao(self):
        """Confirmado contra a amostra real: altura/largura/comprimento já vêm em cm, peso já em kg."""
        produtos = AsiaFornecedor().normalizar([ASIA_PRODUTO_MC511P])
        dim = produtos[0].variacoes[0].dimensoes
        self.assertEqual(dim.altura, 45)
        self.assertEqual(dim.largura, 38)
        self.assertEqual(dim.comprimento, 39)
        self.assertEqual(dim.peso_liquido, 0.868)

    def test_ncm_so_existe_dentro_da_variacao(self):
        produtos = AsiaFornecedor().normalizar([ASIA_PRODUTO_MC511P])
        self.assertEqual(produtos[0].variacoes[0].ncm, "4202.92.00")
        # ProdutoNormalizado (produto-pai) não tem campo estruturado de NCM —
        # o único NCM confiável na asia é o da variação.
        self.assertFalse(hasattr(produtos[0], "ncm"))

    def test_cor_e_extraida_do_dict_de_atributos(self):
        produtos = AsiaFornecedor().normalizar([ASIA_PRODUTO_MC511P])
        self.assertEqual(produtos[0].variacoes[0].cor, "Cinza")

    def test_preco_string_e_convertido_para_decimal(self):
        produtos = AsiaFornecedor().normalizar([ASIA_PRODUTO_MC511P])
        self.assertEqual(produtos[0].variacoes[0].preco, Decimal("89"))


class BuscarAsiaPaginacaoTests(TestCase):
    """
    A asia pagina no máximo 100 produtos por página e devolve
    `total_paginas` na própria resposta (confirmado em
    samples/asia/produtos_pagina1_...json: total_produtos=475,
    total_paginas=5 com por_pagina=100). buscar() precisa seguir até a
    última página, sem se limitar à primeira.
    """

    @patch("apps.fornecedores.asia.requests.post")
    def test_buscar_percorre_todas_as_paginas_informadas_pela_api(self, mock_post):
        pagina_1 = {**ASIA_META_PAGINACAO, "pagina": 1, "produtos": [{"referencia": "A1"}]}
        pagina_2 = {**ASIA_META_PAGINACAO, "pagina": 2, "produtos": [{"referencia": "A2"}]}
        pagina_3 = {**ASIA_META_PAGINACAO, "pagina": 3, "produtos": [{"referencia": "A3"}]}

        def resposta_falsa(dados):
            class Resposta:
                def raise_for_status(self):
                    return None

                def json(self):
                    return dados

            return Resposta()

        # a asia real tem 5 páginas; aqui simulamos só 3 para o teste ficar
        # rápido, mas com total_paginas=3 explícito na 1ª resposta
        pagina_1["total_paginas"] = 3
        pagina_2["total_paginas"] = 3
        pagina_3["total_paginas"] = 3

        mock_post.side_effect = [
            resposta_falsa(pagina_1),
            resposta_falsa(pagina_2),
            resposta_falsa(pagina_3),
        ]

        produtos = AsiaFornecedor().buscar({"api_key": "x", "secret_key": "y"})

        self.assertEqual(mock_post.call_count, 3)
        self.assertEqual([p["referencia"] for p in produtos], ["A1", "A2", "A3"])

    @patch("apps.fornecedores.asia.requests.post")
    def test_buscar_para_na_pagina_informada_mesmo_se_total_produtos_sugerir_mais(self, mock_post):
        # total_produtos=475 com por_pagina=100 sugeriria 5 páginas — o
        # critério de parada é sempre total_paginas, nunca um cálculo feito
        # aqui a partir de total_produtos/por_pagina.
        unica_pagina = {
            "pagina": 1,
            "total_paginas": 1,
            "por_pagina": 100,
            "total_produtos": 475,
            "produtos": [{"referencia": "UNICO"}],
        }

        class Resposta:
            def raise_for_status(self):
                return None

            def json(self):
                return unica_pagina

        mock_post.return_value = Resposta()

        produtos = AsiaFornecedor().buscar({"api_key": "x", "secret_key": "y"})

        self.assertEqual(mock_post.call_count, 1)
        self.assertEqual([p["referencia"] for p in produtos], ["UNICO"])
