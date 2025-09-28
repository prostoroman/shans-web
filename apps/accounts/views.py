"""
Account views for user profile and dashboard.
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.utils.translation import gettext_lazy as _
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods

from .models import UserProfile


@login_required
def dashboard(request):
    """User dashboard view."""
    user = request.user
    profile = user.profile
    
    # Get user statistics
    portfolio_count = user.portfolios.count()
    saved_sets_count = user.saved_sets.count()
    recent_views = user.view_events.all()[:10]
    
    context = {
        'title': _('Dashboard'),
        'profile': profile,
        'portfolio_count': portfolio_count,
        'saved_sets_count': saved_sets_count,
        'recent_views': recent_views,
        'plan_limits': {
            'portfolios': profile.portfolio_limit,
            'compare_symbols': profile.compare_limit,
            'history_days': profile.history_retention_days,
        }
    }
    
    return render(request, 'accounts/dashboard.html', context)


@login_required
def profile(request):
    """User profile view."""
    user = request.user
    profile = user.profile
    
    if request.method == 'POST':
        # Update profile
        locale = request.POST.get('locale', 'en')
        if locale in ['en', 'ru']:
            profile.locale = locale
            profile.save()
            messages.success(request, _('Profile updated successfully.'))
            return redirect('accounts:profile')
    
    context = {
        'title': _('Profile'),
        'profile': profile,
    }
    
    return render(request, 'accounts/profile.html', context)


@login_required
@require_http_methods(["POST"])
def upgrade_plan(request):
    """Upgrade user plan (stub for future billing integration)."""
    profile = request.user.profile
    
    if profile.status == 'basic':
        # In a real implementation, this would integrate with billing
        profile.status = 'pro'
        profile.save()
        messages.success(request, _('Plan upgraded to Pro!'))
    else:
        messages.info(request, _('You already have the Pro plan.'))
    
    return redirect('accounts:dashboard')