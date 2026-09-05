from datetime import timedelta

from django.core.exceptions import ValidationError
from django.db import connection
from django.test import TestCase
from django.utils import timezone

from ..models import CredencialFornecedor, Instancia


class InstanciaSlugTests(TestCase):
    def test_slug_gerado_a_partir_do_nome_minusculo_sem_acento_ou_espaco(self):
        instancia = Instancia.objects.create(nome="Ação Brindes & Cia")
        self.assertEqual(instancia.slug, "acao-brindes-cia")

    def test_slugs_colidentes_recebem_sufixo_unico(self):
        Instancia.objects.create(nome="Loja Azul")
        outra = Instancia.objects.create(nome="Loja Azul")
        self.assertEqual(outra.slug, "loja-azul-2")

    def test_slug_pode_mudar_antes_da_primeira_autorizacao(self):
        instancia = Instancia.objects.create(nome="Loja Amarela")
        instancia.slug = "slug-manual"
        instancia.save()
        instancia.refresh_from_db()
        self.assertEqual(instancia.slug, "slug-manual")

    def test_mudar_status_sozinho_nao_trava_o_slug(self):
        """
        Corrige uma suposição do passo 2 (documentada como "decisão sem
        instrução explícita" na época): o que trava o slug não é o status
        mudar de nao_conectado, é o access_token ser preenchido pela
        primeira vez.
        """
        instancia = Instancia.objects.create(nome="Loja Sem Token")
        instancia.status = Instancia.Status.ERRO
        instancia.save()

        instancia.slug = "novo-slug-sem-token"
        instancia.save()  # não deve levantar

        instancia.refresh_from_db()
        self.assertEqual(instancia.slug, "novo-slug-sem-token")

    def test_preencher_access_token_trava_o_slug_definitivamente(self):
        instancia = Instancia.objects.create(nome="Loja Com Token")
        instancia.aplicar_tokens(
            access_token="a", refresh_token="r", expires_in=3600, refresh_expires_in=7200
        )

        instancia.slug = "tentativa-de-mudanca"
        with self.assertRaises(ValidationError):
            instancia.save()

    def test_desconectar_nao_libera_o_slug_de_novo(self):
        instancia = Instancia.objects.create(nome="Loja Desconectada")
        instancia.aplicar_tokens(
            access_token="a", refresh_token="r", expires_in=3600, refresh_expires_in=7200
        )

        # simula o efeito de POST .../desconectar/: limpa tokens e status,
        # mas ja_foi_autorizada continua True
        instancia.access_token = ""
        instancia.refresh_token = ""
        instancia.status = Instancia.Status.NAO_CONECTADO
        instancia.save()

        instancia.slug = "tentativa-pos-desconectar"
        with self.assertRaises(ValidationError):
            instancia.save()


class AplicarTokensTests(TestCase):
    def test_aplicar_tokens_calcula_expiracoes_a_partir_de_expires_in(self):
        instancia = Instancia.objects.create(nome="Loja Token")
        antes = timezone.now()
        instancia.aplicar_tokens(
            access_token="acc", refresh_token="ref", expires_in=3600, refresh_expires_in=86400
        )
        depois = timezone.now()

        self.assertEqual(instancia.access_token, "acc")
        self.assertEqual(instancia.refresh_token, "ref")
        self.assertEqual(instancia.status, Instancia.Status.CONECTADO)
        self.assertTrue(antes + timedelta(seconds=3600) <= instancia.token_expira_em <= depois + timedelta(seconds=3600))
        self.assertTrue(
            antes + timedelta(seconds=86400) <= instancia.refresh_expira_em <= depois + timedelta(seconds=86400)
        )

    def test_aplicar_tokens_zera_tentativas_falha_e_limpa_ultimo_erro(self):
        instancia = Instancia.objects.create(
            nome="Loja Recuperada", tentativas_falha=2, ultimo_erro="algo deu errado"
        )
        instancia.aplicar_tokens(
            access_token="a", refresh_token="r", expires_in=3600, refresh_expires_in=7200
        )
        self.assertEqual(instancia.tentativas_falha, 0)
        self.assertEqual(instancia.ultimo_erro, "")


class PrecisaRenovarTokenTests(TestCase):
    def test_nao_precisa_renovar_antes_de_70_por_cento(self):
        agora = timezone.now()
        instancia = Instancia(
            token_emitido_em=agora - timedelta(seconds=60),
            token_expira_em=agora + timedelta(seconds=40),  # 60/100 = 60% decorrido
        )
        self.assertFalse(instancia.precisa_renovar_token(agora))

    def test_precisa_renovar_a_partir_de_70_por_cento(self):
        agora = timezone.now()
        instancia = Instancia(
            token_emitido_em=agora - timedelta(seconds=70),
            token_expira_em=agora + timedelta(seconds=30),  # 70/100 = 70% decorrido
        )
        self.assertTrue(instancia.precisa_renovar_token(agora))

    def test_sem_datas_nao_precisa_renovar(self):
        instancia = Instancia()
        self.assertFalse(instancia.precisa_renovar_token())


class RegistrarFalhaRenovacaoTests(TestCase):
    """Regra do cliente: 3 falhas seguidas de renovação -> status erro."""

    def test_falhas_incrementam_contador_e_gravam_ultimo_erro_sem_mudar_status(self):
        instancia = Instancia.objects.create(nome="Loja com Falha")
        instancia.registrar_falha_renovacao("erro 1")
        self.assertEqual(instancia.tentativas_falha, 1)
        self.assertEqual(instancia.ultimo_erro, "erro 1")
        self.assertEqual(instancia.status, Instancia.Status.NAO_CONECTADO)

        instancia.registrar_falha_renovacao("erro 2")
        self.assertEqual(instancia.tentativas_falha, 2)
        self.assertEqual(instancia.status, Instancia.Status.NAO_CONECTADO)

    def test_terceira_falha_seguida_muda_status_para_erro(self):
        instancia = Instancia.objects.create(nome="Loja com 3 Falhas", status=Instancia.Status.CONECTADO)
        instancia.registrar_falha_renovacao("erro 1")
        instancia.registrar_falha_renovacao("erro 2")
        instancia.registrar_falha_renovacao("erro 3")

        self.assertEqual(instancia.tentativas_falha, 3)
        self.assertEqual(instancia.status, Instancia.Status.ERRO)
        self.assertEqual(instancia.ultimo_erro, "erro 3")

    def test_sucesso_apos_falhas_zera_o_contador(self):
        instancia = Instancia.objects.create(nome="Loja Recuperada 2")
        instancia.registrar_falha_renovacao("erro 1")
        instancia.registrar_falha_renovacao("erro 2")

        instancia.aplicar_tokens(
            access_token="a", refresh_token="r", expires_in=3600, refresh_expires_in=7200
        )
        self.assertEqual(instancia.tentativas_falha, 0)


class RefreshTokenExpiradoTests(TestCase):
    def test_refresh_expirado_retorna_true(self):
        instancia = Instancia(refresh_expira_em=timezone.now() - timedelta(seconds=1))
        self.assertTrue(instancia.refresh_token_expirado())

    def test_refresh_valido_retorna_false(self):
        instancia = Instancia(refresh_expira_em=timezone.now() + timedelta(hours=1))
        self.assertFalse(instancia.refresh_token_expirado())

    def test_sem_refresh_expira_em_retorna_false(self):
        instancia = Instancia()
        self.assertFalse(instancia.refresh_token_expirado())


class CriptografiaDeCredenciaisTests(TestCase):
    """
    Regra do cliente: client_secret, access_token, refresh_token e as
    credenciais de fornecedor nunca podem ficar em texto puro no banco.
    """

    def test_tokens_da_instancia_sao_gravados_cifrados_e_lidos_de_volta_iguais(self):
        instancia = Instancia.objects.create(
            nome="Loja Cifrada",
            client_secret="segredo-super-secreto",
            access_token="token-de-acesso",
            refresh_token="token-de-renovacao",
        )

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT client_secret, access_token, refresh_token "
                "FROM instancias_instancia WHERE id = %s",
                [instancia.pk],
            )
            client_secret_bruto, access_token_bruto, refresh_token_bruto = cursor.fetchone()

        self.assertNotIn("segredo-super-secreto", client_secret_bruto)
        self.assertNotIn("token-de-acesso", access_token_bruto)
        self.assertNotIn("token-de-renovacao", refresh_token_bruto)

        instancia.refresh_from_db()
        self.assertEqual(instancia.client_secret, "segredo-super-secreto")
        self.assertEqual(instancia.access_token, "token-de-acesso")
        self.assertEqual(instancia.refresh_token, "token-de-renovacao")

    def test_credenciais_de_fornecedor_sao_gravadas_cifradas_e_lidas_de_volta_como_dict(self):
        instancia = Instancia.objects.create(nome="Loja com Fornecedor")
        credencial = CredencialFornecedor.objects.create(
            instancia=instancia,
            fornecedor="xbz",
            credenciais={"cnpj": "23948964000161", "token": "X7E561BBF9"},
        )

        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT credenciais FROM instancias_credencialfornecedor WHERE id = %s",
                [credencial.pk],
            )
            (credenciais_bruto,) = cursor.fetchone()

        self.assertNotIn("X7E561BBF9", credenciais_bruto)

        credencial.refresh_from_db()
        self.assertEqual(
            credencial.credenciais, {"cnpj": "23948964000161", "token": "X7E561BBF9"}
        )
