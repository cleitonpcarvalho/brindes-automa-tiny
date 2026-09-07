from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.instancias.models import CredencialFornecedor

from .models import CadenciaFornecedor


@receiver(post_save, sender=CredencialFornecedor)
def criar_cadencia_padrao(sender, instance, created, **kwargs):
    """
    Toda credencial nova ganha uma cadência de sincronização (60min), mas
    DESLIGADA (`ativo=False`): a sincronização automática só começa depois
    que o usuário ativa a cadência explicitamente pela interface.
    """
    if created:
        CadenciaFornecedor.objects.get_or_create(
            instancia=instance.instancia,
            fornecedor=instance.fornecedor,
            defaults={"ativo": False},
        )
