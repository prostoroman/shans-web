"""
URL configuration for portfolio app.
"""

from django.urls import path
from . import views

app_name = 'portfolio'

urlpatterns = [
    path('', views.portfolio_form, name='form'),
    path('list/', views.portfolio_list, name='list'),
    path('<int:portfolio_id>/', views.portfolio_detail, name='detail'),
    path('<int:portfolio_id>/delete/', views.delete_portfolio, name='delete'),
]