"""Estoque Spot indisponível: distinção de zero e preservação sem banco/rede."""

from copy import deepcopy
from types import SimpleNamespace
from unittest.mock import Mock, patch

from django.test import SimpleTestCase, TestCase

from apps.catalogo.models import Produto, StatusVariacao, Variacao
from apps.fornecedores.management.commands.importar_fornecedor import Command
from apps.fornecedores.spot import SpotFornecedor
from apps.instancias.models import Instancia

from .fixtures import (
    SPOT_ESTOQUES_11112,
    SPOT_OPCIONAIS_11112,
    SPOT_PRODUTO_11112,
)


def _payload(stocks):
    return {
        "products": [deepcopy(SPOT_PRODUTO_11112)],
        "optionals": deepcopy(SPOT_OPCIONAIS_11112),
        "stocks": deepcopy(stocks),
    }


def _variacao_existente(normalizada, *, estoque=37, hash_conteudo="hash-anterior"):
    return SimpleNamespace(
        hash_conteudo=hash_conteudo,
        estoque=estoque,
        estoque_tiny_sincronizado=estoque,
        status=StatusVariacao.CADASTRADO,
        imagens=deepcopy(normalizada.imagens),
        imagens_tiny_sincronizadas=[],
        ncm=normalizada.ncm,
        largura=normalizada.dimensoes.largura,
        altura=normalizada.dimensoes.altura,
        comprimento=normalizada.dimensoes.comprimento,
        diametro=normalizada.dimensoes.diametro,
        peso_liquido=normalizada.dimensoes.peso_liquido,
        peso_bruto=normalizada.dimensoes.peso_bruto,
        dados_tiny_sincronizados_em=Mock(name="marcador_dados"),
        save=Mock(),
    )


class NormalizarEstoqueSpotTests(SimpleTestCase):
    @patch("apps.fornecedores.spot.logger.warning")
    def test_stocks_none_mantem_estoque_indisponivel(self, mock_warning):
        produtos = SpotFornecedor().normalizar(_payload(None))

        self.assertTrue(produtos)
        self.assertTrue(all(v.estoque is None for v in produtos[0].variacoes))
        mock_warning.assert_called_once()
        mensagem, diagnostico = mock_warning.call_args.args
        self.assertIn("stocks indisponível", mensagem)
        self.assertEqual(
            diagnostico["stocks"],
            {"presente": True, "tipo": "NoneType"},
        )

    @patch("apps.fornecedores.spot.logger.warning")
    def test_stocks_lista_vazia_continua_sendo_saldo_zero_valido(self, mock_warning):
        produtos = SpotFornecedor().normalizar(_payload([]))

        self.assertEqual([v.estoque for v in produtos[0].variacoes], [0, 0])
        mock_warning.assert_not_called()

    @patch("apps.fornecedores.spot.logger.warning")
    def test_stocks_tipo_invalido_continua_sendo_rejeitado(self, mock_warning):
        with self.assertRaisesRegex(ValueError, "'stocks' deve ser uma lista"):
            SpotFornecedor().normalizar(_payload({"unexpected": []}))

        mock_warning.assert_called_once()

    @patch("apps.fornecedores.spot.logger.warning")
    def test_stocks_validos_mantem_quantidades_atuais(self, mock_warning):
        produtos = SpotFornecedor().normalizar(_payload(SPOT_ESTOQUES_11112))

        por_sku = {v.sku: v.estoque for v in produtos[0].variacoes}
        self.assertEqual(por_sku["11112-104"], 4669)
        self.assertEqual(por_sku["11112-115"], 52)
        mock_warning.assert_not_called()

    @patch("apps.fornecedores.spot.logger.warning")
    def test_resumo_nao_classifica_estoque_indisponivel_como_zero(self, _mock_warning):
        produtos = SpotFornecedor().normalizar(_payload(None))

        resumo = Command()._resumo_dry_run(
            "spot", SimpleNamespace(slug="teste"), produtos
        )

        self.assertEqual(resumo["estoque_indisponivel"], 2)
        self.assertEqual(resumo["sem_estoque"], 0)
        self.assertEqual(resumo["com_estoque"], 0)


class PersistirEstoqueSpotIndisponivelTests(SimpleTestCase):
    @patch("apps.fornecedores.spot.requests.get")
    @patch("apps.fornecedores.spot.logger.warning")
    @patch("apps.fornecedores.management.commands.importar_fornecedor.Variacao")
    def test_stocks_none_nao_zera_estoque_status_ou_marcador_tiny(
        self, mock_variacao_model, _mock_warning, mock_get
    ):
        normalizada = SpotFornecedor().normalizar(_payload(None))[0].variacoes[0]
        existente = _variacao_existente(normalizada)
        mock_variacao_model.objects.filter.return_value.first.return_value = existente

        resultado, variacao = Command()._gravar_variacao(Mock(), normalizada)

        self.assertEqual(resultado, "atualizados")
        self.assertIs(variacao, existente)
        self.assertEqual(existente.estoque, 37)
        self.assertEqual(existente.estoque_tiny_sincronizado, 37)
        self.assertEqual(existente.status, StatusVariacao.CADASTRADO)
        campos = existente.save.call_args.kwargs["update_fields"]
        self.assertNotIn("estoque", campos)
        self.assertNotIn("estoque_tiny_sincronizado", campos)
        self.assertNotIn("status", campos)
        mock_get.assert_not_called()

    @patch("apps.fornecedores.management.commands.importar_fornecedor.Variacao")
    def test_stock_valido_mantem_persistencia_atual(self, mock_variacao_model):
        normalizada = SpotFornecedor().normalizar(
            _payload(SPOT_ESTOQUES_11112)
        )[0].variacoes[0]
        existente = _variacao_existente(normalizada, estoque=37)
        mock_variacao_model.objects.filter.return_value.first.return_value = existente

        resultado, variacao = Command()._gravar_variacao(Mock(), normalizada)

        self.assertEqual(resultado, "atualizados")
        self.assertIs(variacao, existente)
        self.assertEqual(existente.estoque, 4669)
        self.assertEqual(existente.estoque_tiny_sincronizado, 37)
        existente.save.assert_called_once_with()

    @patch("apps.fornecedores.management.commands.importar_fornecedor.Variacao")
    def test_variacao_nova_sem_estoque_e_adiada(self, mock_variacao_model):
        with patch("apps.fornecedores.spot.logger.warning"):
            normalizada = SpotFornecedor().normalizar(_payload(None))[0].variacoes[0]
        mock_variacao_model.objects.filter.return_value.first.return_value = None

        resultado, variacao = Command()._gravar_variacao(Mock(), normalizada)

        self.assertEqual(resultado, "ignorados")
        self.assertIsNone(variacao)
        mock_variacao_model.assert_not_called()


class PersistirEstoqueSpotMesmoHashRegressionTests(TestCase):
    """Regressões para mudanças exclusivas do endpoint ``stocks`` da Spot."""

    def setUp(self):
        self.instancia = Instancia.objects.create(nome="Loja Spot")
        self.produto = Produto.objects.create(
            instancia=self.instancia,
            fornecedor="spot",
            codigo_pai=SPOT_PRODUTO_11112["ProdReference"],
            nome=SPOT_PRODUTO_11112["Name"],
        )
        self.comando = Command()

    def _normalizada(self, stocks):
        return SpotFornecedor().normalizar(_payload(stocks))[0].variacoes[0]

    def _normalizada_com_estoque(self, quantidade):
        stocks = deepcopy(SPOT_ESTOQUES_11112)
        stocks[0]["Quantity"] = quantidade
        return self._normalizada(stocks)

    def _variacao_existente(
        self,
        normalizada,
        *,
        estoque,
        estoque_tiny_sincronizado,
        status=StatusVariacao.CADASTRADO,
    ):
        return Variacao.objects.create(
            produto=self.produto,
            sku=normalizada.sku,
            nome=normalizada.nome,
            ncm=normalizada.ncm,
            preco=normalizada.preco,
            estoque=estoque,
            cor=normalizada.cor,
            imagens=deepcopy(normalizada.imagens),
            atributos=deepcopy(normalizada.atributos),
            payload_bruto=deepcopy(normalizada.payload_bruto),
            status=status,
            tiny_id="900" if status == StatusVariacao.CADASTRADO else None,
            estoque_tiny_sincronizado=estoque_tiny_sincronizado,
        )

    def test_mesmo_payload_estoque_muda_de_200_para_zero(self):
        normalizada = self._normalizada_com_estoque(0)
        existente = self._variacao_existente(
            normalizada,
            estoque=200,
            estoque_tiny_sincronizado=200,
        )

        resultado, _ = self.comando._gravar_variacao(self.produto, normalizada)

        existente.refresh_from_db()
        self.assertEqual(resultado, "atualizados")
        self.assertEqual(existente.estoque, 0)
        self.assertEqual(existente.estoque_tiny_sincronizado, 200)
        self.assertEqual(existente.status, StatusVariacao.CADASTRADO)

    def test_mesmo_payload_e_mesmo_estoque_continua_ignorado(self):
        normalizada = self._normalizada_com_estoque(200)
        existente = self._variacao_existente(
            normalizada,
            estoque=200,
            estoque_tiny_sincronizado=200,
        )
        atualizado_em = existente.atualizado_em

        resultado, _ = self.comando._gravar_variacao(self.produto, normalizada)

        existente.refresh_from_db()
        self.assertEqual(resultado, "ignorados")
        self.assertEqual(existente.estoque, 200)
        self.assertEqual(existente.atualizado_em, atualizado_em)

    def test_stocks_vazio_persiste_zero_sobre_estoque_positivo(self):
        normalizada = self._normalizada([])
        existente = self._variacao_existente(
            normalizada,
            estoque=200,
            estoque_tiny_sincronizado=200,
        )

        resultado, _ = self.comando._gravar_variacao(self.produto, normalizada)

        existente.refresh_from_db()
        self.assertEqual(resultado, "atualizados")
        self.assertEqual(existente.estoque, 0)
        self.assertEqual(existente.estoque_tiny_sincronizado, 200)

    @patch("apps.fornecedores.spot.logger.warning")
    def test_stocks_none_preserva_estoque_anterior(self, _mock_warning):
        normalizada = self._normalizada(None)
        existente = self._variacao_existente(
            normalizada,
            estoque=200,
            estoque_tiny_sincronizado=200,
        )

        resultado, _ = self.comando._gravar_variacao(self.produto, normalizada)

        existente.refresh_from_db()
        self.assertEqual(resultado, "ignorados")
        self.assertEqual(existente.estoque, 200)
        self.assertEqual(existente.estoque_tiny_sincronizado, 200)
        self.assertEqual(existente.status, StatusVariacao.CADASTRADO)

    def test_reposicao_com_mesmo_payload_persiste_estoque_e_volta_a_pendente(self):
        normalizada = self._normalizada_com_estoque(25)
        existente = self._variacao_existente(
            normalizada,
            estoque=0,
            estoque_tiny_sincronizado=None,
            status=StatusVariacao.AGUARDANDO,
        )

        resultado, _ = self.comando._gravar_variacao(self.produto, normalizada)

        existente.refresh_from_db()
        self.assertEqual(resultado, "atualizados")
        self.assertEqual(existente.estoque, 25)
        self.assertEqual(existente.status, StatusVariacao.PENDENTE)
