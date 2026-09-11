from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.test import TestCase, TransactionTestCase

from apps.instancias.models import Instancia

from .models import Execucao, LogItem, NivelLog, StatusExecucao, TipoExecucao
from .locks import lock_fornecedor


class ExecucaoELogItemTests(TestCase):
    def test_execucao_e_log_item_sao_criados_e_associados(self):
        instancia = Instancia.objects.create(nome="Instância de Teste")
        execucao = Execucao.objects.create(
            instancia=instancia,
            fornecedor="xbz",
            tipo=TipoExecucao.CARGA_INICIAL,
            status=StatusExecucao.RODANDO,
        )
        log = LogItem.objects.create(
            execucao=execucao,
            nivel=NivelLog.INFO,
            mensagem="Sincronização iniciada",
        )
        self.assertEqual(execucao.logs.count(), 1)
        self.assertEqual(log.execucao, execucao)

    def test_log_sobrevive_a_exclusao_da_variacao_associada(self):
        from apps.catalogo.models import Produto, Variacao
        from decimal import Decimal

        instancia = Instancia.objects.create(nome="Outra Instância")
        produto = Produto.objects.create(
            instancia=instancia, fornecedor="xbz", codigo_pai="0001", nome="Produto"
        )
        variacao = Variacao.objects.create(
            produto=produto, sku="0001-A", nome="Variação", preco=Decimal("1.00"), estoque=1
        )
        execucao = Execucao.objects.create(
            instancia=instancia, fornecedor="xbz", tipo=TipoExecucao.INCREMENTAL
        )
        log = LogItem.objects.create(execucao=execucao, variacao=variacao, mensagem="teste")

        variacao.delete()
        log.refresh_from_db()
        self.assertIsNone(log.variacao)


class AdvisoryLockTests(TransactionTestCase):
    def test_chaves_de_fornecedores_e_instancias_diferentes_podem_ser_adquiridas_em_paralelo(self):
        barrier = Barrier(2)

        def acquire(instancia_id, fornecedor):
            with lock_fornecedor(instancia_id, fornecedor) as acquired:
                barrier.wait(timeout=5)
                return acquired

        with ThreadPoolExecutor(max_workers=2) as executor:
            resultados = list(
                executor.map(
                    lambda par: acquire(*par),
                    [(103, "somarcas"), (103, "spot")],
                )
            )
        self.assertEqual(resultados, [True, True])

        with ThreadPoolExecutor(max_workers=2) as executor:
            resultados = list(
                executor.map(
                    lambda par: acquire(*par),
                    [(104, "somarcas"), (105, "somarcas")],
                )
            )
        self.assertEqual(resultados, [True, True])

    def test_lock_e_liberado_ao_sair_normalmente_e_pode_ser_adquirido_novamente(self):
        with lock_fornecedor(101, "somarcas") as acquired:
            self.assertTrue(acquired)

        with lock_fornecedor(101, "somarcas") as acquired:
            self.assertTrue(acquired)

    def test_lock_e_liberado_quando_o_bloco_termina_com_excecao(self):
        with self.assertRaises(RuntimeError):
            with lock_fornecedor(102, "somarcas") as acquired:
                self.assertTrue(acquired)
                raise RuntimeError("falha simulada")

        with lock_fornecedor(102, "somarcas") as acquired:
            self.assertTrue(acquired)
