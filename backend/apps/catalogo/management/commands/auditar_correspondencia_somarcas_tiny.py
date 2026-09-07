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
TAMANHO_AMOSTRA_SKU_PADRAO = 50
TOP_NCM_PADRAO = 20

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

    def handle(self, *args, **options):
        instancia = self._obter_instancia(options["instancia_slug"])
        tamanho_amostra = max(0, options["amostra"])
        tamanho_amostra_sku = max(0, options["amostra_sku"])
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
