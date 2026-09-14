from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.catalogo.tasks import AUTOMATIC_CADASTRO_LOTE
from apps.catalogo.tasks import _propagar_dados, propagar_fornecedor_tiny_task


class PropagarFornecedorTinyUnitTests(SimpleTestCase):
    """Testes da orquestração automática sem banco, Redis ou APIs externas."""

    def setUp(self):
        self.instancia = SimpleNamespace(id=7, slug="loja-teste", access_token="token-local")
        self.lock = MagicMock()
        self.lock.__enter__.return_value = True
        self.lock.__exit__.return_value = False

    def _rodar(self, *, ordem=None):
        ordem = ordem if ordem is not None else []
        with (
            patch("apps.catalogo.tasks.Instancia.objects.get", return_value=self.instancia),
            patch("apps.catalogo.tasks.lock_instancia_tiny", return_value=self.lock) as mock_lock,
            patch("apps.catalogo.tasks.tiny_sync.execucao_cadastro_tiny_aberta", return_value=None),
            patch("apps.catalogo.tasks.RetentativaLote.objects.filter") as mock_lotes,
            patch("apps.catalogo.tasks._propagar_novos_e_imagens") as mock_novos,
            patch("apps.catalogo.tasks._propagar_dados") as mock_dados,
            patch("apps.catalogo.tasks._propagar_estoque") as mock_estoque,
        ):
            mock_lotes.return_value.exists.return_value = False
            mock_novos.side_effect = lambda *args: ordem.append("novos/imagens")
            mock_dados.side_effect = lambda *args: ordem.append("dados")
            mock_estoque.side_effect = lambda *args: ordem.append("estoque")

            propagar_fornecedor_tiny_task(self.instancia.id, "asia")

        return mock_lock, mock_novos, mock_dados, mock_estoque

    def test_chama_as_tres_etapas_na_ordem_controlada(self):
        ordem = []

        mock_lock, mock_novos, mock_dados, mock_estoque = self._rodar(ordem=ordem)

        self.assertEqual(ordem, ["novos/imagens", "dados", "estoque"])
        mock_novos.assert_called_once_with(self.instancia, "asia")
        mock_dados.assert_called_once_with(self.instancia, "asia")
        mock_estoque.assert_called_once_with(self.instancia, "asia")
        mock_lock.assert_called_once_with(self.instancia.id)

    def test_etapa_de_dados_reutiliza_command_com_lote_25(self):
        with patch("apps.catalogo.tasks.call_command") as mock_command:
            _propagar_dados(self.instancia, "asia")

        mock_command.assert_called_once_with(
            "corrigir_dados_produto_tiny",
            instancia=self.instancia.slug,
            fornecedor="asia",
            executar=True,
            limite=AUTOMATIC_CADASTRO_LOTE,
        )
        self.assertEqual(AUTOMATIC_CADASTRO_LOTE, 25)

    def test_erro_da_etapa_de_dados_e_absorvido_sem_chamada_real(self):
        with patch(
            "apps.catalogo.tasks.call_command",
            side_effect=RuntimeError("erro simulado"),
        ) as mock_command, patch("requests.request") as mock_request:
            _propagar_dados(self.instancia, "asia")

        mock_command.assert_called_once()
        mock_request.assert_not_called()

    def test_conta_tiny_desconectada_nao_entra_no_fluxo(self):
        self.instancia.access_token = ""
        with (
            patch("apps.catalogo.tasks.Instancia.objects.get", return_value=self.instancia),
            patch("apps.catalogo.tasks.lock_instancia_tiny") as mock_lock,
            patch("apps.catalogo.tasks._propagar_novos_e_imagens") as mock_novos,
            patch("apps.catalogo.tasks._propagar_dados") as mock_dados,
            patch("apps.catalogo.tasks._propagar_estoque") as mock_estoque,
        ):
            propagar_fornecedor_tiny_task(self.instancia.id, "asia")

        mock_lock.assert_not_called()
        mock_novos.assert_not_called()
        mock_dados.assert_not_called()
        mock_estoque.assert_not_called()

    def test_lock_ocupado_reagenda_e_nao_executa_etapas(self):
        self.lock.__enter__.return_value = False
        with (
            patch("apps.catalogo.tasks.Instancia.objects.get", return_value=self.instancia),
            patch("apps.catalogo.tasks.lock_instancia_tiny", return_value=self.lock),
            patch("apps.catalogo.tasks._reagendar_task_tiny") as mock_reagendar,
            patch("apps.catalogo.tasks._propagar_novos_e_imagens") as mock_novos,
            patch("apps.catalogo.tasks._propagar_dados") as mock_dados,
            patch("apps.catalogo.tasks._propagar_estoque") as mock_estoque,
        ):
            propagar_fornecedor_tiny_task(self.instancia.id, "asia")

        mock_reagendar.assert_called_once()
        mock_novos.assert_not_called()
        mock_dados.assert_not_called()
        mock_estoque.assert_not_called()

    def test_orquestrador_nao_instancia_cliente_tiny_nem_rate_limiter(self):
        with (
            patch("apps.catalogo.tasks.Instancia.objects.get", return_value=self.instancia),
            patch("apps.catalogo.tasks.lock_instancia_tiny", return_value=self.lock),
            patch("apps.catalogo.tasks.tiny_sync.execucao_cadastro_tiny_aberta", return_value=None),
            patch("apps.catalogo.tasks.RetentativaLote.objects.filter") as mock_lotes,
            patch("apps.catalogo.tasks._propagar_novos_e_imagens"),
            patch("apps.catalogo.tasks._propagar_dados"),
            patch("apps.catalogo.tasks._propagar_estoque"),
            patch("apps.instancias.tiny_client.TinyApiClient") as mock_cliente,
            patch("apps.instancias.tiny_throttle.RateLimiterCompartilhado") as mock_limiter,
        ):
            mock_lotes.return_value.exists.return_value = False
            propagar_fornecedor_tiny_task(self.instancia.id, "asia")

        mock_cliente.assert_not_called()
        mock_limiter.assert_not_called()
