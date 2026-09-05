from celery import shared_task
from django.core.management import call_command


@shared_task
def renovar_tokens_tiny_task():
    """Beat dispara isso a cada 10 minutos — a lógica real está no management command."""
    call_command("renovar_tokens_tiny")
