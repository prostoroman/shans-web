"""
API URL configuration for portfolio app.
"""

from django.urls import path
from .api import PortfolioAnalyzeAPIView, PortfolioListAPIView, PortfolioDetailAPIView

urlpatterns = [
    # Backward-compatible legacy endpoint expected by tests
    path('analyze/', PortfolioAnalyzeAPIView.as_view(), name='portfolio_analyze_api_legacy'),
    path('v1/analyze/', PortfolioAnalyzeAPIView.as_view(), name='portfolio_analyze_api'),
    path('v1/list/', PortfolioListAPIView.as_view(), name='portfolio_list_api'),
    path('v1/<int:portfolio_id>/', PortfolioDetailAPIView.as_view(), name='portfolio_detail_api'),
]
