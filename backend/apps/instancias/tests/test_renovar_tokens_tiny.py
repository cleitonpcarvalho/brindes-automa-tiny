from datetime import timedelta
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from ..models import Instancia
from ..tiny_oauth import TinyOAuthError


def _instancia_conectada(**kwargs):
    agora = timezone.now()
    dados = {
        "nome": "Loja Conectada",
        "client_id": "cid",
        "client_secret": "csecret",
        "access_token": "access-atual",
        "refresh_token": "refresh-atual",
        "status": Instancia.Status.CONECTADO,
        "token_emitido_em": agora - timedelta(seconds=3600),
        "token_expira_em": agora + timedelta(seconds=1),  # praticamente 100% decorrido -> renova
        "refresh_expira_em": agora + timedelta(days=30),
    }
    dados.update(kwargs)
    return Instancia.objects.create(**dados)


class RenovacaoComRotacaoDeRefreshTests(TestCase):
    @patch("apps.instancias.management.commands.renovar_tokens_tiny.renovar_com_refresh_token")
    def test_renovacao_bem_sucedida_grava_o_novo_par_e_substitui_o_refresh_antigo(self, mock_renovar):
        instancia = _instancia_conectada()
        refresh_antigo = instancia.refresh_token

        mock_renovar.return_value = {
            "access_token": "access-novo",
            "refresh_token": "refresh-novo-rotacionado",
            "expires_in": 3600,
            "refresh_expires_in": 2592000,
        }

        call_command("renovar_tokens_tiny")

        instancia.refresh_from_db()
        self.assertEqual(instancia.access_token, "access-novo")
        self.assertEqual(instancia.refresh_token, "refresh-novo-rotacionado")
        self.assertNotEqual(instancia.refresh_token, refresh_antigo)
        self.assertEqual(instancia.status, Instancia.Status.CONECTADO)
        self.assertEqual(instancia.tentativas_falha, 0)

    @patch("apps.instancias.management.commands.renovar_tokens_tiny.renovar_com_refresh_token")
    def test_instancia_longe_de_70_por_cento_nao_e_renovada(self, mock_renovar):
        agora = timezone.now()
        _instancia_conectada(
            token_emitido_em=agora - timedelta(seconds=10),
            token_expira_em=agora + timedelta(seconds=90),  # 10% decorrido
        )

        call_command("renovar_tokens_tiny")

        mock_renovar.assert_not_called()


class TresFalhasSeguidasTests(TestCase):
    @patch("apps.instancias.management.commands.renovar_tokens_tiny.renovar_com_refresh_token")
    def test_terceira_falha_seguida_muda_status_para_erro_e_para_de_tentar(self, mock_renovar):
        instancia = _instancia_conectada()
        mock_renovar.side_effect = TinyOAuthError("Tiny recusou: invalid_grant")

        call_command("renovar_tokens_tiny")
        instancia.refresh_from_db()
        self.assertEqual(instancia.tentativas_falha, 1)
        self.assertEqual(instancia.status, Instancia.Status.CONECTADO)

        call_command("renovar_tokens_tiny")
        instancia.refresh_from_db()
        self.assertEqual(instancia.tentativas_falha, 2)
        self.assertEqual(instancia.status, Instancia.Status.CONECTADO)

        call_command("renovar_tokens_tiny")
        instancia.refresh_from_db()
        self.assertEqual(instancia.tentativas_falha, 3)
        self.assertEqual(instancia.status, Instancia.Status.ERRO)

        # a 4ª rodada nem tenta mais: a instância já não está mais em status=conectado
        mock_renovar.reset_mock()
        call_command("renovar_tokens_tiny")
        mock_renovar.assert_not_called()

    @patch("apps.instancias.management.commands.renovar_tokens_tiny.renovar_com_refresh_token")
    def test_falha_grava_ultimo_erro(self, mock_renovar):
        instancia = _instancia_conectada()
        mock_renovar.side_effect = TinyOAuthError("motivo específico da falha")

        call_command("renovar_tokens_tiny")

        instancia.refresh_from_db()
        self.assertEqual(instancia.ultimo_erro, "motivo específico da falha")


class RefreshTokenExpiradoTests(TestCase):
    @patch("apps.instancias.management.commands.renovar_tokens_tiny.renovar_com_refresh_token")
    def test_refresh_expirado_marca_para_reautorizacao_sem_chamar_a_api(self, mock_renovar):
        instancia = _instancia_conectada(refresh_expira_em=timezone.now() - timedelta(seconds=1))

        call_command("renovar_tokens_tiny")

        mock_renovar.assert_not_called()
        instancia.refresh_from_db()
        self.assertEqual(instancia.status, Instancia.Status.ERRO)
        self.assertIn("autorizar novamente", instancia.ultimo_erro)


class OutraInstanciaNaoAfetadaTests(TestCase):
    """Uma instância com problema não pode impedir a renovação das demais."""

    @patch("apps.instancias.management.commands.renovar_tokens_tiny.renovar_com_refresh_token")
    def test_falha_em_uma_instancia_nao_impede_renovacao_de_outra(self, mock_renovar):
        instancia_com_falha = _instancia_conectada(nome="Loja A", refresh_token="refresh-a")
        instancia_ok = _instancia_conectada(nome="Loja B", refresh_token="refresh-b")

        def side_effect(client_id, client_secret, refresh_token):
            if refresh_token == instancia_com_falha.refresh_token:
                raise TinyOAuthError("falhou")
            return {
                "access_token": "novo-access-b",
                "refresh_token": "novo-refresh-b",
                "expires_in": 3600,
                "refresh_expires_in": 2592000,
            }

        mock_renovar.side_effect = side_effect

        call_command("renovar_tokens_tiny")

        instancia_com_falha.refresh_from_db()
        instancia_ok.refresh_from_db()
        self.assertEqual(instancia_com_falha.tentativas_falha, 1)
        self.assertEqual(instancia_ok.access_token, "novo-access-b")
        self.assertEqual(instancia_ok.tentativas_falha, 0)
