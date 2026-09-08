"""
`POST /api/instancias/<slug>/execucoes/<id>/produtos/<variacao_id>/retentar/`
— "Tentar novamente" um SKU com erro na tela de detalhe de Execução.

Reusa `cadastrar_variacao_individual` (-> `_processar_variacao`). Os LogItems
da tentativa são APPENDADOS na Execucao original; o log do erro original
NUNCA é tocado.
"""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework import status

from apps.catalogo.models import Produto, StatusVariacao, Variacao
from apps.instancias.tiny_client import TinyApiValidationError
from apps.sincronizacao.auditoria import logs_da_variacao, resumo_auditoria
from apps.sincronizacao.models import (
    EventoLog,
    Execucao,
    LogItem,
    NivelLog,
    StatusExecucao,
    TipoExecucao,
)

from ..models import CredencialFornecedor, Instancia
from .test_views import _client_autenticado

TINY_FORN_ID = 752133514


def _cenario(*, fornecedor="asia", estoque=5, preco="10.00", instancia=None):
    instancia = instancia or Instancia.objects.create(
        nome="Loja", access_token="tok", tiny_origem_padrao=0, tiny_unidade_medida_padrao="UN"
    )
    CredencialFornecedor.objects.update_or_create(
        instancia=instancia, fornecedor=fornecedor, defaults={"tiny_fornecedor_id": TINY_FORN_ID}
    )
    produto = Produto.objects.create(
        instancia=instancia, fornecedor=fornecedor, codigo_pai="pai", nome="Produto",
        descricao="Descrição rica.",
    )
    variacao = Variacao.objects.create(
        produto=produto, sku="SKU-ERR", nome="SKU-ERR", preco=Decimal(preco), estoque=estoque,
    )
    Variacao.objects.filter(pk=variacao.pk).update(
        status=StatusVariacao.ERRO, ultimo_erro="Falha original: Tiny recusou (NCM)"
    )
    variacao.refresh_from_db()

    execucao = Execucao.objects.create(
        instancia=instancia, fornecedor=fornecedor, tipo=TipoExecucao.CADASTRO_TINY,
        status=StatusExecucao.PARCIAL, finalizada_em=timezone.now(),
        total_lidos=2, total_cadastrados=1, total_novos=1, total_erros=1, total_ignorados=0,
    )
    log_erro_original = LogItem.objects.create(
        execucao=execucao, variacao=variacao, nivel=NivelLog.ERRO, evento=EventoLog.ERRO,
        mensagem="Falha ao sincronizar SKU SKU-ERR",
        detalhe={"erro": "Falha original: Tiny recusou (NCM)"},
    )
    return instancia, execucao, variacao, log_erro_original


class RetentarVariacaoViewTests(TestCase):
    def setUp(self):
        self.client = _client_autenticado()
        self.instancia, self.execucao, self.variacao, self.log_original = _cenario()

    def _url(self, *, execucao=None, variacao=None, slug=None):
        execucao = execucao or self.execucao
        variacao = variacao or self.variacao
        slug = slug or self.instancia.slug
        return f"/api/instancias/{slug}/execucoes/{execucao.id}/produtos/{variacao.id}/retentar/"

    # -- sucesso ---------------------------------------------------------

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto", return_value={"id": 55, "sku": "SKU-ERR"})
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_retry_com_sucesso_atualiza_linha_status_tiny_id_e_contadores(self, _mb, _mc):
        resp = self.client.post(self._url())

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["resultado"], "criado")
        self.assertEqual(resp.data["tiny_id"], "55")
        self.assertEqual(resp.data["variacao_id"], self.variacao.id)

        self.variacao.refresh_from_db()
        self.assertEqual(self.variacao.status, StatusVariacao.CADASTRADO)
        self.assertEqual(self.variacao.tiny_id, "55")

        # contadores da execução recomputados
        self.execucao.refresh_from_db()
        self.assertEqual(self.execucao.total_erros, 0)
        self.assertEqual(self.execucao.total_cadastrados, 1)
        aud = resumo_auditoria(self.execucao)
        self.assertEqual(aud["erros"], 0)
        self.assertEqual(aud["cadastrados"], 1)

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto", return_value={"id": 55, "sku": "SKU-ERR"})
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_retry_que_zera_os_erros_consolida_o_status_para_sucesso(self, _mb, _mc):
        self.client.post(self._url())

        self.execucao.refresh_from_db()
        self.assertEqual(self.execucao.total_erros, 0)
        self.assertEqual(self.execucao.total_ignorados, 0)
        # o badge "Parcial / com erros" some: status final consolidado
        self.assertEqual(self.execucao.status, StatusExecucao.SUCESSO)
        # rastro da reclassificação, sem apagar nada do histórico
        marcador = LogItem.objects.filter(
            execucao=self.execucao, mensagem__icontains="Status consolidado"
        ).first()
        self.assertIsNotNone(marcador)
        self.assertEqual(marcador.detalhe["status_anterior"], StatusExecucao.PARCIAL)
        self.assertTrue(LogItem.objects.filter(pk=self.log_original.pk).exists())

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto", return_value={"id": 55, "sku": "SKU-ERR"})
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_retry_com_outro_erro_pendente_mantem_parcial(self, _mb, _mc):
        outra = Variacao.objects.create(
            produto=self.variacao.produto, sku="SKU-ERR-2", nome="SKU-ERR-2",
            preco=Decimal("10.00"), estoque=5,
        )
        Variacao.objects.filter(pk=outra.pk).update(status=StatusVariacao.ERRO, ultimo_erro="x")
        LogItem.objects.create(
            execucao=self.execucao, variacao=outra, nivel=NivelLog.ERRO, evento=EventoLog.ERRO,
            mensagem="Falha ao sincronizar SKU SKU-ERR-2", detalhe={"erro": "x"},
        )
        Execucao.objects.filter(pk=self.execucao.pk).update(total_erros=2, total_lidos=3)

        self.client.post(self._url())

        self.execucao.refresh_from_db()
        self.assertEqual(self.execucao.total_erros, 1)
        self.assertEqual(self.execucao.status, StatusExecucao.PARCIAL)

    def test_retry_bem_sucedido_preserva_o_log_do_erro_original(self):
        antes = LogItem.objects.get(pk=self.log_original.pk)
        with patch(
            "apps.instancias.tiny_client.TinyApiClient.criar_produto",
            return_value={"id": 55, "sku": "SKU-ERR"},
        ), patch(
            "apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None
        ):
            self.client.post(self._url())

        depois = LogItem.objects.get(pk=self.log_original.pk)  # ainda existe, byte a byte
        self.assertEqual(depois.evento, EventoLog.ERRO)
        self.assertEqual(depois.mensagem, antes.mensagem)
        self.assertEqual(depois.detalhe, antes.detalhe)
        self.assertEqual(depois.criado_em, antes.criado_em)

        # cronologia completa no expand técnico do SKU: erro -> marcador -> criado
        eventos = [log.evento for log in logs_da_variacao(self.execucao, self.variacao.id)]
        self.assertEqual(eventos, [EventoLog.ERRO, EventoLog.GERAL, EventoLog.CRIADO])
        # a tabela de auditoria mostra o ÚLTIMO desfecho
        self.assertEqual(resumo_auditoria(self.execucao)["erros"], 0)

    # -- falha de novo -------------------------------------------------

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto",
           side_effect=TinyApiValidationError("Novo erro: campo origem inválido"))
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_retry_que_falha_de_novo_mostra_o_novo_erro_e_mantem_como_erro(self, _mb, _mc):
        resp = self.client.post(self._url())

        self.assertEqual(resp.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertIn("origem inválido", resp.data["detail"])

        self.variacao.refresh_from_db()
        self.assertEqual(self.variacao.status, StatusVariacao.ERRO)
        self.assertIn("origem inválido", self.variacao.ultimo_erro)

        # log do erro original intacto + NOVO log de erro appendado
        self.assertTrue(LogItem.objects.filter(pk=self.log_original.pk).exists())
        eventos = [log.evento for log in logs_da_variacao(self.execucao, self.variacao.id)]
        self.assertEqual(eventos, [EventoLog.ERRO, EventoLog.GERAL, EventoLog.ERRO])
        self.assertEqual(resumo_auditoria(self.execucao)["erros"], 1)  # continua contando

    # -- bloqueios ----------------------------------------------------

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_bloqueio_de_regra_nao_gera_logitem_e_preserva_historico(self, _mb, mock_criar):
        Variacao.objects.filter(pk=self.variacao.pk).update(estoque=0)  # agora bloqueia

        resp = self.client.post(self._url())

        self.assertEqual(resp.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertIn("estoque", resp.data["detail"].lower())
        mock_criar.assert_not_called()
        # nenhum desfecho novo — só o marcador GERAL; SKU continua como erro
        eventos = [log.evento for log in logs_da_variacao(self.execucao, self.variacao.id)]
        self.assertEqual(eventos, [EventoLog.ERRO, EventoLog.GERAL])
        self.assertEqual(resumo_auditoria(self.execucao)["erros"], 1)

    # -- produto já cadastrado / clique duplo -------------------------

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    def test_produto_ja_cadastrado_devolve_409(self, mock_criar):
        Variacao.objects.filter(pk=self.variacao.pk).update(
            status=StatusVariacao.CADASTRADO, tiny_id="9"
        )
        resp = self.client.post(self._url())
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("já está cadastrado", resp.data["detail"])
        mock_criar.assert_not_called()

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto", return_value={"id": 55, "sku": "SKU-ERR"})
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_segundo_retry_apos_sucesso_e_409(self, _mb, mock_criar):
        self.assertEqual(self.client.post(self._url()).status_code, status.HTTP_200_OK)
        resp2 = self.client.post(self._url())
        self.assertEqual(resp2.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(mock_criar.call_count, 1)  # não recadastrou

    # -- SKU que não está com erro -----------------------------------

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    def test_sku_cujo_ultimo_desfecho_nao_e_erro_devolve_422(self, mock_criar):
        LogItem.objects.create(
            execucao=self.execucao, variacao=self.variacao, nivel=NivelLog.INFO,
            evento=EventoLog.CRIADO, mensagem="SKU criado", detalhe={"tiny_id": "3"},
        )
        resp = self.client.post(self._url())
        self.assertEqual(resp.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertIn("não está com erro", resp.data["detail"])
        mock_criar.assert_not_called()

    # -- concorrência massa / tipo / isolamento / auth ---------------

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    def test_409_com_sincronizacao_em_massa_ativa(self, mock_criar):
        Execucao.objects.create(
            instancia=self.instancia, fornecedor="asia", tipo=TipoExecucao.CADASTRO_TINY,
            status=StatusExecucao.RODANDO, heartbeat_em=timezone.now(),
        )
        resp = self.client.post(self._url())
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        mock_criar.assert_not_called()

    def test_execucao_que_nao_e_cadastro_tiny_devolve_400(self):
        ex = Execucao.objects.create(
            instancia=self.instancia, fornecedor="asia", tipo=TipoExecucao.INCREMENTAL,
            status=StatusExecucao.SUCESSO,
        )
        LogItem.objects.create(
            execucao=ex, variacao=self.variacao, nivel=NivelLog.ERRO, evento=EventoLog.ERRO,
            mensagem="x", detalhe={},
        )
        resp = self.client.post(self._url(execucao=ex))
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_execucao_de_outra_instancia_devolve_404(self):
        outra = Instancia.objects.create(nome="Outra", access_token="t")
        resp = self.client.post(self._url(slug=outra.slug))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_variacao_de_outra_instancia_devolve_404(self):
        _inst, _ex, v_outra, _log = _cenario(
            instancia=Instancia.objects.create(
                nome="B", access_token="t", tiny_origem_padrao=0, tiny_unidade_medida_padrao="UN"
            )
        )
        resp = self.client.post(self._url(variacao=v_outra))
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_exige_autenticacao(self):
        from rest_framework.test import APIClient

        resp = APIClient().post(self._url())
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
