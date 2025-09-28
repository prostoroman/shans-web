from django.urls import path
from . import views


urlpatterns = [
    path("info/<str:symbol>", views.info_page, name="info"),
    path("info", views.info_page, name="info_q"),
    path("compare/<str:symbols>", views.compare_page, name="compare"),
    path("compare", views.compare_page, name="compare_q"),
]

