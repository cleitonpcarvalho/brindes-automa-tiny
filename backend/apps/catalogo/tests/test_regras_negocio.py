from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase

from apps.instancias.models import Instancia

from ..models import Produto, StatusVariacao, Variacao


def _instancia():
    return Instancia.objects.create(nome="Instância de Teste")


def _produto(instancia, **kwargs):
    dados = {
        "instancia": instancia,
        "fornecedor": "xbz",
        "codigo_pai": "06520",
        "nome": "Caneca Acrílica 400ml",
    }
    dados.update(kwargs)
    return Produto.objects.create(**dados)


def _variacao(produto, **kwargs):
    dados = {
        "produto": produto,
        "sku": "06520-AZU",
        "nome": "Caneca Acrílica 400ml Azul",
        "preco": Decimal("12.90"),
        "estoque": 10,
    }
    dados.update(kwargs)
    return Variacao.objects.create(**dados)


class RegraCadaVariacaoViraProdutoProprioTests(TestCase):
    """
    Regra nº 1 (pedido explícito do cliente): cada cor ou tamanho é uma
    Variacao própria e vira um produto separado no Tiny.
    """

    def test_cada_cor_gera_uma_variacao_independente_com_ciclo_de_vida_proprio(self):
        instancia = _instancia()
        produto = _produto(instancia)

        azul = _variacao(produto, sku="06520-AZU", cor="AZUL")
        verde = _variacao(produto, sku="06520-VD", cor="VERDE")

        self.assertEqual(produto.variacoes.count(), 2)

        # cada uma tem seu próprio status e tiny_id, independentes entre si
        azul.status = StatusVariacao.CADASTRADO
        azul.tiny_id = "1001"
        azul.save()

        verde.refresh_from_db()
        self.assertEqual(verde.status, StatusVariacao.PENDENTE)
        self.assertIsNone(verde.tiny_id)

    def test_sku_e_unico_dentro_do_mesmo_produto_pai(self):
        instancia = _instancia()
        produto = _produto(instancia)
        _variacao(produto, sku="06520-AZU", cor="AZUL")

        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                _variacao(produto, sku="06520-AZU", cor="OUTRA")

    def test_mesmo_sku_e_permitido_em_produtos_pai_diferentes(self):
        instancia = _instancia()
        produto_1 = _produto(instancia, codigo_pai="06520")
        produto_2 = _produto(instancia, codigo_pai="06521")

        _variacao(produto_1, sku="REPETIDO")
        # não deve levantar: unicidade é por (produto, sku), não sku global
        _variacao(produto_2, sku="REPETIDO")
        self.assertEqual(Variacao.objects.filter(sku="REPETIDO").count(), 2)


class RegraXbzPrefixoSaindoDeLinhaTests(TestCase):
    """
    Regra nº 2 (cliente): XBZ com codigo_pai iniciado por "P@" está saindo
    de linha e nunca deve ser cadastrado. É prefixo, não "contém @ em
    qualquer posição" — na amostra real isso muda a contagem de 876 (contém
    @) para 661 (prefixo) registros afetados.
    """

    def test_codigo_pai_com_prefixo_p_arroba_marca_produto_como_descontinuado(self):
        instancia = _instancia()
        produto = _produto(instancia, codigo_pai="P@12288")
        self.assertTrue(produto.descontinuado)

    def test_codigo_pai_sem_prefixo_p_arroba_nao_e_afetado(self):
        instancia = _instancia()
        produto = _produto(instancia, codigo_pai="06520")
        self.assertFalse(produto.descontinuado)

    def test_arroba_fora_do_prefixo_nao_conta_como_saindo_de_linha(self):
        """Garante que o filtro é por prefixo, e não por conter '@' em qualquer posição."""
        instancia = _instancia()
        produto = _produto(instancia, codigo_pai="06520P@")
        self.assertFalse(produto.descontinuado)

    def test_regra_e_exclusiva_da_xbz(self):
        instancia = _instancia()
        produto = _produto(instancia, fornecedor="asia", codigo_pai="P@99999")
        self.assertFalse(produto.descontinuado)

    def test_variacao_de_produto_descontinuado_nao_pode_ser_cadastrada(self):
        instancia = _instancia()
        produto = _produto(instancia, codigo_pai="P@12288")
        variacao = _variacao(produto, estoque=50)  # mesmo com estoque, é descarte permanente
        self.assertEqual(variacao.status, StatusVariacao.DESCONTINUADO)


class RegraEstoqueZeroFicaAguardandoTests(TestCase):
    """
    Regra nº 3 (cliente): variação com estoque zero no fornecedor não é
    cadastrada no Tiny, mas fica registrada no espelho como 'aguardando',
    para ser cadastrada quando houver reposição. Diferente da regra nº 2
    (descarte permanente).
    """

    def test_variacao_criada_com_estoque_zero_fica_aguardando(self):
        instancia = _instancia()
        produto = _produto(instancia)
        variacao = _variacao(produto, estoque=0)
        self.assertEqual(variacao.status, StatusVariacao.AGUARDANDO)

    def test_variacao_criada_com_estoque_positivo_fica_pendente(self):
        instancia = _instancia()
        produto = _produto(instancia)
        variacao = _variacao(produto, estoque=5)
        self.assertEqual(variacao.status, StatusVariacao.PENDENTE)

    def test_reposicao_de_estoque_volta_de_aguardando_para_pendente(self):
        instancia = _instancia()
        produto = _produto(instancia)
        variacao = _variacao(produto, estoque=0)
        self.assertEqual(variacao.status, StatusVariacao.AGUARDANDO)

        variacao.estoque = 20
        variacao.save()
        self.assertEqual(variacao.status, StatusVariacao.PENDENTE)

    def test_estoque_zero_nao_reverte_status_ja_cadastrado(self):
        """Uma variação já cadastrada no Tiny não deve voltar para 'aguardando' só por zerar estoque."""
        instancia = _instancia()
        produto = _produto(instancia)
        variacao = _variacao(produto, estoque=10)
        variacao.status = StatusVariacao.CADASTRADO
        variacao.tiny_id = "555"
        variacao.save()

        variacao.estoque = 0
        variacao.save()
        self.assertEqual(variacao.status, StatusVariacao.CADASTRADO)

    def test_estoque_zero_nao_reverte_descontinuado(self):
        instancia = _instancia()
        produto = _produto(instancia, codigo_pai="P@12288")
        variacao = _variacao(produto, estoque=0)
        self.assertEqual(variacao.status, StatusVariacao.DESCONTINUADO)


class RegraPrecoSemMargemTests(TestCase):
    """Regra nº 4 (cliente): o preço gravado é o preço do fornecedor, sem margem."""

    def test_preco_venda_tiny_e_identico_ao_preco_do_fornecedor(self):
        instancia = _instancia()
        produto = _produto(instancia)
        variacao = _variacao(produto, preco=Decimal("29.90"))
        self.assertEqual(variacao.preco_venda_tiny, Decimal("29.90"))
        self.assertEqual(variacao.preco_venda_tiny, variacao.preco)

    def test_preco_nao_sofre_nenhuma_transformacao_ao_salvar(self):
        instancia = _instancia()
        produto = _produto(instancia)
        variacao = _variacao(produto, preco=Decimal("100.00"))
        variacao.refresh_from_db()
        self.assertEqual(variacao.preco, Decimal("100.00"))
