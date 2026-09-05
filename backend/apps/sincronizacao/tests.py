from django.test import TestCase

from apps.instancias.models import Instancia

from .models import Execucao, LogItem, NivelLog, StatusExecucao, TipoExecucao


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
