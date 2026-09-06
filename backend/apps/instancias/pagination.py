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
