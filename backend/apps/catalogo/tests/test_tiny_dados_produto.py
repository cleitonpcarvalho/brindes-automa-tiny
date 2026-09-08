"""
`apps.catalogo.tiny_dados_produto` — regra definitiva + payload defensivo do
`PUT /produtos/{id}`. Só transforma dicts; não fala com Tiny nem banco.
"""

from decimal import Decimal

from django.test import TestCase

from apps.instancias.models import Instancia

from ..models import Produto, Variacao
from ..tiny_dados_produto import (
    DadosProdutoError,
    comparar_campos,
    montar_fornecedores,
    montar_payload_atualizacao,
)

# GET real do produto canário (BL026-BG), com os read-only presentes.
GET_BL026 = {
    "id": 924267500,
    "sku": "BL026-BG",
    "descricao": "Mini Caderno (8x5cm) - Bege",
    "tipo": "S",
    "descricaoComplementar": "",
    "situacao": "A",
    "produtoPai": None,
    "unidade": "UN",
    "unidadePorCaixa": "",
    "ncm": "4820.20.00",
    "gtin": "",
    "origem": "0",
    "garantia": "",
    "observacoes": "",
    "categoria": None,
    "marca": None,
    "dimensoes": {
        "embalagem": {"id": None, "tipo": 0, "descricao": ""},
        "largura": 5.3, "altura": 8, "comprimento": 1.2, "diametro": 0,
        "pesoLiquido": 0.025, "pesoBruto": 0, "quantidadeVolumes": 0,
    },
    "precos": {"preco": 3.6, "precoPromocional": 0, "precoCusto": 0, "precoCustoMedio": 0},
    "estoque": {
        "controlar": True, "sobEncomenda": False, "diasPreparacao": 0,
        "localizacao": "", "minimo": 0, "maximo": 0, "quantidade": 1518,
    },
    "fornecedores": [],
    "seo": None,
    "tributacao": {"gtinEmbalagem": "", "valorIPIFixo": 0, "classeIPI": ""},
    "anexos": [{"id": 924267502, "url": "https://s3/x/y.jpg", "externo": False}],
    "variacoes": [], "kit": [], "producao": None,
    "codigoListaServicos": "", "tipoVariacao": "N",
}
DESC_COMPL = "Mini caderno com capa dura em papel reciclado, sticky notes e miolo com 22 folhas."


def _variacao(*, sku="BL026-BG", preco="3.60", descricao_produto=DESC_COMPL):
    instancia = Instancia.objects.create(nome="Loja", access_token="t")
    produto = Produto.objects.create(
        instancia=instancia, fornecedor="asia", codigo_pai="BL026", nome="Mini Caderno",
        descricao=descricao_produto,
    )
    return Variacao.objects.create(
        produto=produto, sku=sku, nome="Mini Caderno - Bege", preco=Decimal(preco), estoque=1518
    )


class MontarFornecedoresTests(TestCase):
    def test_lista_vazia_nosso_entra_como_padrao(self):
        self.assertEqual(
            montar_fornecedores([], tiny_fornecedor_id=752133514, codigo_produto_no_fornecedor="BL026-BG"),
            [{"id": 752133514, "codigoProdutoNoFornecedor": "BL026-BG", "padrao": True}],
        )

    def test_nosso_ja_existente_nao_duplica_e_preserva_o_codigo(self):
        atuais = [{"id": 752133514, "nome": "Asia", "codigoProdutoNoFornecedor": "X-1"}]
        resultado = montar_fornecedores(
            atuais, tiny_fornecedor_id=752133514, codigo_produto_no_fornecedor="BL026-BG"
        )
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]["codigoProdutoNoFornecedor"], "X-1")
        self.assertTrue(resultado[0]["padrao"])  # nosso é sempre padrao=true

    def test_get_real_sem_campo_padrao_nao_desmarca_o_nosso(self):
        """
        Reprodução EXATA do GET /produtos/924267500 (dry-run real): o v3 não
        devolve `padrao` por fornecedor. O nosso fornecedor, que já está
        associado (e é o padrão no Tiny), tem que voltar com padrao=true —
        antes virava padrao=false e o PUT o desmarcaria.
        """
        atuais = [
            {
                "id": 752133514,
                "nome": "ASIA IMPORT COMERCIO DE BRINDES LTDA",
                "codigoProdutoNoFornecedor": "BL026-BG",
            }
        ]
        resultado = montar_fornecedores(
            atuais, tiny_fornecedor_id=752133514, codigo_produto_no_fornecedor="BL026-BG"
        )
        self.assertEqual(
            resultado,
            [{"id": 752133514, "codigoProdutoNoFornecedor": "BL026-BG", "padrao": True}],
        )

    def test_nosso_ja_existente_com_outro_fornecedor_junto(self):
        atuais = [
            {"id": 999, "nome": "Outro"},  # GET sem `padrao`
            {"id": 752133514, "nome": "Asia", "codigoProdutoNoFornecedor": "BL026-BG"},
        ]
        resultado = montar_fornecedores(
            atuais, tiny_fornecedor_id=752133514, codigo_produto_no_fornecedor="BL026-BG"
        )
        self.assertEqual(resultado, [
            {"id": 999, "codigoProdutoNoFornecedor": "", "padrao": False},
            {"id": 752133514, "codigoProdutoNoFornecedor": "BL026-BG", "padrao": True},
        ])

    def test_outro_fornecedor_padrao_o_nosso_entra_nao_padrao(self):
        resultado = montar_fornecedores(
            [{"id": 999, "padrao": True}], tiny_fornecedor_id=752133514,
            codigo_produto_no_fornecedor="BL026-BG",
        )
        self.assertEqual(resultado, [
            {"id": 999, "codigoProdutoNoFornecedor": "", "padrao": True},
            {"id": 752133514, "codigoProdutoNoFornecedor": "BL026-BG", "padrao": False},
        ])

    def test_outro_fornecedor_sem_padrao_o_nosso_vira_padrao(self):
        resultado = montar_fornecedores(
            [{"id": 999}], tiny_fornecedor_id=752133514, codigo_produto_no_fornecedor="BL026-BG"
        )
        self.assertTrue(resultado[1]["padrao"])

    def test_fornecedor_existente_sem_id_aborta(self):
        with self.assertRaises(DadosProdutoError):
            montar_fornecedores(
                [{"nome": "Sem id"}], tiny_fornecedor_id=752133514,
                codigo_produto_no_fornecedor="BL026-BG",
            )


class MontarPayloadAtualizacaoTests(TestCase):
    def setUp(self):
        self.variacao = _variacao()
        self.payload = montar_payload_atualizacao(
            GET_BL026, variacao=self.variacao, tiny_fornecedor_id=752133514
        )

    def test_nao_contem_read_only_nem_de_outro_endpoint(self):
        for chave in ("id", "anexos", "situacao", "tipo", "tipoVariacao", "produtoPai",
                      "variacoes", "kit", "producao", "codigoListaServicos"):
            self.assertNotIn(chave, self.payload)
        self.assertNotIn("precoCustoMedio", self.payload["precos"])
        self.assertNotIn("quantidade", self.payload["estoque"])
        self.assertNotIn("quantidadeVolumes", self.payload["dimensoes"])
        self.assertNotIn("embalagem", self.payload["dimensoes"])

    def test_regra_definitiva_de_precos(self):
        self.assertEqual(
            self.payload["precos"], {"preco": 0.0, "precoPromocional": 0, "precoCusto": 3.6}
        )

    def test_descricao_complementar_vem_do_produto_do_espelho(self):
        self.assertEqual(self.payload["descricaoComplementar"], DESC_COMPL)

    def test_fornecedor_do_par_e_incluido(self):
        self.assertEqual(self.payload["fornecedores"], [
            {"id": 752133514, "codigoProdutoNoFornecedor": "BL026-BG", "padrao": True}
        ])

    def test_preserva_os_demais_campos_graveis_do_get(self):
        self.assertEqual(self.payload["sku"], "BL026-BG")
        self.assertEqual(self.payload["descricao"], "Mini Caderno (8x5cm) - Bege")  # título intocado
        self.assertEqual(self.payload["ncm"], "4820.20.00")
        self.assertEqual(self.payload["origem"], 0)  # int, não "0"
        self.assertEqual(
            self.payload["dimensoes"],
            {"largura": 5.3, "altura": 8, "comprimento": 1.2, "diametro": 0,
             "pesoLiquido": 0.025, "pesoBruto": 0},
        )
        self.assertEqual(self.payload["estoque"]["controlar"], True)
        for chave in ("marca", "categoria", "seo"):  # null no GET -> fora
            self.assertNotIn(chave, self.payload)

    def test_sku_divergente_no_get_aborta_sem_fuzzy(self):
        with self.assertRaises(DadosProdutoError):
            montar_payload_atualizacao(
                {**GET_BL026, "sku": "OUTRO"}, variacao=self.variacao, tiny_fornecedor_id=752133514
            )


class CompararCamposTests(TestCase):
    def test_precos_agora_e_mudanca_esperada_ncm_e_inesperada(self):
        depois = {
            **GET_BL026,
            "precos": {**GET_BL026["precos"], "precoCusto": 3.6},
            "ncm": "9999.99.99",
        }
        linhas = {linha["campo"]: linha for linha in comparar_campos(GET_BL026, depois)}
        self.assertTrue(linhas["precos"]["esperado_mudar"])
        self.assertFalse(linhas["precos"]["igual"])
        self.assertFalse(linhas["ncm"]["esperado_mudar"])
        self.assertFalse(linhas["ncm"]["igual"])
        self.assertTrue(linhas["anexos"]["igual"])
