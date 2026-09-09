"""
`retentar_lote_task` — job em background que retenta em lote os SKUs com erro
de UMA Execucao. Cada SKU passa por `cadastrar_variacao_individual` ->
`_processar_variacao` (mesma regra do cadastro em massa e do retry individual).
Histórico preservado: LogItems appendados na Execucao original.
"""

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.instancias.models import CredencialFornecedor, Instancia
from apps.instancias.tiny_client import TinyApiValidationError
from apps.sincronizacao.auditoria import logs_da_variacao, resumo_auditoria
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

from ..models import Produto, StatusVariacao, Variacao
from ..tasks import reconciliar_retentativas_lote_travadas, retentar_lote_task

TINY_FORN_ID = 752133514


def _cenario(*, n_erros=3, fornecedor="asia"):
    instancia = Instancia.objects.create(
        nome="Loja", access_token="tok", tiny_origem_padrao=0, tiny_unidade_medida_padrao="UN"
    )
    CredencialFornecedor.objects.create(
        instancia=instancia, fornecedor=fornecedor, tiny_fornecedor_id=TINY_FORN_ID
    )
    execucao = Execucao.objects.create(
        instancia=instancia, fornecedor=fornecedor, tipo=TipoExecucao.CADASTRO_TINY,
        status=StatusExecucao.PARCIAL, finalizada_em=timezone.now(),
        total_lidos=n_erros, total_cadastrados=0, total_novos=0, total_erros=n_erros, total_ignorados=0,
    )
    variacoes, logs_originais = [], []
    for i in range(n_erros):
        produto = Produto.objects.create(
            instancia=instancia, fornecedor=fornecedor, codigo_pai=f"p{i}", nome=f"P{i}",
            descricao="Descrição rica.",
        )
        v = Variacao.objects.create(
            produto=produto, sku=f"SKU-{i}", nome=f"SKU-{i}", preco=Decimal("10.00"), estoque=5,
        )
        Variacao.objects.filter(pk=v.pk).update(
            status=StatusVariacao.ERRO, ultimo_erro=f"Falha original {i}"
        )
        v.refresh_from_db()
        variacoes.append(v)
        logs_originais.append(
            LogItem.objects.create(
                execucao=execucao, variacao=v, nivel=NivelLog.ERRO, evento=EventoLog.ERRO,
                mensagem=f"Falha ao sincronizar SKU SKU-{i}", detalhe={"erro": f"Falha original {i}"},
            )
        )
    return instancia, execucao, variacoes, logs_originais


def _lote(execucao, variacoes, **extra):
    dados = {
        "execucao": execucao,
        "variacao_ids": [v.id for v in variacoes],
        "total": len(variacoes),
        "lease_token": "tok-lote",
        "heartbeat_em": timezone.now(),
    }
    dados.update(extra)
    return RetentativaLote.objects.create(**dados)


class RetentarLoteTaskTests(TestCase):
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    def test_lote_com_sucesso_total(self, mock_criar, _mb):
        instancia, execucao, variacoes, originais = _cenario(n_erros=3)
        mock_criar.side_effect = lambda p: {"id": 900 + int(p["sku"][-1]), "sku": p["sku"]}
        lote = _lote(execucao, variacoes)

        retentar_lote_task(lote.id, "tok-lote")

        lote.refresh_from_db()
        self.assertEqual(lote.status, StatusRetentativaLote.CONCLUIDO)
        self.assertEqual((lote.processados, lote.sucessos, lote.erros, lote.ignorados), (3, 3, 0, 0))
        self.assertIsNotNone(lote.finalizado_em)

        for v in variacoes:
            v.refresh_from_db()
            self.assertEqual(v.status, StatusVariacao.CADASTRADO)
            self.assertTrue(v.tiny_id)

        execucao.refresh_from_db()
        self.assertEqual(execucao.total_erros, 0)
        self.assertEqual(execucao.total_cadastrados, 3)
        self.assertEqual(resumo_auditoria(execucao)["erros"], 0)
        # lote zerou os erros -> status final consolidado (badge deixa de ser "Parcial")
        self.assertEqual(execucao.status, StatusExecucao.SUCESSO)
        self.assertTrue(
            LogItem.objects.filter(
                execucao=execucao, mensagem__icontains="Status consolidado"
            ).exists()
        )
        for log in originais:
            self.assertTrue(LogItem.objects.filter(pk=log.pk).exists())

    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    def test_lote_parcial_sucesso_e_falha_misturados_nao_interrompe(self, mock_criar, _mb):
        instancia, execucao, variacoes, originais = _cenario(n_erros=3)

        def criar(p):
            if p["sku"] == "SKU-1":
                raise TinyApiValidationError("Novo erro: NCM inválido")
            return {"id": 999, "sku": p["sku"]}

        mock_criar.side_effect = criar
        lote = _lote(execucao, variacoes)

        retentar_lote_task(lote.id, "tok-lote")

        lote.refresh_from_db()
        self.assertEqual((lote.processados, lote.sucessos, lote.erros), (3, 2, 1))
        self.assertEqual(lote.status, StatusRetentativaLote.CONCLUIDO)

        variacoes[1].refresh_from_db()
        self.assertEqual(variacoes[1].status, StatusVariacao.ERRO)
        self.assertIn("NCM inválido", variacoes[1].ultimo_erro)
        # SKU-0 e SKU-2 cadastraram apesar do erro no meio
        self.assertEqual(Variacao.objects.filter(status=StatusVariacao.CADASTRADO).count(), 2)

        execucao.refresh_from_db()
        self.assertEqual(execucao.total_erros, 1)
        self.assertEqual(execucao.total_cadastrados, 2)
        # ainda sobrou 1 erro -> continua parcial
        self.assertEqual(execucao.status, StatusExecucao.PARCIAL)

    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto", return_value={"id": 5, "sku": "x"})
    def test_idempotencia_sku_ja_cadastrado_e_pulado(self, mock_criar, _mb):
        instancia, execucao, variacoes, originais = _cenario(n_erros=3)
        # SKU-1 já foi cadastrado (retry individual, rodada anterior…)
        Variacao.objects.filter(pk=variacoes[1].pk).update(
            status=StatusVariacao.CADASTRADO, tiny_id="42"
        )
        lote = _lote(execucao, variacoes)

        retentar_lote_task(lote.id, "tok-lote")

        lote.refresh_from_db()
        self.assertEqual((lote.processados, lote.sucessos, lote.ignorados), (3, 2, 1))
        # criar_produto chamado só para SKU-0 e SKU-2
        skus_criados = {c.args[0]["sku"] for c in mock_criar.call_args_list}
        self.assertEqual(skus_criados, {"SKU-0", "SKU-2"})
        variacoes[1].refresh_from_db()
        self.assertEqual(variacoes[1].tiny_id, "42")  # intacto

    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto", return_value={"id": 7, "sku": "x"})
    def test_historico_do_erro_original_preservado(self, _mc, _mb):
        instancia, execucao, variacoes, originais = _cenario(n_erros=2)
        antes = {log.pk: (log.mensagem, log.detalhe, log.criado_em) for log in originais}
        lote = _lote(execucao, variacoes)

        retentar_lote_task(lote.id, "tok-lote")

        for log in originais:
            atual = LogItem.objects.get(pk=log.pk)  # ainda existe, imutável
            self.assertEqual((atual.mensagem, atual.detalhe, atual.criado_em), antes[log.pk])
        # cronologia por SKU: erro -> marcador -> criado
        for v in variacoes:
            eventos = [lg.evento for lg in logs_da_variacao(execucao, v.id)]
            self.assertEqual(eventos, [EventoLog.ERRO, EventoLog.GERAL, EventoLog.CRIADO])

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    def test_claim_aborta_se_o_lease_nao_bate(self, mock_criar):
        instancia, execucao, variacoes, originais = _cenario(n_erros=1)
        lote = _lote(execucao, variacoes)

        retentar_lote_task(lote.id, "token-errado")

        lote.refresh_from_db()
        self.assertEqual(lote.status, StatusRetentativaLote.RODANDO)  # intacto
        self.assertEqual(lote.processados, 0)
        mock_criar.assert_not_called()

    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto", return_value={"id": 1, "sku": "x"})
    def test_lease_trocado_no_meio_faz_o_job_parar_sem_finalizar(self, _mc, _mb):
        instancia, execucao, variacoes, originais = _cenario(n_erros=3)
        lote = _lote(execucao, variacoes)

        from apps.catalogo import tasks as tasks_mod

        real = tasks_mod.cadastrar_variacao_individual
        chamadas = {"n": 0}

        def espiao(*a, **k):
            chamadas["n"] += 1
            resultado = real(*a, **k)
            if chamadas["n"] == 1:  # outra retomada assumiu o job depois do 1º SKU
                RetentativaLote.objects.filter(pk=lote.id).update(lease_token="outro-dono")
            return resultado

        with patch("apps.catalogo.tasks.cadastrar_variacao_individual", side_effect=espiao):
            retentar_lote_task(lote.id, "tok-lote")

        lote.refresh_from_db()
        self.assertEqual(lote.status, StatusRetentativaLote.RODANDO)  # NÃO finalizou (não é o dono)
        self.assertEqual(lote.processados, 1)  # parou após o 1º

    def test_reaper_marca_lote_travado_como_interrompido(self):
        instancia, execucao, variacoes, originais = _cenario(n_erros=1)
        lote = _lote(execucao, variacoes, heartbeat_em=timezone.now() - timedelta(hours=1))

        self.assertEqual(reconciliar_retentativas_lote_travadas(), 1)
        lote.refresh_from_db()
        self.assertEqual(lote.status, StatusRetentativaLote.INTERROMPIDO)

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    def test_parada_solicitada_antes_do_proximo_item_preserva_a_fila(self, mock_criar):
        instancia, execucao, variacoes, originais = _cenario(n_erros=2)
        lote = _lote(execucao, variacoes, parada_solicitada=True)

        retentar_lote_task(lote.id, "tok-lote")

        lote.refresh_from_db()
        self.assertEqual(lote.status, StatusRetentativaLote.INTERROMPIDO)
        self.assertEqual(lote.processados, 0)
        self.assertEqual(lote.parada_solicitada, True)
        mock_criar.assert_not_called()
        self.assertTrue(
            LogItem.objects.filter(
                execucao=execucao,
                mensagem__icontains=f"Retentativa em lote #{lote.id} interrompida",
            ).exists()
        )

    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto", return_value={"id": 1, "sku": "x"})
    def test_parada_apos_item_preserva_item_concluido_e_nao_processa_os_demais(self, mock_criar, _mb):
        instancia, execucao, variacoes, originais = _cenario(n_erros=3)
        lote = _lote(execucao, variacoes)

        from apps.catalogo import tasks as tasks_mod

        real = tasks_mod.cadastrar_variacao_individual
        chamadas = {"n": 0}

        def parar_depois_do_primeiro(*args, **kwargs):
            chamadas["n"] += 1
            resultado = real(*args, **kwargs)
            if chamadas["n"] == 1:
                RetentativaLote.objects.filter(pk=lote.id).update(parada_solicitada=True)
            return resultado

        with patch("apps.catalogo.tasks.cadastrar_variacao_individual", side_effect=parar_depois_do_primeiro):
            retentar_lote_task(lote.id, "tok-lote")

        lote.refresh_from_db()
        self.assertEqual(lote.status, StatusRetentativaLote.INTERROMPIDO)
        self.assertEqual((lote.processados, lote.sucessos), (1, 1))
        self.assertEqual(mock_criar.call_count, 1)
        variacoes[0].refresh_from_db()
        self.assertEqual(variacoes[0].status, StatusVariacao.CADASTRADO)
        for variacao in variacoes[1:]:
            variacao.refresh_from_db()
            self.assertEqual(variacao.status, StatusVariacao.ERRO)

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    def test_variacao_de_outra_instancia_na_fila_e_ignorada(self, mock_criar):
        instancia, execucao, variacoes, originais = _cenario(n_erros=1)
        _outra_inst, _e, outras, _l = _cenario(n_erros=1)
        lote = _lote(execucao, [variacoes[0]])
        RetentativaLote.objects.filter(pk=lote.id).update(
            variacao_ids=[variacoes[0].id, outras[0].id], total=2
        )

        with patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None):
            mock_criar.return_value = {"id": 3, "sku": "SKU-0"}
            retentar_lote_task(lote.id, "tok-lote")

        lote.refresh_from_db()
        self.assertEqual(lote.ignorados, 1)  # a de outra instância
        self.assertEqual(lote.sucessos, 1)
        outras[0].refresh_from_db()
        self.assertEqual(outras[0].status, StatusVariacao.ERRO)  # intacta
