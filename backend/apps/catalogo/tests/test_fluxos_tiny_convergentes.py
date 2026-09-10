"""Regressões de integração: serviços reais, somente a rede Tiny é simulada."""

from io import StringIO
from unittest.mock import MagicMock, patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.instancias.models import CredencialFornecedor, Instancia
from apps.instancias.tests.test_views import _client_autenticado
from apps.sincronizacao.models import EventoLog, Execucao, LogItem, RetentativaLote

from .. import tiny_sync
from ..models import Produto, StatusVariacao, Variacao
from ..tasks import retentar_lote_task


class FluxosTinyConvergentesTests(TestCase):
    def setUp(self):
        self.client = _client_autenticado()
        self.instancia = Instancia.objects.create(
            nome="Regressão Tiny", access_token="token-de-teste",
            tiny_origem_padrao=0, tiny_unidade_medida_padrao="UN",
        )
        CredencialFornecedor.objects.create(
            instancia=self.instancia, fornecedor="xbz", tiny_fornecedor_id=700,
        )
        produto = Produto.objects.create(
            instancia=self.instancia, fornecedor="xbz", codigo_pai="18700",
            nome="CANECA TÉRMICA 500ML", descricao="Descrição completa da caneca",
        )
        self.v = Variacao.objects.create(
            produto=produto, sku="X134074", nome=produto.nome, preco="19.90", estoque=8,
            atributos={"codigo_composto": "18700-DOU"},
            payload_bruto={"CodigoComposto": "18700-DOU"}, ncm="12345678",
        )
        self.execucao = Execucao.objects.create(
            instancia=self.instancia, fornecedor="xbz", tipo="cadastro_tiny", status="parcial",
            finalizada_em=timezone.now(), total_lidos=8949, total_cadastrados=3975, total_erros=4974,
        )
        self.log = LogItem.objects.create(
            execucao=self.execucao, variacao=self.v, evento=EventoLog.ERRO,
            nivel="erro", mensagem="Tiny retornou 401: ", detalhe={"erro": "Tiny retornou 401: "},
        )
        self.tiny = MagicMock()
        self.tiny.buscar_produto_por_sku.return_value = None
        self.tiny.criar_produto.return_value = {"id": 924385783}
        self.tiny.obter_produto.return_value = {
            "id": 924385783, "sku": "X134074", "fornecedores": [], "ncm": "12345678",
        }
        for alvo in ("apps.catalogo.tiny_sync.TinyApiClient", "apps.catalogo.tasks.TinyApiClient",
                     "apps.catalogo.management.commands.cadastrar_produtos_tiny.TinyApiClient"):
            p = patch(alvo, return_value=self.tiny)
            p.start()
            self.addCleanup(p.stop)
        # Sem imagens na fixture: usa a implementação real que retorna sem rede.
        self._erro()

    def _erro(self, tiny_id=None):
        Variacao.objects.filter(pk=self.v.pk).update(
            status=StatusVariacao.ERRO, tiny_id=tiny_id, ultimo_erro="Tiny retornou 401: ",
        )
        self.v.refresh_from_db()

    def _url(self, sufixo=""):
        return f"/api/instancias/{self.instancia.slug}/execucoes/{self.execucao.id}/{sufixo}"

    def _enviar(self, fluxo):
        if fluxo == "atualizar":
            return self.client.post(
                f"/api/instancias/{self.instancia.slug}/produtos/{self.v.id}/atualizar-tiny/"
            )
        if fluxo == "retry":
            return self.client.post(self._url(f"produtos/{self.v.id}/retentar/"))
        if fluxo == "lote":
            lote = RetentativaLote.objects.create(
                execucao=self.execucao, variacao_ids=[self.v.id], total=1,
                lease_token="lease-teste", heartbeat_em=timezone.now(),
            )
            retentar_lote_task(lote.id, "lease-teste")
            lote.refresh_from_db()
            self.assertEqual(lote.processados, 1)
            return lote
        if fluxo == "massa":
            return tiny_sync.executar_sincronizacao_tiny(self.instancia, "xbz", cliente=self.tiny)
        call_command("cadastrar_produtos_tiny", self.instancia.slug, "--skus", self.v.sku,
                     stdout=StringIO(), stderr=StringIO())

    def _matriz(self, fluxo):
        for cenario in ("nenhum", "legado", "composto", "ambos", "tiny_id"):
            with self.subTest(fluxo=fluxo, cenario=cenario):
                self._erro("924385783" if cenario == "tiny_id" else None)
                self.tiny.reset_mock()
                encontrados = {}
                if cenario in ("legado", "ambos"):
                    encontrados["X134074"] = {"id": 924385783, "sku": "X134074"}
                if cenario in ("composto", "ambos"):
                    encontrados["18700-DOU"] = {"id": 111 if cenario == "ambos" else 924385783, "sku": "18700-DOU"}
                self.tiny.buscar_produto_por_sku.side_effect = encontrados.get
                alvo_central = (
                    "apps.catalogo.management.commands.cadastrar_produtos_tiny._processar_variacao"
                    if fluxo == "command" else "apps.catalogo.tiny_sync._processar_variacao"
                )
                with patch(alvo_central, wraps=tiny_sync._processar_variacao) as central:
                    resposta = self._enviar(fluxo)
                    central.assert_called_once()
                self.v.refresh_from_db()
                self.assertEqual(self.v.sku, "X134074")
                if cenario == "ambos":
                    self.tiny.criar_produto.assert_not_called()
                    self.tiny.atualizar_produto.assert_not_called()
                    self.tiny.atualizar_estoque.assert_not_called()
                    self.assertIsNone(self.v.tiny_id)
                    self.assertEqual(self.v.status, StatusVariacao.ERRO)
                    if fluxo in ("atualizar", "retry"):
                        self.assertIn(resposta.status_code, (409, 422))
                        self.assertIn("conflito XBZ", resposta.data["detail"])
                    continue
                self.assertEqual(self.v.tiny_id, "924385783")
                self.assertEqual(self.v.status, StatusVariacao.CADASTRADO)
                if cenario == "nenhum":
                    self.tiny.criar_produto.assert_called_once()
                    payload = self.tiny.criar_produto.call_args.args[0]
                else:
                    self.tiny.criar_produto.assert_not_called()
                    self.tiny.atualizar_produto.assert_called_once()
                    self.assertEqual(self.tiny.atualizar_produto.call_args.args[0], 924385783)
                    payload = self.tiny.atualizar_produto.call_args.args[1]
                if cenario == "tiny_id":
                    self.tiny.buscar_produto_por_sku.assert_not_called()
                self.assertEqual(payload["sku"], "18700-DOU")
                self.assertEqual(payload["fornecedores"][0]["codigoProdutoNoFornecedor"], "18700-DOU")
                self.assertEqual(payload["precos"], {"preco": 0, "precoPromocional": 0, "precoCusto": 19.9})
                self.assertEqual(payload["descricaoComplementar"], "Descrição completa da caneca")
                self.assertEqual(payload["ncm"], "12345678")
                if fluxo in ("atualizar", "retry"):
                    self.assertEqual(resposta.status_code, 200, resposta.data)

    def test_atualizar_tiny_converge_para_protecao_central(self):
        self._matriz("atualizar")

    def test_retry_individual_converge_para_protecao_central(self):
        self._matriz("retry")

    def test_retry_lote_converge_para_protecao_central(self):
        self._matriz("lote")

    def test_massa_converge_para_protecao_central(self):
        self._matriz("massa")

    def test_command_converge_para_protecao_central(self):
        self._matriz("command")

    def test_sucesso_posterior_concilia_execucao_sem_reescrever_historico(self):
        original = LogItem.objects.filter(pk=self.log.pk).values().get()
        # Outro cadastro do mesmo fornecedor NÃO pertence a esta execução.
        Variacao.objects.create(produto=self.v.produto, sku="OUTRA", nome="Outra", preco=1, estoque=1,
                                status="cadastrado", tiny_id="999")
        self.assertEqual(self._enviar("atualizar").status_code, 200)
        quantidade_logs = LogItem.objects.count()
        resumo = self.client.get(self._url()).data
        linha = self.client.get(self._url("produtos/")).data["results"][0]
        self.assertEqual((resumo["total_lidos"], resumo["total_cadastrados"], resumo["total_erros"]), (1, 1, 0))
        self.assertEqual(resumo["total_cadastrados"], resumo["auditoria"]["cadastrados_e_vinculados"])
        self.assertEqual(resumo["contadores_registrados"]["total_cadastrados"], 3975)
        self.assertEqual(self.client.get(self._url("produtos/?resultado=erros")).data["count"], 0)
        self.assertEqual(self.client.get(self._url("produtos/?resultado=cadastrados")).data["count"], 1)
        self.assertEqual(self.client.get(self._url("produtos/?busca=18700-DOU")).data["count"], 1)
        self.assertEqual(linha["tiny_id"], "924385783")
        self.assertEqual(linha["resultado"], "vinculado")
        self.assertEqual(linha["resultado_historico"], "erro")
        self.assertEqual(linha["detalhe_historico"], "Tiny retornou 401: ")
        self.assertTrue(linha["reconciliado"])
        self.assertEqual(linha["status_atual"], "cadastrado")
        self.assertEqual(LogItem.objects.filter(pk=self.log.pk).values().get(), original)
        self.assertEqual(LogItem.objects.count(), quantidade_logs)

    def test_falha_put_preserva_id_e_retry_atualiza_sem_criar(self):
        self.tiny.buscar_produto_por_sku.side_effect = lambda sku: {"id": 924385783} if sku == "X134074" else None
        self.tiny.atualizar_produto.side_effect = ValueError("Tiny indisponível")
        resposta = self._enviar("atualizar")
        self.assertEqual(resposta.status_code, 422)
        self.assertIn("Tiny indisponível", resposta.data["detail"])
        self.v.refresh_from_db()
        self.assertEqual((self.v.tiny_id, self.v.status), ("924385783", "erro"))
        self.assertEqual(self.client.get(self._url("produtos/")).data["results"][0]["tiny_id"], "924385783")
        self.tiny.atualizar_produto.side_effect = None
        self.assertEqual(self._enviar("retry").status_code, 200)
        self.tiny.criar_produto.assert_not_called()

    def test_erro_atual_sobre_log_criado_pode_ser_retentado(self):
        self._erro("924385783")
        LogItem.objects.create(execucao=self.execucao, variacao=self.v, evento="criado", mensagem="Histórico OK")
        self.assertEqual(self.client.get(self._url("produtos/?resultado=erros")).data["count"], 1)
        self.assertEqual(self._enviar("retry").status_code, 200)
        self.tiny.criar_produto.assert_not_called()

    def test_xbz_p_arroba_com_id_continua_bloqueado(self):
        self._erro("924385783")
        self.v.produto.codigo_pai = "P@18700"
        self.v.produto.save()
        self.assertEqual(self._enviar("atualizar").status_code, 409)
        self.tiny.atualizar_produto.assert_not_called()
        self.tiny.criar_produto.assert_not_called()

    def test_command_dry_run_reconcilia_sem_escrita(self):
        self.tiny.buscar_produto_por_sku.side_effect = lambda sku: {"id": 924385783} if sku == "X134074" else None
        antes = Variacao.objects.filter(pk=self.v.pk).values().get()
        out = StringIO()
        call_command("cadastrar_produtos_tiny", self.instancia.slug, "--dry-run", "--skus", self.v.sku, stdout=out)
        self.assertIn("SERIA ATUALIZADO", out.getvalue())
        self.assertEqual(Variacao.objects.filter(pk=self.v.pk).values().get(), antes)
        self.tiny.criar_produto.assert_not_called()
        self.tiny.atualizar_produto.assert_not_called()

    def test_demais_fornecedores_preservam_sku_e_nao_adotam_automaticamente(self):
        for fornecedor in ("asia", "somarcas", "spot"):
            with self.subTest(fornecedor=fornecedor):
                CredencialFornecedor.objects.create(instancia=self.instancia, fornecedor=fornecedor, tiny_fornecedor_id=700)
                self.v.produto.fornecedor = fornecedor
                self.v.produto.save()
                self._erro()
                self.tiny.reset_mock()
                self.tiny.buscar_produto_por_sku.side_effect = None
                self.tiny.buscar_produto_por_sku.return_value = {"id": 924385783}
                self.assertEqual(self._enviar("atualizar").status_code, 409)
                self.tiny.buscar_produto_por_sku.assert_called_once_with("X134074")
                self.tiny.atualizar_produto.assert_not_called()
                self.tiny.buscar_produto_por_sku.return_value = None
                self.assertEqual(self._enviar("atualizar").status_code, 200)
                payload = self.tiny.criar_produto.call_args.args[0]
                self.assertEqual(payload["sku"], "X134074")
                self.assertEqual(payload["fornecedores"][0]["codigoProdutoNoFornecedor"], "X134074")
                self.assertEqual(self._enviar("atualizar").status_code, 200)
                payload_put = self.tiny.atualizar_produto.call_args.args[1]
                self.assertEqual(payload_put["sku"], "X134074")
                self.assertEqual(payload_put["fornecedores"][0]["codigoProdutoNoFornecedor"], "X134074")
                self.v.refresh_from_db()
                self.assertEqual(self.v.sku, "X134074")

    @patch("apps.catalogo.management.commands.diagnosticar_xbz_tiny.TinyApiClient")
    def test_diagnostico_local_nao_chama_tiny_nem_escreve(self, cliente):
        antes = Variacao.objects.filter(pk=self.v.pk).values().get()
        logs = list(LogItem.objects.values())
        out = StringIO()
        call_command("diagnosticar_xbz_tiny", "--instancia", self.instancia.slug, "--sku", self.v.sku,
                     "--execucao", str(self.execucao.id), "--somente-local", stdout=out)
        cliente.assert_not_called()
        self.assertIn("histórico=erro", out.getvalue())
        self.assertIn("Contadores conciliados", out.getvalue())
        self.assertEqual(Variacao.objects.filter(pk=self.v.pk).values().get(), antes)
        self.assertEqual(list(LogItem.objects.values()), logs)

    @patch("apps.catalogo.management.commands.diagnosticar_xbz_tiny.TinyApiClient")
    def test_diagnostico_tiny_so_consulta_com_cliente_somente_leitura(self, cliente):
        self._erro("924385783")
        cliente.return_value = self.tiny
        call_command("diagnosticar_xbz_tiny", "--instancia", self.instancia.slug,
                     "--sku", self.v.sku, stdout=StringIO())
        cliente.assert_called_once_with(self.instancia, somente_leitura=True)
        self.tiny.obter_produto.assert_called_once_with(924385783)
        self.tiny.atualizar_produto.assert_not_called()
        self.tiny.criar_produto.assert_not_called()
