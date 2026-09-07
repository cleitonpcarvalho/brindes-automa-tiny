from decimal import Decimal

from django.test import TestCase

from apps.fornecedores.spot import SpotFornecedor, _ncm_do_taric

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


def _payload_uma_variacao(opcional, produto=None):
    ref = opcional["ProdReference"]
    produto = produto or {"ProdReference": ref, "Name": f"{ref}. Produto", "Taric": ""}
    return {
        "products": [produto],
        "optionals": [opcional],
        "stocks": [{"Sku": opcional["Sku"], "WebSku": opcional["Sku"], "Quantity": 10}],
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

    def test_ncm_vem_do_taric_de_8_digitos_e_taric_cru_fica_em_atributos(self):
        produtos = SpotFornecedor().normalizar(_payload())
        for variacao in produtos[0].variacoes:
            # fixture: Taric "4202.92.00" -> 8 dígitos -> NCM só-dígitos
            self.assertEqual(variacao.ncm, "42029200")
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


class ImagensSpotTests(TestCase):
    """
    `AllImageList` (lista separada por vírgula) é a fonte; `MainImage` é só
    fallback. A foto limpa da cor da variação vem primeiro, `-logo`/`-box`
    por último, campos técnicos (`11110_1_1_1.png`, `11110_105_C1.png`)
    nunca entram. Dedupe por URL, no máximo 5.
    """

    BASE = "https://www.spotgifts.com.br/fotos/produtos"

    def _imagens(self, opcional, produto=None, base=BASE):
        config = {"url_base_imagens": base} if base else {}
        produtos = SpotFornecedor(configuracao=config).normalizar(
            _payload_uma_variacao(opcional, produto)
        )
        return produtos[0].variacoes[0].imagens

    def _op(self, **extra):
        base = {"Sku": "11110-105", "ProdReference": "11110", "ColorCode": "105", "Price1": 1.99}
        base.update(extra)
        return base

    def test_sem_nenhum_campo_de_imagem_fica_vazio(self):
        self.assertEqual(self._imagens(self._op()), [])

    def test_sem_url_base_continua_sem_imagem(self):
        op = self._op(AllImageList="11110_105.jpg")
        self.assertEqual(self._imagens(op, base=None), [])

    def test_all_image_list_vazio_cai_para_main_image(self):
        op = self._op(MainImage="11110_105.jpg")
        self.assertEqual(self._imagens(op), [f"{self.BASE}/11110_105.jpg"])

    def test_all_image_list_com_uma_imagem(self):
        op = self._op(AllImageList="11110_105.jpg")
        self.assertEqual(self._imagens(op), [f"{self.BASE}/11110_105.jpg"])

    def test_prioriza_foto_limpa_da_cor_e_manda_logo_para_o_fim(self):
        op = self._op(AllImageList="11110_105-logo.jpg, 11110_105.jpg")
        self.assertEqual(
            self._imagens(op),
            [f"{self.BASE}/11110_105.jpg", f"{self.BASE}/11110_105-logo.jpg"],
        )

    def test_multiplas_imagens_da_cor_certa_antes_das_outras_cores(self):
        op = self._op(
            Sku="11112-104",
            ProdReference="11112",
            ColorCode="104",
            AllImageList="11112_115.jpg, 11112_104.jpg, 11112_104-c.jpg",
        )
        self.assertEqual(
            self._imagens(op),
            [
                f"{self.BASE}/11112_104.jpg",
                f"{self.BASE}/11112_104-c.jpg",
                f"{self.BASE}/11112_115.jpg",
            ],
        )

    def test_deduplica_urls_repetidas(self):
        op = self._op(
            AllImageList="11110_105.jpg, 11110_105.jpg ,  11110_105.jpg",
            MainImage="11110_105.jpg",
        )
        self.assertEqual(self._imagens(op), [f"{self.BASE}/11110_105.jpg"])

    def test_limita_a_cinco_imagens(self):
        angulos = ", ".join(f"11110_105-{s}.jpg" for s in "abcdefgh")
        op = self._op(AllImageList=f"11110_105.jpg, {angulos}")
        imagens = self._imagens(op)
        self.assertEqual(len(imagens), 5)
        self.assertEqual(imagens[0], f"{self.BASE}/11110_105.jpg")

    def test_ignora_imagens_tecnicas_de_area_e_componente(self):
        op = self._op(AllImageList="11110_1_1_1.png, 11110_105_C1.png, 11110_105.jpg")
        self.assertEqual(self._imagens(op), [f"{self.BASE}/11110_105.jpg"])


class NcmDoTaricUnitTests(TestCase):
    """`_ncm_do_taric`: só-dígitos, e só devolve se sobrarem exatamente 8."""

    def test_oito_digitos_crus(self):
        self.assertEqual(_ncm_do_taric("96081000"), "96081000")

    def test_oito_digitos_pontuados(self):
        self.assertEqual(_ncm_do_taric("9608.10.00"), "96081000")

    def test_oito_digitos_com_ponto_final(self):
        self.assertEqual(_ncm_do_taric("5603.13.40."), "56031340")

    def test_nove_digitos_nao_e_truncado(self):
        self.assertEqual(_ncm_do_taric("621600000"), "")

    def test_dez_digitos_nao_e_truncado(self):
        self.assertEqual(_ncm_do_taric("9608109900"), "")
        self.assertEqual(_ncm_do_taric("4202.92.91.90"), "")

    def test_vazio_e_none(self):
        self.assertEqual(_ncm_do_taric(""), "")
        self.assertEqual(_ncm_do_taric(None), "")


class NcmSpotNormalizarTests(TestCase):
    def _variacao(self, **opcional_extra):
        opcional = {
            "Sku": "11110-105",
            "ProdReference": "11110",
            "ColorCode": "105",
            "Price1": 1.99,
        }
        opcional.update(opcional_extra)
        produtos = SpotFornecedor().normalizar(_payload_uma_variacao(opcional))
        return produtos[0].variacoes[0]

    def test_taric_de_8_digitos_vira_ncm(self):
        v = self._variacao(Taric="96081000")
        self.assertEqual(v.ncm, "96081000")
        self.assertEqual(v.atributos["taric"], "96081000")

    def test_taric_pontuado_vira_ncm_so_digitos(self):
        v = self._variacao(Taric="9608.10.00")
        self.assertEqual(v.ncm, "96081000")
        self.assertEqual(v.atributos["taric"], "9608.10.00")

    def test_taric_com_ponto_final(self):
        v = self._variacao(Taric="5603.13.40.")
        self.assertEqual(v.ncm, "56031340")
        self.assertEqual(v.atributos["taric"], "5603.13.40.")

    def test_taric_de_9_digitos_fica_sem_ncm_mas_preserva_cru(self):
        v = self._variacao(Taric="621600000")
        self.assertEqual(v.ncm, "")
        self.assertEqual(v.atributos["taric"], "621600000")

    def test_taric_de_10_digitos_fica_sem_ncm_mas_preserva_cru(self):
        v = self._variacao(Taric="9608109900")
        self.assertEqual(v.ncm, "")
        self.assertEqual(v.atributos["taric"], "9608109900")

    def test_taric_ausente_fica_sem_ncm_e_sem_taric(self):
        v = self._variacao()
        self.assertEqual(v.ncm, "")
        self.assertNotIn("taric", v.atributos)

    def test_cai_para_taric_do_produto_quando_opcional_nao_tem(self):
        produto = {"ProdReference": "11110", "Name": "11110. Caneta", "Taric": "9608.10.00"}
        produtos = SpotFornecedor().normalizar(
            _payload_uma_variacao(
                {"Sku": "11110-105", "ProdReference": "11110", "ColorCode": "105", "Price1": 1},
                produto,
            )
        )
        self.assertEqual(produtos[0].variacoes[0].ncm, "96081000")


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
