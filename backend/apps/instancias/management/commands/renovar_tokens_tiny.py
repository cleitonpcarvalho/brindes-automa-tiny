from django.core.management.base import BaseCommand
from django.utils import timezone

from ...models import Instancia
from ...tiny_oauth import TinyOAuthError, renovar_com_refresh_token


class Command(BaseCommand):
    """
    Varre as instâncias conectadas e renova proativamente o access_token
    das que já consumiram 70% ou mais do tempo de vida — nunca espera dar
    401. Feito para rodar a cada 10 minutos (via cron/scheduler externo;
    este comando só faz uma varredura e termina).
    """

    help = "Renova proativamente os access_tokens do Tiny que estão perto de expirar."

    def handle(self, *args, **options):
        agora = timezone.now()
        instancias = Instancia.objects.filter(status=Instancia.Status.CONECTADO)

        for instancia in instancias:
            try:
                self._processar(instancia, agora)
            except Exception as exc:  # uma instância com problema não pode travar as demais
                self.stderr.write(f"[{instancia.slug}] falha inesperada: {exc}")

    def _processar(self, instancia, agora):
        if instancia.refresh_token_expirado(agora):
            instancia.marcar_para_reautorizacao(
                "refresh_token expirado — é necessário autorizar novamente."
            )
            self.stdout.write(
                self.style.WARNING(f"[{instancia.slug}] refresh_token expirado, marcado para reautorização.")
            )
            return

        if not instancia.precisa_renovar_token(agora):
            return

        try:
            corpo = renovar_com_refresh_token(
                instancia.client_id, instancia.client_secret, instancia.refresh_token
            )
        except TinyOAuthError as exc:
            instancia.registrar_falha_renovacao(str(exc))
            nivel = self.style.ERROR if instancia.status == Instancia.Status.ERRO else self.style.WARNING
            self.stdout.write(
                nivel(
                    f"[{instancia.slug}] falha ao renovar (tentativa {instancia.tentativas_falha}): {exc}"
                )
            )
            return

        instancia.aplicar_tokens(
            access_token=corpo["access_token"],
            refresh_token=corpo["refresh_token"],
            expires_in=int(corpo["expires_in"]),
            refresh_expires_in=int(corpo["refresh_expires_in"]),
        )
        self.stdout.write(self.style.SUCCESS(f"[{instancia.slug}] token renovado com sucesso."))
