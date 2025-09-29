"""
API URL configuration for markets app.
"""

from django.urls import path
from .api import MarketAPIView, CompareAPIView, HistoryAPIView, ETFHoldingsAPIView

urlpatterns = [
    # Backward-compatible legacy endpoints expected by tests
    path('info/', MarketAPIView.as_view(), name='market_api_legacy'),
    path('compare/', CompareAPIView.as_view(), name='compare_api_legacy'),
    path('v1/info/<str:symbol>/', MarketAPIView.as_view(), name='market_api'),
    path('v1/compare/', CompareAPIView.as_view(), name='compare_api'),
    path('v1/history/<str:symbol>/', HistoryAPIView.as_view(), name='history_api'),
    path('v1/etf/<str:symbol>/holdings/', ETFHoldingsAPIView.as_view(), name='etf_holdings_api'),
]
