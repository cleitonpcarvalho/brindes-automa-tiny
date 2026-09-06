"""
Fluxo OAuth2 (authorization_code + refresh_token) do Tiny via Keycloak.

O endpoint de token foi dado pela especificação. O endpoint de autorização
NÃO foi — inferi `.../protocol/openid-connect/auth` pelo padrão-padrão do
próprio Keycloak (mesmo realm, mesmo prefixo do endpoint de token). Os dois
são configuráveis via settings/env (TINY_OAUTH_TOKEN_URL,
TINY_OAUTH_AUTHORIZE_URL) para não exigir mudança de código se a inferência
estiver errada — confirmar contra a documentação oficial do Tiny antes de ir
para produção.
"""

import base64
from urllib.parse import urlencode

import requests
from django.conf import settings
from django.urls import reverse


class TinyOAuthError(Exception):
    """Erro ao trocar/renovar token com o Tiny (Keycloak)."""


def montar_url_callback(slug: str) -> str:
    """
    redirect_uri registrada no app do Tiny para esta instância. Vem de
    `settings.PUBLIC_BASE_URL` (fixo por ambiente, passo 10) — não de
    `request.build_absolute_uri` — porque o Tiny exige essa URL
    byte-idêntica entre a chamada de autorizar e a de troca de token, e
    confiar no Host header da requisição corrente é frágil atrás de proxy.
    """
    caminho = reverse("tiny-oauth-callback", kwargs={"slug": slug})
    return f"{settings.PUBLIC_BASE_URL.rstrip('/')}{caminho}"


def montar_url_autorizacao(client_id: str, redirect_uri: str, state: str) -> str:
    parametros = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return f"{settings.TINY_OAUTH_AUTHORIZE_URL}?{urlencode(parametros)}"


def trocar_code_por_token(client_id: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    return _chamar_token_endpoint(
        client_id,
        client_secret,
        {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": redirect_uri,
        },
    )


def renovar_com_refresh_token(client_id: str, client_secret: str, refresh_token: str) -> dict:
    return _chamar_token_endpoint(
        client_id,
        client_secret,
        {
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
    )


def _chamar_token_endpoint(client_id: str, client_secret: str, dados_form: dict) -> dict:
    credenciais = base64.b64encode(f"{client_id}:{client_secret}".encode("utf-8")).decode("ascii")

    try:
        resposta = requests.post(
            settings.TINY_OAUTH_TOKEN_URL,
            data=dados_form,
            headers={
                "Authorization": f"Basic {credenciais}",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            timeout=30,
        )
    except requests.RequestException as exc:
        raise TinyOAuthError(f"Falha de rede ao falar com o Tiny: {exc}") from exc

    try:
        corpo = resposta.json()
    except ValueError:
        corpo = {}

    if resposta.status_code != 200:
        mensagem = corpo.get("error_description") or corpo.get("error") or resposta.text[:300]
        raise TinyOAuthError(f"Tiny recusou a solicitação ({resposta.status_code}): {mensagem}")

    campos_obrigatorios = ("access_token", "refresh_token", "expires_in", "refresh_expires_in")
    faltando = [c for c in campos_obrigatorios if c not in corpo]
    if faltando:
        raise TinyOAuthError(f"Resposta do Tiny sem os campos esperados: {faltando}")

    return corpo
