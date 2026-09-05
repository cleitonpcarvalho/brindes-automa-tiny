from django.urls import path

from .views import AlertasView, AtividadeView, ResumoView

urlpatterns = [
    path("dashboard/resumo/", ResumoView.as_view(), name="dashboard-resumo"),
    path("dashboard/alertas/", AlertasView.as_view(), name="dashboard-alertas"),
    path("dashboard/atividade/", AtividadeView.as_view(), name="dashboard-atividade"),
]
