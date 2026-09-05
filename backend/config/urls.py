from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/", include("apps.instancias.urls")),
    path("api/", include("apps.dashboard.urls")),
    # Schema OpenAPI — usado pelo frontend para gerar tipos TypeScript
    # (openapi-typescript), não editado à mão (ver frontend/package.json).
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
]
