"""
API URL configuration for portfolio app.
"""

from django.urls import path
from .api import PortfolioAnalyzeAPIView, PortfolioListAPIView, PortfolioDetailAPIView

urlpatterns = [
    path('analyze/', PortfolioAnalyzeAPIView.as_view(), name='portfolio_analyze_api'),
    path('list/', PortfolioListAPIView.as_view(), name='portfolio_list_api'),
    path('<int:portfolio_id>/', PortfolioDetailAPIView.as_view(), name='portfolio_detail_api'),
]
