from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from ..models import Instancia
from ..tiny_oauth import TinyOAuthError

CAMPOS_PROIBIDOS = {"client_secret", "access_token", "refresh_token"}


def _client_autenticado():
    """Todas as rotas (exceto o callback) exigem token desde o passo 5."""
    usuario = get_user_model().objects.create_user(email="operador-teste@example.com", password="x")
    token = Token.objects.create(user=usuario)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


class InstanciaEndpointsCrudTests(TestCase):
    def setUp(self):
        self.client = _client_autenticado()

    def test_criar_instancia(self):
        resposta = self.client.post(
            "/api/instancias/",
            {"nome": "Loja Nova", "client_id": "cid-123", "client_secret": "segredo-123"},
        )
        self.assertEqual(resposta.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resposta.data["nome"], "Loja Nova")
        self.assertTrue(resposta.data["slug"])
        self.assertFalse(CAMPOS_PROIBIDOS & resposta.data.keys())

        instancia = Instancia.objects.get(slug=resposta.data["slug"])
        self.assertEqual(instancia.client_secret, "segredo-123")

    def test_criar_sem_client_secret_falha(self):
        resposta = self.client.post("/api/instancias/", {"nome": "Loja Incompleta", "client_id": "cid"})
        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_listar_instancias(self):
        Instancia.objects.create(nome="Loja 1")
        Instancia.objects.create(nome="Loja 2")
        resposta = self.client.get("/api/instancias/")
        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        self.assertEqual(resposta.data["count"], 2)
        self.assertEqual(len(resposta.data["results"]), 2)

    def test_detalhe_inclui_status_da_conexao_e_url_callback(self):
        instancia = Instancia.objects.create(nome="Loja Detalhe")
        resposta = self.client.get(f"/api/instancias/{instancia.slug}/")
        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        self.assertEqual(resposta.data["status"], "nao_conectado")
        self.assertIn(f"/api/tiny/oauth/callback/{instancia.slug}/", resposta.data["url_callback"])
        self.assertFalse(CAMPOS_PROIBIDOS & resposta.data.keys())

    def test_resposta_nunca_inclui_tokens_mesmo_quando_preenchidos(self):
        instancia = Instancia.objects.create(nome="Loja com Tokens")
        instancia.aplicar_tokens(
            access_token="segredo-acesso",
            refresh_token="segredo-refresh",
            expires_in=3600,
            refresh_expires_in=7200,
        )
        resposta = self.client.get(f"/api/instancias/{instancia.slug}/")
        self.assertFalse(CAMPOS_PROIBIDOS & resposta.data.keys())
        conteudo = str(resposta.content)
        self.assertNotIn("segredo-acesso", conteudo)
        self.assertNotIn("segredo-refresh", conteudo)
        self.assertTrue(resposta.data["access_token_preenchido"])
        self.assertTrue(resposta.data["refresh_token_preenchido"])

    def test_patch_atualiza_credenciais(self):
        instancia = Instancia.objects.create(nome="Loja Patch", client_id="antigo")
        resposta = self.client.patch(
            f"/api/instancias/{instancia.slug}/", {"client_id": "novo-cid"}, format="json"
        )
        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        instancia.refresh_from_db()
        self.assertEqual(instancia.client_id, "novo-cid")

    def test_delete_remove_instancia(self):
        instancia = Instancia.objects.create(nome="Loja pra Apagar")
        resposta = self.client.delete(f"/api/instancias/{instancia.slug}/")
        self.assertEqual(resposta.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(Instancia.objects.filter(pk=instancia.pk).exists())


class AutorizarActionTests(TestCase):
    def setUp(self):
        self.client = _client_autenticado()

    def test_autorizar_sem_credenciais_retorna_400(self):
        instancia = Instancia.objects.create(nome="Loja Sem Credencial")
        resposta = self.client.get(f"/api/instancias/{instancia.slug}/autorizar/")
        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_autorizar_gera_state_novo_e_url_de_autorizacao(self):
        instancia = Instancia.objects.create(nome="Loja Pronta", client_id="cid", client_secret="csecret")
        resposta = self.client.get(f"/api/instancias/{instancia.slug}/autorizar/")
        self.assertEqual(resposta.status_code, status.HTTP_200_OK)

        instancia.refresh_from_db()
        self.assertTrue(instancia.oauth_state)
        self.assertIsNotNone(instancia.oauth_state_expira_em)
        self.assertIn(instancia.oauth_state, resposta.data["url_autorizacao"])
        self.assertIn("client_id=cid", resposta.data["url_autorizacao"])

    def test_cada_chamada_a_autorizar_gera_um_state_diferente(self):
        instancia = Instancia.objects.create(nome="Loja Dupla", client_id="cid", client_secret="csecret")
        r1 = self.client.get(f"/api/instancias/{instancia.slug}/autorizar/")
        state_1 = Instancia.objects.get(pk=instancia.pk).oauth_state
        r2 = self.client.get(f"/api/instancias/{instancia.slug}/autorizar/")
        state_2 = Instancia.objects.get(pk=instancia.pk).oauth_state
        self.assertNotEqual(state_1, state_2)


class DesconectarActionTests(TestCase):
    def setUp(self):
        self.client = _client_autenticado()

    def test_desconectar_limpa_tokens_e_volta_para_nao_conectado(self):
        instancia = Instancia.objects.create(nome="Loja Conectada")
        instancia.aplicar_tokens(access_token="a", refresh_token="r", expires_in=3600, refresh_expires_in=7200)

        resposta = self.client.post(f"/api/instancias/{instancia.slug}/desconectar/")
        self.assertEqual(resposta.status_code, status.HTTP_200_OK)

        instancia.refresh_from_db()
        self.assertEqual(instancia.access_token, "")
        self.assertEqual(instancia.refresh_token, "")
        self.assertEqual(instancia.status, Instancia.Status.NAO_CONECTADO)
        self.assertTrue(instancia.ja_foi_autorizada)  # slug continua travado


class TinyOAuthCallbackTests(TestCase):
    """Regra de segurança: state ausente ou divergente é rejeitado, mesmo com o slug correto."""

    def setUp(self):
        self.client = APIClient()
        self.instancia = Instancia.objects.create(
            nome="Loja Callback", client_id="cid", client_secret="csecret"
        )

    def _url(self, **query):
        url = reverse("tiny-oauth-callback", kwargs={"slug": self.instancia.slug})
        if query:
            from urllib.parse import urlencode

            url = f"{url}?{urlencode(query)}"
        return url

    def _definir_state(self, state, expira_em=None):
        self.instancia.oauth_state = state
        self.instancia.oauth_state_expira_em = expira_em or (timezone.now() + timedelta(minutes=10))
        self.instancia.save()

    def test_callback_sem_state_e_rejeitado(self):
        self._definir_state("state-correto")
        resposta = self.client.get(self._url(code="algum-code"))
        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_callback_com_state_divergente_e_rejeitado_mesmo_com_slug_correto(self):
        self._definir_state("state-correto")
        resposta = self.client.get(self._url(code="algum-code", state="state-errado"))
        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)

        self.instancia.refresh_from_db()
        # nada foi trocado — o state salvo nem foi consumido nessa tentativa inválida
        self.assertEqual(self.instancia.access_token, "")

    def test_callback_com_state_expirado_e_rejeitado(self):
        self._definir_state("state-correto", expira_em=timezone.now() - timedelta(seconds=1))
        resposta = self.client.get(self._url(code="algum-code", state="state-correto"))
        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_callback_com_slug_inexistente_retorna_404(self):
        url = reverse("tiny-oauth-callback", kwargs={"slug": "slug-que-nao-existe"})
        resposta = self.client.get(f"{url}?code=x&state=y")
        self.assertEqual(resposta.status_code, status.HTTP_404_NOT_FOUND)

    @patch("apps.instancias.views.trocar_code_por_token")
    def test_callback_com_state_correto_troca_code_por_token_e_consome_o_state(self, mock_trocar):
        self._definir_state("state-correto")
        mock_trocar.return_value = {
            "access_token": "access-final",
            "refresh_token": "refresh-final",
            "expires_in": 3600,
            "refresh_expires_in": 7200,
        }

        resposta = self.client.get(self._url(code="code-valido", state="state-correto"))

        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        self.instancia.refresh_from_db()
        self.assertEqual(self.instancia.access_token, "access-final")
        self.assertEqual(self.instancia.status, Instancia.Status.CONECTADO)
        self.assertEqual(self.instancia.oauth_state, "")  # state consumido, não reaproveitável
        self.assertFalse(CAMPOS_PROIBIDOS & resposta.data.keys())

    @patch("apps.instancias.views.trocar_code_por_token")
    def test_callback_com_erro_do_tiny_marca_status_erro(self, mock_trocar):
        self._definir_state("state-correto")
        mock_trocar.side_effect = TinyOAuthError("code inválido")

        resposta = self.client.get(self._url(code="code-invalido", state="state-correto"))

        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)
        self.instancia.refresh_from_db()
        self.assertEqual(self.instancia.status, Instancia.Status.ERRO)
        self.assertEqual(self.instancia.ultimo_erro, "code inválido")
