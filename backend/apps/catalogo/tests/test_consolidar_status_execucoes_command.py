"""`python manage.py consolidar_status_execucoes` — reclassifica execuções de
cadastro no Tiny que fecharam `parcial` mas hoje não têm erro nem pendência."""

from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from apps.instancias.models import Instancia
from apps.sincronizacao.models import Execucao, LogItem, StatusExecucao, TipoExecucao


def _execucao(**over):
    inst = Instancia.objects.create(nome="Loja", access_token="tok")
    dados = dict(
        instancia=inst, fornecedor="somarcas", tipo=TipoExecucao.CADASTRO_TINY,
        status=StatusExecucao.PARCIAL, finalizada_em=timezone.now(),
        total_lidos=1240, total_cadastrados=1240, total_erros=0, total_ignorados=0,
    )
    dados.update(over)
    return Execucao.objects.create(**dados)


class ConsolidarStatusExecucoesCommandTests(TestCase):
    def test_aplica_e_e_idempotente(self):
        ex = _execucao()
        call_command("consolidar_status_execucoes", stdout=StringIO())
        ex.refresh_from_db()
        self.assertEqual(ex.status, StatusExecucao.SUCESSO)

        logs_antes = LogItem.objects.filter(execucao=ex).count()
        call_command("consolidar_status_execucoes", stdout=StringIO())
        self.assertEqual(LogItem.objects.filter(execucao=ex).count(), logs_antes)

    def test_dry_run_nao_grava(self):
        ex = _execucao()
        call_command("consolidar_status_execucoes", "--dry-run", stdout=StringIO())
        ex.refresh_from_db()
        self.assertEqual(ex.status, StatusExecucao.PARCIAL)

    def test_nao_toca_em_execucao_com_erros(self):
        ex = _execucao(total_erros=2)
        call_command("consolidar_status_execucoes", stdout=StringIO())
        ex.refresh_from_db()
        self.assertEqual(ex.status, StatusExecucao.PARCIAL)

    def test_filtra_por_execucao(self):
        alvo = _execucao()
        outra = _execucao()
        call_command("consolidar_status_execucoes", "--execucao", str(alvo.pk), stdout=StringIO())
        alvo.refresh_from_db()
        outra.refresh_from_db()
        self.assertEqual(alvo.status, StatusExecucao.SUCESSO)
        self.assertEqual(outra.status, StatusExecucao.PARCIAL)
