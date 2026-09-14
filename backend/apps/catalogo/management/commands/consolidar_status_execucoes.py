"""
Reclassifica o `status` de execuções de cadastro no Tiny que fecharam como
`parcial` mas cujos contadores hoje não têm nenhum erro nem pendência — o caso
de retentativas (individuais ou em lote) feitas ANTES de a consolidação de
status passar a ser automática (ex.: Execução #7 / Só Marcas).

É idempotente e não destrutivo. No uso geral, só troca `parcial` -> `sucesso`
quando os contadores consolidados não têm erro nem pendência. Com
``--execucao``, também pode encerrar uma execução ``interrompido`` cuja fila
REAL de retomada esteja vazia, sem executar a retomada nem chamar o Tiny.

    python manage.py consolidar_status_execucoes            # aplica
    python manage.py consolidar_status_execucoes --dry-run  # só lista
    python manage.py consolidar_status_execucoes --execucao 7
"""

from django.core.management.base import BaseCommand

from apps.catalogo.tasks import (
    consolidar_execucao_interrompida_sem_trabalho,
    consolidar_status_execucao,
    execucao_interrompida_sem_trabalho,
)
from apps.sincronizacao.models import Execucao, StatusExecucao, TipoExecucao


class Command(BaseCommand):
    help = "Consolida o status de execuções de cadastro no Tiny sem trabalho pendente."

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Só lista, não grava.")
        parser.add_argument("--execucao", type=int, default=None, help="Uma execução específica.")

    def handle(self, *args, **options):
        execucao_id = options["execucao"]
        if execucao_id is not None:
            execucao = (
                Execucao.objects.filter(pk=execucao_id, tipo=TipoExecucao.CADASTRO_TINY)
                .select_related("instancia")
                .first()
            )
            if execucao is not None and execucao.status == StatusExecucao.INTERROMPIDO:
                rotulo = f"Execução #{execucao.pk} ({execucao.fornecedor})"
                if not execucao_interrompida_sem_trabalho(execucao):
                    self.stdout.write(
                        f"{rotulo}: mantida como interrompida; "
                        "a fila atual ainda possui trabalho ou a execução não é consolidável."
                    )
                    self.stdout.write("0 execução(ões) consolidada(s).")
                    return
                if options["dry_run"]:
                    self.stdout.write(
                        f"{rotulo}: interrompida -> sucesso; fila atual vazia (dry-run)"
                    )
                    self.stdout.write("1 execução(ões) seriam consolidada(s).")
                    return
                if consolidar_execucao_interrompida_sem_trabalho(execucao.pk):
                    self.stdout.write(
                        self.style.SUCCESS(
                            f"{rotulo}: interrompida -> sucesso; fila atual vazia"
                        )
                    )
                    self.stdout.write("1 execução(ões) consolidada(s).")
                    return
                self.stdout.write(
                    f"{rotulo}: não consolidada; o estado mudou ou a instância está em uso."
                )
                self.stdout.write("0 execução(ões) consolidada(s).")
                return

        qs = Execucao.objects.filter(
            tipo=TipoExecucao.CADASTRO_TINY,
            status=StatusExecucao.PARCIAL,
            finalizada_em__isnull=False,
            total_erros=0,
            total_ignorados=0,
        )
        if execucao_id is not None:
            qs = qs.filter(pk=execucao_id)

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
