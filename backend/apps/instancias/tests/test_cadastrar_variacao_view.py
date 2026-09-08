"""
`POST /api/instancias/<slug>/produtos/<id>/cadastro-tiny/` — cadastro
INDIVIDUAL de uma variação no Tiny, pela tela de Produtos.

Reusa o caminho do cadastro em massa (`tiny_sync._processar_variacao`) — os
testes conferem que as MESMAS proteções e o MESMO payload valem aqui.
"""

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from django.utils import timezone
from rest_framework import status

from apps.catalogo.models import Produto, StatusVariacao, Variacao
from apps.instancias.tiny_client import TinyApiValidationError
from apps.sincronizacao.models import Execucao, StatusExecucao, TipoExecucao

from ..models import CredencialFornecedor, Instancia
from .test_views import _client_autenticado

TINY_FORN_ID = 752133514


def _instancia_pronta(**kwargs):
    dados = {
        "nome": "Loja Individual",
        "access_token": "tok",
        "tiny_origem_padrao": 0,
        "tiny_unidade_medida_padrao": "UN",
    }
    dados.update(kwargs)
    return Instancia.objects.create(**dados)


def _variacao(instancia, sku, *, fornecedor="asia", estoque=5, preco="10.00",
              descricao_produto="Descrição rica do produto.", codigo_pai=None,
              com_id_fornecedor=True, **kwargs):
    produto = Produto.objects.create(
        instancia=instancia, fornecedor=fornecedor, codigo_pai=codigo_pai or f"pai-{sku}",
        nome=sku, descricao=descricao_produto,
    )
    variacao = Variacao.objects.create(
        produto=produto, sku=sku, nome=sku, preco=Decimal(preco), estoque=estoque, **kwargs
    )
    if com_id_fornecedor:
        CredencialFornecedor.objects.update_or_create(
            instancia=instancia, fornecedor=fornecedor, defaults={"tiny_fornecedor_id": TINY_FORN_ID}
        )
    return variacao


class CadastrarVariacaoViewTests(TestCase):
    def setUp(self):
        self.client = _client_autenticado()
        self.instancia = _instancia_pronta()

    def _url(self, variacao):
        return f"/api/instancias/{self.instancia.slug}/produtos/{variacao.id}/cadastro-tiny/"

    # -- sucesso ------------------------------------------------------------

    @patch("apps.instancias.tiny_client.TinyApiClient.sincronizar_anexos_produto", return_value={})
    @patch("apps.instancias.tiny_client.TinyApiClient.anexos_do_produto", return_value=[])
    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_sucesso_cadastra_com_o_mesmo_payload_do_fluxo_em_massa_e_sincroniza_imagens(
        self, _mb, mock_criar, _ma, mock_anexos
    ):
        v = _variacao(self.instancia, "SKU-OK", preco="19.90", imagens=["http://img/a.jpg"])
        mock_criar.return_value = {"id": 5, "sku": "SKU-OK"}

        resp = self.client.post(self._url(v))

        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data["status"], "cadastrado")
        self.assertEqual(resp.data["tiny_id"], "5")

        payload = mock_criar.call_args[0][0]
        self.assertEqual(payload["sku"], "SKU-OK")
        self.assertEqual(
            payload["precos"], {"preco": 0.0, "precoPromocional": 0, "precoCusto": 19.90}
        )
        self.assertEqual(payload["descricaoComplementar"], "Descrição rica do produto.")
        self.assertEqual(payload["fornecedores"], [
            {"id": TINY_FORN_ID, "codigoProdutoNoFornecedor": "SKU-OK", "padrao": True}
        ])
        # imagens sincronizadas na MESMA unidade de trabalho, logo após criar
        mock_anexos.assert_called_once_with(5, ["http://img/a.jpg"])

        v.refresh_from_db()
        self.assertEqual(v.status, StatusVariacao.CADASTRADO)
        self.assertEqual(v.tiny_id, "5")
        self.assertEqual(v.preco_custo_tiny_sincronizado, Decimal("19.90"))

    # -- bloqueios (mesmas regras do cadastro em massa) --------------------

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_bloqueia_estoque_zero(self, _mb, mock_criar):
        v = _variacao(self.instancia, "SKU-ZERO", estoque=0)  # save() -> aguardando

        resp = self.client.post(self._url(v))

        self.assertEqual(resp.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertIn("estoque", resp.data["detail"].lower())
        mock_criar.assert_not_called()

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_bloqueia_regra_p_arroba_da_xbz(self, _mb, mock_criar):
        v = _variacao(self.instancia, "SKU-PA", fornecedor="xbz", codigo_pai="P@123")

        resp = self.client.post(self._url(v))

        self.assertEqual(resp.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertIn("P@", resp.data["detail"])
        mock_criar.assert_not_called()

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku")
    def test_bloqueia_sku_ja_existente_no_tiny_sem_vincular(self, mock_buscar, mock_criar):
        v = _variacao(self.instancia, "SKU-EXISTE")
        mock_buscar.return_value = {"id": 999, "sku": "SKU-EXISTE"}

        resp = self.client.post(self._url(v))

        self.assertEqual(resp.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertIn("já existe no Tiny", resp.data["detail"])
        mock_criar.assert_not_called()
        v.refresh_from_db()
        self.assertEqual(v.status, StatusVariacao.PENDENTE)
        self.assertIsNone(v.tiny_id)

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_bloqueia_colisao_de_sku_entre_fornecedores(self, _mb, mock_criar):
        v = _variacao(self.instancia, "SKU-DUP", fornecedor="asia")
        _variacao(self.instancia, "SKU-DUP", fornecedor="xbz")  # mesmo SKU, outro fornecedor

        resp = self.client.post(self._url(v))

        self.assertEqual(resp.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertIn("mais de um fornecedor", resp.data["detail"])
        mock_criar.assert_not_called()

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    def test_bloqueia_sem_id_do_fornecedor_no_tiny_configurado(self, mock_criar):
        v = _variacao(self.instancia, "SKU-SEM-FORN", com_id_fornecedor=False)

        resp = self.client.post(self._url(v))

        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("ID do fornecedor no Tiny", resp.data["detail"])
        mock_criar.assert_not_called()

    # -- duplicidade -----------------------------------------------------

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_ja_cadastrada_devolve_409_e_nao_reenvia(self, _mb, mock_criar):
        v = _variacao(self.instancia, "SKU-FEITO")
        Variacao.objects.filter(pk=v.pk).update(
            status=StatusVariacao.CADASTRADO, tiny_id="77"
        )

        resp = self.client.post(self._url(v))

        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("já está cadastrado", resp.data["detail"])
        mock_criar.assert_not_called()

    # -- erro (não mascarado) ------------------------------------------------

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    @patch("apps.instancias.tiny_client.TinyApiClient.buscar_produto_por_sku", return_value=None)
    def test_erro_do_tiny_nao_e_mascarado_e_a_linha_fica_com_status_erro(self, _mb, mock_criar):
        v = _variacao(self.instancia, "SKU-ERR")
        mock_criar.side_effect = TinyApiValidationError("O campo NCM é obrigatório")

        resp = self.client.post(self._url(v))

        self.assertEqual(resp.status_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        self.assertIn("NCM é obrigatório", resp.data["detail"])
        v.refresh_from_db()
        self.assertEqual(v.status, StatusVariacao.ERRO)
        self.assertIn("NCM", v.ultimo_erro)

    # -- concorrência / massa / isolamento --------------------------------

    @patch("apps.instancias.tiny_client.TinyApiClient.criar_produto")
    def test_409_quando_ha_sincronizacao_em_massa_ativa_do_fornecedor(self, mock_criar):
        v = _variacao(self.instancia, "SKU-MASSA", fornecedor="asia")
        Execucao.objects.create(
            instancia=self.instancia, fornecedor="asia", tipo=TipoExecucao.CADASTRO_TINY,
            status=StatusExecucao.RODANDO, heartbeat_em=timezone.now(),
        )

        resp = self.client.post(self._url(v))

        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertIn("sincronização em massa", resp.data["detail"])
        mock_criar.assert_not_called()

    def test_instancia_nao_conectada_devolve_400(self):
        instancia = Instancia.objects.create(nome="Desconectada")
        v = _variacao(instancia, "SKU-X")
        resp = self.client.post(f"/api/instancias/{instancia.slug}/produtos/{v.id}/cadastro-tiny/")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_variacao_de_outra_instancia_devolve_404(self):
        outra = _instancia_pronta(nome="Outra")
        v_outra = _variacao(outra, "SKU-OUTRA")
        resp = self.client.post(
            f"/api/instancias/{self.instancia.slug}/produtos/{v_outra.id}/cadastro-tiny/"
        )
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_exige_autenticacao(self):
        from rest_framework.test import APIClient

        v = _variacao(self.instancia, "SKU-AUTH")
        resp = APIClient().post(self._url(v))
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)
