from decimal import Decimal

from django.test import TestCase

from apps.fornecedores.somarcas import SomarcasFornecedor

from .fixtures import SOMARCAS_ITEM_COM_DIMENSOES_REAIS, SOMARCAS_ITEM_COM_ESTOQUE


class NormalizarSomarcasTests(TestCase):
    """
    Usa um recorte real de samples/somarcas/ (capturado depois que as
    credenciais chegaram). Confirma o que a amostra real mostrou e a
    especificação não deixava claro: não existe produto-pai separado —
    cada `codigo` já é uma variação de cor, então aqui codigo_pai == sku.
    """

    def test_codigo_pai_e_sku_sao_o_mesmo_valor(self):
        produtos = SomarcasFornecedor().normalizar([SOMARCAS_ITEM_COM_ESTOQUE])
        self.assertEqual(len(produtos), 1)
        produto = produtos[0]
        self.assertEqual(produto.codigo_pai, "AS-00610")
        self.assertEqual(len(produto.variacoes), 1)
        self.assertEqual(produto.variacoes[0].sku, "AS-00610")

    def test_preco_usado_e_com_gravacao_com_impostos(self):
        """Confirmado pelo cliente em 2026-09-04 (passo 5): com gravação, com impostos."""
        produtos = SomarcasFornecedor().normalizar([SOMARCAS_ITEM_COM_ESTOQUE])
        self.assertEqual(produtos[0].variacoes[0].preco, Decimal("21.01"))

    def test_categorias_e_imagens_sao_separadas_do_texto_delimitado_por_pipe(self):
        produtos = SomarcasFornecedor().normalizar([SOMARCAS_ITEM_COM_ESTOQUE])
        produto = produtos[0]
        self.assertEqual(
            produto.categorias,
            ["Copos, Canecas, Squeezes e Garrafas", "Lançamentos", "Garrafa Personalizada"],
        )
        self.assertIn(SOMARCAS_ITEM_COM_ESTOQUE["url_foto"], produto.imagens)

    def test_data_ultima_atualizacao_e_convertida_para_datetime(self):
        produtos = SomarcasFornecedor().normalizar([SOMARCAS_ITEM_COM_ESTOQUE])
        atualizado_em = produtos[0].atualizado_em_fornecedor
        self.assertIsNotNone(atualizado_em)
        self.assertEqual(atualizado_em.strftime("%Y-%m-%d %H:%M:%S"), "2026-09-04 11:51:45")


class ConversaoDeUnidadesSomarcasTests(TestCase):
    """
    Confirmado contra a amostra real: `dimensoes_da_embalagem` vem
    rotulado "AxLxP mm" (1278/1278 registros bateram no formato) — convertido
    para cm (÷10). `peso_da_embalagem` vem em gramas — convertido para kg
    (÷1000). Mapeados como peso/dimensão BRUTOS (são da embalagem, não do
    produto isolado). `dimensoes_do_produto` (sem eixos rotulados) nunca é
    parseado.
    """

    def test_dimensoes_da_embalagem_mm_convertidas_para_cm(self):
        produtos = SomarcasFornecedor().normalizar([SOMARCAS_ITEM_COM_DIMENSOES_REAIS])
        dim = produtos[0].variacoes[0].dimensoes
        # "70x215x70 mm (AxLxP)" -> altura=7cm, largura=21.5cm, comprimento=7cm
        self.assertEqual(dim.altura, 7.0)
        self.assertEqual(dim.largura, 21.5)
        self.assertEqual(dim.comprimento, 7.0)

    def test_peso_da_embalagem_gramas_convertido_para_kg_como_peso_bruto(self):
        produtos = SomarcasFornecedor().normalizar([SOMARCAS_ITEM_COM_DIMENSOES_REAIS])
        dim = produtos[0].variacoes[0].dimensoes
        self.assertEqual(dim.peso_bruto, 0.125)  # "125 g" -> 0.125kg
        self.assertIsNone(dim.peso_liquido)  # Só Marcas não informa peso líquido

    def test_embalagem_zerada_e_tratada_como_nao_informada(self):
        """"0x0x0 mm (AxLxP)" (caso real da amostra) não é uma medida, é ausência de dado."""
        produtos = SomarcasFornecedor().normalizar([SOMARCAS_ITEM_COM_ESTOQUE])
        dim = produtos[0].variacoes[0].dimensoes
        self.assertIsNone(dim.altura)
        self.assertIsNone(dim.largura)
        self.assertIsNone(dim.comprimento)

    def test_dimensoes_do_produto_sem_eixos_rotulados_nunca_e_parseada(self):
        """"24,5x7cm"/"21x6,5Øcm" não têm eixo identificado — não viram largura/altura/comprimento."""
        produtos = SomarcasFornecedor().normalizar([SOMARCAS_ITEM_COM_DIMENSOES_REAIS])
        dim = produtos[0].variacoes[0].dimensoes
        # as únicas dimensões preenchidas vêm de dimensoes_da_embalagem, não de dimensoes_do_produto
        self.assertNotEqual(dim.altura, 21)
        self.assertNotEqual(dim.diametro, 6.5)
        self.assertIsNone(dim.diametro)
