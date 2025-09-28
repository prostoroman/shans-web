"""
Context processors for accounts app.
"""

from django.utils.translation import gettext_lazy as _


def plan_status(request):
    """Add plan status to template context."""
    context = {
        'user_plan': 'basic',
        'is_pro': False,
        'plan_limits': {
            'portfolios': 3,
            'compare_symbols': 4,
            'history_days': 30,
        }
    }
    
    if request.user.is_authenticated and hasattr(request.user, 'profile'):
        profile = request.user.profile
        context.update({
            'user_plan': profile.status,
            'is_pro': profile.is_pro,
            'plan_limits': {
                'portfolios': profile.portfolio_limit,
                'compare_symbols': profile.compare_limit,
                'history_days': profile.history_retention_days,
            }
        })
    
    return context