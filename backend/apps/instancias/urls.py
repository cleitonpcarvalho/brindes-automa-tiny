from django.urls import path
from rest_framework.routers import DefaultRouter

from .auth_views import LoginView, LogoutView, MeView
from .views import InstanciaViewSet, TinyOAuthCallbackView

router = DefaultRouter()
router.register("instancias", InstanciaViewSet, basename="instancia")

urlpatterns = router.urls + [
    path(
        "tiny/oauth/callback/<slug:slug>/",
        TinyOAuthCallbackView.as_view(),
        name="tiny-oauth-callback",
    ),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/me/", MeView.as_view(), name="auth-me"),
]
