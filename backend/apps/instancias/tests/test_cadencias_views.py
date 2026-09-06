from django.test import TestCase
from rest_framework import status

from apps.fornecedores.models import CadenciaFornecedor

from ..models import Instancia
from .test_views import _client_autenticado


class CadenciasFornecedorListTests(TestCase):
    def setUp(self):
        self.client = _client_autenticado()
        self.instancia = Instancia.objects.create(nome="Loja Cadencias")

    def test_lista_com_defaults_quando_nao_existe_linha(self):
        resposta = self.client.get(f"/api/instancias/{self.instancia.slug}/cadencias/")
        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        self.assertEqual(len(resposta.data), 4)
        for linha in resposta.data:
            self.assertEqual(linha["intervalo_minutos"], 60)
            self.assertFalse(linha["ativo"])
            self.assertIsNone(linha["proxima_execucao_em"])


class CadenciaFornecedorDetailPatchTests(TestCase):
    def setUp(self):
        self.client = _client_autenticado()
        self.instancia = Instancia.objects.create(nome="Loja Patch Cadencia")

    def test_patch_cria_e_atualiza(self):
        resposta = self.client.patch(
            f"/api/instancias/{self.instancia.slug}/cadencias/somarcas/",
            {"intervalo_minutos": 120, "ativo": True},
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        self.assertEqual(resposta.data["intervalo_minutos"], 120)
        self.assertTrue(resposta.data["ativo"])

        cadencia = CadenciaFornecedor.objects.get(instancia=self.instancia, fornecedor="somarcas")
        self.assertEqual(cadencia.intervalo_minutos, 120)

        resposta2 = self.client.patch(
            f"/api/instancias/{self.instancia.slug}/cadencias/somarcas/",
            {"ativo": False},
            content_type="application/json",
        )
        self.assertEqual(resposta2.status_code, status.HTTP_200_OK)
        self.assertFalse(resposta2.data["ativo"])
        self.assertEqual(resposta2.data["intervalo_minutos"], 120)  # não mexeu no que não foi enviado
        self.assertEqual(
            CadenciaFornecedor.objects.filter(instancia=self.instancia, fornecedor="somarcas").count(), 1
        )

    def test_patch_xbz_abaixo_do_minimo_retorna_400(self):
        resposta = self.client.patch(
            f"/api/instancias/{self.instancia.slug}/cadencias/xbz/",
            {"intervalo_minutos": 30},
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(CadenciaFornecedor.objects.filter(instancia=self.instancia, fornecedor="xbz").exists())

    def test_patch_fornecedor_desconhecido_retorna_404(self):
        resposta = self.client.patch(
            f"/api/instancias/{self.instancia.slug}/cadencias/inexistente/",
            {"intervalo_minutos": 60},
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, status.HTTP_404_NOT_FOUND)
