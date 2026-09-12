from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.instancias.models import CredencialFornecedor, Instancia
from apps.instancias.tiny_client import TinyApiValidationError

from ..models import Produto, ProdutoTiny, StatusVariacao, Variacao


def _com_tiny_fornecedor_id(instancia, fornecedor, tiny_id=700_000_000):
    CredencialFornecedor.objects.update_or_create(
        instancia=instancia, fornecedor=fornecedor, defaults={"tiny_fornecedor_id": tiny_id}
    )


def _rodar(*args):
    out = StringIO()
    err = StringIO()
    call_command(*args, stdout=out, stderr=err)
    return out.getvalue() + err.getvalue()


def _instancia_pronta(**kwargs):
    dados = {
        "nome": "Loja Cadastro",
        "access_token": "token-valido",
        "tiny_origem_padrao": 0,
        "tiny_unidade_medida_padrao": "UN",
    }
    dados.update(kwargs)
    return Instancia.objects.create(**dados)


def _variacao_pendente(instancia, sku, *, fornecedor="xbz", **kwargs):
    produto = Produto.objects.create(
        instancia=instancia, fornecedor=fornecedor, codigo_pai=f"pai-{sku}", nome=f"Produto {sku}"
    )
    dados = {
        "produto": produto,
        "sku": sku,
        "nome": f"Variação {sku}",
        "preco": Decimal("10.00"),
        "estoque": 5,
    }
    if fornecedor == "xbz":
        dados["payload_bruto"] = {"CodigoComposto": sku}
        dados["atributos"] = {"codigo_composto": sku}
    dados.update(kwargs)
    variacao = Variacao.objects.create(**dados)
    _com_tiny_fornecedor_id(instancia, fornecedor)
    return variacao


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

    @override_settings(TINY_API_BASE_URL="https://api.tiny.example")
    @patch("apps.instancias.tiny_client.requests.request")
    def test_http_201_do_tiny_e_tratado_como_sucesso_ponta_a_ponta(self, mock_request):
        """Regressão do 1º teste real: Tiny responde 201 no POST /produtos."""
        from unittest.mock import Mock

        instancia = _instancia_pronta()
        variacao = _variacao_pendente(instancia, "X000019", nome="CANECA ACRÍLICA 400 ML COM TAMPA")

        def handler(metodo, url, **kw):
            r = Mock(headers={}, text="")
            if metodo == "GET":  # buscar_produto_por_sku: SKU ainda não existe
                r.status_code = 200
                r.json.return_value = {"itens": []}
            else:  # POST /produtos
                r.status_code = 201
                r.json.return_value = {
                    "id": 924252038, "codigo": "X000019",
                    "descricao": "CANECA ACRÍLICA 400 ML COM TAMPA",
                }
            return r

        mock_request.side_effect = handler
        call_command("cadastrar_produtos_tiny", instancia.slug)

        variacao.refresh_from_db()
        self.assertEqual(variacao.status, StatusVariacao.CADASTRADO)
        self.assertEqual(variacao.tiny_id, "924252038")
        self.assertEqual(variacao.ultimo_erro, "")
        self.assertEqual(variacao.preco_custo_tiny_sincronizado, variacao.preco)

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
        # regra definitiva: o valor do fornecedor é CUSTO; a venda fica zerada
        self.assertEqual(payload["precos"], {"preco": 0, "precoPromocional": 0, "precoCusto": 19.90})
        self.assertEqual(payload["unidade"], "UN")
        self.assertEqual(payload["origem"], 0)
        # produto nasce no Tiny já com o estoque correto
        self.assertEqual(payload["estoque"], {"controlar": True, "inicial": 7.0})


class SkuPreexistenteNoTinyTests(TestCase):
    """
    Proteção conservadora: se o SKU exato já existe no Tiny e a Variacao
    não tem vínculo confirmado, o comando NÃO assume que o produto é da
    automação — bloqueia, não altera o produto Tiny nem a Variacao.
    """

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_sku_ja_existente_sem_vinculo_confirmado_e_bloqueado(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        variacao = _variacao_pendente(instancia, "SKU-ANTIGO", fornecedor="asia")
        mock_buscar.return_value = {"id": 999, "sku": "SKU-ANTIGO"}

        saida = _rodar("cadastrar_produtos_tiny", instancia.slug)

        variacao.refresh_from_db()
        self.assertIsNone(variacao.tiny_id)
        self.assertEqual(variacao.status, StatusVariacao.PENDENTE)  # inalterada
        mock_criar.assert_not_called()
        self.assertIn("BLOQUEADO", saida)
        self.assertIn("não possui vínculo confirmado", saida)

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_vinculo_so_acontece_com_confirmacao_explicita_do_operador(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        variacao = _variacao_pendente(instancia, "SKU-ANTIGO", fornecedor="asia")
        mock_buscar.return_value = {"id": 999, "sku": "SKU-ANTIGO"}

        call_command("cadastrar_produtos_tiny", instancia.slug, "--vincular-skus", "SKU-ANTIGO")

        variacao.refresh_from_db()
        self.assertEqual(variacao.tiny_id, "999")
        self.assertEqual(variacao.status, StatusVariacao.CADASTRADO)
        self.assertIsNone(variacao.preco_custo_tiny_sincronizado)  # não assume o custo de um produto preexistente
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
    def test_payload_de_criacao_nunca_mais_manda_anexos(self, mock_buscar, mock_criar):
        """Imagens saíram do POST /produtos (MC511: anexo na criação não apareceu no ERP)."""
        instancia = _instancia_pronta()
        _variacao_pendente(
            instancia, "SKU-IMG",
            imagens=["https://cdn.exemplo.com/a.jpg", "https://cdn.exemplo.com/b.jpg"],
        )
        mock_buscar.return_value = None
        mock_criar.return_value = {"id": 1}

        call_command("cadastrar_produtos_tiny", instancia.slug)

        self.assertNotIn("anexos", mock_criar.call_args[0][0])

    def test_imagens_utilizaveis_filtra_vazias_dedup_e_limita_a_cinco(self):
        from ..management.commands.cadastrar_produtos_tiny import (
            MAX_ANEXOS_POR_PRODUTO,
            imagens_utilizaveis,
        )

        instancia = _instancia_pronta()
        v = _variacao_pendente(
            instancia, "SKU-U",
            imagens=[
                "https://img.example/a.jpg",
                "",
                None,
                "  ",
                "https://img.example/a.jpg",
                "https://img.example/b.jpg",
            ] + [f"https://img.example/u{i}.jpg" for i in range(10)],
        )
        urls = imagens_utilizaveis(v)
        self.assertEqual(urls[:3], [
            "https://img.example/a.jpg",
            "https://img.example/b.jpg",
            "https://img.example/u0.jpg",
        ])  # vazias, texto e duplicata removidos
        self.assertEqual(len(urls), MAX_ANEXOS_POR_PRODUTO)   # limitado a 5

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_garantia_e_incluida_quando_presente_nos_atributos(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        _variacao_pendente(
            instancia, "SKU-GARANTIA", atributos={
                "codigo_composto": "SKU-GARANTIA",
                "garantia_do_produto": "Contra defeitos de fabricação",
            }
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


class VinculoFornecedorNoTinyTests(TestCase):
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_payload_inclui_o_bloco_fornecedores_com_o_id_configurado(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        _variacao_pendente(instancia, "SKU-FORN")  # helper já configura tiny_fornecedor_id
        CredencialFornecedor.objects.filter(instancia=instancia, fornecedor="xbz").update(
            tiny_fornecedor_id=752131325
        )
        mock_buscar.return_value = None
        mock_criar.return_value = {"id": 1}

        call_command("cadastrar_produtos_tiny", instancia.slug)

        payload = mock_criar.call_args[0][0]
        self.assertEqual(
            payload["fornecedores"],
            [{"id": 752131325, "padrao": True, "codigoProdutoNoFornecedor": "SKU-FORN"}],
        )

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_sem_id_configurado_bloqueia_a_criacao(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        variacao = _variacao_pendente(instancia, "SKU-SEM-FORN")
        CredencialFornecedor.objects.filter(instancia=instancia, fornecedor="xbz").update(
            tiny_fornecedor_id=None
        )
        mock_buscar.return_value = None

        saida = _rodar("cadastrar_produtos_tiny", instancia.slug)

        mock_criar.assert_not_called()
        variacao.refresh_from_db()
        self.assertEqual(variacao.status, StatusVariacao.PENDENTE)  # bloqueado, não erro
        self.assertIn("BLOQUEADO", saida)
        self.assertIn("Fornecedor no Tiny não configurado", saida)

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_id_resolvido_uma_vez_por_fornecedor_e_nao_por_sku(self, _mb, mock_criar):
        instancia = _instancia_pronta()
        for i in range(4):
            _variacao(_produto(instancia, "asia", f"pai{i}"), f"ASIA-{i}")
        mock_criar.return_value = {"id": 1}

        with patch(
            "apps.catalogo.management.commands.cadastrar_produtos_tiny.tiny_fornecedor_id_de",
            return_value=752133514,
        ) as mock_resolver:
            call_command("cadastrar_produtos_tiny", instancia.slug, "--fornecedor", "asia")

        self.assertEqual(mock_resolver.call_count, 1)  # 1x para o fornecedor, não 4x
        self.assertEqual(mock_criar.call_count, 4)


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


class CorrespondenciaSoPorSkuExatoTests(TestCase):
    """
    Modelo operacional definitivo: o vínculo com o Tiny é SÓ por SKU exato.
    Heurística (nome/NCM/descrição/fuzzy) e o espelho `ProdutoTiny` nunca
    participam de criação/atualização.
    """

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_produtotiny_com_mesmo_ncm_e_descricao_nao_vincula_a_variacao(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        variacao = _variacao_pendente(
            instancia, "SKU-FORNECEDOR", nome="Caneca Térmica 300ml", ncm="69120000"
        )
        # espelho do Tiny com produto "equivalente" por nome+NCM, SKU diferente
        ProdutoTiny.objects.create(
            instancia=instancia, tiny_id=8888, sku="ANTIGO-999",
            descricao="Caneca Térmica 300ml", ncm="69120000",
        )
        mock_buscar.return_value = None          # SKU exato NÃO existe no Tiny
        mock_criar.return_value = {"id": 4242}

        call_command("cadastrar_produtos_tiny", instancia.slug)

        variacao.refresh_from_db()
        # criou um produto novo — NÃO vinculou ao ProdutoTiny 8888
        self.assertEqual(variacao.tiny_id, "4242")
        self.assertEqual(variacao.status, StatusVariacao.CADASTRADO)
        mock_criar.assert_called_once()
        mock_buscar.assert_called_once_with("SKU-FORNECEDOR")

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_sku_do_fornecedor_e_usado_verbatim_na_busca_e_no_payload(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        sku_cru = "kt-9032Q/Caixa .01"
        _variacao_pendente(instancia, sku_cru)
        mock_buscar.return_value = None
        mock_criar.return_value = {"id": 1}

        call_command("cadastrar_produtos_tiny", instancia.slug)

        mock_buscar.assert_called_once_with(sku_cru)      # sem normalização
        self.assertEqual(mock_criar.call_args[0][0]["sku"], sku_cru)

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_sku_exato_existente_no_tiny_sem_vinculo_nao_e_tocado(self, mock_buscar, mock_criar):
        """Produto legado/preexistente com o mesmo SKU exato: nunca alterado sem vínculo confirmado."""
        instancia = _instancia_pronta()
        # A exceção XBZ reconcilia automaticamente; os demais continuam conservadores.
        variacao = _variacao_pendente(instancia, "EKKT-90395", fornecedor="asia")
        mock_buscar.return_value = {"id": 321, "sku": "EKKT-90395"}

        call_command("cadastrar_produtos_tiny", instancia.slug)

        variacao.refresh_from_db()
        self.assertIsNone(variacao.tiny_id)
        self.assertEqual(variacao.status, StatusVariacao.PENDENTE)
        mock_criar.assert_not_called()  # nada foi escrito no Tiny


class RegrasDeElegibilidadePreservadasTests(TestCase):
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_variacao_de_produto_xbz_p_arroba_nunca_e_enviada(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        produto = Produto.objects.create(
            instancia=instancia, fornecedor="xbz", codigo_pai="P@12288", nome="Saindo de linha"
        )
        variacao = Variacao.objects.create(
            produto=produto, sku="SKU-P-ARROBA", nome="x", preco=Decimal("10.00"), estoque=50
        )
        self.assertEqual(variacao.status, StatusVariacao.DESCONTINUADO)

        call_command("cadastrar_produtos_tiny", instancia.slug)

        mock_buscar.assert_not_called()
        mock_criar.assert_not_called()
        variacao.refresh_from_db()
        self.assertEqual(variacao.status, StatusVariacao.DESCONTINUADO)

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_variacao_com_estoque_zero_aguardando_nunca_e_enviada(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        variacao = _variacao_pendente(instancia, "SKU-SEM-ESTOQUE", estoque=0)
        self.assertEqual(variacao.status, StatusVariacao.AGUARDANDO)

        call_command("cadastrar_produtos_tiny", instancia.slug)

        mock_buscar.assert_not_called()
        mock_criar.assert_not_called()

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_custo_enviado_e_o_do_fornecedor_com_venda_zerada(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        variacao = _variacao_pendente(instancia, "SKU-PRECO", preco=Decimal("47.53"))
        mock_buscar.return_value = None
        mock_criar.return_value = {"id": 1}

        call_command("cadastrar_produtos_tiny", instancia.slug)

        precos = mock_criar.call_args[0][0]["precos"]
        self.assertEqual(precos["precoCusto"], 47.53)  # valor do fornecedor = CUSTO
        self.assertEqual(precos["preco"], 0)           # venda sempre zerada
        self.assertEqual(precos["precoPromocional"], 0)
        variacao.refresh_from_db()
        # criação levou precos.precoCusto = Variacao.preco -> marcador de custo avançou
        self.assertEqual(variacao.preco_custo_tiny_sincronizado, Decimal("47.53"))


def _produto(instancia, fornecedor, codigo_pai, nome="Produto"):
    _com_tiny_fornecedor_id(instancia, fornecedor)
    return Produto.objects.create(
        instancia=instancia, fornecedor=fornecedor, codigo_pai=codigo_pai, nome=nome
    )


def _variacao(produto, sku, **kwargs):
    dados = {"produto": produto, "sku": sku, "nome": f"Variação {sku}", "preco": Decimal("10.00"), "estoque": 5}
    if produto.fornecedor == "xbz":
        dados.update(payload_bruto={"CodigoComposto": sku}, atributos={"codigo_composto": sku})
    dados.update(kwargs)
    return Variacao.objects.create(**dados)


class SelecaoControladaTests(TestCase):
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_selecao_por_fornecedor(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        _variacao(_produto(instancia, "xbz", "x1"), "XBZ-1")
        _variacao(_produto(instancia, "asia", "a1"), "ASIA-1")
        mock_buscar.return_value = None
        mock_criar.return_value = {"id": 1}

        call_command("cadastrar_produtos_tiny", instancia.slug, "--fornecedor", "asia")

        skus_criados = [c.args[0]["sku"] for c in mock_criar.call_args_list]
        self.assertEqual(skus_criados, ["ASIA-1"])

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_selecao_por_skus_explicitos(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        p = _produto(instancia, "spot", "s1")
        for sku in ("SP-A", "SP-B", "SP-C"):
            _variacao(p, sku)
        mock_buscar.return_value = None
        mock_criar.return_value = {"id": 1}

        call_command("cadastrar_produtos_tiny", instancia.slug, "--skus", "SP-A, SP-C")

        skus_criados = sorted(c.args[0]["sku"] for c in mock_criar.call_args_list)
        self.assertEqual(skus_criados, ["SP-A", "SP-C"])

    @patch("apps.catalogo.management.commands.cadastrar_produtos_tiny.colisoes_cross_fornecedor")
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_skus_explicitos_recortam_tambem_a_analise_de_colisoes(
        self, mock_buscar, mock_criar, mock_colisoes
    ):
        instancia = _instancia_pronta()
        alvo = _variacao(_produto(instancia, "xbz", "alvo"), "ALVO")
        _variacao(_produto(instancia, "xbz", "fora"), "FORA")
        mock_buscar.return_value = None
        mock_criar.return_value = {"id": 1}
        mock_colisoes.return_value = {}

        call_command(
            "cadastrar_produtos_tiny",
            instancia.slug,
            "--fornecedor",
            "xbz",
            "--skus",
            "ALVO",
            "--dry-run",
        )

        mock_colisoes.assert_called_once_with(instancia, variacoes=[alvo])
        mock_criar.assert_not_called()

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_selecao_fornecedor_mais_skus(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        _variacao(_produto(instancia, "asia", "a"), "COD-1")
        _variacao(_produto(instancia, "asia", "b"), "COD-2")
        _variacao(_produto(instancia, "somarcas", "c"), "COD-3")
        mock_buscar.return_value = None
        mock_criar.return_value = {"id": 1}

        call_command("cadastrar_produtos_tiny", instancia.slug, "--fornecedor", "asia", "--skus", "COD-1")

        self.assertEqual([c.args[0]["sku"] for c in mock_criar.call_args_list], ["COD-1"])

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_skus_permite_reprocessar_uma_variacao_em_erro(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        v = _variacao(_produto(instancia, "xbz", "x"), "RETRY-1", status=StatusVariacao.ERRO, ultimo_erro="falhou antes")
        mock_buscar.return_value = None
        mock_criar.return_value = {"id": 77}

        call_command("cadastrar_produtos_tiny", instancia.slug, "--skus", "RETRY-1")

        v.refresh_from_db()
        self.assertEqual(v.status, StatusVariacao.CADASTRADO)
        self.assertEqual(v.tiny_id, "77")


class DryRunTests(TestCase):
    def _resp(self, corpo):
        from unittest.mock import Mock

        r = Mock()
        r.status_code = 200
        r.headers = {}
        r.json.return_value = corpo
        r.text = ""
        return r

    @patch("apps.instancias.tiny_client.requests.request")
    def test_dry_run_nunca_faz_metodo_de_escrita_e_nao_altera_banco(self, mock_request):
        instancia = _instancia_pronta()
        v = _variacao(_produto(instancia, "xbz", "x1"), "DRY-1", ncm="12345678", preco=Decimal("9.90"))

        metodos = []

        def handler(metodo, url, **kw):
            metodos.append(metodo)
            assert metodo == "GET", f"MÉTODO DE ESCRITA no dry-run: {metodo} {url}"
            return self._resp({"itens": []})  # SKU não existe no Tiny

        mock_request.side_effect = handler
        saida = _rodar("cadastrar_produtos_tiny", instancia.slug, "--dry-run")

        self.assertEqual(set(metodos), {"GET"})
        self.assertIn("SERIA CRIADO", saida)
        self.assertIn("payload que seria enviado", saida)
        v.refresh_from_db()
        self.assertIsNone(v.tiny_id)
        self.assertEqual(v.status, StatusVariacao.PENDENTE)
        self.assertIsNone(v.cadastrado_em)
        self.assertIsNone(v.preco_custo_tiny_sincronizado)

    @patch("apps.instancias.tiny_client.requests.request")
    def test_dry_run_nao_persiste_rate_limit_da_conta(self, mock_request):
        instancia = _instancia_pronta()
        _variacao(_produto(instancia, "xbz", "x1"), "DRY-RL")

        def handler(metodo, url, **kw):
            assert metodo == "GET"
            r = self._resp({"itens": []})
            r.headers = {"x-limit-api": "120"}
            return r

        mock_request.side_effect = handler
        call_command("cadastrar_produtos_tiny", instancia.slug, "--dry-run")

        instancia.refresh_from_db()
        self.assertIsNone(instancia.rate_limit_por_minuto)

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_dry_run_mostra_bloqueios(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        _variacao(_produto(instancia, "xbz", "P@99"), "PA-1")  # descontinuado por P@
        mock_buscar.return_value = None

        saida = _rodar("cadastrar_produtos_tiny", instancia.slug, "--dry-run", "--skus", "PA-1")

        self.assertIn("BLOQUEADO", saida)
        mock_criar.assert_not_called()


class BloqueiosTests(TestCase):
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_p_arroba_bloqueado_mesmo_quando_pedido_por_skus(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        p = _produto(instancia, "xbz", "P@12288", "Saindo de linha")
        v = _variacao(p, "PA-SKU", estoque=50)
        self.assertEqual(v.status, StatusVariacao.DESCONTINUADO)
        mock_buscar.return_value = None

        saida = _rodar("cadastrar_produtos_tiny", instancia.slug, "--skus", "PA-SKU")

        mock_criar.assert_not_called()
        mock_buscar.assert_not_called()
        self.assertIn("BLOQUEADO", saida)
        self.assertIn("P@", saida)
        v.refresh_from_db()
        self.assertEqual(v.status, StatusVariacao.DESCONTINUADO)

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_estoque_zero_bloqueado_mesmo_quando_pedido_por_skus(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        v = _variacao(_produto(instancia, "asia", "a"), "SEM-EST", estoque=0)
        self.assertEqual(v.status, StatusVariacao.AGUARDANDO)
        mock_buscar.return_value = None

        saida = _rodar("cadastrar_produtos_tiny", instancia.slug, "--skus", "SEM-EST")

        mock_criar.assert_not_called()
        self.assertIn("estoque <= 0", saida)

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_colisao_cross_supplier_bloqueia_o_sku_e_nao_escreve(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        _variacao(_produto(instancia, "xbz", "x"), "DUP-1")
        _variacao(_produto(instancia, "somarcas", "s"), "DUP-1")  # mesmo SKU, fornecedor diferente
        mock_buscar.return_value = None

        saida = _rodar("cadastrar_produtos_tiny", instancia.slug, "--skus", "DUP-1")

        mock_criar.assert_not_called()
        self.assertIn("mais de um fornecedor", saida)
        self.assertIn("somarcas", saida)
        self.assertIn("xbz", saida)
        self.assertEqual(
            Variacao.objects.filter(sku="DUP-1", tiny_id__isnull=False).count(), 0
        )

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_produto_legado_preexistente_nunca_e_alterado_sem_vinculo(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        v = _variacao(_produto(instancia, "somarcas", "s"), "AS-00610")
        mock_buscar.return_value = {"id": 4040, "sku": "AS-00610", "descricao": "produto do cliente"}

        call_command("cadastrar_produtos_tiny", instancia.slug)

        mock_criar.assert_not_called()  # nenhum POST
        v.refresh_from_db()
        self.assertIsNone(v.tiny_id)
        self.assertEqual(v.status, StatusVariacao.PENDENTE)


class RespostaDaCriacaoTests(TestCase):
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_resposta_sem_id_e_reconsulta_nao_confirma_marca_erro(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        v = _variacao(_produto(instancia, "xbz", "x"), "SEM-ID")
        mock_buscar.return_value = None            # 1ª busca: não existe
        mock_criar.return_value = {"status": "ok"}  # resposta ambígua, sem id

        call_command("cadastrar_produtos_tiny", instancia.slug)

        v.refresh_from_db()
        self.assertEqual(v.status, StatusVariacao.ERRO)   # NUNCA "cadastrado" sem confirmação
        self.assertIsNone(v.tiny_id)
        self.assertIn("id utilizável", v.ultimo_erro)

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_resposta_sem_id_mas_reconsulta_confirma_usa_o_id_reconsultado(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        v = _variacao(_produto(instancia, "xbz", "x"), "RECONS")
        # 1ª busca: não existe; após o POST ambíguo, reconsulta encontra o produto
        mock_buscar.side_effect = [None, {"id": 555, "sku": "RECONS"}]
        mock_criar.return_value = {}

        call_command("cadastrar_produtos_tiny", instancia.slug)

        v.refresh_from_db()
        self.assertEqual(v.status, StatusVariacao.CADASTRADO)
        self.assertEqual(v.tiny_id, "555")

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_id_aninhado_em_wrapper_e_aceito(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        v = _variacao(_produto(instancia, "xbz", "x"), "WRAP")
        mock_buscar.return_value = None
        mock_criar.return_value = {"produto": {"id": 909}}

        call_command("cadastrar_produtos_tiny", instancia.slug)

        v.refresh_from_db()
        self.assertEqual(v.tiny_id, "909")


class SemHeuristicaTests(TestCase):
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_nunca_usa_nome_ncm_descricao_ou_produtotiny(self, mock_buscar, mock_criar):
        instancia = _instancia_pronta()
        v = _variacao(_produto(instancia, "xbz", "x"), "SKU-NOVO-XYZ", nome="Caneca Preta", ncm="69120000")
        ProdutoTiny.objects.create(
            instancia=instancia, tiny_id=1, sku="OUTRO-SKU",
            descricao="Caneca Preta", ncm="69120000",
        )
        mock_buscar.return_value = None  # SKU exato não existe
        mock_criar.return_value = {"id": 1}

        call_command("cadastrar_produtos_tiny", instancia.slug)

        mock_buscar.assert_called_once_with("SKU-NOVO-XYZ")  # só SKU exato
        mock_criar.assert_called_once()                       # criou, não vinculou ao ProdutoTiny
        v.refresh_from_db()
        self.assertEqual(v.tiny_id, "1")


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
