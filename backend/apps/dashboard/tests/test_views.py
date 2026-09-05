from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient


def _client_autenticado():
    usuario = get_user_model().objects.create_user(email="operador@example.com", password="x")
    token = Token.objects.create(user=usuario)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


class DashboardEndpointsTests(TestCase):
    def setUp(self):
        self.client = _client_autenticado()

    def test_resumo_exige_autenticacao(self):
        resposta = APIClient().get("/api/dashboard/resumo/")
        self.assertEqual(resposta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_resumo_devolve_as_quatro_secoes(self):
        resposta = self.client.get("/api/dashboard/resumo/")
        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        self.assertEqual(
            set(resposta.data.keys()),
            {"periodo", "instancias", "produtos_sincronizados", "execucoes_24h", "alertas"},
        )

    def test_resumo_periodo_invalido_cai_para_hoje(self):
        resposta = self.client.get("/api/dashboard/resumo/?periodo=invalido")
        self.assertEqual(resposta.data["periodo"], "hoje")

    def test_alertas_exige_autenticacao_e_devolve_lista_vazia_sem_dados(self):
        anonimo = APIClient().get("/api/dashboard/alertas/")
        self.assertEqual(anonimo.status_code, status.HTTP_401_UNAUTHORIZED)

        resposta = self.client.get("/api/dashboard/alertas/")
        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        self.assertEqual(resposta.data, [])

    def test_atividade_exige_autenticacao_e_respeita_limit(self):
        anonimo = APIClient().get("/api/dashboard/atividade/")
        self.assertEqual(anonimo.status_code, status.HTTP_401_UNAUTHORIZED)

        resposta = self.client.get("/api/dashboard/atividade/?limit=5")
        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        self.assertEqual(resposta.data, [])
