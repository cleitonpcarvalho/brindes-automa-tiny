"""
`propagar_fornecedor_tiny_task` — a ponte automática espelho -> Tiny, disparada
depois de uma importação de espelho quando a cadência do par tem
`propagar_tiny` ligado. Reaproveita, SEM duplicar regra:

  1. produtos novos elegíveis + imagens -> cadastro em massa (com Execucao);
  2. estoque que mudou -> `atualizar_estoque_tiny --fornecedor`;
  3. dados de produtos existentes não são propagados automaticamente;
     `corrigir_dados_produto_tiny` permanece manual.

Cada etapa é guiada por marcador de drift: nada que já esteja em dia é
reescrito.
"""

from decimal import Decimal
from unittest.mock import Mock, patch

from django.test import TestCase
from django.utils import timezone

from apps.instancias.models import CredencialFornecedor, Instancia
from apps.instancias.tiny_client import TinyApiError
from apps.sincronizacao.models import (
    Execucao,
    RetentativaLote,
    StatusExecucao,
    StatusRetentativaLote,
    TipoExecucao,
)

from ..models import Produto, StatusVariacao, Variacao
from ..tasks import AUTOMATIC_CADASTRO_LOTE, propagar_fornecedor_tiny_task

TINY_FORN_ID = 752133514


def _get_tiny(tiny_id, sku):
    return {
        "id": tiny_id, "sku": sku, "descricao": f"T {sku}", "descricaoComplementar": "",
        "situacao": "A", "tipo": "S", "unidade": "UN", "ncm": "4820.20.00", "origem": "0",
        "dimensoes": {}, "precos": {"preco": 0, "precoPromocional": 0, "precoCusto": 0},
        "estoque": {"controlar": True}, "fornecedores": [], "anexos": [],
        "variacoes": [], "kit": [], "producao": None,
    }


class _Base(TestCase):
    def setUp(self):
        self.instancia = Instancia.objects.create(
            nome="Loja", access_token="tok", tiny_origem_padrao=0, tiny_unidade_medida_padrao="UN"
        )
        CredencialFornecedor.objects.update_or_create(
            instancia=self.instancia, fornecedor="asia",
            defaults={"tiny_fornecedor_id": TINY_FORN_ID},
        )

    def _variacao(self, sku, **extra):
        produto = extra.pop("produto", None) or Produto.objects.create(
            instancia=self.instancia, fornecedor="asia", codigo_pai=f"pai-{sku}", nome=f"P {sku}",
            descricao="Descrição rica.",
        )
        dados = {
            "produto": produto, "sku": sku, "nome": f"V {sku}",
            "preco": Decimal("10.00"), "estoque": 5,
        }
        dados.update(extra)
        return Variacao.objects.create(**dados)

    def _cadastrada(self, sku, **extra):
        return self._variacao(
            sku, status=StatusVariacao.CADASTRADO, tiny_id=extra.pop("tiny_id", "900"),
            preco_custo_tiny_sincronizado=extra.pop("preco_custo_tiny_sincronizado", Decimal("10.00")),
            estoque_tiny_sincronizado=extra.pop("estoque_tiny_sincronizado", 5),
            dados_tiny_sincronizados_em=extra.pop("dados_tiny_sincronizados_em", timezone.now()),
            **extra,
        )

    def _rodar(self):
        propagar_fornecedor_tiny_task(self.instancia.id, "asia")


class NovosProdutosTests(_Base):
    @patch("apps.catalogo.tasks._propagar_estoque")
    @patch("apps.catalogo.tasks.cadastrar_produtos_tiny_task")
    @patch("apps.catalogo.tasks.tiny_sync.fila_cadastro_massa")
    def test_cadastro_automatico_limita_a_fila_por_lote(
        self, mock_fila, mock_cadastro, _mock_estoque
    ):
        variacao = self._variacao("LOTE-1")
        mock_fila.return_value = [variacao]

        self._rodar()

        self.assertEqual(mock_fila.call_args.kwargs["limite"], AUTOMATIC_CADASTRO_LOTE)
        self.assertTrue(mock_fila.call_args.kwargs["incluir_imagens_pendentes"])
        mock_cadastro.assert_called_once()

    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_estoque")
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto", return_value={"id": 51, "sku": "NOVO-1"})
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_produto_novo_e_cadastrado_via_execucao_sem_estoque_ou_dados_redundantes(
        self, _mb, _mc, mock_estoque, mock_get, mock_put
    ):
        v = self._variacao("NOVO-1")  # PENDENTE, estoque 5

        self._rodar()

        v.refresh_from_db()
        self.assertEqual(v.status, StatusVariacao.CADASTRADO)
        self.assertEqual(v.tiny_id, "51")
        # rodou dentro de uma Execucao de cadastro Tiny, concluída
        execucao = Execucao.objects.get(tipo=TipoExecucao.CADASTRO_TINY, fornecedor="asia")
        self.assertEqual(execucao.status, StatusExecucao.SUCESSO)
        # o POST /produtos já levou estoque inicial + pacote de dados: nada de
        # Balanço nem PUT redundante logo em seguida
        mock_estoque.assert_not_called()
        mock_put.assert_not_called()

    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_estoque")
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_produto_sem_estoque_nao_e_cadastrado_e_nao_gera_execucao(
        self, _mb, mock_criar, mock_estoque, _mg, _mp
    ):
        self._variacao("SEM-ESTOQUE", estoque=0)  # -> AGUARDANDO no save

        self._rodar()

        mock_criar.assert_not_called()
        mock_estoque.assert_not_called()
        # fila de cadastro vazia -> nenhuma Execucao criada (sem spam)
        self.assertFalse(Execucao.objects.filter(tipo=TipoExecucao.CADASTRO_TINY).exists())

    @patch("apps.instancias.tiny_client.TinyApiClient.sincronizar_anexos_produto", return_value={})
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto", return_value=[])
    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_estoque")
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto", return_value={"id": 7, "sku": "IMG-NOVO"})
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_imagens_do_produto_novo_vao_junto(
        self, _mb, _mc, _me, _mg, _mp, _man, mock_anexos
    ):
        self._variacao("IMG-NOVO", imagens=["https://cdn/a.jpg"])

        self._rodar()

        mock_anexos.assert_called_once()


class DriftTests(_Base):
    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_estoque")
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_sem_mudanca_nenhuma_escrita_no_tiny(
        self, mock_busca, mock_criar, mock_estoque, mock_get, mock_put
    ):
        self._cadastrada("EM-DIA")  # todos os marcadores em dia

        self._rodar()

        mock_busca.assert_not_called()
        mock_criar.assert_not_called()
        mock_estoque.assert_not_called()
        mock_get.assert_not_called()
        mock_put.assert_not_called()
        self.assertFalse(Execucao.objects.filter(tipo=TipoExecucao.CADASTRO_TINY).exists())

    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_estoque", return_value={})
    def test_estoque_que_mudou_e_empurrado(self, mock_estoque, mock_get, mock_put):
        v = self._cadastrada("EST-1", tiny_id="111", estoque=42, estoque_tiny_sincronizado=10)

        self._rodar()

        mock_estoque.assert_called_once()
        self.assertEqual(mock_estoque.call_args.args[0], 111)
        v.refresh_from_db()
        self.assertEqual(v.estoque_tiny_sincronizado, 42)
        mock_put.assert_not_called()  # custo/dados seguem em dia

    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_estoque")
    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto", return_value=_get_tiny(222, "CUSTO-1"))
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    def test_custo_que_mudou_nao_e_reprocessado_automaticamente(self, mock_get, mock_put, mock_estoque):
        v = self._cadastrada(
            "CUSTO-1", tiny_id="222", preco=Decimal("18.00"),
            preco_custo_tiny_sincronizado=Decimal("12.00"),
        )
        mock_get.return_value = _get_tiny(222, "CUSTO-1")

        self._rodar()

        mock_put.assert_not_called()
        v.refresh_from_db()
        self.assertEqual(v.preco_custo_tiny_sincronizado, Decimal("12.00"))
        mock_estoque.assert_not_called()

    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_estoque")
    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto", return_value=_get_tiny(333, "DESC-1"))
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    def test_descricao_que_mudou_nao_e_reprocessada_automaticamente(self, mock_get, mock_put, _me):
        # marcador de dados zerado pela importação (descrição mudou no fornecedor)
        v = self._cadastrada("DESC-1", tiny_id="333", dados_tiny_sincronizados_em=None)
        mock_get.return_value = _get_tiny(333, "DESC-1")

        self._rodar()

        mock_put.assert_not_called()
        v.refresh_from_db()
        self.assertIsNone(v.dados_tiny_sincronizados_em)

    @patch("apps.instancias.tiny_client.TinyApiClient.sincronizar_anexos_produto", return_value={})
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto", return_value=[])
    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_estoque")
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_imagem_que_mudou_e_reenviada(
        self, mock_busca, _mc, _me, _mg, _mp, _man, mock_anexos
    ):
        # marcador de imagem zerado pela importação; produto já cadastrado
        self._cadastrada(
            "IMG-DRIFT", tiny_id="444", imagens=["https://cdn/nova.jpg"],
            imagens_tiny_sincronizadas=[],
        )

        self._rodar()

        # entrou na fila de cadastro só pela etapa de imagens: reenvia os
        # anexos, sem recriar o produto (SKU já cadastrado -> ja_cadastrado)
        mock_busca.assert_not_called()
        mock_anexos.assert_called_once()


class ErrosEProtecoesTests(_Base):
    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_estoque",
           side_effect=RuntimeError("Tiny 500"))
    def test_erro_do_tiny_no_estoque_nao_inicia_backfill_de_dados(
        self, mock_estoque, mock_get, mock_put
    ):
        # estoque vai falhar; o backfill de dados não faz parte do automático.
        v = self._cadastrada(
            "MIX-1", tiny_id="555", estoque=9, estoque_tiny_sincronizado=1,
            preco=Decimal("20.00"), preco_custo_tiny_sincronizado=Decimal("10.00"),
        )
        mock_get.return_value = _get_tiny(555, "MIX-1")

        self._rodar()  # não levanta

        mock_estoque.assert_called_once()  # tentou
        v.refresh_from_db()
        self.assertEqual(v.estoque_tiny_sincronizado, 1)          # não avançou (erro)
        self.assertEqual(v.preco_custo_tiny_sincronizado, Decimal("10.00"))
        mock_get.assert_not_called()
        mock_put.assert_not_called()

    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_estoque",
           side_effect=TinyApiError("429 persistente após 12 tentativas"))
    def test_rate_limit_numa_etapa_e_absorvido(self, mock_estoque, mock_get, mock_put):
        v = self._cadastrada("RL-1", tiny_id="666", estoque=3, estoque_tiny_sincronizado=1)

        self._rodar()  # não levanta

        v.refresh_from_db()
        self.assertEqual(v.estoque_tiny_sincronizado, 1)  # tenta de novo na próxima rodada

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_pula_tudo_se_ha_cadastro_em_massa_aberto_para_o_par(self, _mb, mock_criar):
        self._variacao("NOVO-BLOQ")
        Execucao.objects.create(
            instancia=self.instancia, fornecedor="asia", tipo=TipoExecucao.CADASTRO_TINY,
            status=StatusExecucao.RODANDO, heartbeat_em=timezone.now(),
        )

        self._rodar()

        mock_criar.assert_not_called()

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_pula_tudo_se_ha_retentativa_em_lote_ativa_para_o_par(self, _mb, mock_criar):
        self._variacao("NOVO-RETENTATIVA")
        execucao = Execucao.objects.create(
            instancia=self.instancia,
            fornecedor="asia",
            tipo=TipoExecucao.CADASTRO_TINY,
            status=StatusExecucao.RODANDO,
            heartbeat_em=timezone.now(),
        )
        RetentativaLote.objects.create(
            execucao=execucao,
            status=StatusRetentativaLote.RODANDO,
            heartbeat_em=timezone.now(),
            total=1,
            variacao_ids=[],
        )

        self._rodar()

        mock_criar.assert_not_called()

    @patch("apps.catalogo.tasks._reagendar_task_tiny")
    @patch("apps.catalogo.tasks.lock_instancia_tiny")
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_reagenda_se_a_conta_tiny_ja_esta_ocupada(
        self, _mb, mock_criar, mock_lock, mock_reagendar
    ):
        mock_lock.return_value.__enter__.return_value = False
        self._variacao("NOVO-LOCK")

        self._rodar()

        mock_criar.assert_not_called()
        mock_reagendar.assert_called_once()

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    def test_instancia_sem_token_nao_faz_nada(self, mock_criar):
        self.instancia.access_token = ""
        self.instancia.save(update_fields=["access_token"])
        self._variacao("SEM-TOKEN")

        self._rodar()

        mock_criar.assert_not_called()
