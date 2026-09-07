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

Além disso, este comando MEDE (não aplica) uma possível regra histórica
de SKU vista nos dados reais: o SKU do Tiny parece ser o SKU do
fornecedor com um prefixo `EK`/`EKK` colado na frente
(`KT-90395` -> `EKKT-90395`, `KT-90507` -> `EKKT90507`). A seção 11
compara SKUs por uma normalização SÓ PARA AUDITORIA (ver
`normalizar_sku` / `variantes_sku_tiny_para_auditoria`) e cruza esses
matches com NCM e descrição para estimar falsos positivos. Nada disso
altera SKU nem implementa matching de produção.

Seções 13–15: análise EXPLORATÓRIA de similaridade de descrição para as
variações que ainda NÃO têm match inequívoco (nem por NCM+descrição
exata, nem pela regra de prefixo de SKU, nem por `tiny_id` já gravado).
Para cada uma dessas variações, os candidatos do lado Tiny são
filtrados pelo NCM normalizado (mesmo NCM dos dois lados — NCM sozinho
NUNCA é match) e a semelhança entre as descrições normalizadas é medida
com `difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()` (só
biblioteca padrão, determinístico). NENHUM score vira "match" aqui: o
objetivo é observar a distribuição real dos dados antes de decidir a
regra. Não há threshold de produção — os cortes `--score-perigo` /
`--gap-perigo` existem só para separar os casos de risco na saída.
"""

import re
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher

from django.core.management.base import BaseCommand, CommandError

from apps.instancias.constants import Fornecedor
from apps.instancias.models import Instancia

from ...models import ProdutoTiny, Variacao

FORNECEDOR = Fornecedor.SOMARCAS
TAMANHO_AMOSTRA_PADRAO = 30
TAMANHO_AMOSTRA_SKU_PADRAO = 50
TAMANHO_AMOSTRA_SIM_PADRAO = 50
TOP_NCM_PADRAO = 20

# Cortes usados SÓ para organizar a saída das seções 13–15 (distribuição e
# "casos perigosos"). NÃO são threshold de produção — a decisão da regra de
# matching vem depois, olhando a distribuição real.
SCORE_PERIGO_PADRAO = 0.90  # score alto o bastante para "quase igual"
GAP_PERIGO_PADRAO = 0.05  # distância pequena entre 1º e 2º = candidato não se destaca

# Faixas de score para o histograma da seção 13 (limite inferior, rótulo).
FAIXAS_SCORE = (
    (0.95, ">= 0.95"),
    (0.90, ">= 0.90 e < 0.95"),
    (0.85, ">= 0.85 e < 0.90"),
    (0.80, ">= 0.80 e < 0.85"),
    (0.0, "< 0.80"),
)

# Prefixos que o Tiny parece colar na frente do SKU do fornecedor. Removidos
# APENAS quando iniciais e APENAS para a auditoria da seção 11 — nunca do
# meio do SKU, nunca gravados. Ordem: mais longo primeiro só para
# documentar a intenção; a normalização testa os dois independentemente.
PREFIXOS_TINY_AUDITORIA = ("EKK", "EK")

# Categorias Unicode de pontuação/símbolo — viram espaço na normalização.
_CATEGORIAS_PONTUACAO = {"P", "S"}

_SO_DIGITOS = re.compile(r"\D+")
_NAO_ALFANUM = re.compile(r"[^0-9A-Za-z]+")


def normalizar_sku(valor: str) -> str:
    """
    Normalização de SKU SÓ PARA AUDITORIA (seção 11): caixa alta e remoção
    de tudo que não é `[0-9A-Za-z]` — espaço, hífen, ponto, barra, etc.

      - "KT-90395"  -> "KT90395"
      - "EKKT 90507" -> "EKKT90507"
      - "" / None    -> ""

    NÃO remove prefixo aqui (isso é `variantes_sku_tiny_para_auditoria`) e
    NÃO é fuzzy matching. Não é usada para gravar nem para o matching real.
    """
    if not valor:
        return ""
    return _NAO_ALFANUM.sub("", str(valor)).upper()


def variantes_sku_tiny_para_auditoria(sku_tiny_normalizado: str) -> set[str]:
    """
    A partir de um SKU do Tiny já normalizado (`normalizar_sku`), devolve
    o próprio valor MAIS as versões sem SOMENTE o prefixo inicial `EK` ou
    `EKK`:

      - "EKKT90507" -> {"EKKT90507", "KT90507", "T90507"}
      - "EK12345"   -> {"EK12345", "12345"}
      - "KT90395"   -> {"KT90395"}   (nenhum prefixo no início)

    O prefixo só é removido quando está no COMEÇO e sobra algo depois —
    "EK" no meio do SKU nunca é tocado.
    """
    variantes = {sku_tiny_normalizado}
    for prefixo in PREFIXOS_TINY_AUDITORIA:
        if sku_tiny_normalizado.startswith(prefixo) and len(sku_tiny_normalizado) > len(prefixo):
            variantes.add(sku_tiny_normalizado[len(prefixo):])
    return variantes


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


def similaridade_descricao(a: str, b: str) -> float:
    """
    Semelhança entre duas descrições JÁ normalizadas (`normalizar_descricao`),
    no intervalo [0.0, 1.0], via `difflib.SequenceMatcher`:

        SequenceMatcher(None, a, b, autojunk=False).ratio()

    - stdlib, sem dependência nova;
    - determinística (mesma entrada -> mesmo número);
    - `autojunk=False` desliga a heurística de "caractere lixo" do difflib,
      que só liga com sequências > 200 itens e tornaria o número sensível
      ao tamanho da string — indesejável para comparar descrições curtas.

    É medição exploratória: o resultado NÃO decide match. Arredondado a 4
    casas para a saída ficar estável entre execuções.
    """
    if not a or not b:
        return 0.0
    return round(SequenceMatcher(None, a, b, autojunk=False).ratio(), 4)


def _faixa_score(score: float) -> str:
    for limite, rotulo in FAIXAS_SCORE:
        if score >= limite:
            return rotulo
    return FAIXAS_SCORE[-1][1]


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
            "--amostra-sku",
            type=int,
            default=TAMANHO_AMOSTRA_SKU_PADRAO,
            help=f"Linhas na amostra de matches por SKU normalizado, seção 11 "
            f"(padrão: {TAMANHO_AMOSTRA_SKU_PADRAO}).",
        )
        parser.add_argument(
            "--top-ncm",
            type=int,
            default=TOP_NCM_PADRAO,
            help=f"Quantos NCMs mais frequentes listar (padrão: {TOP_NCM_PADRAO}).",
        )
        parser.add_argument(
            "--amostra-sim",
            type=int,
            default=TAMANHO_AMOSTRA_SIM_PADRAO,
            help=f"Linhas nas amostras de similaridade de descrição, seções 14/15 "
            f"(padrão: {TAMANHO_AMOSTRA_SIM_PADRAO}).",
        )
        parser.add_argument(
            "--score-perigo",
            type=float,
            default=SCORE_PERIGO_PADRAO,
            help=f"Só para a seção 15: score a partir do qual um par conta como "
            f"'quase igual' (padrão: {SCORE_PERIGO_PADRAO}). NÃO é threshold de produção.",
        )
        parser.add_argument(
            "--gap-perigo",
            type=float,
            default=GAP_PERIGO_PADRAO,
            help=f"Só para a seção 15: diferença máxima entre 1º e 2º melhor score "
            f"para o candidato ser considerado 'não destacado' (padrão: {GAP_PERIGO_PADRAO}).",
        )
        parser.add_argument(
            "--limite-sim",
            type=int,
            default=0,
            help="Processa no máximo N variações não identificadas na análise de "
            "similaridade (0 = todas). Útil para uma passada rápida.",
        )

    def handle(self, *args, **options):
        instancia = self._obter_instancia(options["instancia_slug"])
        tamanho_amostra = max(0, options["amostra"])
        tamanho_amostra_sku = max(0, options["amostra_sku"])
        tamanho_amostra_sim = max(0, options["amostra_sim"])
        score_perigo = options["score_perigo"]
        gap_perigo = options["gap_perigo"]
        limite_sim = max(0, options["limite_sim"])
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

        # --- seção 11: auditoria da regra de prefixo EK/EKK no SKU --------
        sku = self._auditar_sku_prefixo(variacoes, produtos_tiny)

        # --- seções 13–15: similaridade de descrição p/ o que sobrou -----
        identificadas_pks = (
            {v.pk for v, _ in inequivocos}
            | {v.pk for v, _ in sku["inequivocos"]}
            | {v.pk for v in variacoes if v.tiny_id}
        )
        similaridade = self._auditar_similaridade(
            variacoes,
            produtos_tiny,
            identificadas_pks,
            score_perigo=score_perigo,
            gap_perigo=gap_perigo,
            limite=limite_sim,
        )

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
        w("")
        self._imprimir_secao_sku(sku, tamanho_amostra_sku)
        w("")
        self._imprimir_secao_similaridade(similaridade, tamanho_amostra_sim)

    # -- seção 11: regra de prefixo EK/EKK no SKU ---------------------

    def _auditar_sku_prefixo(self, variacoes, produtos_tiny):
        """
        Mede (não aplica) a hipótese "SKU Tiny = prefixo EK/EKK + SKU
        fornecedor". Só leitura: monta índices em memória a partir das
        listas já carregadas e cruza cada match candidato com NCM e
        descrição normalizados para estimar falsos positivos.
        """
        # Índices do lado Tiny. `plain`: SKU normalizado como está.
        # `com_prefixo_removido`: só as variantes geradas ao tirar EK/EKK
        # do início — o que permite separar "casaria de qualquer jeito" de
        # "só casa removendo o prefixo".
        idx_plain = defaultdict(list)
        idx_prefixo = defaultdict(list)
        tiny_sku_vazio = 0
        for p in produtos_tiny:
            base = normalizar_sku(p.sku)
            if not base:
                tiny_sku_vazio += 1
                continue
            idx_plain[base].append(p)
            for variante in variantes_sku_tiny_para_auditoria(base) - {base}:
                idx_prefixo[variante].append(p)

        exato_como_hoje = 0  # SKU cru idêntico (mesmo critério da seção 3)
        casam_norm = []  # (variacao, [ProdutoTiny]) — união plain + prefixo
        so_via_prefixo = 0
        pares = []  # (variacao, ProdutoTiny) achatado, p/ métricas e amostra
        variacao_sku_vazio = 0

        skus_tiny_crus = {p.sku.strip() for p in produtos_tiny if p.sku and p.sku.strip()}

        for variacao in variacoes:
            if (variacao.sku or "").strip() and (variacao.sku or "").strip() in skus_tiny_crus:
                exato_como_hoje += 1

            s = normalizar_sku(variacao.sku)
            if not s:
                variacao_sku_vazio += 1
                continue

            plain = idx_plain.get(s, [])
            via_prefixo = idx_prefixo.get(s, [])
            if not plain and not via_prefixo:
                continue

            por_id = {}
            for p in plain:
                por_id[p.tiny_id] = p
            for p in via_prefixo:
                por_id.setdefault(p.tiny_id, p)
            candidatos = sorted(por_id.values(), key=lambda p: (p.sku, p.tiny_id))

            casam_norm.append((variacao, candidatos))
            if not plain:
                so_via_prefixo += 1
            for p in candidatos:
                pares.append((variacao, p))

        inequivocos = [(v, c[0]) for v, c in casam_norm if len(c) == 1]
        ambiguos = [(v, c) for v, c in casam_norm if len(c) > 1]
        tiny_ids_apontados = {p.tiny_id for _v, p in pares}

        ncm_igual = sum(
            1 for v, p in pares if normalizar_ncm(v.ncm) and normalizar_ncm(v.ncm) == normalizar_ncm(p.ncm)
        )
        desc_igual = sum(
            1
            for v, p in pares
            if normalizar_descricao(v.nome or v.produto.nome)
            and normalizar_descricao(v.nome or v.produto.nome) == normalizar_descricao(p.descricao)
        )
        ncm_diferente = sum(
            1 for v, p in pares if normalizar_ncm(v.ncm) != normalizar_ncm(p.ncm)
        )
        ncm_diferente_ambos_preenchidos = sum(
            1
            for v, p in pares
            if normalizar_ncm(v.ncm) and normalizar_ncm(p.ncm)
            and normalizar_ncm(v.ncm) != normalizar_ncm(p.ncm)
        )

        return {
            "exato_como_hoje": exato_como_hoje,
            "variacoes_que_casam": len(casam_norm),
            "so_via_prefixo": so_via_prefixo,
            "inequivocos": inequivocos,
            "ambiguos": ambiguos,
            "tiny_ids_apontados": len(tiny_ids_apontados),
            "pares": pares,
            "ncm_igual": ncm_igual,
            "desc_igual": desc_igual,
            "ncm_diferente": ncm_diferente,
            "ncm_diferente_ambos_preenchidos": ncm_diferente_ambos_preenchidos,
            "variacao_sku_vazio": variacao_sku_vazio,
            "tiny_sku_vazio": tiny_sku_vazio,
        }

    def _imprimir_secao_sku(self, sku, tamanho_amostra):
        w = self.stdout.write
        pares = sku["pares"]
        w("== 11. Regra histórica de SKU (prefixo EK/EKK no Tiny) — AUDITORIA ==")
        w(f"  a. Variações com SKU cru idêntico (= item 3) ..... {sku['exato_como_hoje']}")
        w(f"  b. Variações que casam pela normalização de SKU .. {sku['variacoes_que_casam']}")
        w(f"       (SKU normalizado, com/sem prefixo EK ou EKK)")
        w(f"  c.   ...que só casam removendo o prefixo EK/EKK .. {sku['so_via_prefixo']}")
        w(f"  d.   ...inequívocas (1 fornecedor -> 1 Tiny) ..... {len(sku['inequivocos'])}")
        w(f"  e.   ...ambíguas (>1 Tiny candidato) ............. {len(sku['ambiguos'])}")
        w(f"  f. Produtos Tiny distintos apontados ............. {sku['tiny_ids_apontados']}")
        w(f"  g. Pares (variação, Tiny) analisados ............. {len(pares)}")
        w(f"  h.   ...com NCM normalizado igual ................ {sku['ncm_igual']}")
        w(f"  i.   ...com descrição normalizada igual .......... {sku['desc_igual']}")
        w(f"  j.   ...com NCM normalizado DIFERENTE (falso +?) . {sku['ncm_diferente']}")
        w(f"         desses, NCM preenchido nos dois lados ..... {sku['ncm_diferente_ambos_preenchidos']}")
        w(f"  Variações sem SKU utilizável .................... {sku['variacao_sku_vazio']}")
        w(f"  Produtos Tiny sem SKU utilizável ............... {sku['tiny_sku_vazio']}")
        w("")
        w(f"== 12. Amostra de {tamanho_amostra} matches por SKU normalizado ==")
        if not pares:
            w("  (nenhum)")
            return
        for variacao, tiny in pares[:tamanho_amostra]:
            ncm_bate = "=" if normalizar_ncm(variacao.ncm) == normalizar_ncm(tiny.ncm) else "≠"
            w(
                f"  - {variacao.sku}  ->  {tiny.sku}  (tiny_id {tiny.tiny_id})\n"
                f"    SKU norm ...: {normalizar_sku(variacao.sku)}  ->  {normalizar_sku(tiny.sku)}\n"
                f"    desc forn ..: {variacao.nome or variacao.produto.nome}\n"
                f"    desc Tiny ..: {tiny.descricao}\n"
                f"    NCM ........: {variacao.ncm!r}  {ncm_bate}  {tiny.ncm!r}"
            )

    # -- seções 13–15: similaridade de descrição (exploratória) ------

    def _auditar_similaridade(
        self, variacoes, produtos_tiny, identificadas_pks, *, score_perigo, gap_perigo, limite
    ):
        """
        Para cada variação AINDA sem match inequívoco, mede a semelhança da
        descrição normalizada contra os produtos Tiny de MESMO NCM
        normalizado. Só leitura, só memória, sem transformar score em match.

        `identificadas_pks`: pks já resolvidos pelos sinais fortes (seção 5,
        seção 11d, ou `tiny_id` já gravado) — ficam de fora.
        """
        # Índice Tiny por NCM normalizado. Tiny sem NCM ou sem descrição
        # utilizável não entra: não dá para afirmar "mesmo NCM" nem comparar.
        tiny_por_ncm = defaultdict(list)  # ncm -> [(ProdutoTiny, descricao_norm)]
        for p in produtos_tiny:
            ncm = normalizar_ncm(p.ncm)
            desc = normalizar_descricao(p.descricao)
            if ncm and desc:
                tiny_por_ncm[ncm].append((p, desc))
        for ncm in tiny_por_ncm:
            tiny_por_ncm[ncm].sort(key=lambda par: par[0].tiny_id)

        pendentes = [
            v
            for v in variacoes
            if v.pk not in identificadas_pks and normalizar_descricao(v.nome or v.produto.nome)
        ]
        pendentes_sem_descricao = sum(
            1
            for v in variacoes
            if v.pk not in identificadas_pks and not normalizar_descricao(v.nome or v.produto.nome)
        )
        if limite:
            pendentes = pendentes[:limite]

        faixas = Counter()
        sem_ncm_forn = 0
        sem_candidato_mesmo_ncm = 0
        resultados = []  # dict por variação analisada

        for variacao in pendentes:
            alvo = normalizar_descricao(variacao.nome or variacao.produto.nome)
            ncm_forn = normalizar_ncm(variacao.ncm)
            if not ncm_forn:
                sem_ncm_forn += 1
                faixas["sem NCM no fornecedor"] += 1
                continue

            candidatos = tiny_por_ncm.get(ncm_forn, [])
            if not candidatos:
                sem_candidato_mesmo_ncm += 1
                faixas["sem candidato com mesmo NCM"] += 1
                continue

            melhor, s1, segundo, s2 = self._top2_por_similaridade(alvo, candidatos)
            gap = round(s1 - s2, 4) if segundo is not None else None
            # quantos candidatos de mesmo NCM chegam ao patamar "quase igual".
            # Só recontado (sem poda) quando o melhor já passou do corte —
            # subconjunto pequeno.
            if s1 >= score_perigo:
                n_quase_iguais = sum(
                    1
                    for _tiny, desc in candidatos
                    if similaridade_descricao(alvo, desc) >= score_perigo
                )
            else:
                n_quase_iguais = 0
            faixas[_faixa_score(s1)] += 1
            resultados.append(
                {
                    "variacao": variacao,
                    "melhor": melhor,
                    "s1": s1,
                    "segundo": segundo,
                    "s2": s2 if segundo is not None else None,
                    "gap": gap,
                    "n_candidatos": len(candidatos),
                    "n_quase_iguais": n_quase_iguais,
                }
            )

        resultados.sort(key=lambda r: (-r["s1"], r["variacao"].sku, r["variacao"].pk))

        perigosos = [
            r
            for r in resultados
            if r["s1"] >= score_perigo
            and (
                (r["gap"] is not None and r["gap"] < gap_perigo)
                or r["n_quase_iguais"] > 1
            )
        ]

        return {
            "analisadas": len(resultados),
            "pendentes_total": len(pendentes),
            "pendentes_sem_descricao": pendentes_sem_descricao,
            "identificadas": len(identificadas_pks),
            "sem_ncm_forn": sem_ncm_forn,
            "sem_candidato_mesmo_ncm": sem_candidato_mesmo_ncm,
            "faixas": faixas,
            "resultados": resultados,
            "perigosos": perigosos,
            "score_perigo": score_perigo,
            "gap_perigo": gap_perigo,
        }

    @staticmethod
    def _top2_por_similaridade(alvo, candidatos):
        """
        Devolve (melhor_tiny, s1, segundo_tiny, s2) para `alvo` contra
        `candidatos` = lista de (ProdutoTiny, descricao_norm), já ordenada
        de forma determinística. Usa quick_ratio/real_quick_ratio (limites
        superiores baratos do difflib) para pular o ratio() completo quando
        ele não pode superar o 2º melhor corrente.
        """
        sm = SequenceMatcher(None, autojunk=False)
        sm.set_seq2(alvo)
        melhor_tiny, s1 = None, 0.0
        segundo_tiny, s2 = None, 0.0
        for tiny, desc in candidatos:
            sm.set_seq1(desc)
            if sm.real_quick_ratio() <= s2 or sm.quick_ratio() <= s2:
                continue
            r = round(sm.ratio(), 4)
            if r > s1:
                melhor_tiny, s1, segundo_tiny, s2 = tiny, r, melhor_tiny, s1
            elif r > s2:
                segundo_tiny, s2 = tiny, r
        if melhor_tiny is None:
            # nenhum candidato teve sobreposição — devolve o 1º como melhor 0.0
            melhor_tiny = candidatos[0][0]
        return melhor_tiny, s1, segundo_tiny, s2

    def _imprimir_secao_similaridade(self, sim, tamanho_amostra):
        w = self.stdout.write
        w("== 13. Similaridade de descrição (EXPLORATÓRIA — nada vira match) ==")
        w("  Algoritmo: difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()")
        w("  Candidatos: só produtos Tiny com o MESMO NCM normalizado (NCM sozinho não casa).")
        w(f"  Variações já identificadas por sinal forte ...... {sim['identificadas']}")
        w(f"  Variações pendentes analisadas .................. {sim['analisadas']}")
        w(f"  Pendentes sem descrição utilizável .............. {sim['pendentes_sem_descricao']}")
        w(f"  Pendentes sem NCM no fornecedor (fora do filtro)  {sim['sem_ncm_forn']}")
        w(f"  Pendentes sem nenhum Tiny de mesmo NCM .......... {sim['sem_candidato_mesmo_ncm']}")
        w("")
        w("  Distribuição do MELHOR score por variação pendente:")
        rotulos = [r for _l, r in FAIXAS_SCORE] + [
            "sem candidato com mesmo NCM",
            "sem NCM no fornecedor",
        ]
        for rotulo in rotulos:
            w(f"    {rotulo:<28} {sim['faixas'].get(rotulo, 0):>8}")
        w("")
        w(f"== 14. Amostra dos {tamanho_amostra} maiores scores ==")
        if not sim["resultados"]:
            w("  (nenhum)")
        else:
            for r in sim["resultados"][:tamanho_amostra]:
                self._linha_similaridade(r)
        w("")
        w(
            f"== 15. Casos de risco de falso positivo "
            f"(score >= {sim['score_perigo']} e gap < {sim['gap_perigo']}, "
            f"ou >1 Tiny quase igual) =="
        )
        w(f"  Total de casos de risco ........................ {len(sim['perigosos'])}")
        if not sim["perigosos"]:
            w("  (nenhum)")
        else:
            for r in sim["perigosos"][:tamanho_amostra]:
                self._linha_similaridade(r)

    def _linha_similaridade(self, r):
        w = self.stdout.write
        v = r["variacao"]
        melhor = r["melhor"]
        s2 = "-" if r["s2"] is None else f"{r['s2']:.4f}"
        gap = "-" if r["gap"] is None else f"{r['gap']:.4f}"
        w(
            f"  - {v.sku}  ->  {melhor.sku}  (tiny_id {melhor.tiny_id})\n"
            f"    score ......: {r['s1']:.4f}   2º: {s2}   gap: {gap}   "
            f"candidatos mesmo NCM: {r['n_candidatos']}   quase iguais: {r['n_quase_iguais']}\n"
            f"    desc forn ..: {v.nome or v.produto.nome}\n"
            f"    desc Tiny ..: {melhor.descricao}\n"
            f"    NCM ........: {v.ncm!r}  vs  {melhor.ncm!r}\n"
            f"    dim forn ...: {self._dimensoes(v)}\n"
            f"    dim Tiny ...: {self._dimensoes(melhor)}"
        )

    @staticmethod
    def _dimensoes(obj):
        """
        Dimensões/peso JÁ presentes no modelo local (Variacao e ProdutoTiny
        têm os mesmos campos, nas mesmas unidades — cm/kg). Só exibição:
        ajuda a explicar um score alto sem servir de critério. `cor`,
        `capacidade` e `tamanho` existem na Variacao mas NÃO no ProdutoTiny,
        então não dá para cruzar — ficam de fora.
        """
        partes = []
        lxaxc = [getattr(obj, campo, None) for campo in ("largura", "altura", "comprimento")]
        if any(v is not None for v in lxaxc):
            partes.append("x".join("?" if v is None else f"{v:g}" for v in lxaxc) + "cm")
        if getattr(obj, "diametro", None) is not None:
            partes.append(f"Ø{obj.diametro:g}cm")
        if getattr(obj, "peso_bruto", None) is not None:
            partes.append(f"{obj.peso_bruto:g}kg br")
        if getattr(obj, "peso_liquido", None) is not None:
            partes.append(f"{obj.peso_liquido:g}kg líq")
        return " ".join(partes) or "(sem dimensões)"

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
