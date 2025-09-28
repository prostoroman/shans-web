"""
URL configuration for markets app.
"""

from django.urls import path
from . import views

app_name = 'markets'

urlpatterns = [
    path('info/', views.info, name='info'),
    path('info/<str:symbol>/', views.info, name='info_symbol'),
    path('compare/', views.compare, name='compare'),
    path('compare/<str:symbols>/', views.compare, name='compare_symbols'),
    path('save-compare/', views.save_compare_set, name='save_compare_set'),
]