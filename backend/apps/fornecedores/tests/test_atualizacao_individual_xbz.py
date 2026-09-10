from copy import deepcopy
from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.utils import timezone
from rest_framework.authtoken.models import Token
from rest_framework.test import APIClient

from apps.catalogo.models import Produto, StatusVariacao, Variacao
from apps.fornecedores.base import ProdutoNormalizado, VariacaoNormalizada
from apps.fornecedores.models import (
    AtualizacaoVariacaoFornecedor,
    StatusAtualizacaoVariacao,
)
from apps.fornecedores.services import atualizar_variacao_do_fornecedor
from apps.fornecedores.tasks import atualizar_variacao_fornecedor_task
from apps.instancias.constants import Fornecedor
from apps.instancias.models import CredencialFornecedor, Instancia
from apps.sincronizacao.models import Execucao, StatusExecucao, TipoExecucao

from .fixtures import XBZ_GRUPO_06520


class AtualizacaoIndividualXbzTests(TestCase):
    def setUp(self):
        # Carrega o módulo do comando antes dos patches dos testes. O serviço
        # importa Command sob demanda e o comando, por sua vez, captura o
        # registry no import; importar dentro de um patch contaminaria outros
        # testes no mesmo processo.
        from apps.fornecedores.management.commands.importar_fornecedor import Command

        self.command_class = Command
        self.instancia = Instancia.objects.create(nome="Loja XBZ individual")
        CredencialFornecedor.objects.create(
            instancia=self.instancia,
            fornecedor=Fornecedor.XBZ,
            credenciais={"cnpj": "0", "token": "0"},
            ativo=True,
        )

        self.linha_alvo = deepcopy(XBZ_GRUPO_06520[0])
        self.linha_alvo.update(
            {
                "CodigoAmigavel": "08765",
                "CodigoXbz": "X134260",
                "CodigoComposto": "08765-ROX",
                "Nome": "GARRAFA DE VIDRO 470ML",
                "PrecoVenda": 22.5,
                "QuantidadeDisponivel": 31,
                "CorWebPrincipal": "ROXO",
            }
        )
        self.linha_irma = deepcopy(XBZ_GRUPO_06520[1])
        self.linha_irma.update(
            {
                "CodigoAmigavel": "08765",
                "CodigoXbz": "X134261",
                "CodigoComposto": "08765-AZU",
                "Nome": "GARRAFA DE VIDRO 470ML",
            }
        )
        self.execucao = Execucao.objects.create(
            instancia=self.instancia,
            fornecedor=Fornecedor.XBZ,
            tipo=TipoExecucao.INCREMENTAL,
        )
        self.produto = Produto.objects.create(
            instancia=self.instancia,
            fornecedor=Fornecedor.XBZ,
            codigo_pai="08765",
            nome="Garrafa antiga",
            payload_bruto={"linhas": [self.linha_alvo, self.linha_irma]},
        )
        self.variacao = Variacao.objects.create(
            produto=self.produto,
            sku="X134260",
            nome="Nome antigo",
            preco="1.00",
            estoque=1,
            atributos={"codigo_composto": "08765-ROX"},
            payload_bruto={"estado": "anterior"},
            status=StatusVariacao.CADASTRADO,
            tiny_id="123",
        )
        self.irma = Variacao.objects.create(
            produto=self.produto,
            sku="X134261",
            nome="Irmã inalterada",
            preco="7.00",
            estoque=7,
            atributos={"codigo_composto": "08765-AZU"},
            payload_bruto={"estado": "irma"},
        )
        self.execucao.status = StatusExecucao.SUCESSO
        self.execucao.finalizada_em = timezone.now()
        self.execucao.save(update_fields=["status", "finalizada_em"])

    def _snapshot_irma(self):
        return Variacao.objects.filter(pk=self.irma.pk).values().get()

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_importada_hoje_reprocessa_cache_sem_chamada_e_so_altera_alvo(self, buscar):
        snapshot_irma = self._snapshot_irma()
        produto_atualizado_em = self.produto.atualizado_em

        atualizada = atualizar_variacao_do_fornecedor(self.instancia, self.variacao)

        buscar.assert_not_called()
        atualizada.refresh_from_db()
        self.produto.refresh_from_db()
        self.assertEqual(atualizada.pk, self.variacao.pk)
        self.assertEqual(atualizada.sku, "X134260")
        self.assertEqual(atualizada.atributos["codigo_composto"], "08765-ROX")
        self.assertEqual(atualizada.nome, "GARRAFA DE VIDRO 470ML")
        self.assertEqual(atualizada.preco, Decimal("22.50"))
        self.assertEqual(atualizada.estoque, 31)
        self.assertEqual(atualizada.tiny_id, "123")
        self.assertEqual(self._snapshot_irma(), snapshot_irma)
        self.assertEqual(self.produto.atualizado_em, produto_atualizado_em)

    @patch("apps.fornecedores.services.checar_limite_diario_xbz")
    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_atualizacao_individual_nao_usa_force_nem_a_trava_da_importacao(
        self, buscar, checar_limite
    ):
        atualizar_variacao_do_fornecedor(self.instancia, self.variacao)

        buscar.assert_not_called()
        checar_limite.assert_not_called()

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_sem_cache_comprovado_exige_importacao_explicita_sem_consumir_cota(self, buscar):
        self.execucao.delete()
        estado_anterior = Variacao.objects.filter(pk=self.variacao.pk).values().get()

        with self.assertRaisesRegex(ValueError, "nenhuma chamada à API foi consumida"):
            atualizar_variacao_do_fornecedor(self.instancia, self.variacao)

        buscar.assert_not_called()
        self.assertEqual(
            Variacao.objects.filter(pk=self.variacao.pk).values().get(), estado_anterior
        )

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_cache_sem_a_variacao_alvo_nao_corrompe_dados(self, buscar):
        self.produto.payload_bruto = {"linhas": [self.linha_irma]}
        self.produto.save(update_fields=["payload_bruto", "atualizado_em"])
        estado_anterior = Variacao.objects.filter(pk=self.variacao.pk).values().get()

        with self.assertRaisesRegex(ValueError, "não há cache atual comprovado"):
            atualizar_variacao_do_fornecedor(self.instancia, self.variacao)

        buscar.assert_not_called()
        self.assertEqual(
            Variacao.objects.filter(pk=self.variacao.pk).values().get(), estado_anterior
        )

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_task_e_status_http_terminam_em_sucesso(self, buscar):
        operacao = AtualizacaoVariacaoFornecedor.objects.create(
            instancia=self.instancia,
            variacao=self.variacao,
            fornecedor=Fornecedor.XBZ,
        )

        atualizar_variacao_fornecedor_task.run(operacao.id)

        buscar.assert_not_called()
        operacao.refresh_from_db()
        self.assertEqual(operacao.status, StatusAtualizacaoVariacao.SUCESSO)
        self.assertEqual(operacao.erro, "")
        resposta = self._client_autenticado().get(self._url_status(operacao))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.data["status"], StatusAtualizacaoVariacao.SUCESSO)

    @patch("apps.fornecedores.xbz.XbzFornecedor.buscar")
    def test_task_e_status_http_expoem_erro_sem_cache(self, buscar):
        self.execucao.delete()
        operacao = AtualizacaoVariacaoFornecedor.objects.create(
            instancia=self.instancia,
            variacao=self.variacao,
            fornecedor=Fornecedor.XBZ,
        )

        atualizar_variacao_fornecedor_task.run(operacao.id)

        buscar.assert_not_called()
        operacao.refresh_from_db()
        self.assertEqual(operacao.status, StatusAtualizacaoVariacao.ERRO)
        self.assertIn("não oferece consulta individual", operacao.erro)
        resposta = self._client_autenticado().get(self._url_status(operacao))
        self.assertEqual(resposta.status_code, 200)
        self.assertEqual(resposta.data["status"], StatusAtualizacaoVariacao.ERRO)
        self.assertIn("não oferece consulta individual", resposta.data["erro"])

    def _client_autenticado(self):
        usuario = get_user_model().objects.create_user(
            email=f"operador-{self.id()}@example.com", password="x"
        )
        token = Token.objects.create(user=usuario)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Token {token.key}")
        return client

    def _url_status(self, operacao):
        return (
            f"/api/instancias/{self.instancia.slug}/produtos/{self.variacao.id}/"
            f"atualizar-fornecedor/{operacao.id}/"
        )


class AtualizacaoIndividualOutrosFornecedoresTests(TestCase):
    def setUp(self):
        from apps.fornecedores.management.commands.importar_fornecedor import Command

        self.command_class = Command

    def _criar_variacao(self, fornecedor):
        instancia = Instancia.objects.create(nome=f"Loja {fornecedor}")
        CredencialFornecedor.objects.create(
            instancia=instancia,
            fornecedor=fornecedor,
            credenciais={"credencial": fornecedor},
            ativo=True,
        )
        produto = Produto.objects.create(
            instancia=instancia,
            fornecedor=fornecedor,
            codigo_pai=f"PAI-{fornecedor}",
            nome="Produto antigo",
        )
        variacao = Variacao.objects.create(
            produto=produto,
            sku=f"SKU-{fornecedor}",
            nome="Variação antiga",
            preco="1.00",
            estoque=1,
            payload_bruto={"estado": "anterior"},
        )
        return instancia, produto, variacao

    @patch("apps.fornecedores.registry.obter_cliente")
    def test_asia_somarcas_e_spot_mantem_busca_e_persistencia_seletiva(self, obter_cliente):
        for fornecedor in (Fornecedor.ASIA, Fornecedor.SOMARCAS, Fornecedor.SPOT):
            with self.subTest(fornecedor=fornecedor):
                instancia, produto, variacao = self._criar_variacao(fornecedor)
                cliente = MagicMock()
                payload = {"catalogo": fornecedor}
                cliente.buscar.return_value = payload
                cliente.normalizar.return_value = [
                    ProdutoNormalizado(
                        codigo_pai=produto.codigo_pai,
                        nome="Produto atualizado",
                        variacoes=[
                            VariacaoNormalizada(
                                sku=variacao.sku,
                                nome="Variação atualizada",
                                preco=Decimal("9.90"),
                                estoque=9,
                                payload_bruto={"estado": "novo"},
                            )
                        ],
                    )
                ]
                obter_cliente.return_value = cliente

                atualizar_variacao_do_fornecedor(instancia, variacao)

                cliente.buscar.assert_called_once_with({"credencial": fornecedor})
                cliente.normalizar.assert_called_once_with(payload)
                variacao.refresh_from_db()
                self.assertEqual(variacao.nome, "Variação atualizada")
                self.assertEqual(variacao.preco, Decimal("9.90"))
                self.assertEqual(variacao.estoque, 9)

    @patch("apps.fornecedores.registry.obter_cliente")
    def test_falha_da_api_externa_nao_altera_variacao(self, obter_cliente):
        instancia, _produto, variacao = self._criar_variacao(Fornecedor.ASIA)
        cliente = MagicMock()
        cliente.buscar.side_effect = ValueError("API indisponível")
        obter_cliente.return_value = cliente
        estado_anterior = Variacao.objects.filter(pk=variacao.pk).values().get()

        with self.assertRaisesRegex(ValueError, "API indisponível"):
            atualizar_variacao_do_fornecedor(instancia, variacao)

        self.assertEqual(Variacao.objects.filter(pk=variacao.pk).values().get(), estado_anterior)
