from django.core.management.base import BaseCommand, CommandError
from django.db.models import F, Q

from apps.instancias.constants import Fornecedor
from apps.instancias.models import Instancia
from apps.instancias.tiny_client import TinyApiClient

from ...models import StatusVariacao, Variacao


class Command(BaseCommand):
    """
    Atualiza no Tiny o estoque das variações já cadastradas cujo valor
    mudou no espelho desde a última sincronização (`estoque` difere de
    `estoque_tiny_sincronizado`, ou nunca foi sincronizado). Mesmo
    tratamento de throttle e de erro do cadastro — uma falha não trava as
    demais, e como o marcador só avança em caso de sucesso, rodar de novo
    naturalmente tenta de novo só o que ainda está fora de sincronia.
    """

    help = "Atualiza no Tiny o estoque das variações cadastradas cujo valor mudou no espelho."

    def add_arguments(self, parser):
        parser.add_argument("instancia_slug")
        parser.add_argument("--limite", type=int, default=None)
        parser.add_argument(
            "--fornecedor",
            choices=[f.value for f in Fornecedor],
            default=None,
            help="Restringe a fila a um fornecedor (usado pela propagação automática).",
        )

    def handle(self, *args, **options):
        instancia = self._obter_instancia(options["instancia_slug"])
        if not instancia.access_token:
            raise CommandError(f"Instância '{instancia.slug}' não está conectada ao Tiny.")

        cliente = TinyApiClient(instancia)

        fila = (
            Variacao.objects.filter(produto__instancia=instancia, status=StatusVariacao.CADASTRADO)
            .filter(Q(estoque_tiny_sincronizado__isnull=True) | ~Q(estoque=F("estoque_tiny_sincronizado")))
            .order_by("id")
        )
        if options["fornecedor"]:
            fila = fila.filter(produto__fornecedor=options["fornecedor"])
        if options["limite"]:
            fila = fila[: options["limite"]]

        atualizadas = erros = 0

        for variacao in fila.iterator():
            try:
                cliente.atualizar_estoque(
                    int(variacao.tiny_id),
                    quantidade=variacao.estoque,
                    # `precoUnitario` do lançamento de Balanço é CUSTO — usa o
                    # preço do fornecedor (NÃO o de venda, que agora é sempre 0).
                    preco_unitario=variacao.preco_custo_tiny,
                )
                variacao.estoque_tiny_sincronizado = variacao.estoque
                variacao.ultimo_erro = ""
                variacao.save(update_fields=["estoque_tiny_sincronizado", "ultimo_erro", "atualizado_em"])
                atualizadas += 1
            except Exception as exc:  # uma variação ruim não pode travar o lote
                # NÃO muda status: o produto continua cadastrado no Tiny, só a
                # sincronização de estoque desta rodada falhou — tenta de novo
                # na próxima (estoque_tiny_sincronizado não avançou).
                variacao.ultimo_erro = f"Falha ao atualizar estoque: {exc}"
                variacao.save(update_fields=["ultimo_erro", "atualizado_em"])
                erros += 1
                self.stderr.write(f"[{variacao.sku}] erro: {exc}")

        self.stdout.write(self.style.SUCCESS(f"Atualizadas: {atualizadas} | erros: {erros}"))

    def _obter_instancia(self, slug):
        try:
            return Instancia.objects.get(slug=slug)
        except Instancia.DoesNotExist:
            raise CommandError(f"Instância com slug '{slug}' não encontrada.") from None
