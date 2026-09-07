import os

from celery import Celery
from celery.schedules import crontab

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("brindes_automa")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

app.conf.beat_schedule = {
    "renovar-tokens-tiny": {
        "task": "apps.instancias.tasks.renovar_tokens_tiny_task",
        "schedule": crontab(minute="*/10"),
    },
    # Tick frequente que só DECIDE quem já venceu a cadência configurada
    # (CadenciaFornecedor, por instância+fornecedor) — a cadência real não
    # fica fixa aqui, fica no banco.
    "verificar-sincronizacoes-fornecedores": {
        "task": "apps.fornecedores.tasks.verificar_e_disparar_sincronizacoes",
        "schedule": crontab(minute="*/5"),
    },
    # Reconhece execuções de cadastro Tiny travadas (worker morto) como
    # `interrompido` — persistente, não depende do estado do Celery.
    "reconciliar-execucoes-cadastro-tiny": {
        "task": "apps.catalogo.tasks.reconciliar_execucoes_travadas",
        "schedule": crontab(minute="*/5"),
    },
}
