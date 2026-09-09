import uuid
from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone

from apps.instancias.models import CredencialFornecedor, Instancia
from apps.sincronizacao.models import (
    EventoLog,
    Execucao,
    LogItem,
    NivelLog,
    StatusExecucao,
    TipoExecucao,
)

from ..models import Produto, StatusVariacao, Variacao
from ..tasks import (
    _ControladorLease,
    _persistir_contadores,
    cadastrar_produtos_tiny_task,
    reconciliar_execucoes_travadas,
)


def _instancia():
    return Instancia.objects.create(
        nome="Loja Task",
        access_token="token",
        tiny_origem_padrao=0,
        tiny_unidade_medida_padrao="UN",
    )


def _variacao(instancia, sku, *, fornecedor="xbz", **kwargs):
    produto = Produto.objects.create(
        instancia=instancia, fornecedor=fornecedor, codigo_pai=f"pai-{sku}", nome=f"P {sku}"
    )
    dados = {"produto": produto, "sku": sku, "nome": f"V {sku}", "preco": Decimal("10.00"), "estoque": 5,
             "payload_bruto": {"CodigoComposto": sku}, "atributos": {"codigo_composto": sku}}
    dados.update(kwargs)
    variacao = Variacao.objects.create(**dados)
    CredencialFornecedor.objects.update_or_create(
        instancia=instancia, fornecedor=fornecedor, defaults={"tiny_fornecedor_id": 700_000_000}
    )
    return variacao


def _execucao(instancia, fornecedor="xbz", **kwargs):
    dados = {
        "instancia": instancia,
        "fornecedor": fornecedor,
        "tipo": TipoExecucao.CADASTRO_TINY,
        "lease_token": uuid.uuid4().hex,
        "heartbeat_em": timezone.now(),
    }
    dados.update(kwargs)
    return Execucao.objects.create(**dados)


class CadastrarProdutosTinyTaskTests(TestCase):
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_task_processa_a_fila_e_fecha_a_execucao(self, _mb, mock_criar):
        inst = _instancia()
        v1 = _variacao(inst, "T-1")
        v2 = _variacao(inst, "T-2")
        mock_criar.side_effect = [{"id": 1, "sku": "T-1"}, {"id": 2, "sku": "T-2"}]
        execucao = _execucao(inst)

        cadastrar_produtos_tiny_task(execucao.id)

        execucao.refresh_from_db()
        self.assertEqual(execucao.status, StatusExecucao.SUCESSO)
        self.assertIsNotNone(execucao.finalizada_em)
        self.assertEqual(execucao.total_lidos, 2)
        self.assertEqual(execucao.total_novos, 2)
        self.assertEqual(execucao.total_cadastrados, 2)
        self.assertEqual(execucao.total_erros, 0)
        v1.refresh_from_db()
        v2.refresh_from_db()
        self.assertEqual(v1.status, StatusVariacao.CADASTRADO)
        self.assertEqual(v2.status, StatusVariacao.CADASTRADO)

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_erro_individual_vira_logitem_e_execucao_parcial(self, _mb, mock_criar):
        inst = _instancia()
        _variacao(inst, "OK")
        ruim = _variacao(inst, "RUIM")

        def efeito(payload):
            if payload["sku"] == "RUIM":
                raise RuntimeError("recusado pelo Tiny")
            return {"id": 9, "sku": payload["sku"]}

        mock_criar.side_effect = efeito
        execucao = _execucao(inst)

        cadastrar_produtos_tiny_task(execucao.id)

        execucao.refresh_from_db()
        self.assertEqual(execucao.status, StatusExecucao.PARCIAL)
        self.assertEqual(execucao.total_novos, 1)
        self.assertEqual(execucao.total_erros, 1)
        ruim.refresh_from_db()
        self.assertEqual(ruim.status, StatusVariacao.ERRO)
        logs_erro = LogItem.objects.filter(execucao=execucao, nivel=NivelLog.ERRO)
        self.assertEqual(logs_erro.count(), 1)
        self.assertEqual(logs_erro.first().variacao_id, ruim.id)

    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_crash_inesperado_marca_execucao_como_falha(self, mock_buscar):
        inst = _instancia()
        _variacao(inst, "X")
        mock_buscar.side_effect = None
        execucao = _execucao(inst)

        with patch(
            "apps.catalogo.tasks.executar_sincronizacao_tiny", side_effect=RuntimeError("boom")
        ):
            cadastrar_produtos_tiny_task(execucao.id)

        execucao.refresh_from_db()
        self.assertEqual(execucao.status, StatusExecucao.FALHA)
        self.assertIn("boom", execucao.mensagem_erro)
        self.assertIsNotNone(execucao.finalizada_em)

    @patch("apps.instancias.tiny_client.TinyApiClient.sincronizar_anexos_produto", return_value={})
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto", return_value=[])
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_imagens_sao_sincronizadas_e_registradas_em_log(self, _mb, mock_criar, _mg, mock_put):
        inst = _instancia()
        _variacao(inst, "IMG-1", fornecedor="asia", imagens=["https://cdn/a.jpg"])
        mock_criar.return_value = {"id": 42, "sku": "IMG-1"}
        execucao = _execucao(inst, fornecedor="asia")

        cadastrar_produtos_tiny_task(execucao.id)

        mock_put.assert_called_once()
        execucao.refresh_from_db()
        self.assertEqual(execucao.status, StatusExecucao.SUCESSO)
        self.assertTrue(
            LogItem.objects.filter(execucao=execucao, mensagem__icontains="Imagens do SKU").exists()
        )

    @patch(
        "apps.instancias.tiny_client.TinyApiClient.sincronizar_anexos_produto",
        side_effect=RuntimeError("anexo recusado pelo Tiny"),
    )
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto", return_value=[])
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_erro_de_imagem_deixa_execucao_parcial_e_loga_estruturado(
        self, _mb, mock_criar, _mg, _mput
    ):
        inst = _instancia()
        v = _variacao(inst, "IE-1", fornecedor="asia", imagens=["https://cdn/x.jpg"])
        mock_criar.return_value = {"id": 7, "sku": "IE-1"}
        execucao = _execucao(inst, fornecedor="asia")

        cadastrar_produtos_tiny_task(execucao.id)

        execucao.refresh_from_db()
        v.refresh_from_db()
        self.assertEqual(v.status, StatusVariacao.CADASTRADO)      # produto criado
        self.assertEqual(v.tiny_id, "7")
        self.assertEqual(v.imagens_tiny_sincronizadas, [])         # imagem NÃO marcada
        self.assertEqual(execucao.status, StatusExecucao.PARCIAL)  # rodada não ficou 100%
        self.assertTrue(
            LogItem.objects.filter(
                execucao=execucao, evento=EventoLog.IMAGENS_ERRO, variacao=v
            ).exists()
        )

        # retomada: sem recriar o produto, só a imagem volta à fila
        Execucao.objects.filter(pk=execucao.id).update(
            status=StatusExecucao.RODANDO, heartbeat_em=timezone.now()
        )
        with patch(
            "apps.instancias.tiny_client.TinyApiClient.sincronizar_anexos_produto", return_value={}
        ):
            cadastrar_produtos_tiny_task(execucao.id, execucao.lease_token)

        v.refresh_from_db()
        self.assertEqual(mock_criar.call_count, 1)                 # produto não recriado
        self.assertEqual(v.imagens_tiny_sincronizadas, ["https://cdn/x.jpg"])


class HeartbeatELeaseTests(TestCase):
    def test_controlador_atualiza_heartbeat_e_devolve_none(self):
        inst = _instancia()
        ex = _execucao(inst, heartbeat_em=timezone.now() - timedelta(minutes=5))
        antes = ex.heartbeat_em

        motivo = _ControladorLease(ex.id, ex.lease_token).checar()

        ex.refresh_from_db()
        self.assertIsNone(motivo)
        self.assertGreater(ex.heartbeat_em, antes)

    def test_controlador_detecta_pausa_solicitada(self):
        inst = _instancia()
        ex = _execucao(inst)
        Execucao.objects.filter(pk=ex.id).update(pausa_solicitada=True)
        self.assertEqual(_ControladorLease(ex.id, ex.lease_token).checar(), "pausa")

    def test_controlador_detecta_lease_perdida(self):
        inst = _instancia()
        ex = _execucao(inst)
        self.assertEqual(_ControladorLease(ex.id, "token-de-outra-retomada").checar(), "lease_perdida")

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_heartbeat_avanca_durante_o_processamento(self, _mb, mock_criar):
        inst = _instancia()
        _variacao(inst, "H-1")
        _variacao(inst, "H-2")
        mock_criar.side_effect = [{"id": 1, "sku": "H-1"}, {"id": 2, "sku": "H-2"}]
        antigo = timezone.now() - timedelta(minutes=8)
        execucao = _execucao(inst, heartbeat_em=antigo)

        cadastrar_produtos_tiny_task(execucao.id, execucao.lease_token)

        execucao.refresh_from_db()
        self.assertGreater(execucao.heartbeat_em, antigo)

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_pausa_no_meio_termina_produto_atual_e_para_no_proximo(self, _mb, mock_criar):
        inst = _instancia()
        a = _variacao(inst, "P-A")
        b = _variacao(inst, "P-B")
        c = _variacao(inst, "P-C")
        execucao = _execucao(inst)

        def cria_e_pede_pausa(payload):
            # simula o endpoint de pausa disparando DURANTE o 1º produto
            Execucao.objects.filter(pk=execucao.id).update(
                pausa_solicitada=True, status=StatusExecucao.PAUSANDO
            )
            return {"id": 1, "sku": payload["sku"]}

        mock_criar.side_effect = cria_e_pede_pausa

        cadastrar_produtos_tiny_task(execucao.id, execucao.lease_token)

        execucao.refresh_from_db()
        a.refresh_from_db(); b.refresh_from_db(); c.refresh_from_db()
        self.assertEqual(mock_criar.call_count, 1)          # só o produto atual
        self.assertEqual(a.status, StatusVariacao.CADASTRADO)
        self.assertEqual(b.status, StatusVariacao.PENDENTE)  # próximo nem começou
        self.assertEqual(c.status, StatusVariacao.PENDENTE)
        self.assertEqual(execucao.status, StatusExecucao.PAUSADO)
        self.assertFalse(execucao.pausa_solicitada)
        self.assertIsNone(execucao.finalizada_em)            # pausado não é finalizado
        self.assertEqual(execucao.total_cadastrados, 1)
        self.assertEqual(execucao.total_ignorados, 2)        # ainda pendentes

    @patch("apps.instancias.tiny_client.TinyApiClient.sincronizar_anexos_produto", return_value={})
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto", return_value=[])
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_retomada_da_mesma_execucao_nao_duplica_nem_reenvia_imagem(self, _mb, mock_criar, _mg, mock_put):
        inst = _instancia()
        a = _variacao(inst, "R-A", fornecedor="asia", imagens=["https://cdn/ra.jpg"])
        b = _variacao(inst, "R-B", fornecedor="asia")
        execucao = _execucao(inst, fornecedor="asia")

        contador = {"n": 0}

        def cria(payload):
            contador["n"] += 1
            if contador["n"] == 1:
                Execucao.objects.filter(pk=execucao.id).update(
                    pausa_solicitada=True, status=StatusExecucao.PAUSANDO
                )
            return {"id": contador["n"], "sku": payload["sku"]}

        mock_criar.side_effect = cria

        # rodada 1: pausa após A
        cadastrar_produtos_tiny_task(execucao.id, execucao.lease_token)
        execucao.refresh_from_db()
        self.assertEqual(execucao.status, StatusExecucao.PAUSADO)
        a.refresh_from_db()
        self.assertEqual(a.status, StatusVariacao.CADASTRADO)

        # retomada: MESMA Execucao, token novo, volta a rodar
        novo_token = uuid.uuid4().hex
        Execucao.objects.filter(pk=execucao.id).update(
            status=StatusExecucao.RODANDO, lease_token=novo_token, pausa_solicitada=False,
            heartbeat_em=timezone.now(),
        )
        cadastrar_produtos_tiny_task(execucao.id, novo_token)

        execucao.refresh_from_db()
        b.refresh_from_db()
        self.assertEqual(mock_criar.call_count, 2)      # A não recriado
        self.assertEqual(b.status, StatusVariacao.CADASTRADO)
        self.assertEqual(mock_put.call_count, 1)        # imagem de A enviada só 1x
        self.assertIn(execucao.status, (StatusExecucao.SUCESSO, StatusExecucao.PARCIAL))

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_task_com_lease_diferente_aborta_sem_tocar_no_estado(self, _mb, mock_criar):
        inst = _instancia()
        _variacao(inst, "L-1")
        execucao = _execucao(inst)

        cadastrar_produtos_tiny_task(execucao.id, "lease-que-nao-e-o-atual")

        execucao.refresh_from_db()
        mock_criar.assert_not_called()
        self.assertEqual(execucao.status, StatusExecucao.RODANDO)  # intacto

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_lease_revogado_no_meio_faz_a_task_parar_sem_fechar(self, _mb, mock_criar):
        inst = _instancia()
        _variacao(inst, "Z-A")
        _variacao(inst, "Z-B")
        execucao = _execucao(inst)
        meu_token = execucao.lease_token

        def cria(payload):
            # uma retomada concorrente troca o lease durante o 1º produto
            Execucao.objects.filter(pk=execucao.id).update(lease_token="token-do-novo-dono")
            return {"id": 1, "sku": payload["sku"]}

        mock_criar.side_effect = cria

        cadastrar_produtos_tiny_task(execucao.id, meu_token)

        execucao.refresh_from_db()
        self.assertEqual(mock_criar.call_count, 1)                 # parou antes do 2º
        self.assertEqual(execucao.lease_token, "token-do-novo-dono")
        # a task que perdeu o lease NÃO fecha a execução
        self.assertEqual(execucao.status, StatusExecucao.RODANDO)


class ProgressoIncrementalTests(TestCase):
    @patch.object(_ControladorLease, "PROGRESSO_A_CADA_PRODUTOS", 1)
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_progresso_aumenta_durante_a_execucao(self, _mb, mock_criar):
        inst = _instancia()
        _variacao(inst, "PG-1")
        _variacao(inst, "PG-2")
        _variacao(inst, "PG-3")
        execucao = _execucao(inst)

        vistos = []

        def cria(payload):
            # snapshot do que a UI veria neste instante (o controlador já
            # persistiu o progresso ANTES deste produto)
            e = Execucao.objects.get(pk=execucao.id)
            vistos.append((e.total_cadastrados, e.total_ignorados, e.total_lidos))
            return {"id": len(vistos), "sku": payload["sku"]}

        mock_criar.side_effect = cria

        cadastrar_produtos_tiny_task(execucao.id, execucao.lease_token)

        # antes de cada produto: 0 feitos/3 restantes -> 1/2 -> 2/1
        self.assertEqual([v[0] for v in vistos], [0, 1, 2])   # cadastrados
        self.assertEqual([v[1] for v in vistos], [3, 2, 1])   # a fazer (pendentes)
        self.assertTrue(all(v[2] == 3 for v in vistos))       # universo estável
        execucao.refresh_from_db()
        self.assertEqual(execucao.total_cadastrados, 3)       # definitivo reconciliado

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_progresso_imediato_no_baseline_ao_retomar(self, _mb, mock_criar):
        inst = _instancia()
        # 2 já cadastradas antes, 1 pendente
        _variacao(inst, "B-1", status=StatusVariacao.CADASTRADO, tiny_id="1")
        _variacao(inst, "B-2", status=StatusVariacao.CADASTRADO, tiny_id="2")
        pend = _variacao(inst, "B-3")
        execucao = _execucao(inst, total_cadastrados=0)  # contador "zerado" como no bug

        baseline = {}

        def cria(payload):
            baseline["cadastrados"] = Execucao.objects.get(pk=execucao.id).total_cadastrados
            return {"id": 3, "sku": payload["sku"]}

        mock_criar.side_effect = cria
        cadastrar_produtos_tiny_task(execucao.id, execucao.lease_token)

        # já no 1º produto a Execucao mostra as 2 que existiam (baseline persistido no claim)
        self.assertEqual(baseline["cadastrados"], 2)
        execucao.refresh_from_db()
        self.assertEqual(execucao.total_cadastrados, 3)
        pend.refresh_from_db()
        self.assertEqual(pend.status, StatusVariacao.CADASTRADO)

    def test_persistir_contadores_recomputa_da_verdade_do_banco(self):
        inst = _instancia()
        _variacao(inst, "C-1", status=StatusVariacao.CADASTRADO, tiny_id="1")
        _variacao(inst, "C-2", status=StatusVariacao.ERRO)
        _variacao(inst, "C-3")  # pendente
        ex = _execucao(inst)

        n = _persistir_contadores(ex.id, ex.lease_token)

        ex.refresh_from_db()
        self.assertEqual(n, 1)
        self.assertEqual(ex.total_cadastrados, 1)
        self.assertEqual(ex.total_erros, 1)
        self.assertEqual(ex.total_ignorados, 1)
        self.assertEqual(ex.total_lidos, 3)

    def test_persistir_contadores_com_token_errado_nao_toca_na_execucao(self):
        inst = _instancia()
        _variacao(inst, "T-1", status=StatusVariacao.CADASTRADO, tiny_id="1")
        ex = _execucao(inst, total_cadastrados=99, heartbeat_em=timezone.now() - timedelta(minutes=3))
        hb_antes = ex.heartbeat_em

        n = _persistir_contadores(ex.id, "token-de-outra-retomada")

        ex.refresh_from_db()
        self.assertEqual(n, 0)
        self.assertEqual(ex.total_cadastrados, 99)  # intacto — lease protege
        self.assertEqual(ex.heartbeat_em, hb_antes)

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_progresso_nao_atrapalha_heartbeat_nem_lease(self, _mb, mock_criar):
        inst = _instancia()
        _variacao(inst, "HL-1")
        _variacao(inst, "HL-2")
        mock_criar.side_effect = [{"id": 1, "sku": "HL-1"}, {"id": 2, "sku": "HL-2"}]
        antigo = timezone.now() - timedelta(minutes=9)
        execucao = _execucao(inst, heartbeat_em=antigo)
        token = execucao.lease_token

        cadastrar_produtos_tiny_task(execucao.id, token)

        execucao.refresh_from_db()
        self.assertGreater(execucao.heartbeat_em, antigo)   # heartbeat avançou (junto com o progresso)
        self.assertEqual(execucao.lease_token, token)       # lease inalterado
        self.assertEqual(execucao.status, StatusExecucao.SUCESSO)


class ReconciliarExecucoesTravadasTests(TestCase):
    def _stale(self, inst, **kw):
        dados = {
            "instancia": inst, "fornecedor": "xbz", "tipo": TipoExecucao.CADASTRO_TINY,
            "status": StatusExecucao.RODANDO, "lease_token": uuid.uuid4().hex,
            "heartbeat_em": timezone.now() - timedelta(minutes=20),
        }
        dados.update(kw)
        return Execucao.objects.create(**dados)

    def test_rodando_sem_heartbeat_vira_interrompido(self):
        inst = _instancia()
        ex = self._stale(inst)
        n = reconciliar_execucoes_travadas()
        ex.refresh_from_db()
        self.assertEqual(n, 1)
        self.assertEqual(ex.status, StatusExecucao.INTERROMPIDO)
        self.assertTrue(LogItem.objects.filter(execucao=ex, mensagem__icontains="interrompida").exists())

    def test_pausando_travado_tambem_vira_interrompido(self):
        inst = _instancia()
        ex = self._stale(inst, status=StatusExecucao.PAUSANDO)
        reconciliar_execucoes_travadas()
        ex.refresh_from_db()
        self.assertEqual(ex.status, StatusExecucao.INTERROMPIDO)

    def test_rodando_com_heartbeat_fresco_e_intocado(self):
        inst = _instancia()
        ex = self._stale(inst, heartbeat_em=timezone.now())
        reconciliar_execucoes_travadas()
        ex.refresh_from_db()
        self.assertEqual(ex.status, StatusExecucao.RODANDO)

    def test_nao_mexe_em_importacao_de_espelho_travada(self):
        inst = _instancia()
        ex = self._stale(inst, tipo=TipoExecucao.INCREMENTAL)
        reconciliar_execucoes_travadas()
        ex.refresh_from_db()
        self.assertEqual(ex.status, StatusExecucao.RODANDO)

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_recuperacao_apos_worker_morto_pela_retomada(self, _mb, mock_criar):
        """Worker morre -> reaper marca interrompido -> retomada (mesmo id) conclui."""
        inst = _instancia()
        v = _variacao(inst, "REC-1")
        mock_criar.return_value = {"id": 9, "sku": "REC-1"}
        ex = self._stale(inst)

        reconciliar_execucoes_travadas()
        ex.refresh_from_db()
        self.assertEqual(ex.status, StatusExecucao.INTERROMPIDO)

        # retomada da MESMA Execucao
        novo_token = uuid.uuid4().hex
        Execucao.objects.filter(pk=ex.id).update(
            status=StatusExecucao.RODANDO, lease_token=novo_token, heartbeat_em=timezone.now()
        )
        cadastrar_produtos_tiny_task(ex.id, novo_token)

        ex.refresh_from_db()
        v.refresh_from_db()
        self.assertEqual(v.status, StatusVariacao.CADASTRADO)
        self.assertEqual(ex.status, StatusExecucao.SUCESSO)
        self.assertEqual(Execucao.objects.filter(instancia=inst, fornecedor="xbz").count(), 1)  # não criou nova
