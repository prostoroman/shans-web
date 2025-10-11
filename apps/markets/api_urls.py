"""
API URL configuration for markets app.
"""

from django.urls import path
from .api import (
    MarketAPIView,
    CompareAPIView,
    HistoryAPIView,
    ETFHoldingsAPIView,
    CommoditiesAPIView,
    CommoditiesSearchAPIView,
    ForexAPIView,
    ForexSearchAPIView,
    SymbolSearchAPIView,
    ExchangeAPIView,
    AISummaryStartAPIView,
    AISummaryStatusAPIView,
    AISummaryGetAPIView,
)

urlpatterns = [
    # Backward-compatible legacy endpoints expected by tests
    path('info/', MarketAPIView.as_view(), name='market_api_legacy'),
    path('compare/', CompareAPIView.as_view(), name='compare_api_legacy'),
    path('v1/info/<str:symbol>/', MarketAPIView.as_view(), name='market_api'),
    path('v1/compare/', CompareAPIView.as_view(), name='compare_api'),
    path('v1/history/<str:symbol>/', HistoryAPIView.as_view(), name='history_api'),
    path('v1/etf/<str:symbol>/holdings/', ETFHoldingsAPIView.as_view(), name='etf_holdings_api'),
    # Commodities endpoints
    path('v1/commodities/<str:symbol>/', CommoditiesAPIView.as_view(), name='commodities_api'),
    path('v1/commodities/search/', CommoditiesSearchAPIView.as_view(), name='commodities_search_api'),
    # Forex endpoints
    path('v1/forex/<str:symbol>/', ForexAPIView.as_view(), name='forex_api'),
    path('v1/forex/search/', ForexSearchAPIView.as_view(), name='forex_search_api'),
    # Comprehensive symbol search
    path('v1/search/', SymbolSearchAPIView.as_view(), name='symbol_search_api'),
    # Exchange data
    path('v1/exchanges/', ExchangeAPIView.as_view(), name='exchange_api'),
    # AI summary endpoints
    path('v1/ai/summary/start', AISummaryStartAPIView.as_view(), name='ai_summary_start'),
    path('v1/ai/summary/status', AISummaryStatusAPIView.as_view(), name='ai_summary_status'),
    path('v1/ai/summary/<str:symbol>/', AISummaryGetAPIView.as_view(), name='ai_summary_get'),
]
