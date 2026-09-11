"""
`sincronizar_imagens_tiny <slug>` — replica as imagens do fornecedor para
o Tiny via `PUT /produtos/{id}/anexos` com `externo=false` (o Tiny baixa e
hospeda a imagem — confirmado no MC511).

Idempotência: `Variacao.imagens_tiny_sincronizadas` guarda as URLs
ORIGINAIS já importadas. Não dá para comparar com o que o GET devolve
porque, depois do `externo=false`, o Tiny devolve a URL interna dele (S3).
"""

from decimal import Decimal
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.instancias.models import Instancia

from ..models import Produto, StatusVariacao, Variacao

ORIG = "https://media.asiaimport.com.br/2024/05/IMG_7230.jpg"
S3 = "https://s3.amazonaws.com/tiny-anexos-us/2026/abc123-IMG_7230.jpg"


def _instancia():
    return Instancia.objects.create(nome="Loja Img", access_token="tok")


def _cadastrada(instancia, sku, *, imagens, tiny_id="100", fornecedor="asia", sincronizadas=None):
    produto = Produto.objects.create(
        instancia=instancia, fornecedor=fornecedor, codigo_pai=f"pai-{sku}", nome=sku
    )
    return Variacao.objects.create(
        produto=produto,
        sku=sku,
        nome=sku,
        preco=Decimal("10.00"),
        estoque=5,
        status=StatusVariacao.CADASTRADO,
        tiny_id=tiny_id,
        imagens=imagens,
        imagens_tiny_sincronizadas=sincronizadas or [],
    )


class EnvioTests(TestCase):
    @patch("apps.instancias.tiny_client.TinyApiClient.sincronizar_anexos_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto")
    def test_produto_com_uma_imagem_manda_put_com_a_url_original(self, mock_get, mock_put):
        instancia = _instancia()
        v = _cadastrada(instancia, "MC511", imagens=[ORIG], tiny_id="924")
        mock_get.return_value = []                     # Tiny ainda sem anexo
        mock_put.return_value = {"anexos": [{"url": S3, "externo": False}]}

        call_command("sincronizar_imagens_tiny", instancia.slug)

        mock_put.assert_called_once_with(924, [ORIG])   # lista completa de URLs ORIGINAIS
        v.refresh_from_db()
        self.assertEqual(v.imagens_tiny_sincronizadas, [ORIG])  # marcador = originais

    @patch("apps.instancias.tiny_client.TinyApiClient.sincronizar_anexos_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto")
    def test_multiplas_imagens_limitadas_a_cinco(self, mock_get, mock_put):
        instancia = _instancia()
        _cadastrada(instancia, "MULTI", imagens=[f"https://x/{i}.jpg" for i in range(8)])
        mock_get.return_value = []
        mock_put.return_value = {}

        call_command("sincronizar_imagens_tiny", instancia.slug)

        enviadas = mock_put.call_args[0][1]
        self.assertEqual(enviadas, [f"https://x/{i}.jpg" for i in range(5)])

    @patch("apps.instancias.tiny_client.TinyApiClient.sincronizar_anexos_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto")
    def test_produto_sem_imagem_utilizavel_nao_e_erro(self, mock_get, mock_put):
        instancia = _instancia()
        _cadastrada(instancia, "SEM", imagens=["", None, "   "])

        saida = StringIO()
        call_command("sincronizar_imagens_tiny", instancia.slug, stdout=saida)

        mock_get.assert_not_called()
        mock_put.assert_not_called()
        self.assertIn("sem imagem utilizável", saida.getvalue())

    @patch("apps.instancias.tiny_client.TinyApiClient.sincronizar_anexos_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto")
    def test_urls_vazias_e_duplicadas_filtradas_antes_do_put(self, mock_get, mock_put):
        instancia = _instancia()
        _cadastrada(instancia, "MIX", imagens=["", "https://ok/1.jpg", None, "  ", "https://ok/1.jpg"])
        mock_get.return_value = []
        mock_put.return_value = {}

        call_command("sincronizar_imagens_tiny", instancia.slug)

        mock_put.assert_called_once_with(100, ["https://ok/1.jpg"])


class IdempotenciaTests(TestCase):
    @patch("apps.instancias.tiny_client.TinyApiClient.sincronizar_anexos_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto")
    def test_marcador_cobre_tudo_pula_sem_nem_o_get(self, mock_get, mock_put):
        instancia = _instancia()
        _cadastrada(instancia, "OK", imagens=[ORIG], sincronizadas=[ORIG])

        call_command("sincronizar_imagens_tiny", instancia.slug)

        mock_get.assert_not_called()
        mock_put.assert_not_called()

    @patch("apps.instancias.tiny_client.TinyApiClient.sincronizar_anexos_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto")
    def test_reexecucao_apos_sucesso_nao_faz_nova_escrita(self, mock_get, mock_put):
        instancia = _instancia()
        v = _cadastrada(instancia, "MC511", imagens=[ORIG], tiny_id="924")
        mock_get.return_value = []
        mock_put.return_value = {}

        call_command("sincronizar_imagens_tiny", instancia.slug)   # 1ª: envia
        self.assertEqual(mock_put.call_count, 1)
        v.refresh_from_db()
        self.assertEqual(v.imagens_tiny_sincronizadas, [ORIG])

        mock_get.reset_mock()
        mock_put.reset_mock()
        call_command("sincronizar_imagens_tiny", instancia.slug)   # 2ª: nada
        mock_put.assert_not_called()                               # não subiu
        mock_get.assert_not_called()                               # nem GET

    @patch("apps.instancias.tiny_client.TinyApiClient.sincronizar_anexos_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto")
    def test_tiny_retorna_url_s3_diferente_da_original_nao_reenvia(self, mock_get, mock_put):
        """Depois do externo=false o GET devolve a URL interna S3, != da original."""
        instancia = _instancia()
        v = _cadastrada(instancia, "MC511", imagens=[ORIG], tiny_id="924", sincronizadas=[])
        mock_get.return_value = [S3]   # Tiny já tem 1 anexo (interno), != ORIG

        call_command("sincronizar_imagens_tiny", instancia.slug)

        mock_put.assert_not_called()                       # contagem 1 >= 1 -> não reenvia
        v.refresh_from_db()
        self.assertEqual(v.imagens_tiny_sincronizadas, [ORIG])  # marcador reconciliado c/ a ORIGINAL

    @patch("apps.instancias.tiny_client.TinyApiClient.sincronizar_anexos_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto")
    def test_tiny_com_menos_anexos_que_o_desejado_faz_put_da_lista_completa(self, mock_get, mock_put):
        instancia = _instancia()
        _cadastrada(instancia, "P", imagens=["https://x/1.jpg", "https://x/2.jpg", "https://x/3.jpg"])
        mock_get.return_value = ["https://s3/only-one.jpg"]   # Tiny só tem 1 de 3
        mock_put.return_value = {}

        call_command("sincronizar_imagens_tiny", instancia.slug)

        mock_put.assert_called_once_with(
            100, ["https://x/1.jpg", "https://x/2.jpg", "https://x/3.jpg"]
        )


class MC511LikeTests(TestCase):
    @patch("apps.instancias.tiny_client.TinyApiClient.sincronizar_anexos_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto")
    def test_imagem_interna_ja_existente_e_marcador_ausente_so_reconcilia(self, mock_get, mock_put):
        instancia = _instancia()
        v = _cadastrada(instancia, "MC511", imagens=[ORIG], tiny_id="924252215", sincronizadas=[])
        mock_get.return_value = [S3]   # já internalizada à mão

        call_command("sincronizar_imagens_tiny", instancia.slug, "--fornecedor", "asia", "--skus", "MC511")

        mock_put.assert_not_called()
        v.refresh_from_db()
        self.assertEqual(v.imagens_tiny_sincronizadas, [ORIG])

    @override_settings(TINY_API_BASE_URL="https://api.tiny.example")
    @patch("apps.instancias.tiny_client.requests.request")
    def test_so_reconciliar_nunca_escreve_no_tiny_e_marca_o_que_ja_esta_la(self, mock_request):
        instancia = _instancia()
        pronto = _cadastrada(instancia, "MC511", imagens=[ORIG], tiny_id="924", sincronizadas=[])
        faltando = _cadastrada(instancia, "OUTRO", imagens=["https://x/1.jpg", "https://x/2.jpg"], tiny_id="925", sincronizadas=[])
        metodos = []

        def handler(metodo, url, **kw):
            metodos.append(metodo)
            assert metodo == "GET", f"escrita no --so-reconciliar: {metodo}"
            r = Mock(status_code=200, headers={}, text="")
            r.json.return_value = {"id": 1, "anexos": ([{"url": S3}] if "924" in url else [])}
            return r

        mock_request.side_effect = handler
        out = StringIO()
        call_command("sincronizar_imagens_tiny", instancia.slug, "--so-reconciliar", stdout=out)

        self.assertEqual(set(metodos), {"GET"})
        pronto.refresh_from_db()
        faltando.refresh_from_db()
        self.assertEqual(pronto.imagens_tiny_sincronizadas, [ORIG])   # reconciliado
        self.assertEqual(faltando.imagens_tiny_sincronizadas, [])     # não mexe
        self.assertIn("precisa de PUT", out.getvalue())


class FalhaTests(TestCase):
    @patch("apps.instancias.tiny_client.TinyApiClient.sincronizar_anexos_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto")
    def test_falha_no_put_nao_perde_status_nem_tiny_id(self, mock_get, mock_put):
        instancia = _instancia()
        v = _cadastrada(instancia, "FALHA", imagens=[ORIG], tiny_id="777")
        mock_get.return_value = []
        mock_put.side_effect = RuntimeError("Tiny recusou o anexo")

        call_command("sincronizar_imagens_tiny", instancia.slug)

        v.refresh_from_db()
        self.assertEqual(v.status, StatusVariacao.CADASTRADO)
        self.assertEqual(v.tiny_id, "777")
        self.assertEqual(v.imagens_tiny_sincronizadas, [])   # não avançou
        self.assertIn("Tiny recusou o anexo", v.ultimo_erro)

    @patch("apps.instancias.tiny_client.TinyApiClient.sincronizar_anexos_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto")
    def test_uma_falha_nao_trava_o_lote(self, mock_get, mock_put):
        instancia = _instancia()
        ruim = _cadastrada(instancia, "RUIM", imagens=["https://x/r.jpg"], tiny_id="1")
        bom = _cadastrada(instancia, "BOM", imagens=["https://x/b.jpg"], tiny_id="2")
        mock_get.return_value = []

        def efeito(id_produto, urls):
            if id_produto == 1:
                raise RuntimeError("falhou")
            return {}

        mock_put.side_effect = efeito
        call_command("sincronizar_imagens_tiny", instancia.slug)

        bom.refresh_from_db()
        ruim.refresh_from_db()
        self.assertEqual(bom.imagens_tiny_sincronizadas, ["https://x/b.jpg"])
        self.assertEqual(ruim.imagens_tiny_sincronizadas, [])


class SelecaoTests(TestCase):
    @patch("apps.instancias.tiny_client.TinyApiClient.sincronizar_anexos_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto")
    def test_selecao_por_fornecedor_e_skus(self, mock_get, mock_put):
        instancia = _instancia()
        _cadastrada(instancia, "A-1", imagens=["https://x/a1.jpg"], fornecedor="asia", tiny_id="11")
        _cadastrada(instancia, "A-2", imagens=["https://x/a2.jpg"], fornecedor="asia", tiny_id="12")
        _cadastrada(instancia, "X-1", imagens=["https://x/x1.jpg"], fornecedor="xbz", tiny_id="13")
        mock_get.return_value = []
        mock_put.return_value = {}

        call_command("sincronizar_imagens_tiny", instancia.slug, "--fornecedor", "asia", "--skus", "A-1")

        self.assertEqual([c.args[0] for c in mock_put.call_args_list], [11])

    @patch("apps.instancias.tiny_client.TinyApiClient.sincronizar_anexos_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto")
    def test_so_processa_cadastrados_com_tiny_id(self, mock_get, mock_put):
        instancia = _instancia()
        v = _cadastrada(instancia, "PEND", imagens=["https://x/1.jpg"], tiny_id="")
        v.status = StatusVariacao.PENDENTE
        v.save(update_fields=["status"])

        call_command("sincronizar_imagens_tiny", instancia.slug)
        mock_get.assert_not_called()
        mock_put.assert_not_called()


class DryRunTests(TestCase):
    @override_settings(TINY_API_BASE_URL="https://api.tiny.example")
    @patch("apps.instancias.tiny_client.requests.request")
    def test_dry_run_faz_get_mas_nunca_escreve_e_nao_altera_banco(self, mock_request):
        instancia = _instancia()
        v = _cadastrada(instancia, "DRY", imagens=["https://x/1.jpg", "https://x/2.jpg"], tiny_id="55")
        metodos = []

        def handler(metodo, url, **kw):
            metodos.append(metodo)
            assert metodo == "GET", f"escrita no dry-run: {metodo} {url}"
            r = Mock(status_code=200, headers={}, text="")
            r.json.return_value = {"id": 55, "anexos": [{"url": S3}]}   # Tiny tem 1 de 2
            return r

        mock_request.side_effect = handler
        out = StringIO()
        call_command("sincronizar_imagens_tiny", instancia.slug, "--dry-run", stdout=out)

        self.assertEqual(set(metodos), {"GET"})
        self.assertIn("PUT com 2 imagem", out.getvalue())
        self.assertIn("externo=false", out.getvalue())
        self.assertIn("https://x/1.jpg", out.getvalue())
        v.refresh_from_db()
        self.assertEqual(v.imagens_tiny_sincronizadas, [])   # nada gravado


class ClienteAnexosTests(TestCase):
    def test_normaliza_unicode_espaco_sem_codificar_estrutura(self):
        from apps.instancias.tiny_client import normalizar_url_http

        original = "https://host/produto m².webp?a=valor ²&b=1#parte ²"
        self.assertEqual(
            normalizar_url_http(original),
            "https://host/produto%20m%C2%B2.webp?a=valor%20%C2%B2&b=1#parte%20%C2%B2",
        )

    def test_normalizacao_preserva_percent_encoding_e_eh_idempotente(self):
        from apps.instancias.tiny_client import normalizar_url_http

        url = "https://host/produto%20m%C2%B2.webp?a=%C2%B2"
        normalizada = normalizar_url_http(url)
        self.assertEqual(normalizada, url)
        self.assertEqual(normalizar_url_http(normalizada), normalizada)

    def test_corpo_anexos_e_lista_direta_com_externo_false(self):
        from apps.instancias.tiny_client import _corpo_anexos

        self.assertEqual(
            _corpo_anexos(["https://a", "https://b"]),
            [{"url": "https://a", "externo": False}, {"url": "https://b", "externo": False}],
        )
        self.assertEqual(_corpo_anexos([]), [])

    def test_payload_de_anexos_normaliza_somente_a_url_enviada(self):
        from apps.instancias.tiny_client import _corpo_anexos

        self.assertEqual(
            _corpo_anexos(["https://host/produto m².webp?x=1&y=2"]),
            [{"url": "https://host/produto%20m%C2%B2.webp?x=1&y=2", "externo": False}],
        )

    @override_settings(TINY_API_BASE_URL="https://api.tiny.example")
    @patch("apps.instancias.tiny_client.requests.request")
    def test_sincronizar_anexos_usa_put_no_endpoint_com_corpo_lista(self, mock_request):
        from apps.instancias.tiny_client import TinyApiClient

        instancia = _instancia()
        chamadas = []

        def handler(metodo, url, **kw):
            chamadas.append((metodo, url, kw.get("json")))
            r = Mock(status_code=200, headers={}, text="")
            r.json.return_value = {"ok": True}
            return r

        mock_request.side_effect = handler
        cliente = TinyApiClient(instancia, sleep_fn=lambda s: None)
        cliente.sincronizar_anexos_produto(55, ["https://x/produto m².jpg", "https://x/2.jpg"])

        metodo, url, corpo = chamadas[0]
        self.assertEqual(metodo, "PUT")
        self.assertTrue(url.endswith("/produtos/55/anexos"))
        self.assertEqual(corpo, [
            {"url": "https://x/produto%20m%C2%B2.jpg", "externo": False},
            {"url": "https://x/2.jpg", "externo": False},
        ])

    @override_settings(TINY_API_BASE_URL="https://api.tiny.example")
    @patch("apps.instancias.tiny_client.requests.request")
    def test_anexos_do_produto_extrai_urls_incluindo_as_internas_s3(self, mock_request):
        from apps.instancias.tiny_client import TinyApiClient

        instancia = _instancia()
        r = Mock(status_code=200, headers={}, text="")
        r.json.return_value = {
            "id": 55,
            "anexos": [
                {"url": S3, "externo": False},
                {"url": "", "externo": False},
                {"nome": "sem url"},
                {"url": "  https://x/2.jpg  "},
            ],
        }
        mock_request.return_value = r
        cliente = TinyApiClient(instancia, sleep_fn=lambda s: None)

        self.assertEqual(cliente.anexos_do_produto(55), [S3, "https://x/2.jpg"])

    @override_settings(TINY_API_BASE_URL="https://api.tiny.example")
    @patch("apps.instancias.tiny_client.requests.request")
    def test_cliente_somente_leitura_bloqueia_o_put_de_anexos(self, mock_request):
        from apps.instancias.tiny_client import TinyApiClient, TinyEscritaBloqueadaError

        instancia = _instancia()
        cliente = TinyApiClient(instancia, sleep_fn=lambda s: None, somente_leitura=True)
        with self.assertRaises(TinyEscritaBloqueadaError):
            cliente.sincronizar_anexos_produto(55, ["https://x/1.jpg"])
        mock_request.assert_not_called()
