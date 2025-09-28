"""
Smoke tests for basic functionality.
"""

import pytest
from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth.models import User
from django.conf import settings


class SmokeTests(TestCase):
    """Basic smoke tests to ensure the application works."""
    
    def setUp(self):
        """Set up test data."""
        self.client = Client()
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_home_page_loads(self):
        """Test that the home page loads successfully."""
        response = self.client.get(reverse('core:home'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Shan's Web")
    
    def test_health_check(self):
        """Test that the health check endpoint works."""
        response = self.client.get(reverse('core:healthz'))
        self.assertEqual(response.status_code, 200)
        self.assertJSONEqual(response.content, {
            'status': 'healthy',
            'version': '1.0.0',
            'debug': settings.DEBUG
        })
    
    def test_robots_txt(self):
        """Test that robots.txt is served correctly."""
        response = self.client.get(reverse('core:robots_txt'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/plain')
        self.assertContains(response, 'User-agent: *')
    
    def test_sitemap_xml(self):
        """Test that sitemap.xml is served correctly."""
        response = self.client.get(reverse('core:sitemap_xml'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/xml')
        self.assertContains(response, '<?xml version="1.0" encoding="UTF-8"?>')
    
    def test_market_info_page(self):
        """Test that market info page loads."""
        response = self.client.get(reverse('markets:info'))
        self.assertEqual(response.status_code, 200)
    
    def test_compare_page(self):
        """Test that compare page loads."""
        response = self.client.get(reverse('markets:compare'))
        self.assertEqual(response.status_code, 200)
    
    def test_portfolio_form(self):
        """Test that portfolio form loads."""
        response = self.client.get(reverse('portfolio:form'))
        self.assertEqual(response.status_code, 200)
    
    def test_dashboard_requires_login(self):
        """Test that dashboard requires authentication."""
        response = self.client.get(reverse('accounts:dashboard'))
        self.assertEqual(response.status_code, 302)  # Redirect to login
    
    def test_dashboard_with_login(self):
        """Test that dashboard loads for authenticated user."""
        self.client.login(username='testuser', password='testpass123')
        response = self.client.get(reverse('accounts:dashboard'))
        self.assertEqual(response.status_code, 200)
    
    def test_profile_requires_login(self):
        """Test that profile page requires authentication."""
        response = self.client.get(reverse('accounts:profile'))
        self.assertEqual(response.status_code, 302)  # Redirect to login
    
    def test_history_requires_login(self):
        """Test that history page requires authentication."""
        response = self.client.get(reverse('activity:history'))
        self.assertEqual(response.status_code, 302)  # Redirect to login
    
    def test_saved_requires_login(self):
        """Test that saved page requires authentication."""
        response = self.client.get(reverse('activity:saved'))
        self.assertEqual(response.status_code, 302)  # Redirect to login


class ModelTests(TestCase):
    """Test model functionality."""
    
    def setUp(self):
        """Set up test data."""
        self.user = User.objects.create_user(
            username='testuser',
            email='test@example.com',
            password='testpass123'
        )
    
    def test_user_profile_creation(self):
        """Test that UserProfile is created when User is created."""
        from apps.accounts.models import UserProfile
        
        # UserProfile should be created automatically via signals
        self.assertTrue(hasattr(self.user, 'profile'))
        self.assertEqual(self.user.profile.status, 'basic')
        self.assertEqual(self.user.profile.locale, 'en')
    
    def test_user_profile_properties(self):
        """Test UserProfile properties."""
        profile = self.user.profile
        
        # Test basic plan properties
        self.assertFalse(profile.is_pro)
        self.assertEqual(profile.portfolio_limit, 3)
        self.assertEqual(profile.compare_limit, 4)
        self.assertEqual(profile.history_retention_days, 30)
        
        # Test pro plan properties
        profile.status = 'pro'
        profile.save()
        
        self.assertTrue(profile.is_pro)
        self.assertEqual(profile.portfolio_limit, 50)
        self.assertEqual(profile.compare_limit, 10)
        self.assertEqual(profile.history_retention_days, 365)


class APITests(TestCase):
    """Test API endpoints."""
    
    def setUp(self):
        """Set up test data."""
        self.client = Client()
    
    def test_market_api_endpoint_exists(self):
        """Test that market API endpoint exists."""
        response = self.client.get('/api/info/')
        # Should return 400 (missing symbol parameter) not 404
        self.assertEqual(response.status_code, 400)
    
    def test_compare_api_endpoint_exists(self):
        """Test that compare API endpoint exists."""
        response = self.client.get('/api/compare/')
        # Should return 400 (missing symbols parameter) not 404
        self.assertEqual(response.status_code, 400)
    
    def test_portfolio_api_endpoint_exists(self):
        """Test that portfolio API endpoint exists."""
        response = self.client.post('/api/portfolio/analyze/')
        # Should return 400 (missing data) not 404
        self.assertEqual(response.status_code, 400)


if __name__ == '__main__':
    pytest.main([__file__])