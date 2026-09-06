from django.test import TestCase
from rest_framework import status

from ..models import CredencialFornecedor, Instancia
from .test_views import _client_autenticado


class CredenciaisFornecedorListTests(TestCase):
    def setUp(self):
        self.client = _client_autenticado()
        self.instancia = Instancia.objects.create(nome="Loja Credenciais")

    def test_lista_sempre_traz_os_4_fornecedores(self):
        resposta = self.client.get(f"/api/instancias/{self.instancia.slug}/credenciais/")
        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        fornecedores = {linha["fornecedor"] for linha in resposta.data}
        self.assertEqual(fornecedores, {"xbz", "asia", "somarcas", "spot"})
        for linha in resposta.data:
            self.assertFalse(linha["configurado"])
            self.assertFalse(linha["ativo"])

    def test_campo_nao_sensivel_volta_pleno_e_sensivel_mascarado(self):
        CredencialFornecedor.objects.create(
            instancia=self.instancia,
            fornecedor="xbz",
            credenciais={"cnpj": "12345678000190", "token": "abcdef123456"},
            ativo=True,
        )
        resposta = self.client.get(f"/api/instancias/{self.instancia.slug}/credenciais/")
        xbz = next(linha for linha in resposta.data if linha["fornecedor"] == "xbz")

        self.assertTrue(xbz["configurado"])
        self.assertTrue(xbz["ativo"])
        # cnpj não é sensível — volta em texto pleno
        self.assertEqual(xbz["campos_mascarados"]["cnpj"], "12345678000190")
        # token é sensível — só os últimos 4 caracteres reais aparecem
        self.assertEqual(xbz["campos_mascarados"]["token"], "••••••••3456")
        self.assertNotIn("abcdef", str(resposta.content))


class CredencialFornecedorDetailPutTests(TestCase):
    def setUp(self):
        self.client = _client_autenticado()
        self.instancia = Instancia.objects.create(nome="Loja Put Credencial")

    def test_put_rejeita_chave_obrigatoria_faltando(self):
        resposta = self.client.put(
            f"/api/instancias/{self.instancia.slug}/credenciais/xbz/",
            {"credenciais": {"cnpj": "123"}},
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertFalse(CredencialFornecedor.objects.filter(instancia=self.instancia).exists())

    def test_put_rejeita_chave_desconhecida(self):
        resposta = self.client.put(
            f"/api/instancias/{self.instancia.slug}/credenciais/xbz/",
            {"credenciais": {"cnpj": "123", "token": "456", "campo_invalido": "x"}},
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)

    def test_put_grava_criptografado_e_nunca_ecoa_o_valor_pleno(self):
        resposta = self.client.put(
            f"/api/instancias/{self.instancia.slug}/credenciais/xbz/",
            {"credenciais": {"cnpj": "12345678000190", "token": "segredo-xyz-9876"}},
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        self.assertNotIn("segredo-xyz", str(resposta.content))
        self.assertEqual(resposta.data["campos_mascarados"]["token"], "••••••••9876")

        credencial = CredencialFornecedor.objects.get(instancia=self.instancia, fornecedor="xbz")
        self.assertEqual(credencial.credenciais["token"], "segredo-xyz-9876")  # decriptografado ao ler de volta

        # no banco, a coluna não guarda o texto puro (Fernet cifra em repouso)
        from django.db import connection

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT credenciais FROM instancias_credencialfornecedor WHERE id = %s", [credencial.id]
            )
            bruto_no_banco = cursor.fetchone()[0]
        self.assertNotIn("segredo-xyz", bruto_no_banco)

    def test_put_de_novo_atualiza_a_mesma_linha(self):
        self.client.put(
            f"/api/instancias/{self.instancia.slug}/credenciais/xbz/",
            {"credenciais": {"cnpj": "1", "token": "primeiro"}},
            content_type="application/json",
        )
        self.client.put(
            f"/api/instancias/{self.instancia.slug}/credenciais/xbz/",
            {"credenciais": {"cnpj": "2", "token": "segundo"}},
            content_type="application/json",
        )
        self.assertEqual(CredencialFornecedor.objects.filter(instancia=self.instancia, fornecedor="xbz").count(), 1)
        credencial = CredencialFornecedor.objects.get(instancia=self.instancia, fornecedor="xbz")
        self.assertEqual(credencial.credenciais["cnpj"], "2")

    def test_put_exige_reentrada_do_secret_sem_alterar_credencial_existente(self):
        credencial = CredencialFornecedor.objects.create(
            instancia=self.instancia,
            fornecedor="xbz",
            credenciais={"cnpj": "1", "token": "segredo-existente"},
            ativo=False,
        )

        for dados in ({"cnpj": "2"}, {"cnpj": "2", "token": ""}):
            with self.subTest(dados=dados):
                resposta = self.client.put(
                    f"/api/instancias/{self.instancia.slug}/credenciais/xbz/",
                    {"credenciais": dados},
                    content_type="application/json",
                )

                self.assertEqual(resposta.status_code, status.HTTP_400_BAD_REQUEST)
                credencial.refresh_from_db()
                self.assertEqual(credencial.credenciais, {"cnpj": "1", "token": "segredo-existente"})
                self.assertFalse(credencial.ativo)
                self.assertNotIn("segredo-existente", str(resposta.content))

    def test_put_preserva_isolamento_por_instancia_e_fornecedor(self):
        outra_instancia = Instancia.objects.create(nome="Outra Loja")
        outra_loja = CredencialFornecedor.objects.create(
            instancia=outra_instancia,
            fornecedor="xbz",
            credenciais={"cnpj": "outro-cnpj", "token": "segredo-outra-loja"},
        )
        outro_fornecedor = CredencialFornecedor.objects.create(
            instancia=self.instancia,
            fornecedor="spot",
            credenciais={"access_key": "segredo-outro-fornecedor"},
        )

        resposta = self.client.put(
            f"/api/instancias/{self.instancia.slug}/credenciais/xbz/",
            {"credenciais": {"cnpj": "1", "token": "segredo-novo"}, "ativo": False},
            content_type="application/json",
        )

        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        self.assertTrue(resposta.data["configurado"])
        self.assertFalse(resposta.data["ativo"])
        outra_loja.refresh_from_db()
        outro_fornecedor.refresh_from_db()
        self.assertEqual(outra_loja.credenciais, {"cnpj": "outro-cnpj", "token": "segredo-outra-loja"})
        self.assertEqual(outro_fornecedor.credenciais, {"access_key": "segredo-outro-fornecedor"})
        resposta_lista = self.client.get(f"/api/instancias/{self.instancia.slug}/credenciais/")
        xbz = next(linha for linha in resposta_lista.data if linha["fornecedor"] == "xbz")
        self.assertEqual(xbz["campos_mascarados"]["cnpj"], "1")
        self.assertNotIn("outro-cnpj", str(resposta_lista.content))

    def test_put_aceita_formato_real_dos_demais_fornecedores(self):
        exemplos = {
            "asia": {"api_key": "chave-api-ficticia", "secret_key": "segredo-ficticio"},
            "somarcas": {"usuario": "usuario-ficticio", "senha": "senha-ficticia", "estado": "CE"},
            "spot": {"access_key": "chave-access-ficticia"},
        }

        for fornecedor, credenciais in exemplos.items():
            with self.subTest(fornecedor=fornecedor):
                resposta = self.client.put(
                    f"/api/instancias/{self.instancia.slug}/credenciais/{fornecedor}/",
                    {"credenciais": credenciais, "ativo": False},
                    content_type="application/json",
                )

                self.assertEqual(resposta.status_code, status.HTTP_200_OK)
                self.assertTrue(resposta.data["configurado"])
                gravada = CredencialFornecedor.objects.get(instancia=self.instancia, fornecedor=fornecedor)
                self.assertEqual(gravada.credenciais, credenciais)
                self.assertFalse(gravada.ativo)
                for chave, valor in credenciais.items():
                    if chave not in {"usuario", "estado"}:
                        self.assertNotIn(valor, str(resposta.content))

    def test_put_fornecedor_desconhecido_retorna_404(self):
        resposta = self.client.put(
            f"/api/instancias/{self.instancia.slug}/credenciais/inexistente/",
            {"credenciais": {}},
            content_type="application/json",
        )
        self.assertEqual(resposta.status_code, status.HTTP_404_NOT_FOUND)
