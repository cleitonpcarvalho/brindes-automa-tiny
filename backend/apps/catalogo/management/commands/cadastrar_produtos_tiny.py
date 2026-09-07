import json
from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError
from django.db.models import Count
from django.utils import timezone

from apps.instancias.constants import Fornecedor
from apps.instancias.models import Instancia
from apps.instancias.tiny_client import TinyApiClient

from ...models import StatusVariacao, Variacao

# Regra do passo 6: nenhum limite foi dado pelo cliente para quantos
# anexos (imagens) mandar por produto — escolhido por nós. 5 cobre a
# imagem principal + a galeria típica dos fornecedores sem inflar o
# payload à toa (documentado no README).
MAX_ANEXOS_POR_PRODUTO = 5

# Ações possíveis por Variacao (impressas no relatório).
CRIAR = "SERIA CRIADO"
VINCULAR = "JA EXISTE NO TINY / SERIA VINCULADO"
BLOQUEADO = "BLOQUEADO"
JA_CADASTRADO = "JA CADASTRADO (ignorado)"


@dataclass
class Decisao:
    acao: str
    motivo: str
    tiny_existente: dict | None = None
    payload: dict | None = None


class Command(BaseCommand):
    """
    Cadastra no Tiny as variações pendentes de uma instância (uma Variacao = um produto).

    Modelo operacional definitivo — determinístico por SKU:
      SKU do fornecedor == SKU no espelho (Variacao.sku) == SKU no Tiny.
    A correspondência com o catálogo do Tiny é feita EXCLUSIVAMENTE por SKU
    exato (`TinyApiClient.buscar_produto_por_sku`). Este fluxo NUNCA
    consulta o espelho `ProdutoTiny` e NUNCA casa por nome, NCM, descrição,
    fuzzy ou qualquer heurística.

    Proteções antes do piloto real:
      - `--dry-run`: só GET no Tiny, nenhum POST/PUT/PATCH/DELETE, nenhuma
        escrita local; monta e imprime o payload exato que seria enviado.
      - `--fornecedor` / `--skus`: seleção explícita (não depende da ordem
        por id).
      - SKU exato já existe no Tiny e a Variacao não tem vínculo confirmado
        -> BLOQUEADO (não assume controle de produto preexistente). Só
        vincula se o operador confirmar via `--vincular-skus`.
      - Mesmo SKU em Variacao de mais de um fornecedor na instância ->
        BLOQUEADO.
      - Regra P@ (produto descontinuado) e estoque <= 0 -> BLOQUEADO.
      - Resposta do POST /produtos sem id utilizável -> reconsulta por SKU
        exato; se ainda ambígua, marca ERRO (nunca "cadastrado" sem
        confirmação inequívoca).

    Idempotente e retomável: cada variação processada com sucesso sai de
    `pendente` (vira `cadastrado` ou `erro`) e não é mais selecionada pela
    consulta padrão.
    """

    help = "Cadastra no Tiny as variações pendentes de uma instância (uma Variacao = um produto)."

    def add_arguments(self, parser):
        parser.add_argument("instancia_slug")
        parser.add_argument(
            "--limite", type=int, default=None, help="Máximo de variações a processar nesta execução."
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Não escreve NADA (nem no Tiny, nem no banco). Faz só os GET de "
            "verificação e imprime o payload exato que seria enviado.",
        )
        parser.add_argument(
            "--fornecedor",
            choices=[f.value for f in Fornecedor],
            default=None,
            help="Restringe a um fornecedor.",
        )
        parser.add_argument(
            "--skus",
            default=None,
            help="Lista explícita de SKUs (separados por vírgula). Processa exatamente "
            "esses SKUs (com --fornecedor, só dessa combinação), independente do status "
            "— mas as regras de bloqueio continuam valendo.",
        )
        parser.add_argument(
            "--vincular-skus",
            default=None,
            help="Lista de SKUs (separados por vírgula) cujo produto preexistente no "
            "Tiny o operador CONFIRMA que pertence a esta automação — só para esses o "
            "vínculo automático é permitido.",
        )

    # -- entrada --------------------------------------------------------

    def handle(self, *args, **options):
        instancia = self._obter_instancia(options["instancia_slug"])
        self._validar_configuracao(instancia)

        dry_run = options["dry_run"]
        fornecedor = options["fornecedor"]
        skus = _lista(options["skus"])
        vincular_skus = set(_lista(options["vincular_skus"]))

        w = self.stdout.write
        if dry_run:
            w(self.style.WARNING("DRY-RUN — nenhuma escrita no Tiny e nenhuma alteração local."))

        variacoes = self._fila(instancia, fornecedor, skus, options["limite"])

        if skus:
            achados = {v.sku for v in variacoes}
            faltando = [s for s in skus if s not in achados]
            if faltando:
                w(self.style.WARNING(f"SKUs de --skus não encontrados no espelho: {faltando}"))

        colisao_por_sku = self._colisoes_cross_fornecedor(instancia)

        # `somente_leitura=dry_run` é a trava dura: nesse modo o cliente
        # levanta antes de qualquer POST/PUT sair da máquina.
        cliente = TinyApiClient(instancia, somente_leitura=dry_run)

        contagem = {CRIAR: 0, VINCULAR: 0, BLOQUEADO: 0, JA_CADASTRADO: 0, "erro": 0}
        sem_ncm = 0

        for variacao in variacoes:
            decisao = self._avaliar(cliente, instancia, variacao, colisao_por_sku, vincular_skus)
            self._imprimir_decisao(variacao, decisao, dry_run)
            if decisao.acao == CRIAR and not (variacao.ncm or "").strip():
                sem_ncm += 1

            if dry_run or decisao.acao in (BLOQUEADO, JA_CADASTRADO):
                contagem[decisao.acao] += 1
                continue

            try:
                if decisao.acao == CRIAR:
                    self._executar_criacao(cliente, variacao, decisao.payload)
                    contagem[CRIAR] += 1
                elif decisao.acao == VINCULAR:
                    self._marcar_cadastrada(variacao, decisao.tiny_existente["id"], preco_publicado=None)
                    contagem[VINCULAR] += 1
            except Exception as exc:  # uma variação ruim não pode travar o lote
                contagem["erro"] += 1
                self._marcar_erro(variacao, str(exc))
                self.stderr.write(f"[{variacao.sku}] erro: {exc}")

        w("")
        w(self.style.SUCCESS(
            f"{'(dry-run) ' if dry_run else ''}"
            f"Criadas/seriam criadas: {contagem[CRIAR]} | vinculadas: {contagem[VINCULAR]} | "
            f"bloqueadas: {contagem[BLOQUEADO]} | já cadastradas: {contagem[JA_CADASTRADO]} | "
            f"erros: {contagem['erro']}"
        ))
        if sem_ncm:
            w(self.style.WARNING(
                f"{sem_ncm} variação(ões) na ação CRIAR estão SEM NCM — pendência fiscal a "
                "cobrar do fornecedor (não bloqueia o cadastro)."
            ))
        if not dry_run and contagem[CRIAR]:
            w(
                f"{contagem[CRIAR]} produto(s) criado(s) com estoque inicial = valor atual da "
                f"Variacao. Ajustes futuros de estoque: `atualizar_estoque_tiny {instancia.slug}`."
            )

    # -- seleção -------------------------------------------------------

    def _fila(self, instancia, fornecedor, skus, limite):
        qs = Variacao.objects.filter(produto__instancia=instancia).select_related("produto")
        if fornecedor:
            qs = qs.filter(produto__fornecedor=fornecedor)
        if skus:
            qs = qs.filter(sku__in=skus)  # status ignorado de propósito: permite retry de ERRO
        else:
            qs = qs.filter(status=StatusVariacao.PENDENTE)
        qs = qs.order_by("produto__fornecedor", "sku", "id")
        if limite:
            qs = qs[:limite]
        return list(qs)

    def _colisoes_cross_fornecedor(self, instancia):
        """{sku: [fornecedores]} para SKUs que aparecem em mais de um fornecedor na instância."""
        skus_colididos = (
            Variacao.objects.filter(produto__instancia=instancia)
            .exclude(sku="")
            .values("sku")
            .annotate(n=Count("produto__fornecedor", distinct=True))
            .filter(n__gt=1)
            .values_list("sku", flat=True)
        )
        skus_colididos = list(skus_colididos)
        if not skus_colididos:
            return {}
        mapa: dict[str, list[str]] = {}
        for linha in (
            Variacao.objects.filter(produto__instancia=instancia, sku__in=skus_colididos)
            .values("sku", "produto__fornecedor")
            .distinct()
        ):
            mapa.setdefault(linha["sku"], []).append(linha["produto__fornecedor"])
        return {sku: sorted(set(forn)) for sku, forn in mapa.items()}

    # -- decisão por variação ----------------------------------------

    def _avaliar(self, cliente, instancia, variacao, colisao_por_sku, vincular_skus) -> Decisao:
        sku = (variacao.sku or "").strip()
        if not sku:
            return Decisao(BLOQUEADO, "SKU vazio no espelho")

        if variacao.status == StatusVariacao.DESCONTINUADO or (
            variacao.produto_id and variacao.produto.descontinuado
        ):
            return Decisao(BLOQUEADO, "regra P@ / produto descontinuado — nunca vai ao Tiny")

        if variacao.estoque <= 0 or variacao.status == StatusVariacao.AGUARDANDO:
            return Decisao(BLOQUEADO, f"estoque <= 0 (estoque={variacao.estoque}) — aguarda reposição")

        if variacao.status == StatusVariacao.CADASTRADO and (variacao.tiny_id or "").strip():
            return Decisao(JA_CADASTRADO, f"já vinculada (tiny_id={variacao.tiny_id})")

        if sku in colisao_por_sku:
            forns = ", ".join(colisao_por_sku[sku])
            return Decisao(BLOQUEADO, f"mesmo SKU em mais de um fornecedor nesta instância: {forns}")

        existente = cliente.buscar_produto_por_sku(sku)  # GET — permitido no dry-run
        if existente:
            if sku in vincular_skus:
                return Decisao(
                    VINCULAR, f"vínculo confirmado pelo operador (--vincular-skus); tiny_id={existente.get('id')}",
                    tiny_existente=existente,
                )
            return Decisao(
                BLOQUEADO,
                f"SKU já existe no Tiny (id={existente.get('id')}) e não possui vínculo confirmado — "
                f"revisar manualmente e, se for nosso, reprocessar com --vincular-skus",
                tiny_existente=existente,
            )

        return Decisao(CRIAR, "SKU não existe no Tiny", payload=montar_payload_produto(variacao, instancia))

    def _executar_criacao(self, cliente, variacao, payload):
        resultado = cliente.criar_produto(payload)
        tiny_id = _id_do_resultado(resultado)
        if not tiny_id:
            # Resposta ambígua: reconsulta pelo SKU EXATO antes de decidir.
            confirmado = cliente.buscar_produto_por_sku(variacao.sku)
            tiny_id = _id_do_resultado(confirmado) if confirmado else None
        if not tiny_id:
            raise CommandError(
                f"POST /produtos não devolveu um id utilizável e a reconsulta por SKU não "
                f"confirmou — NÃO marcado como cadastrado. Resposta: {resultado!r}"
            )
        self._marcar_cadastrada(variacao, tiny_id, preco_publicado=variacao.preco)

    # -- persistência local ----------------------------------------

    @staticmethod
    def _marcar_cadastrada(variacao, tiny_id, *, preco_publicado):
        variacao.tiny_id = str(tiny_id)
        variacao.status = StatusVariacao.CADASTRADO
        variacao.cadastrado_em = timezone.now()
        variacao.ultimo_erro = ""
        campos = ["tiny_id", "status", "cadastrado_em", "ultimo_erro", "atualizado_em"]
        if preco_publicado is not None:
            # O payload de criação levou `precos.preco` = este valor, então o
            # preço de venda no Tiny está sincronizado com este `preco`.
            variacao.preco_tiny_sincronizado = preco_publicado
            campos.append("preco_tiny_sincronizado")
        variacao.save(update_fields=campos)

    @staticmethod
    def _marcar_erro(variacao, mensagem):
        variacao.status = StatusVariacao.ERRO
        variacao.ultimo_erro = mensagem
        variacao.save(update_fields=["status", "ultimo_erro", "atualizado_em"])

    # -- saída --------------------------------------------------------

    def _imprimir_decisao(self, variacao, decisao, dry_run):
        w = self.stdout.write
        fornecedor = variacao.produto.fornecedor if variacao.produto_id else "?"
        estilo = {
            CRIAR: self.style.SUCCESS,
            VINCULAR: self.style.WARNING,
            BLOQUEADO: self.style.ERROR,
            JA_CADASTRADO: self.style.NOTICE,
        }.get(decisao.acao, str)
        w(estilo(f"[{fornecedor}] {variacao.sku!r} -> {decisao.acao}: {decisao.motivo}"))
        if dry_run and decisao.acao == CRIAR and decisao.payload is not None:
            w("    payload que seria enviado ao POST /produtos:")
            for linha in json.dumps(decisao.payload, ensure_ascii=False, indent=2).splitlines():
                w("    " + linha)

    def _obter_instancia(self, slug):
        try:
            return Instancia.objects.get(slug=slug)
        except Instancia.DoesNotExist:
            raise CommandError(f"Instância com slug '{slug}' não encontrada.") from None

    def _validar_configuracao(self, instancia):
        faltando = []
        if instancia.tiny_origem_padrao is None:
            faltando.append("tiny_origem_padrao")
        if not instancia.tiny_unidade_medida_padrao:
            faltando.append("tiny_unidade_medida_padrao")
        if faltando:
            raise CommandError(
                f"Configure {', '.join(faltando)} na instância '{instancia.slug}' "
                "(admin) antes de cadastrar produtos."
            )
        if not instancia.access_token:
            raise CommandError(f"Instância '{instancia.slug}' não está conectada ao Tiny.")


# ---------------------------------------------------------------------------


def _lista(valor):
    return [s.strip() for s in (valor or "").split(",") if s.strip()]


def _id_do_resultado(resultado):
    """
    Extrai de forma robusta o id do produto criado. Aceita `id` no topo ou
    aninhado em wrappers comuns; rejeita valores vazios / '0' / None.
    """
    if not isinstance(resultado, dict):
        return None
    if _id_valido(resultado.get("id")):
        return resultado["id"]
    for wrapper in ("produto", "data", "retorno", "registro"):
        sub = resultado.get(wrapper)
        if isinstance(sub, dict) and _id_valido(sub.get("id")):
            return sub["id"]
    return None


def _id_valido(valor):
    if valor is None:
        return False
    texto = str(valor).strip()
    return bool(texto) and texto.lower() not in ("0", "none", "null", "")


def montar_payload_produto(variacao, instancia):
    """
    Regra do cliente: cada Variacao vira um produto Simples ('S') próprio no
    Tiny, com o SKU do fornecedor como código. Contrato conferido em
    https://api-docs.erp.olist.com/api-reference/produtos/criar-produto.md
    (passo 6): só sku, descricao e tipo são obrigatórios — todo o resto,
    incluindo ncm, é nullable.

    ESTOQUE: o produto nasce no Tiny já com o estoque correto — `estoque`
    leva `controlar=true` e `inicial` = estoque atual da Variacao. A fila só
    contém variações com `estoque > 0` (estoque <= 0 é BLOQUEADO), então
    `inicial` é sempre positivo aqui.
    """
    payload = {
        "sku": variacao.sku,
        "descricao": variacao.nome,
        "tipo": "S",
        "unidade": instancia.tiny_unidade_medida_padrao,
        "origem": instancia.tiny_origem_padrao,
        "ncm": variacao.ncm or None,
        # Regra do cliente nº 4: preço do fornecedor, sem margem (ver
        # Variacao.preco_venda_tiny). float() de um Decimal de 2 casas.
        "precos": {"preco": float(variacao.preco_venda_tiny)},
        "estoque": {"controlar": True, "inicial": float(variacao.estoque)},
    }

    dimensoes = _montar_dimensoes(variacao)
    if dimensoes:
        payload["dimensoes"] = dimensoes

    anexos = _montar_anexos(variacao)
    if anexos:
        payload["anexos"] = anexos

    garantia = (variacao.atributos or {}).get("garantia_do_produto")
    if garantia:
        payload["garantia"] = garantia

    return payload


def _montar_dimensoes(variacao):
    """
    Só inclui `dimensoes` se ao menos um campo foi normalizado.

    PENDÊNCIA: os nomes exatos das chaves de `dimensoes` no POST /produtos
    (`comprimento` vs `profundidade`, `pesoLiquido`/`pesoBruto` vs `peso`)
    ainda não foram confirmados contra a API real. Se um nome estiver
    errado, o Tiny ou recusa (400, cai como erro, produto NÃO criado) ou
    ignora a chave (produto criado sem essa dimensão) — os dois casos são
    recuperáveis, mas confira antes do piloto.
    """
    campos = {
        "largura": variacao.largura,
        "altura": variacao.altura,
        "comprimento": variacao.comprimento,
        "diametro": variacao.diametro,
        "pesoLiquido": variacao.peso_liquido,
        "pesoBruto": variacao.peso_bruto,
    }
    preenchidos = {k: v for k, v in campos.items() if v is not None}
    return preenchidos or None


def _montar_anexos(variacao):
    """
    Imagens já normalizadas no espelho (`Variacao.imagens`) viram anexos
    externos — o Tiny só guarda o link. Limitado a MAX_ANEXOS_POR_PRODUTO.
    """
    urls = [u for u in (variacao.imagens or []) if u][:MAX_ANEXOS_POR_PRODUTO]
    return [{"url": url, "externo": True} for url in urls]
