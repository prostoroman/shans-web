from django.urls import path
from . import views


urlpatterns = [
    path("portfolio", views.portfolio_form, name="portfolio_form"),
    path("portfolio/analyze", views.portfolio_analyze, name="portfolio_analyze"),
]

