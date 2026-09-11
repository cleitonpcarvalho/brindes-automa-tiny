import json

from django.core.management.base import BaseCommand, CommandError

from apps.instancias.constants import Fornecedor
from apps.instancias.models import Instancia
from apps.instancias.tiny_client import TinyApiClient
from apps.sincronizacao.locks import lock_instancia_tiny

from ...tiny_sync import (
    ACAO_BLOQUEADO,
    ACAO_ATUALIZAR_EXISTENTE,
    ACAO_CRIAR,
    ACAO_JA_CADASTRADO,
    ACAO_VINCULAR,
    MAX_ANEXOS_POR_PRODUTO,
    Decisao,
    EventosSincronizacao,
    ResultadoSincronizacao,
    _processar_variacao,
    colisoes_cross_fornecedor,
    fila_cadastro,
    imagens_utilizaveis,
    montar_payload_produto,
    tiny_fornecedor_id_de,
)

# Rótulos de UI das ações — o comando imprime estes; a lógica de decisão
# (neutra) vive em `apps.catalogo.tiny_sync`.
_ROTULO_ACAO = {
    ACAO_ATUALIZAR_EXISTENTE: "JA EXISTE NO TINY / SERIA ATUALIZADO",
    ACAO_CRIAR: "SERIA CRIADO",
    ACAO_VINCULAR: "JA EXISTE NO TINY / SERIA VINCULADO",
    ACAO_BLOQUEADO: "BLOQUEADO",
    ACAO_JA_CADASTRADO: "JA CADASTRADO (ignorado)",
}

# Nomes históricos re-exportados para compatibilidade (imports externos e
# testes). A implementação real está em `apps.catalogo.tiny_sync`.
__all__ = [
    "Command",
    "Decisao",
    "montar_payload_produto",
    "imagens_utilizaveis",
    "MAX_ANEXOS_POR_PRODUTO",
]


class Command(BaseCommand):
    """
    Cadastra no Tiny as variações pendentes de uma instância (uma Variacao = um produto).

    Modelo operacional determinístico pela identidade central Tiny:
      XBZ: composto no Tiny, código X... estável no espelho;
      demais fornecedores: SKU do espelho no Tiny, sem reconciliação automática.
    A correspondência com o catálogo do Tiny é feita EXCLUSIVAMENTE por SKU
    exato (`TinyApiClient.buscar_produto_por_sku`). Este fluxo NUNCA
    consulta o espelho `ProdutoTiny` e NUNCA casa por nome, NCM, descrição,
    fuzzy ou qualquer heurística.

    As regras (proteções, decisão, criação, marcação) vivem em
    `apps.catalogo.tiny_sync` — este comando é só a interface de linha de
    comando; a task Celera de sincronização em massa usa exatamente a mesma
    implementação.

    Proteções:
      - `--dry-run`: só GET no Tiny, nenhum POST/PUT/PATCH/DELETE, nenhuma
        escrita local; monta e imprime o payload exato que seria enviado.
      - `--fornecedor` / `--skus`: seleção explícita.
      - SKU exato já existe no Tiny e a Variacao não tem vínculo confirmado
        -> BLOQUEADO. Só vincula com `--vincular-skus`.
      - Mesmo SKU em Variacao de mais de um fornecedor -> BLOQUEADO.
      - Regra P@ (descontinuado) e estoque <= 0 -> BLOQUEADO.

    NÃO sincroniza imagens — isso é `sincronizar_imagens_tiny` (ou o
    orquestrador `sincronizar_com_tiny`).

    Idempotente e retomável: cada variação processada com sucesso sai de
    `pendente`.
    """

    help = "Cadastra no Tiny as variações pendentes de uma instância (uma Variacao = um produto)."

    def add_arguments(self, parser):
        parser.add_argument("instancia_slug")
        parser.add_argument("--limite", type=int, default=None)
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Não escreve NADA (nem no Tiny, nem no banco). Só GET de verificação "
            "e imprime o payload exato que seria enviado.",
        )
        parser.add_argument(
            "--fornecedor", choices=[f.value for f in Fornecedor], default=None
        )
        parser.add_argument(
            "--skus",
            default=None,
            help="Lista explícita de SKUs (por vírgula). Processa exatamente esses, "
            "independente do status — as regras de bloqueio continuam valendo.",
        )
        parser.add_argument(
            "--vincular-skus",
            default=None,
            help="SKUs (por vírgula) cujo produto preexistente no Tiny o operador "
            "CONFIRMA que pertence a esta automação.",
        )

    def handle(self, *args, **options):
        instancia = self._obter_instancia(options["instancia_slug"])
        if options["dry_run"]:
            return self._handle(*args, instancia=instancia, **options)
        with lock_instancia_tiny(instancia.id) as adquirida:
            if not adquirida:
                raise CommandError("A conta Tiny desta instância está ocupada por outra propagação.")
            return self._handle(*args, instancia=instancia, **options)

    def _handle(self, *args, instancia, **options):
        self._validar_configuracao(instancia)

        dry_run = options["dry_run"]
        skus = _lista(options["skus"])
        vincular_skus = set(_lista(options["vincular_skus"]))

        w = self.stdout.write
        if dry_run:
            w(self.style.WARNING("DRY-RUN — nenhuma escrita no Tiny e nenhuma alteração local."))

        variacoes = fila_cadastro(
            instancia, fornecedor=options["fornecedor"], skus=skus or None, limite=options["limite"]
        )
        if skus:
            faltando = [s for s in skus if s not in {v.sku for v in variacoes}]
            if faltando:
                w(self.style.WARNING(f"SKUs de --skus não encontrados no espelho: {faltando}"))

        colisoes = colisoes_cross_fornecedor(instancia)
        cliente = TinyApiClient(instancia, somente_leitura=dry_run)

        resultado = ResultadoSincronizacao(fila=len(variacoes))
        eventos = _EventosCommand(self, dry_run)
        # Id do contato-fornecedor no Tiny, resolvido UMA vez por fornecedor
        # (a fila vem ordenada por fornecedor) — nunca uma consulta por SKU.
        tiny_fornecedor_ids: dict[str, int | None] = {}

        for variacao in variacoes:
            fornecedor_da_variacao = variacao.produto.fornecedor if variacao.produto_id else None
            if fornecedor_da_variacao not in tiny_fornecedor_ids:
                tiny_fornecedor_ids[fornecedor_da_variacao] = tiny_fornecedor_id_de(
                    instancia, fornecedor_da_variacao
                )
            _processar_variacao(
                cliente,
                instancia,
                variacao,
                colisoes,
                vincular_skus=vincular_skus,
                tiny_fornecedor_id=tiny_fornecedor_ids[fornecedor_da_variacao],
                resultado=resultado,
                eventos=eventos,
                dry_run=dry_run,
                sincronizar_imagens=False,
            )

        w("")
        w(self.style.SUCCESS(
            f"{'(dry-run) ' if dry_run else ''}"
            f"Criadas/seriam criadas: {resultado.criadas} | vinculadas: {resultado.vinculadas} | "
            f"bloqueadas: {resultado.bloqueadas} | já cadastradas: {resultado.ja_cadastradas} | "
            f"erros: {resultado.erros}"
        ))
        sem_ncm = eventos.sem_ncm
        if sem_ncm:
            w(self.style.WARNING(
                f"{sem_ncm} variação(ões) na ação CRIAR estão SEM NCM — pendência fiscal a "
                "cobrar do fornecedor (não bloqueia o cadastro)."
            ))
        if not dry_run and resultado.criadas:
            w(
                f"{resultado.criadas} produto(s) criado(s) com estoque inicial = valor atual da "
                f"Variacao. Ajustes futuros de estoque: `atualizar_estoque_tiny {instancia.slug}`."
            )

    # -- saída --------------------------------------------------------

    def _imprimir_decisao(self, variacao, decisao: Decisao, dry_run):
        w = self.stdout.write
        fornecedor = variacao.produto.fornecedor if variacao.produto_id else "?"
        estilo = {
            ACAO_CRIAR: self.style.SUCCESS,
            ACAO_VINCULAR: self.style.WARNING,
            ACAO_BLOQUEADO: self.style.ERROR,
            ACAO_JA_CADASTRADO: self.style.NOTICE,
        }.get(decisao.acao, str)
        rotulo = _ROTULO_ACAO.get(decisao.acao, decisao.acao)
        w(estilo(f"[{fornecedor}] {variacao.sku!r} -> {rotulo}: {decisao.motivo}"))
        if dry_run and decisao.acao == ACAO_CRIAR and decisao.payload is not None:
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


def _lista(valor):
    return [s.strip() for s in (valor or "").split(",") if s.strip()]


class _EventosCommand(EventosSincronizacao):
    def __init__(self, command, dry_run):
        self.command = command
        self.dry_run = dry_run
        self.sem_ncm = 0

    def variacao_avaliada(self, variacao, decisao):
        self.command._imprimir_decisao(variacao, decisao, self.dry_run)
        if decisao.acao == ACAO_CRIAR and not (variacao.ncm or "").strip():
            self.sem_ncm += 1

    def variacao_erro(self, variacao, exc):
        self.command.stderr.write(f"[{variacao.sku}] erro: {exc}")
