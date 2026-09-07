"""
Auditoria SOMENTE LEITURA da correspondência entre o espelho local da Só
Marcas (catalogo.Variacao / catalogo.Produto do fornecedor `somarcas`) e o
espelho local do catálogo do Tiny (catalogo.ProdutoTiny) de uma instância.

O objetivo é MEDIR, não casar: o comando não implementa matching de
produção, não faz fuzzy matching, não altera SKU, não escreve no Tiny e
não grava/atualiza/apaga nenhum registro do banco. Ele só executa
consultas de leitura no ORM e imprime números para diagnóstico.

Correspondência "exata" aqui é definida por:
  - SKU: `Variacao.sku` == `ProdutoTiny.sku` (comparação exata, apenas
    `strip()` das pontas — espaço nas bordas não é significativo);
  - descrição: NCM idêntico E descrição normalizada idêntica. O NCM é
    comparado só pelos dígitos (ver `normalizar_ncm`): a Só Marcas grava
    `76151000` e o Tiny grava `7615.10.00` — é o mesmo NCM, só muda a
    formatação. A normalização da descrição (ver `normalizar_descricao`)
    só trata diferenças triviais de formatação: caixa, acentos,
    pontuação e espaçamento. Nada de similaridade, tokens parciais ou
    distância de edição.

O valor original do NCM (com ou sem pontos) é preservado e usado tal
qual nas amostras — a normalização vale só para comparação e índices.
"""

import re
import unicodedata
from collections import Counter, defaultdict

from django.core.management.base import BaseCommand, CommandError

from apps.instancias.constants import Fornecedor
from apps.instancias.models import Instancia

from ...models import ProdutoTiny, Variacao

FORNECEDOR = Fornecedor.SOMARCAS
TAMANHO_AMOSTRA_PADRAO = 30
TOP_NCM_PADRAO = 20

# Categorias Unicode de pontuação/símbolo — viram espaço na normalização.
_CATEGORIAS_PONTUACAO = {"P", "S"}

_SO_DIGITOS = re.compile(r"\D+")


def normalizar_ncm(valor: str) -> str:
    """
    Reduz um NCM à sua forma só-dígitos, para comparar valores que
    diferem apenas na formatação:

      - "7615.10.00" -> "76151000"
      - "76151000"   -> "76151000"
      - " 7615.10.00 " -> "76151000"
      - "" / None     -> ""

    Não valida quantidade de dígitos nem inventa conversão — só remove
    tudo que não é dígito. NÃO é fuzzy matching.
    """
    if not valor:
        return ""
    return _SO_DIGITOS.sub("", str(valor))


def normalizar_descricao(texto: str) -> str:
    """
    Normaliza uma descrição para comparação exata de "mesma descrição",
    tratando apenas diferenças triviais de formatação:

      - casefold (lowercase agressivo, cobre ß/İ etc.);
      - remove acentos (decompõe em NFKD e descarta os diacríticos);
      - troca qualquer pontuação/símbolo por espaço;
      - colapsa espaços e remove as pontas.

    NÃO faz fuzzy matching: não remove stopwords, não ordena tokens, não
    corrige plural/singular, não mede similaridade.
    """
    if not texto:
        return ""
    decomposto = unicodedata.normalize("NFKD", texto)
    saida = []
    for caractere in decomposto:
        categoria = unicodedata.category(caractere)
        if categoria.startswith("M"):
            continue  # diacrítico solto após o NFKD
        if categoria[0] in _CATEGORIAS_PONTUACAO:
            saida.append(" ")
        else:
            saida.append(caractere)
    return " ".join("".join(saida).casefold().split())


class Command(BaseCommand):
    help = (
        "Auditoria SOMENTE LEITURA: mede a correspondência exata entre o espelho "
        "local da Só Marcas (Variacao/Produto do fornecedor somarcas) e o espelho "
        "local do Tiny (ProdutoTiny) de uma instância. Não escreve nada — nem no "
        "Tiny, nem no banco. Serve só para diagnóstico."
    )

    def add_arguments(self, parser):
        parser.add_argument("instancia_slug", help="slug da Instancia (ex.: ekk-brindes)")
        parser.add_argument(
            "--amostra",
            type=int,
            default=TAMANHO_AMOSTRA_PADRAO,
            help=f"Quantas linhas imprimir em cada amostra (padrão: {TAMANHO_AMOSTRA_PADRAO}).",
        )
        parser.add_argument(
            "--top-ncm",
            type=int,
            default=TOP_NCM_PADRAO,
            help=f"Quantos NCMs mais frequentes listar (padrão: {TOP_NCM_PADRAO}).",
        )

    def handle(self, *args, **options):
        instancia = self._obter_instancia(options["instancia_slug"])
        tamanho_amostra = max(0, options["amostra"])
        top_ncm = max(0, options["top_ncm"])

        variacoes = list(
            Variacao.objects.filter(
                produto__instancia=instancia, produto__fornecedor=FORNECEDOR
            )
            .select_related("produto")
            .order_by("sku", "id")
        )
        produtos_tiny = list(
            ProdutoTiny.objects.filter(instancia=instancia).order_by("sku", "tiny_id")
        )

        # --- índices do lado Tiny (só leitura, em memória) -------------------
        skus_tiny = {p.sku.strip() for p in produtos_tiny if p.sku and p.sku.strip()}
        indice_tiny = defaultdict(list)  # (ncm, descricao_normalizada) -> [ProdutoTiny]
        tiny_sem_descricao = 0
        for p in produtos_tiny:
            descricao_norm = normalizar_descricao(p.descricao)
            if not descricao_norm:
                tiny_sem_descricao += 1
                continue
            indice_tiny[(normalizar_ncm(p.ncm), descricao_norm)].append(p)

        # --- varredura do lado fornecedor ----------------------------------
        com_sku_igual = 0
        sku_em_comum = set()
        variacao_sem_descricao = 0

        inequivocos = []  # (variacao, produto_tiny)
        ambiguos = []  # (variacao, [ProdutoTiny])
        sem_match = []  # variacao
        ncms_somarcas = Counter()
        # colisão reversa: um mesmo ProdutoTiny apontado por >1 variação inequívoca
        tiny_id_para_variacoes = defaultdict(list)

        for variacao in variacoes:
            ncms_somarcas[normalizar_ncm(variacao.ncm) or "(vazio)"] += 1

            sku_forn = (variacao.sku or "").strip()
            if sku_forn and sku_forn in skus_tiny:
                com_sku_igual += 1
                sku_em_comum.add(sku_forn)

            descricao_forn = variacao.nome or variacao.produto.nome
            descricao_norm = normalizar_descricao(descricao_forn)
            if not descricao_norm:
                variacao_sem_descricao += 1
                sem_match.append(variacao)
                continue

            candidatos = indice_tiny.get((normalizar_ncm(variacao.ncm), descricao_norm), [])
            if len(candidatos) == 1:
                inequivocos.append((variacao, candidatos[0]))
                tiny_id_para_variacoes[candidatos[0].tiny_id].append(variacao)
            elif len(candidatos) > 1:
                ambiguos.append((variacao, candidatos))
            else:
                sem_match.append(variacao)

        total_com_match_exato = len(inequivocos) + len(ambiguos)
        tiny_alvo_compartilhado = sum(
            1 for vs in tiny_id_para_variacoes.values() if len(vs) > 1
        )

        # --- distribuição de NCM (fornecedor x Tiny) -----------------------
        ncms_tiny = Counter()
        for p in produtos_tiny:
            ncms_tiny[normalizar_ncm(p.ncm) or "(vazio)"] += 1

        # --- impressão ---------------------------------------------------
        w = self.stdout.write
        w("")
        w(self.style.WARNING("AUDITORIA SOMENTE LEITURA — nenhum registro foi alterado."))
        w(f"  Instância ................................. {instancia.slug} (id {instancia.pk})")
        w(f"  Fornecedor ............................... {FORNECEDOR.value}")
        w("")
        w("== Totais ==")
        w(f"  1. Variações Só Marcas ................... {len(variacoes)}")
        w(f"  2. Produtos Tiny (espelho) .............. {len(produtos_tiny)}")
        w("")
        w("== Correspondência por SKU (exata, só strip) ==")
        w(f"  3. Variações com SKU idêntico a algum Tiny  {com_sku_igual}")
        w(f"     SKUs distintos em comum ............... {len(sku_em_comum)}")
        w("")
        w("== Correspondência por NCM + descrição normalizada (exata) ==")
        w(f"  4. Variações com match exato (>=1 candidato) {total_com_match_exato}")
        w(f"  5.   ...com exatamente 1 candidato Tiny ... {len(inequivocos)}")
        w(f"  6.   ...com mais de 1 candidato (ambíguo) . {len(ambiguos)}")
        w(f"  7. Variações sem match exato ............. {len(sem_match)}")
        w(f"     (5 + 6 + 7 = {len(inequivocos) + len(ambiguos) + len(sem_match)}; total de variações = {len(variacoes)})")
        w("")
        w("== Observações de qualidade dos dados ==")
        w(f"  Variações sem descrição utilizável ...... {variacao_sem_descricao}")
        w(f"  Produtos Tiny sem descrição utilizável .. {tiny_sem_descricao}")
        w(
            "  Alvos Tiny apontados por >1 variação "
            f"inequívoca ... {tiny_alvo_compartilhado}"
        )
        w("")
        w(f"== 8. NCMs mais frequentes (top {top_ncm}) ==")
        w(f"  {'NCM':<16} {'Só Marcas':>10} {'Tiny':>10}")
        for ncm, qtd in ncms_somarcas.most_common(top_ncm):
            w(f"  {ncm:<16} {qtd:>10} {ncms_tiny.get(ncm, 0):>10}")
        w("")
        w(f"== 9. Amostra de {tamanho_amostra} matches inequívocos ==")
        self._imprimir_amostra_matches(inequivocos[:tamanho_amostra])
        w("")
        w(f"== 10. Amostra de {tamanho_amostra} casos sem match exato ==")
        self._imprimir_amostra_sem_match(sem_match[:tamanho_amostra])

    # -- helpers -------------------------------------------------------

    def _obter_instancia(self, slug):
        try:
            return Instancia.objects.get(slug=slug)
        except Instancia.DoesNotExist:
            raise CommandError(f"Instância com slug '{slug}' não encontrada.") from None

    def _imprimir_amostra_matches(self, pares):
        w = self.stdout.write
        if not pares:
            w("  (nenhum)")
            return
        for variacao, tiny in pares:
            w(
                f"  - SKU forn ...: {variacao.sku}\n"
                f"    desc forn ..: {variacao.nome or variacao.produto.nome}\n"
                f"    NCM forn ...: {variacao.ncm!r}\n"
                f"    tiny_id ....: {tiny.tiny_id}\n"
                f"    SKU Tiny ...: {tiny.sku}\n"
                f"    desc Tiny ..: {tiny.descricao}\n"
                f"    NCM Tiny ...: {tiny.ncm!r}"
            )

    def _imprimir_amostra_sem_match(self, variacoes):
        w = self.stdout.write
        if not variacoes:
            w("  (nenhum)")
            return
        for variacao in variacoes:
            w(
                f"  - SKU forn ...: {variacao.sku}\n"
                f"    desc forn ..: {variacao.nome or variacao.produto.nome}\n"
                f"    NCM forn ...: {variacao.ncm!r}\n"
                f"    desc norm ..: {normalizar_descricao(variacao.nome or variacao.produto.nome)!r}"
            )
