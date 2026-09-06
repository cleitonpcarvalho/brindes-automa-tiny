"""
Mascaramento de credenciais de fornecedor para resposta de API (passo 10).

Nenhum valor sensível completo é devolvido em nenhuma resposta — só um
preview fixo (8 bullets + últimos 4 caracteres reais). Campos marcados como
não sensíveis em CAMPOS_POR_FORNECEDOR (ex.: CNPJ, usuário) voltam em texto
pleno, porque são identificadores que o operador precisa conferir, não
segredos.
"""

from .constants import CAMPOS_POR_FORNECEDOR

_BULLETS = "•" * 8


def mascarar_valor(valor) -> str:
    texto = str(valor)
    if len(texto) <= 4:
        return _BULLETS
    return _BULLETS + texto[-4:]


def mascarar_credenciais(fornecedor, credenciais: dict) -> dict:
    campos = CAMPOS_POR_FORNECEDOR.get(fornecedor, {})
    resultado = {}
    for chave, regras in campos.items():
        valor = credenciais.get(chave)
        if valor in (None, ""):
            resultado[chave] = None
        elif regras["sensivel"]:
            resultado[chave] = mascarar_valor(valor)
        else:
            resultado[chave] = valor
    return resultado
