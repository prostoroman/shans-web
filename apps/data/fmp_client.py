"""
Financial Modeling Prep client wrapper using direct HTTP requests.
"""

import os
import logging
import requests
from typing import Dict, List, Optional, Any
from datetime import datetime, date

logger = logging.getLogger(__name__)

# FMP API configuration
BASE_URL = "https://financialmodelingprep.com/api/v3"

def _get_api_key():
    """Get API key from Django settings."""
    try:
        from django.conf import settings
        return getattr(settings, 'FMP_API_KEY', '')
    except ImportError:
        # Fallback to environment variable if Django not available
        return os.getenv("FMP_API_KEY", "")


def _make_request(endpoint: str, params: Dict[str, Any] = None) -> Optional[List[Dict[str, Any]]]:
    """
    Make a request to the FMP API.
    
    Args:
        endpoint: API endpoint
        params: Query parameters
        
    Returns:
        Response data or None if error
    """
    api_key = _get_api_key()
    if not api_key:
        logger.error("FMP_API_KEY not configured")
        return None
    
    url = f"{BASE_URL}/{endpoint}"
    params = params or {}
    params['apikey'] = api_key
    
    try:
        response = requests.get(url, params=params, timeout=30)
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else [data] if data else []
    except requests.exceptions.RequestException as e:
        logger.error(f"API request failed: {e}")
        return None
    except Exception as e:
        logger.error(f"Error processing API response: {e}")
        return None


def get_profile(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Get company profile for a symbol.
    
    Args:
        symbol: Stock symbol
        
    Returns:
        Company profile data or None if error
    """
    try:
        data = _make_request(f"profile/{symbol}")
        if data and len(data) > 0:
            return data[0]
        return None
    except Exception as e:
        logger.error(f"Error getting profile for {symbol}: {e}")
        return None


def get_price_series(symbol: str, start_date: Optional[str] = None, end_date: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Get historical price data for a symbol.
    
    Args:
        symbol: Stock symbol
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        
    Returns:
        List of price data
    """
    try:
        params = {}
        if start_date:
            params['from'] = start_date
        if end_date:
            params['to'] = end_date
        
        data = _make_request(f"historical-price-full/{symbol}", params)
        if not data:
            return []
        
        # Extract the historical data from the response
        if data and len(data) > 0 and 'historical' in data[0]:
            return data[0]['historical']
        
        return []
    except Exception as e:
        logger.error(f"Error getting price series for {symbol}: {e}")
        return []


def get_key_metrics(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Get key metrics for a symbol.
    
    Args:
        symbol: Stock symbol
        
    Returns:
        Key metrics data or None if error
    """
    try:
        # Try key metrics first
        data = _make_request(f"key-metrics/{symbol}", {'limit': 1})
        if data and len(data) > 0:
            return data[0]
        
        # Fallback to ratios
        data = _make_request(f"ratios/{symbol}", {'limit': 1})
        if data and len(data) > 0:
            return data[0]
        
        return None
    except Exception as e:
        logger.error(f"Error getting key metrics for {symbol}: {e}")
        return None


def get_financial_ratios(symbol: str) -> List[Dict[str, Any]]:
    """
    Get financial ratios for a symbol.
    
    Args:
        symbol: Stock symbol
        
    Returns:
        List of financial ratios
    """
    try:
        data = _make_request(f"ratios/{symbol}")
        return data if data else []
    except Exception as e:
        logger.error(f"Error getting financial ratios for {symbol}: {e}")
        return []


def get_income_statement(symbol: str, limit: int = 1) -> List[Dict[str, Any]]:
    """
    Get income statement for a symbol.
    
    Args:
        symbol: Stock symbol
        limit: Number of periods to return
        
    Returns:
        List of income statements
    """
    try:
        data = _make_request(f"income-statement/{symbol}", {'limit': limit})
        return data if data else []
    except Exception as e:
        logger.error(f"Error getting income statement for {symbol}: {e}")
        return []


def get_balance_sheet(symbol: str, limit: int = 1) -> List[Dict[str, Any]]:
    """
    Get balance sheet for a symbol.
    
    Args:
        symbol: Stock symbol
        limit: Number of periods to return
        
    Returns:
        List of balance sheets
    """
    try:
        data = _make_request(f"balance-sheet-statement/{symbol}", {'limit': limit})
        return data if data else []
    except Exception as e:
        logger.error(f"Error getting balance sheet for {symbol}: {e}")
        return []


def get_cash_flow(symbol: str, limit: int = 1) -> List[Dict[str, Any]]:
    """
    Get cash flow statement for a symbol.
    
    Args:
        symbol: Stock symbol
        limit: Number of periods to return
        
    Returns:
        List of cash flow statements
    """
    try:
        data = _make_request(f"cash-flow-statement/{symbol}", {'limit': limit})
        return data if data else []
    except Exception as e:
        logger.error(f"Error getting cash flow for {symbol}: {e}")
        return []


def get_quote(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Get real-time quote for a symbol.
    
    Args:
        symbol: Stock symbol
        
    Returns:
        Quote data or None if error
    """
    try:
        data = _make_request(f"quote/{symbol}")
        if data and len(data) > 0:
            return data[0]
        return None
    except Exception as e:
        logger.error(f"Error getting quote for {symbol}: {e}")
        return None


def search_symbols(query: str) -> List[Dict[str, Any]]:
    """
    Search for symbols by company name or symbol.
    
    Args:
        query: Search query
        
    Returns:
        List of matching symbols
    """
    try:
        data = _make_request("search", {'query': query})
        return data if data else []
    except Exception as e:
        logger.error(f"Error searching symbols for {query}: {e}")
        return []


def get_market_cap(symbol: str) -> Optional[float]:
    """
    Get market capitalization for a symbol.
    
    Args:
        symbol: Stock symbol
        
    Returns:
        Market cap value or None if error
    """
    try:
        data = _make_request(f"market-capitalization/{symbol}")
        if data and len(data) > 0:
            return data[0].get('marketCap')
        return None
    except Exception as e:
        logger.error(f"Error getting market cap for {symbol}: {e}")
        return None


def get_dividend_history(symbol: str) -> List[Dict[str, Any]]:
    """
    Get dividend history for a symbol.
    
    Args:
        symbol: Stock symbol
        
    Returns:
        List of dividend payments
    """
    try:
        data = _make_request(f"historical-price-full/stock_dividend/{symbol}")
        return data if data else []
    except Exception as e:
        logger.error(f"Error getting dividend history for {symbol}: {e}")
        return []


def get_earnings_calendar(symbol: str) -> List[Dict[str, Any]]:
    """
    Get earnings calendar for a symbol.
    
    Args:
        symbol: Stock symbol
        
    Returns:
        List of earnings dates
    """
    try:
        data = _make_request(f"earning_calendar", {'symbol': symbol})
        return data if data else []
    except Exception as e:
        logger.error(f"Error getting earnings calendar for {symbol}: {e}")
        return []