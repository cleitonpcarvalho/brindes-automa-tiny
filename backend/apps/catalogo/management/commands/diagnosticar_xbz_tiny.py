"""Diagnóstico somente leitura da correspondência XBZ no Tiny."""

from django.core.management.base import BaseCommand, CommandError

from apps.instancias.constants import Fornecedor
from apps.instancias.models import Instancia
from apps.instancias.tiny_client import TinyApiClient

from ...models import Variacao


class Command(BaseCommand):
    help = "Diagnostica, sem escrita, os SKUs legado e composto de uma variação XBZ no Tiny."

    def add_arguments(self, parser):
        parser.add_argument("--instancia", required=True)
        parser.add_argument("--sku", required=True, help="Variacao.sku, por exemplo X134066")
        parser.add_argument(
            "--codigo-composto",
            help="Opcional; se omitido, usa atributos.codigo_composto da variação local",
        )

    def handle(self, *args, **options):
        instancia = Instancia.objects.filter(slug=options["instancia"]).first()
        if not instancia:
            raise CommandError(f"Instância com slug '{options['instancia']}' não encontrada.")
        variacao = (
            Variacao.objects.select_related("produto")
            .filter(
                produto__instancia=instancia,
                produto__fornecedor=Fornecedor.XBZ,
                sku=options["sku"],
            )
            .first()
        )
        if not variacao:
            raise CommandError("Variação XBZ não encontrada no espelho local.")

        atributos = variacao.atributos or {}
        composto = str(options["codigo_composto"] or atributos.get("codigo_composto") or "").strip()
        if not composto:
            raise CommandError("A variação não possui atributos.codigo_composto.")
        if not instancia.access_token:
            raise CommandError(f"Instância '{instancia.slug}' não está conectada ao Tiny.")

        cliente = TinyApiClient(instancia, somente_leitura=True)
        legado = cliente.buscar_produto_por_sku(variacao.sku)
        atual = cliente.buscar_produto_por_sku(composto)

        self.stdout.write(f"Variação local: sku={variacao.sku} codigo_composto={composto}")
        self.stdout.write(f"Variacao.tiny_id: {variacao.tiny_id or '(vazio)'}")
        self.stdout.write(f"Tiny SKU legado {variacao.sku}: {self._resumo(legado)}")
        self.stdout.write(f"Tiny SKU composto {composto}: {self._resumo(atual)}")
        self.stdout.write("Nenhuma escrita foi executada.")

    @staticmethod
    def _resumo(produto):
        if not produto:
            return "não encontrado"
        return f"id={produto.get('id')} sku={produto.get('sku')}"
