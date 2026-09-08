"""
Reclassifica o `status` de execuções de cadastro no Tiny que fecharam como
`parcial` mas cujos contadores hoje não têm nenhum erro nem pendência — o caso
de retentativas (individuais ou em lote) feitas ANTES de a consolidação de
status passar a ser automática (ex.: Execução #7 / Só Marcas).

É idempotente e não destrutivo: só troca `parcial` -> `sucesso` quando
`total_erros == 0 and total_ignorados == 0`, registra um `LogItem` informativo
e não toca em `finalizada_em`, `mensagem_erro` nem em nenhum log histórico.

    python manage.py consolidar_status_execucoes            # aplica
    python manage.py consolidar_status_execucoes --dry-run  # só lista
    python manage.py consolidar_status_execucoes --execucao 7
"""

from django.core.management.base import BaseCommand

from apps.catalogo.tasks import consolidar_status_execucao
from apps.sincronizacao.models import Execucao, StatusExecucao, TipoExecucao


class Command(BaseCommand):
    help = "Consolida o status de execuções de cadastro no Tiny já finalizadas."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Só lista, não grava.")
        parser.add_argument("--execucao", type=int, default=None, help="Uma execução específica.")

    def handle(self, *args, **options):
        qs = Execucao.objects.filter(
            tipo=TipoExecucao.CADASTRO_TINY,
            status=StatusExecucao.PARCIAL,
            finalizada_em__isnull=False,
            total_erros=0,
            total_ignorados=0,
        )
        if options["execucao"]:
            qs = qs.filter(pk=options["execucao"])

        total = 0
        for execucao in qs.order_by("pk"):
            rotulo = f"Execução #{execucao.pk} ({execucao.fornecedor})"
            if options["dry_run"]:
                self.stdout.write(f"{rotulo}: parcial -> sucesso (dry-run)")
                total += 1
                continue
            if consolidar_status_execucao(execucao):
                self.stdout.write(self.style.SUCCESS(f"{rotulo}: parcial -> sucesso"))
                total += 1

        self.stdout.write(
            f"{total} execução(ões) {'seriam ' if options['dry_run'] else ''}consolidada(s)."
        )
