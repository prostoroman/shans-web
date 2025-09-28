"""
API URL configuration for markets app.
"""

from django.urls import path
from .api import MarketAPIView, CompareAPIView

urlpatterns = [
    path('info/', MarketAPIView.as_view(), name='market_api'),
    path('compare/', CompareAPIView.as_view(), name='compare_api'),
]
