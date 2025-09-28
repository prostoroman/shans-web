"""
Activity views for viewing history and saved sets.
"""

from django.shortcuts import render
from django.contrib.auth.decorators import login_required
from django.utils.translation import gettext_lazy as _
from django.core.paginator import Paginator
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
import logging

from .models import ViewEvent, SavedSet

logger = logging.getLogger(__name__)


@login_required
def history(request):
    """User viewing history."""
    # Get user's view events
    view_events = ViewEvent.objects.filter(user=request.user).order_by('-timestamp')
    
    # Paginate
    paginator = Paginator(view_events, 50)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'title': _('Viewing History'),
        'page_obj': page_obj,
        'view_events': page_obj,
    }
    
    return render(request, 'activity/history.html', context)


@login_required
def saved(request):
    """User saved sets."""
    # Get user's saved sets
    saved_sets = SavedSet.objects.filter(user=request.user).order_by('-created_at')
    
    # Paginate
    paginator = Paginator(saved_sets, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'title': _('Saved Sets'),
        'page_obj': page_obj,
        'saved_sets': page_obj,
    }
    
    return render(request, 'activity/saved.html', context)


@login_required
@require_http_methods(["POST"])
def save_set(request):
    """Save a comparison set or portfolio."""
    set_type = request.POST.get('set_type', '')
    name = request.POST.get('name', '')
    payload = request.POST.get('payload', '')
    
    if not all([set_type, name, payload]):
        return JsonResponse({'error': _('All fields are required')}, status=400)
    
    try:
        import json
        payload_data = json.loads(payload)
        
        SavedSet.objects.create(
            user=request.user,
            name=name,
            set_type=set_type,
            payload=payload_data
        )
        
        return JsonResponse({'success': True})
        
    except json.JSONDecodeError:
        return JsonResponse({'error': _('Invalid payload format')}, status=400)
    except Exception as e:
        logger.error(f"Error saving set: {e}")
        return JsonResponse({'error': _('Error saving set')}, status=500)


@login_required
@require_http_methods(["POST"])
def delete_saved_set(request, set_id):
    """Delete a saved set."""
    try:
        saved_set = SavedSet.objects.get(id=set_id, user=request.user)
        saved_set.delete()
        return JsonResponse({'success': True})
    except SavedSet.DoesNotExist:
        return JsonResponse({'error': _('Set not found')}, status=404)
    except Exception as e:
        logger.error(f"Error deleting saved set: {e}")
        return JsonResponse({'error': _('Error deleting set')}, status=500)


@login_required
@require_http_methods(["POST"])
def clear_history(request):
    """Clear user's viewing history."""
    try:
        # Get user's profile to check retention period
        profile = request.user.profile
        retention_days = profile.history_retention_days
        
        # Delete old events (this is a simplified implementation)
        # In a real implementation, you'd use a date filter
        ViewEvent.objects.filter(user=request.user).delete()
        
        return JsonResponse({'success': True})
    except Exception as e:
        logger.error(f"Error clearing history: {e}")
        return JsonResponse({'error': _('Error clearing history')}, status=500)