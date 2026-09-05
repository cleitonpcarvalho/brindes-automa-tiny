from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient


class LoginViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.user = get_user_model().objects.create_user(
            email="operador@example.com", password="senha-forte", nome="Operador"
        )

    def test_login_com_credenciais_corretas_devolve_token(self):
        resposta = self.client.post(
            "/api/auth/login/",
            {"email": "operador@example.com", "password": "senha-forte"},
            format="json",
        )
        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        self.assertEqual(resposta.data["email"], "operador@example.com")
        self.assertEqual(resposta.data["nome"], "Operador")
        self.assertTrue(Token.objects.filter(key=resposta.data["token"], user=self.user).exists())

    def test_login_com_senha_errada_e_rejeitado(self):
        resposta = self.client.post(
            "/api/auth/login/",
            {"email": "operador@example.com", "password": "errada"},
            format="json",
        )
        self.assertEqual(resposta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_com_email_inexistente_e_rejeitado(self):
        resposta = self.client.post(
            "/api/auth/login/",
            {"email": "nao-existe@example.com", "password": "qualquer"},
            format="json",
        )
        self.assertEqual(resposta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_login_reaproveita_token_existente(self):
        token_existente = Token.objects.create(user=self.user)
        resposta = self.client.post(
            "/api/auth/login/",
            {"email": "operador@example.com", "password": "senha-forte"},
            format="json",
        )
        self.assertEqual(resposta.data["token"], token_existente.key)


class LogoutViewTests(TestCase):
    def test_logout_apaga_o_token(self):
        user = get_user_model().objects.create_user(email="operador2@example.com", password="x")
        token = Token.objects.create(user=user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        resposta = client.post("/api/auth/logout/")

        self.assertEqual(resposta.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Token.objects.filter(key=token.key).exists())

    def test_logout_sem_token_e_barrado(self):
        client = APIClient()
        resposta = client.post("/api/auth/logout/")
        self.assertEqual(resposta.status_code, status.HTTP_401_UNAUTHORIZED)


class MeViewTests(TestCase):
    def test_me_devolve_usuario_autenticado(self):
        user = get_user_model().objects.create_user(
            email="op3@example.com", password="x", nome="Operador Três"
        )
        token = Token.objects.create(user=user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")

        resposta = client.get("/api/auth/me/")

        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        self.assertEqual(resposta.data, {"email": "op3@example.com", "nome": "Operador Três"})

    def test_me_com_token_invalido_e_barrado(self):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION="Token token-invalido")
        resposta = client.get("/api/auth/me/")
        self.assertEqual(resposta.status_code, status.HTTP_401_UNAUTHORIZED)
