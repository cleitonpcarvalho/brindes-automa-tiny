from django.urls import path
from rest_framework.routers import DefaultRouter

from .auth_views import LoginView, LogoutView, MeView
from .views import (
    CadenciaFornecedorDetailView,
    CadenciasFornecedorView,
    ConfiguracoesInstanciaView,
    CredencialFornecedorDetailView,
    CredenciaisFornecedorView,
    ExecucaoLogsView,
    ExecucoesInstanciaView,
    InstanciaViewSet,
    ProdutosEspelhoView,
    SincronizarFornecedorView,
    TinyOAuthCallbackView,
)

router = DefaultRouter()
router.register("instancias", InstanciaViewSet, basename="instancia")

urlpatterns = router.urls + [
    path(
        "tiny/oauth/callback/<slug:slug>/",
        TinyOAuthCallbackView.as_view(),
        name="tiny-oauth-callback",
    ),
    path(
        "instancias/<slug:slug>/credenciais/",
        CredenciaisFornecedorView.as_view(),
        name="instancia-credenciais",
    ),
    path(
        "instancias/<slug:slug>/credenciais/<str:fornecedor>/",
        CredencialFornecedorDetailView.as_view(),
        name="instancia-credencial-detalhe",
    ),
    path(
        "instancias/<slug:slug>/configuracoes/",
        ConfiguracoesInstanciaView.as_view(),
        name="instancia-configuracoes",
    ),
    path(
        "instancias/<slug:slug>/cadencias/",
        CadenciasFornecedorView.as_view(),
        name="instancia-cadencias",
    ),
    path(
        "instancias/<slug:slug>/cadencias/<str:fornecedor>/",
        CadenciaFornecedorDetailView.as_view(),
        name="instancia-cadencia-detalhe",
    ),
    path(
        "instancias/<slug:slug>/fornecedores/<str:fornecedor>/sincronizar/",
        SincronizarFornecedorView.as_view(),
        name="instancia-fornecedor-sincronizar",
    ),
    path(
        "instancias/<slug:slug>/produtos/",
        ProdutosEspelhoView.as_view(),
        name="instancia-produtos",
    ),
    path(
        "instancias/<slug:slug>/execucoes/",
        ExecucoesInstanciaView.as_view(),
        name="instancia-execucoes",
    ),
    path(
        "instancias/<slug:slug>/execucoes/<int:execucao_id>/logs/",
        ExecucaoLogsView.as_view(),
        name="instancia-execucao-logs",
    ),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
]
