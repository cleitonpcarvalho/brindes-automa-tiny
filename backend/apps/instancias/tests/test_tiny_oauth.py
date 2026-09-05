import base64
from unittest.mock import Mock, patch

from django.test import TestCase

from ..tiny_oauth import (
    TinyOAuthError,
    montar_url_autorizacao,
    renovar_com_refresh_token,
    trocar_code_por_token,
)


def _resposta_ok(corpo):
    resposta = Mock()
    resposta.status_code = 200
    resposta.json.return_value = corpo
    return resposta


def _resposta_erro(status_code, corpo):
    resposta = Mock()
    resposta.status_code = status_code
    resposta.json.return_value = corpo
    resposta.text = str(corpo)
    return resposta


class MontarUrlAutorizacaoTests(TestCase):
    def test_url_inclui_client_id_redirect_uri_e_state(self):
        url = montar_url_autorizacao("meu-client-id", "https://exemplo.com/callback/loja/", "state-123")
        self.assertIn("client_id=meu-client-id", url)
        self.assertIn("state=state-123", url)
        self.assertIn("response_type=code", url)
        self.assertIn("redirect_uri=https%3A%2F%2Fexemplo.com%2Fcallback%2Floja%2F", url)


class TrocarCodePorTokenTests(TestCase):
    @patch("apps.instancias.tiny_oauth.requests.post")
    def test_troca_bem_sucedida_grava_o_authorization_header_basic_correto(self, mock_post):
        mock_post.return_value = _resposta_ok(
            {
                "access_token": "novo-access",
                "refresh_token": "novo-refresh",
                "expires_in": 3600,
                "refresh_expires_in": 1800,
            }
        )

        resultado = trocar_code_por_token("cid", "csecret", "code-recebido", "https://x.com/cb/")

        self.assertEqual(resultado["access_token"], "novo-access")
        self.assertEqual(resultado["refresh_token"], "novo-refresh")

        _, kwargs = mock_post.call_args
        esperado = base64.b64encode(b"cid:csecret").decode("ascii")
        self.assertEqual(kwargs["headers"]["Authorization"], f"Basic {esperado}")
        self.assertEqual(kwargs["data"]["grant_type"], "authorization_code")
        self.assertEqual(kwargs["data"]["code"], "code-recebido")
        self.assertEqual(kwargs["data"]["redirect_uri"], "https://x.com/cb/")

    @patch("apps.instancias.tiny_oauth.requests.post")
    def test_erro_do_keycloak_levanta_tinyoautherror(self, mock_post):
        mock_post.return_value = _resposta_erro(
            400, {"error": "invalid_grant", "error_description": "Code not valid"}
        )

        with self.assertRaises(TinyOAuthError):
            trocar_code_por_token("cid", "csecret", "code-invalido", "https://x.com/cb/")

    @patch("apps.instancias.tiny_oauth.requests.post")
    def test_resposta_sem_campos_esperados_levanta_erro(self, mock_post):
        mock_post.return_value = _resposta_ok({"access_token": "só isso"})

        with self.assertRaises(TinyOAuthError):
            trocar_code_por_token("cid", "csecret", "code", "https://x.com/cb/")


class RenovarComRefreshTokenTests(TestCase):
    """
    O Keycloak rotaciona o refresh_token a cada renovação e invalida o
    anterior — o resultado da renovação deve trazer um refresh_token novo,
    diferente do usado na chamada.
    """

    @patch("apps.instancias.tiny_oauth.requests.post")
    def test_renovacao_devolve_um_refresh_token_diferente_do_anterior(self, mock_post):
        refresh_antigo = "refresh-antigo"
        mock_post.return_value = _resposta_ok(
            {
                "access_token": "access-renovado",
                "refresh_token": "refresh-novo-rotacionado",
                "expires_in": 3600,
                "refresh_expires_in": 1800,
            }
        )

        resultado = renovar_com_refresh_token("cid", "csecret", refresh_antigo)

        self.assertNotEqual(resultado["refresh_token"], refresh_antigo)
        self.assertEqual(resultado["refresh_token"], "refresh-novo-rotacionado")

        _, kwargs = mock_post.call_args
        self.assertEqual(kwargs["data"]["grant_type"], "refresh_token")
        self.assertEqual(kwargs["data"]["refresh_token"], refresh_antigo)
