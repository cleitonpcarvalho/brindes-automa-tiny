"""
`importar_catalogo_tiny <slug>` — espelho local (ProdutoTiny) do catálogo do
Tiny. Somente leitura: nenhum POST/PUT/PATCH/DELETE no Tiny.

Os testes mockam o transporte HTTP (`requests.request`) do TinyApiClient e
o handler falso rejeita qualquer método != GET — é a prova de que o comando
nunca escreve no Tiny.
"""

from decimal import Decimal
from io import StringIO
from unittest.mock import Mock, patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase, override_settings

from apps.instancias.models import Instancia

from ..management.commands import importar_catalogo_tiny as cmd
from ..models import ProdutoTiny


def _resp(status_code=200, corpo=None, headers=None):
    r = Mock()
    r.status_code = status_code
    r.headers = headers or {}
    r.json.return_value = {} if corpo is None else corpo
    r.text = str(corpo or "")
    return r


def _listagem(pid, **over):
    base = {
        "id": pid,
        "sku": f"SKU-{pid}",
        "descricao": f"Produto {pid}",
        "tipo": "S",
        "situacao": "A",
        "unidade": "UN",
        "gtin": f"789000000{pid:04d}",
        "dataCriacao": "2026-01-01 10:00:00",
        "dataAlteracao": "2026-02-01 10:00:00",
        "precos": {"preco": 10.0 + pid, "precoPromocional": None, "precoCusto": 5.0},
        "tipoVariacao": "N",
    }
    base.update(over)
    return base


def _detalhe(pid, **over):
    base = {
        "id": pid,
        "sku": f"SKU-{pid}",
        "descricao": f"Produto {pid}",
        "ncm": "73239300",
        "gtin": f"789000000{pid:04d}",
        "unidade": "UN",
        "origem": "0",
        "marca": {"id": 7, "nome": "Marca X"},
        "categoria": {"id": 3, "nome": "Copos", "caminhoCompleto": "Casa >> Copos"},
        "dimensoes": {
            "largura": 8.0, "altura": 12.0, "comprimento": 8.0,
            "diametro": None, "pesoLiquido": 0.15, "pesoBruto": 0.2,
        },
        "estoque": {"quantidade": 42.0, "controlar": True},
        "precos": {"preco": 10.0 + pid, "precoPromocional": None, "precoCusto": 5.0},
    }
    base.update(over)
    return base


class HandlerTiny:
    """Handler de `requests.request`: só GET; pagina /produtos e serve /produtos/{id}."""

    def __init__(self, produtos, page_size=100, headers_listagem=None):
        self.produtos = produtos  # {pid: {"listagem": {...}, "detalhe": {...}}}
        self.page_size = page_size
        self.headers_listagem = headers_listagem or {}
        self.chamadas_listagem = 0
        self.chamadas_detalhe = 0
        self.metodos = []
        self.tokens_usados = []

    def __call__(self, metodo, url, **kw):
        self.metodos.append(metodo)
        auth = (kw.get("headers") or {}).get("Authorization", "")
        self.tokens_usados.append(auth)
        assert metodo == "GET", f"MÉTODO PROIBIDO no Tiny: {metodo} {url}"

        itens = [d["listagem"] for d in self.produtos.values()]
        if url.rstrip("/").endswith("/produtos"):
            self.chamadas_listagem += 1
            offset = kw["params"]["offset"]
            limit = kw["params"]["limit"]
            return _resp(200, {"itens": itens[offset:offset + limit],
                               "paginacao": {"limit": limit, "offset": offset, "total": len(itens)}},
                         headers=self.headers_listagem)

        pid = int(url.rsplit("/", 1)[1])
        self.chamadas_detalhe += 1
        return _resp(200, self.produtos[pid]["detalhe"])


@override_settings(TINY_API_BASE_URL="https://api.tiny.example")
class ImportarCatalogoTinyTests(TestCase):
    def setUp(self):
        self.instancia = Instancia.objects.create(nome="EKK Brindes", access_token="tok-1")
        self.produtos = {
            1: {"listagem": _listagem(1), "detalhe": _detalhe(1)},
            2: {"listagem": _listagem(2, gtin="", situacao="I"), "detalhe": _detalhe(2, ncm="", gtin="")},
            3: {"listagem": _listagem(3), "detalhe": _detalhe(3)},
        }
        # não dormir de verdade nos testes; registra as pausas pedidas.
        self.pausas = []
        p = patch.object(cmd.Command, "_dormir", lambda _self, s: self.pausas.append(s))
        p.start()
        self.addCleanup(p.stop)

    def _rodar(self, *args, headers_listagem=None):
        handler = HandlerTiny(self.produtos, headers_listagem=headers_listagem)
        out = StringIO()
        with patch("apps.instancias.tiny_client.requests.request", side_effect=handler):
            call_command("importar_catalogo_tiny", self.instancia.slug, *args, stdout=out)
        return handler, out.getvalue()

    def test_instancia_nao_conectada_recusa(self):
        self.instancia.access_token = ""
        self.instancia.save()
        with self.assertRaises(CommandError):
            self._rodar()

    def test_dry_run_consulta_a_api_mas_nao_grava(self):
        handler, saida = self._rodar("--dry-run")
        self.assertEqual(ProdutoTiny.objects.count(), 0)
        self.assertGreater(handler.chamadas_listagem, 0)
        self.assertEqual(handler.chamadas_detalhe, 3)  # dry-run completo busca detalhe
        self.assertIn("DRY-RUN", saida)
        self.assertIn("Produtos no Tiny (total) .. 3", saida)

    def test_importa_e_faz_upsert_com_campos_da_listagem_e_do_detalhe(self):
        self._rodar()
        self.assertEqual(ProdutoTiny.objects.count(), 3)

        p1 = ProdutoTiny.objects.get(instancia=self.instancia, tiny_id=1)
        self.assertEqual(p1.sku, "SKU-1")
        self.assertEqual(p1.descricao, "Produto 1")
        self.assertEqual(p1.situacao, "A")
        self.assertEqual(p1.gtin, "7890000000001")   # listagem
        self.assertEqual(p1.ncm, "73239300")          # só no detalhe
        self.assertEqual(p1.origem, "0")              # só no detalhe
        self.assertEqual(p1.marca, "Marca X")         # só no detalhe
        self.assertEqual(p1.marca_id, 7)
        self.assertEqual(p1.categoria, "Casa >> Copos")
        self.assertEqual(p1.altura, 12.0)
        self.assertEqual(p1.peso_liquido, 0.15)
        self.assertEqual(p1.estoque_quantidade, 42.0)
        self.assertEqual(p1.preco, Decimal("11"))
        self.assertTrue(p1.tem_detalhe)
        self.assertIsNotNone(p1.sincronizado_em)
        self.assertTrue(p1.hash_conteudo)
        self.assertEqual(p1.payload_bruto["listagem"]["id"], 1)
        self.assertIn("detalhe", p1.payload_bruto)

    def test_idempotente_nao_duplica_e_nao_rebusca_detalhe(self):
        self._rodar()
        handler2, saida2 = self._rodar()

        self.assertEqual(ProdutoTiny.objects.count(), 3)
        self.assertEqual(handler2.chamadas_detalhe, 0)  # dataAlteracao igual -> pula o GET /produtos/{id}
        self.assertIn("inalterados ............. 3", saida2)

    def test_produto_alterado_no_tiny_e_reprocessado(self):
        self._rodar()
        # muda dataAlteracao + preço do produto 2
        self.produtos[2]["listagem"] = _listagem(2, gtin="", situacao="I", dataAlteracao="2026-09-09 09:09:09", precos={"preco": 999.0})
        self.produtos[2]["detalhe"] = _detalhe(2, ncm="", gtin="", precos={"preco": 999.0})

        handler2, saida2 = self._rodar()
        self.assertEqual(handler2.chamadas_detalhe, 1)  # só o alterado
        p2 = ProdutoTiny.objects.get(instancia=self.instancia, tiny_id=2)
        self.assertEqual(p2.preco, Decimal("999"))
        self.assertIn("atualizados ............. 1", saida2)
        self.assertIn("inalterados ............. 2", saida2)

    def test_retomavel_processa_so_o_que_falta(self):
        # já existe o produto 1 no espelho, idêntico ao que o Tiny devolve
        handler0 = HandlerTiny(self.produtos)
        with patch("apps.instancias.tiny_client.requests.request", side_effect=handler0):
            call_command("importar_catalogo_tiny", self.instancia.slug, "--limite", "1", stdout=StringIO())
        self.assertEqual(ProdutoTiny.objects.count(), 1)

        handler1, saida1 = self._rodar()
        self.assertEqual(ProdutoTiny.objects.count(), 3)
        self.assertEqual(handler1.chamadas_detalhe, 2)  # só os 2 que faltavam
        self.assertIn("inalterados ............. 1", saida1)
        self.assertIn("novos ................... 2", saida1)

    def test_sem_detalhe_nao_chama_o_endpoint_de_detalhe(self):
        handler, _ = self._rodar("--sem-detalhe")
        self.assertEqual(handler.chamadas_detalhe, 0)
        p1 = ProdutoTiny.objects.get(instancia=self.instancia, tiny_id=1)
        self.assertEqual(p1.sku, "SKU-1")
        self.assertEqual(p1.ncm, "")       # detalhe não foi buscado
        self.assertEqual(p1.origem, "")
        self.assertFalse(p1.tem_detalhe)

    def test_limite_processa_no_maximo_n(self):
        handler, saida = self._rodar("--limite", "2")
        self.assertEqual(ProdutoTiny.objects.count(), 2)
        self.assertEqual(handler.chamadas_detalhe, 2)
        self.assertIn("Processados nesta execução  2", saida)

    def test_paginacao_faz_varias_chamadas_de_listagem(self):
        handler = HandlerTiny(self.produtos, page_size=2)
        with patch("apps.instancias.tiny_client.requests.request", side_effect=handler):
            call_command("importar_catalogo_tiny", self.instancia.slug, "--page-size", "2", stdout=StringIO())
        self.assertEqual(handler.chamadas_listagem, 2)  # total 3, page 2 -> 2 páginas
        self.assertEqual(ProdutoTiny.objects.count(), 3)

    def test_situacao_e_repassada_como_filtro(self):
        capturados = []
        handler = HandlerTiny(self.produtos)
        orig = handler.__call__

        def espiao(metodo, url, **kw):
            if url.rstrip("/").endswith("/produtos"):
                capturados.append(dict(kw["params"]))
            return orig(metodo, url, **kw)

        with patch("apps.instancias.tiny_client.requests.request", side_effect=espiao):
            call_command("importar_catalogo_tiny", self.instancia.slug, "--situacao", "A", "--dry-run", stdout=StringIO())
        self.assertTrue(all(p.get("situacao") == "A" for p in capturados))

    def test_nunca_usa_metodo_de_escrita_no_tiny(self):
        # o HandlerTiny já levanta AssertionError se method != GET; reforço:
        with patch("apps.instancias.tiny_client.TinyApiClient.post", side_effect=AssertionError("POST no Tiny!")):
            handler, _ = self._rodar()
        self.assertEqual(set(handler.metodos), {"GET"})

    def test_recarrega_token_no_meio_da_carga_longa(self):
        handler = HandlerTiny(self.produtos)

        chamadas = {"n": 0}
        orig = handler.__call__

        def troca_token(metodo, url, **kw):
            chamadas["n"] += 1
            if chamadas["n"] == 2:
                Instancia.objects.filter(pk=self.instancia.pk).update(access_token="tok-NOVO")
            return orig(metodo, url, **kw)

        with patch.object(cmd, "INTERVALO_REFRESH_TOKEN", 1), \
             patch("apps.instancias.tiny_client.requests.request", side_effect=troca_token):
            call_command("importar_catalogo_tiny", self.instancia.slug, stdout=StringIO())

        self.assertTrue(any("tok-NOVO" in t for t in handler.tokens_usados))

    def test_resumo_conta_gtin_ncm_e_situacao(self):
        _, saida = self._rodar()
        self.assertIn("Com GTIN .................. 2", saida)   # produto 2 tem gtin=""
        self.assertIn("Com NCM (do detalhe) ..... 2", saida)   # produto 2 tem ncm=""
        self.assertIn("Situação A / I / E / outra . 2 / 1 / 0 / 0", saida)


# ---------------------------------------------------------------------------
# Rate limit / ritmo das chamadas de detalhe
# ---------------------------------------------------------------------------


@override_settings(TINY_API_BASE_URL="https://api.tiny.example")
class RitmoDetalheTests(TestCase):
    def setUp(self):
        self.instancia = Instancia.objects.create(nome="EKK Brindes", access_token="tok-1")
        self.produtos = {i: {"listagem": _listagem(i), "detalhe": _detalhe(i)} for i in (1, 2, 3)}
        self.pausas = []
        p = patch.object(cmd.Command, "_dormir", lambda _self, s: self.pausas.append(s))
        p.start()
        self.addCleanup(p.stop)

    def _rodar(self, *args, headers_listagem=None):
        handler = HandlerTiny(self.produtos, headers_listagem=headers_listagem)
        out = StringIO()
        with patch("apps.instancias.tiny_client.requests.request", side_effect=handler):
            call_command("importar_catalogo_tiny", self.instancia.slug, *args, stdout=out)
        return handler, out.getvalue()

    def _pausas_significativas(self):
        return [p for p in self.pausas if p > 0.01]

    def test_rpm_detalhe_explicito_espaca_uniformemente_sem_rajada(self):
        handler, saida = self._rodar("--rpm-detalhe", "60")  # 1 chamada/s
        self.assertEqual(handler.chamadas_detalhe, 3)
        pausas = self._pausas_significativas()
        self.assertEqual(len(pausas), 2)  # 1ª chamada sem espera; as 2 seguintes esperam
        for pausa in pausas:
            self.assertAlmostEqual(pausa, 1.0, delta=0.4)
        self.assertIn("Ritmo do detalhe .......... 60/min", saida)

    def test_ritmo_padrao_vem_de_metade_do_x_limit_api(self):
        # x-limit-api = 20 -> limiter usa 16 (0.8); a carga usa 10 (0.5) -> 6s/chamada
        _, saida = self._rodar(headers_listagem={"x-limit-api": "20"})
        self.assertIn("Ritmo do detalhe .......... 10/min", saida)
        for pausa in self._pausas_significativas():
            self.assertAlmostEqual(pausa, 6.0, delta=1.0)

    def test_ritmo_padrao_conservador_enquanto_limite_desconhecido(self):
        _, saida = self._rodar()  # sem x-limit-api
        self.assertIn(f"Ritmo do detalhe .......... {cmd.RPM_DETALHE_PADRAO}/min", saida)

    def test_nao_espaca_quando_nao_ha_chamada_de_detalhe(self):
        self._rodar("--sem-detalhe")
        self.assertEqual(self._pausas_significativas(), [])

    def test_nao_reespaça_itens_pulados_por_dataAlteracao(self):
        self._rodar("--rpm-detalhe", "60")            # 1ª carga: 3 detalhes, 2 pausas
        self.pausas.clear()
        handler2, _ = self._rodar("--rpm-detalhe", "60")  # 2ª: nada mudou -> 0 detalhe
        self.assertEqual(handler2.chamadas_detalhe, 0)
        self.assertEqual(self._pausas_significativas(), [])

    def test_429_persistente_para_com_progresso_salvo_e_e_retomavel(self):
        from apps.instancias.tiny_client import TinyApiError

        class HandlerCom429(HandlerTiny):
            def __call__(self, metodo, url, **kw):
                if not url.rstrip("/").endswith("/produtos") and self.chamadas_detalhe >= 1:
                    # o 2º GET /produtos/{id} em diante: 429 sem Retry-After
                    self.chamadas_detalhe += 1
                    raise TinyApiError("429 persistente após 5 tentativas em '/produtos/2'.")
                return super().__call__(metodo, url, **kw)

        handler = HandlerCom429(self.produtos)
        out = StringIO()
        with patch("apps.instancias.tiny_client.requests.request", side_effect=handler):
            with self.assertRaises(CommandError):
                call_command("importar_catalogo_tiny", self.instancia.slug, "--rpm-detalhe", "60", stdout=out)

        # o 1º produto foi salvo antes do 429
        self.assertEqual(ProdutoTiny.objects.filter(instancia=self.instancia).count(), 1)
        self.assertIn("Carga interrompida", out.getvalue())
        self.assertIn("Rode o MESMO comando", out.getvalue())

    def test_erro_de_validacao_no_meio_propaga_sem_virar_retomavel(self):
        from apps.instancias.tiny_client import TinyApiValidationError

        class HandlerComValidacao(HandlerTiny):
            def __call__(self, metodo, url, **kw):
                if not url.rstrip("/").endswith("/produtos"):
                    raise TinyApiValidationError("produto não encontrado", [])
                return super().__call__(metodo, url, **kw)

        handler = HandlerComValidacao(self.produtos)
        with patch("apps.instancias.tiny_client.requests.request", side_effect=handler):
            with self.assertRaises(TinyApiValidationError):
                call_command("importar_catalogo_tiny", self.instancia.slug, stdout=StringIO())
