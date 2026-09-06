"""
Cliente HTTP para a API "de negócio" do Tiny (produtos, estoque — não o
endpoint de OAuth, que fica em tiny_oauth.py). Contrato confirmado contra
o Swagger oficial: https://erp.tiny.com.br/public-api/v3/swagger.

Regras respeitadas aqui:
  - o Tiny devolve o teto de requisições por minuto da conta (não do
    aplicativo) no header `x-limit-api`; guardamos esse valor na própria
    Instancia e usamos 80% dele como teto real de chamadas nossas — a
    janela deslizante em si vive no Redis (tiny_throttle.py), compartilhada
    entre o servidor Django e os workers do Celery;
  - 429 é tratado com respeito a `Retry-After` quando presente, e backoff
    exponencial quando não.
"""

import time

import requests
from django.core.exceptions import ImproperlyConfigured

from .tiny_throttle import RateLimiterCompartilhado


class TinyApiError(Exception):
    """Erro definitivo ao chamar a API do Tiny (ex.: 429 esgotado)."""


class TinyApiValidationError(TinyApiError):
    """A API do Tiny recusou a requisição (ex.: 400) com um motivo estruturado."""

    def __init__(self, mensagem, detalhes=None):
        self.mensagem = mensagem
        self.detalhes = detalhes or []
        super().__init__(mensagem)

    def menciona_ncm(self):
        texto = self.mensagem.lower()
        if "ncm" in texto:
            return True
        return any("ncm" in f"{d.get('campo', '')} {d.get('mensagem', '')}".lower() for d in self.detalhes)


class TinyApiClient:
    MAX_TENTATIVAS_429 = 5
    BACKOFF_BASE_SEGUNDOS = 1.0
    BACKOFF_MAXIMO_SEGUNDOS = 60.0

    def __init__(self, instancia, base_url=None, sleep_fn=time.sleep, limiter=None):
        self.instancia = instancia
        self.base_url = base_url if base_url is not None else _base_url_padrao()
        self._sleep = sleep_fn
        self._limiter = limiter or RateLimiterCompartilhado(instancia.slug, sleep_fn=sleep_fn)

    # -- API pública de baixo nível ----------------------------------------

    def get(self, caminho: str, **kwargs) -> requests.Response:
        return self._request("GET", caminho, **kwargs)

    def post(self, caminho: str, **kwargs) -> requests.Response:
        return self._request("POST", caminho, **kwargs)

    # -- API de domínio (produtos/estoque) ----------------------------------

    def buscar_produto_por_sku(self, sku: str) -> dict | None:
        """GET /produtos?codigo=<sku> — usado para nunca duplicar um SKU já cadastrado."""
        resposta = self.get("/produtos", params={"codigo": sku, "limit": 1})
        self._levantar_se_erro(resposta)
        itens = resposta.json().get("itens", [])
        return itens[0] if itens else None

    def listar_produtos(self, *, limit: int = 100, offset: int = 0, situacao: str | None = None) -> dict:
        """
        GET /produtos — uma página da listagem do catálogo (somente leitura).

        Contrato v3 confirmado na doc oficial: paginação por `limit` (default
        100) + `offset` (default 0); resposta
        `{"itens": [...], "paginacao": {"limit", "offset", "total"}}`.
        Devolve o corpo inteiro; a paginação/loop fica com quem chama.
        """
        params: dict = {"limit": limit, "offset": offset}
        if situacao:
            params["situacao"] = situacao
        resposta = self.get("/produtos", params=params)
        self._levantar_se_erro(resposta)
        return resposta.json()

    def obter_produto(self, id_produto) -> dict:
        """
        GET /produtos/{id} — detalhe completo de um produto (somente leitura).
        Traz os campos que a listagem não devolve: ncm, origem, marca,
        categoria, dimensoes, estoque.quantidade, etc.
        """
        resposta = self.get(f"/produtos/{id_produto}")
        self._levantar_se_erro(resposta)
        return resposta.json()

    def criar_produto(self, payload: dict) -> dict:
        """POST /produtos — cria um produto tipo 'S' (Simples). Uma Variacao = um produto."""
        resposta = self.post("/produtos", json=payload)
        self._levantar_se_erro(resposta)
        return resposta.json()

    def atualizar_estoque(self, id_produto, *, quantidade, preco_unitario) -> dict:
        """POST /estoque/{idProduto}, tipo Balanço (define o saldo absoluto, não um delta)."""
        resposta = self.post(
            f"/estoque/{id_produto}",
            json={
                "tipo": "B",
                "quantidade": float(quantidade),
                "precoUnitario": float(preco_unitario),
            },
        )
        self._levantar_se_erro(resposta)
        return resposta.json()

    @staticmethod
    def _levantar_se_erro(resposta: requests.Response):
        if resposta.status_code == 200:
            return
        corpo = {}
        try:
            corpo = resposta.json()
        except ValueError:
            pass
        mensagem = corpo.get("mensagem") or f"Tiny retornou {resposta.status_code}: {resposta.text[:300]}"
        raise TinyApiValidationError(mensagem, corpo.get("detalhes"))

    # -- mecânica interna ----------------------------------------------------

    def _request(self, metodo: str, caminho: str, **kwargs) -> requests.Response:
        if not self.base_url:
            raise ImproperlyConfigured("TINY_API_BASE_URL não configurado.")

        tentativa = 0
        while True:
            self._limiter.aguardar_vaga(self.instancia.rate_limit_por_minuto)

            headers = {"Authorization": f"Bearer {self.instancia.access_token}"}
            headers.update(kwargs.pop("headers", {}) or {})

            resposta = requests.request(
                metodo, f"{self.base_url}{caminho}", headers=headers, timeout=30, **kwargs
            )
            self._atualizar_limite_da_conta(resposta)

            if resposta.status_code == 429:
                tentativa += 1
                if tentativa > self.MAX_TENTATIVAS_429:
                    raise TinyApiError(
                        f"429 persistente após {self.MAX_TENTATIVAS_429} tentativas em {caminho!r}."
                    )
                self._aguardar_backoff(resposta, tentativa)
                continue

            return resposta

    def _atualizar_limite_da_conta(self, resposta: requests.Response):
        valor = resposta.headers.get("x-limit-api")
        if not valor:
            return
        try:
            valor_int = int(valor)
        except ValueError:
            return
        # Guarda defensiva: um `x-limit-api` <= 0 (visto em alguns cenários de
        # estrangulamento) gravaria rate_limit_por_minuto=0, e aí o limiter
        # trata como "limite desconhecido" e para de segurar — exatamente o
        # oposto do que queremos quando o Tiny já está reclamando.
        if valor_int <= 0:
            return
        if valor_int != self.instancia.rate_limit_por_minuto:
            self.instancia.rate_limit_por_minuto = valor_int
            self.instancia.save(update_fields=["rate_limit_por_minuto", "atualizado_em"])

    def _aguardar_backoff(self, resposta: requests.Response, tentativa: int):
        retry_after = resposta.headers.get("Retry-After")
        if retry_after:
            try:
                self._sleep(float(retry_after))
                return
            except ValueError:
                pass
        espera = min(self.BACKOFF_BASE_SEGUNDOS * (2 ** (tentativa - 1)), self.BACKOFF_MAXIMO_SEGUNDOS)
        self._sleep(espera)


def _base_url_padrao():
    from django.conf import settings

    return getattr(settings, "TINY_API_BASE_URL", "")
