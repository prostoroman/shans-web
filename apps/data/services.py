"""
Data services for caching and managing financial data.
"""

import logging
from datetime import datetime, date, timedelta
from typing import List, Dict, Any, Optional
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from .models import Instrument, PriceOHLC, Fundamentals, CachedWindow
from .fmp_client import (
    get_profile, get_price_series, get_key_metrics,
    get_financial_ratios, get_income_statement
)

logger = logging.getLogger(__name__)


def ensure_instrument(symbol: str) -> Optional[Instrument]:
    """
    Ensure instrument exists in database, create if not.
    
    Args:
        symbol: Stock symbol
        
    Returns:
        Instrument instance or None if error
    """
    try:
        # Check if instrument already exists
        instrument = Instrument.objects.filter(symbol=symbol.upper()).first()
        if instrument:
            return instrument
        
        # Get profile from FMP
        profile_data = get_profile(symbol)
        if not profile_data:
            logger.warning(f"No profile data found for {symbol}")
            return None
        
        # Create instrument
        with transaction.atomic():
            instrument = Instrument.objects.create(
                symbol=symbol.upper(),
                name=profile_data.get('companyName', ''),
                exchange=profile_data.get('exchange', ''),
                sector=profile_data.get('sector', ''),
                industry=profile_data.get('industry', ''),
                market_cap=profile_data.get('mktCap'),
                currency=profile_data.get('currency', 'USD'),
                is_active=True
            )
            logger.info(f"Created instrument: {instrument}")
            return instrument
            
    except Exception as e:
        logger.error(f"Error ensuring instrument {symbol}: {e}")
        return None


def ensure_prices(symbol: str, days: int = 1825) -> bool:
    """
    Ensure price data exists for symbol, fetch if not.
    
    Args:
        symbol: Stock symbol
        days: Number of days to fetch
        
    Returns:
        True if successful, False otherwise
    """
    try:
        instrument = ensure_instrument(symbol)
        if not instrument:
            return False
        
        # Calculate date range
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        # Check if we have recent data
        recent_price = PriceOHLC.objects.filter(
            instrument=instrument,
            date__gte=start_date
        ).first()
        
        if recent_price:
            logger.info(f"Price data already exists for {symbol}")
            return True
        
        # Fetch price data from FMP
        price_data = get_price_series(
            symbol,
            start_date.strftime('%Y-%m-%d'),
            end_date.strftime('%Y-%m-%d')
        )
        
        if not price_data:
            logger.warning(f"No price data found for {symbol}")
            return False
        
        # Save price data
        with transaction.atomic():
            prices_to_create = []
            for item in price_data:
                try:
                    price = PriceOHLC(
                        instrument=instrument,
                        date=datetime.strptime(item['date'], '%Y-%m-%d').date(),
                        open_price=Decimal(str(item.get('open', 0))),
                        high_price=Decimal(str(item.get('high', 0))),
                        low_price=Decimal(str(item.get('low', 0))),
                        close_price=Decimal(str(item.get('close', 0))),
                        volume=int(item.get('volume', 0)),
                        adjusted_close=Decimal(str(item.get('adjClose', 0))) if item.get('adjClose') else None
                    )
                    prices_to_create.append(price)
                except (ValueError, KeyError) as e:
                    logger.warning(f"Error parsing price data for {symbol}: {e}")
                    continue
            
            # Bulk create prices
            PriceOHLC.objects.bulk_create(prices_to_create, ignore_conflicts=True)
            logger.info(f"Created {len(prices_to_create)} price records for {symbol}")
            
            # Update cache window
            CachedWindow.objects.update_or_create(
                instrument=instrument,
                window_type='prices',
                start_date=start_date,
                end_date=end_date,
                defaults={'last_updated': timezone.now()}
            )
            
            return True
            
    except Exception as e:
        logger.error(f"Error ensuring prices for {symbol}: {e}")
        return False


def ensure_fundamentals(symbol: str) -> bool:
    """
    Ensure fundamental data exists for symbol, fetch if not.
    
    Args:
        symbol: Stock symbol
        
    Returns:
        True if successful, False otherwise
    """
    try:
        instrument = ensure_instrument(symbol)
        if not instrument:
            return False
        
        # Check if we have recent fundamental data
        recent_fundamentals = Fundamentals.objects.filter(
            instrument=instrument
        ).first()
        
        if recent_fundamentals:
            logger.info(f"Fundamental data already exists for {symbol}")
            return True
        
        # Fetch key metrics from FMP
        metrics_data = get_key_metrics(symbol)
        if not metrics_data:
            logger.warning(f"No fundamental data found for {symbol}")
            return False
        
        # Save fundamental data
        with transaction.atomic():
            try:
                fundamentals = Fundamentals.objects.create(
                    instrument=instrument,
                    period=date.today(),
                    pe_ratio=Decimal(str(metrics_data.get('peRatio', 0))) if metrics_data.get('peRatio') else None,
                    pb_ratio=Decimal(str(metrics_data.get('priceToBookRatio', 0))) if metrics_data.get('priceToBookRatio') else None,
                    debt_to_equity=Decimal(str(metrics_data.get('debtToEquity', 0))) if metrics_data.get('debtToEquity') else None,
                    roe=Decimal(str(metrics_data.get('roe', 0))) if metrics_data.get('roe') else None,
                    roa=Decimal(str(metrics_data.get('roa', 0))) if metrics_data.get('roa') else None,
                    current_ratio=Decimal(str(metrics_data.get('currentRatio', 0))) if metrics_data.get('currentRatio') else None
                )
                logger.info(f"Created fundamental data for {symbol}")
                
                # Update cache window
                CachedWindow.objects.update_or_create(
                    instrument=instrument,
                    window_type='fundamentals',
                    start_date=date.today(),
                    end_date=date.today(),
                    defaults={'last_updated': timezone.now()}
                )
                
                return True
                
            except (ValueError, KeyError) as e:
                logger.warning(f"Error parsing fundamental data for {symbol}: {e}")
                return False
                
    except Exception as e:
        logger.error(f"Error ensuring fundamentals for {symbol}: {e}")
        return False


def get_instrument_data(symbol: str, include_prices: bool = True, include_fundamentals: bool = True) -> Optional[Dict[str, Any]]:
    """
    Get comprehensive instrument data.
    
    Args:
        symbol: Stock symbol
        include_prices: Whether to include price data
        include_fundamentals: Whether to include fundamental data
        
    Returns:
        Dictionary with instrument data or None if error
    """
    try:
        instrument = ensure_instrument(symbol)
        if not instrument:
            return None
        
        data = {
            'instrument': instrument,
            'prices': [],
            'fundamentals': None
        }
        
        if include_prices:
            # Ensure we have price data
            if ensure_prices(symbol):
                data['prices'] = list(
                    PriceOHLC.objects.filter(instrument=instrument)
                    .order_by('-date')[:252]  # Last year of trading days
                )
        
        if include_fundamentals:
            # Ensure we have fundamental data
            if ensure_fundamentals(symbol):
                data['fundamentals'] = Fundamentals.objects.filter(
                    instrument=instrument
                ).first()
        
        return data
        
    except Exception as e:
        logger.error(f"Error getting instrument data for {symbol}: {e}")
        return None


def cleanup_old_data(days: int = 30) -> int:
    """
    Clean up old cached data.
    
    Args:
        days: Number of days to keep
        
    Returns:
        Number of records deleted
    """
    try:
        cutoff_date = timezone.now() - timedelta(days=days)
        
        # Delete old cached windows
        deleted_windows = CachedWindow.objects.filter(
            last_updated__lt=cutoff_date
        ).delete()[0]
        
        logger.info(f"Cleaned up {deleted_windows} old cached windows")
        return deleted_windows
        
    except Exception as e:
        logger.error(f"Error cleaning up old data: {e}")
        return 0