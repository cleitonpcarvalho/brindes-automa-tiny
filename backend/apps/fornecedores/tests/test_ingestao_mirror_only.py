"""
Ingestão manual "espelho apenas" (fornecedor -> PostgreSQL), via
`importar_fornecedor --mirror-only`.

O foco destes testes é provar que a operação NÃO toca o Tiny e respeita os
limites pedidos (uma instância, um fornecedor, sem cadência), além das
regras de negócio já existentes e da observabilidade (Execucao/LogItem).
"""

from copy import deepcopy
from decimal import Decimal
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.catalogo.models import Produto, StatusVariacao, Variacao
from apps.fornecedores.models import CadenciaFornecedor, ConfiguracaoFornecedor
from apps.instancias.models import CredencialFornecedor, Instancia
from apps.instancias.tiny_client import TinyApiClient
from apps.sincronizacao.models import Execucao, LogItem, NivelLog, StatusExecucao

from .fixtures import SOMARCAS_ITEM_COM_ESTOQUE, XBZ_GRUPO_06520, XBZ_GRUPO_P12288


def _instancia(nome):
    return Instancia.objects.create(nome=nome)


def _credencial(instancia, fornecedor, credenciais=None):
    return CredencialFornecedor.objects.create(
        instancia=instancia,
        fornecedor=fornecedor,
        credenciais=credenciais or {"usuario": "u", "senha": "s"},
        ativo=True,
    )


def _somarcas(**overrides):
    item = deepcopy(SOMARCAS_ITEM_COM_ESTOQUE)
    item.update(overrides)
    return item


class MirrorOnlyObrigatorioTests(TestCase):
    def setUp(self):
        self.instancia = _instancia("EKK Brindes")
        _credencial(self.instancia, "somarcas")

    @patch("apps.fornecedores.somarcas.SomarcasFornecedor.buscar")
    def test_sem_a_flag_recusa_e_nao_cria_nada(self, mock_buscar):
        mock_buscar.return_value = [_somarcas()]
        with self.assertRaises(CommandError):
            call_command("importar_fornecedor", self.instancia.slug, "somarcas")

        mock_buscar.assert_not_called()
        self.assertEqual(Execucao.objects.count(), 0)
        self.assertEqual(Produto.objects.count(), 0)
        self.assertEqual(Variacao.objects.count(), 0)

    @patch("apps.fornecedores.somarcas.SomarcasFornecedor.buscar")
    def test_com_a_flag_roda(self, mock_buscar):
        mock_buscar.return_value = [_somarcas()]
        call_command("importar_fornecedor", self.instancia.slug, "somarcas", "--mirror-only")
        self.assertEqual(Produto.objects.count(), 1)


class MirrorOnlyNaoEscreveNoTinyTests(TestCase):
    """A evidência central: nenhum método do TinyApiClient é chamado."""

    def setUp(self):
        self.instancia = _instancia("EKK Brindes")
        _credencial(self.instancia, "somarcas")

    @patch("apps.fornecedores.somarcas.SomarcasFornecedor.buscar")
    def test_ingestao_completa_sem_nenhuma_chamada_ao_tiny(self, mock_buscar):
        mock_buscar.return_value = [
            _somarcas(codigo="AS-1", estoque=10),
            _somarcas(codigo="AS-2", estoque=0),
        ]

        estoura = lambda *a, **k: (_ for _ in ()).throw(AssertionError("chamou o Tiny!"))  # noqa: E731
        with patch.object(TinyApiClient, "__init__", estoura), \
             patch.object(TinyApiClient, "buscar_produto_por_sku", estoura), \
             patch.object(TinyApiClient, "criar_produto", estoura), \
             patch.object(TinyApiClient, "atualizar_estoque", estoura), \
             patch.object(TinyApiClient, "post", estoura), \
             patch.object(TinyApiClient, "get", estoura):
            call_command("importar_fornecedor", self.instancia.slug, "somarcas", "--mirror-only")

        self.assertEqual(Variacao.objects.count(), 2)
        execucao = Execucao.objects.get()
        self.assertEqual(execucao.status, StatusExecucao.SUCESSO)

    def test_o_comando_nao_importa_o_cliente_do_tiny(self):
        import apps.fornecedores.management.commands.importar_fornecedor as mod

        fonte = open(mod.__file__, encoding="utf-8").read().lower()
        self.assertNotIn("tiny_client", fonte)
        self.assertNotIn("tinyapiclient", fonte)


class MirrorOnlyIsolamentoEUmFornecedorTests(TestCase):
    def setUp(self):
        self.ekk = _instancia("EKK Brindes")
        self.outra = _instancia("Outra Loja")
        _credencial(self.ekk, "somarcas")
        _credencial(self.ekk, "xbz", {"cnpj": "0", "token": "0"})
        _credencial(self.outra, "somarcas")

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    @patch("apps.fornecedores.somarcas.SomarcasFornecedor.buscar")
    def test_so_o_fornecedor_pedido_e_so_a_instancia_pedida(self, mock_somarcas, mock_xbz):
        mock_somarcas.return_value = [_somarcas()]
        mock_xbz.return_value = XBZ_GRUPO_06520

        call_command("importar_fornecedor", self.ekk.slug, "somarcas", "--mirror-only")

        # xbz nunca foi consultado
        mock_xbz.assert_not_called()
        self.assertFalse(Produto.objects.filter(fornecedor="xbz").exists())
        # nada foi gravado na outra instância
        self.assertFalse(Produto.objects.filter(instancia=self.outra).exists())
        self.assertEqual(Produto.objects.filter(instancia=self.ekk, fornecedor="somarcas").count(), 1)
        self.assertEqual(Execucao.objects.filter(instancia=self.ekk, fornecedor="somarcas").count(), 1)
        self.assertEqual(Execucao.objects.exclude(instancia=self.ekk).count(), 0)


class MirrorOnlyPersistenciaERegrasTests(TestCase):
    def setUp(self):
        self.instancia = _instancia("EKK Brindes")
        _credencial(self.instancia, "somarcas")
        _credencial(self.instancia, "xbz", {"cnpj": "0", "token": "0"})

    @patch("apps.fornecedores.somarcas.SomarcasFornecedor.buscar")
    def test_grava_produto_e_variacao_com_preco_do_fornecedor(self, mock_buscar):
        mock_buscar.return_value = [_somarcas()]  # preco_com_gravacao_com_impostos = 21.01
        call_command("importar_fornecedor", self.instancia.slug, "somarcas", "--mirror-only")

        variacao = Variacao.objects.get(sku="AS-00610")
        self.assertEqual(variacao.produto.instancia, self.instancia)
        self.assertEqual(variacao.preco, Decimal("21.01"))
        self.assertEqual(variacao.preco_venda_tiny, variacao.preco)  # regra nº 4: sem margem
        self.assertEqual(variacao.ncm, "76151000")
        self.assertEqual(variacao.estoque, 1788)
        self.assertEqual(variacao.status, StatusVariacao.PENDENTE)

    @patch("apps.fornecedores.somarcas.SomarcasFornecedor.buscar")
    def test_idempotente(self, mock_buscar):
        mock_buscar.return_value = [_somarcas()]
        call_command("importar_fornecedor", self.instancia.slug, "somarcas", "--mirror-only")
        call_command("importar_fornecedor", self.instancia.slug, "somarcas", "--mirror-only")

        self.assertEqual(Produto.objects.count(), 1)
        self.assertEqual(Variacao.objects.count(), 1)
        segunda = Execucao.objects.order_by("-iniciada_em").first()
        self.assertEqual(segunda.total_novos, 0)
        self.assertEqual(segunda.total_ignorados, 1)

    @patch("apps.fornecedores.somarcas.SomarcasFornecedor.buscar")
    def test_estoque_zero_fica_no_espelho_como_aguardando(self, mock_buscar):
        mock_buscar.return_value = [_somarcas(codigo="AS-ZERO", estoque=0)]
        call_command("importar_fornecedor", self.instancia.slug, "somarcas", "--mirror-only")

        variacao = Variacao.objects.get(sku="AS-ZERO")
        self.assertEqual(variacao.status, StatusVariacao.AGUARDANDO)
        # continua rastreada no espelho
        self.assertTrue(Variacao.objects.filter(sku="AS-ZERO").exists())

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_regra_p_arroba_marca_descontinuado_e_fora_da_fila_de_cadastro(self, mock_buscar):
        mock_buscar.return_value = XBZ_GRUPO_P12288
        call_command("importar_fornecedor", self.instancia.slug, "xbz", "--mirror-only")

        produto = Produto.objects.get(codigo_pai="P@12288")
        self.assertTrue(produto.descontinuado)
        variacoes = produto.variacoes.all()
        self.assertTrue(all(v.status == StatusVariacao.DESCONTINUADO for v in variacoes))
        # nenhuma dessas variações seria elegível ao cadastro no Tiny (só PENDENTE é)
        self.assertEqual(
            Variacao.objects.filter(produto__instancia=self.instancia, status=StatusVariacao.PENDENTE).count(),
            0,
        )


class MirrorOnlyObservabilidadeTests(TestCase):
    def setUp(self):
        self.instancia = _instancia("EKK Brindes")
        _credencial(self.instancia, "somarcas")

    @patch("apps.fornecedores.somarcas.SomarcasFornecedor.buscar")
    def test_execucao_e_logitens_da_ingestao(self, mock_buscar):
        mock_buscar.return_value = [
            _somarcas(codigo="AS-A", estoque=5),
            _somarcas(codigo="AS-B", estoque=0),
        ]
        call_command("importar_fornecedor", self.instancia.slug, "somarcas", "--mirror-only")

        execucao = Execucao.objects.get()
        self.assertEqual(execucao.fornecedor, "somarcas")
        self.assertEqual(execucao.status, StatusExecucao.SUCESSO)
        self.assertEqual(execucao.total_lidos, 2)
        self.assertEqual(execucao.total_novos, 2)
        self.assertEqual(execucao.total_erros, 0)
        self.assertIsNotNone(execucao.finalizada_em)

        inicio = execucao.logs.get(mensagem__startswith="Ingestão iniciada")
        self.assertEqual(inicio.nivel, NivelLog.INFO)
        self.assertEqual(inicio.detalhe["modo"], "mirror-only")
        self.assertFalse(inicio.detalhe["escreve_no_tiny"])

        fim = execucao.logs.get(mensagem="Importação concluída")
        self.assertEqual(fim.detalhe["produtos"], 2)
        self.assertEqual(fim.detalhe["lidos"], 2)
        self.assertEqual(fim.detalhe["sem_estoque"], 1)
        self.assertEqual(fim.detalhe["ignorados_regra"], 0)
        self.assertEqual(fim.detalhe["erros"], 0)
        self.assertEqual(LogItem.objects.filter(nivel=NivelLog.ERRO).count(), 0)


class DryRunTests(TestCase):
    def setUp(self):
        self.instancia = _instancia("EKK Brindes")
        _credencial(self.instancia, "somarcas")

    def _rodar_dry_run(self, fornecedor="somarcas", args=()):
        out = StringIO()
        call_command(
            "importar_fornecedor",
            self.instancia.slug,
            fornecedor,
            "--mirror-only",
            "--dry-run",
            *args,
            stdout=out,
        )
        return out.getvalue()

    def test_dry_run_ainda_exige_mirror_only(self):
        with self.assertRaises(CommandError):
            call_command(
                "importar_fornecedor", self.instancia.slug, "somarcas", "--dry-run", stdout=StringIO()
            )

    def test_dry_run_incompativel_com_execucao_id(self):
        with self.assertRaises(CommandError):
            call_command(
                "importar_fornecedor",
                self.instancia.slug,
                "somarcas",
                "--mirror-only",
                "--dry-run",
                execucao_id=1,
                stdout=StringIO(),
            )

    @patch("apps.fornecedores.somarcas.SomarcasFornecedor.normalizar", autospec=True)
    @patch("apps.fornecedores.somarcas.SomarcasFornecedor.buscar")
    def test_dry_run_chama_buscar_e_normalizar(self, mock_buscar, mock_normalizar):
        mock_buscar.return_value = [_somarcas()]
        mock_normalizar.return_value = []
        self._rodar_dry_run()
        mock_buscar.assert_called_once()
        mock_normalizar.assert_called_once()

    @patch("apps.fornecedores.somarcas.SomarcasFornecedor.buscar")
    def test_dry_run_nao_cria_produto_variacao_execucao_logitem(self, mock_buscar):
        mock_buscar.return_value = [_somarcas(codigo="AS-A"), _somarcas(codigo="AS-B", estoque=0)]
        self._rodar_dry_run(args=("--tipo", "carga_inicial"))

        self.assertEqual(Produto.objects.count(), 0)
        self.assertEqual(Variacao.objects.count(), 0)
        self.assertEqual(Execucao.objects.count(), 0)
        self.assertEqual(LogItem.objects.count(), 0)

    @patch("apps.fornecedores.somarcas.SomarcasFornecedor.buscar")
    def test_dry_run_nao_toca_no_tiny(self, mock_buscar):
        mock_buscar.return_value = [_somarcas()]
        estoura = lambda *a, **k: (_ for _ in ()).throw(AssertionError("chamou o Tiny!"))  # noqa: E731
        with patch.object(TinyApiClient, "__init__", estoura), \
             patch.object(TinyApiClient, "get", estoura), \
             patch.object(TinyApiClient, "post", estoura), \
             patch.object(TinyApiClient, "buscar_produto_por_sku", estoura), \
             patch.object(TinyApiClient, "criar_produto", estoura), \
             patch.object(TinyApiClient, "atualizar_estoque", estoura):
            self._rodar_dry_run()

    @patch("apps.fornecedores.somarcas.SomarcasFornecedor.buscar")
    def test_dry_run_nao_altera_cadencia_configuracao_nem_credencial(self, mock_buscar):
        mock_buscar.return_value = [_somarcas()]
        # a credencial do setUp já criou a cadência padrão (signal) — ajusto essa.
        cadencia = CadenciaFornecedor.objects.get(instancia=self.instancia, fornecedor="somarcas")
        cadencia.intervalo_minutos = 180
        cadencia.ativo = False
        cadencia.save()
        cadencia.refresh_from_db()
        cad_touch = cadencia.atualizado_em
        credencial = CredencialFornecedor.objects.get(instancia=self.instancia, fornecedor="somarcas")
        cred_snapshot = (credencial.credenciais, credencial.ativo)

        self._rodar_dry_run()

        cadencia.refresh_from_db()
        self.assertEqual(cadencia.intervalo_minutos, 180)
        self.assertFalse(cadencia.ativo)
        self.assertEqual(cadencia.atualizado_em, cad_touch)
        self.assertEqual(ConfiguracaoFornecedor.objects.count(), 0)
        credencial.refresh_from_db()
        self.assertEqual((credencial.credenciais, credencial.ativo), cred_snapshot)

    @patch("apps.fornecedores.somarcas.SomarcasFornecedor.buscar")
    def test_dry_run_resumo_tem_os_totais_esperados(self, mock_buscar):
        mock_buscar.return_value = [
            _somarcas(codigo="AS-A", estoque=10),  # com estoque, com ncm, com imagem
            _somarcas(codigo="AS-B", estoque=0),  # sem estoque, com ncm, com imagem
            _somarcas(codigo="AS-C", estoque=5, ncm="", url_foto="", matriz_de_fotos_adicionais=""),
        ]
        saida = self._rodar_dry_run(args=("--tipo", "carga_inicial"))

        self.assertIn("DRY-RUN — nada foi gravado", saida)
        self.assertIn("Fornecedor .................. somarcas", saida)
        self.assertIn("Produtos-pai ................ 3", saida)
        self.assertIn("Variações (total) .......... 3", saida)
        self.assertIn("Com estoque (> 0) .......... 2", saida)
        self.assertIn("Sem estoque (<= 0) ......... 1", saida)
        self.assertIn("Descontinuadas por regra ... 0", saida)
        self.assertIn("Com NCM .................... 2", saida)
        self.assertIn("Sem NCM ................... 1", saida)
        self.assertIn("Com imagem ................. 2", saida)
        self.assertIn("Sem imagem ................ 1", saida)
        self.assertIn("Avisos de normalização ..... nenhum", saida)

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_dry_run_conta_regra_p_arroba_da_xbz(self, mock_buscar):
        _credencial(self.instancia, "xbz", {"cnpj": "0", "token": "0"})
        mock_buscar.return_value = XBZ_GRUPO_P12288  # 2 variações, grupo "P@12288"
        saida = self._rodar_dry_run(fornecedor="xbz")

        self.assertIn("Descontinuadas por regra ... 2", saida)
        self.assertEqual(Produto.objects.count(), 0)  # continua sem persistir

    @patch("apps.fornecedores.somarcas.SomarcasFornecedor.buscar")
    def test_mirror_only_sem_dry_run_continua_persistindo(self, mock_buscar):
        mock_buscar.return_value = [_somarcas()]
        call_command("importar_fornecedor", self.instancia.slug, "somarcas", "--mirror-only")

        self.assertEqual(Produto.objects.count(), 1)
        self.assertEqual(Variacao.objects.count(), 1)
        self.assertEqual(Execucao.objects.count(), 1)
