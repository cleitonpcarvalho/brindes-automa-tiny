"""
Sessão do OPERADOR humano que usa o frontend (login com e-mail/senha,
token do DRF) — não confundir com o OAuth do Tiny (apps/instancias/
views.py, tiny_oauth.py), que autentica cada Instancia contra o Tiny.
"""

from django.contrib.auth import authenticate
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView


class LoginRequestSerializer(serializers.Serializer):
    email = serializers.EmailField()
    password = serializers.CharField(trim_whitespace=False)


class LoginResponseSerializer(serializers.Serializer):
    token = serializers.CharField()
    email = serializers.EmailField()
    nome = serializers.CharField()


class ErrorResponseSerializer(serializers.Serializer):
    detail = serializers.CharField()


class MeResponseSerializer(serializers.Serializer):
    email = serializers.EmailField()
    nome = serializers.CharField()


class LoginView(APIView):
    """POST {email, password} -> {token, email, nome}. Público: ainda não há token."""

    authentication_classes = []
    permission_classes = [AllowAny]

    @extend_schema(
        request=LoginRequestSerializer,
        responses={200: LoginResponseSerializer, 401: ErrorResponseSerializer},
    )
    def post(self, request):
        serializer = LoginRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        # authenticate() repassa kwargs extras ao backend; como
        # USERNAME_FIELD do Usuario é "email", ModelBackend usa
        # kwargs["email"] como identificador natural (ver django.contrib.
        # auth.backends.ModelBackend.authenticate).
        user = authenticate(
            request,
            email=serializer.validated_data["email"],
            password=serializer.validated_data["password"],
        )
        if user is None:
            return Response(
                {"detail": "E-mail ou senha inválidos."}, status=status.HTTP_401_UNAUTHORIZED
            )

        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "email": user.email, "nome": user.nome})


class LogoutView(APIView):
    """Apaga o token atual — derruba a sessão de qualquer lugar que o esteja usando."""

    @extend_schema(request=None, responses={204: None})
    def post(self, request):
        request.auth.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    """Usado pelo frontend para popular o bloco de usuário e validar que o token ainda é válido."""

    @extend_schema(responses={200: MeResponseSerializer})
    def get(self, request):
        return Response({"email": request.user.email, "nome": request.user.nome})
