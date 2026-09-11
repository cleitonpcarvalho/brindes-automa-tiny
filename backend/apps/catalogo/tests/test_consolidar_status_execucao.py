"""
`consolidar_status_execucao` — reavalia o desfecho de uma Execucao de cadastro
no Tiny JÁ FINALIZADA a partir dos contadores consolidados. Serve para quando
retentativas posteriores zeram os erros de uma execução que fechou `parcial`:
o badge "Parcial / com erros" precisa virar `sucesso`.
"""

from django.test import TestCase
from django.utils import timezone

from apps.instancias.models import Instancia
from apps.catalogo.models import Produto, Variacao
from apps.sincronizacao.models import (
    EventoLog,
    Execucao,
    LogItem,
    StatusExecucao,
    TipoExecucao,
)

from ..tasks import consolidar_status_execucao


def _execucao(**over):
    instancia = Instancia.objects.create(nome="Loja", access_token="tok")
    dados = dict(
        instancia=instancia,
        fornecedor="asia",
        tipo=TipoExecucao.CADASTRO_TINY,
        status=StatusExecucao.PARCIAL,
        finalizada_em=timezone.now(),
        total_lidos=1240,
        total_cadastrados=1240,
        total_erros=0,
        total_ignorados=0,
    )
    dados.update(over)
    return Execucao.objects.create(**dados)


class ConsolidarStatusExecucaoTests(TestCase):
    def test_parcial_sem_erros_nem_pendentes_vira_sucesso(self):
        ex = _execucao()

        self.assertTrue(consolidar_status_execucao(ex))

        ex.refresh_from_db()
        self.assertEqual(ex.status, StatusExecucao.SUCESSO)
        marcador = LogItem.objects.get(execucao=ex, mensagem__icontains="Status consolidado")
        self.assertEqual(marcador.detalhe["status_anterior"], StatusExecucao.PARCIAL)
        self.assertEqual(marcador.detalhe["status"], StatusExecucao.SUCESSO)

    def test_com_erros_pendentes_continua_parcial_sem_logitem(self):
        ex = _execucao(total_erros=3)

        self.assertFalse(consolidar_status_execucao(ex))

        ex.refresh_from_db()
        self.assertEqual(ex.status, StatusExecucao.PARCIAL)
        self.assertFalse(
            LogItem.objects.filter(execucao=ex, mensagem__icontains="Status consolidado").exists()
        )

    def test_com_ignorados_continua_parcial(self):
        ex = _execucao(total_ignorados=5)
        self.assertFalse(consolidar_status_execucao(ex))
        ex.refresh_from_db()
        self.assertEqual(ex.status, StatusExecucao.PARCIAL)

    def test_falha_de_imagem_impede_reclassificacao_incorreta(self):
        ex = _execucao()
        variacao = Variacao.objects.create(
            produto=Produto.objects.create(
                instancia=ex.instancia, fornecedor="asia", codigo_pai="pai-img", nome="Imagem"
            ),
            sku="IMG-1", nome="Imagem", preco="10.00", estoque=1,
        )
        LogItem.objects.create(
            execucao=ex, variacao=variacao, evento=EventoLog.IMAGENS_ERRO, nivel="erro",
            mensagem="Falha no anexo", detalhe={"erro": "anexo recusado"},
        )

        self.assertFalse(consolidar_status_execucao(ex))
        ex.refresh_from_db()
        self.assertEqual(ex.status, StatusExecucao.PARCIAL)

    def test_falha_de_imagem_resolvida_pode_ser_consolidada(self):
        ex = _execucao()
        variacao = Variacao.objects.create(
            produto=Produto.objects.create(
                instancia=ex.instancia, fornecedor="asia", codigo_pai="pai-img-ok", nome="Imagem OK"
            ),
            sku="IMG-OK", nome="Imagem OK", preco="10.00", estoque=1,
        )
        LogItem.objects.create(
            execucao=ex, variacao=variacao, evento=EventoLog.IMAGENS_ERRO, nivel="erro",
            mensagem="Falha no anexo", detalhe={"erro": "temporário"},
        )
        LogItem.objects.create(
            execucao=ex, variacao=variacao, evento=EventoLog.IMAGENS, nivel="info",
            mensagem="Imagens sincronizadas", detalhe={},
        )

        self.assertTrue(consolidar_status_execucao(ex))
        ex.refresh_from_db()
        self.assertEqual(ex.status, StatusExecucao.SUCESSO)

    def test_ja_sucesso_nao_faz_nada(self):
        ex = _execucao(status=StatusExecucao.SUCESSO)
        self.assertFalse(consolidar_status_execucao(ex))

    def test_execucao_em_andamento_nao_e_consolidada(self):
        ex = _execucao(status=StatusExecucao.RODANDO, finalizada_em=None)
        self.assertFalse(consolidar_status_execucao(ex))
        ex.refresh_from_db()
        self.assertEqual(ex.status, StatusExecucao.RODANDO)

    def test_execucao_pausada_nao_e_consolidada(self):
        ex = _execucao(status=StatusExecucao.PAUSADO, finalizada_em=None)
        self.assertFalse(consolidar_status_execucao(ex))

    def test_falha_nao_e_reclassificada_como_sucesso(self):
        ex = _execucao(status=StatusExecucao.FALHA, mensagem_erro="boom")
        self.assertFalse(consolidar_status_execucao(ex))
        ex.refresh_from_db()
        self.assertEqual(ex.status, StatusExecucao.FALHA)

    def test_importacao_de_espelho_nao_e_afetada(self):
        ex = _execucao(tipo=TipoExecucao.INCREMENTAL, status=StatusExecucao.PARCIAL)
        self.assertFalse(consolidar_status_execucao(ex))
        ex.refresh_from_db()
        self.assertEqual(ex.status, StatusExecucao.PARCIAL)
