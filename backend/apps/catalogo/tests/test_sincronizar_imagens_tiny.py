"""
`sincronizar_imagens_tiny <slug>` — replica as imagens do fornecedor para
o Tiny, pelo endpoint específico POST /produtos/{id}/anexos, DEPOIS do
produto já estar cadastrado e com tiny_id confirmado.
"""

from decimal import Decimal
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.test import TestCase, override_settings

from apps.instancias.models import Instancia

from ..models import Produto, StatusVariacao, Variacao


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


class ImagemBasicaTests(TestCase):
    @patch("apps.instancias.tiny_client.TinyApiClient.adicionar_anexos_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto")
    def test_produto_com_uma_imagem(self, mock_get, mock_post):
        instancia = _instancia()
        v = _cadastrada(instancia, "MC511", imagens=["https://media.asiaimport.com.br/IMG_7230.jpg"], tiny_id="924")
        mock_get.return_value = []  # Tiny ainda sem anexo
        mock_post.return_value = {"ok": True}

        call_command("sincronizar_imagens_tiny", instancia.slug)

        mock_post.assert_called_once_with(924, ["https://media.asiaimport.com.br/IMG_7230.jpg"])
        v.refresh_from_db()
        self.assertEqual(v.imagens_tiny_sincronizadas, ["https://media.asiaimport.com.br/IMG_7230.jpg"])

    @patch("apps.instancias.tiny_client.TinyApiClient.adicionar_anexos_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto")
    def test_produto_com_multiplas_imagens_respeita_o_limite_de_cinco(self, mock_get, mock_post):
        instancia = _instancia()
        _cadastrada(instancia, "MULTI", imagens=[f"https://x/{i}.jpg" for i in range(8)])
        mock_get.return_value = []
        mock_post.return_value = {}

        call_command("sincronizar_imagens_tiny", instancia.slug)

        enviadas = mock_post.call_args[0][1]
        self.assertEqual(len(enviadas), 5)
        self.assertEqual(enviadas, [f"https://x/{i}.jpg" for i in range(5)])

    @patch("apps.instancias.tiny_client.TinyApiClient.adicionar_anexos_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto")
    def test_produto_sem_imagem_nao_e_erro(self, mock_get, mock_post):
        instancia = _instancia()
        # imagens=[] é excluído pela própria fila; imagens só com lixo entra e é ignorado
        _cadastrada(instancia, "SEM", imagens=["", None, "   "])

        saida = StringIO()
        call_command("sincronizar_imagens_tiny", instancia.slug, stdout=saida)

        mock_get.assert_not_called()
        mock_post.assert_not_called()
        self.assertIn("sem imagem utilizável", saida.getvalue())

    @patch("apps.instancias.tiny_client.TinyApiClient.adicionar_anexos_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto")
    def test_urls_invalidas_ou_vazias_sao_filtradas_antes_de_enviar(self, mock_get, mock_post):
        instancia = _instancia()
        _cadastrada(instancia, "MIX", imagens=["", "https://ok/1.jpg", None, "  ", "https://ok/1.jpg"])
        mock_get.return_value = []
        mock_post.return_value = {}

        call_command("sincronizar_imagens_tiny", instancia.slug)

        mock_post.assert_called_once_with(100, ["https://ok/1.jpg"])  # dedup + sem vazias


class IdempotenciaTests(TestCase):
    @patch("apps.instancias.tiny_client.TinyApiClient.adicionar_anexos_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto")
    def test_nao_reenvia_imagem_ja_presente_no_tiny(self, mock_get, mock_post):
        instancia = _instancia()
        _cadastrada(instancia, "DUP", imagens=["https://x/1.jpg", "https://x/2.jpg"])
        mock_get.return_value = ["https://x/1.jpg"]  # 1 já lá; 2 falta

        call_command("sincronizar_imagens_tiny", instancia.slug)

        mock_post.assert_called_once_with(100, ["https://x/2.jpg"])  # só a que falta

    @patch("apps.instancias.tiny_client.TinyApiClient.adicionar_anexos_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto")
    def test_reexecucao_apos_sucesso_nao_faz_nada(self, mock_get, mock_post):
        instancia = _instancia()
        _cadastrada(
            instancia, "OK", imagens=["https://x/1.jpg"],
            sincronizadas=["https://x/1.jpg"],  # marcador já cobre tudo
        )

        call_command("sincronizar_imagens_tiny", instancia.slug)

        mock_get.assert_not_called()   # nem o GET de diff
        mock_post.assert_not_called()

    @patch("apps.instancias.tiny_client.TinyApiClient.adicionar_anexos_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto")
    def test_marcador_stale_mas_tiny_ja_tem_tudo_so_atualiza_o_marcador(self, mock_get, mock_post):
        instancia = _instancia()
        v = _cadastrada(instancia, "STALE", imagens=["https://x/1.jpg"], sincronizadas=[])
        mock_get.return_value = ["https://x/1.jpg"]  # Tiny já tem

        call_command("sincronizar_imagens_tiny", instancia.slug)

        mock_post.assert_not_called()
        v.refresh_from_db()
        self.assertEqual(v.imagens_tiny_sincronizadas, ["https://x/1.jpg"])


class FalhaTests(TestCase):
    @patch("apps.instancias.tiny_client.TinyApiClient.adicionar_anexos_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto")
    def test_falha_ao_enviar_imagem_nao_perde_o_vinculo_do_produto(self, mock_get, mock_post):
        instancia = _instancia()
        v = _cadastrada(instancia, "FALHA", imagens=["https://x/1.jpg"], tiny_id="777")
        mock_get.return_value = []
        mock_post.side_effect = RuntimeError("Tiny recusou o anexo")

        call_command("sincronizar_imagens_tiny", instancia.slug)

        v.refresh_from_db()
        self.assertEqual(v.status, StatusVariacao.CADASTRADO)   # vínculo preservado
        self.assertEqual(v.tiny_id, "777")
        self.assertEqual(v.imagens_tiny_sincronizadas, [])       # não avançou
        self.assertIn("Tiny recusou o anexo", v.ultimo_erro)

    @patch("apps.instancias.tiny_client.TinyApiClient.adicionar_anexos_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto")
    def test_uma_falha_nao_trava_o_lote(self, mock_get, mock_post):
        instancia = _instancia()
        ruim = _cadastrada(instancia, "RUIM", imagens=["https://x/r.jpg"], tiny_id="1")
        bom = _cadastrada(instancia, "BOM", imagens=["https://x/b.jpg"], tiny_id="2")
        mock_get.return_value = []

        def efeito(id_produto, urls):
            if id_produto == 1:
                raise RuntimeError("falhou")
            return {}

        mock_post.side_effect = efeito
        call_command("sincronizar_imagens_tiny", instancia.slug)

        bom.refresh_from_db()
        ruim.refresh_from_db()
        self.assertEqual(bom.imagens_tiny_sincronizadas, ["https://x/b.jpg"])
        self.assertEqual(ruim.imagens_tiny_sincronizadas, [])


class SelecaoTests(TestCase):
    @patch("apps.instancias.tiny_client.TinyApiClient.adicionar_anexos_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto")
    def test_selecao_por_fornecedor_e_skus(self, mock_get, mock_post):
        instancia = _instancia()
        _cadastrada(instancia, "A-1", imagens=["https://x/a1.jpg"], fornecedor="asia", tiny_id="11")
        _cadastrada(instancia, "A-2", imagens=["https://x/a2.jpg"], fornecedor="asia", tiny_id="12")
        _cadastrada(instancia, "X-1", imagens=["https://x/x1.jpg"], fornecedor="xbz", tiny_id="13")
        mock_get.return_value = []
        mock_post.return_value = {}

        call_command("sincronizar_imagens_tiny", instancia.slug, "--fornecedor", "asia", "--skus", "A-1")

        self.assertEqual([c.args[0] for c in mock_post.call_args_list], [11])

    @patch("apps.instancias.tiny_client.TinyApiClient.adicionar_anexos_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto")
    def test_so_processa_produtos_ja_cadastrados_com_tiny_id(self, mock_get, mock_post):
        instancia = _instancia()
        v = _cadastrada(instancia, "PEND", imagens=["https://x/1.jpg"], tiny_id="")
        v.status = StatusVariacao.PENDENTE
        v.save(update_fields=["status"])

        call_command("sincronizar_imagens_tiny", instancia.slug)
        mock_get.assert_not_called()
        mock_post.assert_not_called()


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
            r.json.return_value = {"id": 55, "anexos": [{"url": "https://x/1.jpg", "externo": True}]}
            return r

        mock_request.side_effect = handler
        out = StringIO()
        call_command("sincronizar_imagens_tiny", instancia.slug, "--dry-run", stdout=out)

        self.assertEqual(set(metodos), {"GET"})
        self.assertIn("enviaria 1 imagem", out.getvalue())
        self.assertIn("https://x/2.jpg", out.getvalue())
        v.refresh_from_db()
        self.assertEqual(v.imagens_tiny_sincronizadas, [])   # nada gravado


class ClienteAnexosTests(TestCase):
    def test_corpo_anexos_e_lista_direta_sem_chave_anexos(self):
        from apps.instancias.tiny_client import _corpo_anexos

        self.assertEqual(
            _corpo_anexos(["https://a", "https://b"]),
            [{"url": "https://a", "externo": True}, {"url": "https://b", "externo": True}],
        )
        self.assertEqual(_corpo_anexos([]), [])

    @override_settings(TINY_API_BASE_URL="https://api.tiny.example")
    @patch("apps.instancias.tiny_client.requests.request")
    def test_adicionar_anexos_usa_endpoint_especifico_e_corpo_isolado(self, mock_request):
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
        cliente.adicionar_anexos_produto(55, ["https://x/1.jpg", "https://x/2.jpg"])

        metodo, url, corpo = chamadas[0]
        self.assertEqual(metodo, "POST")
        self.assertTrue(url.endswith("/produtos/55/anexos"))
        # contrato oficial Olist ERP v3: LISTA JSON direta, sem chave "anexos"
        self.assertEqual(corpo, [
            {"url": "https://x/1.jpg", "externo": True},
            {"url": "https://x/2.jpg", "externo": True},
        ])

    @override_settings(TINY_API_BASE_URL="https://api.tiny.example")
    @patch("apps.instancias.tiny_client.requests.request")
    def test_anexos_do_produto_extrai_so_urls_validas(self, mock_request):
        from apps.instancias.tiny_client import TinyApiClient

        instancia = _instancia()
        r = Mock(status_code=200, headers={}, text="")
        r.json.return_value = {
            "id": 55,
            "anexos": [
                {"url": "https://x/1.jpg", "externo": True},
                {"url": "", "externo": True},
                {"nome": "sem url"},
                {"url": "  https://x/2.jpg  "},
            ],
        }
        mock_request.return_value = r
        cliente = TinyApiClient(instancia, sleep_fn=lambda s: None)

        self.assertEqual(
            cliente.anexos_do_produto(55), ["https://x/1.jpg", "https://x/2.jpg"]
        )

    @override_settings(TINY_API_BASE_URL="https://api.tiny.example")
    @patch("apps.instancias.tiny_client.requests.request")
    def test_cliente_somente_leitura_bloqueia_o_post_de_anexos(self, mock_request):
        from apps.instancias.tiny_client import TinyApiClient, TinyEscritaBloqueadaError

        instancia = _instancia()
        cliente = TinyApiClient(instancia, sleep_fn=lambda s: None, somente_leitura=True)
        with self.assertRaises(TinyEscritaBloqueadaError):
            cliente.adicionar_anexos_produto(55, ["https://x/1.jpg"])
        mock_request.assert_not_called()
