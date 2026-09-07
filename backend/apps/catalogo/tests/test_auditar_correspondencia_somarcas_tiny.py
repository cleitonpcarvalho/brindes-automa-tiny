"""
`auditar_correspondencia_somarcas_tiny <slug>` — auditoria SOMENTE LEITURA
da correspondência entre o espelho da Só Marcas (Variacao/Produto) e o
espelho do Tiny (ProdutoTiny).

Os testes provam que o comando:
  - mede totais, match por SKU e match por NCM + descrição normalizada;
  - separa match inequívoco (1 candidato) de ambíguo (>1) e de sem match;
  - normaliza só formatação trivial (caixa/acento/pontuação/espaço) e NÃO
    faz fuzzy matching;
  - não grava, não atualiza e não apaga nada.
"""

from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from apps.instancias.constants import Fornecedor
from apps.instancias.models import Instancia

from ..management.commands import auditar_correspondencia_somarcas_tiny as cmd
from ..models import Produto, ProdutoTiny, Variacao


def _secao(saida: str, titulo: str) -> str:
    """Recorta o trecho da saída entre o cabeçalho `titulo` e o próximo `==`."""
    linhas = saida.splitlines()
    inicio = next(i for i, l in enumerate(linhas) if titulo in l)
    fim = next(
        (i for i in range(inicio + 1, len(linhas)) if linhas[i].strip().startswith("==")),
        len(linhas),
    )
    return "\n".join(linhas[inicio:fim])


class NormalizarDescricaoTests(TestCase):
    def test_trata_caixa_acento_pontuacao_e_espaco(self):
        n = cmd.normalizar_descricao
        base = n("Garrafa Térmica 500ml")
        self.assertEqual(base, "garrafa termica 500ml")
        self.assertEqual(n("garrafa termica  500ml"), base)  # espaço duplo
        self.assertEqual(n("GARRAFA TÉRMICA 500ML"), base)  # caixa
        self.assertEqual(n("Garrafa Térmica - 500ml."), base)  # pontuação
        self.assertEqual(n("  Garrafa   Térmica 500ml  "), base)  # pontas

    def test_nao_faz_fuzzy(self):
        n = cmd.normalizar_descricao
        # sinônimo / palavra a mais continua sendo string diferente
        self.assertNotEqual(n("Garrafa Térmica 500ml"), n("Garrafa Térmica 500 ml preta"))
        self.assertNotEqual(n("Caneca"), n("Canecas"))

    def test_vazio(self):
        self.assertEqual(cmd.normalizar_descricao(""), "")
        self.assertEqual(cmd.normalizar_descricao(None), "")


class NormalizarNcmTests(TestCase):
    def test_mantem_so_digitos(self):
        n = cmd.normalizar_ncm
        self.assertEqual(n("7615.10.00"), "76151000")
        self.assertEqual(n("76151000"), "76151000")
        self.assertEqual(n(" 7615.10.00 "), "76151000")
        self.assertEqual(n("7615-10-00"), "76151000")

    def test_pontuado_e_sem_pontuacao_normalizam_igual(self):
        self.assertEqual(cmd.normalizar_ncm("7615.10.00"), cmd.normalizar_ncm("76151000"))

    def test_vazio(self):
        self.assertEqual(cmd.normalizar_ncm(""), "")
        self.assertEqual(cmd.normalizar_ncm(None), "")


class NormalizarSkuTests(TestCase):
    def test_uppercase_e_remove_nao_alfanumerico(self):
        n = cmd.normalizar_sku
        self.assertEqual(n("KT-90395"), "KT90395")
        self.assertEqual(n("kt.90395"), "KT90395")
        self.assertEqual(n("KT 90395"), "KT90395")
        self.assertEqual(n("KT/90395"), "KT90395")
        self.assertEqual(n(" ekkt-90507 "), "EKKT90507")

    def test_vazio(self):
        self.assertEqual(cmd.normalizar_sku(""), "")
        self.assertEqual(cmd.normalizar_sku(None), "")

    def test_variantes_removem_so_prefixo_inicial_ek_ekk(self):
        v = cmd.variantes_sku_tiny_para_auditoria
        self.assertEqual(v("EKKT90507"), {"EKKT90507", "KT90507", "T90507"})
        self.assertEqual(v("EK12345"), {"EK12345", "12345"})
        self.assertEqual(v("KT90395"), {"KT90395"})  # sem prefixo no início

    def test_variantes_nao_tocam_ek_no_meio(self):
        v = cmd.variantes_sku_tiny_para_auditoria
        self.assertEqual(v("TEKK123"), {"TEKK123"})  # EKK no meio, não no início
        self.assertEqual(v("XEK9"), {"XEK9"})

    def test_variantes_nunca_produzem_string_vazia(self):
        v = cmd.variantes_sku_tiny_para_auditoria
        self.assertEqual(v("EK"), {"EK"})  # remover "EK" esvaziaria -> não gera
        self.assertNotIn("", v("EKK"))


class SimilaridadeDescricaoUnitTests(TestCase):
    def test_score_identico_e_um(self):
        self.assertEqual(cmd.similaridade_descricao("garrafa termica 500ml", "garrafa termica 500ml"), 1.0)

    def test_descricoes_semelhantes_score_alto_mas_menor_que_um(self):
        s = cmd.similaridade_descricao("garrafa termica inox 500ml", "garrafa termica inox 500 ml")
        self.assertGreater(s, 0.9)
        self.assertLess(s, 1.0)

    def test_descricoes_diferentes_score_baixo(self):
        self.assertLess(
            cmd.similaridade_descricao("guarda chuva automatico preto", "caneca de ceramica 300ml"),
            0.5,
        )

    def test_vazio_e_zero(self):
        self.assertEqual(cmd.similaridade_descricao("", "abc"), 0.0)
        self.assertEqual(cmd.similaridade_descricao("abc", ""), 0.0)

    def test_faixa_score(self):
        self.assertEqual(cmd._faixa_score(0.97), ">= 0.95")
        self.assertEqual(cmd._faixa_score(0.95), ">= 0.95")
        self.assertEqual(cmd._faixa_score(0.93), ">= 0.90 e < 0.95")
        self.assertEqual(cmd._faixa_score(0.86), ">= 0.85 e < 0.90")
        self.assertEqual(cmd._faixa_score(0.80), ">= 0.80 e < 0.85")
        self.assertEqual(cmd._faixa_score(0.5), "< 0.80")


class ExtrairAtributosUnitTests(TestCase):
    def _cmp(self, a, b):
        return cmd.comparar_atributos(cmd.extrair_atributos(a), cmd.extrair_atributos(b))

    def test_capacidade_extraida_com_e_sem_espaco(self):
        self.assertEqual(cmd.extrair_atributos("CANECA EM VIDRO - 300ML")["capacidade_ml"], frozenset({300.0}))
        self.assertEqual(cmd.extrair_atributos("Garrafa 1,5 L")["capacidade_ml"], frozenset({1500.0}))

    def test_300ml_vs_390ml_conflito_capacidade(self):
        r = self._cmp("Caneca em vidro 300ml", "Caneca em vidro 390ml")
        self.assertEqual(r["conflitos"], ["capacidade_ml"])
        self.assertEqual(r["iguais"], [])
        self.assertEqual(r["nao_comparaveis"], [])

    def test_1_litro_vs_1000ml_igual(self):
        r = self._cmp("Jarra 1 litro", "Jarra 1000 ml")
        self.assertEqual(r["iguais"], ["capacidade_ml"])
        self.assertEqual(r["conflitos"], [])

    def test_4_pcs_vs_6_pecas_conflito_quantidade(self):
        r = self._cmp("KIT QUEIJO E VINHO - 4 PÇS", "Kit Queijo E Vinho - 6 Peças")
        self.assertEqual(r["conflitos"], ["pecas"])

    def test_4_pcs_vs_4_pecas_igual(self):
        r = self._cmp("Kit 4 PÇS", "Kit 4 peças")
        self.assertEqual(r["iguais"], ["pecas"])
        self.assertEqual(r["conflitos"], [])

    def test_atributo_so_de_um_lado_e_nao_comparavel_nao_conflito(self):
        r = self._cmp("Squeeze 500ml inox", "Squeeze inox")
        self.assertEqual(r["conflitos"], [])
        self.assertEqual(r["iguais"], [])
        self.assertEqual(r["nao_comparaveis"], ["capacidade_ml"])

    def test_numero_sem_unidade_nao_vira_atributo(self):
        self.assertEqual(cmd.extrair_atributos("Caneca modelo 90395 azul 12 meses garantia"), {})
        r = self._cmp("Kit modelo 300 edicao 4", "Kit modelo 900 edicao 8")
        self.assertEqual(r["conflitos"], [])
        self.assertEqual(r["iguais"], [])
        self.assertEqual(r["nao_comparaveis"], [])

    def test_dimensoes_mm_para_cm_e_ordenacao(self):
        a = cmd.extrair_atributos("Suporte 32x14,5x5,5 mm (AxLxP)")
        self.assertEqual(a["dimensoes_cm"], frozenset({(0.55, 1.45, 3.2)}))
        r = self._cmp("Caixa 10x20 cm", "Caixa 20 x 10 cm")
        self.assertEqual(r["iguais"], ["dimensoes_cm"])

    def test_peso_kg_para_g(self):
        r = self._cmp("Kit 147 g", "Kit 0,147 kg")
        self.assertEqual(r["iguais"], ["peso_g"])

    def test_formatar_atributos(self):
        self.assertEqual(cmd.formatar_atributos({}), "(nenhum)")
        self.assertEqual(
            cmd.formatar_atributos(cmd.extrair_atributos("Kit 4 pçs 300ml")),
            "capacidade=300ml, peças=4",
        )


class AuditoriaTests(TestCase):
    def setUp(self):
        self.instancia = Instancia.objects.create(nome="EKK Brindes")
        self.produto = Produto.objects.create(
            instancia=self.instancia,
            fornecedor=Fornecedor.SOMARCAS,
            codigo_pai="PAI",
            nome="pai",
        )
        # outra instância + outro fornecedor: têm de ser ignorados
        self.outra_instancia = Instancia.objects.create(nome="Outra")
        self.produto_xbz = Produto.objects.create(
            instancia=self.instancia, fornecedor=Fornecedor.XBZ, codigo_pai="X", nome="x"
        )

    def _variacao(self, sku, nome, ncm, produto=None):
        return Variacao.objects.create(
            produto=produto or self.produto,
            sku=sku,
            nome=nome,
            ncm=ncm,
            preco=Decimal("10.00"),
            estoque=5,
        )

    def _tiny(self, tiny_id, sku, descricao, ncm, instancia=None):
        return ProdutoTiny.objects.create(
            instancia=instancia or self.instancia,
            tiny_id=tiny_id,
            sku=sku,
            descricao=descricao,
            ncm=ncm,
        )

    def _rodar(self, *args):
        out = StringIO()
        call_command(
            "auditar_correspondencia_somarcas_tiny", self.instancia.slug, *args, stdout=out
        )
        return out.getvalue()

    def test_instancia_inexistente_recusa(self):
        with self.assertRaises(CommandError):
            call_command("auditar_correspondencia_somarcas_tiny", "nao-existe", stdout=StringIO())

    def test_totais_contam_so_o_fornecedor_e_a_instancia_certos(self):
        self._variacao("A-1", "Caneca Branca", "39241000")
        self._variacao("A-2", "Caneca Preta", "39241000")
        self._variacao("X-1", "Item XBZ", "39241000", produto=self.produto_xbz)  # outro fornecedor
        self._tiny(1, "T-1", "Qualquer", "39241000")
        self._tiny(2, "T-2", "Outra", "39241000")
        self._tiny(9, "T-9", "Da outra instância", "39241000", instancia=self.outra_instancia)

        saida = self._rodar()
        self.assertIn("1. Variações Só Marcas ................... 2", saida)
        self.assertIn("2. Produtos Tiny (espelho) .............. 2", saida)

    def test_match_por_sku_exato(self):
        self._variacao("SKU-IGUAL", "Nada a ver", "111")
        self._variacao("SKU-SO-FORN", "Nada a ver", "111")
        self._tiny(1, "SKU-IGUAL", "Descricao Tiny", "999")
        self._tiny(2, "SKU-TINY-SO", "Outra", "999")

        saida = self._rodar()
        self.assertIn("3. Variações com SKU idêntico a algum Tiny  1", saida)
        self.assertIn("SKUs distintos em comum ............... 1", saida)

    def test_match_inequivoco_por_ncm_mais_descricao_normalizada(self):
        self._variacao("F-1", "Garrafa Térmica 500ml", "96170010")
        # mesmo NCM, descrição só com diferença de formatação -> match exato, 1 candidato
        self._tiny(10, "T-10", "GARRAFA TÉRMICA - 500ML.", "96170010")
        # ruído: mesmo NCM, descrição diferente de verdade
        self._tiny(11, "T-11", "Copo Plástico", "96170010")

        saida = self._rodar("--amostra", "5")
        self.assertIn("4. Variações com match exato (>=1 candidato) 1", saida)
        self.assertIn("5.   ...com exatamente 1 candidato Tiny ... 1", saida)
        self.assertIn("6.   ...com mais de 1 candidato (ambíguo) . 0", saida)
        self.assertIn("7. Variações sem match exato ............. 0", saida)
        # amostra de match inequívoco mostra os dois lados
        self.assertIn("SKU forn ...: F-1", saida)
        self.assertIn("tiny_id ....: 10", saida)
        self.assertIn("desc Tiny ..: GARRAFA TÉRMICA - 500ML.", saida)

    def test_ambiguidade_quando_ha_mais_de_um_candidato(self):
        self._variacao("F-1", "Caneca Cerâmica", "69120000")
        self._tiny(20, "T-20", "caneca ceramica", "69120000")
        self._tiny(21, "T-21", "Caneca Cerâmica!", "69120000")

        saida = self._rodar()
        self.assertIn("5.   ...com exatamente 1 candidato Tiny ... 0", saida)
        self.assertIn("6.   ...com mais de 1 candidato (ambíguo) . 1", saida)

    def test_ncm_diferente_nao_casa_mesmo_com_descricao_igual(self):
        self._variacao("F-1", "Mochila Executiva", "42021200")
        self._tiny(30, "T-30", "Mochila Executiva", "42029200")  # NCM diferente

        saida = self._rodar()
        self.assertIn("7. Variações sem match exato ............. 1", saida)
        self.assertIn("SKU forn ...: F-1", saida)

    def test_nao_faz_fuzzy_matching(self):
        self._variacao("F-1", "Squeeze 750ml", "39241000")
        self._tiny(40, "T-40", "Squeeze 750ml Azul", "39241000")  # palavra a mais

        saida = self._rodar()
        self.assertIn("7. Variações sem match exato ............. 1", saida)

    def test_ncm_pontuado_no_tiny_casa_com_ncm_sem_pontuacao_da_so_marcas(self):
        # bug de produção: Só Marcas grava "76151000", Tiny grava "7615.10.00"
        self._variacao("F-1", "Panela de Alumínio", "76151000")
        self._tiny(50, "T-50", "Panela de Alumínio", "7615.10.00")

        saida = self._rodar("--amostra", "5")
        self.assertIn("5.   ...com exatamente 1 candidato Tiny ... 1", saida)
        self.assertIn("7. Variações sem match exato ............. 0", saida)
        # o valor ORIGINAL de cada lado aparece na amostra, sem reformatar
        self.assertIn("NCM forn ...: '76151000'", saida)
        self.assertIn("NCM Tiny ...: '7615.10.00'", saida)

    def test_distribuicao_agrupa_ncm_pontuado_e_sem_pontuacao(self):
        self._variacao("F-1", "A", "76151000")
        self._variacao("F-2", "B", "7615.10.00")
        self._tiny(1, "T-1", "X", "7615.10.00")
        self._tiny(2, "T-2", "Y", "76151000")

        saida = self._rodar("--top-ncm", "5")
        distribuicao = _secao(saida, "8. NCMs mais frequentes")
        linhas = [l for l in distribuicao.splitlines() if "76151000" in l]
        self.assertEqual(len(linhas), 1)  # uma única linha, não duas
        self.assertRegex(linhas[0], r"76151000\s+2\s+2")

    def test_distribuicao_de_ncm(self):
        self._variacao("F-1", "A", "39241000")
        self._variacao("F-2", "B", "39241000")
        self._variacao("F-3", "C", "42021200")
        self._tiny(1, "T-1", "X", "39241000")

        saida = self._rodar("--top-ncm", "5")
        self.assertIn("8. NCMs mais frequentes", saida)
        # NCM 39241000: 2 na Só Marcas, 1 no Tiny
        linha = next(l for l in saida.splitlines() if "39241000" in l)
        self.assertRegex(linha, r"39241000\s+2\s+1")

    def test_amostra_sem_match(self):
        self._variacao("SEM-1", "Produto Só Fornecedor", "11111111")
        saida = self._rodar()
        self.assertIn("10. Amostra de 30 casos sem match", saida)
        self.assertIn("SKU forn ...: SEM-1", saida)
        self.assertIn("desc norm ..: 'produto so fornecedor'", saida)

    def test_e_estritamente_read_only(self):
        self._variacao("F-1", "Garrafa Térmica 500ml", "96170010")
        self._tiny(10, "T-10", "garrafa termica 500ml", "96170010")
        # também exercita a seção 11 (SKU) no snapshot read-only
        self._variacao("KT-90395", "Caneca", "39241000")
        self._tiny(11, "EKKT-90395", "Caneca", "39241000")

        antes = self._snapshot()
        self._rodar()
        self.assertEqual(self._snapshot(), antes)

    # -- seção 11/12: regra de prefixo EK/EKK no SKU --------------------

    def test_regra_de_prefixo_ek_ekk_em_escala(self):
        # os 3 casos reais informados
        self._variacao("KT-90395", "Caneca Térmica", "96170010")
        self._variacao("KT-90410", "Garrafa Inox", "96170010")
        self._variacao("KT-90507", "Squeeze Alumínio", "76151000")
        self._tiny(1, "EKKT-90395", "Caneca Térmica", "96170010")
        self._tiny(2, "EKKT-90410", "Garrafa Inox", "96170010")
        self._tiny(3, "EKKT90507", "Squeeze Alumínio", "76151000")

        saida = self._rodar()
        secao = _secao(saida, "11. Regra histórica de SKU")
        self.assertIn("a. Variações com SKU cru idêntico (= item 3) ..... 0", secao)
        self.assertIn("b. Variações que casam pela normalização de SKU .. 3", secao)
        self.assertIn("c.   ...que só casam removendo o prefixo EK/EKK .. 3", secao)
        self.assertIn("d.   ...inequívocas (1 fornecedor -> 1 Tiny) ..... 3", secao)
        self.assertIn("e.   ...ambíguas (>1 Tiny candidato) ............. 0", secao)
        self.assertIn("f. Produtos Tiny distintos apontados ............. 3", secao)
        self.assertIn("g. Pares (variação, Tiny) analisados ............. 3", secao)
        self.assertIn("h.   ...com NCM normalizado igual ................ 3", secao)
        self.assertIn("i.   ...com descrição normalizada igual .......... 3", secao)
        self.assertIn("j.   ...com NCM normalizado DIFERENTE (falso +?) . 0", secao)

        amostra = _secao(saida, "12. Amostra de")
        self.assertIn("KT-90395  ->  EKKT-90395  (tiny_id 1)", amostra)
        self.assertIn("SKU norm ...: KT90507  ->  EKKT90507", amostra)

    def test_sku_cru_identico_conta_em_11a_e_nao_em_11c(self):
        self._variacao("EKKT-90395", "Caneca", "96170010")  # já igual ao Tiny
        self._tiny(1, "EKKT-90395", "Caneca", "96170010")

        secao = _secao(self._rodar(), "11. Regra histórica de SKU")
        self.assertIn("a. Variações com SKU cru idêntico (= item 3) ..... 1", secao)
        self.assertIn("b. Variações que casam pela normalização de SKU .. 1", secao)
        self.assertIn("c.   ...que só casam removendo o prefixo EK/EKK .. 0", secao)

    def test_ambiguidade_quando_normalizacao_bate_em_dois_tiny(self):
        self._variacao("KT-90395", "Caneca", "96170010")
        self._tiny(1, "KT-90395", "Caneca", "96170010")     # bate direto
        self._tiny(2, "EKKT-90395", "Caneca", "96170010")   # bate removendo EK

        secao = _secao(self._rodar(), "11. Regra histórica de SKU")
        self.assertIn("d.   ...inequívocas (1 fornecedor -> 1 Tiny) ..... 0", secao)
        self.assertIn("e.   ...ambíguas (>1 Tiny candidato) ............. 1", secao)
        self.assertIn("f. Produtos Tiny distintos apontados ............. 2", secao)
        self.assertIn("g. Pares (variação, Tiny) analisados ............. 2", secao)

    def test_sku_compativel_mas_ncm_diferente_e_marcado_como_falso_positivo(self):
        self._variacao("KT-90395", "Caneca", "96170010")
        self._tiny(1, "EKKT-90395", "Caneca", "39241000")  # SKU compatível, NCM diferente

        saida = self._rodar()
        secao = _secao(saida, "11. Regra histórica de SKU")
        self.assertIn("h.   ...com NCM normalizado igual ................ 0", secao)
        self.assertIn("j.   ...com NCM normalizado DIFERENTE (falso +?) . 1", secao)
        self.assertIn("desses, NCM preenchido nos dois lados ..... 1", secao)
        self.assertIn("NCM ........: '96170010'  ≠  '39241000'", _secao(saida, "12. Amostra de"))

    def test_prefixo_no_meio_do_sku_nao_gera_match(self):
        self._variacao("90395", "Caneca", "96170010")
        self._tiny(1, "EKKT-90395", "Caneca", "96170010")  # "90395" não é prefixo-removível

        secao = _secao(self._rodar(), "11. Regra histórica de SKU")
        self.assertIn("b. Variações que casam pela normalização de SKU .. 0", secao)

    # -- seções 13–15: similaridade de descrição -----------------------

    def _contagem(self, secao, rotulo):
        import re as _re

        m = _re.search(rf"{_re.escape(rotulo)}[.\s]*(\d+)", secao)
        self.assertIsNotNone(m, f"rótulo {rotulo!r} não encontrado em:\n{secao}")
        return int(m.group(1))

    def test_similaridade_so_analisa_pendentes_e_distribui_scores(self):
        # v1 tem match exato inequívoco -> NÃO entra na similaridade
        self._variacao("F-1", "Caneca Branca", "691110")
        self._tiny(1, "T-1", "Caneca Branca", "691110")
        # v2 sem match exato, mas com Tiny de mesmo NCM e descrição quase igual
        self._variacao("F-2", "Garrafa Térmica Inox 500ml", "96170010")
        self._tiny(2, "T-2", "Garrafa Termica Inox 500 ml", "96170010")
        self._tiny(3, "T-3", "Garrafa Térmica Inox 1 Litro", "96170010")

        saida = self._rodar()
        s13 = _secao(saida, "13. Similaridade de descrição")
        self.assertEqual(self._contagem(s13, "Variações já identificadas por sinal forte"), 1)
        self.assertEqual(self._contagem(s13, "Variações pendentes analisadas"), 1)
        self.assertEqual(self._contagem(s13, ">= 0.95"), 1)

        s14 = _secao(saida, "14. Amostra dos")
        self.assertIn("F-2  ->  T-2  (tiny_id 2)", s14)
        self.assertRegex(s14, r"score \.+: 0\.\d{4}   2º: 0\.\d{4}   gap: 0\.\d{4}")

    def test_ncm_diferente_com_ambos_preenchidos_nao_entra_nos_candidatos(self):
        self._variacao("F-1", "Caneca Cerâmica Vermelha", "69120000")
        # descrição idêntica, mas NCM diferente -> fora do conjunto de candidatos
        self._tiny(1, "T-1", "Caneca Cerâmica Vermelha", "39241000")

        saida = self._rodar()
        s13 = _secao(saida, "13. Similaridade de descrição")
        self.assertEqual(self._contagem(s13, "Pendentes sem nenhum Tiny de mesmo NCM"), 1)
        self.assertEqual(self._contagem(s13, "sem candidato com mesmo NCM"), 1)
        self.assertNotIn("tiny_id 1", _secao(saida, "14. Amostra dos"))

    def test_fornecedor_sem_ncm_fica_fora_do_filtro(self):
        self._variacao("F-1", "Mochila Executiva", "")
        self._tiny(1, "T-1", "Mochila Executiva", "42021200")

        s13 = _secao(self._rodar(), "13. Similaridade de descrição")
        self.assertEqual(self._contagem(s13, "Pendentes sem NCM no fornecedor (fora do filtro)"), 1)
        self.assertEqual(self._contagem(s13, "Variações pendentes analisadas"), 0)

    def test_gap_e_segundo_candidato(self):
        self._variacao("F-1", "Copo Térmico 300ml", "96170010")
        self._tiny(1, "T-1", "Copo Termico 300 ml", "96170010")          # bem parecido
        self._tiny(2, "T-2", "Guarda-chuva Automático Grande", "96170010")  # nada a ver

        s14 = _secao(self._rodar(), "14. Amostra dos")
        self.assertIn("F-1  ->  T-1  (tiny_id 1)", s14)
        # 1º bem acima do 2º -> gap grande (candidato se destaca)
        m = __import__("re").search(r"gap: (0\.\d{4})", s14)
        self.assertIsNotNone(m)
        self.assertGreater(float(m.group(1)), 0.2)

    def test_empate_entre_dois_tiny_e_caso_de_risco(self):
        self._variacao("F-1", "Squeeze Aluminio 750ml Azul", "39241000")
        # dois Tiny com a MESMA descrição normalizada -> score idêntico, gap 0
        self._tiny(1, "T-1", "Squeeze Alumínio 750 ml Azul", "39241000")
        self._tiny(2, "T-2", "Squeeze Alumínio 750 ml Azul", "39241000")

        saida = self._rodar()
        s15 = _secao(saida, "15. Casos de risco")
        self.assertEqual(self._contagem(s15, "Total de casos de risco"), 1)
        self.assertIn("F-1  ->  T-1  (tiny_id 1)", s15)
        self.assertRegex(s15, r"gap: 0\.0000")
        self.assertRegex(s15, r"quase iguais: 2")

    def test_similaridade_e_read_only(self):
        self._variacao("F-1", "Garrafa Térmica Inox 500ml", "96170010")
        self._tiny(1, "T-1", "Garrafa Termica Inox 500 ml", "96170010")
        self._tiny(2, "T-2", "Garrafa Térmica Inox 500 ml Preta", "96170010")

        antes = self._snapshot()
        self._rodar()
        self.assertEqual(self._snapshot(), antes)

    # -- seções 16–17: atributos numéricos na descrição ---------------

    def test_secao_16_conta_conflitos_por_tipo(self):
        # score alto dos dois, conflito de capacidade
        self._variacao("F-1", "CANECA EM VIDRO - 300ML", "70139900")
        self._tiny(1, "T-1", "Caneca em vidro 390ml", "70139900")
        # score alto, conflito de peças
        self._variacao("F-2", "KIT QUEIJO E VINHO - 4 PÇS", "82119200")
        self._tiny(2, "T-2", "Kit Queijo E Vinho - 6 Pcs", "82119200")
        # score alto, atributos iguais
        self._variacao("F-3", "Squeeze Aluminio 750ml", "76151000")
        self._tiny(3, "T-3", "Squeeze Aluminio 750 ml", "76151000")

        saida = self._rodar()
        s16 = _secao(saida, "16. Atributos numéricos")
        self.assertEqual(self._contagem(s16, "Total de pares analisados"), 3)
        self.assertEqual(self._contagem(s16, "Pares com pelo menos um atributo comparável"), 3)
        self.assertEqual(self._contagem(s16, "com TODOS os comparáveis iguais"), 1)
        self.assertEqual(self._contagem(s16, "com pelo menos um CONFLITO"), 2)
        self.assertRegex(s16, r"capacidade\s+1")
        self.assertRegex(s16, r"peças\s+1")

    def test_secao_17_separa_alto_score_por_conflito(self):
        self._variacao("F-1", "CANECA EM VIDRO - 300ML", "70139900")
        self._tiny(1, "T-1", "Caneca em vidro 390ml", "70139900")
        self._variacao("F-2", "Squeeze Aluminio 750ml", "76151000")
        self._tiny(3, "T-3", "Squeeze Aluminio 750 ml", "76151000")

        saida = self._rodar()
        s17 = _secao(saida, "17. Candidatos com score textual")
        self.assertIn("--- SEM conflito numérico detectado: 1 ---", s17)
        self.assertIn("--- COM conflito numérico detectado: 1 ---", s17)
        # o par com conflito mostra descrições, NCM, score, atributos e o conflito
        self.assertIn("F-1  ->  T-1  (tiny_id 1)", s17)
        self.assertIn("attrs forn .: capacidade=300ml", s17)
        self.assertIn("attrs Tiny .: capacidade=390ml", s17)
        self.assertIn("CONFLITO ...: capacidade", s17)

    def test_ausencia_de_atributo_nao_e_conflito_na_auditoria(self):
        self._variacao("F-1", "Garrafa Inox 500ml Premium", "96170010")
        self._tiny(1, "T-1", "Garrafa Inox Premium", "96170010")  # Tiny sem capacidade

        saida = self._rodar()
        s16 = _secao(saida, "16. Atributos numéricos")
        self.assertEqual(self._contagem(s16, "com pelo menos um CONFLITO"), 0)
        self.assertEqual(self._contagem(s16, "Pares sem nenhum atributo comparável"), 1)
        self.assertIn("CONFLITO ...: (nenhum)   (não comparável: capacidade)", saida)

    def test_atributos_read_only(self):
        self._variacao("F-1", "CANECA EM VIDRO - 300ML", "70139900")
        self._tiny(1, "T-1", "Caneca em vidro 390ml", "70139900")
        self._variacao("F-2", "Kit 4 pçs 32x14,5x5,5 mm", "82119200")
        self._tiny(2, "T-2", "Kit 6 pcs 33x15x6 mm", "82119200")

        antes = self._snapshot()
        self._rodar()
        self.assertEqual(self._snapshot(), antes)

    def _snapshot(self):
        return {
            "variacoes": list(
                Variacao.objects.order_by("pk").values_list("pk", "sku", "nome", "ncm", "atualizado_em")
            ),
            "produtos": list(
                Produto.objects.order_by("pk").values_list("pk", "nome", "atualizado_em")
            ),
            "tiny": list(
                ProdutoTiny.objects.order_by("pk").values_list(
                    "pk", "sku", "descricao", "ncm", "hash_conteudo", "atualizado_em"
                )
            ),
            "instancias": list(
                Instancia.objects.order_by("pk").values_list("pk", "slug", "atualizado_em")
            ),
        }
