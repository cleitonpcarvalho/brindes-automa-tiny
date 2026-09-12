import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.catalogo.models import Produto, Variacao
from apps.sincronizacao.models import EventoLog, LogItem, NivelLog
from apps.sincronizacao.models import Execucao, StatusExecucao, TipoExecucao

from ..models import Instancia
from ..serializers import InstanciaDetalheSerializer


def _cadastro_tiny(instancia, fornecedor="xbz"):
    dados = InstanciaDetalheSerializer(instancia).data["fornecedores"]
    return next(f["cadastro_tiny"] for f in dados if f["fornecedor"] == fornecedor)


def _execucao(instancia, **kwargs):
    dados = {
        "instancia": instancia,
        "fornecedor": "xbz",
        "tipo": TipoExecucao.CADASTRO_TINY,
        "lease_token": uuid.uuid4().hex,
        "heartbeat_em": timezone.now(),
    }
    dados.update(kwargs)
    return Execucao.objects.create(**dados)


class EstadoCadastroTinyNoDetalheTests(TestCase):
    def setUp(self):
        self.instancia = Instancia.objects.create(nome="Loja Estado")

    def test_sem_execucao_estado_pronto_so_pode_iniciar(self):
        ct = _cadastro_tiny(self.instancia)
        self.assertEqual(ct["estado"], "pronto")
        self.assertTrue(ct["pode_iniciar"])
        self.assertFalse(ct["pode_pausar"])
        self.assertFalse(ct["pode_retomar"])
        self.assertIsNone(ct["execucao_id"])

    def test_rodando_fresco_estado_sincronizando_so_pode_pausar(self):
        _execucao(self.instancia, status=StatusExecucao.RODANDO, total_lidos=10, total_cadastrados=3)
        ct = _cadastro_tiny(self.instancia)
        self.assertEqual(ct["estado"], "sincronizando")
        self.assertFalse(ct["pode_iniciar"])
        self.assertTrue(ct["pode_pausar"])
        self.assertFalse(ct["pode_retomar"])
        self.assertAlmostEqual(ct["progresso"], 0.3, places=3)

    def test_rodando_com_heartbeat_expirado_aparece_interrompido(self):
        _execucao(
            self.instancia,
            status=StatusExecucao.RODANDO,
            heartbeat_em=timezone.now() - timedelta(minutes=30),
        )
        ct = _cadastro_tiny(self.instancia)
        self.assertEqual(ct["estado"], "interrompido")
        self.assertTrue(ct["pode_retomar"])
        self.assertFalse(ct["pode_pausar"])

    def test_pausado_pode_retomar(self):
        _execucao(self.instancia, status=StatusExecucao.PAUSADO)
        ct = _cadastro_tiny(self.instancia)
        self.assertEqual(ct["estado"], "pausado")
        self.assertTrue(ct["pode_retomar"])
        self.assertFalse(ct["pode_pausar"])
        self.assertFalse(ct["pode_iniciar"])

    def test_pausando_nao_oferece_acao(self):
        _execucao(self.instancia, status=StatusExecucao.PAUSANDO)
        ct = _cadastro_tiny(self.instancia)
        self.assertEqual(ct["estado"], "pausando")
        self.assertFalse(ct["pode_iniciar"])
        self.assertFalse(ct["pode_pausar"])
        self.assertFalse(ct["pode_retomar"])

    def test_sucesso_estado_concluido_pode_iniciar_de_novo(self):
        _execucao(
            self.instancia,
            status=StatusExecucao.SUCESSO,
            finalizada_em=timezone.now(),
            total_lidos=5,
            total_cadastrados=5,
        )
        ct = _cadastro_tiny(self.instancia)
        self.assertEqual(ct["estado"], "concluido")
        self.assertTrue(ct["pode_iniciar"])
        self.assertEqual(ct["progresso"], 1.0)

    def test_parcial_pode_iniciar_de_novo(self):
        _execucao(
            self.instancia,
            status=StatusExecucao.PARCIAL,
            finalizada_em=timezone.now(),
            total_lidos=10,
            total_cadastrados=7,
            total_erros=1,
            total_ignorados=2,
        )
        ct = _cadastro_tiny(self.instancia)
        self.assertEqual(ct["estado"], "parcial")
        self.assertTrue(ct["pode_iniciar"])
        self.assertEqual(ct["total_erros"], 1)

    def test_card_explica_colisao_legada_sem_chamar_de_erro(self):
        execucao = _execucao(
            self.instancia,
            fornecedor="asia",
            status=StatusExecucao.PARCIAL,
            finalizada_em=timezone.now(),
            total_lidos=1,
            total_ignorados=1,
        )
        produto = Produto.objects.create(
            instancia=self.instancia,
            fornecedor="asia",
            codigo_pai="ME550P",
            nome="Mala Esportiva",
        )
        variacao = Variacao.objects.create(
            produto=produto,
            sku="ME550",
            nome="Mala Esportiva",
            preco="86.50",
            estoque=94,
        )
        LogItem.objects.create(
            execucao=execucao,
            variacao=variacao,
            nivel=NivelLog.AVISO,
            evento=EventoLog.BLOQUEADO,
            mensagem="SKU ME550 bloqueado",
            detalhe={"motivo": "SKU já existe no Tiny (id=857279363) e não possui vínculo confirmado"},
        )

        ct = _cadastro_tiny(self.instancia, "asia")
        self.assertEqual(ct["bloqueados"], 1)
        self.assertEqual(ct["falhas_secundarias"], 0)
        self.assertIn("sem erro técnico", ct["motivo_status"])
        self.assertNotIn("com erro(s)", ct["motivo_status"])
