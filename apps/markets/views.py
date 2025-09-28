"""
Market views for symbol info and comparison.
"""

from django.shortcuts import render, get_object_or_404
from django.http import JsonResponse, Http404
from django.views.decorators.http import require_http_methods
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.conf import settings
import logging

from apps.data.services import get_instrument_data
from apps.data.models import Instrument
from apps.activity.models import ViewEvent
from .metrics import calculate_metrics
from .api import MarketAPIView

logger = logging.getLogger(__name__)


def info(request, symbol=None):
    """Symbol info page."""
    # Get symbol from URL or query parameter
    if not symbol:
        symbol = request.GET.get('symbol', '').upper()
    
    if not symbol:
        # Show symbol search form when no symbol is provided
        context = {
            'title': _('Stock Information'),
            'symbol': '',
            'show_search_form': True,
        }
        return render(request, 'markets/info.html', context)
    
    # Check if FMP API key is configured
    from django.conf import settings
    if not hasattr(settings, 'FMP_API_KEY') or not settings.FMP_API_KEY or settings.FMP_API_KEY == 'your_fmp_api_key_here':
        context = {
            'title': f'{symbol} - Configuration Required',
            'symbol': symbol,
            'error': _('FMP API key not configured. Please set FMP_API_KEY in your environment variables.'),
            'instrument': None,
            'prices': [],
            'fundamentals': None,
            'metrics': {},
        }
        return render(request, 'markets/info.html', context)
    
    try:
        # Get instrument data
        data = get_instrument_data(symbol, include_prices=True, include_fundamentals=True)
        if not data:
            context = {
                'title': f'{symbol} - Not Found',
                'symbol': symbol,
                'error': _('Symbol not found or no data available.'),
                'instrument': None,
                'prices': [],
                'fundamentals': None,
                'metrics': {},
            }
            return render(request, 'markets/info.html', context)
        
        instrument = data['instrument']
        prices = data['prices']
        fundamentals = data['fundamentals']
        
        # Calculate metrics
        if prices:
            price_values = [float(p.close_price) for p in prices]
            metrics = calculate_metrics(
                price_values, 
                risk_free_rate=settings.DEFAULT_RF,
                years=5.0
            )
        else:
            metrics = {}
        
        # Log view event for authenticated users
        if request.user.is_authenticated:
            ViewEvent.objects.create(
                user=request.user,
                symbol=symbol,
                view_type='info'
            )
        
        context = {
            'title': f'{symbol} - {instrument.name}',
            'symbol': symbol,
            'instrument': instrument,
            'prices': prices[:252],  # Last year
            'fundamentals': fundamentals,
            'metrics': metrics,
        }
        
        return render(request, 'markets/info.html', context)
        
    except Exception as e:
        logger.error(f"Error loading info for {symbol}: {e}")
        context = {
            'title': f'{symbol} - Error',
            'symbol': symbol,
            'error': _('Error loading symbol data. Please check the symbol and try again.'),
            'instrument': None,
            'prices': [],
            'fundamentals': None,
            'metrics': {},
        }
        return render(request, 'markets/info.html', context)


def compare(request, symbols=None):
    """Symbol comparison page."""
    # Get symbols from URL or query parameter
    if not symbols:
        symbols = request.GET.get('symbols', '')
    
    if not symbols:
        # Show form for symbol input
        context = {
            'title': _('Compare Symbols'),
            'symbols': [],
        }
        return render(request, 'markets/compare.html', context)
    
    # Parse symbols
    symbol_list = [s.strip().upper() for s in symbols.split(',') if s.strip()]
    
    if len(symbol_list) < 2:
        context = {
            'title': _('Compare Symbols'),
            'error': _('Please provide at least 2 symbols to compare'),
            'symbols': symbol_list,
        }
        return render(request, 'markets/compare.html', context)
    
    # Check user limits
    if request.user.is_authenticated:
        profile = request.user.profile
        if len(symbol_list) > profile.compare_limit:
            context = {
                'title': _('Compare Symbols'),
                'error': _('Too many symbols. Limit is {} for {} plan.').format(
                    profile.compare_limit, profile.status
                ),
                'symbols': symbol_list,
            }
            return render(request, 'markets/compare.html', context)
    
    # Check if FMP API key is configured
    if not hasattr(settings, 'FMP_API_KEY') or not settings.FMP_API_KEY or settings.FMP_API_KEY == 'your_fmp_api_key_here':
        context = {
            'title': _('Compare Symbols'),
            'error': _('FMP API key not configured. Please set FMP_API_KEY in your environment variables.'),
            'symbols': symbol_list,
        }
        return render(request, 'markets/compare.html', context)
    
    try:
        # Get data for all symbols
        instruments_data = {}
        all_metrics = {}
        
        for symbol in symbol_list:
            data = get_instrument_data(symbol, include_prices=True, include_fundamentals=True)
            if data:
                instruments_data[symbol] = data
                
                # Calculate metrics
                if data['prices']:
                    price_values = [float(p.close_price) for p in data['prices']]
                    metrics = calculate_metrics(
                        price_values,
                        risk_free_rate=settings.DEFAULT_RF,
                        years=5.0
                    )
                    all_metrics[symbol] = metrics
        
        # Calculate correlation matrix
        correlation_matrix = {}
        if len(symbol_list) >= 2:
            for i, symbol1 in enumerate(symbol_list):
                for j, symbol2 in enumerate(symbol_list):
                    if i < j and symbol1 in all_metrics and symbol2 in all_metrics:
                        # This is a simplified correlation calculation
                        # In a real implementation, you'd align the price series
                        correlation_matrix[f"{symbol1}_{symbol2}"] = 0.5  # Placeholder
        
        # Log view event for authenticated users
        if request.user.is_authenticated:
            ViewEvent.objects.create(
                user=request.user,
                symbol=','.join(symbol_list),
                view_type='compare'
            )
        
        # Create symbol data list for easier template access
        symbol_data = []
        for symbol in symbol_list:
            data = {
                'symbol': symbol,
                'metrics': all_metrics.get(symbol, {}),
                'has_data': symbol in instruments_data,
            }
            if symbol in instruments_data:
                data['instrument_data'] = instruments_data[symbol]
            symbol_data.append(data)

        context = {
            'title': _('Compare Symbols'),
            'symbols': symbol_list,
            'symbol_data': symbol_data,
            'instruments_data': instruments_data,
            'metrics': all_metrics,
            'correlation_matrix': correlation_matrix,
        }
        
        return render(request, 'markets/compare.html', context)
        
    except Exception as e:
        logger.error(f"Error loading comparison for {symbols}: {e}")
        context = {
            'title': _('Compare Symbols'),
            'error': _('Error loading comparison data'),
            'symbols': symbol_list,
        }
        return render(request, 'markets/compare.html', context)


@login_required
@require_http_methods(["POST"])
def save_compare_set(request):
    """Save comparison set for authenticated users."""
    symbols = request.POST.get('symbols', '')
    name = request.POST.get('name', '')
    
    if not symbols or not name:
        return JsonResponse({'error': _('Symbols and name are required')}, status=400)
    
    symbol_list = [s.strip().upper() for s in symbols.split(',') if s.strip()]
    
    # Check user limits
    profile = request.user.profile
    if len(symbol_list) > profile.compare_limit:
        return JsonResponse({
            'error': _('Too many symbols. Limit is {} for {} plan.').format(
                profile.compare_limit, profile.status
            )
        }, status=400)
    
    try:
        from apps.activity.models import SavedSet
        
        SavedSet.objects.create(
            user=request.user,
            name=name,
            set_type='compare',
            payload={'symbols': symbol_list}
        )
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        logger.error(f"Error saving compare set: {e}")
        return JsonResponse({'error': _('Error saving comparison set')}, status=500)