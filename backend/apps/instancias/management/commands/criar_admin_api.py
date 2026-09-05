import secrets

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from rest_framework.authtoken.models import Token


class Command(BaseCommand):
    """
    Cria (ou reaproveita) o usuário administrador — para admin do Django e
    para autenticar na API (/api/instancias/...) — sem depender de
    `createsuperuser` manual. Sempre imprime o token de API no final.
    """

    help = "Cria o usuário administrador e o token de autenticação da API."

    def add_arguments(self, parser):
        parser.add_argument("--email", required=True)
        parser.add_argument("--nome", default="")
        parser.add_argument(
            "--password",
            default=None,
            help="Se omitido, gera uma senha aleatória e a imprime (guarde, não é mostrada de novo).",
        )

    def handle(self, *args, **options):
        Usuario = get_user_model()
        email = Usuario.objects.normalize_email(options["email"])
        if not email:
            raise CommandError("--email é obrigatório.")

        usuario, criado = Usuario.objects.get_or_create(
            email=email,
            defaults={"nome": options["nome"], "is_staff": True, "is_superuser": True},
        )

        if criado:
            senha = options["password"] or secrets.token_urlsafe(16)
            usuario.set_password(senha)
            usuario.is_staff = True
            usuario.is_superuser = True
            usuario.save()
            self.stdout.write(self.style.SUCCESS(f"Usuário '{email}' criado."))
            if not options["password"]:
                self.stdout.write(f"Senha gerada (guarde agora, não será mostrada de novo): {senha}")
        else:
            self.stdout.write(f"Usuário '{email}' já existia — senha não foi alterada.")

        token, _ = Token.objects.get_or_create(user=usuario)
        self.stdout.write(self.style.SUCCESS(f"Token de API: {token.key}"))
        self.stdout.write('Use como header: Authorization: Token <o token acima>')
