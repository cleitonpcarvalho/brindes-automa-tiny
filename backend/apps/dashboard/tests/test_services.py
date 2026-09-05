from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.catalogo.models import Produto, StatusVariacao, Variacao
from apps.instancias.constants import Fornecedor
from apps.instancias.models import Instancia
from apps.sincronizacao.models import Execucao, StatusExecucao, TipoExecucao

from .. import services


def _criar_instancia(**kwargs):
    kwargs.setdefault("nome", "Loja Teste")
    return Instancia.objects.create(**kwargs)


def _criar_execucao(instancia, *, fornecedor=Fornecedor.XBZ, iniciada_em=None, **kwargs):
    execucao = Execucao.objects.create(
        instancia=instancia,
        fornecedor=fornecedor,
        tipo=TipoExecucao.INCREMENTAL,
        **kwargs,
    )
    if iniciada_em is not None:
        Execucao.objects.filter(pk=execucao.pk).update(iniciada_em=iniciada_em)
        execucao.refresh_from_db()
    return execucao


def _criar_variacao(instancia, *, fornecedor=Fornecedor.XBZ, status=StatusVariacao.ERRO, sku="sku-1"):
    produto = Produto.objects.create(
        instancia=instancia, fornecedor=fornecedor, codigo_pai=f"pai-{sku}", nome="Produto"
    )
    return Variacao.objects.create(
        produto=produto, sku=sku, nome="Variação", preco="10.00", estoque=1, status=status
    )


class CalcularResumoTests(TestCase):
    def test_sem_nenhum_dado_nao_quebra_e_devolve_zeros(self):
        resumo = services.calcular_resumo("hoje")
        self.assertEqual(resumo["instancias"], {"ativas": 0, "total": 0})
        self.assertEqual(
            resumo["produtos_sincronizados"],
            {"total": 0, "periodo_anterior": 0, "diferenca": 0},
        )
        self.assertEqual(resumo["execucoes_24h"], {"total": 0, "sucesso": 0})
        self.assertEqual(resumo["alertas"], {"abertos": 0, "requerem_acao": 0})

    def test_instancia_com_zero_execucoes_conta_no_total_sem_afetar_produtos_ou_execucoes(self):
        _criar_instancia(nome="Sem execuções")
        resumo = services.calcular_resumo("hoje")
        self.assertEqual(resumo["instancias"]["total"], 1)
        self.assertEqual(resumo["produtos_sincronizados"]["total"], 0)
        self.assertEqual(resumo["execucoes_24h"]["total"], 0)

    def test_instancias_ativas_conta_so_status_conectado(self):
        _criar_instancia(nome="Conectada", status=Instancia.Status.CONECTADO)
        _criar_instancia(nome="Não conectada", status=Instancia.Status.NAO_CONECTADO)
        resumo = services.calcular_resumo("hoje")
        self.assertEqual(resumo["instancias"], {"ativas": 1, "total": 2})

    def test_produtos_sincronizados_hoje_vs_ontem(self):
        instancia = _criar_instancia()
        agora = timezone.now()
        _criar_execucao(
            instancia,
            iniciada_em=agora,
            status=StatusExecucao.SUCESSO,
            total_novos=10,
            total_atualizados=5,
        )
        _criar_execucao(
            instancia,
            iniciada_em=agora - timedelta(days=1, hours=1),
            status=StatusExecucao.SUCESSO,
            total_novos=3,
            total_atualizados=2,
        )
        resumo = services.calcular_resumo("hoje")
        self.assertEqual(resumo["produtos_sincronizados"]["total"], 15)
        self.assertEqual(resumo["produtos_sincronizados"]["periodo_anterior"], 5)
        self.assertEqual(resumo["produtos_sincronizados"]["diferenca"], 10)

    def test_execucoes_24h_conta_sucesso_separado_do_total(self):
        instancia = _criar_instancia()
        agora = timezone.now()
        _criar_execucao(instancia, iniciada_em=agora, status=StatusExecucao.SUCESSO)
        _criar_execucao(instancia, iniciada_em=agora, status=StatusExecucao.FALHA)
        _criar_execucao(instancia, iniciada_em=agora - timedelta(hours=30), status=StatusExecucao.SUCESSO)
        resumo = services.calcular_resumo("hoje")
        self.assertEqual(resumo["execucoes_24h"], {"total": 2, "sucesso": 1})


class CalcularAlertasTests(TestCase):
    def test_token_expirado_gera_alerta_critico(self):
        instancia = _criar_instancia(
            status=Instancia.Status.ERRO, refresh_expira_em=timezone.now() - timedelta(hours=1)
        )
        alertas = services.calcular_alertas()
        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0]["tipo"], "token_expirado")
        self.assertEqual(alertas[0]["severidade"], "critica")
        self.assertEqual(alertas[0]["instancia"]["slug"], instancia.slug)

    def test_falhas_de_renovacao_nao_duplica_com_token_expirado(self):
        _criar_instancia(
            tentativas_falha=3,
            refresh_expira_em=timezone.now() - timedelta(hours=1),
        )
        alertas = services.calcular_alertas()
        # já é "token expirado" — não deve também aparecer como "falhas_renovacao"
        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0]["tipo"], "token_expirado")

    def test_falhas_de_renovacao_isolado_gera_alerta(self):
        _criar_instancia(tentativas_falha=3)
        alertas = services.calcular_alertas()
        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0]["tipo"], "falhas_renovacao")

    def test_execucao_com_mensagem_de_limite_vira_alerta_de_limite_diario(self):
        instancia = _criar_instancia()
        _criar_execucao(
            instancia,
            status=StatusExecucao.FALHA,
            mensagem_erro="xbz: 403 - limite diário de chamadas atingido.",
        )
        alertas = services.calcular_alertas()
        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0]["tipo"], "limite_diario")
        self.assertEqual(alertas[0]["severidade"], "critica")

    def test_execucao_falha_generica_vira_alerta_de_atencao(self):
        instancia = _criar_instancia()
        _criar_execucao(instancia, status=StatusExecucao.FALHA, mensagem_erro="timeout na API")
        alertas = services.calcular_alertas()
        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0]["tipo"], "execucao_falhou")
        self.assertEqual(alertas[0]["severidade"], "atencao")

    def test_execucao_com_sucesso_nao_gera_alerta(self):
        instancia = _criar_instancia()
        _criar_execucao(instancia, status=StatusExecucao.SUCESSO)
        self.assertEqual(services.calcular_alertas(), [])

    def test_variacoes_com_erro_abaixo_do_limiar_nao_gera_alerta(self):
        instancia = _criar_instancia()
        for indice in range(services.LIMIAR_VARIACOES_COM_ERRO):
            _criar_variacao(instancia, sku=f"sku-{indice}")
        self.assertEqual(services.calcular_alertas(), [])

    def test_variacoes_com_erro_acima_do_limiar_gera_alerta(self):
        instancia = _criar_instancia()
        for indice in range(services.LIMIAR_VARIACOES_COM_ERRO + 1):
            _criar_variacao(instancia, sku=f"sku-{indice}")
        alertas = services.calcular_alertas()
        self.assertEqual(len(alertas), 1)
        self.assertEqual(alertas[0]["tipo"], "variacoes_com_erro")
        self.assertEqual(alertas[0]["fornecedor"], Fornecedor.XBZ)

    def test_alertas_ordenados_do_mais_recente_para_o_mais_antigo(self):
        instancia = _criar_instancia()
        _criar_instancia(nome="Outra", tentativas_falha=3)
        _criar_execucao(
            instancia,
            status=StatusExecucao.FALHA,
            mensagem_erro="erro genérico",
            iniciada_em=timezone.now(),
        )
        alertas = services.calcular_alertas()
        momentos = [alerta["momento"] for alerta in alertas]
        self.assertEqual(momentos, sorted(momentos, reverse=True))


class CalcularAtividadeTests(TestCase):
    def test_sem_execucoes_devolve_lista_vazia(self):
        self.assertEqual(services.calcular_atividade(), [])

    def test_devolve_execucoes_mais_recentes_primeiro_com_duracao(self):
        instancia = _criar_instancia()
        agora = timezone.now()
        antiga = _criar_execucao(instancia, iniciada_em=agora - timedelta(hours=2))
        Execucao.objects.filter(pk=antiga.pk).update(finalizada_em=antiga.iniciada_em + timedelta(seconds=30))
        recente = _criar_execucao(instancia, iniciada_em=agora)

        atividade = services.calcular_atividade()

        self.assertEqual(len(atividade), 2)
        self.assertEqual(atividade[0]["id"], recente.id)
        self.assertEqual(atividade[1]["id"], antiga.id)
        self.assertEqual(atividade[1]["duracao_segundos"], 30.0)
        self.assertIsNone(atividade[0]["duracao_segundos"])

    def test_respeita_limite(self):
        instancia = _criar_instancia()
        for _ in range(5):
            _criar_execucao(instancia)
        self.assertEqual(len(services.calcular_atividade(limit=2)), 2)
