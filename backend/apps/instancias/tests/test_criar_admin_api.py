from io import StringIO

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from rest_framework.authtoken.models import Token


class CriarAdminApiTests(TestCase):
    def test_cria_usuario_com_email_e_token(self):
        saida = StringIO()
        call_command(
            "criar_admin_api",
            "--email=admin@example.com",
            "--password=senha-forte-123",
            "--nome=Admin",
            stdout=saida,
        )

        usuario = get_user_model().objects.get(email="admin@example.com")
        self.assertTrue(usuario.is_staff)
        self.assertTrue(usuario.is_superuser)
        self.assertEqual(usuario.nome, "Admin")
        self.assertTrue(usuario.check_password("senha-forte-123"))
        self.assertTrue(Token.objects.filter(user=usuario).exists())
        self.assertIn("Token de API", saida.getvalue())

    def test_reaproveita_usuario_existente_sem_trocar_senha(self):
        get_user_model().objects.create_user(email="admin2@example.com", password="senha-original")

        call_command(
            "criar_admin_api",
            "--email=admin2@example.com",
            "--password=senha-nova",
            stdout=StringIO(),
        )

        usuario = get_user_model().objects.get(email="admin2@example.com")
        self.assertTrue(usuario.check_password("senha-original"))
