"""
URL configuration for accounts app.
"""

from django.urls import path
from . import views

app_name = 'accounts'

urlpatterns = [
    path('dashboard/', views.dashboard, name='dashboard'),
    path('account/profile/', views.profile, name='account_profile'),
    path('account/upgrade/', views.upgrade_plan, name='upgrade_plan'),
]