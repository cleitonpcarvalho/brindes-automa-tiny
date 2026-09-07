import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework import status

from apps.catalogo.models import Produto, StatusVariacao, Variacao
from apps.sincronizacao.models import Execucao, StatusExecucao, TipoExecucao

from ..models import Instancia
from .test_views import _client_autenticado


def _execucao_cadastro(instancia, fornecedor="xbz", **kwargs):
    dados = {
        "instancia": instancia,
        "fornecedor": fornecedor,
        "tipo": TipoExecucao.CADASTRO_TINY,
        "status": StatusExecucao.RODANDO,
        "lease_token": uuid.uuid4().hex,
        "heartbeat_em": timezone.now(),
    }
    dados.update(kwargs)
    return Execucao.objects.create(**dados)


def _instancia_pronta(**kwargs):
    dados = {
        "nome": "Loja Cadastro Tiny",
        "access_token": "token",
        "tiny_origem_padrao": 0,
        "tiny_unidade_medida_padrao": "UN",
    }
    dados.update(kwargs)
    return Instancia.objects.create(**dados)


def _variacao(instancia, sku, *, fornecedor="xbz", **kwargs):
    produto = Produto.objects.create(
        instancia=instancia, fornecedor=fornecedor, codigo_pai=f"pai-{sku}", nome=f"P {sku}"
    )
    dados = {"produto": produto, "sku": sku, "nome": f"V {sku}", "preco": Decimal("10.00"), "estoque": 5}
    dados.update(kwargs)
    return Variacao.objects.create(**dados)


class CadastroTinyPreviewTests(TestCase):
    def setUp(self):
        self.client = _client_autenticado()
        self.instancia = _instancia_pronta()

    def _url(self, fornecedor="xbz"):
        return f"/api/instancias/{self.instancia.slug}/fornecedores/{fornecedor}/cadastro-tiny/preview/"

    def test_exige_autenticacao(self):
        from rest_framework.test import APIClient

        resp = APIClient().get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_estimativa_conta_elegiveis_sem_tocar_no_tiny(self):
        _variacao(self.instancia, "A", fornecedor="xbz")
        _variacao(self.instancia, "B", fornecedor="xbz")
        _variacao(self.instancia, "ZERO", fornecedor="xbz", estoque=0)
        _variacao(self.instancia, "OUTRA-INST-N/A", fornecedor="asia")

        with patch("apps.instancias.tiny_client.TinyApiClient") as mock_cliente:
            resp = self.client.get(self._url("xbz"))

        mock_cliente.assert_not_called()
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["elegiveis"], 2)
        self.assertEqual(resp.data["sem_estoque"], 1)
        self.assertTrue(resp.data["pronta_para_cadastro"])
        self.assertFalse(resp.data["sincronizacao_em_andamento"])

    def test_preview_avisa_quando_instancia_nao_esta_pronta(self):
        instancia = Instancia.objects.create(nome="Sem token")
        resp = self.client.get(
            f"/api/instancias/{instancia.slug}/fornecedores/xbz/cadastro-tiny/preview/"
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertFalse(resp.data["pronta_para_cadastro"])
        self.assertIn("não está conectada", resp.data["motivo_nao_pronta"])

    def test_fornecedor_desconhecido_404(self):
        resp = self.client.get(self._url("inexistente"))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)


class CadastrarProdutosTinyViewTests(TestCase):
    def setUp(self):
        self.client = _client_autenticado()
        self.instancia = _instancia_pronta()

    def _url(self, fornecedor="xbz"):
        return f"/api/instancias/{self.instancia.slug}/fornecedores/{fornecedor}/cadastro-tiny/"

    @patch("apps.instancias.views.cadastrar_produtos_tiny_task")
    def test_cria_execucao_cadastro_tiny_e_enfileira_sem_tocar_no_tiny(self, mock_task):
        _variacao(self.instancia, "SKU-1", fornecedor="xbz")

        with patch("apps.instancias.tiny_client.TinyApiClient") as mock_cliente:
            resp = self.client.post(self._url("xbz"))

        mock_cliente.assert_not_called()  # nada de Tiny na request
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        execucao = Execucao.objects.get(pk=resp.data["execucao_id"])
        self.assertEqual(execucao.instancia, self.instancia)
        self.assertEqual(execucao.fornecedor, "xbz")
        self.assertEqual(execucao.tipo, TipoExecucao.CADASTRO_TINY)
        self.assertEqual(execucao.status, StatusExecucao.RODANDO)
        mock_task.delay.assert_called_once_with(execucao.id, execucao.lease_token)
        self.assertTrue(execucao.lease_token)
        self.assertIsNotNone(execucao.heartbeat_em)

    @patch("apps.instancias.views.cadastrar_produtos_tiny_task")
    def test_bloqueia_segunda_sincronizacao_simultanea_do_mesmo_par(self, mock_task):
        Execucao.objects.create(
            instancia=self.instancia,
            fornecedor="xbz",
            tipo=TipoExecucao.CADASTRO_TINY,
            status=StatusExecucao.RODANDO,
        )
        antes = Execucao.objects.count()

        resp = self.client.post(self._url("xbz"))

        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(Execucao.objects.count(), antes)
        mock_task.delay.assert_not_called()

    @patch("apps.instancias.views.cadastrar_produtos_tiny_task")
    def test_bloqueia_se_ha_importacao_de_espelho_rodando(self, mock_task):
        Execucao.objects.create(
            instancia=self.instancia,
            fornecedor="xbz",
            tipo=TipoExecucao.INCREMENTAL,
            status=StatusExecucao.RODANDO,
        )
        resp = self.client.post(self._url("xbz"))
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        mock_task.delay.assert_not_called()

    @patch("apps.instancias.views.cadastrar_produtos_tiny_task")
    def test_400_quando_instancia_nao_conectada(self, mock_task):
        instancia = Instancia.objects.create(nome="Desconectada")
        resp = self.client.post(
            f"/api/instancias/{instancia.slug}/fornecedores/xbz/cadastro-tiny/"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        mock_task.delay.assert_not_called()

    @patch("apps.instancias.views.cadastrar_produtos_tiny_task")
    def test_400_quando_config_do_tiny_faltando(self, mock_task):
        instancia = Instancia.objects.create(nome="Sem config", access_token="t")
        resp = self.client.post(
            f"/api/instancias/{instancia.slug}/fornecedores/xbz/cadastro-tiny/"
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        mock_task.delay.assert_not_called()

    @patch("apps.instancias.views.cadastrar_produtos_tiny_task")
    def test_isolamento_entre_instancias_na_trava_de_concorrencia(self, mock_task):
        outra = _instancia_pronta(nome="Outra loja")
        Execucao.objects.create(
            instancia=outra,
            fornecedor="xbz",
            tipo=TipoExecucao.CADASTRO_TINY,
            status=StatusExecucao.RODANDO,
        )
        # a instância 'self' não tem sincronização rodando -> pode disparar
        resp = self.client.post(self._url("xbz"))
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        mock_task.delay.assert_called_once()

    def test_fornecedor_desconhecido_404(self):
        resp = self.client.post(self._url("inexistente"))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    @patch("apps.instancias.views.cadastrar_produtos_tiny_task")
    def test_xbz_e_asia_podem_rodar_simultaneamente(self, mock_task):
        _variacao(self.instancia, "X-1", fornecedor="xbz")
        _variacao(self.instancia, "A-1", fornecedor="asia")

        r1 = self.client.post(self._url("xbz"))
        r2 = self.client.post(self._url("asia"))

        self.assertEqual(r1.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(r2.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(
            Execucao.objects.filter(
                instancia=self.instancia, tipo=TipoExecucao.CADASTRO_TINY, status=StatusExecucao.RODANDO
            ).count(),
            2,
        )
        self.assertEqual(mock_task.delay.call_count, 2)

    @patch("apps.instancias.views.cadastrar_produtos_tiny_task")
    def test_start_bloqueado_quando_ha_execucao_pausada(self, mock_task):
        _execucao_cadastro(self.instancia, "xbz", status=StatusExecucao.PAUSADO)
        resp = self.client.post(self._url("xbz"))
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        mock_task.delay.assert_not_called()

    @patch("apps.instancias.views.cadastrar_produtos_tiny_task")
    def test_start_bloqueado_quando_ha_execucao_interrompida(self, mock_task):
        _execucao_cadastro(self.instancia, "xbz", status=StatusExecucao.INTERROMPIDO)
        resp = self.client.post(self._url("xbz"))
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        mock_task.delay.assert_not_called()

    @patch("apps.instancias.views.cadastrar_produtos_tiny_task")
    def test_mesma_fornecedora_em_instancias_diferentes_continua_isolada(self, mock_task):
        outra = _instancia_pronta(nome="Loja B")
        _execucao_cadastro(outra, "xbz", status=StatusExecucao.RODANDO)
        _variacao(self.instancia, "X-1", fornecedor="xbz")

        resp = self.client.post(self._url("xbz"))

        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        mock_task.delay.assert_called_once()


class PausarRetomarCadastroTinyTests(TestCase):
    def setUp(self):
        self.client = _client_autenticado()
        self.instancia = _instancia_pronta()

    def _url(self, acao, fornecedor="xbz"):
        return f"/api/instancias/{self.instancia.slug}/fornecedores/{fornecedor}/cadastro-tiny/{acao}/"

    def test_pausar_marca_pausando_e_pausa_solicitada(self):
        ex = _execucao_cadastro(self.instancia, "xbz", status=StatusExecucao.RODANDO)
        resp = self.client.post(self._url("pausar"))
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        ex.refresh_from_db()
        self.assertEqual(ex.status, StatusExecucao.PAUSANDO)
        self.assertTrue(ex.pausa_solicitada)

    def test_pausar_sem_nada_rodando_da_409(self):
        _execucao_cadastro(self.instancia, "xbz", status=StatusExecucao.PAUSADO)
        resp = self.client.post(self._url("pausar"))
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)

    @patch("apps.instancias.views.cadastrar_produtos_tiny_task")
    def test_retomar_reusa_a_execucao_gera_token_novo_e_enfileira(self, mock_task):
        ex = _execucao_cadastro(
            self.instancia, "xbz", status=StatusExecucao.PAUSADO, total_cadastrados=5
        )
        token_antigo = ex.lease_token

        resp = self.client.post(self._url("retomar"))

        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(resp.data["execucao_id"], ex.id)  # MESMA Execucao
        ex.refresh_from_db()
        self.assertEqual(ex.status, StatusExecucao.RODANDO)
        self.assertNotEqual(ex.lease_token, token_antigo)
        self.assertFalse(ex.pausa_solicitada)
        self.assertEqual(ex.total_cadastrados, 5)  # contadores preservados
        mock_task.delay.assert_called_once_with(ex.id, ex.lease_token)

    @patch("apps.instancias.views.cadastrar_produtos_tiny_task")
    def test_retomar_execucao_interrompida(self, mock_task):
        ex = _execucao_cadastro(self.instancia, "xbz", status=StatusExecucao.INTERROMPIDO)
        resp = self.client.post(self._url("retomar"))
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        ex.refresh_from_db()
        self.assertEqual(ex.status, StatusExecucao.RODANDO)

    @patch("apps.instancias.views.cadastrar_produtos_tiny_task")
    def test_retomar_rodando_com_heartbeat_expirado(self, mock_task):
        ex = _execucao_cadastro(
            self.instancia, "xbz", status=StatusExecucao.RODANDO,
            heartbeat_em=timezone.now() - timedelta(minutes=30),
        )
        resp = self.client.post(self._url("retomar"))
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        ex.refresh_from_db()
        self.assertEqual(ex.status, StatusExecucao.RODANDO)
        self.assertGreater(ex.heartbeat_em, timezone.now() - timedelta(minutes=1))

    @patch("apps.instancias.views.cadastrar_produtos_tiny_task")
    def test_retomar_quando_ja_esta_rodando_fresco_da_409(self, mock_task):
        _execucao_cadastro(self.instancia, "xbz", status=StatusExecucao.RODANDO)
        resp = self.client.post(self._url("retomar"))
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        mock_task.delay.assert_not_called()

    @patch("apps.instancias.views.cadastrar_produtos_tiny_task")
    def test_dois_retomar_seguidos_so_enfileiram_uma_task(self, mock_task):
        _execucao_cadastro(self.instancia, "xbz", status=StatusExecucao.PAUSADO)

        r1 = self.client.post(self._url("retomar"))
        r2 = self.client.post(self._url("retomar"))

        self.assertEqual(r1.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(r2.status_code, status.HTTP_409_CONFLICT)  # já rodando (heartbeat fresco)
        mock_task.delay.assert_called_once()

    @patch("apps.instancias.views.cadastrar_produtos_tiny_task")
    def test_retomar_sem_execucao_aberta_da_409(self, mock_task):
        resp = self.client.post(self._url("retomar"))
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        mock_task.delay.assert_not_called()


class EspelhoBloqueadoPorCadastroTinyTests(TestCase):
    def setUp(self):
        self.client = _client_autenticado()
        self.instancia = _instancia_pronta()
        from apps.instancias.models import CredencialFornecedor

        CredencialFornecedor.objects.create(
            instancia=self.instancia, fornecedor="asia",
            credenciais={"api_key": "a", "secret_key": "b"}, ativo=True,
        )

    def _sincronizar_url(self):
        return f"/api/instancias/{self.instancia.slug}/fornecedores/asia/sincronizar/"

    @patch("apps.instancias.views.executar_sincronizacao_manual_task")
    def test_importacao_de_espelho_bloqueada_por_cadastro_tiny_ativo(self, mock_task):
        _execucao_cadastro(self.instancia, "asia", status=StatusExecucao.RODANDO)
        resp = self.client.post(self._sincronizar_url())
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        mock_task.delay.assert_not_called()

    @patch("apps.instancias.views.executar_sincronizacao_manual_task")
    def test_importacao_de_espelho_liberada_quando_cadastro_tiny_pausado(self, mock_task):
        _execucao_cadastro(self.instancia, "asia", status=StatusExecucao.PAUSADO)
        resp = self.client.post(self._sincronizar_url())
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        mock_task.delay.assert_called_once()
