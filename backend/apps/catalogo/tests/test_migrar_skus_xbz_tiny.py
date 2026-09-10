from decimal import Decimal
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.instancias.models import CredencialFornecedor, Instancia
from apps.instancias.tiny_client import TinyRateLimitError

from ..models import Produto, StatusVariacao, Variacao

TINY_ID = 924252038
TINY_FORNECEDOR_ID = 752133514
SKU_INTERNO = "X167827"
SKU_TINY = "08002-DOU"
ANEXOS = [{"id": 42, "url": "https://tiny.example/imagem.jpg", "externo": False}]


def _detalhe(
    sku,
    *,
    tiny_id=TINY_ID,
    fornecedor_codigo=None,
    custo=1,
    corrigido=False,
):
    return {
        "id": tiny_id,
        "sku": sku,
        "descricao": "Produto",
        "descricaoComplementar": "Descrição complementar" if corrigido else "",
        "origem": "0",
        "ncm": "73239300",
        "precos": {
            "preco": 0 if corrigido else 10,
            "precoPromocional": 0 if corrigido else 4,
            "precoCusto": custo,
        },
        "estoque": {
            "controlar": True,
            "sobEncomenda": False,
            "diasPreparacao": 0,
            "quantidade": 20,
        },
        "dimensoes": {"largura": 8, "altura": 10, "pesoBruto": 0.3},
        "fornecedores": (
            [{"id": TINY_FORNECEDOR_ID, "codigoProdutoNoFornecedor": fornecedor_codigo}]
            if fornecedor_codigo
            else []
        ),
        "anexos": ANEXOS,
    }


def _resposta(status, body=None, *, headers=None, sem_corpo=False):
    resposta = Mock()
    resposta.status_code = status
    resposta.headers = headers or {}
    resposta.text = ""
    if sem_corpo:
        resposta.json.side_effect = ValueError("sem corpo")
    else:
        resposta.json.return_value = body if body is not None else {}
    return resposta


class MigrarSkusXbzBase(TestCase):
    def setUp(self):
        self.instancia = Instancia.objects.create(nome="Loja", access_token="token")
        CredencialFornecedor.objects.create(
            instancia=self.instancia,
            fornecedor="xbz",
            tiny_fornecedor_id=TINY_FORNECEDOR_ID,
        )
        produto = Produto.objects.create(
            instancia=self.instancia,
            fornecedor="xbz",
            codigo_pai="08002",
            nome="Produto",
            descricao="Descrição complementar",
        )
        self.variacao = Variacao.objects.create(
            produto=produto,
            sku=SKU_INTERNO,
            nome="Produto",
            preco=Decimal("3.50"),
            estoque=2,
            status=StatusVariacao.CADASTRADO,
            tiny_id=str(TINY_ID),
            payload_bruto={"CodigoComposto": SKU_TINY},
            atributos={"codigo_composto": SKU_TINY},
        )
        patcher = patch(
            "apps.catalogo.management.commands.migrar_skus_xbz_tiny.time.sleep"
        )
        self.sleep = patcher.start()
        self.addCleanup(patcher.stop)

    def _rodar(self, *args):
        out, err = StringIO(), StringIO()
        call_command(
            "migrar_skus_xbz_tiny",
            "--instancia",
            self.instancia.slug,
            *args,
            stdout=out,
            stderr=err,
        )
        return out.getvalue() + err.getvalue()


class MigrarSkusXbzTests(MigrarSkusXbzBase):
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto")
    def test_dry_run_nao_faz_put(self, put, obter, buscar):
        obter.return_value = _detalhe(SKU_INTERNO)

        saida = self._rodar("--dry-run")

        put.assert_not_called()
        buscar.assert_called_once_with(SKU_TINY)
        self.assertIn("SERIA ATUALIZADO", saida)

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto", return_value={})
    def test_atualiza_mesmo_id_sem_create_sem_imagens_e_sem_mudar_identidade_local(
        self, put, obter, buscar, criar
    ):
        obter.side_effect = [
            _detalhe(SKU_INTERNO),
            _detalhe(SKU_TINY, fornecedor_codigo=SKU_TINY, custo=3.5, corrigido=True),
        ]

        saida = self._rodar("--executar")

        criar.assert_not_called()
        buscar.assert_called_once_with(SKU_TINY)
        put.assert_called_once()
        produto_id, payload = put.call_args.args
        self.assertEqual(produto_id, TINY_ID)
        self.assertEqual(payload["sku"], SKU_TINY)
        self.assertEqual(payload["fornecedores"][0]["codigoProdutoNoFornecedor"], SKU_TINY)
        self.assertEqual(payload["descricao"], "Produto")
        self.assertEqual(payload["descricaoComplementar"], "Descrição complementar")
        self.assertEqual(payload["ncm"], "73239300")
        self.assertEqual(payload["precos"], {"preco": 0.0, "precoPromocional": 0, "precoCusto": 3.5})
        self.assertEqual(payload["dimensoes"], {"largura": 8, "altura": 10, "pesoBruto": 0.3})
        self.assertEqual(
            payload["estoque"],
            {"controlar": True, "sobEncomenda": False, "diasPreparacao": 0},
        )
        self.assertNotIn("anexos", payload)
        self.assertNotIn("quantidade", payload["estoque"])
        self.assertIn("ATUALIZADO", saida)
        self.variacao.refresh_from_db()
        self.assertEqual(self.variacao.sku, SKU_INTERNO)
        self.assertEqual(self.variacao.tiny_id, str(TINY_ID))

    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto")
    def test_ja_migrado_e_idempotente_sem_novo_put(self, put, obter, buscar):
        obter.return_value = _detalhe(
            SKU_TINY, fornecedor_codigo=SKU_TINY, custo=3.5, corrigido=True
        )
        buscar.return_value = {"id": TINY_ID, "sku": SKU_TINY}

        primeira = self._rodar("--executar")
        segunda = self._rodar("--executar")

        put.assert_not_called()
        self.assertIn("JÁ MIGRADO", primeira)
        self.assertIn("JÁ MIGRADO", segunda)
        self.variacao.refresh_from_db()
        self.assertEqual(self.variacao.sku, SKU_INTERNO)
        self.assertEqual(self.variacao.tiny_id, str(TINY_ID))

    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto")
    def test_colisao_com_outro_tiny_id_bloqueia_put(self, put, obter, buscar):
        obter.return_value = _detalhe(SKU_INTERNO)
        buscar.return_value = {"id": 999, "sku": SKU_TINY}

        saida = self._rodar("--executar")

        put.assert_not_called()
        self.assertIn("COLISÃO", saida)
        self.assertIn("'colisoes': 1", saida)

    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto", return_value={})
    def test_pacing_e_aplicado_entre_todas_as_chamadas(self, put, obter, buscar):
        obter.side_effect = [
            _detalhe(SKU_INTERNO),
            _detalhe(SKU_TINY, fornecedor_codigo=SKU_TINY, custo=3.5, corrigido=True),
        ]

        self._rodar("--executar")

        self.assertEqual(self.sleep.call_count, 3)
        self.assertEqual([c.args[0] for c in self.sleep.call_args_list], [1.5, 1.5, 1.5])

    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto", return_value={})
    def test_put_aplicado_confirmacao_inconclusiva_e_retomado_sem_repetir_put(
        self, put, obter, buscar
    ):
        obter.side_effect = [
            _detalhe(SKU_INTERNO),
            TinyRateLimitError(f"/produtos/{TINY_ID}", 2),
        ]
        buscar.return_value = None

        primeira = self._rodar(
            "--executar",
            "--intervalo-requisicoes",
            "0",
            "--tentativas-operacao-429",
            "1",
        )

        self.assertIn("PUT enviado; confirmação inconclusiva", primeira)
        self.assertEqual(put.call_count, 1)
        self.variacao.refresh_from_db()
        self.assertIsNone(self.variacao.dados_tiny_sincronizados_em)

        obter.side_effect = None
        obter.return_value = _detalhe(
            SKU_TINY, fornecedor_codigo=SKU_TINY, custo=3.5, corrigido=True
        )
        buscar.return_value = {"id": TINY_ID, "sku": SKU_TINY}
        segunda = self._rodar("--executar", "--intervalo-requisicoes", "0")

        self.assertIn("JÁ MIGRADO", segunda)
        self.assertEqual(put.call_count, 1)
        self.variacao.refresh_from_db()
        self.assertIsNotNone(self.variacao.dados_tiny_sincronizados_em)

    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    @patch("apps.instancias.tiny_client.TinyApiClient.obter_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.atualizar_produto", return_value={})
    def test_interrupcao_preserva_concluidos_e_retomada_continua_restantes(
        self, put, obter, buscar
    ):
        produto_2 = Produto.objects.create(
            instancia=self.instancia,
            fornecedor="xbz",
            codigo_pai="06520",
            nome="Produto 2",
            descricao="Descrição complementar",
        )
        variacao_2 = Variacao.objects.create(
            produto=produto_2,
            sku="X000477",
            nome="Produto 2",
            preco=Decimal("3.50"),
            estoque=2,
            status=StatusVariacao.CADASTRADO,
            tiny_id="924252039",
            atributos={"codigo_composto": "06520-VD"},
        )
        obter.side_effect = [
            _detalhe(SKU_INTERNO),
            _detalhe(SKU_TINY, fornecedor_codigo=SKU_TINY, custo=3.5, corrigido=True),
            KeyboardInterrupt(),
        ]
        buscar.return_value = None

        with self.assertRaises(KeyboardInterrupt):
            self._rodar("--executar", "--intervalo-requisicoes", "0")

        self.variacao.refresh_from_db()
        variacao_2.refresh_from_db()
        self.assertIsNotNone(self.variacao.dados_tiny_sincronizados_em)
        self.assertIsNone(variacao_2.dados_tiny_sincronizados_em)
        self.assertEqual(put.call_count, 1)

        obter.side_effect = [
            _detalhe(SKU_TINY, fornecedor_codigo=SKU_TINY, custo=3.5, corrigido=True),
            _detalhe("X000477", tiny_id=924252039),
            _detalhe(
                "06520-VD",
                tiny_id=924252039,
                fornecedor_codigo="06520-VD",
                custo=3.5,
                corrigido=True,
            ),
        ]
        buscar.side_effect = [
            {"id": TINY_ID, "sku": SKU_TINY},
            None,
        ]

        saida = self._rodar("--executar", "--intervalo-requisicoes", "0")

        self.assertIn("JÁ MIGRADO", saida)
        self.assertIn("ATUALIZADO", saida)
        self.assertEqual(put.call_count, 2)
        self.assertEqual(put.call_args.args[0], 924252039)
        variacao_2.refresh_from_db()
        self.assertEqual(variacao_2.sku, "X000477")
        self.assertEqual(variacao_2.tiny_id, "924252039")
        self.assertIsNotNone(variacao_2.dados_tiny_sincronizados_em)


@override_settings(TINY_API_BASE_URL="https://api.tiny.example")
@patch("apps.instancias.tiny_client.RateLimiterCompartilhado")
@patch("apps.instancias.tiny_client.requests.request")
class MigrarSkusXbz429Tests(MigrarSkusXbzBase):
    def _sem_limiter(self, limiter):
        limiter.return_value.aguardar_vaga = lambda *args, **kwargs: None

    def _opcoes_rapidas(self):
        return (
            "--executar",
            "--intervalo-requisicoes",
            "0",
            "--max-tentativas-429",
            "2",
            "--tentativas-operacao-429",
            "2",
            "--espera-operacao-429",
            "7",
        )

    def test_429_antes_do_put_respeita_retry_after_e_recupera(self, request, limiter):
        self._sem_limiter(limiter)
        request.side_effect = [
            _resposta(429, headers={"Retry-After": "5"}),
            _resposta(200, _detalhe(SKU_INTERNO)),
            _resposta(200, {"itens": []}),
            _resposta(204, sem_corpo=True),
            _resposta(
                200,
                _detalhe(SKU_TINY, fornecedor_codigo=SKU_TINY, custo=3.5, corrigido=True),
            ),
        ]

        saida = self._rodar(*self._opcoes_rapidas())

        self.assertIn("429 em /produtos/924252038", saida)
        self.assertIn("aguardando 5 segundos (Retry-After)", saida)
        self.assertIn("ATUALIZADO", saida)
        self.assertIn(5.0, [c.args[0] for c in self.sleep.call_args_list])

    def test_429_no_put_usa_backoff_e_tenta_o_mesmo_id_novamente(self, request, limiter):
        self._sem_limiter(limiter)
        request.side_effect = [
            _resposta(200, _detalhe(SKU_INTERNO)),
            _resposta(200, {"itens": []}),
            _resposta(429),
            _resposta(204, sem_corpo=True),
            _resposta(
                200,
                _detalhe(SKU_TINY, fornecedor_codigo=SKU_TINY, custo=3.5, corrigido=True),
            ),
        ]

        saida = self._rodar(*self._opcoes_rapidas())

        puts = [c for c in request.call_args_list if c.args[0] == "PUT"]
        self.assertEqual(len(puts), 2)
        self.assertTrue(all(c.args[1].endswith(f"/produtos/{TINY_ID}") for c in puts))
        self.assertIn("(backoff)", saida)
        self.assertIn("ATUALIZADO", saida)

    def test_put_aceito_e_429_persistente_na_confirmacao_aguarda_e_confirma(
        self, request, limiter
    ):
        self._sem_limiter(limiter)
        request.side_effect = [
            _resposta(200, _detalhe(SKU_INTERNO)),
            _resposta(200, {"itens": []}),
            _resposta(204, sem_corpo=True),
            _resposta(429),
            _resposta(429),
            _resposta(429),
            _resposta(
                200,
                _detalhe(SKU_TINY, fornecedor_codigo=SKU_TINY, custo=3.5, corrigido=True),
            ),
        ]

        saida = self._rodar(*self._opcoes_rapidas())

        puts = [c for c in request.call_args_list if c.args[0] == "PUT"]
        self.assertEqual(len(puts), 1)
        self.assertIn("429 persistente ao confirmar PUT", saida)
        self.assertIn("aguardando 7 segundos", saida)
        self.assertIn("ATUALIZADO", saida)
        self.variacao.refresh_from_db()
        self.assertEqual(self.variacao.sku, SKU_INTERNO)
        self.assertEqual(self.variacao.tiny_id, str(TINY_ID))
