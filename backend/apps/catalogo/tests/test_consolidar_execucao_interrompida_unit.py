"""Decisão de consolidação histórica sem banco e sem chamadas ao Tiny."""

from io import StringIO
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import SimpleTestCase

from apps.sincronizacao.models import StatusExecucao, TipoExecucao

from ..tasks import (
    consolidar_execucao_interrompida_sem_trabalho,
    execucao_interrompida_sem_trabalho,
)


def _execucao(**overrides):
    dados = {
        "tipo": TipoExecucao.CADASTRO_TINY,
        "status": StatusExecucao.INTERROMPIDO,
        "finalizada_em": None,
        "instancia": Mock(name="instancia"),
        "fornecedor": "asia",
        # Contadores antigos são deliberadamente irrelevantes para a decisão.
        "total_erros": 0,
        "total_ignorados": 102,
    }
    dados.update(overrides)
    return SimpleNamespace(**dados)


class ExecucaoInterrompidaSemTrabalhoUnitTests(SimpleTestCase):
    @patch("apps.catalogo.tasks.TinyApiClient")
    @patch("apps.catalogo.tasks.tiny_sync.fila_cadastro_massa", return_value=[])
    def test_fila_real_vazia_permite_mesmo_com_contadores_historicos(
        self, mock_fila, mock_client
    ):
        execucao = _execucao(total_ignorados=102)

        self.assertTrue(execucao_interrompida_sem_trabalho(execucao))

        mock_fila.assert_called_once_with(execucao.instancia, "asia", limite=1)
        mock_client.assert_not_called()

    @patch(
        "apps.catalogo.tasks.tiny_sync.fila_cadastro_massa",
        return_value=[Mock(name="trabalho_pendente")],
    )
    def test_qualquer_trabalho_real_impede_consolidacao(self, mock_fila):
        execucao = _execucao(total_ignorados=0)

        self.assertFalse(execucao_interrompida_sem_trabalho(execucao))

        mock_fila.assert_called_once_with(execucao.instancia, "asia", limite=1)

    @patch("apps.catalogo.tasks.tiny_sync.fila_cadastro_massa")
    def test_nao_toca_na_fila_de_execucao_que_nao_esta_interrompida(self, mock_fila):
        execucao = _execucao(status=StatusExecucao.PAUSADO)

        self.assertFalse(execucao_interrompida_sem_trabalho(execucao))

        mock_fila.assert_not_called()

    @patch("apps.catalogo.tasks.tiny_sync.fila_cadastro_massa")
    def test_nao_toca_na_fila_de_execucao_ja_finalizada(self, mock_fila):
        execucao = _execucao(finalizada_em=Mock(name="data_finalizacao"))

        self.assertFalse(execucao_interrompida_sem_trabalho(execucao))

        mock_fila.assert_not_called()

    @patch("apps.catalogo.tasks.tiny_sync.fila_cadastro_massa")
    def test_nao_afeta_execucao_de_importacao(self, mock_fila):
        execucao = _execucao(tipo=TipoExecucao.INCREMENTAL)

        self.assertFalse(execucao_interrompida_sem_trabalho(execucao))

        mock_fila.assert_not_called()


class ConsolidarExecucaoInterrompidaUnitTests(SimpleTestCase):
    @patch("apps.catalogo.tasks.TinyApiClient")
    @patch("apps.catalogo.tasks.LogItem")
    @patch("apps.catalogo.tasks.Instancia")
    @patch("apps.catalogo.tasks.Execucao")
    @patch("apps.catalogo.tasks._atualizar_contadores")
    @patch("apps.catalogo.tasks.tiny_sync.fila_cadastro_massa", return_value=[])
    @patch("apps.catalogo.tasks.transaction.atomic")
    @patch("apps.catalogo.tasks.lock_instancia_tiny")
    def test_finaliza_sem_enfileirar_nem_chamar_tiny(
        self,
        mock_lock,
        mock_atomic,
        mock_fila,
        mock_atualizar_contadores,
        mock_execucao_model,
        mock_instancia_model,
        mock_logitem,
        mock_client,
    ):
        mock_lock.return_value.__enter__.return_value = True
        mock_execucao_model.objects.filter.return_value.values.return_value.first.return_value = {
            "instancia_id": 7
        }
        execucao = _execucao(
            instancia_id=7,
            mensagem_erro="worker sem heartbeat",
            pausa_solicitada=True,
            lease_token="lease-antigo",
            total_lidos=1238,
            total_novos=1136,
            total_cadastrados=1136,
            total_erros=0,
            total_ignorados=0,
            save=Mock(),
        )
        (
            mock_execucao_model.objects.select_for_update.return_value
            .select_related.return_value.get.return_value
        ) = execucao

        with patch("apps.catalogo.tasks.cadastrar_produtos_tiny_task.delay") as mock_delay:
            self.assertTrue(consolidar_execucao_interrompida_sem_trabalho(51))

        mock_lock.assert_called_once_with(7)
        mock_atomic.assert_called_once_with()
        mock_instancia_model.objects.select_for_update.return_value.get.assert_called_once_with(pk=7)
        mock_fila.assert_called_once_with(execucao.instancia, "asia", limite=1)
        mock_atualizar_contadores.assert_called_once_with(execucao)
        self.assertEqual(execucao.status, StatusExecucao.SUCESSO)
        self.assertIsNotNone(execucao.finalizada_em)
        self.assertIsNotNone(execucao.heartbeat_em)
        self.assertFalse(execucao.pausa_solicitada)
        self.assertNotEqual(execucao.lease_token, "lease-antigo")
        self.assertEqual(execucao.mensagem_erro, "")
        execucao.save.assert_called_once()
        mock_logitem.objects.create.assert_called_once()
        detalhe_log = mock_logitem.objects.create.call_args.kwargs["detalhe"]
        self.assertEqual(detalhe_log["status_anterior"], StatusExecucao.INTERROMPIDO)
        self.assertEqual(detalhe_log["criterio"], "fila_cadastro_massa_vazia")
        mock_delay.assert_not_called()
        mock_client.assert_not_called()

    @patch("apps.catalogo.tasks.TinyApiClient")
    @patch("apps.catalogo.tasks.LogItem")
    @patch("apps.catalogo.tasks.Instancia")
    @patch("apps.catalogo.tasks.Execucao")
    @patch("apps.catalogo.tasks.lock_instancia_tiny")
    def test_lock_ocupado_nao_altera_nada(
        self,
        mock_lock,
        mock_execucao_model,
        mock_instancia_model,
        mock_logitem,
        mock_client,
    ):
        mock_execucao_model.objects.filter.return_value.values.return_value.first.return_value = {
            "instancia_id": 7
        }
        mock_lock.return_value.__enter__.return_value = False

        self.assertFalse(consolidar_execucao_interrompida_sem_trabalho(51))

        mock_instancia_model.objects.select_for_update.assert_not_called()
        mock_logitem.objects.create.assert_not_called()
        mock_client.assert_not_called()


class ConsolidarStatusExecucoesCommandUnitTests(SimpleTestCase):
    @patch(
        "apps.catalogo.management.commands.consolidar_status_execucoes."
        "consolidar_execucao_interrompida_sem_trabalho",
        return_value=True,
    )
    @patch(
        "apps.catalogo.management.commands.consolidar_status_execucoes."
        "execucao_interrompida_sem_trabalho",
        return_value=True,
    )
    @patch("apps.catalogo.management.commands.consolidar_status_execucoes.Execucao")
    def test_execucao_explicita_consolida_sem_disparar_retomada(
        self, mock_execucao_model, mock_consolidavel, mock_consolidar
    ):
        execucao = SimpleNamespace(pk=51, fornecedor="asia", status=StatusExecucao.INTERROMPIDO)
        (
            mock_execucao_model.objects.filter.return_value
            .select_related.return_value.first.return_value
        ) = execucao

        saida = StringIO()
        call_command("consolidar_status_execucoes", "--execucao", "51", stdout=saida)

        mock_consolidavel.assert_called_once_with(execucao)
        mock_consolidar.assert_called_once_with(51)
        self.assertIn("interrompida -> sucesso", saida.getvalue())

    @patch(
        "apps.catalogo.management.commands.consolidar_status_execucoes."
        "consolidar_execucao_interrompida_sem_trabalho"
    )
    @patch(
        "apps.catalogo.management.commands.consolidar_status_execucoes."
        "execucao_interrompida_sem_trabalho",
        return_value=False,
    )
    @patch("apps.catalogo.management.commands.consolidar_status_execucoes.Execucao")
    def test_execucao_com_fila_nao_e_consolidada(
        self, mock_execucao_model, mock_consolidavel, mock_consolidar
    ):
        execucao = SimpleNamespace(pk=51, fornecedor="asia", status=StatusExecucao.INTERROMPIDO)
        (
            mock_execucao_model.objects.filter.return_value
            .select_related.return_value.first.return_value
        ) = execucao

        saida = StringIO()
        call_command("consolidar_status_execucoes", "--execucao", "51", stdout=saida)

        mock_consolidavel.assert_called_once_with(execucao)
        mock_consolidar.assert_not_called()
        self.assertIn("mantida como interrompida", saida.getvalue())
