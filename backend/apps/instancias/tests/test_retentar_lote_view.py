"""
`POST/GET /api/instancias/<slug>/execucoes/<id>/retentar-lote/` — dispara e
acompanha o job de retentativa em lote. O navegador faz UMA requisição; o
processamento é do Celery (`retentar_lote_task`).
"""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework import status

from apps.catalogo.models import Produto, StatusVariacao, Variacao
from apps.sincronizacao.models import (
    EventoLog,
    Execucao,
    LogItem,
    NivelLog,
    RetentativaLote,
    StatusExecucao,
    StatusRetentativaLote,
    TipoExecucao,
)

from ..models import CredencialFornecedor, Instancia
from .test_views import _client_autenticado

TINY_FORN_ID = 752133514
_seq = iter(range(1, 10_000))


def _cenario(*, n_erros=3, n_ok=1, n_bloq=1, fornecedor="asia", instancia=None):
    p = f"c{next(_seq)}-"  # prefixo único por cenário (evita colisão de codigo_pai/sku)
    instancia = instancia or Instancia.objects.create(
        nome="Loja", access_token="tok", tiny_origem_padrao=0, tiny_unidade_medida_padrao="UN"
    )
    CredencialFornecedor.objects.update_or_create(
        instancia=instancia, fornecedor=fornecedor, defaults={"tiny_fornecedor_id": TINY_FORN_ID}
    )
    execucao = Execucao.objects.create(
        instancia=instancia, fornecedor=fornecedor, tipo=TipoExecucao.CADASTRO_TINY,
        status=StatusExecucao.PARCIAL, finalizada_em=timezone.now(),
        total_erros=n_erros, total_cadastrados=n_ok,
    )

    def _mk(sku, *, status_v, evento, tiny_id=""):
        produto = Produto.objects.create(
            instancia=instancia, fornecedor=fornecedor, codigo_pai=sku, nome=sku, descricao="d",
        )
        v = Variacao.objects.create(
            produto=produto, sku=sku, nome=sku, preco=Decimal("10.00"), estoque=5,
        )
        Variacao.objects.filter(pk=v.pk).update(status=status_v, tiny_id=tiny_id)
        v.refresh_from_db()
        LogItem.objects.create(
            execucao=execucao, variacao=v, nivel=NivelLog.INFO, evento=evento,
            mensagem=f"{sku} {evento}", detalhe={"tiny_id": tiny_id} if tiny_id else {"erro": "x"},
        )
        return v

    erros = [_mk(f"{p}ERR-{i}", status_v=StatusVariacao.ERRO, evento=EventoLog.ERRO) for i in range(n_erros)]
    oks = [
        _mk(f"{p}OK-{i}", status_v=StatusVariacao.CADASTRADO, evento=EventoLog.CRIADO, tiny_id=f"7{i}")
        for i in range(n_ok)
    ]
    bloqs = [
        _mk(f"{p}BLK-{i}", status_v=StatusVariacao.PENDENTE, evento=EventoLog.BLOQUEADO)
        for i in range(n_bloq)
    ]
    return instancia, execucao, erros, oks, bloqs


class RetentarLoteViewTests(TestCase):
    def setUp(self):
        self.client = _client_autenticado()
        self.instancia, self.execucao, self.erros, self.oks, self.bloqs = _cenario()

    def _url(self, *, execucao=None, slug=None):
        execucao = execucao or self.execucao
        slug = slug or self.instancia.slug
        return f"/api/instancias/{slug}/execucoes/{execucao.id}/retentar-lote/"

    # -- seleção -------------------------------------------------------

    @patch("apps.instancias.views.retentar_lote_task")
    def test_selecao_de_ids_da_pagina_cria_o_lote_e_enfileira_uma_task(self, mock_task):
        alvos = [self.erros[0].id, self.erros[1].id]
        resp = self.client.post(self._url(), {"variacao_ids": alvos}, content_type="application/json")

        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        lote = RetentativaLote.objects.get(pk=resp.data["id"])
        self.assertEqual(sorted(lote.variacao_ids), sorted(alvos))
        self.assertEqual(lote.total, 2)
        self.assertFalse(lote.selecao_todos)
        mock_task.delay.assert_called_once_with(lote.id, lote.lease_token)

    @patch("apps.instancias.views.retentar_lote_task")
    def test_selecionar_todos_os_erros_resolve_no_servidor_com_uma_requisicao(self, mock_task):
        resp = self.client.post(self._url(), {"todos": True}, content_type="application/json")

        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        lote = RetentativaLote.objects.get(pk=resp.data["id"])
        self.assertEqual(sorted(lote.variacao_ids), sorted(v.id for v in self.erros))
        self.assertEqual(lote.total, len(self.erros))
        self.assertTrue(lote.selecao_todos)
        mock_task.delay.assert_called_once()

    @patch("apps.instancias.views.retentar_lote_task")
    def test_selecao_entre_paginas_aceita_ids_de_qualquer_pagina(self, mock_task):
        instancia, execucao, erros, _o, _b = _cenario(n_erros=60, instancia=self.instancia)
        alvos = [erros[0].id, erros[42].id, erros[59].id]  # "páginas" diferentes
        resp = self.client.post(
            f"/api/instancias/{instancia.slug}/execucoes/{execucao.id}/retentar-lote/",
            {"variacao_ids": alvos}, content_type="application/json",
        )
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(sorted(RetentativaLote.objects.get(pk=resp.data["id"]).variacao_ids), sorted(alvos))

    @patch("apps.instancias.views.retentar_lote_task")
    def test_ids_que_nao_sao_erro_sao_descartados(self, mock_task):
        alvos = [self.erros[0].id, self.oks[0].id, self.bloqs[0].id, 999999]
        resp = self.client.post(self._url(), {"variacao_ids": alvos}, content_type="application/json")

        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        self.assertEqual(RetentativaLote.objects.get(pk=resp.data["id"]).variacao_ids, [self.erros[0].id])

    @patch("apps.instancias.views.retentar_lote_task")
    def test_selecao_vazia_400(self, mock_task):
        resp = self.client.post(self._url(), {"variacao_ids": []}, content_type="application/json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        mock_task.delay.assert_not_called()

    @patch("apps.instancias.views.retentar_lote_task")
    def test_variacao_ids_invalido_400(self, mock_task):
        resp = self.client.post(self._url(), {"variacao_ids": "x"}, content_type="application/json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    # -- concorrência / segurança -----------------------------------

    @patch("apps.instancias.views.retentar_lote_task")
    def test_409_se_ja_ha_um_lote_rodando(self, mock_task):
        RetentativaLote.objects.create(
            execucao=self.execucao, status=StatusRetentativaLote.RODANDO,
            heartbeat_em=timezone.now(), total=1, variacao_ids=[self.erros[0].id],
        )
        resp = self.client.post(self._url(), {"todos": True}, content_type="application/json")
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        mock_task.delay.assert_not_called()

    @patch("apps.instancias.views.retentar_lote_task")
    def test_lote_rodando_mas_travado_libera_novo_lote(self, mock_task):
        from datetime import timedelta

        RetentativaLote.objects.create(
            execucao=self.execucao, status=StatusRetentativaLote.RODANDO,
            heartbeat_em=timezone.now() - timedelta(hours=1), total=1, variacao_ids=[self.erros[0].id],
        )
        resp = self.client.post(self._url(), {"todos": True}, content_type="application/json")
        self.assertEqual(resp.status_code, status.HTTP_202_ACCEPTED)
        mock_task.delay.assert_called_once()

    @patch("apps.instancias.views.retentar_lote_task")
    def test_409_com_sincronizacao_em_massa_ativa(self, mock_task):
        Execucao.objects.create(
            instancia=self.instancia, fornecedor="asia", tipo=TipoExecucao.CADASTRO_TINY,
            status=StatusExecucao.RODANDO, heartbeat_em=timezone.now(),
        )
        resp = self.client.post(self._url(), {"todos": True}, content_type="application/json")
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)

    def test_execucao_de_outra_instancia_404(self):
        outra = Instancia.objects.create(nome="Outra", access_token="t")
        resp = self.client.post(self._url(slug=outra.slug), {"todos": True}, content_type="application/json")
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    @patch("apps.instancias.views.retentar_lote_task")
    def test_ids_de_variacao_de_outra_instancia_sao_isolados(self, mock_task):
        _o, _e, erros_b, _ok, _bl = _cenario(
            instancia=Instancia.objects.create(
                nome="B", access_token="t", tiny_origem_padrao=0, tiny_unidade_medida_padrao="UN"
            )
        )
        resp = self.client.post(
            self._url(), {"variacao_ids": [erros_b[0].id]}, content_type="application/json"
        )
        # nenhum id da instância B casa com os erros da execução A -> 400
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_execucao_que_nao_e_cadastro_tiny_400(self):
        ex = Execucao.objects.create(
            instancia=self.instancia, fornecedor="asia", tipo=TipoExecucao.INCREMENTAL,
            status=StatusExecucao.SUCESSO,
        )
        resp = self.client.post(self._url(execucao=ex), {"todos": True}, content_type="application/json")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_exige_autenticacao(self):
        from rest_framework.test import APIClient

        resp = APIClient().post(self._url(), {"todos": True}, content_type="application/json")
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    # -- progresso (GET) --------------------------------------------

    def test_get_devolve_o_progresso_do_lote_mais_recente(self):
        lote = RetentativaLote.objects.create(
            execucao=self.execucao, status=StatusRetentativaLote.RODANDO,
            heartbeat_em=timezone.now(), total=3, processados=1, sucessos=1,
            variacao_ids=[v.id for v in self.erros],
        )
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["id"], lote.id)
        self.assertEqual(resp.data["total"], 3)
        self.assertEqual(resp.data["processados"], 1)
        self.assertNotIn("variacao_ids", resp.data)

    def test_get_sem_lote_404(self):
        resp = self.client.get(self._url())
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)
