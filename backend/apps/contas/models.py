"""
Usuário operador do painel (quem faz login no frontend e usa a API).

Passo 8: o design pede login por e-mail e a versão anterior tratava isso
como "username com formato de e-mail" (convenção frágil, sem unicidade real
de e-mail no banco). Este app substitui o `auth.User` padrão do Django por
um modelo próprio com e-mail como identificador único de autenticação.
"""

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import PermissionsMixin
from django.db import models


class UsuarioManager(BaseUserManager):
    use_in_migrations = True

    def _criar_usuario(self, email, password, **extra_fields):
        if not email:
            raise ValueError("O e-mail é obrigatório.")
        email = self.normalize_email(email)
        usuario = self.model(email=email, **extra_fields)
        usuario.set_password(password)
        usuario.save(using=self._db)
        return usuario

    def create_user(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", False)
        extra_fields.setdefault("is_superuser", False)
        return self._criar_usuario(email, password, **extra_fields)

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superusuário precisa de is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superusuário precisa de is_superuser=True.")
        return self._criar_usuario(email, password, **extra_fields)


class Usuario(AbstractBaseUser, PermissionsMixin):
    """Operador humano do painel — login por e-mail, não por username."""

    email = models.EmailField(unique=True)
    nome = models.CharField(max_length=150, blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    criado_em = models.DateTimeField(auto_now_add=True)

    objects = UsuarioManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        verbose_name = "Usuário"
        verbose_name_plural = "Usuários"
        ordering = ["email"]

    def __str__(self):
        return self.nome or self.email

    def get_full_name(self):
        return self.nome or self.email

    def get_short_name(self):
        return self.nome.split(" ")[0] if self.nome else self.email
