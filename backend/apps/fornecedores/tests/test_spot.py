from decimal import Decimal

from django.test import TestCase

from apps.fornecedores.spot import SpotFornecedor

from .fixtures import (
    SPOT_ESTOQUE_CANETA,
    SPOT_ESTOQUES_11112,
    SPOT_OPCIONAIS_11112,
    SPOT_OPCIONAL_CANETA,
    SPOT_PRODUTO_11112,
    SPOT_PRODUTO_CANETA_DIAMETRO,
)


def _payload():
    return {
        "products": [SPOT_PRODUTO_11112],
        "optionals": SPOT_OPCIONAIS_11112,
        "stocks": SPOT_ESTOQUES_11112,
    }


class NormalizarSpotTests(TestCase):
    """
    Usa um recorte real de samples/spot/ — ProdReference "11112" (mochila,
    2 cores) — para testar o join das três fontes: products (produto-base,
    sem SKU), optionalsComplete (SKU + preço) e stocks (quantidade por
    SKU). Confirmado nas amostras reais que o join por Sku é 1:1 sem
    órfãos entre optionalsComplete e stocks, e por ProdReference entre
    optionalsComplete e products.
    """

    def test_gera_um_produto_com_duas_variacoes_uma_por_cor(self):
        produtos = SpotFornecedor().normalizar(_payload())
        self.assertEqual(len(produtos), 1)
        produto = produtos[0]
        self.assertEqual(produto.codigo_pai, "11112")
        self.assertEqual(len(produto.variacoes), 2)

    def test_estoque_da_variacao_vem_do_join_com_stocks_por_sku(self):
        produtos = SpotFornecedor().normalizar(_payload())
        por_sku = {v.sku: v for v in produtos[0].variacoes}
        self.assertEqual(por_sku["11112-104"].estoque, 4669)
        self.assertEqual(por_sku["11112-115"].estoque, 52)

    def test_join_usa_websku_como_fallback_quando_sku_nao_bate_em_stocks(self):
        payload = _payload()
        # simula um caso em que o estoque só existe indexado por WebSku,
        # não por Sku (o pedido explícito foi "o join é por Sku e WebSku")
        payload["stocks"] = [
            {"Sku": "SKU-DIFERENTE", "WebSku": "11112-104", "Quantity": 999},
            {"Sku": "11112-115", "WebSku": "11112-115", "Quantity": 52},
        ]
        produtos = SpotFornecedor().normalizar(payload)
        por_sku = {v.sku: v for v in produtos[0].variacoes}
        self.assertEqual(por_sku["11112-104"].estoque, 999)

    def test_preco_vem_de_price1_do_optionalscomplete(self):
        produtos = SpotFornecedor().normalizar(_payload())
        for variacao in produtos[0].variacoes:
            self.assertEqual(variacao.preco, Decimal("69.9"))

    def test_ncm_fica_vazio_e_taric_vai_para_atributos(self):
        produtos = SpotFornecedor().normalizar(_payload())
        for variacao in produtos[0].variacoes:
            self.assertEqual(variacao.ncm, "")
            self.assertEqual(variacao.atributos["taric"], "4202.92.00")

    def test_imagem_fica_vazia_sem_url_base_configurada(self):
        produtos = SpotFornecedor(configuracao={}).normalizar(_payload())
        for variacao in produtos[0].variacoes:
            self.assertEqual(variacao.imagens, [])

    def test_imagem_e_montada_quando_url_base_esta_configurada(self):
        produtos = SpotFornecedor(
            configuracao={"url_base_imagens": "https://cdn.exemplo.com/spot"}
        ).normalizar(_payload())
        for variacao in produtos[0].variacoes:
            self.assertEqual(variacao.imagens, ["https://cdn.exemplo.com/spot/11112_115.jpg"])


class ConversaoDeUnidadesSpotTests(TestCase):
    """
    Confirmado contra a amostra real: `CombinedSizes` só tem eixo explícito
    no padrão "ø<diametro> x <comprimento> mm" (o símbolo de diâmetro) —
    convertido de mm para cm (÷10). Formatos sem essa marcação (2 ou 3
    números soltos) nunca são parseados. `Weight` nunca é usado (295 dos
    1247 produtos da amostra real têm Weight=1, um valor repetido demais
    pra ser medição de verdade).
    """

    def _payload_caneta(self):
        return {
            "products": [SPOT_PRODUTO_CANETA_DIAMETRO],
            "optionals": [SPOT_OPCIONAL_CANETA],
            "stocks": [SPOT_ESTOQUE_CANETA],
        }

    def test_padrao_diametro_x_comprimento_e_convertido_de_mm_para_cm(self):
        produtos = SpotFornecedor().normalizar(self._payload_caneta())
        dim = produtos[0].variacoes[0].dimensoes
        # "ø7 x 129 mm" -> diametro=0.7cm, comprimento=12.9cm
        self.assertEqual(dim.diametro, 0.7)
        self.assertEqual(dim.comprimento, 12.9)

    def test_combinedsizes_sem_diametro_nao_e_parseado(self):
        """"55 x 22 x 12 mm" (3 números soltos, sem eixo) não vira largura/altura/comprimento."""
        produtos = SpotFornecedor().normalizar(_payload())  # 11112: "330 x 480 x 180 mm | Placa..."
        dim = produtos[0].variacoes[0].dimensoes
        self.assertTrue(dim.vazio())

    def test_weight_nunca_e_usado_como_peso(self):
        produtos = SpotFornecedor().normalizar(self._payload_caneta())
        dim = produtos[0].variacoes[0].dimensoes
        self.assertIsNone(dim.peso_liquido)
        self.assertIsNone(dim.peso_bruto)
