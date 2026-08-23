from django.urls import path

from .views import (
    AnalysisChartImageView,
    AnalysisDetailView,
    AnalysisHistoryView,
    RunAnalysisView,
)

urlpatterns = [
    path("run/", RunAnalysisView.as_view(), name="run-analysis"),
    path("history/", AnalysisHistoryView.as_view(), name="analysis-history"),
    path("<uuid:id>/", AnalysisDetailView.as_view(), name="analysis-detail"),
    path("<uuid:id>/image/", AnalysisChartImageView.as_view(), name="analysis-image"),
]
