"""
Rotina automática (Celery Beat): `verificar_e_disparar_sincronizacoes` decide
quem venceu a cadência e agenda `sincronizar_fornecedor_task`, que importa o
espelho e — SÓ quando `CadenciaFornecedor.propagar_tiny` está ligado — dispara
a propagação ao Tiny (`propagar_fornecedor_tiny_task`).
"""

from copy import deepcopy
from datetime import timedelta
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import call, patch

from django.test import TestCase, TransactionTestCase
from django.utils import timezone

from apps.catalogo.models import Produto, Variacao
from apps.instancias.models import CredencialFornecedor, Instancia
from apps.sincronizacao.models import Execucao, StatusExecucao, TipoExecucao

from ..models import CadenciaFornecedor
from ..tasks import (
    reconciliar_importacoes_fornecedor_stale,
    sincronizar_fornecedor_task,
    verificar_e_disparar_sincronizacoes,
)
from .fixtures import SOMARCAS_ITEM_COM_ESTOQUE


def _somarcas(**over):
    item = deepcopy(SOMARCAS_ITEM_COM_ESTOQUE)
    item.update(over)
    return item


class VerificarEDispararTests(TestCase):
    def setUp(self):
        self.instancia = Instancia.objects.create(nome="Loja")
        CredencialFornecedor.objects.create(
            instancia=self.instancia, fornecedor="somarcas", credenciais={"u": "x"}, ativo=True
        )
        self.cadencia = CadenciaFornecedor.objects.get(
            instancia=self.instancia, fornecedor="somarcas"
        )

    @patch("apps.fornecedores.tasks.sincronizar_fornecedor_task.delay")
    def test_cadencia_desligada_nunca_dispara(self, mock_delay):
        self.cadencia.ativo = False
        self.cadencia.proxima_execucao_em = timezone.now() - timedelta(hours=1)
        self.cadencia.save()

        verificar_e_disparar_sincronizacoes()

        mock_delay.assert_not_called()

    @patch("apps.fornecedores.tasks.sincronizar_fornecedor_task.delay")
    def test_cadencia_ativa_ainda_no_prazo_nao_dispara(self, mock_delay):
        self.cadencia.ativo = True
        self.cadencia.proxima_execucao_em = timezone.now() + timedelta(minutes=30)
        self.cadencia.save()

        verificar_e_disparar_sincronizacoes()

        mock_delay.assert_not_called()

    @patch("apps.fornecedores.tasks.sincronizar_fornecedor_task.delay")
    def test_cadencia_vencida_dispara_e_reprograma_pelo_intervalo(self, mock_delay):
        self.cadencia.ativo = True
        self.cadencia.intervalo_minutos = 120
        self.cadencia.proxima_execucao_em = timezone.now() - timedelta(minutes=5)
        self.cadencia.save()

        antes = timezone.now()
        verificar_e_disparar_sincronizacoes()

        mock_delay.assert_called_once_with(self.instancia.id, "somarcas")
        self.cadencia.refresh_from_db()
        # próxima ~ agora + 120 min
        delta = self.cadencia.proxima_execucao_em - antes
        self.assertGreater(delta, timedelta(minutes=118))
        self.assertLess(delta, timedelta(minutes=122))

    @patch("apps.fornecedores.tasks.sincronizar_fornecedor_task.delay")
    def test_primeira_vez_proxima_execucao_nula_dispara_imediatamente(self, mock_delay):
        self.cadencia.ativo = True
        self.cadencia.proxima_execucao_em = None
        self.cadencia.save()

        verificar_e_disparar_sincronizacoes()

        mock_delay.assert_called_once()

    @patch("apps.fornecedores.tasks.sincronizar_fornecedor_task.delay")
    def test_claim_repetido_da_mesma_cadencia_dispara_uma_so_vez(self, mock_delay):
        self.cadencia.ativo = True
        self.cadencia.proxima_execucao_em = timezone.now() - timedelta(minutes=1)
        self.cadencia.save()

        verificar_e_disparar_sincronizacoes()
        verificar_e_disparar_sincronizacoes()

        mock_delay.assert_called_once_with(self.instancia.id, "somarcas")

    @patch("apps.fornecedores.tasks.sincronizar_fornecedor_task.delay")
    def test_fornecedores_e_instancias_diferentes_nao_compartilham_claim(self, mock_delay):
        outra = Instancia.objects.create(nome="Outra loja")
        CredencialFornecedor.objects.create(
            instancia=outra, fornecedor="spot", credenciais={"u": "y"}, ativo=True
        )
        self.cadencia.ativo = True
        self.cadencia.save(update_fields=["ativo"])
        CadenciaFornecedor.objects.filter(ativo=True).update(proxima_execucao_em=timezone.now())
        CadenciaFornecedor.objects.filter(instancia=outra, fornecedor="spot").update(
            ativo=True, proxima_execucao_em=timezone.now()
        )

        verificar_e_disparar_sincronizacoes()

        self.assertCountEqual(mock_delay.call_args_list, [call(self.instancia.id, "somarcas"), call(outra.id, "spot")])

    @patch("apps.fornecedores.tasks.call_command")
    def test_task_defensiva_nao_inicia_importacao_ativa(self, mock_command):
        Execucao.objects.create(
            instancia=self.instancia,
            fornecedor="somarcas",
            tipo=TipoExecucao.INCREMENTAL,
            status=StatusExecucao.RODANDO,
            heartbeat_em=timezone.now(),
        )

        sincronizar_fornecedor_task(self.instancia.id, "somarcas")

        mock_command.assert_not_called()

    @patch("apps.fornecedores.tasks.call_command")
    def test_importacao_interrompida_nao_bloqueia_nova_rodada(self, mock_command):
        Execucao.objects.create(
            instancia=self.instancia,
            fornecedor="somarcas",
            tipo=TipoExecucao.INCREMENTAL,
            status=StatusExecucao.INTERROMPIDO,
            finalizada_em=timezone.now(),
        )

        sincronizar_fornecedor_task(self.instancia.id, "somarcas")

        mock_command.assert_called_once()

    def test_reconciliador_marca_importacao_stale(self):
        execucao = Execucao.objects.create(
            instancia=self.instancia,
            fornecedor="somarcas",
            tipo=TipoExecucao.INCREMENTAL,
            status=StatusExecucao.RODANDO,
            heartbeat_em=timezone.now() - timedelta(minutes=31),
        )

        self.assertEqual(reconciliar_importacoes_fornecedor_stale(), 1)
        execucao.refresh_from_db()
        self.assertEqual(execucao.status, StatusExecucao.INTERROMPIDO)


class ClaimConcorrenciaTests(TransactionTestCase):
    reset_sequences = True

    def setUp(self):
        instancia = Instancia.objects.create(nome="Loja concorrente")
        CredencialFornecedor.objects.create(
            instancia=instancia, fornecedor="somarcas", credenciais={"u": "x"}, ativo=True
        )
        CadenciaFornecedor.objects.filter(instancia=instancia, fornecedor="somarcas").update(
            ativo=True, proxima_execucao_em=timezone.now() - timedelta(minutes=1)
        )
        self.instancia_id = instancia.id

    @patch("apps.fornecedores.tasks.sincronizar_fornecedor_task.delay")
    def test_duas_execucoes_concorrentes_fazem_um_unico_disparo(self, mock_delay):
        with ThreadPoolExecutor(max_workers=2) as executor:
            futures = [executor.submit(verificar_e_disparar_sincronizacoes) for _ in range(2)]
            for future in futures:
                future.result()

        self.assertEqual(mock_delay.call_count, 1)
        self.assertEqual(mock_delay.call_args.args, (self.instancia_id, "somarcas"))


class SincronizarFornecedorTaskPropagacaoTests(TestCase):
    def setUp(self):
        self.instancia = Instancia.objects.create(
            nome="Loja", access_token="tok", tiny_origem_padrao=0, tiny_unidade_medida_padrao="UN"
        )
        CredencialFornecedor.objects.create(
            instancia=self.instancia, fornecedor="somarcas", credenciais={"u": "x"}, ativo=True,
            tiny_fornecedor_id=762735197,
        )
        self.cadencia = CadenciaFornecedor.objects.get(
            instancia=self.instancia, fornecedor="somarcas"
        )
        self.cadencia.ativo = True
        self.cadencia.save()

    @patch("apps.catalogo.tasks.propagar_fornecedor_tiny_task.delay")
    @patch("apps.fornecedores.somarcas.SomarcasFornecedor.buscar")
    def test_sem_propagar_tiny_so_atualiza_o_espelho(self, mock_buscar, mock_prop):
        mock_buscar.return_value = [_somarcas()]

        sincronizar_fornecedor_task(self.instancia.id, "somarcas")

        self.assertEqual(Produto.objects.count(), 1)
        mock_prop.assert_not_called()

    @patch("apps.catalogo.tasks.propagar_fornecedor_tiny_task.delay")
    @patch("apps.fornecedores.somarcas.SomarcasFornecedor.buscar")
    def test_com_propagar_tiny_dispara_a_propagacao_apos_o_espelho(self, mock_buscar, mock_prop):
        mock_buscar.return_value = [_somarcas()]
        self.cadencia.propagar_tiny = True
        self.cadencia.save()

        sincronizar_fornecedor_task(self.instancia.id, "somarcas")

        self.assertEqual(Produto.objects.count(), 1)
        mock_prop.assert_called_once_with(self.instancia.id, "somarcas")

    @patch("apps.catalogo.tasks.propagar_fornecedor_tiny_task.delay")
    @patch("apps.fornecedores.somarcas.SomarcasFornecedor.buscar")
    def test_propagar_tiny_ligado_mas_cadencia_inativa_nao_propaga(self, mock_buscar, mock_prop):
        mock_buscar.return_value = [_somarcas()]
        self.cadencia.ativo = False
        self.cadencia.propagar_tiny = True
        self.cadencia.save()

        sincronizar_fornecedor_task(self.instancia.id, "somarcas")

        mock_prop.assert_not_called()

    @patch("apps.catalogo.tasks.propagar_fornecedor_tiny_task.delay")
    @patch("apps.fornecedores.somarcas.SomarcasFornecedor.buscar", side_effect=RuntimeError("Só Marcas fora do ar"))
    def test_erro_do_fornecedor_nao_dispara_propagacao(self, _mb, mock_prop):
        self.cadencia.propagar_tiny = True
        self.cadencia.save()

        # o comando marca a Execucao como falha e levanta CommandError, que a
        # task trata como skip esperado — sem propagar nada ao Tiny.
        sincronizar_fornecedor_task(self.instancia.id, "somarcas")

        mock_prop.assert_not_called()
        self.assertEqual(
            Execucao.objects.filter(fornecedor="somarcas", status=StatusExecucao.FALHA).count(), 1
        )

    @patch("apps.catalogo.tasks.propagar_fornecedor_tiny_task.delay")
    @patch("apps.fornecedores.somarcas.SomarcasFornecedor.buscar")
    def test_cadastro_tiny_ativo_pula_espelho_e_propagacao(self, mock_buscar, mock_prop):
        mock_buscar.return_value = [_somarcas()]
        self.cadencia.propagar_tiny = True
        self.cadencia.save()
        Execucao.objects.create(
            instancia=self.instancia, fornecedor="somarcas", tipo=TipoExecucao.CADASTRO_TINY,
            status=StatusExecucao.RODANDO, heartbeat_em=timezone.now(),
        )

        sincronizar_fornecedor_task(self.instancia.id, "somarcas")

        mock_buscar.assert_not_called()
        mock_prop.assert_not_called()
        self.assertEqual(Variacao.objects.count(), 0)
