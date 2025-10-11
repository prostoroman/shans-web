"""
URL configuration for shans_web project.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.generic import RedirectView
from django.http import HttpResponse, FileResponse
from apps.markets import views
import os

def favicon_view(request):
    print("Favicon view called!")  # Debug print
    favicon_path = os.path.join(settings.STATICFILES_DIRS[0], 'images', 'favicon.ico')
    print(f"Favicon path: {favicon_path}")  # Debug print
    return FileResponse(open(favicon_path, 'rb'), content_type='image/x-icon')

urlpatterns = [
    # Favicon - must be first to avoid conflicts
    path('favicon.ico', favicon_view, name='favicon'),
    
    # Admin
    path('admin/', admin.site.urls),
    
    # Core pages
    path('', include('apps.core.urls')),
    
    # Market analysis
    path('markets/', include('apps.markets.urls')),
    
    # Direct compare routes
    path('compare/', views.compare, name='compare'),
    path('compare/<str:symbols>/', views.compare, name='compare_symbols'),
    
    # Portfolio analysis
    path('portfolio/', include('apps.portfolio.urls')),
    
    # User accounts and dashboard
    path('', include('apps.accounts.urls')),
    
    # Activity and history
    path('', include('apps.activity.urls')),
    
    # API endpoints
    path('api/', include('apps.markets.api_urls')),
    path('api/portfolio/', include('apps.portfolio.api_urls')),
    
    # Authentication (django-allauth)
    path('auth/', include('allauth.urls')),
]

# Serve static files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATICFILES_DIRS[0])