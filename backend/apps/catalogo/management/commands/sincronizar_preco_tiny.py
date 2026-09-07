from django.core.management.base import BaseCommand, CommandError
from django.db.models import F, Q

from apps.instancias.constants import Fornecedor
from apps.instancias.models import Instancia
from apps.instancias.tiny_client import TinyApiClient

from ...models import StatusVariacao, Variacao


class Command(BaseCommand):
    """
    Mantém o PREÇO DE VENDA (`precos.preco`) do cadastro do produto no Tiny
    sincronizado com `Variacao.preco` — o preço do fornecedor, sem margem
    (regra do cliente nº 4).

    NÃO confundir com `atualizar_estoque_tiny`: aquele manda o
    `precoUnitario` de um movimento de Balanço (custo do lançamento de
    estoque), não o preço de venda do produto.

    Fila: variações `cadastrado` com `tiny_id`, cujo `preco` difere de
    `preco_tiny_sincronizado` (ou nunca foi sincronizado). Uma falha não
    trava as demais; o marcador `preco_tiny_sincronizado` só avança em caso
    de sucesso, então rodar de novo tenta só o que ainda está fora de
    sincronia.

    `--dry-run`: nenhuma chamada de escrita ao Tiny e nenhuma escrita local —
    só mostra, por variação, o preço atual sincronizado e o novo.

    A escrita usa `TinyApiClient.atualizar_preco_venda`, que chama o endpoint
    específico `PUT /produtos/{idProduto}/preco` com apenas `{"preco": ...}` —
    não toca em descrição/NCM/dimensões.
    """

    help = "Sincroniza o preço de venda dos produtos já cadastrados no Tiny com o preço do fornecedor."

    def add_arguments(self, parser):
        parser.add_argument("instancia_slug")
        parser.add_argument("--limite", type=int, default=None)
        parser.add_argument("--dry-run", action="store_true")
        parser.add_argument("--fornecedor", choices=[f.value for f in Fornecedor], default=None)
        parser.add_argument(
            "--skus", default=None, help="Lista explícita de SKUs (separados por vírgula)."
        )

    def handle(self, *args, **options):
        instancia = self._obter_instancia(options["instancia_slug"])
        if not instancia.access_token:
            raise CommandError(f"Instância '{instancia.slug}' não está conectada ao Tiny.")

        dry_run = options["dry_run"]
        w = self.stdout.write
        if dry_run:
            w(self.style.WARNING("DRY-RUN — nenhum PUT no Tiny e nenhuma alteração local."))

        fila = (
            Variacao.objects.filter(
                produto__instancia=instancia, status=StatusVariacao.CADASTRADO
            )
            .exclude(tiny_id__isnull=True)
            .exclude(tiny_id="")
            .filter(
                Q(preco_tiny_sincronizado__isnull=True) | ~Q(preco=F("preco_tiny_sincronizado"))
            )
            .select_related("produto")
        )
        if options["fornecedor"]:
            fila = fila.filter(produto__fornecedor=options["fornecedor"])
        skus = [s.strip() for s in (options["skus"] or "").split(",") if s.strip()]
        if skus:
            fila = fila.filter(sku__in=skus)
        fila = fila.order_by("produto__fornecedor", "sku", "id")
        if options["limite"]:
            fila = fila[: options["limite"]]

        cliente = TinyApiClient(instancia, somente_leitura=dry_run)
        atualizadas = erros = 0

        for variacao in list(fila):
            de = variacao.preco_tiny_sincronizado
            para = variacao.preco_venda_tiny
            w(f"[{variacao.produto.fornecedor}] {variacao.sku!r} (tiny_id={variacao.tiny_id}): {de} -> {para}")
            if dry_run:
                continue
            try:
                cliente.atualizar_preco_venda(int(variacao.tiny_id), preco=para)
                variacao.preco_tiny_sincronizado = para
                variacao.ultimo_erro = ""
                variacao.save(update_fields=["preco_tiny_sincronizado", "ultimo_erro", "atualizado_em"])
                atualizadas += 1
            except Exception as exc:  # uma variação ruim não pode travar o lote
                variacao.ultimo_erro = f"Falha ao sincronizar preço de venda: {exc}"
                variacao.save(update_fields=["ultimo_erro", "atualizado_em"])
                erros += 1
                self.stderr.write(f"[{variacao.sku}] erro: {exc}")

        w("")
        w(self.style.SUCCESS(
            f"{'(dry-run) ' if dry_run else ''}Preços sincronizados: {atualizadas} | erros: {erros}"
        ))

    def _obter_instancia(self, slug):
        try:
            return Instancia.objects.get(slug=slug)
        except Instancia.DoesNotExist:
            raise CommandError(f"Instância com slug '{slug}' não encontrada.") from None
