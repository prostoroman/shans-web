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
from typing import List
from datetime import datetime, date, timedelta

from apps.data.models import Instrument, Commodity, Cryptocurrency, Forex
from apps.activity.models import ViewEvent
from apps.data.fmp_client import get_profile, get_commodities_quote, get_cryptocurrency_quote, get_forex_quote, search_by_company_name, search_by_isin
from .comparison_service import get_comparison_service
from .assets import AssetFactory, AssetType

logger = logging.getLogger(__name__)


def _get_days_for_period(period: str) -> int:
    """Get number of days for the given period."""
    period_map = {
        '1M': 30,
        '3M': 90,
        '6M': 180,
        'YTD': 365,  # Will be filtered to YTD in the chart
        '1Y': 365,
        '3Y': 1095,
        '5Y': 1825,
        '10Y': 3650,
    }
    # Always fetch more data than needed to ensure we have enough for filtering
    requested_days = period_map.get(period, 365)
    # Add buffer to ensure we have enough data for filtering
    return max(requested_days * 2, 3650)  # Fetch at least 10 years or 2x the requested period


def _get_years_for_period(period: str) -> float:
    """Get number of years for the given period."""
    period_map = {
        '1M': 30/365.25,
        '3M': 90/365.25,
        '6M': 180/365.25,
        'YTD': 1.0,  # Approximate for YTD
        '1Y': 1.0,
        '3Y': 3.0,
        '5Y': 5.0,
        '10Y': 10.0,
    }
    return period_map.get(period, 1.0)  # Default to 1 year


def _aggregate_monthly_data(prices: List) -> List:
    """
    Aggregate daily price data into monthly data points.
    
    Args:
        prices: List of price objects with date, close_price, etc.
        
    Returns:
        List of monthly aggregated price objects
    """
    if not prices:
        return prices
    
    # Group prices by year-month
    monthly_groups = {}
    for price in prices:
        # Use the last day of the month as the representative date
        year_month = (price.date.year, price.date.month)
        if year_month not in monthly_groups:
            monthly_groups[year_month] = []
        monthly_groups[year_month].append(price)
    
    # Create monthly aggregated data points
    monthly_prices = []
    for (year, month), month_prices in sorted(monthly_groups.items()):
        if not month_prices:
            continue
            
        # Sort by date to get chronological order
        month_prices.sort(key=lambda p: p.date)
        
        # Use the last trading day of the month
        last_price = month_prices[-1]
        
        # Create aggregated price object
        monthly_price = type('Price', (), {})()
        monthly_price.date = last_price.date
        monthly_price.close_price = last_price.close_price
        monthly_price.open_price = month_prices[0].open_price if month_prices[0].open_price else last_price.close_price
        monthly_price.high_price = max(p.high_price for p in month_prices if p.high_price) if any(p.high_price for p in month_prices) else last_price.close_price
        monthly_price.low_price = min(p.low_price for p in month_prices if p.low_price) if any(p.low_price for p in month_prices) else last_price.close_price
        monthly_price.volume = sum(p.volume for p in month_prices if p.volume) if any(p.volume for p in month_prices) else last_price.volume
        
        # Format prices
        monthly_price.open_price_formatted = f"₽{monthly_price.open_price:.2f}" if monthly_price.open_price else 'N/A'
        monthly_price.high_price_formatted = f"₽{monthly_price.high_price:.2f}" if monthly_price.high_price else 'N/A'
        monthly_price.low_price_formatted = f"₽{monthly_price.low_price:.2f}" if monthly_price.low_price else 'N/A'
        monthly_price.close_price_formatted = f"₽{monthly_price.close_price:.2f}" if monthly_price.close_price else 'N/A'
        monthly_price.volume_formatted = f"{monthly_price.volume:,}" if monthly_price.volume else 'N/A'
        
        # For template compatibility
        monthly_price.price = monthly_price.close_price
        monthly_price.formatted_price = monthly_price.close_price_formatted
        
        monthly_prices.append(monthly_price)
    
    return monthly_prices


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
    # Get period parameter for price chart
    period = request.GET.get('period', 'YTD')
    
    # Determine asset type from URL path
    asset_type = None
    if request.resolver_match and request.resolver_match.url_name:
        url_name = request.resolver_match.url_name
        if url_name == 'stock_info':
            asset_type = 'stock'
        elif url_name == 'etf_info':
            asset_type = 'etf'
        elif url_name == 'index_info':
            asset_type = 'index'
        elif url_name == 'crypto_info':
            asset_type = 'cryptocurrency'
        elif url_name == 'forex_info':
            asset_type = 'forex'
        elif url_name == 'commodity_info':
            asset_type = 'commodity'
    
    if not symbol:
        # Redirect to homepage since analysis form is now there
        return redirect('core:home')
        
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
                            # Redirect to the appropriate type-based symbol page
                            if asset_type == 'stock':
                                return redirect('markets:stock_info', symbol=symbol_upper)
                            elif asset_type == 'etf':
                                return redirect('markets:etf_info', symbol=symbol_upper)
                            elif asset_type == 'commodity':
                                return redirect('markets:commodity_info', symbol=symbol_upper)
                            elif asset_type == 'cryptocurrency':
                                return redirect('markets:crypto_info', symbol=symbol_upper)
                            elif asset_type == 'forex':
                                return redirect('markets:forex_info', symbol=symbol_upper)
                            else:
                                # Fallback to stock route
                                return redirect('markets:stock_info', symbol=symbol_upper)
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
                            # Redirect to the appropriate type-based symbol page
                            if asset_type == 'stock':
                                return redirect('markets:stock_info', symbol=symbol_upper)
                            elif asset_type == 'etf':
                                return redirect('markets:etf_info', symbol=symbol_upper)
                            elif asset_type == 'commodity':
                                return redirect('markets:commodity_info', symbol=symbol_upper)
                            elif asset_type == 'cryptocurrency':
                                return redirect('markets:crypto_info', symbol=symbol_upper)
                            elif asset_type == 'forex':
                                return redirect('markets:forex_info', symbol=symbol_upper)
                            else:
                                # Fallback to stock route
                                return redirect('markets:stock_info', symbol=symbol_upper)
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
    
    # Get price history using the asset based on period
    days = _get_days_for_period(period)
    raw_prices = asset.get_price_history(days=days)
    logger.info(f"Retrieved {len(raw_prices)} raw price records for {symbol} (period: {period}, days: {days})")
    
    # Debug: Check date range of raw data
    if raw_prices:
        dates = []
        for p in raw_prices:
            if isinstance(p, dict) and p.get('date'):
                dates.append(p['date'])
        if dates:
            min_date = min(dates)
            max_date = max(dates)
            logger.info(f"Raw data date range for {symbol}: {min_date} to {max_date}")
    
    
    # Convert raw prices to Price objects first
    prices = []
    for p in raw_prices:
        # Create a simple price object for template compatibility
        price_obj = type('Price', (), {})()
        
        # Ensure date is a datetime object for template formatting
        date_value = p.get('date')
        if isinstance(date_value, str):
            try:
                price_obj.date = datetime.strptime(date_value, '%Y-%m-%d')
            except ValueError:
                price_obj.date = datetime.now()
        elif not date_value:
            price_obj.date = datetime.now()
        else:
            price_obj.date = date_value
        
        # Try multiple possible field names for price data
        price_obj.close_price = (p.get('close') or 
                              p.get('adjClose') or 
                              p.get('price') or 
                              p.get('close_price'))
        price_obj.open_price = p.get('open') or p.get('open_price')
        price_obj.high_price = p.get('high') or p.get('high_price')
        price_obj.low_price = p.get('low') or p.get('low_price')
        price_obj.volume = p.get('volume')
        
        price_obj.open_price_formatted = f"₽{price_obj.open_price:.2f}" if price_obj.open_price else 'N/A'
        price_obj.high_price_formatted = f"₽{price_obj.high_price:.2f}" if price_obj.high_price else 'N/A'
        price_obj.low_price_formatted = f"₽{price_obj.low_price:.2f}" if price_obj.low_price else 'N/A'
        price_obj.close_price_formatted = f"₽{price_obj.close_price:.2f}" if price_obj.close_price else 'N/A'
        price_obj.volume_formatted = f"{price_obj.volume:,}" if price_obj.volume else 'N/A'
        
        # For template compatibility
        price_obj.price = price_obj.close_price
        price_obj.formatted_price = price_obj.close_price_formatted
        
        prices.append(price_obj)
    
    
    # Filter prices by period if needed
    if period == 'YTD':
        current_year = datetime.now().year
        prices = [p for p in prices if p.date.year == current_year]
        logger.info(f"Filtered to YTD: {len(prices)} records")
    else:
        # For other periods, ensure we have the correct date range
        today = datetime.now().date()
        
        if period == '1M':
            start_date = today - timedelta(days=30)
        elif period == '3M':
            start_date = today - timedelta(days=90)
        elif period == '6M':
            start_date = today - timedelta(days=180)
        elif period == '1Y':
            start_date = today - timedelta(days=365)
        elif period == '3Y':
            start_date = today - timedelta(days=1095)
        elif period == '5Y':
            start_date = today - timedelta(days=1825)
        elif period == '10Y':
            start_date = today - timedelta(days=3650)
        else:
            start_date = today - timedelta(days=3650)  # Default to 10Y
        
        # Filter prices to ensure they're within the period
        filtered_prices = [p for p in prices if p.date.date() >= start_date]
        
        if len(filtered_prices) != len(prices):
            logger.info(f"Filtered {symbol} from {len(prices)} to {len(filtered_prices)} records for period {period}")
            prices = filtered_prices
    
    # Apply monthly aggregation for very long periods to reduce chart density
    if period in ['3Y', '5Y', '10Y']:
        prices = _aggregate_monthly_data(prices)
        logger.info(f"Applied monthly aggregation for {period}: {len(prices)} monthly data points")
    
    # Check if API key is configured
    api_key = getattr(settings, 'FMP_API_KEY', '') or os.getenv('FMP_API_KEY', '')
    has_api_key = api_key and api_key != 'your_fmp_api_key_here'
    
    # If no API key and no data, provide sample data for demonstration
    if not raw_prices and not has_api_key:
        logger.info("No API key configured, providing sample data for demonstration")
        # Generate sample price data for demonstration
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
        
        # Convert sample prices to Price objects
        prices = []
        for p in raw_prices:
            # Create a simple price object for template compatibility
            price_obj = type('Price', (), {})()
            
            # Ensure date is a datetime object for template formatting
            date_value = p.get('date')
            if isinstance(date_value, str):
                try:
                    price_obj.date = datetime.strptime(date_value, '%Y-%m-%d')
                except ValueError:
                    price_obj.date = datetime.now()
            elif not date_value:
                price_obj.date = datetime.now()
            else:
                price_obj.date = date_value
            
            # Try multiple possible field names for price data
            price_obj.close_price = (p.get('close') or 
                                  p.get('adjClose') or 
                                  p.get('price') or 
                                  p.get('close_price'))
            price_obj.open_price = p.get('open') or p.get('open_price')
            price_obj.high_price = p.get('high') or p.get('high_price')
            price_obj.low_price = p.get('low') or p.get('low_price')
            price_obj.volume = p.get('volume')
            
            price_obj.open_price_formatted = f"₽{price_obj.open_price:.2f}" if price_obj.open_price else 'N/A'
            price_obj.high_price_formatted = f"₽{price_obj.high_price:.2f}" if price_obj.high_price else 'N/A'
            price_obj.low_price_formatted = f"₽{price_obj.low_price:.2f}" if price_obj.low_price else 'N/A'
            price_obj.close_price_formatted = f"₽{price_obj.close_price:.2f}" if price_obj.close_price else 'N/A'
            price_obj.volume_formatted = f"{price_obj.volume:,}" if price_obj.volume else 'N/A'
            
            # For template compatibility
            price_obj.price = price_obj.close_price
            price_obj.formatted_price = price_obj.close_price_formatted
            
            prices.append(price_obj)
    
    # Transform price data to match template expectations
    # prices are already converted to Price objects above
    logger.info(f"Transformed {len(prices)} price records for template")
    
    # Calculate metrics for template based on period
    metrics = {}
    if prices:
        try:
            from .metrics import calculate_metrics
            price_values = [float(p.close_price) for p in prices if p.close_price is not None]
            if price_values:
                # Calculate years based on period
                years = _get_years_for_period(period)
                # Determine frequency based on period (monthly vs daily)
                frequency = 12 if period in ['3Y', '5Y', '10Y'] else 252
                metrics = calculate_metrics(
                    price_values,
                    risk_free_rate=settings.DEFAULT_RF,
                    years=years,
                    frequency=frequency
                )
        except Exception as e:
            logger.warning(f"Failed to calculate metrics for {symbol}: {e}")
            metrics = {}
    
    # Prepare context based on asset type
    if asset.asset_type == AssetType.COMMODITY:
        context = {
            'title': f'{symbol} - {asset.name}',
            'symbol': symbol,
            'is_commodity': True,
            'quote': quote,
            'prices': prices,
            'metrics': metrics,
            'period': period,
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
            'metrics': metrics,
            'period': period,
            'show_search_form': False,
        }
    elif asset.asset_type == AssetType.FOREX:
        context = {
            'title': f'{symbol} - {asset.name}',
            'symbol': symbol,
            'is_forex': True,
            'quote': quote,
            'prices': prices,
            'metrics': metrics,
            'period': period,
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
            'metrics': metrics,
            'period': period,
            'show_search_form': False,
            'currency_symbol': '$' if asset.currency == 'USD' else asset.currency,
            'is_stock': True,
            'is_commodity': False,
            'is_cryptocurrency': False,
            'is_forex': False,
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
    normalize_mode = request.GET.get('normalize_mode', 'percent_change')
    
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


def detect_base_currency_from_symbol(symbol):
    """Detect base currency from symbol pattern."""
    symbol_upper = symbol.upper()
    
    # Forex pairs (6 characters: EURUSD, GBPUSD, etc.)
    if len(symbol_upper) == 6:
        base_currency = symbol_upper[:3]
        
        # Common forex base currencies
        forex_currencies = [
            'EUR', 'GBP', 'JPY', 'CHF', 'AUD', 'CAD', 'NZD', 'RUB', 
            'CNY', 'INR', 'BRL', 'MXN', 'KRW', 'SGD', 'HKD', 'NOK', 
            'SEK', 'DKK', 'PLN', 'CZK', 'HUF', 'TRY', 'ZAR'
        ]
        
        if base_currency in forex_currencies:
            return base_currency
    
    # Exchange suffixes
    exchange_currency_map = {
        '.L': 'GBP',      # London Stock Exchange
        '.PA': 'EUR',     # Paris Stock Exchange
        '.F': 'EUR',      # Frankfurt Stock Exchange
        '.BR': 'EUR',     # Brussels Stock Exchange
        '.AS': 'EUR',     # Amsterdam Stock Exchange
        '.MI': 'EUR',     # Milan Stock Exchange
        '.VI': 'EUR',     # Vienna Stock Exchange
        '.ST': 'SEK',     # Stockholm Stock Exchange
        '.OL': 'NOK',     # Oslo Stock Exchange
        '.CO': 'DKK',     # Copenhagen Stock Exchange
        '.HE': 'EUR',     # Helsinki Stock Exchange
        '.LS': 'EUR',     # Lisbon Stock Exchange
        '.MC': 'EUR',     # Madrid Stock Exchange
        '.AT': 'EUR',     # Athens Stock Exchange
        '.IR': 'EUR',     # Irish Stock Exchange
        '.SI': 'SGD',     # Singapore Exchange
        '.AX': 'AUD',     # Australian Securities Exchange
        '.TO': 'CAD',     # Toronto Stock Exchange
        '.MX': 'MXN',     # Mexican Stock Exchange
        '.SA': 'BRL',     # Brazilian Stock Exchange
        '.ME': 'RUB'      # Moscow Stock Exchange
    }
    
    for suffix, currency in exchange_currency_map.items():
        if symbol_upper.endswith(suffix):
            return currency
    
    # Default to USD for US exchanges and unknown
    return 'USD'


def compare(request, symbols=None):
    """Enhanced asset comparison page supporting multiple asset types."""
    # Get symbols from URL or query parameter
    if not symbols:
        symbols = request.GET.get('symbols', '')
    
    # Get comparison parameters
    base_currency = request.GET.get('base_currency', '').upper()
    include_dividends = True  # Always include dividends
    period = request.GET.get('period', 'YTD')
    normalize_mode = request.GET.get('normalize_mode', 'percent_change')
    
    # Validate base currency
    from .smart_currency_converter import get_smart_currency_converter
    currency_converter = get_smart_currency_converter()
    if base_currency and not currency_converter.is_currency_supported(base_currency):
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
    
    # Auto-detect base currency from first symbol if not provided
    if not base_currency and symbol_list:
        base_currency = detect_base_currency_from_symbol(symbol_list[0])
    
    # Default to USD if still no currency detected
    if not base_currency:
        base_currency = 'USD'
    
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