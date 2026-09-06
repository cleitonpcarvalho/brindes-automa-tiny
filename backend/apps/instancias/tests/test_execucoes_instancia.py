from django.contrib.auth import get_user_model
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework import status
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.catalogo.models import Produto, Variacao
from apps.sincronizacao.models import Execucao, LogItem, NivelLog, StatusExecucao, TipoExecucao

from ..constants import Fornecedor
from ..models import Instancia


def _client_autenticado():
    usuario = get_user_model().objects.create_user(email="operador-execucoes@example.com", password="x")
    token = Token.objects.create(user=usuario)
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
    return client


def _execucao(instancia, *, fornecedor=Fornecedor.XBZ, tipo=TipoExecucao.INCREMENTAL,
              status_execucao=StatusExecucao.SUCESSO, finalizada=True, **extra):
    execucao = Execucao.objects.create(
        instancia=instancia, fornecedor=fornecedor, tipo=tipo, status=status_execucao, **extra
    )
    if finalizada:
        execucao.finalizada_em = timezone.now()
        execucao.save(update_fields=["finalizada_em"])
    return execucao


class ExecucoesInstanciaTests(TestCase):
    def setUp(self):
        self.client = _client_autenticado()
        self.instancia = Instancia.objects.create(nome="Loja A")
        self.outra = Instancia.objects.create(nome="Loja B")

    def _url(self, instancia=None):
        return f"/api/instancias/{(instancia or self.instancia).slug}/execucoes/"

    def test_exige_autenticacao(self):
        self.assertEqual(APIClient().get(self._url()).status_code, status.HTTP_401_UNAUTHORIZED)

    def test_slug_inexistente_404(self):
        self.assertEqual(
            self.client.get("/api/instancias/nao-existe/execucoes/").status_code,
            status.HTTP_404_NOT_FOUND,
        )

    def test_isolamento_por_instancia(self):
        _execucao(self.instancia, fornecedor=Fornecedor.XBZ)
        _execucao(self.outra, fornecedor=Fornecedor.SPOT)

        resposta = self.client.get(self._url())
        self.assertEqual(resposta.data["count"], 1)
        self.assertEqual(resposta.data["results"][0]["fornecedor"], Fornecedor.XBZ)

        resposta_outra = self.client.get(self._url(self.outra))
        self.assertEqual([e["fornecedor"] for e in resposta_outra.data["results"]], [Fornecedor.SPOT])

    def test_ordenacao_mais_recente_primeiro(self):
        antiga = _execucao(self.instancia)
        Execucao.objects.filter(pk=antiga.pk).update(
            iniciada_em=timezone.now() - timezone.timedelta(days=2)
        )
        nova = _execucao(self.instancia)

        ids = [e["id"] for e in self.client.get(self._url()).data["results"]]
        self.assertEqual(ids, [nova.id, antiga.id])

    def test_paginacao_no_servidor(self):
        for _ in range(25):
            _execucao(self.instancia)

        pagina1 = self.client.get(self._url(), {"page_size": 10})
        self.assertEqual(pagina1.data["count"], 25)
        self.assertEqual(len(pagina1.data["results"]), 10)
        self.assertIsNotNone(pagina1.data["next"])

        pagina3 = self.client.get(self._url(), {"page_size": 10, "page": 3})
        self.assertEqual(len(pagina3.data["results"]), 5)

    def test_filtro_por_fornecedor(self):
        _execucao(self.instancia, fornecedor=Fornecedor.XBZ)
        _execucao(self.instancia, fornecedor=Fornecedor.SPOT)

        resposta = self.client.get(self._url(), {"fornecedor": Fornecedor.SPOT})
        self.assertEqual([e["fornecedor"] for e in resposta.data["results"]], [Fornecedor.SPOT])

    def test_filtro_por_status(self):
        _execucao(self.instancia, status_execucao=StatusExecucao.SUCESSO)
        _execucao(self.instancia, status_execucao=StatusExecucao.FALHA, finalizada=False)

        resposta = self.client.get(self._url(), {"status": StatusExecucao.FALHA})
        self.assertEqual([e["status"] for e in resposta.data["results"]], [StatusExecucao.FALHA])

    def test_filtro_invalido_e_ignorado(self):
        _execucao(self.instancia)
        resposta = self.client.get(self._url(), {"fornecedor": "xxx", "status": "yyy"})
        self.assertEqual(resposta.data["count"], 1)

    def test_campos_da_resposta(self):
        execucao = _execucao(
            self.instancia,
            fornecedor=Fornecedor.XBZ,
            tipo=TipoExecucao.CARGA_INICIAL,
            status_execucao=StatusExecucao.PARCIAL,
            total_lidos=10,
            total_novos=3,
            total_cadastrados=2,
            total_ignorados=1,
            total_erros=1,
            mensagem_erro="1 item falhou",
        )
        LogItem.objects.create(execucao=execucao, mensagem="linha de log")

        linha = self.client.get(self._url()).data["results"][0]
        self.assertEqual(linha["id"], execucao.id)
        self.assertEqual(linha["tipo"], TipoExecucao.CARGA_INICIAL)
        self.assertEqual(linha["status"], StatusExecucao.PARCIAL)
        self.assertEqual(linha["total_lidos"], 10)
        self.assertEqual(linha["total_cadastrados"], 2)
        self.assertEqual(linha["total_ignorados"], 1)
        self.assertEqual(linha["mensagem_erro"], "1 item falhou")
        self.assertEqual(linha["total_logs"], 1)
        self.assertIsNotNone(linha["iniciada_em"])
        self.assertIsNotNone(linha["finalizada_em"])
        self.assertIsInstance(linha["duracao_segundos"], float)

    def test_duracao_nula_enquanto_rodando(self):
        _execucao(self.instancia, status_execucao=StatusExecucao.RODANDO, finalizada=False)
        linha = self.client.get(self._url()).data["results"][0]
        self.assertIsNone(linha["duracao_segundos"])
        self.assertIsNone(linha["finalizada_em"])

    def test_sem_n_mais_1(self):
        for _ in range(3):
            execucao = _execucao(self.instancia)
            LogItem.objects.create(execucao=execucao, mensagem="log")

        with CaptureQueriesContext(connection) as ctx:
            self.client.get(self._url(), {"page_size": 50})
        consultas_com_3 = len(ctx.captured_queries)

        for _ in range(9):
            execucao = _execucao(self.instancia)
            LogItem.objects.create(execucao=execucao, mensagem="log")

        with CaptureQueriesContext(connection) as ctx:
            self.client.get(self._url(), {"page_size": 50})
        self.assertEqual(consultas_com_3, len(ctx.captured_queries))


class ExecucaoLogsTests(TestCase):
    def setUp(self):
        self.client = _client_autenticado()
        self.instancia = Instancia.objects.create(nome="Loja A")
        self.outra = Instancia.objects.create(nome="Loja B")
        self.execucao = _execucao(self.instancia)
        self.execucao_outra = _execucao(self.outra)

    def _url(self, slug, execucao_id):
        return f"/api/instancias/{slug}/execucoes/{execucao_id}/logs/"

    def test_exige_autenticacao(self):
        resposta = APIClient().get(self._url(self.instancia.slug, self.execucao.id))
        self.assertEqual(resposta.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_lista_logs_em_ordem_cronologica(self):
        LogItem.objects.create(execucao=self.execucao, nivel=NivelLog.INFO, mensagem="primeiro")
        LogItem.objects.create(execucao=self.execucao, nivel=NivelLog.ERRO, mensagem="segundo")

        resposta = self.client.get(self._url(self.instancia.slug, self.execucao.id))
        self.assertEqual(resposta.status_code, status.HTTP_200_OK)
        self.assertEqual([l["mensagem"] for l in resposta.data["results"]], ["primeiro", "segundo"])

    def test_filtro_por_nivel(self):
        LogItem.objects.create(execucao=self.execucao, nivel=NivelLog.INFO, mensagem="info")
        LogItem.objects.create(execucao=self.execucao, nivel=NivelLog.ERRO, mensagem="erro")

        resposta = self.client.get(self._url(self.instancia.slug, self.execucao.id), {"nivel": NivelLog.ERRO})
        self.assertEqual([l["mensagem"] for l in resposta.data["results"]], ["erro"])

    def test_variacao_sku_quando_ligado_e_none_quando_nao(self):
        produto = Produto.objects.create(
            instancia=self.instancia, fornecedor=Fornecedor.XBZ, codigo_pai="p1", nome="P"
        )
        variacao = Variacao.objects.create(
            produto=produto, sku="SKU-1", nome="V", preco="1.00", estoque=1
        )
        LogItem.objects.create(execucao=self.execucao, variacao=variacao, mensagem="com variacao")
        LogItem.objects.create(execucao=self.execucao, mensagem="sem variacao")

        linhas = self.client.get(self._url(self.instancia.slug, self.execucao.id)).data["results"]
        por_msg = {l["mensagem"]: l["variacao_sku"] for l in linhas}
        self.assertEqual(por_msg["com variacao"], "SKU-1")
        self.assertIsNone(por_msg["sem variacao"])

    def test_nao_vaza_logs_de_execucao_de_outra_instancia(self):
        LogItem.objects.create(execucao=self.execucao_outra, mensagem="segredo da loja B")

        # id de execução da outra instância, mas slug da instância A -> 404.
        resposta = self.client.get(self._url(self.instancia.slug, self.execucao_outra.id))
        self.assertEqual(resposta.status_code, status.HTTP_404_NOT_FOUND)

    def test_execucao_inexistente_404(self):
        resposta = self.client.get(self._url(self.instancia.slug, 999999))
        self.assertEqual(resposta.status_code, status.HTTP_404_NOT_FOUND)

    def test_sem_n_mais_1_nos_logs(self):
        produto = Produto.objects.create(
            instancia=self.instancia, fornecedor=Fornecedor.XBZ, codigo_pai="p1", nome="P"
        )

        def _log_com_variacao(i):
            variacao = Variacao.objects.create(
                produto=produto, sku=f"SKU-{i}", nome="V", preco="1.00", estoque=1
            )
            LogItem.objects.create(execucao=self.execucao, variacao=variacao, mensagem=f"log {i}")

        for i in range(3):
            _log_com_variacao(i)
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(self._url(self.instancia.slug, self.execucao.id), {"page_size": 500})
        consultas_com_3 = len(ctx.captured_queries)

        for i in range(3, 12):
            _log_com_variacao(i)
        with CaptureQueriesContext(connection) as ctx:
            self.client.get(self._url(self.instancia.slug, self.execucao.id), {"page_size": 500})
        self.assertEqual(consultas_com_3, len(ctx.captured_queries))
