from decimal import Decimal
from unittest.mock import Mock, patch

import requests

from django.test import SimpleTestCase, TestCase

from apps.fornecedores.xbz import XbzFornecedor

from .fixtures import XBZ_GRUPO_06520, XBZ_GRUPO_P12288, XBZ_LINHA_COM_DIMENSOES


class NormalizarXbzTests(TestCase):
    """
    Usa um recorte real de samples/xbz/ (grupo CodigoAmigavel="06520", 6
    linhas de cor) para testar o agrupamento que o cliente pediu
    explicitamente: a xbz devolve uma lista plana, e é o normalizador que
    reconstrói produto-pai + variações a partir de CodigoAmigavel.
    """

    def test_linhas_do_mesmo_codigo_amigavel_viram_um_unico_produto(self):
        produtos = XbzFornecedor().normalizar(XBZ_GRUPO_06520)
        self.assertEqual(len(produtos), 1)
        self.assertEqual(produtos[0].codigo_pai, "06520")

    def test_cada_linha_vira_uma_variacao_identificada_por_codigoxbz(self):
        produtos = XbzFornecedor().normalizar(XBZ_GRUPO_06520)
        variacoes = produtos[0].variacoes
        self.assertEqual(len(variacoes), 6)
        skus = {v.sku for v in variacoes}
        self.assertEqual(skus, {r["CodigoXbz"] for r in XBZ_GRUPO_06520})

    def test_campos_da_variacao_vem_das_colunas_certas(self):
        produtos = XbzFornecedor().normalizar(XBZ_GRUPO_06520)
        azul = next(v for v in produtos[0].variacoes if v.sku == "X000019")
        self.assertEqual(azul.cor, "AZUL")
        self.assertEqual(azul.ncm, "73239300")
        self.assertEqual(azul.preco, Decimal("10.9"))
        self.assertEqual(azul.estoque, 5690)
        self.assertIn("https://cdn.xbzbrindes.com.br", azul.imagens[0])

    def test_nome_e_descricao_do_produto_pai_vem_da_primeira_linha_do_grupo(self):
        produtos = XbzFornecedor().normalizar(XBZ_GRUPO_06520)
        self.assertEqual(produtos[0].nome, XBZ_GRUPO_06520[0]["Nome"].strip())

    def test_dois_grupos_diferentes_de_codigo_amigavel_viram_dois_produtos(self):
        produtos = XbzFornecedor().normalizar(XBZ_GRUPO_06520 + XBZ_GRUPO_P12288)
        codigos_pai = {p.codigo_pai for p in produtos}
        self.assertEqual(codigos_pai, {"06520", "P@12288"})
        por_codigo = {p.codigo_pai: p for p in produtos}
        self.assertEqual(len(por_codigo["06520"].variacoes), 6)
        self.assertEqual(len(por_codigo["P@12288"].variacoes), 2)

    def test_payload_bruto_do_produto_guarda_todas_as_linhas_do_grupo(self):
        produtos = XbzFornecedor().normalizar(XBZ_GRUPO_06520)
        self.assertEqual(len(produtos[0].payload_bruto["linhas"]), 6)


class ConversaoDeUnidadesXbzTests(TestCase):
    """
    Confirmado contra samples/xbz/: Altura/Largura/Profundidade já vêm em
    cm (sem conversão); Peso vem em gramas e precisa virar kg (÷1000) para
    bater com o que o Tiny espera.
    """

    def test_altura_e_largura_nao_sao_convertidas_peso_vira_kg(self):
        produtos = XbzFornecedor().normalizar([XBZ_LINHA_COM_DIMENSOES])
        dim = produtos[0].variacoes[0].dimensoes
        self.assertEqual(dim.altura, 20.0)
        self.assertEqual(dim.largura, 21.5)
        self.assertEqual(dim.peso_liquido, 0.274)  # 274g -> 0.274kg

    def test_profundidade_zero_e_tratada_como_nao_informada(self):
        """0.0 na xbz normalmente significa 'não medido', não uma dimensão real."""
        produtos = XbzFornecedor().normalizar([XBZ_LINHA_COM_DIMENSOES])
        dim = produtos[0].variacoes[0].dimensoes
        self.assertIsNone(dim.comprimento)  # Profundidade=0.0 na fixture

    def test_linha_sem_nenhum_campo_de_dimensao_fica_com_dimensoes_vazias(self):
        produtos = XbzFornecedor().normalizar([XBZ_GRUPO_06520[0]])
        dim = produtos[0].variacoes[0].dimensoes
        self.assertTrue(dim.vazio())


class HttpXbzTests(SimpleTestCase):
    def _resposta(self, status=200, json_data=None):
        resposta = Mock(status_code=status)
        resposta.json.return_value = json_data or []
        if status >= 400:
            resposta.raise_for_status.side_effect = requests.HTTPError(f"HTTP {status}")
        return resposta

    @patch("apps.fornecedores.xbz.requests.get")
    def test_timeout_faz_somente_uma_chamada(self, mock_get):
        mock_get.side_effect = requests.exceptions.Timeout("timeout")
        with self.assertRaises(requests.exceptions.Timeout):
            XbzFornecedor().buscar({"cnpj": "cnpj-teste", "token": "token-teste"})
        self.assertEqual(mock_get.call_count, 1)

    @patch("apps.fornecedores.xbz.requests.get")
    def test_502_faz_somente_uma_chamada(self, mock_get):
        mock_get.return_value = self._resposta(502)
        with self.assertRaises(requests.HTTPError):
            XbzFornecedor().buscar({"cnpj": "cnpj-teste", "token": "token-teste"})
        self.assertEqual(mock_get.call_count, 1)

    @patch("apps.fornecedores.xbz.requests.get")
    def test_sucesso_continua_funcionando(self, mock_get):
        mock_get.return_value = self._resposta()
        self.assertEqual(XbzFornecedor().buscar({"cnpj": "cnpj-teste", "token": "token-teste"}), [])
        self.assertEqual(mock_get.call_count, 1)

    @patch("apps.fornecedores.xbz.requests.get")
    def test_401_nao_e_repetido(self, mock_get):
        mock_get.return_value = self._resposta(401)
        with self.assertRaisesMessage(ValueError, "401"):
            XbzFornecedor().buscar({"cnpj": "cnpj-teste", "token": "token-teste"})
        self.assertEqual(mock_get.call_count, 1)

    @patch("apps.fornecedores.xbz.requests.get")
    def test_403_nao_e_repetido(self, mock_get):
        mock_get.return_value = self._resposta(403)
        with self.assertRaisesMessage(ValueError, "403"):
            XbzFornecedor().buscar({"cnpj": "cnpj-teste", "token": "token-teste"})
        self.assertEqual(mock_get.call_count, 1)
