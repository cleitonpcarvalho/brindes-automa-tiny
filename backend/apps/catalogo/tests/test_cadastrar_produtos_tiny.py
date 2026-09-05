from decimal import Decimal
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.instancias.models import Instancia
from apps.instancias.tiny_client import TinyApiValidationError

from ..models import Produto, StatusVariacao, Variacao


def _instancia_pronta(**kwargs):
    dados = {
        "nome": "Loja Cadastro",
        "access_token": "token-valido",
        "tiny_origem_padrao": 0,
        "tiny_unidade_medida_padrao": "UN",
    }
    dados.update(kwargs)
    return Instancia.objects.create(**dados)


def _variacao_pendente(instancia, sku, **kwargs):
    produto = Produto.objects.create(
        instancia=instancia, fornecedor="xbz", codigo_pai=f"pai-{sku}", nome=f"Produto {sku}"
    )
    dados = {
        "produto": produto,
        "sku": sku,
        "nome": f"Variação {sku}",
        "preco": Decimal("10.00"),
        "estoque": 5,
    }
    dados.update(kwargs)
    return Variacao.objects.create(**dados)


class ValidacaoDeConfiguracaoTests(TestCase):
    def test_recusa_rodar_sem_origem_e_unidade_configuradas(self):
        instancia = Instancia.objects.create(nome="Loja Sem Config", access_token="t")
        _variacao_pendente(instancia, "SKU-1")
        with self.assertRaises(CommandError):
            call_command("cadastrar_produtos_tiny", instancia.slug)

    def test_recusa_rodar_sem_instancia_conectada(self):
        instancia = Instancia.objects.create(
            nome="Loja Desconectada", tiny_origem_padrao=0, tiny_unidade_medida_padrao="UN"
        )
        with self.assertRaises(CommandError):
            call_command("cadastrar_produtos_tiny", instancia.slug)


class CadastroCriaProdutoTests(TestCase):
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_produto_novo_e_criado_e_tiny_id_e_gravado(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        variacao = _variacao_pendente(instancia, "SKU-NOVO")
        mock_buscar.return_value = None
        mock_criar.return_value = {"id": 12345, "codigo": "SKU-NOVO", "descricao": "x"}

        call_command("cadastrar_produtos_tiny", instancia.slug)

        variacao.refresh_from_db()
        self.assertEqual(variacao.tiny_id, "12345")
        self.assertEqual(variacao.status, StatusVariacao.CADASTRADO)
        self.assertIsNotNone(variacao.cadastrado_em)
        mock_criar.assert_called_once()

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_payload_usa_sku_como_codigo_um_produto_por_variacao(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        _variacao_pendente(instancia, "SKU-PAYLOAD", ncm="12345678", preco=Decimal("19.90"), estoque=7)
        mock_buscar.return_value = None
        mock_criar.return_value = {"id": 1}

        call_command("cadastrar_produtos_tiny", instancia.slug)

        payload = mock_criar.call_args[0][0]
        self.assertEqual(payload["sku"], "SKU-PAYLOAD")
        self.assertEqual(payload["tipo"], "S")  # produto Simples — uma Variacao, um produto
        self.assertEqual(payload["ncm"], "12345678")
        self.assertEqual(payload["precos"]["preco"], 19.90)
        self.assertEqual(payload["unidade"], "UN")
        self.assertEqual(payload["origem"], 0)


class VinculacaoDeSkuExistenteTests(TestCase):
    """Regra do cliente: a conta já tem produtos cadastrados manualmente — nunca duplicar."""

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_sku_ja_existente_e_vinculado_sem_criar_duplicata(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        variacao = _variacao_pendente(instancia, "SKU-ANTIGO")
        mock_buscar.return_value = {"id": 999, "sku": "SKU-ANTIGO"}

        call_command("cadastrar_produtos_tiny", instancia.slug)

        variacao.refresh_from_db()
        self.assertEqual(variacao.tiny_id, "999")
        self.assertEqual(variacao.status, StatusVariacao.CADASTRADO)
        mock_criar.assert_not_called()


class NcmOpcionalTests(TestCase):
    """
    Correção do passo 6: o contrato oficial só exige sku/descricao/tipo — o
    NCM é nullable. Cadastrar sem NCM tem que dar certo (status cadastrado),
    não erro; a ausência só vira aviso no log, nunca bloqueia o lote.
    """

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_cadastro_sem_ncm_e_bem_sucedido_nao_e_erro(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        variacao = _variacao_pendente(instancia, "SKU-SEM-NCM", ncm="")
        mock_buscar.return_value = None
        mock_criar.return_value = {"id": 42}

        call_command("cadastrar_produtos_tiny", instancia.slug)

        variacao.refresh_from_db()
        self.assertEqual(variacao.status, StatusVariacao.CADASTRADO)
        self.assertEqual(variacao.tiny_id, "42")
        self.assertEqual(variacao.ultimo_erro, "")

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_payload_manda_ncm_none_em_vez_de_recusar_cadastro(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        _variacao_pendente(instancia, "SKU-SEM-NCM-2", ncm="")
        mock_buscar.return_value = None
        mock_criar.return_value = {"id": 1}

        call_command("cadastrar_produtos_tiny", instancia.slug)

        payload = mock_criar.call_args[0][0]
        self.assertIsNone(payload["ncm"])
        mock_criar.assert_called_once()  # tentou cadastrar normalmente, não pulou

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_erro_real_do_tiny_continua_marcando_status_erro(self, mock_buscar, mock_criar):
        """Um 400 de verdade (não relacionado a NCM) continua sendo tratado como erro normal."""
        instancia = _instancia_pronta()
        variacao = _variacao_pendente(instancia, "SKU-ERRO-REAL")
        mock_buscar.return_value = None
        mock_criar.side_effect = TinyApiValidationError("SKU inválido")

        call_command("cadastrar_produtos_tiny", instancia.slug)

        variacao.refresh_from_db()
        self.assertEqual(variacao.status, StatusVariacao.ERRO)
        self.assertIn("SKU inválido", variacao.ultimo_erro)


class DimensoesAnexosEGarantiaNoPayloadTests(TestCase):
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_payload_inclui_dimensoes_quando_normalizadas(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        _variacao_pendente(
            instancia,
            "SKU-DIM",
            largura=10.0,
            altura=20.0,
            comprimento=30.0,
            peso_liquido=0.5,
        )
        mock_buscar.return_value = None
        mock_criar.return_value = {"id": 1}

        call_command("cadastrar_produtos_tiny", instancia.slug)

        payload = mock_criar.call_args[0][0]
        self.assertEqual(
            payload["dimensoes"],
            {"largura": 10.0, "altura": 20.0, "comprimento": 30.0, "pesoLiquido": 0.5},
        )

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_payload_sem_nenhuma_dimensao_nao_inclui_o_campo(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        _variacao_pendente(instancia, "SKU-SEM-DIM")
        mock_buscar.return_value = None
        mock_criar.return_value = {"id": 1}

        call_command("cadastrar_produtos_tiny", instancia.slug)

        payload = mock_criar.call_args[0][0]
        self.assertNotIn("dimensoes", payload)

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_payload_monta_anexos_a_partir_das_imagens_do_espelho(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        _variacao_pendente(
            instancia,
            "SKU-IMG",
            imagens=["https://cdn.exemplo.com/a.jpg", "https://cdn.exemplo.com/b.jpg"],
        )
        mock_buscar.return_value = None
        mock_criar.return_value = {"id": 1}

        call_command("cadastrar_produtos_tiny", instancia.slug)

        payload = mock_criar.call_args[0][0]
        self.assertEqual(
            payload["anexos"],
            [
                {"url": "https://cdn.exemplo.com/a.jpg", "externo": True},
                {"url": "https://cdn.exemplo.com/b.jpg", "externo": True},
            ],
        )

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_anexos_respeitam_o_limite_maximo(self, mock_buscar, mock_criar):
        from ..management.commands.cadastrar_produtos_tiny import MAX_ANEXOS_POR_PRODUTO

        instancia = _instancia_pronta()
        muitas_imagens = [f"https://cdn.exemplo.com/{i}.jpg" for i in range(MAX_ANEXOS_POR_PRODUTO + 5)]
        _variacao_pendente(instancia, "SKU-MUITAS-IMG", imagens=muitas_imagens)
        mock_buscar.return_value = None
        mock_criar.return_value = {"id": 1}

        call_command("cadastrar_produtos_tiny", instancia.slug)

        payload = mock_criar.call_args[0][0]
        self.assertEqual(len(payload["anexos"]), MAX_ANEXOS_POR_PRODUTO)

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_sem_imagens_nao_inclui_anexos(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        _variacao_pendente(instancia, "SKU-SEM-IMG")
        mock_buscar.return_value = None
        mock_criar.return_value = {"id": 1}

        call_command("cadastrar_produtos_tiny", instancia.slug)

        payload = mock_criar.call_args[0][0]
        self.assertNotIn("anexos", payload)

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_garantia_e_incluida_quando_presente_nos_atributos(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        _variacao_pendente(
            instancia, "SKU-GARANTIA", atributos={"garantia_do_produto": "Contra defeitos de fabricação"}
        )
        mock_buscar.return_value = None
        mock_criar.return_value = {"id": 1}

        call_command("cadastrar_produtos_tiny", instancia.slug)

        payload = mock_criar.call_args[0][0]
        self.assertEqual(payload["garantia"], "Contra defeitos de fabricação")

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_sem_garantia_nos_atributos_nao_inclui_o_campo(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        _variacao_pendente(instancia, "SKU-SEM-GARANTIA")
        mock_buscar.return_value = None
        mock_criar.return_value = {"id": 1}

        call_command("cadastrar_produtos_tiny", instancia.slug)

        payload = mock_criar.call_args[0][0]
        self.assertNotIn("garantia", payload)


class FalhaNaoDerrubaLoteTests(TestCase):
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_uma_variacao_com_erro_nao_impede_as_demais(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        v1 = _variacao_pendente(instancia, "SKU-RUIM")
        v2 = _variacao_pendente(instancia, "SKU-BOM")
        mock_buscar.return_value = None

        def criar_side_effect(payload):
            if payload["sku"] == "SKU-RUIM":
                raise TinyApiValidationError("erro genérico")
            return {"id": 777}

        mock_criar.side_effect = criar_side_effect

        call_command("cadastrar_produtos_tiny", instancia.slug)

        v1.refresh_from_db()
        v2.refresh_from_db()
        self.assertEqual(v1.status, StatusVariacao.ERRO)
        self.assertEqual(v2.status, StatusVariacao.CADASTRADO)


class RetomadaAposInterrupcaoTests(TestCase):
    """
    Simula uma interrupção no meio do lote: processa só uma parte
    (--limite) e roda de novo sem --limite — precisa continuar exatamente
    de onde parou, sem duplicar nada e sem retocar as já cadastradas.
    """

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_segunda_rodada_so_processa_o_que_restou(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        skus = [f"SKU-LOTE-{i}" for i in range(5)]
        for sku in skus:
            _variacao_pendente(instancia, sku)

        mock_buscar.return_value = None
        mock_criar.side_effect = lambda payload: {"id": abs(hash(payload["sku"])) % 100000}

        # "cai" depois de processar só 2
        call_command("cadastrar_produtos_tiny", instancia.slug, "--limite", "2")
        self.assertEqual(mock_criar.call_count, 2)
        self.assertEqual(
            Variacao.objects.filter(produto__instancia=instancia, status=StatusVariacao.PENDENTE).count(), 3
        )

        # roda de novo, sem limite: continua de onde parou
        call_command("cadastrar_produtos_tiny", instancia.slug)

        self.assertEqual(mock_criar.call_count, 5)  # 2 da 1ª rodada + 3 da 2ª
        self.assertEqual(
            Variacao.objects.filter(produto__instancia=instancia, status=StatusVariacao.CADASTRADO).count(), 5
        )
        # nenhuma duplicata: continuam sendo 5 variações no total
        self.assertEqual(Variacao.objects.filter(produto__instancia=instancia).count(), 5)
