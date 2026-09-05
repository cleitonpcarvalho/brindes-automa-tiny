from unittest.mock import patch

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.catalogo.models import Produto, StatusVariacao, Variacao
from apps.instancias.models import CredencialFornecedor, Instancia
from apps.sincronizacao.models import Execucao, StatusExecucao

from .fixtures import XBZ_GRUPO_06520, XBZ_GRUPO_P12288


class ImportarFornecedorIdempotenciaTests(TestCase):
    """
    Usa o mesmo recorte real da xbz (grupo "06520", 6 cores) para confirmar
    que rodar a importação duas vezes seguidas não duplica nada nem altera
    um status já definido: a segunda rodada deve reconhecer que nada mudou
    (mesmo hash) e contar tudo como ignorado.
    """

    def setUp(self):
        self.instancia = Instancia.objects.create(nome="Loja de Teste")
        CredencialFornecedor.objects.create(
            instancia=self.instancia,
            fornecedor="xbz",
            credenciais={"cnpj": "0", "token": "0"},
            ativo=True,
        )

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_primeira_importacao_cria_produto_e_variacoes(self, mock_buscar):
        mock_buscar.return_value = XBZ_GRUPO_06520
        call_command("importar_fornecedor", self.instancia.slug, "xbz")

        self.assertEqual(Produto.objects.count(), 1)
        self.assertEqual(Variacao.objects.count(), 6)

        execucao = Execucao.objects.get()
        self.assertEqual(execucao.status, StatusExecucao.SUCESSO)
        self.assertEqual(execucao.total_lidos, 6)
        self.assertEqual(execucao.total_novos, 6)
        self.assertEqual(execucao.total_atualizados, 0)
        self.assertEqual(execucao.total_ignorados, 0)

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_rodar_duas_vezes_seguidas_nao_duplica_nada(self, mock_buscar):
        mock_buscar.return_value = XBZ_GRUPO_06520
        call_command("importar_fornecedor", self.instancia.slug, "xbz")
        call_command("importar_fornecedor", self.instancia.slug, "xbz", "--force")

        self.assertEqual(Produto.objects.count(), 1)
        self.assertEqual(Variacao.objects.count(), 6)

        segunda_execucao = Execucao.objects.order_by("-iniciada_em").first()
        self.assertEqual(segunda_execucao.total_novos, 0)
        self.assertEqual(segunda_execucao.total_atualizados, 0)
        self.assertEqual(segunda_execucao.total_ignorados, 6)

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_status_ja_definido_nao_e_alterado_pela_segunda_rodada(self, mock_buscar):
        mock_buscar.return_value = XBZ_GRUPO_06520
        call_command("importar_fornecedor", self.instancia.slug, "xbz")

        variacao = Variacao.objects.get(sku="X000019")
        variacao.status = StatusVariacao.CADASTRADO
        variacao.tiny_id = "999"
        variacao.save()

        call_command("importar_fornecedor", self.instancia.slug, "xbz", "--force")

        variacao.refresh_from_db()
        self.assertEqual(variacao.status, StatusVariacao.CADASTRADO)
        self.assertEqual(variacao.tiny_id, "999")

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_preco_ou_estoque_mudando_conta_como_atualizado_nao_como_novo(self, mock_buscar):
        mock_buscar.return_value = XBZ_GRUPO_06520
        call_command("importar_fornecedor", self.instancia.slug, "xbz")

        grupo_com_reposicao = [dict(linha) for linha in XBZ_GRUPO_06520]
        grupo_com_reposicao[0]["QuantidadeDisponivel"] = 99999
        mock_buscar.return_value = grupo_com_reposicao

        call_command("importar_fornecedor", self.instancia.slug, "xbz", "--force")

        self.assertEqual(Variacao.objects.count(), 6)  # continua sem duplicar
        variacao = Variacao.objects.get(sku="X000019")
        self.assertEqual(variacao.estoque, 99999)

        segunda_execucao = Execucao.objects.order_by("-iniciada_em").first()
        self.assertEqual(segunda_execucao.total_novos, 0)
        self.assertEqual(segunda_execucao.total_atualizados, 1)
        self.assertEqual(segunda_execucao.total_ignorados, 5)

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_segunda_chamada_no_mesmo_dia_e_bloqueada_sem_force(self, mock_buscar):
        mock_buscar.return_value = XBZ_GRUPO_06520
        call_command("importar_fornecedor", self.instancia.slug, "xbz")

        with self.assertRaises(CommandError):
            call_command("importar_fornecedor", self.instancia.slug, "xbz")

        # a checagem falha ANTES de qualquer nova chamada de rede
        self.assertEqual(mock_buscar.call_count, 1)

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_produto_com_prefixo_p_arroba_entra_direto_como_descontinuado(self, mock_buscar):
        mock_buscar.return_value = XBZ_GRUPO_P12288
        call_command("importar_fornecedor", self.instancia.slug, "xbz")

        produto = Produto.objects.get(codigo_pai="P@12288")
        self.assertTrue(produto.descontinuado)
        for variacao in produto.variacoes.all():
            self.assertEqual(variacao.status, StatusVariacao.DESCONTINUADO)
