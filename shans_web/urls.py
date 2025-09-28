"""
URL configuration for shans_web project.
"""

from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static

urlpatterns = [
    # Admin
    path('admin/', admin.site.urls),
    
    # Core pages
    path('', include('apps.core.urls')),
    
    # Market analysis
    path('', include('apps.markets.urls')),
    
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
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)