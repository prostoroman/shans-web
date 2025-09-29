"""
URL configuration for activity app.
"""

from django.urls import path
from . import views

app_name = 'activity'

urlpatterns = [
    path('history/', views.history, name='history'),
    path('saved/', views.saved, name='saved'),
    path('save-set/', views.save_set, name='save_set'),
    path('saved/<int:set_id>/delete/', views.delete_saved_set, name='delete_saved_set'),
    path('clear-history/', views.clear_history, name='clear_history'),
]