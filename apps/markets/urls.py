"""
URL configuration for markets app.
"""

from django.urls import path
from . import views

app_name = 'markets'

urlpatterns = [
    # Type-based info routes
    path('stock/<str:symbol>/', views.info, name='stock_info'),
    path('etf/<str:symbol>/', views.info, name='etf_info'),
    path('index/<str:symbol>/', views.info, name='index_info'),
    path('crypto/<str:symbol>/', views.info, name='crypto_info'),
    path('forex/<str:symbol>/', views.info, name='forex_info'),
    path('commodity/<str:symbol>/', views.info, name='commodity_info'),
    
    # Legacy routes for backward compatibility (redirect to homepage)
    path('info/', views.info, name='info'),
    path('info/<str:symbol>/', views.info, name='info_symbol'),
    
    path('debug-compare/', views.debug_compare, name='debug_compare'),
    path('debug-compare/<str:symbols>/', views.debug_compare, name='debug_compare_symbols'),
    path('save-compare/', views.save_compare_set, name='save_compare_set'),
]