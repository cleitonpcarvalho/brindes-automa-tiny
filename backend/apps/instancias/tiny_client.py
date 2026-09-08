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


class TinyEscritaBloqueadaError(TinyApiError):
    """
    O cliente foi criado em modo somente-leitura e algo tentou um método de
    escrita (POST/PUT/PATCH/DELETE). É uma trava de segurança do --dry-run,
    não um erro da API.
    """


_METODOS_DE_ESCRITA = {"POST", "PUT", "PATCH", "DELETE"}


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

    # `buscar_produto_por_sku` traz uma página pequena (não `limit=1`) porque
    # o filtro `codigo` da API do Tiny não é garantidamente igualdade exata
    # (pode casar por prefixo/"contém"). A regra operacional do projeto é:
    # SKU do fornecedor == SKU no espelho == SKU no Tiny, e a ÚNICA chave de
    # correspondência com o Tiny é o SKU EXATO — então a igualdade é
    # reconfirmada aqui, no nosso código, sobre o campo `sku` do item.
    LIMITE_BUSCA_SKU = 20

    def __init__(self, instancia, base_url=None, sleep_fn=time.sleep, limiter=None, somente_leitura=False):
        self.instancia = instancia
        self.base_url = base_url if base_url is not None else _base_url_padrao()
        self._sleep = sleep_fn
        self._limiter = limiter or RateLimiterCompartilhado(instancia.slug, sleep_fn=sleep_fn)
        # Modo --dry-run: GET liberado, qualquer escrita levanta antes de sair
        # da máquina. Também não persiste `rate_limit_por_minuto` (o dry-run
        # não deve alterar NENHUM dado local).
        self.somente_leitura = somente_leitura

    # -- API pública de baixo nível ----------------------------------------

    def get(self, caminho: str, **kwargs) -> requests.Response:
        return self._request("GET", caminho, **kwargs)

    def post(self, caminho: str, **kwargs) -> requests.Response:
        return self._request("POST", caminho, **kwargs)

    def put(self, caminho: str, **kwargs) -> requests.Response:
        return self._request("PUT", caminho, **kwargs)

    # -- API de domínio (produtos/estoque) ----------------------------------

    def buscar_produto_por_sku(self, sku: str) -> dict | None:
        """
        GET /produtos?codigo=<sku> — a ÚNICA busca de existência do fluxo
        operacional: devolve o produto do Tiny cujo `sku` é EXATAMENTE igual
        ao pedido, ou None. Nunca casa por nome, NCM, aproximação ou prefixo
        — se o Tiny devolver itens cujo `sku` não bate letra a letra, eles
        são ignorados (para o fluxo é "não existe" e o SKU pode ser criado).
        """
        resposta = self.get("/produtos", params={"codigo": sku, "limit": self.LIMITE_BUSCA_SKU})
        self._levantar_se_erro(resposta)
        itens = resposta.json().get("itens", [])
        return next((item for item in itens if item.get("sku") == sku), None)

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
        """
        POST /produtos — cria um produto tipo 'S' (Simples). Uma Variacao = um
        produto. O Tiny responde HTTP 201 com {"id", "codigo", "descricao"}.
        """
        resposta = self.post("/produtos", json=payload)
        self._levantar_se_erro(resposta)
        return self._corpo(resposta)

    def atualizar_produto(self, produto_id, payload: dict) -> dict:
        """
        PUT /produtos/{idProduto} — atualiza um produto JÁ existente. O Tiny
        responde HTTP 204 (sem corpo) em caso de sucesso.

        Passa pelo mesmo rate limiter / autenticação de todo `_request`, e em
        modo `somente_leitura=True` levanta `TinyEscritaBloqueadaError` ANTES
        de qualquer chamada HTTP (PUT é método de escrita).

        Não mexe em anexos (endpoint próprio `PUT /produtos/{id}/anexos`) nem
        move saldo de estoque (`POST /estoque/{id}`). A montagem do payload
        — inclusive a proteção de "só campos graváveis" — é responsabilidade
        de quem chama.
        """
        resposta = self.put(f"/produtos/{produto_id}", json=payload)
        self._levantar_se_erro(resposta)
        return self._corpo(resposta)

    def anexos_do_produto(self, id_produto) -> list[str]:
        """
        URLs dos anexos que o produto JÁ tem no Tiny (do `GET /produtos/{id}`,
        que devolve `anexos` só no detalhe — ver `catalogo.ProdutoTiny`).

        ATENÇÃO: quando enviamos com `externo=false`, o Tiny BAIXA a imagem e
        passa a devolver aqui a URL INTERNA dele
        (`s3.amazonaws.com/tiny-anexos-us/...`), diferente da URL original do
        fornecedor. Por isso o chamador NÃO deve comparar essas URLs com as
        do espelho por igualdade — só a CONTAGEM é confiável (ver
        `sincronizar_imagens_tiny`, que usa `Variacao.imagens_tiny_sincronizadas`
        como marcador das URLs originais).
        """
        detalhe = self.obter_produto(id_produto)
        anexos = detalhe.get("anexos") or []
        urls = []
        for anexo in anexos:
            url = anexo.get("url") if isinstance(anexo, dict) else None
            if isinstance(url, str) and url.strip():
                urls.append(url.strip())
        return urls

    def sincronizar_anexos_produto(self, id_produto, urls) -> dict:
        """
        Define os anexos (imagens) de um produto já existente no Tiny, pelo
        endpoint `PUT /produtos/{idProduto}/anexos`.

        Enviamos com `externo=false` (comportamento CONFIRMADO em produção no
        MC511): o Tiny baixa a imagem e a hospeda internamente, e aí ela
        aparece no cadastro e na listagem do ERP — com `externo=true` a URL
        ficava registrada mas a imagem não aparecia.

        Quem chama garante: só links reais, no máximo 5, e só chama quando há
        de fato imagem a (re)definir.

        Body (contrato oficial Olist ERP v3, confirmado manualmente): LISTA
        JSON direta `[{"url": ..., "externo": false}]`, sem chave "anexos" —
        ver `_corpo_anexos()`.
        """
        resposta = self.put(f"/produtos/{id_produto}/anexos", json=_corpo_anexos(urls))
        self._levantar_se_erro(resposta)
        return self._corpo(resposta)

    def atualizar_preco_venda(self, id_produto, *, preco) -> dict:
        """
        Atualiza SOMENTE o preço de VENDA de um produto (`PUT /produtos/{id}/preco`,
        corpo `{"preco": <valor>}`).

        ATENÇÃO à regra definitiva do cliente (2026-09-08): o valor do
        fornecedor é CUSTO e o preço de venda no Tiny fica sempre 0 — nenhum
        fluxo chama este método de rotina. Ele fica como wrapper fiel do
        endpoint (útil para forçar venda=0 pontualmente). O CUSTO (`precoCusto`)
        NÃO passa por aqui — este endpoint não aceita `precoCusto`; para
        custo/descrição/fornecedor use `atualizar_produto` (comando
        `corrigir_dados_produto_tiny`).
        """
        resposta = self.put(f"/produtos/{id_produto}/preco", json={"preco": float(preco)})
        self._levantar_se_erro(resposta)
        return self._corpo(resposta)

    def atualizar_estoque(self, id_produto, *, quantidade, preco_unitario) -> dict:
        """
        POST /estoque/{idProduto}, tipo Balanço (define o saldo absoluto, não
        um delta).

        `precoUnitario` aqui é o CUSTO do lançamento de balanço exigido por
        esse endpoint — coerente com a regra definitiva (o valor do fornecedor
        é custo). Quem chama manda `Variacao.preco_custo_tiny` (= `Variacao.preco`).
        """
        resposta = self.post(
            f"/estoque/{id_produto}",
            json={
                "tipo": "B",
                "quantidade": float(quantidade),
                "precoUnitario": float(preco_unitario),
            },
        )
        self._levantar_se_erro(resposta)
        return self._corpo(resposta)

    @staticmethod
    def _levantar_se_erro(resposta: requests.Response):
        # Sucesso é QUALQUER 2xx — o Tiny responde 201 no POST /produtos,
        # e pode responder 200/204 nos PUT/POST de preço e estoque.
        if 200 <= resposta.status_code < 300:
            return
        corpo = TinyApiClient._corpo(resposta)
        mensagem = corpo.get("mensagem") or f"Tiny retornou {resposta.status_code}: {resposta.text[:300]}"
        raise TinyApiValidationError(mensagem, corpo.get("detalhes"))

    @staticmethod
    def _corpo(resposta: requests.Response) -> dict:
        """Corpo JSON (objeto) da resposta, ou {} quando não há corpo (ex.: 204) / não é objeto."""
        try:
            corpo = resposta.json()
        except ValueError:
            return {}
        return corpo if isinstance(corpo, dict) else {}

    # -- mecânica interna ----------------------------------------------------

    def _request(self, metodo: str, caminho: str, **kwargs) -> requests.Response:
        if self.somente_leitura and metodo in _METODOS_DE_ESCRITA:
            raise TinyEscritaBloqueadaError(
                f"Cliente em modo somente-leitura (--dry-run): {metodo} {caminho} bloqueado."
            )
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
        if self.somente_leitura:
            return  # dry-run não grava nada local, nem esse cache
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


def _corpo_anexos(urls) -> list[dict]:
    """
    Body do `PUT /produtos/{id}/anexos` — ponto ÚNICO de definição do formato.
    Contrato oficial (Olist ERP v3, confirmado manualmente): LISTA JSON
    direta, SEM chave "anexos", e `externo=false` para o Tiny BAIXAR e
    hospedar a imagem (confirmado no MC511 — com `externo=true` a imagem não
    aparecia no ERP):

        [{"url": "<url original do fornecedor>", "externo": false}, ...]
    """
    return [{"url": url, "externo": False} for url in urls]


def _base_url_padrao():
    from django.conf import settings

    return getattr(settings, "TINY_API_BASE_URL", "")
