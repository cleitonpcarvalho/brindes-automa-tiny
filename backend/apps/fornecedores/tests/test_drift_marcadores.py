"""
Detecção de drift no espelho: quando a importação incremental muda um campo
que o Tiny já tem de um SKU JÁ cadastrado, o marcador correspondente é zerado
para a propagação automática reenviar SÓ o que precisa. Sem mudança, nada é
tocado.

  - estoque / custo  -> detectados por comparação direta (sem reset aqui);
  - descrição (= descricaoComplementar) / ncm / dimensões -> zera
    `dados_tiny_sincronizados_em`;
  - imagens -> zera `imagens_tiny_sincronizadas`.
"""

from copy import deepcopy
from decimal import Decimal
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.catalogo.models import StatusVariacao, Variacao
from apps.instancias.models import CredencialFornecedor, Instancia

from .fixtures import SOMARCAS_ITEM_COM_ESTOQUE


def _item(**over):
    it = deepcopy(SOMARCAS_ITEM_COM_ESTOQUE)
    it.update(over)
    return it


class DriftMarcadoresTests(TestCase):
    def setUp(self):
        self.instancia = Instancia.objects.create(nome="Loja")
        CredencialFornecedor.objects.create(
            instancia=self.instancia, fornecedor="somarcas", credenciais={"u": "x"}, ativo=True
        )

    def _importar(self, itens):
        with patch("apps.fornecedores.somarcas.SomarcasFornecedor.buscar", return_value=itens):
            call_command("importar_fornecedor", self.instancia.slug, "somarcas", "--mirror-only")

    def _cadastrar_no_espelho(self, sku):
        """Simula 'já cadastrada no Tiny, tudo em sincronia'."""
        Variacao.objects.filter(sku=sku).update(
            status=StatusVariacao.CADASTRADO,
            tiny_id="900",
            estoque_tiny_sincronizado=Variacao.objects.get(sku=sku).estoque,
            preco_custo_tiny_sincronizado=Variacao.objects.get(sku=sku).preco,
            dados_tiny_sincronizados_em=timezone.now(),
            imagens_tiny_sincronizadas=["https://cdn/antiga.jpg"],
        )
        return Variacao.objects.get(sku=sku)

    def test_reimportacao_sem_mudanca_nao_toca_marcadores(self):
        self._importar([_item()])
        v = self._cadastrar_no_espelho("AS-00610")
        marca = v.dados_tiny_sincronizados_em

        self._importar([_item()])  # idêntico -> hash igual -> 'ignorado'

        v.refresh_from_db()
        self.assertEqual(v.dados_tiny_sincronizados_em, marca)
        self.assertEqual(v.imagens_tiny_sincronizadas, ["https://cdn/antiga.jpg"])
        self.assertEqual(v.estoque_tiny_sincronizado, v.estoque)

    def test_estoque_mudou_fica_detectavel_por_comparacao(self):
        self._importar([_item(estoque=1788)])
        v = self._cadastrar_no_espelho("AS-00610")

        self._importar([_item(estoque=40)])

        v.refresh_from_db()
        self.assertEqual(v.estoque, 40)
        self.assertNotEqual(v.estoque, v.estoque_tiny_sincronizado)  # drift visível

    def test_custo_mudou_fica_detectavel_por_comparacao(self):
        self._importar([_item()])
        v = self._cadastrar_no_espelho("AS-00610")
        custo_antigo = v.preco_custo_tiny_sincronizado

        self._importar([_item(preco_com_gravacao_com_impostos=99.90)])

        v.refresh_from_db()
        self.assertEqual(v.preco, Decimal("99.90"))
        self.assertEqual(v.preco_custo_tiny_sincronizado, custo_antigo)  # não avança sozinho
        self.assertNotEqual(v.preco, v.preco_custo_tiny_sincronizado)

    def test_descricao_mudou_zera_o_marcador_de_dados(self):
        self._importar([_item()])
        v = self._cadastrar_no_espelho("AS-00610")
        self.assertIsNotNone(v.dados_tiny_sincronizados_em)

        self._importar([_item(descricao="Garrafa em alumínio branco — NOVA descrição do fornecedor.")])

        v.refresh_from_db()
        self.assertIsNone(v.dados_tiny_sincronizados_em)
        # não mexeu no marcador de imagem (imagem não mudou)
        self.assertEqual(v.imagens_tiny_sincronizadas, ["https://cdn/antiga.jpg"])

    def test_imagem_mudou_zera_o_marcador_de_imagens(self):
        self._importar([_item()])
        v = self._cadastrar_no_espelho("AS-00610")

        self._importar([_item(url_foto="https://cdn/produtos/garrafa-NOVA.webp")])

        v.refresh_from_db()
        self.assertEqual(v.imagens_tiny_sincronizadas, [])
        self.assertNotEqual(v.imagens, [])

    def test_ncm_mudou_zera_o_marcador_de_dados(self):
        self._importar([_item()])
        v = self._cadastrar_no_espelho("AS-00610")

        self._importar([_item(ncm="76161000")])

        v.refresh_from_db()
        self.assertEqual(v.ncm, "76161000")
        self.assertIsNone(v.dados_tiny_sincronizados_em)

    def test_variacao_pendente_nao_e_afetada_pelo_reset(self):
        self._importar([_item()])
        # NÃO marca como cadastrada — continua PENDENTE
        antes = Variacao.objects.get(sku="AS-00610")
        self.assertIsNone(antes.dados_tiny_sincronizados_em)

        self._importar([_item(descricao="outra", url_foto="https://cdn/x.webp")])

        v = Variacao.objects.get(sku="AS-00610")
        self.assertEqual(v.status, StatusVariacao.PENDENTE)
        self.assertEqual(v.imagens_tiny_sincronizadas, [])  # nunca teve
