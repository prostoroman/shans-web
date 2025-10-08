"""
Market views for symbol info and comparison.
"""

from django.shortcuts import render, get_object_or_404, redirect
from django.http import JsonResponse, Http404
from django.views.decorators.http import require_http_methods
from django.utils.translation import gettext_lazy as _
from django.contrib.auth.decorators import login_required
from django.utils import timezone
from django.conf import settings
from django.contrib import messages
from django.db.models import Q
import logging
import os

from apps.data.models import Instrument, Commodity, Cryptocurrency, Forex
from apps.activity.models import ViewEvent
from apps.data.fmp_client import get_profile, get_commodities_quote, get_cryptocurrency_quote, get_forex_quote, search_by_company_name, search_by_isin
from .comparison_service import get_comparison_service
from .assets import AssetFactory, AssetType

logger = logging.getLogger(__name__)


def index(request):
    """Market overview page."""
    context = {
        'title': _('Markets'),
    }
    return render(request, 'markets/index.html', context)


def search(request):
    """Search for instruments."""
    query = request.GET.get('q', '').strip()
    results = []
    
    if query:
        # Search instruments
        instruments = Instrument.objects.filter(
            Q(symbol__icontains=query) | Q(name__icontains=query)
        )[:10]
        
        # Search commodities
        commodities = Commodity.objects.filter(
            Q(symbol__icontains=query) | Q(name__icontains=query)
        )[:5]
        
        # Search cryptocurrencies
        cryptos = Cryptocurrency.objects.filter(
            Q(symbol__icontains=query) | Q(name__icontains=query)
        )[:5]
        
        # Search forex
        forex_pairs = Forex.objects.filter(
            Q(symbol__icontains=query) | Q(name__icontains=query)
        )[:5]
        
        results = {
            'instruments': instruments,
            'commodities': commodities,
            'cryptocurrencies': cryptos,
            'forex': forex_pairs,
        }
    
    context = {
        'title': _('Search Markets'),
        'query': query,
        'results': results,
    }
    return render(request, 'markets/search.html', context)


def info(request, symbol=None):
    """Symbol information page."""
    if not symbol:
        # Handle search form submission
        query = request.GET.get('query', '').strip()
        search_type = request.GET.get('search_type', 'symbol')
        
        if query:
            # Perform search based on type
            search_results = []
            search_error = None
            
            try:
                if search_type == 'symbol':
                    # Search for exact symbol match first
                    try:
                        # Try to get data directly for the symbol
                        symbol_upper = query.upper()
                        data = None
                        asset_type = None
                        
                        # Check if it's a stock/ETF
                        try:
                            data = get_profile(symbol_upper)
                            if data:
                                asset_type = 'stock' if data.get('type') == 'stock' else 'etf'
                        except Exception:
                            pass
                        
                        # Check if it's a commodity
                        if not asset_type:
                            try:
                                data = get_commodities_quote(symbol_upper)
                                if data:
                                    asset_type = 'commodity'
                            except Exception:
                                pass
                        
                        # Check if it's a cryptocurrency
                        if not asset_type:
                            try:
                                data = get_cryptocurrency_quote(symbol_upper)
                                if data:
                                    asset_type = 'cryptocurrency'
                            except Exception:
                                pass
                        
                        # Check if it's forex
                        if not asset_type:
                            try:
                                data = get_forex_quote(symbol_upper)
                                if data:
                                    asset_type = 'forex'
                            except Exception:
                                pass
                        
                        if data:
                            # Redirect to the symbol page
                            return redirect('markets:info_symbol', symbol=symbol_upper)
                        else:
                            search_error = _('Symbol not found. Please check the symbol and try again.')
                            
                    except Exception as e:
                        logger.error(f"Error searching for symbol {query}: {e}")
                        search_error = _('Error searching for symbol. Please try again.')
                
                elif search_type == 'company':
                    # Search by company name using FMP API
                    try:
                        search_results = search_by_company_name(query)
                        if search_results:
                            # Show search results
                            context = {
                                'title': _('Search Results'),
                                'search_type': search_type,
                                'query': query,
                                'search_results': search_results,
                                'show_search_form': True,
                            }
                            return render(request, 'markets/info.html', context)
                        else:
                            search_error = _('No companies found with that name. Please try a different search term.')
                    except Exception as e:
                        logger.error(f"Error searching for company {query}: {e}")
                        search_error = _('Error searching for company. Please try again.')
                
                elif search_type == 'isin':
                    # Search by ISIN
                    try:
                        search_results = search_by_isin(query)
                        if search_results:
                            # Show search results
                            context = {
                                'title': _('Search Results'),
                                'search_type': search_type,
                                'query': query,
                                'search_results': search_results,
                                'show_search_form': True,
                            }
                            return render(request, 'markets/info.html', context)
                        else:
                            search_error = _('No instruments found with that ISIN. Please check the ISIN and try again.')
                    except Exception as e:
                        logger.error(f"Error searching for ISIN {query}: {e}")
                        search_error = _('Error searching for ISIN. Please try again.')
                
                elif search_type in ['etf', 'commodity', 'cryptocurrency', 'forex']:
                    # For these types, treat as symbol search
                    try:
                        symbol_upper = query.upper()
                        data = None
                        asset_type = None
                        
                        if search_type == 'etf':
                            try:
                                data = get_profile(symbol_upper)
                                if data and data.get('type') == 'etf':
                                    asset_type = 'etf'
                            except Exception:
                                pass
                        elif search_type == 'commodity':
                            try:
                                data = get_commodities_quote(symbol_upper)
                                if data:
                                    asset_type = 'commodity'
                            except Exception:
                                pass
                        elif search_type == 'cryptocurrency':
                            try:
                                data = get_cryptocurrency_quote(symbol_upper)
                                if data:
                                    asset_type = 'cryptocurrency'
                            except Exception:
                                pass
                        elif search_type == 'forex':
                            try:
                                data = get_forex_quote(symbol_upper)
                                if data:
                                    asset_type = 'forex'
                            except Exception:
                                pass
                        
                        if data:
                            # Redirect to the symbol page
                            return redirect('markets:info_symbol', symbol=symbol_upper)
                        else:
                            search_error = _('{} not found. Please check the symbol and try again.').format(search_type.title())
                            
                    except Exception as e:
                        logger.error(f"Error searching for {search_type} {query}: {e}")
                        search_error = _('Error searching for {}. Please try again.').format(search_type)
                
            except Exception as e:
                logger.error(f"Unexpected error during search: {e}")
                search_error = _('An unexpected error occurred. Please try again.')
            
            context = {
                'title': _('Search Results'),
                'show_search_form': True,
                'query': query,
                'search_type': search_type,
                'search_results': search_results if 'search_results' in locals() else [],
                'search_error': search_error,
                'no_results': not search_results and not search_error,
            }
            return render(request, 'markets/info.html', context)
        else:
            # Show search form when no symbol is provided
            context = {
                'title': _('Search Symbol'),
                'show_search_form': True,
            }
            return render(request, 'markets/info.html', context)
    
    symbol = symbol.upper()
    
    # Create asset using the factory
    try:
        asset = AssetFactory.create_asset(symbol)
        logger.info(f"Created asset {asset.asset_type.value} for symbol {symbol}")
    except Exception as e:
        logger.error(f"Error creating asset for {symbol}: {e}")
        context = {
            'title': f'{symbol} - Error',
            'symbol': symbol,
            'error': _('Error creating asset instance. Please check the symbol and try again.'),
        }
        return render(request, 'markets/info.html', context)
    
    # Get quote data to verify the asset exists
    quote = asset.get_quote()
    if not quote:
        # Check if API key is configured
        api_key = getattr(settings, 'FMP_API_KEY', '') or os.getenv('FMP_API_KEY', '')
        if not api_key or api_key == 'your_fmp_api_key_here':
            error_message = _('FMP API key not configured. Please set FMP_API_KEY in your environment variables.')
        else:
            error_message = _('No data found for this symbol. The symbol may not exist or the API may be temporarily unavailable.')
        
        context = {
            'title': f'{symbol} - Not Found',
            'symbol': symbol,
            'error': error_message,
        }
        return render(request, 'markets/info.html', context)
    
    # Log view event for authenticated users
    if request.user.is_authenticated:
        ViewEvent.objects.create(
            user=request.user,
            symbol=symbol,
            view_type='info'
        )
    
    # Get price history using the asset
    raw_prices = asset.get_price_history(days=365)
    logger.info(f"Retrieved {len(raw_prices)} raw price records for {symbol}")
    
    # Check if API key is configured
    api_key = getattr(settings, 'FMP_API_KEY', '') or os.getenv('FMP_API_KEY', '')
    has_api_key = api_key and api_key != 'your_fmp_api_key_here'
    
    # If no API key and no data, provide sample data for demonstration
    if not raw_prices and not has_api_key:
        logger.info("No API key configured, providing sample data for demonstration")
        # Generate sample price data for demonstration
        from datetime import datetime, timedelta
        import random
        
        base_price = 150.0  # Base price for SBERP.ME
        sample_prices = []
        current_date = datetime.now()
        
        for i in range(30):  # 30 days of sample data
            date = current_date - timedelta(days=i)
            # Generate realistic price movement
            price_change = random.uniform(-0.05, 0.05)  # ±5% daily change
            base_price *= (1 + price_change)
            
            sample_price = {
                'date': date.strftime('%Y-%m-%d'),
                'close': round(base_price, 2),
                'open': round(base_price * random.uniform(0.98, 1.02), 2),
                'high': round(base_price * random.uniform(1.01, 1.05), 2),
                'low': round(base_price * random.uniform(0.95, 0.99), 2),
                'volume': random.randint(1000000, 5000000),
            }
            sample_prices.append(sample_price)
        
        raw_prices = sample_prices
        logger.info(f"Generated {len(raw_prices)} sample price records")
    
    # Create a proper Price class for template compatibility
    class Price:
        def __init__(self, data):
            from datetime import datetime
            
            # Ensure date is a datetime object for template formatting
            date_value = data.get('date')
            if isinstance(date_value, str):
                try:
                    self.date = datetime.strptime(date_value, '%Y-%m-%d')
                except ValueError:
                    self.date = datetime.now()
            elif not date_value:
                self.date = datetime.now()
            else:
                self.date = date_value
            
            self.close_price = data.get('close') or data.get('adjClose')
            self.open_price = data.get('open')
            self.high_price = data.get('high')
            self.low_price = data.get('low')
            self.volume = data.get('volume')
            self.open_price_formatted = f"₽{data.get('open', 0):.2f}" if data.get('open') else 'N/A'
            self.high_price_formatted = f"₽{data.get('high', 0):.2f}" if data.get('high') else 'N/A'
            self.low_price_formatted = f"₽{data.get('low', 0):.2f}" if data.get('low') else 'N/A'
            self.close_price_formatted = f"₽{data.get('close', 0):.2f}" if data.get('close') else 'N/A'
    
    # Transform price data to match template expectations
    prices = [Price(price) for price in raw_prices]
    logger.info(f"Transformed {len(prices)} price records for template")
    
    # Prepare context based on asset type
    if asset.asset_type == AssetType.COMMODITY:
        context = {
            'title': f'{symbol} - {asset.name}',
            'symbol': symbol,
            'is_commodity': True,
            'quote': quote,
            'prices': prices,
            'show_search_form': False,
        }
    elif asset.asset_type == AssetType.CRYPTOCURRENCY:
        context = {
            'title': f'{symbol} - {asset.name}',
            'symbol': symbol,
            'is_cryptocurrency': True,
            'cryptocurrency': quote,
            'quote': quote,
            'prices': prices,
            'show_search_form': False,
        }
    elif asset.asset_type == AssetType.FOREX:
        context = {
            'title': f'{symbol} - {asset.name}',
            'symbol': symbol,
            'is_forex': True,
            'quote': quote,
            'prices': prices,
            'show_search_form': False,
        }
    else:
        # For stocks/ETFs, create an instrument-like object
        instrument = type('Instrument', (), {
            'name': asset.name,
            'exchange': asset.exchange,
            'sector': quote.get('sector', '') if quote else '',
            'industry': quote.get('industry', '') if quote else '',
            'currency': asset.currency,
            'market_cap_formatted': f"${quote.get('marketCap', 0):,.0f}".replace(',', ' ') if quote and quote.get('marketCap') else 'N/A',
            'is_active': True,
            'currency_symbol': '$' if asset.currency == 'USD' else asset.currency,
        })()
        
        context = {
            'title': f'{symbol} - {asset.name}',
            'symbol': symbol,
            'instrument': instrument,
            'data': quote,
            'prices': prices,
            'show_search_form': False,
        }
    
    logger.info(f"Final context for {symbol}: asset_type={asset.asset_type.value}, prices_count={len(prices)}")
    
    # Debug: Log context keys
    logger.info(f"Context keys: {list(context.keys())}")
    if prices:
        logger.info(f"First price object: date={prices[0].date}, close_price={prices[0].close_price}")
    
    return render(request, 'markets/info.html', context)


def debug_compare(request, symbols=None):
    """Debug comparison view to check metrics."""
    # Get symbols from URL or query parameter
    if not symbols:
        symbols = request.GET.get('symbols', '')
    
    # Get comparison parameters
    base_currency = request.GET.get('base_currency', 'USD').upper()
    include_dividends = True  # Always include dividends
    period = request.GET.get('period', 'YTD')
    normalize_mode = request.GET.get('normalize_mode', 'index100')
    
    if not symbols:
        context = {
            'title': _('Debug Compare'),
            'symbols': [],
            'base_currency': base_currency,
            'include_dividends': include_dividends,
            'period': period,
            'normalize_mode': normalize_mode,
        }
        return render(request, 'markets/debug_compare.html', context)
    
    # Parse symbols
    symbol_list = [s.strip().upper() for s in symbols.split(',') if s.strip()]
    
    try:
        # Use the comparison service
        comparison_service = get_comparison_service()
        comparison_result = comparison_service.compare_assets(
            symbol_list, 
            base_currency=base_currency,
            include_dividends=include_dividends,
            period=period,
            normalize_mode=normalize_mode
        )
        
        # Prepare context for template
        context = {
            'title': _('Debug Compare'),
            'symbols': symbol_list,
            'base_currency': base_currency,
            'include_dividends': include_dividends,
            'period': period,
            'normalize_mode': normalize_mode,
            'comparison_result': comparison_result,
        }
        
        return render(request, 'markets/debug_compare.html', context)
        
    except Exception as e:
        logger.error(f"Error in debug comparison for {symbols}: {e}")
        context = {
            'title': _('Debug Compare'),
            'error': str(e),
            'symbols': symbol_list,
            'base_currency': base_currency,
            'include_dividends': include_dividends,
            'period': period,
            'normalize_mode': normalize_mode,
        }
        return render(request, 'markets/debug_compare.html', context)


def compare(request, symbols=None):
    """Enhanced asset comparison page supporting multiple asset types."""
    # Get symbols from URL or query parameter
    if not symbols:
        symbols = request.GET.get('symbols', '')
    
    # Get comparison parameters
    base_currency = request.GET.get('base_currency', 'USD').upper()
    include_dividends = True  # Always include dividends
    period = request.GET.get('period', '1Y')
    normalize_mode = request.GET.get('normalize_mode', 'index100')
    
    # Validate base currency
    from .currency_converter import get_currency_converter
    currency_converter = get_currency_converter()
    if not currency_converter.is_currency_supported(base_currency):
        context = {
            'title': _('Compare Assets'),
            'error': _('Unsupported currency: {}').format(base_currency),
            'symbols': [],
            'base_currency': 'USD',  # Reset to default
            'include_dividends': include_dividends,
            'period': period,
            'normalize_mode': normalize_mode,
        }
        return render(request, 'markets/compare.html', context)
    
    if not symbols:
        # Show form for symbol input
        context = {
            'title': _('Compare Assets'),
            'symbols': [],
            'base_currency': base_currency,
            'include_dividends': include_dividends,
            'period': period,
            'normalize_mode': normalize_mode,
        }
        return render(request, 'markets/compare.html', context)
    
    # Parse symbols
    symbol_list = [s.strip().upper() for s in symbols.split(',') if s.strip()]
    
    if len(symbol_list) < 2:
        context = {
            'title': _('Compare Assets'),
            'error': _('Please provide at least 2 symbols to compare'),
            'symbols': symbol_list,
            'base_currency': base_currency,
            'include_dividends': include_dividends,
            'period': period,
            'normalize_mode': normalize_mode,
        }
        return render(request, 'markets/compare.html', context)
    
    # Check user limits
    if request.user.is_authenticated:
        profile = request.user.profile
        if len(symbol_list) > profile.compare_limit:
            context = {
                'title': _('Compare Assets'),
                'error': _('Too many symbols. Limit is {} for {} plan.').format(
                    profile.compare_limit, profile.status
                ),
                'symbols': symbol_list,
                'base_currency': base_currency,
                'include_dividends': include_dividends,
                'period': period,
                'normalize_mode': normalize_mode,
            }
            return render(request, 'markets/compare.html', context)
    
    # Check if FMP API key is configured
    if not hasattr(settings, 'FMP_API_KEY') or not settings.FMP_API_KEY or settings.FMP_API_KEY == 'your_fmp_api_key_here':
        context = {
            'title': _('Compare Assets'),
            'error': _('FMP API key not configured. Please set FMP_API_KEY in your environment variables.'),
            'symbols': symbol_list,
            'base_currency': base_currency,
            'include_dividends': include_dividends,
            'period': period,
            'normalize_mode': normalize_mode,
        }
        return render(request, 'markets/compare.html', context)
    
    try:
        # Use the new comparison service
        comparison_service = get_comparison_service()
        comparison_result = comparison_service.compare_assets(
            symbol_list, 
            base_currency=base_currency,
            include_dividends=include_dividends,
            period=period,
            normalize_mode=normalize_mode
        )
        
        # Debug: Check comparison result type
        logger.info(f"Comparison result type: {type(comparison_result)}")
        logger.info(f"Comparison result: {comparison_result}")
        
        if isinstance(comparison_result, str):
            logger.error(f"Comparison service returned string instead of dict: {comparison_result}")
            context = {
                'title': _('Compare Assets'),
                'error': _('Error loading comparison data'),
                'symbols': symbol_list,
                'base_currency': base_currency,
                'include_dividends': include_dividends,
                'period': period,
                'normalize_mode': normalize_mode,
            }
            return render(request, 'markets/compare.html', context)
        
        if 'error' in comparison_result:
            context = {
                'title': _('Compare Assets'),
                'error': comparison_result['error'],
                'symbols': symbol_list,
                'base_currency': base_currency,
                'include_dividends': include_dividends,
                'period': period,
                'normalize_mode': normalize_mode,
            }
            return render(request, 'markets/compare.html', context)
        
        # Log view event for authenticated users
        if request.user.is_authenticated:
            ViewEvent.objects.create(
                user=request.user,
                symbol=','.join(symbol_list),
                view_type='compare'
            )
        
        # Prepare context for template
        context = {
            'title': _('Compare Assets'),
            'symbols': symbol_list,
            'base_currency': base_currency,
            'include_dividends': include_dividends,
            'period': period,
            'normalize_mode': normalize_mode,
            'comparison_result': comparison_result,
            'assets': comparison_result.get('assets', {}),
            'metrics': comparison_result.get('metrics', {}),
            'correlation_matrix': comparison_result.get('correlation_matrix', {}),
            'failed_symbols': comparison_result.get('failed_symbols', []),
            'successful_symbols': comparison_result.get('successful_symbols', []),
        }
        
        return render(request, 'markets/compare.html', context)
        
    except Exception as e:
        logger.error(f"Error loading comparison for {symbols}: {e}")
        context = {
            'title': _('Compare Assets'),
            'error': _('Error loading comparison data'),
            'symbols': symbol_list,
            'base_currency': base_currency,
            'include_dividends': include_dividends,
            'period': period,
            'normalize_mode': normalize_mode,
        }
        return render(request, 'markets/compare.html', context)


@login_required
@require_http_methods(["POST"])
def save_compare_set(request):
    """Save comparison set for authenticated users."""
    try:
        symbols = request.POST.get('symbols', '').strip()
        name = request.POST.get('name', '').strip()
        
        if not symbols or not name:
            return JsonResponse({'success': False, 'error': _('Symbols and name are required')})
        
        # Parse symbols
        symbol_list = [s.strip().upper() for s in symbols.split(',') if s.strip()]
        
        # Check user limits
        profile = request.user.profile
        if len(symbol_list) > profile.compare_limit:
            return JsonResponse({
                'success': False, 
                'error': _('Too many symbols. Limit is {} for {} plan.').format(
                    profile.compare_limit, profile.status
                )
            })
        
        # Create comparison set (you'll need to implement this model)
        # For now, just return success
        return JsonResponse({'success': True})
        
    except Exception as e:
        logger.error(f"Error saving comparison set: {e}")
        return JsonResponse({'success': False, 'error': _('Error saving comparison set')})


def commodities(request):
    """Commodities overview page."""
    commodities = Commodity.objects.all()[:20]
    
    context = {
        'title': _('Commodities'),
        'commodities': commodities,
    }
    return render(request, 'markets/commodities.html', context)


def cryptocurrencies(request):
    """Cryptocurrencies overview page."""
    cryptos = Cryptocurrency.objects.all()[:20]
    
    context = {
        'title': _('Cryptocurrencies'),
        'cryptocurrencies': cryptos,
    }
    return render(request, 'markets/cryptocurrencies.html', context)


def forex(request):
    """Forex overview page."""
    forex_pairs = Forex.objects.all()[:20]
    
    context = {
        'title': _('Forex'),
        'forex_pairs': forex_pairs,
    }
    return render(request, 'markets/forex.html', context)