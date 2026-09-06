from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from ..models import Instancia


class AutenticacaoObrigatoriaTests(TestCase):
    """Passo 5: toda a API exige token, exceto o callback do Tiny."""

    def setUp(self):
        self.client = APIClient()
        self.usuario = get_user_model().objects.create_user(
            email="operador@example.com", password="senha-forte"
        )
        self.token = Token.objects.create(user=self.usuario)

    def test_listar_instancias_sem_token_e_barrado(self):
        resposta = self.client.get("/api/instancias/")
        self.assertEqual(resposta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_criar_instancia_sem_token_e_barrado(self):
        resposta = self.client.post(
            "/api/instancias/", {"nome": "Loja", "client_id": "x", "client_secret": "y"}
        )
        self.assertEqual(resposta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_autorizar_e_desconectar_sem_token_sao_barrados(self):
        instancia = Instancia.objects.create(nome="Loja Protegida")
        self.assertEqual(
            self.client.get(f"/api/instancias/{instancia.slug}/autorizar/").status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.assertEqual(
            self.client.post(f"/api/instancias/{instancia.slug}/desconectar/").status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def test_com_token_valido_acesso_e_liberado(self):
        self.client.credentials(HTTP_AUTHORIZATION=f"Token {self.token.key}")
        resposta = self.client.get("/api/instancias/")
        self.assertEqual(resposta.status_code, status.HTTP_200_OK)

    def test_token_invalido_e_barrado(self):
        self.client.credentials(HTTP_AUTHORIZATION="Token token-que-nao-existe")
        resposta = self.client.get("/api/instancias/")
        self.assertEqual(resposta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_callback_do_tiny_continua_publico_sem_token(self):
        """A única exceção: o callback é chamado pelo Tiny, não pelo nosso frontend."""
        instancia = Instancia.objects.create(nome="Loja Callback Publico")
        resposta = self.client.get(f"/api/tiny/oauth/callback/{instancia.slug}/")
        # sem state válido, o callback redireciona de volta pro wizard (passo 10) —
        # nunca 401: a rota em si é pública, e nunca 400: quem chama é o navegador,
        # não um cliente de API.
        self.assertEqual(resposta.status_code, status.HTTP_302_FOUND)
        self.assertIn(f"/instancias/novo?slug={instancia.slug}&erro=1", resposta["Location"])
