from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.catalogo.models import Produto, StatusVariacao, Variacao

from ..constants import Fornecedor
from ..models import Instancia


def _client_autenticado():
    usuario = get_user_model().objects.create_user(email="operador-produtos@example.com", password="x")
    token = Token.objects.create(user=usuario)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


def _produto(instancia, *, fornecedor=Fornecedor.XBZ, codigo_pai="p1", nome="Caneca"):
    return Produto.objects.create(
        instancia=instancia, fornecedor=fornecedor, codigo_pai=codigo_pai, nome=nome
    )


def _variacao(produto, *, sku, nome="Variação", preco="10.00", estoque=5, status=StatusVariacao.PENDENTE, **extra):
    return Variacao.objects.create(
        produto=produto, sku=sku, nome=nome, preco=preco, estoque=estoque, status=status, **extra
    )


class ProdutosEspelhoTests(TestCase):
    def setUp(self):
        self.client = _client_autenticado()
        self.instancia = Instancia.objects.create(nome="Loja A")
        self.outra = Instancia.objects.create(nome="Loja B")

    def _url(self, instancia=None):
        return f"/api/instancias/{(instancia or self.instancia).slug}/produtos/"

    def test_exige_autenticacao(self):
        resposta = APIClient().get(self._url())
        self.assertEqual(resposta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_slug_inexistente_404(self):
        resposta = self.client.get("/api/instancias/nao-existe/produtos/")
        self.assertEqual(resposta.status_code, status.HTTP_404_NOT_FOUND)

    def test_isolamento_por_instancia(self):
        _variacao(_produto(self.instancia, codigo_pai="a1"), sku="SKU-A")
        _variacao(_produto(self.outra, codigo_pai="b1"), sku="SKU-B")

        resposta = self.client.get(self._url())
        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        skus = [linha["sku"] for linha in resposta.data["results"]]
        self.assertEqual(skus, ["SKU-A"])
        self.assertEqual(resposta.data["count"], 1)

        # E a rota da outra instância nunca devolve as variações da primeira.
        resposta_outra = self.client.get(self._url(self.outra))
        self.assertEqual([linha["sku"] for linha in resposta_outra.data["results"]], ["SKU-B"])

    def test_paginacao_no_servidor(self):
        produto = _produto(self.instancia)
        for i in range(25):
            _variacao(produto, sku=f"SKU-{i:02d}")

        pagina1 = self.client.get(self._url(), {"page_size": 10})
        self.assertEqual(pagina1.data["count"], 25)
        self.assertEqual(len(pagina1.data["results"]), 10)
        self.assertIsNotNone(pagina1.data["next"])

        pagina3 = self.client.get(self._url(), {"page_size": 10, "page": 3})
        self.assertEqual(len(pagina3.data["results"]), 5)
        self.assertIsNone(pagina3.data["next"])

    def test_busca_por_sku_e_codigo_pai_e_nome(self):
        p1 = _produto(self.instancia, codigo_pai="CANECA-01", nome="Caneca de porcelana")
        p2 = _produto(self.instancia, codigo_pai="CAMISA-09", nome="Camiseta algodão")
        _variacao(p1, sku="CN-01-AZUL", nome="Caneca azul")
        _variacao(p2, sku="CM-09-P", nome="Camiseta P")

        por_sku = self.client.get(self._url(), {"busca": "CN-01"})
        self.assertEqual([l["sku"] for l in por_sku.data["results"]], ["CN-01-AZUL"])

        por_codigo_pai = self.client.get(self._url(), {"busca": "CAMISA-09"})
        self.assertEqual([l["sku"] for l in por_codigo_pai.data["results"]], ["CM-09-P"])

        por_nome_produto = self.client.get(self._url(), {"busca": "porcelana"})
        self.assertEqual([l["sku"] for l in por_nome_produto.data["results"]], ["CN-01-AZUL"])

    def test_filtro_por_fornecedor(self):
        _variacao(_produto(self.instancia, fornecedor=Fornecedor.XBZ, codigo_pai="x1"), sku="X-1")
        _variacao(_produto(self.instancia, fornecedor=Fornecedor.SPOT, codigo_pai="s1"), sku="S-1")

        resposta = self.client.get(self._url(), {"fornecedor": Fornecedor.SPOT})
        self.assertEqual([l["sku"] for l in resposta.data["results"]], ["S-1"])

    def test_filtro_por_status(self):
        produto = _produto(self.instancia)
        _variacao(produto, sku="OK-1", estoque=3, status=StatusVariacao.CADASTRADO)
        _variacao(produto, sku="ESP-1", estoque=0, status=StatusVariacao.AGUARDANDO)

        resposta = self.client.get(self._url(), {"status": StatusVariacao.CADASTRADO})
        self.assertEqual([l["sku"] for l in resposta.data["results"]], ["OK-1"])

    def test_filtro_invalido_e_ignorado(self):
        _variacao(_produto(self.instancia), sku="SKU-1")
        resposta = self.client.get(self._url(), {"fornecedor": "inexistente", "status": "qualquer"})
        self.assertEqual(resposta.data["count"], 1)

    def test_resposta_traz_dados_do_produto_pai_e_da_variacao(self):
        produto = _produto(self.instancia, fornecedor=Fornecedor.XBZ, codigo_pai="CANECA-01", nome="Caneca")
        _variacao(
            produto,
            sku="CN-01-AZUL",
            nome="Caneca azul 300ml",
            preco="19.90",
            estoque=7,
            status=StatusVariacao.CADASTRADO,
            cor="Azul",
            tamanho="300ml",
            tiny_id="tiny-123",
        )

        linha = self.client.get(self._url()).data["results"][0]
        self.assertEqual(linha["fornecedor"], Fornecedor.XBZ)
        self.assertEqual(linha["produto_codigo_pai"], "CANECA-01")
        self.assertEqual(linha["produto_nome"], "Caneca")
        self.assertEqual(linha["sku"], "CN-01-AZUL")
        self.assertEqual(linha["cor"], "Azul")
        self.assertEqual(linha["tamanho"], "300ml")
        self.assertEqual(linha["preco"], "19.90")
        self.assertEqual(linha["estoque"], 7)
        self.assertEqual(linha["status"], StatusVariacao.CADASTRADO)
        self.assertEqual(linha["status_rotulo"], "Cadastrado no Tiny")
        self.assertEqual(linha["tiny_id"], "tiny-123")

    def test_sem_n_mais_1(self):
        produto = _produto(self.instancia)
        for i in range(3):
            _variacao(produto, sku=f"SKU-{i}")

        with CaptureQueriesContext(connection) as ctx:
            self.client.get(self._url(), {"page_size": 50})
        consultas_com_3 = len(ctx.captured_queries)

        for i in range(3, 12):
            _variacao(produto, sku=f"SKU-{i}")

        with CaptureQueriesContext(connection) as ctx:
            self.client.get(self._url(), {"page_size": 50})
        consultas_com_12 = len(ctx.captured_queries)

        self.assertEqual(consultas_com_3, consultas_com_12)
