from django.contrib.auth import get_user_model
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.db import connection
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.catalogo.models import Produto, StatusVariacao, Variacao
from apps.sincronizacao.models import Execucao, StatusExecucao, TipoExecucao

from ..constants import Fornecedor
from ..models import CredencialFornecedor, Instancia


def _client_autenticado():
    usuario = get_user_model().objects.create_user(email="operador-listagem@example.com", password="x")
    token = Token.objects.create(user=usuario)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


def _montar_instancia_completa(nome, *, status_execucao=StatusExecucao.SUCESSO):
    instancia = Instancia.objects.create(nome=nome, cnpj="11.222.333/0001-44")
    CredencialFornecedor.objects.create(instancia=instancia, fornecedor=Fornecedor.XBZ, ativo=True)
    Execucao.objects.create(
        instancia=instancia, fornecedor=Fornecedor.XBZ, tipo=TipoExecucao.INCREMENTAL, status=status_execucao
    )
    produto = Produto.objects.create(instancia=instancia, fornecedor=Fornecedor.XBZ, codigo_pai="p1", nome="Produto")
    Variacao.objects.create(
        produto=produto, sku="sku-1", nome="Var", preco="10.00", estoque=1, status=StatusVariacao.CADASTRADO
    )
    Variacao.objects.create(
        produto=produto, sku="sku-2", nome="Var2", preco="10.00", estoque=1, status=StatusVariacao.PENDENTE
    )
    return instancia


class ListagemInstanciasTests(TestCase):
    def setUp(self):
        self.client = _client_autenticado()

    def test_busca_por_nome(self):
        Instancia.objects.create(nome="Casa dos Brindes")
        Instancia.objects.create(nome="Outra Loja")
        resposta = self.client.get("/api/instancias/?busca=Brindes")
        nomes = [linha["nome"] for linha in resposta.data["results"]]
        self.assertEqual(nomes, ["Casa dos Brindes"])

    def test_busca_por_cnpj(self):
        Instancia.objects.create(nome="Loja A", cnpj="18.421.908/0001-44")
        Instancia.objects.create(nome="Loja B", cnpj="99.999.999/0001-99")
        resposta = self.client.get("/api/instancias/?busca=18.421.908")
        nomes = [linha["nome"] for linha in resposta.data["results"]]
        self.assertEqual(nomes, ["Loja A"])

    def test_filtro_por_status(self):
        Instancia.objects.create(nome="Erro", status=Instancia.Status.ERRO)
        Instancia.objects.create(nome="Conectada", status=Instancia.Status.CONECTADO)
        resposta = self.client.get("/api/instancias/?status=erro")
        nomes = [linha["nome"] for linha in resposta.data["results"]]
        self.assertEqual(nomes, ["Erro"])

    def test_ordenacao_coloca_problema_primeiro(self):
        Instancia.objects.create(nome="Zeta Conectada", status=Instancia.Status.CONECTADO)
        Instancia.objects.create(nome="Alfa Erro", status=Instancia.Status.ERRO)
        Instancia.objects.create(nome="Beta Nao Conectada", status=Instancia.Status.NAO_CONECTADO)

        resposta = self.client.get("/api/instancias/")
        nomes = [linha["nome"] for linha in resposta.data["results"]]
        self.assertEqual(nomes, ["Alfa Erro", "Beta Nao Conectada", "Zeta Conectada"])

    def test_paginacao_tamanho_padrao(self):
        for indice in range(15):
            Instancia.objects.create(nome=f"Loja {indice:02d}")
        resposta = self.client.get("/api/instancias/")
        self.assertEqual(resposta.data["count"], 15)
        self.assertEqual(len(resposta.data["results"]), 10)
        self.assertIsNotNone(resposta.data["next"])

    def test_linha_traz_fornecedores_produtos_e_ultima_sincronizacao(self):
        instancia = _montar_instancia_completa("Loja Completa")
        resposta = self.client.get("/api/instancias/")
        linha = resposta.data["results"][0]

        self.assertEqual(linha["fornecedores"]["xbz"], "ok")
        self.assertEqual(linha["fornecedores"]["asia"], "nao_configurado")
        self.assertEqual(linha["produtos"], {"total": 2, "cadastrados": 1})
        self.assertEqual(linha["ultima_sincronizacao"]["fornecedor"], "xbz")
        self.assertIsNotNone(linha["ultima_sincronizacao"]["em"])

    def test_fornecedor_falhou_aparece_como_erro(self):
        _montar_instancia_completa("Loja com Falha", status_execucao=StatusExecucao.FALHA)
        resposta = self.client.get("/api/instancias/")
        linha = resposta.data["results"][0]
        self.assertEqual(linha["fornecedores"]["xbz"], "erro")

    def test_instancia_sem_credencial_nem_execucao_fica_zerada(self):
        Instancia.objects.create(nome="Loja Vazia")
        resposta = self.client.get("/api/instancias/")
        linha = resposta.data["results"][0]
        self.assertEqual(
            linha["fornecedores"],
            {"xbz": "nao_configurado", "asia": "nao_configurado", "somarcas": "nao_configurado", "spot": "nao_configurado"},
        )
        self.assertEqual(linha["produtos"], {"total": 0, "cadastrados": 0})
        self.assertEqual(linha["ultima_sincronizacao"], {"em": None, "fornecedor": None})

    def test_numero_de_queries_nao_cresce_com_o_numero_de_instancias(self):
        for indice in range(3):
            _montar_instancia_completa(f"Loja {indice}")

        with CaptureQueriesContext(connection) as contexto_poucas:
            resposta = self.client.get("/api/instancias/")
            self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        queries_poucas = len(contexto_poucas)

        for indice in range(3, 9):
            _montar_instancia_completa(f"Loja {indice}")

        with CaptureQueriesContext(connection) as contexto_muitas:
            resposta = self.client.get("/api/instancias/?page_size=9")
            self.assertEqual(resposta.status_code, status.HTTP_200_OK)
            self.assertEqual(len(resposta.data["results"]), 9)
        queries_muitas = len(contexto_muitas)

        self.assertEqual(queries_poucas, queries_muitas)
