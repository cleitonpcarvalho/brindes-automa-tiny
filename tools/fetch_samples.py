#!/usr/bin/env python3
"""Coleta amostras brutas das APIs dos fornecedores (xbz, asia, somarcas, spot).

Script descartável do passo zero do projeto brindes-automa-tiny. Não transforma
os dados: apenas salva o JSON bruto retornado por cada fornecedor em
samples/<fornecedor>/ para análise posterior por analyze_samples.py.
"""

import argparse
import base64
import json
import sys
from datetime import datetime
from pathlib import Path

import requests
from dotenv import load_dotenv
import os

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent
SAMPLES_DIR = PROJECT_ROOT / "samples"

load_dotenv(SCRIPT_DIR / ".env")

TIMEOUT = 120

FORNECEDORES = ["xbz", "asia", "somarcas", "spot"]


def timestamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H%M")


def supplier_dir(fornecedor: str) -> Path:
    d = SAMPLES_DIR / fornecedor
    d.mkdir(parents=True, exist_ok=True)
    return d


def has_existing_samples(fornecedor: str) -> bool:
    return any(supplier_dir(fornecedor).glob("*.json"))


def save_json(fornecedor: str, prefix: str, data) -> Path:
    path = supplier_dir(fornecedor) / f"{prefix}_{timestamp()}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[{fornecedor}] salvo: {path.relative_to(PROJECT_ROOT)}")
    return path


def log(fornecedor: str, msg: str) -> None:
    print(f"[{fornecedor}] {msg}")


def warn(fornecedor: str, msg: str) -> None:
    print(f"[{fornecedor}] AVISO: {msg}")


def err(fornecedor: str, msg: str) -> None:
    print(f"[{fornecedor}] ERRO: {msg}", file=sys.stderr)


# ---------------------------------------------------------------------------
# XBZ
# ---------------------------------------------------------------------------

def fetch_xbz(force: bool) -> None:
    fornecedor = "xbz"
    if has_existing_samples(fornecedor) and not force:
        warn(fornecedor, "já existe amostra em samples/xbz/. Use --force para reconsultar.")
        return

    cnpj = os.getenv("XBZ_CNPJ", "")
    token = os.getenv("XBZ_TOKEN", "")
    if not cnpj or not token:
        warn(fornecedor, "XBZ_CNPJ ou XBZ_TOKEN vazios no .env. Pulando.")
        return

    print(
        f"[{fornecedor}] ATENÇÃO: a API da XBZ tem limite de 24 chamadas por dia, "
        "compartilhado com o cliente final. Esta chamada vai consumir uma unidade desse limite."
    )
    resposta = input(f"[{fornecedor}] Digite 'sim' para confirmar a chamada: ").strip().lower()
    if resposta != "sim":
        warn(fornecedor, "confirmação não recebida. Pulando.")
        return

    url = "https://api.minhaxbz.com.br:5001/api/clientes/GetListaDeProdutos"
    params = {"cnpj": cnpj, "token": token}

    try:
        resp = requests.get(url, params=params, timeout=TIMEOUT)
    except requests.RequestException as exc:
        err(fornecedor, f"falha de rede: {exc}")
        return

    if resp.status_code == 401:
        err(fornecedor, "401 - credencial inválida (cnpj/token).")
        return
    if resp.status_code == 403:
        err(fornecedor, "403 - limite diário de chamadas atingido.")
        return
    if resp.status_code == 500:
        err(fornecedor, "500 - erro interno do fornecedor.")
        return
    if resp.status_code != 200:
        err(fornecedor, f"status inesperado {resp.status_code}: {resp.text[:300]}")
        return

    try:
        data = resp.json()
    except ValueError:
        err(fornecedor, "resposta não é JSON válido.")
        return

    save_json(fornecedor, "produtos", data)


# ---------------------------------------------------------------------------
# ASIA
# ---------------------------------------------------------------------------

def fetch_asia(force: bool) -> None:
    fornecedor = "asia"
    if has_existing_samples(fornecedor) and not force:
        warn(fornecedor, "já existe amostra em samples/asia/. Use --force para reconsultar.")
        return

    api_key = os.getenv("ASIA_API_KEY", "")
    secret_key = os.getenv("ASIA_SECRET_KEY", "")
    if not api_key or not secret_key:
        warn(fornecedor, "ASIA_API_KEY ou ASIA_SECRET_KEY vazios no .env. Pulando.")
        return

    url = "https://api.asiaimport.com.br/"

    for pagina in (1, 2, 3):
        fields = {
            "api_key": (None, api_key),
            "secret_key": (None, secret_key),
            "funcao": (None, "listarProdutos2"),
            "pagina": (None, str(pagina)),
            "por_pagina": (None, "100"),
        }
        try:
            resp = requests.post(url, files=fields, timeout=TIMEOUT)
        except requests.RequestException as exc:
            err(fornecedor, f"falha de rede na página {pagina}: {exc}")
            continue

        if resp.status_code != 200:
            err(fornecedor, f"página {pagina}: status inesperado {resp.status_code}: {resp.text[:300]}")
            continue

        try:
            data = resp.json()
        except ValueError:
            err(fornecedor, f"página {pagina}: resposta não é JSON válido.")
            continue

        total_produtos = None
        total_paginas = None
        if isinstance(data, dict):
            total_produtos = data.get("total_produtos")
            total_paginas = data.get("total_paginas")
        log(fornecedor, f"página {pagina}: total_produtos={total_produtos} total_paginas={total_paginas}")

        save_json(fornecedor, f"produtos_pagina{pagina}", data)


# ---------------------------------------------------------------------------
# SOMARCAS
# ---------------------------------------------------------------------------

def fetch_somarcas(force: bool) -> None:
    fornecedor = "somarcas"
    if has_existing_samples(fornecedor) and not force:
        warn(fornecedor, "já existe amostra em samples/somarcas/. Use --force para reconsultar.")
        return

    usuario = os.getenv("SOMARCAS_USUARIO", "")
    senha = os.getenv("SOMARCAS_SENHA", "")
    estado = os.getenv("SOMARCAS_ESTADO", "")

    if not usuario or not senha:
        warn(fornecedor, "SOMARCAS_USUARIO ou SOMARCAS_SENHA vazios (credenciais ainda não fornecidas pelo cliente). Pulando.")
        return

    credenciais = base64.b64encode(f"{usuario}:{senha}".encode("utf-8")).decode("ascii")
    headers = {"Authorization": f"Basic {credenciais}"}
    url = "https://www.somarcas.com.br/api-lista-preco-revenda-v1-0-0.php"
    params = {"estado": estado}

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=TIMEOUT)
    except requests.RequestException as exc:
        err(fornecedor, f"falha de rede: {exc}")
        return

    if resp.status_code != 200:
        err(fornecedor, f"status inesperado {resp.status_code}: {resp.text[:300]}")
        return

    try:
        data = resp.json()
    except ValueError:
        err(fornecedor, "resposta não é JSON válido.")
        return

    save_json(fornecedor, "produtos", data)


# ---------------------------------------------------------------------------
# SPOT
# ---------------------------------------------------------------------------

def fetch_spot(force: bool) -> None:
    fornecedor = "spot"
    if has_existing_samples(fornecedor) and not force:
        warn(fornecedor, "já existe amostra em samples/spot/. Use --force para reconsultar.")
        return

    access_key = os.getenv("SPOT_ACCESS_KEY", "")
    if not access_key:
        warn(fornecedor, "SPOT_ACCESS_KEY vazio no .env. Pulando.")
        return

    base = "https://ws.spotgifts.com.br/api/v1SSL"

    try:
        resp = requests.get(f"{base}/AuthenticateClient", params={"accessKey": access_key}, timeout=TIMEOUT)
    except requests.RequestException as exc:
        err(fornecedor, f"falha de rede na autenticação: {exc}")
        return

    if resp.status_code != 200:
        err(fornecedor, f"autenticação: status inesperado {resp.status_code}: {resp.text[:300]}")
        return

    try:
        auth_data = resp.json()
    except ValueError:
        err(fornecedor, "autenticação: resposta não é JSON válido.")
        return

    error_code = auth_data.get("ErrorCode")
    if error_code:
        err(fornecedor, f"autenticação falhou: {auth_data.get('ErrorMessage')}")
        return

    token = auth_data.get("Token")
    if not token:
        err(fornecedor, "autenticação: resposta sem Token.")
        return

    log(fornecedor, "autenticado com sucesso.")

    endpoints = [
        ("products", "products"),
        ("optionalsComplete", "optionalscomplete"),
        ("stocks", "stocks"),
    ]

    try:
        for path, prefix in endpoints:
            try:
                resp = requests.get(f"{base}/{path}", params={"token": token, "lang": "PT"}, timeout=TIMEOUT)
            except requests.RequestException as exc:
                err(fornecedor, f"falha de rede em {path}: {exc}")
                continue

            if resp.status_code != 200:
                err(fornecedor, f"{path}: status inesperado {resp.status_code}: {resp.text[:300]}")
                continue

            try:
                data = resp.json()
            except ValueError:
                err(fornecedor, f"{path}: resposta não é JSON válido.")
                continue

            save_json(fornecedor, prefix, data)
    finally:
        try:
            requests.get(f"{base}/CloseSession", params={"token": token}, timeout=TIMEOUT)
            log(fornecedor, "sessão encerrada.")
        except requests.RequestException as exc:
            warn(fornecedor, f"falha ao encerrar sessão: {exc}")


FETCHERS = {
    "xbz": fetch_xbz,
    "asia": fetch_asia,
    "somarcas": fetch_somarcas,
    "spot": fetch_spot,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Coleta amostras brutas das APIs dos fornecedores.")
    parser.add_argument("--fornecedor", choices=FORNECEDORES, help="Rodar apenas um fornecedor.")
    parser.add_argument("--force", action="store_true", help="Reconsultar mesmo se já existir amostra salva.")
    args = parser.parse_args()

    alvos = [args.fornecedor] if args.fornecedor else FORNECEDORES

    for fornecedor in alvos:
        print(f"\n=== {fornecedor} ===")
        try:
            FETCHERS[fornecedor](args.force)
        except Exception as exc:  # nunca deixar um fornecedor derrubar os demais
            err(fornecedor, f"falha inesperada: {exc}")


if __name__ == "__main__":
    main()
