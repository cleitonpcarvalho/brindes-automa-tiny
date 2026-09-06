from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient

from apps.fornecedores.models import CadenciaFornecedor

from ..models import Instancia
from .test_views import _client_autenticado


class ConfiguracoesInstanciaTests(TestCase):
    def setUp(self):
        self.client = _client_autenticado()
        self.instancia = Instancia.objects.create(nome="Loja A", cnpj="11.222.333/0001-44", client_id="cid-a")
        self.outra = Instancia.objects.create(nome="Loja B", client_id="cid-b")

    def _url(self, instancia=None):
        return f"/api/instancias/{(instancia or self.instancia).slug}/configuracoes/"

    def test_exige_autenticacao(self):
        self.assertEqual(APIClient().get(self._url()).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_slug_inexistente_404(self):
        self.assertEqual(
            self.client.get("/api/instancias/nao-existe/configuracoes/").status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_get_retorna_apenas_os_campos_de_configuracao(self):
        self.instancia.tiny_origem_padrao = 0
        self.instancia.tiny_unidade_medida_padrao = "UN"
        self.instancia.save()

        resposta = self.client.get(self._url())
        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        self.assertEqual(set(resposta.data.keys()), {"tiny_origem_padrao", "tiny_unidade_medida_padrao"})
        self.assertEqual(resposta.data["tiny_origem_padrao"], 0)
        self.assertEqual(resposta.data["tiny_unidade_medida_padrao"], "UN")

    def test_patch_atualiza_campos_permitidos(self):
        resposta = self.client.patch(
            self._url(), {"tiny_origem_padrao": 2, "tiny_unidade_medida_padrao": "CX"}, format="json"
        )
        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        self.instancia.refresh_from_db()
        self.assertEqual(self.instancia.tiny_origem_padrao, 2)
        self.assertEqual(self.instancia.tiny_unidade_medida_padrao, "CX")

    def test_patch_parcial_nao_mexe_no_que_nao_foi_enviado(self):
        self.instancia.tiny_origem_padrao = 1
        self.instancia.tiny_unidade_medida_padrao = "UN"
        self.instancia.save()

        self.client.patch(self._url(), {"tiny_unidade_medida_padrao": "PC"}, format="json")
        self.instancia.refresh_from_db()
        self.assertEqual(self.instancia.tiny_origem_padrao, 1)
        self.assertEqual(self.instancia.tiny_unidade_medida_padrao, "PC")

    def test_patch_aceita_null_para_limpar_origem(self):
        self.instancia.tiny_origem_padrao = 3
        self.instancia.save()

        resposta = self.client.patch(self._url(), {"tiny_origem_padrao": None}, format="json")
        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        self.instancia.refresh_from_db()
        self.assertIsNone(self.instancia.tiny_origem_padrao)

    def test_patch_ignora_campos_sensiveis(self):
        slug_original = self.instancia.slug
        resposta = self.client.patch(
            self._url(),
            {
                "tiny_unidade_medida_padrao": "UN",
                "slug": "hackeado",
                "cnpj": "99.999.999/9999-99",
                "client_id": "roubado",
                "client_secret": "roubado",
                "status": "conectado",
                "nome": "Nome Trocado",
            },
            format="json",
        )
        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        self.instancia.refresh_from_db()
        self.assertEqual(self.instancia.slug, slug_original)
        self.assertEqual(self.instancia.cnpj, "11.222.333/0001-44")
        self.assertEqual(self.instancia.client_id, "cid-a")
        self.assertEqual(self.instancia.nome, "Loja A")
        self.assertEqual(self.instancia.status, Instancia.Status.NAO_CONECTADO)
        self.assertEqual(self.instancia.tiny_unidade_medida_padrao, "UN")  # o campo permitido entrou

    def test_patch_origem_fora_do_intervalo_retorna_400(self):
        resposta = self.client.patch(self._url(), {"tiny_origem_padrao": 99}, format="json")
        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("tiny_origem_padrao", resposta.data)
        self.instancia.refresh_from_db()
        self.assertIsNone(self.instancia.tiny_origem_padrao)

    def test_patch_unidade_maior_que_10_retorna_400(self):
        resposta = self.client.patch(
            self._url(), {"tiny_unidade_medida_padrao": "X" * 11}, format="json"
        )
        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("tiny_unidade_medida_padrao", resposta.data)

    def test_isolamento_por_instancia(self):
        self.client.patch(self._url(self.instancia), {"tiny_origem_padrao": 5}, format="json")
        self.outra.refresh_from_db()
        self.assertIsNone(self.outra.tiny_origem_padrao)

        self.client.patch(self._url(self.outra), {"tiny_origem_padrao": 7}, format="json")
        self.instancia.refresh_from_db()
        self.assertEqual(self.instancia.tiny_origem_padrao, 5)


class CadenciaIsolamentoTests(TestCase):
    """Complementa test_cadencias_views.py: garante que o PATCH de cadência não
    cruza instâncias."""

    def setUp(self):
        self.client = _client_autenticado()
        self.instancia = Instancia.objects.create(nome="Loja A")
        self.outra = Instancia.objects.create(nome="Loja B")

    def test_patch_cadencia_so_afeta_a_instancia_do_slug(self):
        resposta = self.client.patch(
            f"/api/instancias/{self.instancia.slug}/cadencias/spot/",
            {"intervalo_minutos": 240, "ativo": True},
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        self.assertTrue(
            CadenciaFornecedor.objects.filter(instancia=self.instancia, fornecedor="spot").exists()
        )
        self.assertFalse(
            CadenciaFornecedor.objects.filter(instancia=self.outra, fornecedor="spot").exists()
        )
