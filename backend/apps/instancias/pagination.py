from rest_framework.pagination import PageNumberPagination


class InstanciaPagination(PageNumberPagination):
    page_size = 10
    page_size_query_param = "page_size"
    max_page_size = 100


class ProdutoEspelhoPagination(PageNumberPagination):
    """Aba Produtos do detalhe da instância — página um pouco maior que a
    listagem de instâncias porque a linha é bem mais densa de informação."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class ExecucaoPagination(PageNumberPagination):
    """Aba Execuções do detalhe da instância — histórico de sincronizações."""

    page_size = 20
    page_size_query_param = "page_size"
    max_page_size = 100


class LogItemPagination(PageNumberPagination):
    """Logs de uma execução — página grande porque a UI mostra o log inteiro
    de uma vez (modal somente-leitura), sem paginação visível."""

    page_size = 200
    page_size_query_param = "page_size"
    max_page_size = 500


class ExecucaoProdutoPagination(PageNumberPagination):
    """Tabela de auditoria por SKU da tela de detalhe da execução —
    paginada no servidor (podem ser milhares de linhas)."""

    page_size = 25
    page_size_query_param = "page_size"
    max_page_size = 100
