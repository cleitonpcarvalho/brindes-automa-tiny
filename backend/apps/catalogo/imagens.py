"""Validação e transporte seguro de imagens para anexos do Tiny.

O Tiny recebe uma URL e baixa o arquivo com ``externo=false``. O caminho
normal continua enviando a URL original. Só depois de uma rejeição de
validação do endpoint de anexos usamos a URL pública assinada abaixo para
baixar, validar e eventualmente otimizar a imagem no momento em que o Tiny a
busca. Nenhum arquivo permanente é criado.
"""

import hashlib
import hmac
import io
import tempfile
import time
import warnings
from urllib.parse import urlencode, urlsplit

import requests
from django.conf import settings
from django.http import HttpResponse, HttpResponseNotModified
from django.views.decorators.http import require_GET
from PIL import Image, ImageFile, ImageOps

from apps.catalogo.models import Variacao
from apps.instancias.tiny_client import url_http_utilizavel

IMAGE_PROXY_TTL_SECONDS = 24 * 60 * 60
IMAGE_MAX_DOWNLOAD_BYTES = 20 * 1024 * 1024
IMAGE_OPTIMIZE_AFTER_BYTES = 5 * 1024 * 1024
IMAGE_MAX_DIMENSION = 2400
IMAGE_MAX_PIXELS = 25_000_000
IMAGE_DOWNLOAD_TIMEOUT = (5, 30)

ImageFile.LOAD_TRUNCATED_IMAGES = False


class ImagemProxyError(Exception):
    """A fonte não pôde ser transformada em uma imagem segura."""


def _payload_assinatura(variacao_id, indice, expira_em, url_original):
    digest = hashlib.sha256(url_original.encode("utf-8")).hexdigest()
    return f"{variacao_id}:{indice}:{expira_em}:{digest}"


def _assinatura(variacao_id, indice, expira_em, url_original):
    payload = _payload_assinatura(variacao_id, indice, expira_em, url_original)
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256
    ).hexdigest()


def _base_publica():
    base = (getattr(settings, "IMAGE_PROXY_BASE_URL", "") or settings.PUBLIC_BASE_URL).rstrip("/")
    partes = urlsplit(base)
    if partes.scheme not in {"http", "https"} or partes.hostname in {
        "localhost", "127.0.0.1", "::1"
    }:
        raise ImagemProxyError(
            "IMAGE_PROXY_BASE_URL precisa ser uma URL HTTP(S) pública; localhost não é acessível pelo Tiny."
        )
    return base


def url_proxy_imagem(variacao, indice, url_original, *, agora=None):
    if not url_http_utilizavel(url_original):
        raise ImagemProxyError("referência de imagem não é uma URL HTTP(S) utilizável")
    agora = int(agora if agora is not None else time.time())
    expira_em = agora + IMAGE_PROXY_TTL_SECONDS
    assinatura = _assinatura(variacao.pk, indice, expira_em, url_original)
    caminho = f"{_base_publica()}/public/imagens/{variacao.pk}/{indice}/"
    return f"{caminho}?{urlencode({'exp': expira_em, 'sig': assinatura})}"


def _ler_limitado(resposta):
    tamanho = resposta.headers.get("Content-Length")
    if tamanho:
        try:
            if int(tamanho) > IMAGE_MAX_DOWNLOAD_BYTES:
                raise ImagemProxyError("imagem excede o limite seguro de download")
        except ValueError:
            pass

    with tempfile.SpooledTemporaryFile(max_size=IMAGE_MAX_DOWNLOAD_BYTES, mode="w+b") as arquivo:
        total = 0
        for bloco in resposta.iter_content(chunk_size=64 * 1024):
            if not bloco:
                continue
            total += len(bloco)
            if total > IMAGE_MAX_DOWNLOAD_BYTES:
                raise ImagemProxyError("imagem excede o limite seguro de download")
            arquivo.write(bloco)
        arquivo.seek(0)
        return arquivo.read()


def _validar_e_transformar(conteudo, content_type):
    if content_type and not (
        content_type.startswith("image/") or content_type == "application/octet-stream"
    ):
        raise ImagemProxyError("servidor de origem não retornou conteúdo de imagem")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(conteudo)) as imagem:
                imagem.verify()
            with Image.open(io.BytesIO(conteudo)) as imagem:
                formato = imagem.format or ""
                imagem = ImageOps.exif_transpose(imagem)
                largura, altura = imagem.size
                if largura * altura > IMAGE_MAX_PIXELS:
                    raise ImagemProxyError("imagem excede o limite seguro de pixels")
                precisa_otimizar = (
                    len(conteudo) > IMAGE_OPTIMIZE_AFTER_BYTES
                    or max(largura, altura) > IMAGE_MAX_DIMENSION
                    or formato not in {"JPEG", "PNG", "WEBP"}
                )
                if not precisa_otimizar:
                    return conteudo, content_type or "image/jpeg"

                imagem.thumbnail((IMAGE_MAX_DIMENSION, IMAGE_MAX_DIMENSION), Image.Resampling.LANCZOS)
                if imagem.mode in {"RGBA", "LA", "P"}:
                    fundo = Image.new("RGB", imagem.size, "white")
                    if imagem.mode == "P":
                        imagem = imagem.convert("RGBA")
                    fundo.paste(imagem, mask=imagem.getchannel("A"))
                    imagem = fundo
                else:
                    imagem = imagem.convert("RGB")
                saida = io.BytesIO()
                imagem.save(saida, format="JPEG", quality=88, optimize=True, progressive=True)
                return saida.getvalue(), "image/jpeg"
    except Exception as exc:
        raise ImagemProxyError(f"conteúdo não é uma imagem válida: {exc}") from exc


@require_GET
def servir_imagem_proxy(request, variacao_id, indice):
    try:
        expira_em = int(request.GET["exp"])
        assinatura = request.GET["sig"]
        if expira_em < int(time.time()):
            return HttpResponse("URL expirada", status=410)
        variacao = Variacao.objects.select_related("produto").get(pk=variacao_id)
        desejadas = [url for url in (variacao.imagens or []) if url_http_utilizavel(url)]
        desejadas = list(dict.fromkeys(desejadas))[:5]
        url_original = desejadas[int(indice)]
        esperada = _assinatura(variacao.pk, int(indice), expira_em, url_original)
        if not hmac.compare_digest(assinatura, esperada):
            return HttpResponse("Assinatura inválida", status=403)
    except (KeyError, ValueError, IndexError, Variacao.DoesNotExist):
        return HttpResponse("Imagem não encontrada", status=404)

    etag = f'"{assinatura}"'
    if request.headers.get("If-None-Match") == etag:
        return HttpResponseNotModified()

    try:
        resposta = requests.get(
            url_original,
            stream=True,
            timeout=IMAGE_DOWNLOAD_TIMEOUT,
            headers={"User-Agent": "brindes-automa-image-proxy/1.0"},
        )
        resposta.raise_for_status()
        conteudo = _ler_limitado(resposta)
        corpo, content_type = _validar_e_transformar(
            conteudo, (resposta.headers.get("Content-Type") or "").split(";", 1)[0].lower()
        )
    except (requests.RequestException, ImagemProxyError) as exc:
        return HttpResponse(f"Imagem indisponível: {exc}", status=422)
    finally:
        if "resposta" in locals():
            resposta.close()

    resposta_http = HttpResponse(corpo, content_type=content_type)
    resposta_http["Cache-Control"] = "public, max-age=3600"
    resposta_http["ETag"] = etag
    return resposta_http


def urls_proxy_imagens(variacao, desejadas):
    return [url_proxy_imagem(variacao, indice, url) for indice, url in enumerate(desejadas)]
