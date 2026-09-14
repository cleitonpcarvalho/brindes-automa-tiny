from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.catalogo.models import Produto, StatusVariacao, Variacao
from apps.instancias.models import CredencialFornecedor, Instancia
from apps.sincronizacao.models import Execucao, StatusExecucao, TipoExecucao
from apps.fornecedores.tasks import executar_sincronizacao_manual_task, sincronizar_fornecedor_task

from .fixtures import XBZ_GRUPO_06520, XBZ_GRUPO_P12288


class ImportarFornecedorIdempotenciaTests(TestCase):
    """
    Usa o mesmo recorte real da xbz (grupo "06520", 6 cores) para confirmar
    que rodar a importação duas vezes seguidas não duplica nada nem altera
    um status já definido: a segunda rodada deve reconhecer que nada mudou
    (mesmo hash) e contar tudo como ignorado.
    """

    def setUp(self):
        self.instancia = Instancia.objects.create(nome="Loja de Teste")
        CredencialFornecedor.objects.create(
            instancia=self.instancia,
            fornecedor="xbz",
            credenciais={"cnpj": "0", "token": "0"},
            ativo=True,
        )

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_primeira_importacao_cria_produto_e_variacoes(self, mock_buscar):
        mock_buscar.return_value = XBZ_GRUPO_06520
        call_command("importar_fornecedor", self.instancia.slug, "xbz", "--mirror-only")

        self.assertEqual(Produto.objects.count(), 1)
        self.assertEqual(Variacao.objects.count(), 6)

        execucao = Execucao.objects.get()
        self.assertEqual(execucao.status, StatusExecucao.SUCESSO)
        self.assertEqual(execucao.total_lidos, 6)
        self.assertEqual(execucao.total_novos, 6)
        self.assertEqual(execucao.total_atualizados, 0)
        self.assertEqual(execucao.total_ignorados, 0)

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_rodar_duas_vezes_seguidas_nao_duplica_nada(self, mock_buscar):
        mock_buscar.return_value = XBZ_GRUPO_06520
        call_command("importar_fornecedor", self.instancia.slug, "xbz", "--mirror-only")
        call_command("importar_fornecedor", self.instancia.slug, "xbz", "--force", "--mirror-only")

        self.assertEqual(Produto.objects.count(), 1)
        self.assertEqual(Variacao.objects.count(), 6)

        segunda_execucao = Execucao.objects.order_by("-iniciada_em").first()
        self.assertEqual(segunda_execucao.total_novos, 0)
        self.assertEqual(segunda_execucao.total_atualizados, 0)
        self.assertEqual(segunda_execucao.total_ignorados, 6)

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_status_ja_definido_nao_e_alterado_pela_segunda_rodada(self, mock_buscar):
        mock_buscar.return_value = XBZ_GRUPO_06520
        call_command("importar_fornecedor", self.instancia.slug, "xbz", "--mirror-only")

        variacao = Variacao.objects.get(sku="X000019")
        variacao.status = StatusVariacao.CADASTRADO
        variacao.tiny_id = "999"
        variacao.save()

        call_command("importar_fornecedor", self.instancia.slug, "xbz", "--force", "--mirror-only")

        variacao.refresh_from_db()
        self.assertEqual(variacao.status, StatusVariacao.CADASTRADO)
        self.assertEqual(variacao.tiny_id, "999")

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_preco_ou_estoque_mudando_conta_como_atualizado_nao_como_novo(self, mock_buscar):
        mock_buscar.return_value = XBZ_GRUPO_06520
        call_command("importar_fornecedor", self.instancia.slug, "xbz", "--mirror-only")

        grupo_com_reposicao = [dict(linha) for linha in XBZ_GRUPO_06520]
        grupo_com_reposicao[0]["QuantidadeDisponivel"] = 99999
        mock_buscar.return_value = grupo_com_reposicao

        call_command("importar_fornecedor", self.instancia.slug, "xbz", "--force", "--mirror-only")

        self.assertEqual(Variacao.objects.count(), 6)  # continua sem duplicar
        variacao = Variacao.objects.get(sku="X000019")
        self.assertEqual(variacao.estoque, 99999)

        segunda_execucao = Execucao.objects.order_by("-iniciada_em").first()
        self.assertEqual(segunda_execucao.total_novos, 0)
        self.assertEqual(segunda_execucao.total_atualizados, 1)
        self.assertEqual(segunda_execucao.total_ignorados, 5)

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_segunda_chamada_no_mesmo_dia_e_permitida_ate_limite(self, mock_buscar):
        mock_buscar.return_value = XBZ_GRUPO_06520
        call_command("importar_fornecedor", self.instancia.slug, "xbz", "--mirror-only")
        call_command("importar_fornecedor", self.instancia.slug, "xbz", "--mirror-only")
        self.assertEqual(mock_buscar.call_count, 2)

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_execucao_de_cadastro_tiny_nao_conta_como_importacao_xbz(self, mock_buscar):
        Execucao.objects.create(
            instancia=self.instancia,
            fornecedor="xbz",
            tipo=TipoExecucao.CADASTRO_TINY,
            status=StatusExecucao.SUCESSO,
        )
        mock_buscar.return_value = XBZ_GRUPO_06520

        call_command("importar_fornecedor", self.instancia.slug, "xbz", "--mirror-only")

        self.assertEqual(mock_buscar.call_count, 1)
        self.assertTrue(
            Execucao.objects.filter(
                instancia=self.instancia,
                fornecedor="xbz",
                tipo=TipoExecucao.INCREMENTAL,
                status=StatusExecucao.SUCESSO,
            ).exists()
        )

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_produto_com_prefixo_p_arroba_entra_direto_como_descontinuado(self, mock_buscar):
        mock_buscar.return_value = XBZ_GRUPO_P12288
        call_command("importar_fornecedor", self.instancia.slug, "xbz", "--mirror-only")

        produto = Produto.objects.get(codigo_pai="P@12288")
        self.assertTrue(produto.descontinuado)
        for variacao in produto.variacoes.all():
            self.assertEqual(variacao.status, StatusVariacao.DESCONTINUADO)


class ImportarFornecedorComExecucaoIdTests(TestCase):
    """
    Passo 10: a sincronização manual via API cria a Execucao antes de
    enfileirar (pra devolver o id na hora) e passa `--execucao-id` pro
    comando reusar em vez de criar uma nova — sem refazer as checagens de
    limite diário/credencial, que a view já fez de forma síncrona.
    """

    def setUp(self):
        self.instancia = Instancia.objects.create(nome="Loja Execucao Manual")
        CredencialFornecedor.objects.create(
            instancia=self.instancia, fornecedor="xbz", credenciais={"cnpj": "0", "token": "0"}, ativo=True
        )

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_reusa_a_execucao_passada_em_vez_de_criar_outra(self, mock_buscar):
        mock_buscar.return_value = XBZ_GRUPO_06520
        execucao = Execucao.objects.create(
            instancia=self.instancia, fornecedor="xbz", tipo=TipoExecucao.INCREMENTAL
        )

        call_command(
            "importar_fornecedor", self.instancia.slug, "xbz", execucao_id=execucao.id, mirror_only=True
        )

        self.assertEqual(Execucao.objects.count(), 1)
        execucao.refresh_from_db()
        self.assertEqual(execucao.status, StatusExecucao.SUCESSO)
        self.assertEqual(execucao.total_novos, 6)

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_execucao_reservada_nao_conta_contra_o_proprio_slot(self, mock_buscar):
        mock_buscar.return_value = XBZ_GRUPO_06520
        Execucao.objects.bulk_create([
            Execucao(
                instancia=self.instancia,
                fornecedor="xbz",
                tipo=TipoExecucao.INCREMENTAL,
                status=StatusExecucao.FALHA,
            )
            for _ in range(23)
        ])
        execucao = Execucao.objects.create(
            instancia=self.instancia, fornecedor="xbz", tipo=TipoExecucao.INCREMENTAL
        )

        call_command(
            "importar_fornecedor", self.instancia.slug, "xbz",
            execucao_id=execucao.id, mirror_only=True,
        )

        mock_buscar.assert_called_once()
        execucao.refresh_from_db()
        self.assertEqual(execucao.status, StatusExecucao.SUCESSO)

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_execucao_id_considera_a_propria_execucao_como_slot_reservado(self, mock_buscar):
        mock_buscar.return_value = XBZ_GRUPO_06520
        call_command("importar_fornecedor", self.instancia.slug, "xbz", "--mirror-only")  # já rodou hoje

        execucao_manual = Execucao.objects.create(
            instancia=self.instancia, fornecedor="xbz", tipo=TipoExecucao.INCREMENTAL
        )
        # A execução reservada não deve contar contra o próprio slot.
        call_command(
            "importar_fornecedor", self.instancia.slug, "xbz", execucao_id=execucao_manual.id, mirror_only=True
        )

        execucao_manual.refresh_from_db()
        self.assertEqual(execucao_manual.status, StatusExecucao.SUCESSO)

    def test_credencial_removida_entre_o_enqueue_e_a_execucao_marca_falha_sem_travar(self):
        CredencialFornecedor.objects.filter(instancia=self.instancia, fornecedor="xbz").delete()
        execucao = Execucao.objects.create(
            instancia=self.instancia, fornecedor="xbz", tipo=TipoExecucao.INCREMENTAL
        )

        with self.assertRaises(CommandError):
            call_command(
                "importar_fornecedor", self.instancia.slug, "xbz", execucao_id=execucao.id, mirror_only=True
            )

        execucao.refresh_from_db()
        self.assertEqual(execucao.status, StatusExecucao.FALHA)
        self.assertIn("credencial ativa", execucao.mensagem_erro)


class LimiteDiarioXbzTests(TestCase):
    def setUp(self):
        self.instancia = Instancia.objects.create(nome="Loja Limite XBZ")
        CredencialFornecedor.objects.create(
            instancia=self.instancia,
            fornecedor="xbz",
            credenciais={"cnpj": "0", "token": "0"},
            ativo=True,
        )

    def _criar_execucoes(self, quantidade, status=StatusExecucao.FALHA):
        Execucao.objects.bulk_create(
            [
                Execucao(
                    instancia=self.instancia,
                    fornecedor="xbz",
                    tipo=TipoExecucao.INCREMENTAL,
                    status=status,
                )
                for _ in range(quantidade)
            ]
        )

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar", return_value=[])
    def test_com_23_tentativas_a_24a_e_permitida(self, mock_buscar):
        self._criar_execucoes(23)
        call_command("importar_fornecedor", self.instancia.slug, "xbz", "--mirror-only")
        mock_buscar.assert_called_once()
        self.assertEqual(Execucao.objects.filter(fornecedor="xbz").count(), 24)

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_com_24_tentativas_a_25a_e_bloqueada(self, mock_buscar):
        self._criar_execucoes(24)
        with self.assertRaises(CommandError):
            call_command("importar_fornecedor", self.instancia.slug, "xbz", "--mirror-only")
        with self.assertRaises(CommandError):
            call_command("importar_fornecedor", self.instancia.slug, "xbz", "--mirror-only")
        mock_buscar.assert_not_called()
        self.assertEqual(Execucao.objects.filter(fornecedor="xbz").count(), 24)

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar", side_effect=TimeoutError("timeout"))
    def test_falha_de_execucao_entra_na_contagem(self, mock_buscar):
        with self.assertRaises(CommandError):
            call_command("importar_fornecedor", self.instancia.slug, "xbz", "--mirror-only")
        mock_buscar.assert_called_once()
        self.assertEqual(Execucao.objects.filter(fornecedor="xbz").count(), 1)

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_force_nao_ignora_limite_xbz(self, mock_buscar):
        self._criar_execucoes(24)
        with self.assertRaises(CommandError):
            call_command("importar_fornecedor", self.instancia.slug, "xbz", "--force", "--mirror-only")
        mock_buscar.assert_not_called()

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_dry_run_xbz_nao_chama_api(self, mock_buscar):
        with self.assertRaises(CommandError):
            call_command("importar_fornecedor", self.instancia.slug, "xbz", "--dry-run", "--mirror-only")
        mock_buscar.assert_not_called()

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_task_automatica_respeita_limite_xbz(self, mock_buscar):
        self._criar_execucoes(24)
        antes = Execucao.objects.filter(fornecedor="xbz").count()
        sincronizar_fornecedor_task(self.instancia.id, "xbz")
        mock_buscar.assert_not_called()
        self.assertEqual(Execucao.objects.filter(fornecedor="xbz").count(), antes)

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar", return_value=[])
    def test_task_automatica_com_limite_disponivel_cria_execucao(self, mock_buscar):
        sincronizar_fornecedor_task(self.instancia.id, "xbz")
        mock_buscar.assert_called_once()
        self.assertEqual(Execucao.objects.filter(fornecedor="xbz").count(), 1)

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_task_manual_respeita_limite_xbz(self, mock_buscar):
        self._criar_execucoes(24)
        execucao = Execucao.objects.create(
            instancia=self.instancia,
            fornecedor="xbz",
            tipo=TipoExecucao.INCREMENTAL,
        )
        executar_sincronizacao_manual_task(execucao.id)
        mock_buscar.assert_not_called()
