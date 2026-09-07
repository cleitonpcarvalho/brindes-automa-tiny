from django.core.management.base import BaseCommand, CommandError

from apps.instancias.constants import Fornecedor
from apps.instancias.models import Instancia
from apps.instancias.tiny_client import TinyApiClient

from ...tiny_sync import (
    ACAO_BLOQUEADO,
    ACAO_CRIAR,
    ACAO_JA_CADASTRADO,
    ACAO_VINCULAR,
    EventosSincronizacao,
    estimar_cadastro,
    executar_sincronizacao_tiny,
)


class _EventosStdout(EventosSincronizacao):
    def __init__(self, comando, dry_run):
        self.c = comando
        self.dry_run = dry_run

    def inicio(self, *, total_fila):
        self.c.stdout.write(self.c.style.NOTICE(f"Fila: {total_fila} variação(ões) pendente(s)/erro."))

    def variacao_avaliada(self, variacao, decisao):
        rotulo = {
            ACAO_CRIAR: "SERIA CRIADO" if self.dry_run else "CRIAR",
            ACAO_VINCULAR: "VINCULAR",
            ACAO_BLOQUEADO: "BLOQUEADO",
            ACAO_JA_CADASTRADO: "JÁ CADASTRADO",
        }.get(decisao.acao, decisao.acao)
        self.c.stdout.write(f"[{variacao.produto.fornecedor}] {variacao.sku!r} -> {rotulo}: {decisao.motivo}")

    def variacao_criada(self, variacao, tiny_id):
        self.c.stdout.write(self.c.style.SUCCESS(f"    criado no Tiny (id={tiny_id})"))

    def variacao_erro(self, variacao, exc):
        self.c.stderr.write(f"    ERRO: {exc}")

    def imagens(self, variacao, resultado):
        self.c.stdout.write(f"    imagens [{variacao.sku}]: {resultado.get('resultado')}")

    def fim(self, resultado):
        self.c.stdout.write("")
        self.c.stdout.write(self.c.style.SUCCESS(
            f"{'(dry-run) ' if self.dry_run else ''}"
            f"criadas: {resultado.criadas} | vinculadas: {resultado.vinculadas} | "
            f"bloqueadas: {resultado.bloqueadas} | já cadastradas: {resultado.ja_cadastradas} | "
            f"erros: {resultado.erros} | imagens (enviadas/reconciliadas/erros): "
            f"{resultado.imagens_enviadas}/{resultado.imagens_reconciliadas}/{resultado.imagens_erros}"
        ))


class Command(BaseCommand):
    """
    Orquestra a sincronização de UM fornecedor com o Tiny: cria/vincula as
    variações elegíveis e, em seguida, sincroniza as imagens dos produtos
    cadastrados — a MESMA implementação (`apps.catalogo.tiny_sync`) usada
    pela task Celery disparada pela interface.

    `--dry-run`: nenhuma escrita (Tiny ou banco) — só as decisões.
    `--limite`: teto de variações na fase de criação.
    `--preview`: só imprime a estimativa (sem chamar o Tiny) e sai.
    """

    help = "Sincroniza um fornecedor com o Tiny (criação/vínculo + imagens)."

    def add_arguments(self, parser):
        parser.add_argument("instancia_slug")
        parser.add_argument("fornecedor", choices=[f.value for f in Fornecedor])
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--limite", type=int, default=None)
        parser.add_argument("--preview", action="store_true")

    def handle(self, *args, **options):
        instancia = self._obter_instancia(options["instancia_slug"])
        fornecedor = options["fornecedor"]

        if options["preview"]:
            estimativa = estimar_cadastro(instancia, fornecedor)
            for chave, valor in estimativa.items():
                self.stdout.write(f"  {chave} ..... {valor}")
            return

        if instancia.tiny_origem_padrao is None or not instancia.tiny_unidade_medida_padrao:
            raise CommandError(
                f"Configure tiny_origem_padrao e tiny_unidade_medida_padrao na instância "
                f"'{instancia.slug}' antes de sincronizar."
            )
        if not instancia.access_token:
            raise CommandError(f"Instância '{instancia.slug}' não está conectada ao Tiny.")

        dry_run = options["dry_run"]
        if dry_run:
            self.stdout.write(self.style.WARNING("DRY-RUN — nenhuma escrita no Tiny nem no banco."))

        cliente = TinyApiClient(instancia, somente_leitura=dry_run)
        executar_sincronizacao_tiny(
            instancia,
            fornecedor,
            cliente=cliente,
            dry_run=dry_run,
            limite=options["limite"],
            eventos=_EventosStdout(self, dry_run),
        )

    def _obter_instancia(self, slug):
        try:
            return Instancia.objects.get(slug=slug)
        except Instancia.DoesNotExist:
            raise CommandError(f"Instância com slug '{slug}' não encontrada.") from None
