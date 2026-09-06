from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework import status

from apps.sincronizacao.models import Execucao, StatusExecucao, TipoExecucao

from ..models import CredencialFornecedor, Instancia
from .test_views import _client_autenticado


class SincronizarFornecedorViewTests(TestCase):
    def setUp(self):
        self.client = _client_autenticado()
        self.instancia = Instancia.objects.create(nome="Loja Sincronizar")

    def _url(self, fornecedor):
        return f"/api/instancias/{self.instancia.slug}/fornecedores/{fornecedor}/sincronizar/"

    def test_sem_credencial_ativa_retorna_400(self):
        resposta = self.client.post(self._url("xbz"))
        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_xbz_ja_rodou_hoje_retorna_400(self):
        CredencialFornecedor.objects.create(
            instancia=self.instancia, fornecedor="xbz", credenciais={"cnpj": "1", "token": "2"}, ativo=True
        )
        Execucao.objects.create(
            instancia=self.instancia,
            fornecedor="xbz",
            tipo=TipoExecucao.INCREMENTAL,
            status=StatusExecucao.SUCESSO,
        )
        resposta = self.client.post(self._url("xbz"))
        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)

    @patch("apps.instancias.views.executar_sincronizacao_manual_task")
    def test_sucesso_cria_execucao_e_enfileira_devolvendo_o_id(self, mock_task):
        CredencialFornecedor.objects.create(
            instancia=self.instancia, fornecedor="asia", credenciais={"api_key": "a", "secret_key": "b"}, ativo=True
        )
        resposta = self.client.post(self._url("asia"))

        self.assertEqual(resposta.status_code, status.HTTP_202_ACCEPTED)
        self.assertIn("execucao_id", resposta.data)
        self.assertEqual(resposta.data["status"], StatusExecucao.RODANDO)

        execucao = Execucao.objects.get(pk=resposta.data["execucao_id"])
        self.assertEqual(execucao.instancia, self.instancia)
        self.assertEqual(execucao.fornecedor, "asia")
        self.assertEqual(execucao.status, StatusExecucao.RODANDO)
        mock_task.delay.assert_called_once_with(execucao.id)

    @patch("apps.instancias.views.executar_sincronizacao_manual_task")
    def test_ja_existe_execucao_rodando_retorna_409(self, mock_task):
        CredencialFornecedor.objects.create(
            instancia=self.instancia, fornecedor="asia", credenciais={"api_key": "a", "secret_key": "b"}, ativo=True
        )
        Execucao.objects.create(
            instancia=self.instancia,
            fornecedor="asia",
            tipo=TipoExecucao.INCREMENTAL,
            status=StatusExecucao.RODANDO,
        )
        resposta = self.client.post(self._url("asia"))
        self.assertEqual(resposta.status_code, status.HTTP_409_CONFLICT)
        mock_task.delay.assert_not_called()

    def test_fornecedor_desconhecido_retorna_404(self):
        resposta = self.client.post(self._url("inexistente"))
        self.assertEqual(resposta.status_code, status.HTTP_404_NOT_FOUND)
