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
    usuario = get_user_model().objects.create_user(
        email="operador-detalhe@example.com", password="x"
    )
    token = Token.objects.create(user=usuario)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


class VariacaoDetalheTests(TestCase):
    def setUp(self):
        self.client = _client_autenticado()
        self.instancia = Instancia.objects.create(nome="Loja A")
        self.outra = Instancia.objects.create(nome="Loja B")
        self.produto = Produto.objects.create(
            instancia=self.instancia,
            fornecedor=Fornecedor.XBZ,
            codigo_pai="CANECA-01",
            nome="Caneca de porcelana",
            descricao="Caneca de porcelana 300ml.",
            categorias=["Canecas"],
            imagens=["https://cdn.exemplo.com/produto/caneca.jpg"],
        )
        self.variacao = Variacao.objects.create(
            produto=self.produto,
            sku="CN-01-AZUL",
            nome="Caneca azul 300ml",
            ncm="69120000",
            preco="19.90",
            estoque=7,
            cor="Azul",
            tamanho="300ml",
            largura=8.0,
            altura=10.5,
            peso_bruto=0.42,
            imagens=[
                "https://cdn.exemplo.com/caneca-azul-1.jpg",
                "https://cdn.exemplo.com/caneca-azul-2.jpg",
            ],
            atributos={"material": "porcelana", "taric": "6912.00.00"},
            status=StatusVariacao.CADASTRADO,
            tiny_id="tiny-123",
            payload_bruto={"segredo_interno": "nao deve vazar", "x": 1},
        )

    def _url(self, variacao_id, instancia=None):
        slug = (instancia or self.instancia).slug
        return f"/api/instancias/{slug}/produtos/{variacao_id}/"

    def test_exige_autenticacao(self):
        resposta = APIClient().get(self._url(self.variacao.id))
        self.assertEqual(resposta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_detalhe_existente_traz_produto_e_variacao(self):
        resposta = self.client.get(self._url(self.variacao.id))
        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        dados = resposta.data

        self.assertEqual(dados["id"], self.variacao.id)
        self.assertEqual(dados["fornecedor"], Fornecedor.XBZ)
        self.assertEqual(dados["fornecedor_rotulo"], "XBZ")
        self.assertEqual(dados["produto_id"], self.produto.id)
        self.assertEqual(dados["produto_codigo_pai"], "CANECA-01")
        self.assertEqual(dados["produto_nome"], "Caneca de porcelana")
        self.assertEqual(dados["produto_descricao"], "Caneca de porcelana 300ml.")
        self.assertEqual(dados["produto_categorias"], ["Canecas"])
        self.assertEqual(dados["sku"], "CN-01-AZUL")
        self.assertEqual(dados["nome"], "Caneca azul 300ml")
        self.assertEqual(dados["ncm"], "69120000")
        self.assertEqual(dados["preco"], "19.90")
        self.assertEqual(dados["estoque"], 7)
        self.assertEqual(dados["cor"], "Azul")
        self.assertEqual(dados["tamanho"], "300ml")
        self.assertEqual(dados["largura"], 8.0)
        self.assertEqual(dados["altura"], 10.5)
        self.assertEqual(dados["peso_bruto"], 0.42)
        self.assertEqual(dados["atributos"], {"material": "porcelana", "taric": "6912.00.00"})
        self.assertEqual(dados["status"], StatusVariacao.CADASTRADO)
        self.assertEqual(dados["status_rotulo"], "Cadastrado no Tiny")
        self.assertEqual(dados["tiny_id"], "tiny-123")

    def test_multiplas_imagens_preservadas_na_ordem(self):
        dados = self.client.get(self._url(self.variacao.id)).data
        self.assertEqual(
            dados["imagens"],
            [
                "https://cdn.exemplo.com/caneca-azul-1.jpg",
                "https://cdn.exemplo.com/caneca-azul-2.jpg",
            ],
        )
        self.assertEqual(dados["produto_imagens"], ["https://cdn.exemplo.com/produto/caneca.jpg"])

    def test_nao_expoe_payload_bruto(self):
        dados = self.client.get(self._url(self.variacao.id)).data
        self.assertNotIn("payload_bruto", dados)
        self.assertNotIn("nao deve vazar", str(dados))

    def test_campos_opcionais_ausentes_nao_quebram(self):
        produto = Produto.objects.create(
            instancia=self.instancia, fornecedor=Fornecedor.SPOT, codigo_pai="s1", nome="Item Spot"
        )
        magra = Variacao.objects.create(
            produto=produto, sku="S-1", nome="Item Spot", preco="1.00", estoque=0
        )
        dados = self.client.get(self._url(magra.id)).data
        self.assertEqual(dados["cor"], "")
        self.assertIsNone(dados["largura"])
        self.assertIsNone(dados["diametro"])
        self.assertIsNone(dados["peso_liquido"])
        self.assertEqual(dados["atributos"], {})
        self.assertEqual(dados["imagens"], [])
        self.assertIsNone(dados["tiny_id"])
        self.assertIsNone(dados["cadastrado_em"])

    def test_variacao_de_outra_instancia_nao_e_acessivel(self):
        outro_produto = Produto.objects.create(
            instancia=self.outra, fornecedor=Fornecedor.XBZ, codigo_pai="b1", nome="Outra"
        )
        alheia = Variacao.objects.create(
            produto=outro_produto, sku="B-1", nome="Outra", preco="1.00", estoque=1
        )
        # pedindo pelo slug da instância A o id de uma variação da B
        resposta = self.client.get(self._url(alheia.id))
        self.assertEqual(resposta.status_code, status.HTTP_404_NOT_FOUND)
        # e pelo próprio slug dela continua acessível
        self.assertEqual(
            self.client.get(self._url(alheia.id, instancia=self.outra)).status_code,
            status.HTTP_200_OK,
        )

    def test_variacao_inexistente_404(self):
        resposta = self.client.get(self._url(999999))
        self.assertEqual(resposta.status_code, status.HTTP_404_NOT_FOUND)

    def test_slug_inexistente_404(self):
        resposta = self.client.get(f"/api/instancias/nao-existe/produtos/{self.variacao.id}/")
        self.assertEqual(resposta.status_code, status.HTTP_404_NOT_FOUND)

    def test_query_eficiente_sem_n_mais_1(self):
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(self._url(self.variacao.id))
        # auth (usuário + token) + a variação com produto/instância via
        # select_related. Folga pequena; o que não pode é escalar por campo.
        self.assertLessEqual(len(ctx.captured_queries), 4)
