"""
`testar_atualizacao_produto_tiny` — suporte ao teste canário manual de
`PUT /produtos/{id}` (NÃO é o backfill em lote).
"""

from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase
from unittest.mock import patch

from apps.instancias.models import CredencialFornecedor, Instancia

from ..management.commands.testar_atualizacao_produto_tiny import (
    comparar_campos,
    montar_fornecedores,
    montar_payload_canario,
)
from ..models import Produto, Variacao

# GET real do produto canário (BL026-BG), com os campos read-only presentes.
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
        "largura": 5.3,
        "altura": 8,
        "comprimento": 1.2,
        "diametro": 0,
        "pesoLiquido": 0.025,
        "pesoBruto": 0,
        "quantidadeVolumes": 0,
    },
    "precos": {"preco": 3.6, "precoPromocional": 0, "precoCusto": 0, "precoCustoMedio": 0},
    "estoque": {
        "controlar": True,
        "sobEncomenda": False,
        "diasPreparacao": 0,
        "localizacao": "",
        "minimo": 0,
        "maximo": 0,
        "quantidade": 1518,
    },
    "fornecedores": [],
    "seo": None,
    "tributacao": {"gtinEmbalagem": "", "valorIPIFixo": 0, "classeIPI": ""},
    "anexos": [
        {"id": 924267502, "url": "https://s3.amazonaws.com/tiny-anexos-us/erp/x/y.jpg", "externo": False}
    ],
    "variacoes": [],
    "kit": [],
    "producao": None,
    "codigoListaServicos": "",
    "tipoVariacao": "N",
}

DESC_COMPL = "Mini caderno com capa dura em papel reciclado, sticky notes e miolo com 22 folhas."


class MontarFornecedoresTests(TestCase):
    def test_lista_vazia_nosso_entra_como_padrao(self):
        resultado = montar_fornecedores(
            [], tiny_fornecedor_id=752133514, codigo_produto_no_fornecedor="BL026-BG"
        )
        self.assertEqual(
            resultado,
            [{"id": 752133514, "codigoProdutoNoFornecedor": "BL026-BG", "padrao": True}],
        )

    def test_nosso_ja_existente_nao_duplica(self):
        atuais = [{"id": 752133514, "nome": "Asia", "codigoProdutoNoFornecedor": "X-1"}]
        resultado = montar_fornecedores(
            atuais, tiny_fornecedor_id=752133514, codigo_produto_no_fornecedor="BL026-BG"
        )
        self.assertEqual(len(resultado), 1)
        self.assertEqual(resultado[0]["id"], 752133514)
        # preserva o código que já estava lá, não sobrescreve
        self.assertEqual(resultado[0]["codigoProdutoNoFornecedor"], "X-1")

    def test_com_outro_fornecedor_padrao_o_nosso_entra_nao_padrao(self):
        atuais = [{"id": 999, "nome": "Outro", "padrao": True}]
        resultado = montar_fornecedores(
            atuais, tiny_fornecedor_id=752133514, codigo_produto_no_fornecedor="BL026-BG"
        )
        self.assertEqual(len(resultado), 2)
        self.assertEqual(resultado[0], {"id": 999, "codigoProdutoNoFornecedor": "", "padrao": True})
        self.assertEqual(
            resultado[1],
            {"id": 752133514, "codigoProdutoNoFornecedor": "BL026-BG", "padrao": False},
        )

    def test_outro_fornecedor_sem_padrao_o_nosso_vira_padrao(self):
        resultado = montar_fornecedores(
            [{"id": 999}], tiny_fornecedor_id=752133514, codigo_produto_no_fornecedor="BL026-BG"
        )
        self.assertEqual(resultado[1]["padrao"], True)

    def test_fornecedor_existente_sem_id_aborta(self):
        with self.assertRaises(CommandError):
            montar_fornecedores(
                [{"nome": "Sem id", "codigoProdutoNoFornecedor": "z"}],
                tiny_fornecedor_id=752133514,
                codigo_produto_no_fornecedor="BL026-BG",
            )


class MontarPayloadCanarioTests(TestCase):
    def setUp(self):
        self.payload = montar_payload_canario(
            GET_BL026,
            descricao_complementar=DESC_COMPL,
            fornecedores=[{"id": 752133514, "codigoProdutoNoFornecedor": "BL026-BG", "padrao": True}],
        )

    def test_nao_contem_campos_read_only_nem_de_outro_endpoint(self):
        for chave in ("id", "anexos", "situacao", "tipo", "tipoVariacao", "produtoPai",
                      "variacoes", "kit", "producao", "codigoListaServicos"):
            self.assertNotIn(chave, self.payload, chave)
        self.assertNotIn("precoCustoMedio", self.payload["precos"])
        self.assertNotIn("quantidade", self.payload["estoque"])
        self.assertNotIn("quantidadeVolumes", self.payload["dimensoes"])
        self.assertNotIn("embalagem", self.payload["dimensoes"])

    def test_preserva_os_campos_graveis_do_get(self):
        self.assertEqual(self.payload["sku"], "BL026-BG")
        self.assertEqual(self.payload["descricao"], "Mini Caderno (8x5cm) - Bege")
        self.assertEqual(self.payload["ncm"], "4820.20.00")
        self.assertEqual(self.payload["origem"], 0)  # int, não a string "0" do GET
        self.assertEqual(self.payload["unidade"], "UN")
        self.assertEqual(
            self.payload["precos"], {"preco": 3.6, "precoPromocional": 0, "precoCusto": 0}
        )
        self.assertEqual(self.payload["estoque"]["controlar"], True)
        self.assertEqual(
            self.payload["dimensoes"],
            {"largura": 5.3, "altura": 8, "comprimento": 1.2, "diametro": 0,
             "pesoLiquido": 0.025, "pesoBruto": 0},
        )
        self.assertEqual(self.payload["tributacao"], {"gtinEmbalagem": "", "valorIPIFixo": 0, "classeIPI": ""})

    def test_so_altera_descricao_complementar_e_fornecedores(self):
        self.assertEqual(self.payload["descricaoComplementar"], DESC_COMPL)
        self.assertEqual(self.payload["fornecedores"][0]["id"], 752133514)
        # marca/categoria/seo eram null no GET -> ficam de fora (nada a preservar)
        for chave in ("marca", "categoria", "seo"):
            self.assertNotIn(chave, self.payload)


class CompararCamposTests(TestCase):
    def test_marca_alteracao_inesperada_em_precos(self):
        depois = {**GET_BL026, "precos": {**GET_BL026["precos"], "preco": 9.99}}
        linhas = {linha["campo"]: linha for linha in comparar_campos(GET_BL026, depois)}
        self.assertFalse(linhas["precos"]["igual"])
        self.assertFalse(linhas["precos"]["esperado_mudar"])
        self.assertTrue(linhas["sku"]["igual"])
        self.assertTrue(linhas["descricaoComplementar"]["esperado_mudar"])


class ComandoCanarioTests(TestCase):
    def setUp(self):
        self.instancia = Instancia.objects.create(nome="Loja Canário", access_token="tok")
        produto = Produto.objects.create(
            instancia=self.instancia, fornecedor="asia", codigo_pai="BL026", nome="Mini Caderno",
            descricao=DESC_COMPL,
        )
        Variacao.objects.create(
            produto=produto, sku="BL026-BG", nome="Mini Caderno - Bege", preco="3.60", estoque=1518
        )
        CredencialFornecedor.objects.create(
            instancia=self.instancia, fornecedor="asia", tiny_fornecedor_id=752133514
        )

    def _rodar(self, *extra):
        out = StringIO()
        call_command(
            "testar_atualizacao_produto_tiny",
            "--instancia", self.instancia.slug,
            "--tiny-id", "924267500",
            "--sku", "BL026-BG",
            "--fornecedor", "asia",
            *extra,
            stdout=out,
        )
        return out.getvalue()

    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto", return_value=GET_BL026)
    def test_sem_executar_so_faz_get_e_imprime_o_payload(self, mock_get, mock_put):
        saida = self._rodar()

        mock_get.assert_called_once_with(924267500)
        mock_put.assert_not_called()
        self.assertIn("DRY-RUN", saida)
        self.assertIn('"descricaoComplementar"', saida)
        self.assertIn(DESC_COMPL, saida)
        self.assertIn("924267500", saida)

    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto", return_value={})
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    def test_executar_faz_put_com_payload_defensivo_e_diff_sem_surpresa(self, mock_get, mock_put):
        depois = {
            **GET_BL026,
            "descricaoComplementar": DESC_COMPL,
            "fornecedores": [
                {"id": 752133514, "nome": "Asia Import", "codigoProdutoNoFornecedor": "BL026-BG"}
            ],
        }
        mock_get.side_effect = [GET_BL026, depois]

        saida = self._rodar("--executar")

        mock_put.assert_called_once()
        produto_id, payload = mock_put.call_args[0]
        self.assertEqual(produto_id, 924267500)
        self.assertNotIn("id", payload)
        self.assertNotIn("anexos", payload)
        self.assertNotIn("quantidade", payload["estoque"])
        self.assertEqual(payload["fornecedores"], [
            {"id": 752133514, "codigoProdutoNoFornecedor": "BL026-BG", "padrao": True}
        ])
        self.assertIn("alterado (esperado)", saida)
        self.assertIn("Nenhuma alteração inesperada", saida)

    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto", return_value={})
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    def test_executar_destaca_alteracao_inesperada(self, mock_get, mock_put):
        depois = {
            **GET_BL026,
            "descricaoComplementar": DESC_COMPL,
            "fornecedores": [{"id": 752133514, "codigoProdutoNoFornecedor": "BL026-BG"}],
            "precos": {**GET_BL026["precos"], "preco": 0},  # sumiu o preço!
            "estoque": {**GET_BL026["estoque"], "quantidade": 0},  # sumiu o saldo!
        }
        mock_get.side_effect = [GET_BL026, depois]

        saida = self._rodar("--executar")

        self.assertIn("INESPERADO", saida)
        self.assertIn("NÃO seguir para o lote", saida)

    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    def test_aborta_se_o_sku_do_tiny_nao_bate(self, mock_get):
        mock_get.return_value = {**GET_BL026, "sku": "OUTRO-SKU"}
        with self.assertRaises(CommandError):
            self._rodar()

    def test_aborta_sem_tiny_fornecedor_id_configurado(self):
        CredencialFornecedor.objects.filter(instancia=self.instancia, fornecedor="asia").update(
            tiny_fornecedor_id=None
        )
        with self.assertRaises(CommandError):
            self._rodar()

    def test_aborta_se_sku_nao_esta_no_espelho(self):
        with self.assertRaises(CommandError):
            call_command(
                "testar_atualizacao_produto_tiny",
                "--instancia", self.instancia.slug,
                "--tiny-id", "1",
                "--sku", "NAO-EXISTE",
                "--fornecedor", "asia",
                stdout=StringIO(),
            )
