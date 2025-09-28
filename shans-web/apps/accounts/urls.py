from django.urls import path
from . import views


urlpatterns = [
    path("dashboard", views.dashboard, name="dashboard"),
    path("account/profile", views.profile_edit, name="profile_edit"),
]

