"""
Financial Modeling Prep client wrapper.

Priority: use the official `fmp_python` client if available, with robust
retry/backoff and aggressive Django cache. Fallback to direct HTTP if needed.
"""

import os
import re
import time
import logging
from typing import Dict, List, Optional, Any, Callable, Tuple
from datetime import datetime, date
from django.db.models import Q

import requests

try:
    # Official client
    from fmp_python import FMP  # type: ignore
except Exception:  # pragma: no cover - optional dependency import guard
    FMP = None  # type: ignore

logger = logging.getLogger(__name__)

# FMP API configuration
BASE_URL = "https://financialmodelingprep.com/api/v3"
STABLE_BASE_URL = "https://financialmodelingprep.com/stable"


def _sanitize_cache_key(key_part: str) -> str:
    """
    Sanitize cache key part to remove characters that cause memcached warnings.
    
    Args:
        key_part: The part of the cache key to sanitize
        
    Returns:
        Sanitized cache key part safe for memcached
    """
    # Replace spaces, periods, and other problematic characters with underscores
    # Keep alphanumeric characters, hyphens, and underscores
    sanitized = re.sub(r'[^a-zA-Z0-9_-]', '_', str(key_part))
    # Remove multiple consecutive underscores
    sanitized = re.sub(r'_+', '_', sanitized)
    # Remove leading/trailing underscores
    sanitized = sanitized.strip('_')
    return sanitized


def _get_settings():
    """Safe access to Django settings inside functions."""
    try:
        from django.conf import settings
        return settings
    except Exception:  # pragma: no cover
        class _S:
            DEFAULT_RF = 0.03
            CACHE_TTL_EOD = 60 * 60
            CACHE_TTL_RATIOS = 45 * 60
            CACHE_TTL_INTRADAY = 8 * 60
            FMP_API_KEY = os.getenv("FMP_API_KEY", "")

        return _S()


def _get_api_key() -> str:
    settings = _get_settings()
    return getattr(settings, "FMP_API_KEY", "") or os.getenv("FMP_API_KEY", "")


def _get_cache():
    try:
        from django.core.cache import cache
        return cache
    except Exception:  # pragma: no cover - cache may not be available in some contexts
        return None


def _retry_with_backoff(func: Callable[[], Any], attempts: int = 3, base_delay: float = 0.5) -> Any:
    """Retry a callable with exponential backoff."""
    last_exc: Optional[Exception] = None
    for attempt in range(attempts):
        try:
            return func()
        except Exception as exc:  # noqa: BLE001
            last_exc = exc
            # Check if it's a timeout or connection error that should be retried
            should_retry = (
                'timeout' in str(exc).lower() or
                'connection' in str(exc).lower() or
                'read timed out' in str(exc).lower() or
                'HTTPSConnectionPool' in str(exc)
            )
            
            if attempt < attempts - 1 and should_retry:
                delay = base_delay * (2 ** attempt)
                logger.warning(f"Retrying after {delay}s due to {type(exc).__name__}: {exc}")
                time.sleep(delay)
            elif not should_retry:
                # Don't retry for non-network errors
                break
                
    if last_exc:
        raise last_exc
    return None


def _cached_call(cache_key: str, ttl: int, loader: Callable[[], Any]) -> Any:
    cache = _get_cache()
    if cache is not None:
        cached = cache.get(cache_key)
        if cached is not None:
            return cached
    value = _retry_with_backoff(loader)
    if cache is not None and value is not None:
        cache.set(cache_key, value, ttl)
    return value


def _http_get_json(endpoint: str, params: Optional[Dict[str, Any]] = None, timeout: int = 8, use_stable: bool = False) -> Any:
    api_key = _get_api_key()
    if not api_key:
        logger.error("FMP_API_KEY not configured")
        return None
    
    base_url = STABLE_BASE_URL if use_stable else BASE_URL
    url = f"{base_url}/{endpoint}"
    query = dict(params or {})
    query["apikey"] = api_key
    
    try:
        resp = requests.get(url, params=query, timeout=timeout)
        resp.raise_for_status()
        data = resp.json()
        return data
    except requests.exceptions.Timeout as e:
        logger.warning(f"Timeout requesting {endpoint}: {e}")
        raise
    except requests.exceptions.ConnectionError as e:
        logger.warning(f"Connection error requesting {endpoint}: {e}")
        raise
    except requests.exceptions.RequestException as e:
        logger.warning(f"Request error for {endpoint}: {e}")
        raise


_fmp_client: Optional[Any] = None


def _get_fmp() -> Optional[Any]:
    global _fmp_client
    if _fmp_client is not None:
        return _fmp_client
    api_key = _get_api_key()
    if not api_key or FMP is None:
        return None
    try:
        _fmp_client = FMP(apikey=api_key)  # type: ignore[arg-type]
        return _fmp_client
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning(f"Failed to init fmp_python client, will use HTTP fallback: {exc}")
        return None


def get_profile(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Get company profile for a symbol.
    
    Args:
        symbol: Stock symbol
        
    Returns:
        Company profile data or None if error
    """
    settings = _get_settings()
    cache_key = f"fmp:profile:{symbol.upper()}"
    ttl = settings.CACHE_TTL_EOD

    def loader():
        client = _get_fmp()
        if client is not None:
            # fmp_python method names may vary; try common ones
            for method_name in ("company_profile", "profile"):
                if hasattr(client, method_name):
                    data = getattr(client, method_name)(symbol)
                    if isinstance(data, list):
                        return data[0] if data else None
                    return data
        data = _http_get_json(f"profile/{symbol}")
        if isinstance(data, list):
            return data[0] if data else None
        return data

    try:
        return _cached_call(cache_key, ttl, loader)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting profile for {symbol}: {e}")
        return None


def get_price_series(symbol: str, start_date: Optional[str] = None, end_date: Optional[str] = None, include_dividends: bool = False) -> List[Dict[str, Any]]:
    """
    Get historical price data for a symbol.
    
    Args:
        symbol: Stock symbol
        start_date: Start date (YYYY-MM-DD)
        end_date: End date (YYYY-MM-DD)
        include_dividends: Whether to use dividend-adjusted prices
        
    Returns:
        List of price data
    """
    settings = _get_settings()
    ttl = settings.CACHE_TTL_EOD
    cache_key = f"fmp:hist:{symbol.upper()}:{start_date or ''}:{end_date or ''}:dividend_adjusted_{include_dividends}:light_v2"

    def loader():
        if include_dividends:
            # Use dividend-adjusted endpoint for stocks and ETFs
            params: Dict[str, Any] = {}
            if start_date:
                params["from"] = start_date
            if end_date:
                params["to"] = end_date
            
            # Use the stable dividend-adjusted endpoint
            data = _http_get_json(f"historical-price-eod/dividend-adjusted", {
                "symbol": symbol,
                **params
            }, use_stable=True)
            
            if isinstance(data, list):
                return data
            return []
        else:
            # Use the stable historical-price-eod/light endpoint for better historical data
            params: Dict[str, Any] = {}
            if start_date:
                params["from"] = start_date
            if end_date:
                params["to"] = end_date
            
            try:
                data = _http_get_json("historical-price-eod/light", {
                    "symbol": symbol,
                    **params
                }, use_stable=True)
                
                if isinstance(data, list):
                    return data
                if isinstance(data, dict) and "historical" in data:
                    return data.get("historical", [])
                return []
            except Exception as e:
                logger.warning(f"Error fetching light endpoint for {symbol}: {e}")
                # Fallback to regular historical price endpoint
                client = _get_fmp()
                if client is not None and hasattr(client, "historical_price_full"):
                    data = client.historical_price_full(symbol, _from=start_date, to=end_date)  # type: ignore[call-arg]
                    # client may return dict with 'historical'
                    if isinstance(data, dict) and "historical" in data:
                        return data.get("historical", [])
                    if isinstance(data, list) and data and isinstance(data[0], dict) and "historical" in data[0]:
                        return data[0]["historical"]
                    return data or []
                params: Dict[str, Any] = {}
                if start_date:
                    params["from"] = start_date
                if end_date:
                    params["to"] = end_date
                data = _http_get_json(f"historical-price-full/{symbol}", params)
                if isinstance(data, list) and data and "historical" in data[0]:
                    return data[0]["historical"]
                if isinstance(data, dict) and "historical" in data:
                    return data.get("historical", [])
                return []

    try:
        result = _cached_call(cache_key, ttl, loader)
        return result or []
    except Exception as e:  # noqa: BLE001
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
    settings = _get_settings()
    ttl = settings.CACHE_TTL_RATIOS
    cache_key = f"fmp:key_metrics:{symbol.upper()}"

    def loader():
        client = _get_fmp()
        if client is not None:
            for method_name in ("key_metrics", "key_metrics_ttm"):
                if hasattr(client, method_name):
                    data = getattr(client, method_name)(symbol, limit=1)
                    if isinstance(data, list):
                        if data:
                            return data[0]
                    elif isinstance(data, dict):
                        return data
        data = _http_get_json(f"key-metrics/{symbol}", {"limit": 1})
        if isinstance(data, list) and data:
            return data[0]
        if not data:
            data = _http_get_json(f"ratios/{symbol}", {"limit": 1})
            if isinstance(data, list) and data:
                return data[0]
        return None

    try:
        return _cached_call(cache_key, ttl, loader)
    except Exception as e:  # noqa: BLE001
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
    settings = _get_settings()
    ttl = settings.CACHE_TTL_RATIOS
    cache_key = f"fmp:ratios:{symbol.upper()}"

    def loader():
        client = _get_fmp()
        if client is not None and hasattr(client, "ratios"):
            data = client.ratios(symbol)
            return data or []
        data = _http_get_json(f"ratios/{symbol}")
        return data or []

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
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
    settings = _get_settings()
    ttl = settings.CACHE_TTL_RATIOS
    cache_key = f"fmp:income:{symbol.upper()}:{limit}"

    def loader():
        client = _get_fmp()
        if client is not None and hasattr(client, "income_statement"):
            data = client.income_statement(symbol, limit=limit)
            return data or []
        data = _http_get_json(f"income-statement/{symbol}", {"limit": limit})
        return data or []

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
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
    settings = _get_settings()
    ttl = settings.CACHE_TTL_RATIOS
    cache_key = f"fmp:balance:{symbol.upper()}:{limit}"

    def loader():
        client = _get_fmp()
        if client is not None and hasattr(client, "balance_sheet_statement"):
            data = client.balance_sheet_statement(symbol, limit=limit)
            return data or []
        data = _http_get_json(f"balance-sheet-statement/{symbol}", {"limit": limit})
        return data or []

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
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
    settings = _get_settings()
    ttl = settings.CACHE_TTL_RATIOS
    cache_key = f"fmp:cashflow:{symbol.upper()}:{limit}"

    def loader():
        client = _get_fmp()
        if client is not None and hasattr(client, "cash_flow_statement"):
            data = client.cash_flow_statement(symbol, limit=limit)
            return data or []
        data = _http_get_json(f"cash-flow-statement/{symbol}", {"limit": limit})
        return data or []

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
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
    settings = _get_settings()
    ttl = settings.CACHE_TTL_INTRADAY
    cache_key = f"fmp:quote:{symbol.upper()}"

    def loader():
        client = _get_fmp()
        if client is not None and hasattr(client, "quote"):
            data = client.quote(symbol)
            if isinstance(data, list):
                return data[0] if data else None
            return data
        data = _http_get_json(f"quote/{symbol}")
        if isinstance(data, list):
            return data[0] if data else None
        return data

    try:
        return _cached_call(cache_key, ttl, loader)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting quote for {symbol}: {e}")
        return None


def search_symbols(query: str) -> List[Dict[str, Any]]:
    """
    Search for symbols by company name or symbol using the stable FMP endpoint.
    
    Args:
        query: Search query
        
    Returns:
        List of matching symbols
    """
    settings = _get_settings()
    ttl = 24 * 60 * 60  # search can be cached longer
    cache_key = f"fmp:search:{_sanitize_cache_key(query.strip().lower())}"

    def loader():
        # Use the stable endpoint for symbol search
        data = _http_get_json("search-symbol", {"query": query}, use_stable=True)
        return data or []

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error searching symbols for {query}: {e}")
        return []


def unified_search(query: str, limit: int = 50) -> List[Dict[str, Any]]:
    """
    Unified search across all asset types using both FMP search-symbol and search-name endpoints.
    This provides comprehensive coverage for both symbol and company name searches.
    
    Args:
        query: Search query
        limit: Maximum number of results to return
        
    Returns:
        List of matching instruments with categorized asset types
    """
    settings = _get_settings()
    ttl = 24 * 60 * 60  # Cache for 24 hours
    cache_key = f"fmp:unified_search:{_sanitize_cache_key(query.strip().lower())}"

    def loader():
        all_results = []
        
        # 1. Search by symbol (for exact symbol matches and symbol-like queries)
        try:
            symbol_data = _http_get_json("search-symbol", {"query": query}, use_stable=True)
            if symbol_data:
                for result in symbol_data:
                    enhanced_result = _categorize_search_result(result)
                    if enhanced_result:
                        all_results.append(enhanced_result)
        except Exception as e:
            logger.warning(f"Error in symbol search for {query}: {e}")
        
        # 2. Search by company name (for company name searches)
        try:
            name_data = _http_get_json("search-name", {"query": query}, use_stable=True)
            if name_data:
                for result in name_data:
                    enhanced_result = _categorize_search_result(result)
                    if enhanced_result:
                        # Check for duplicates (same symbol)
                        if not any(r.get('symbol') == enhanced_result.get('symbol') for r in all_results):
                            all_results.append(enhanced_result)
        except Exception as e:
            logger.warning(f"Error in name search for {query}: {e}")
        
        # Sort by score and limit results
        all_results.sort(key=lambda x: x.get('score', 0), reverse=True)
        return all_results[:limit]

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error in unified search for {query}: {e}")
        return []


def _categorize_search_result(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Categorize a search result and determine its asset type.
    
    Args:
        result: Raw search result from FMP
        
    Returns:
        Enhanced result with asset type categorization, or None if invalid
    """
    if not isinstance(result, dict):
        return None
    
    symbol = result.get('symbol', '').upper()
    name = result.get('name', '').upper()
    exchange = result.get('exchange', '').upper()
    
    # Determine asset type based on exchange, symbol patterns, and name
    asset_type = 'stock'  # Default
    
    if 'ETF' in name or 'ETF' in exchange or 'EXCHANGE TRADED FUND' in name:
        asset_type = 'etf'
    elif 'CRYPTO' in exchange or symbol.endswith('USD') or symbol.endswith('BTC') or 'BITCOIN' in name:
        asset_type = 'cryptocurrency'
    elif '/' in symbol or 'FOREX' in exchange or 'FX' in exchange:
        asset_type = 'forex'
    elif 'GOLD' in name or 'SILVER' in name or 'OIL' in name or 'COMMODITY' in exchange:
        asset_type = 'commodity'
    elif exchange in ['NASDAQ', 'NYSE', 'AMEX', 'LSE', 'XETRA', 'NEO', 'MEX', 'BSE', 'TSX']:
        asset_type = 'stock'
    elif exchange in ['OTC', 'PINK']:
        asset_type = 'stock'  # Treat OTC as stocks
    
    # Enhance the result with additional metadata
    enhanced_result = result.copy()
    enhanced_result['type'] = asset_type
    enhanced_result['score'] = _calculate_search_score(result, asset_type)
    
    return enhanced_result


def _calculate_search_score(result: Dict[str, Any], asset_type: str) -> int:
    """
    Calculate a relevance score for search results.
    
    Args:
        result: Search result
        asset_type: Determined asset type
        
    Returns:
        Relevance score (higher is better)
    """
    symbol = result.get('symbol', '').upper()
    name = result.get('name', '').upper()
    exchange = result.get('exchange', '').upper()
    
    score = 50  # Base score
    
    # Boost for major exchanges
    if exchange in ['NASDAQ', 'NYSE', 'AMEX']:
        score += 30
    elif exchange in ['LSE', 'XETRA']:
        score += 20
    elif exchange in ['OTC', 'PINK']:
        score -= 10
    
    # Boost for ETFs and major asset types
    if asset_type == 'etf':
        score += 10
    elif asset_type == 'cryptocurrency':
        score += 5
    elif asset_type == 'forex':
        score += 5
    
    # Boost for well-known companies (common symbols)
    well_known_symbols = ['AAPL', 'MSFT', 'GOOGL', 'AMZN', 'TSLA', 'META', 'NVDA', 'BRK.A', 'BRK.B']
    if symbol in well_known_symbols:
        score += 20
    
    # Boost for major company names in the result name
    major_companies = ['APPLE', 'MICROSOFT', 'GOOGLE', 'AMAZON', 'TESLA', 'FACEBOOK', 'NVIDIA', 'BERKSHIRE']
    for company in major_companies:
        if company in name:
            score += 15
            break
    
    return min(score, 100)  # Cap at 100


def search_by_company_name(query: str) -> List[Dict[str, Any]]:
    """
    Search for symbols by company name using the stable FMP search-name endpoint.
    
    Args:
        query: Company name search query
        
    Returns:
        List of matching symbols
    """
    settings = _get_settings()
    ttl = 24 * 60 * 60  # search can be cached longer
    cache_key = f"fmp:search_name:{_sanitize_cache_key(query.strip().lower())}"

    def loader():
        # Use the stable endpoint for company name search
        data = _http_get_json("search-name", {"query": query}, use_stable=True)
        return data or []

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error searching by company name {query}: {e}")
        return []


def search_by_isin(isin: str) -> List[Dict[str, Any]]:
    """
    Search for symbols by ISIN (International Securities Identification Number) using the stable FMP endpoint.
    
    Args:
        isin: ISIN code (e.g., US0378331005)
        
    Returns:
        List of matching symbols with ISIN data
    """
    settings = _get_settings()
    ttl = 24 * 60 * 60  # search can be cached longer
    cache_key = f"fmp:search_isin:{_sanitize_cache_key(isin.strip().upper())}"

    def loader():
        # Use the stable endpoint for ISIN search
        data = _http_get_json("search-isin", {"isin": isin}, use_stable=True)
        return data or []

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error searching by ISIN {isin}: {e}")
        return []


def get_market_cap(symbol: str) -> Optional[float]:
    """
    Get market capitalization for a symbol.
    
    Args:
        symbol: Stock symbol
        
    Returns:
        Market cap value or None if error
    """
    settings = _get_settings()
    ttl = settings.CACHE_TTL_EOD
    cache_key = f"fmp:marketcap:{symbol.upper()}"

    def loader():
        # Client may not expose; fallback to HTTP
        data = _http_get_json(f"market-capitalization/{symbol}")
        if isinstance(data, list) and data:
            return data[0].get("marketCap")
        if isinstance(data, dict):
            return data.get("marketCap")
        return None

    try:
        return _cached_call(cache_key, ttl, loader)
    except Exception as e:  # noqa: BLE001
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
    settings = _get_settings()
    ttl = settings.CACHE_TTL_EOD
    cache_key = f"fmp:dividends:{symbol.upper()}"

    def loader():
        # HTTP fallback because client method may not exist
        data = _http_get_json(f"historical-price-full/stock_dividend/{symbol}")
        return data or []

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting dividend history for {symbol}: {e}")
        return []


def get_stock_splits(symbol: str) -> List[Dict[str, Any]]:
    """
    Get stock split history for a symbol.
    Endpoint: /api/v3/historical-price-full/stock_split/{symbol}
    """
    settings = _get_settings()
    ttl = settings.CACHE_TTL_EOD
    cache_key = f"fmp:splits:{symbol.upper()}"

    def loader():
        data = _http_get_json(f"historical-price-full/stock_split/{symbol}")
        # API can respond with { symbol, historical: [...] } or list
        if isinstance(data, dict) and "historical" in data:
            return data.get("historical", [])
        if isinstance(data, list):
            return data
        return []

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting stock splits for {symbol}: {e}")
        return []


def get_earnings_calendar(symbol: str) -> List[Dict[str, Any]]:
    """
    Get earnings calendar for a symbol.
    
    Args:
        symbol: Stock symbol
        
    Returns:
        List of earnings dates
    """
    settings = _get_settings()
    ttl = settings.CACHE_TTL_EOD
    cache_key = f"fmp:earnings_cal:{symbol.upper()}"

    def loader():
        data = _http_get_json("earning_calendar", {"symbol": symbol})
        return data or []

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting earnings calendar for {symbol}: {e}")
        return []


# Additional endpoints required by the app

def get_peers(symbol: str) -> List[str]:
    """Return peer symbols for a given symbol (for Compare auto-populate)."""
    settings = _get_settings()
    ttl = 24 * 60 * 60
    cache_key = f"fmp:peers:{symbol.upper()}"

    def loader():
        data = _http_get_json(f"stock/peers", {"symbol": symbol})
        if isinstance(data, dict) and "peersList" in data:
            return data.get("peersList", [])
        if isinstance(data, list):
            # sometimes returns list of symbols
            return data
        return []

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting peers for {symbol}: {e}")
        return []


def get_dcf_premium_discount(symbol: str) -> Optional[float]:
    """Return premium/discount percentage vs market from DCF endpoint."""
    settings = _get_settings()
    ttl = settings.CACHE_TTL_RATIOS
    cache_key = f"fmp:dcf:{symbol.upper()}"

    def loader():
        data = _http_get_json(f"discounted-cash-flow/{symbol}")
        # DCF endpoint may return { 'symbol': 'AAPL', 'dcf': 155, 'Stock Price': 170 }
        if isinstance(data, list) and data:
            item = data[0]
        elif isinstance(data, dict):
            item = data
        else:
            return None
        try:
            dcf = float(item.get("dcf"))
            price = float(item.get("Stock Price") or item.get("price") or 0)
            if price > 0:
                return (dcf - price) / price
        except Exception:  # noqa: BLE001
            return None
        return None

    try:
        return _cached_call(cache_key, ttl, loader)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting DCF premium/discount for {symbol}: {e}")
        return None


def get_etf_holdings(symbol: str) -> Dict[str, Any]:
    """Top-10 holdings + sector/country weights and summary metrics for ETF."""
    settings = _get_settings()
    ttl = settings.CACHE_TTL_EOD
    cache_key = f"fmp:etf:{symbol.upper()}:holdings"

    def loader():
        top10 = _http_get_json(f"etf/holdings/{symbol}") or []
        sector_weights = _http_get_json(f"etf-sector-weightings/{symbol}") or []
        country_weights = _http_get_json(f"etf-country-weightings/{symbol}") or []
        summary_list = _http_get_json(f"profile/{symbol}") or []
        summary = summary_list[0] if isinstance(summary_list, list) and summary_list else {}
        return {
            "top10": top10[:10] if isinstance(top10, list) else [],
            "sector_weights": sector_weights,
            "country_weights": country_weights,
            "summary": {
                "expense_ratio": summary.get("expenseRatio"),
                "dividend_yield": summary.get("lastDiv"),
            },
        }

    try:
        return _cached_call(cache_key, ttl, loader) or {"top10": [], "sector_weights": [], "country_weights": [], "summary": {}}
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting ETF holdings for {symbol}: {e}")
        return {"top10": [], "sector_weights": [], "country_weights": [], "summary": {}}


def get_risk_free_yield(tenor: str = "3m") -> Optional[float]:
    """Fetch latest UST yield for tenor in {3m, 6m, 2y}. Returns annual decimal."""
    tenor_map = {"3m": "3month", "6m": "6month", "2y": "2year", "1y": "1year"}
    period = tenor_map.get(tenor.lower(), "3month")
    try:
        # v4 treasury endpoint
        data = requests.get(
            "https://financialmodelingprep.com/api/v4/treasury",
            params={"apikey": _get_api_key(), "period": period, "from": (date.today().replace(year=date.today().year - 1)).isoformat(), "to": date.today().isoformat()},
            timeout=8,
        ).json()
        if isinstance(data, list) and data:
            # take last non-null
            for row in reversed(data):
                try:
                    v = float(row.get("value"))
                    return v / 100.0
                except Exception:  # noqa: BLE001
                    continue
    except Exception as e:  # noqa: BLE001
        logger.warning(f"Risk-free yield fetch failed, falling back to DEFAULT_RF: {e}")
    settings = _get_settings()
    return getattr(settings, "DEFAULT_RF", 0.03)


# ----------------------------- New helper fetchers -----------------------------

def get_analyst_estimates(symbol: str) -> List[Dict[str, Any]]:
    """
    v4 analyst estimates: https://financialmodelingprep.com/api/v4/analyst-estimates?symbol={symbol}
    Cached for EOD horizon.
    """
    settings = _get_settings()
    ttl = settings.CACHE_TTL_EOD
    cache_key = f"fmp:v4:analyst_estimates:{symbol.upper()}"

    def loader():
        data = _http_get_json("analyst-estimates", {"symbol": symbol}, use_stable=False)
        return data or []

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting analyst estimates for {symbol}: {e}")
        return []


def get_price_targets(symbol: str) -> Dict[str, Any]:
    """
    v4 price target summary: https://financialmodelingprep.com/api/v4/price-target-summary?symbol={symbol}
    Cached for EOD horizon. Returns a compact dict.
    """
    settings = _get_settings()
    ttl = settings.CACHE_TTL_EOD
    cache_key = f"fmp:v4:price_targets:{symbol.upper()}"

    def loader():
        data = _http_get_json("price-target-summary", {"symbol": symbol}, use_stable=False)
        if isinstance(data, list) and data:
            item = data[0]
        elif isinstance(data, dict):
            item = data
        else:
            return {}
        return {
            "symbol": item.get("symbol", symbol),
            "targetLow": item.get("targetLow"),
            "targetHigh": item.get("targetHigh"),
            "targetMean": item.get("targetMean"),
            "targetMedian": item.get("targetMedian"),
            "numberAnalystOpinions": item.get("numberAnalystOpinions"),
            "lastUpdated": item.get("lastUpdated"),
        }

    try:
        return _cached_call(cache_key, ttl, loader) or {}
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting price targets for {symbol}: {e}")
        return {}


def get_company_rating(symbol: str) -> Dict[str, Any]:
    """
    v3 company rating: https://financialmodelingprep.com/api/v3/rating/{symbol}
    Cached for EOD horizon.
    """
    settings = _get_settings()
    ttl = settings.CACHE_TTL_EOD
    cache_key = f"fmp:v3:rating:{symbol.upper()}"

    def loader():
        data = _http_get_json(f"rating/{symbol}")
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
        return {}

    try:
        return _cached_call(cache_key, ttl, loader) or {}
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting rating for {symbol}: {e}")
        return {}


def get_market_risk_premium(country: str = "US") -> Optional[float]:
    """
    v4 market risk premium by country: https://financialmodelingprep.com/api/v4/market-risk-premium
    Returns premium for given country code when available; cached for EOD horizon.
    """
    settings = _get_settings()
    ttl = settings.CACHE_TTL_EOD
    cache_key = f"fmp:v4:mrp:{country.upper()}"

    def loader():
        data = _http_get_json("market-risk-premium", use_stable=False)
        if isinstance(data, list):
            for row in data:
                try:
                    if isinstance(row, dict) and row.get("country") and row.get("country").upper() == country.upper():
                        val = row.get("marketRiskPremium") or row.get("value")
                        return float(val) if val is not None else None
                except Exception:
                    continue
        return None

    try:
        return _cached_call(cache_key, ttl, loader)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting market risk premium for {country}: {e}")
        return None


def get_stock_news(symbol: str, limit: int = 10) -> List[Dict[str, Any]]:
    """
    v3 stock news: https://financialmodelingprep.com/api/v3/stock_news?tickers={symbol}&limit=10
    Cached briefly (intraday) since news changes more often.
    """
    settings = _get_settings()
    ttl = settings.CACHE_TTL_INTRADAY
    cache_key = f"fmp:v3:stock_news:{symbol.upper()}:{limit}"

    def loader():
        data = _http_get_json("stock_news", {"tickers": symbol, "limit": limit})
        if isinstance(data, list):
            # keep compact list
            out: List[Dict[str, Any]] = []
            for item in data[:limit]:
                if not isinstance(item, dict):
                    continue
                out.append({
                    "symbol": item.get("symbol", symbol),
                    "title": item.get("title"),
                    "text": item.get("text"),
                    "site": item.get("site"),
                    "url": item.get("url"),
                    "image": item.get("image"),
                    "publishedDate": item.get("publishedDate"),
                })
            return out
        return []

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting stock news for {symbol}: {e}")
        return []


def quote_short(symbols: List[str]) -> List[Dict[str, Any]]:
    """Lightweight quotes for lists of symbols."""
    try:
        data = _http_get_json("quote-short/{}".format(",".join(symbols)))
        return data or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting quote_short for {symbols}: {e}")
        return []


def available_exchanges() -> List[str]:
    try:
        data = _http_get_json("available-exchanges")
        if isinstance(data, list):
            return [d.get("exchangeShortName") or d.get("name") for d in data if isinstance(d, dict)]
        return []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting available exchanges: {e}")
        return []


def index_list() -> List[Dict[str, Any]]:
    try:
        data = _http_get_json("quotes/index")
        return data or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting index list: {e}")
        return []


def get_index_price_history(symbol: str, days: int = 365) -> List[Dict[str, Any]]:
    """
    Get historical price data for indexes using the stable light endpoint.
    Uses endpoint: stable/historical-price-eod/light?symbol={symbol}&from=YYYY-MM-DD&to=YYYY-MM-DD
    """
    settings = _get_settings()
    ttl = settings.CACHE_TTL_EOD
    cache_key = f"fmp:index_history:{symbol.upper()}:{days}"

    def loader():
        from datetime import date, timedelta
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        try:
            data = _http_get_json(
                "historical-price-eod/light",
                {
                    "symbol": symbol,
                    "from": start_date.isoformat(),
                    "to": end_date.isoformat(),
                },
                use_stable=True,
            )
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "historical" in data:
                return data["historical"]
            return []
        except Exception as e:  # noqa: BLE001
            logger.warning(f"Error fetching index history for {symbol}: {e}")
            return []

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting index price history for {symbol}: {e}")
        return []


def get_index_quote(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Get index quote; fallback to latest point from historical light endpoint.
    """
    settings = _get_settings()
    ttl = settings.CACHE_TTL_INTRADAY
    cache_key = f"fmp:index_quote:{symbol.upper()}"

    def loader():
        # Try generic quote endpoint first
        data = _http_get_json("quote", {"symbol": symbol})
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict) and data:
            return data
        # Fallback to history
        hist = get_index_price_history(symbol, days=1)
        if hist:
            latest = hist[0]
            return {
                "symbol": symbol,
                "name": latest.get("name", symbol),
                "price": latest.get("close") or latest.get("adjClose") or latest.get("price"),
                "change": latest.get("change"),
                "changePercentage": latest.get("changePercentage"),
                "dayLow": latest.get("dayLow"),
                "dayHigh": latest.get("dayHigh"),
                "volume": latest.get("volume"),
                "exchange": "INDEX",
                "currency": latest.get("currency") or "USD",
                "type": "index",
            }
        return None

    try:
        return _cached_call(cache_key, ttl, loader)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting index quote for {symbol}: {e}")
        return None


def get_actively_trading_list() -> List[Dict[str, Any]]:
    """
    Get actively trading list from FMP stable endpoint.
    
    Returns:
        List of actively trading securities
    """
    settings = _get_settings()
    ttl = 5 * 60  # Cache for 5 minutes since this is real-time data
    cache_key = "fmp:actively_trading"

    def loader():
        # Use the stable endpoint for actively trading list
        data = _http_get_json("actively-trading-list", use_stable=True)
        return data or []

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting actively trading list: {e}")
        return []


def get_most_searched_stocks(min_market_cap: float = 0) -> List[Dict[str, Any]]:
    """
    Get most searched stocks list from FMP API with enhanced data.
    Uses multiple endpoints to get comprehensive stock information.
    
    Args:
        min_market_cap: Minimum market cap filter in USD (default: 0)
    
    Returns:
        List of most searched/popular stocks with enhanced data
    """
    settings = _get_settings()
    ttl = 15 * 60  # Cache for 15 minutes since this includes real-time data
    cache_key = f"fmp:most_searched_stocks:{min_market_cap}"

    def loader():
        # Get stock list from FMP API
        stock_list = _http_get_json("stock/list")
        if not isinstance(stock_list, list):
            return []
        
        # Filter for stocks only (exclude ETFs, trusts, etc.)
        stocks = [item for item in stock_list if item.get('type') == 'stock']
        
        # Get symbols for batch quote requests
        symbols = [stock['symbol'] for stock in stocks[:100]]  # Limit to 100 for API efficiency
        
        # Get enhanced data for stocks
        enhanced_stocks = []
        
        # Get quotes for price and change data
        if symbols:
            try:
                # Batch quote request
                quotes_data = _http_get_json("quote-short", {"symbol": ",".join(symbols)})
                quotes_dict = {}
                if isinstance(quotes_data, list):
                    quotes_dict = {quote.get('symbol'): quote for quote in quotes_data}
                
                # Get market cap data
                market_cap_data = _http_get_json("market-capitalization", {"symbol": ",".join(symbols)})
                market_cap_dict = {}
                if isinstance(market_cap_data, list):
                    market_cap_dict = {mc.get('symbol'): mc for mc in market_cap_data}
                
                # Combine data
                for stock in stocks:
                    symbol = stock.get('symbol')
                    quote = quotes_dict.get(symbol, {})
                    market_cap_info = market_cap_dict.get(symbol, {})
                    
                    # Calculate market cap
                    market_cap = market_cap_info.get('marketCap')
                    if not market_cap and quote.get('price') and quote.get('sharesOutstanding'):
                        try:
                            market_cap = float(quote['price']) * float(quote['sharesOutstanding'])
                        except (ValueError, TypeError):
                            market_cap = None
                    
                    # Apply market cap filter
                    if min_market_cap > 0 and (not market_cap or market_cap < min_market_cap):
                        continue
                    
                    # Determine currency based on exchange
                    currency = _get_currency_for_exchange(stock.get('exchangeShortName', stock.get('exchange', '')))
                    
                    enhanced_stock = {
                        'symbol': symbol,
                        'name': stock.get('name', ''),
                        'price': quote.get('price'),
                        'change': quote.get('change'),
                        'changePercentage': quote.get('changePercentage'),
                        'marketCap': market_cap,
                        'exchange': stock.get('exchangeShortName', stock.get('exchange', '')),
                        'type': stock.get('type', 'stock'),
                        'currency': currency,
                        'volume': quote.get('volume'),
                        'dayLow': quote.get('dayLow'),
                        'dayHigh': quote.get('dayHigh'),
                    }
                    enhanced_stocks.append(enhanced_stock)
                    
            except Exception as e:
                logger.warning(f"Error getting enhanced data: {e}")
                # Fallback to basic data
                for stock in stocks:
                    currency = _get_currency_for_exchange(stock.get('exchangeShortName', stock.get('exchange', '')))
                    enhanced_stock = {
                        'symbol': stock.get('symbol'),
                        'name': stock.get('name', ''),
                        'price': stock.get('price'),
                        'change': None,
                        'changePercentage': None,
                        'marketCap': None,
                        'exchange': stock.get('exchangeShortName', stock.get('exchange', '')),
                        'type': stock.get('type', 'stock'),
                        'currency': currency,
                        'volume': None,
                        'dayLow': None,
                        'dayHigh': None,
                    }
                    enhanced_stocks.append(enhanced_stock)
        
        # Sort by market cap descending, then by exchange priority
        def sort_key(item):
            market_cap = item.get('marketCap', 0) or 0
            exchange = (item.get('exchange') or '').upper()
            
            # Priority order for exchanges
            exchange_priority = {
                'NASDAQ': 1,
                'NYSE': 2,
                'AMEX': 3,
                'LSE': 4,
                'XETRA': 5,
                'TSX': 6,
                'ASX': 7,
                'NZE': 8,
                'MCX': 9,
            }
            
            priority = exchange_priority.get(exchange, 99)
            return (-market_cap, priority)  # Negative for descending order
        
        enhanced_stocks.sort(key=sort_key)
        return enhanced_stocks[:50]  # Return top 50 stocks

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting most searched stocks: {e}")
        # Return a fallback list of popular stocks if API fails
        return [
            {"symbol": "AAPL", "name": "Apple Inc.", "price": 150.0, "exchange": "NASDAQ", "type": "stock", "currency": "USD", "marketCap": 2500000000000, "changePercentage": 1.5},
            {"symbol": "MSFT", "name": "Microsoft Corporation", "price": 300.0, "exchange": "NASDAQ", "type": "stock", "currency": "USD", "marketCap": 2200000000000, "changePercentage": -0.8},
            {"symbol": "GOOGL", "name": "Alphabet Inc.", "price": 2500.0, "exchange": "NASDAQ", "type": "stock", "currency": "USD", "marketCap": 1800000000000, "changePercentage": 2.1},
            {"symbol": "AMZN", "name": "Amazon.com Inc.", "price": 3000.0, "exchange": "NASDAQ", "type": "stock", "currency": "USD", "marketCap": 1500000000000, "changePercentage": 0.5},
            {"symbol": "TSLA", "name": "Tesla Inc.", "price": 200.0, "exchange": "NASDAQ", "type": "stock", "currency": "USD", "marketCap": 600000000000, "changePercentage": -2.3},
            {"symbol": "META", "name": "Meta Platforms Inc.", "price": 350.0, "exchange": "NASDAQ", "type": "stock", "currency": "USD", "marketCap": 850000000000, "changePercentage": 1.2},
            {"symbol": "NVDA", "name": "NVIDIA Corporation", "price": 450.0, "exchange": "NASDAQ", "type": "stock", "currency": "USD", "marketCap": 1100000000000, "changePercentage": 3.5},
            {"symbol": "BRK.A", "name": "Berkshire Hathaway Inc.", "price": 540000.0, "exchange": "NYSE", "type": "stock", "currency": "USD", "marketCap": 780000000000, "changePercentage": 0.3},
            {"symbol": "BRK.B", "name": "Berkshire Hathaway Inc.", "price": 360.0, "exchange": "NYSE", "type": "stock", "currency": "USD", "marketCap": 780000000000, "changePercentage": 0.3},
            {"symbol": "V", "name": "Visa Inc.", "price": 250.0, "exchange": "NYSE", "type": "stock", "currency": "USD", "marketCap": 520000000000, "changePercentage": -0.5},
            {"symbol": "JPM", "name": "JPMorgan Chase & Co.", "price": 180.0, "exchange": "NYSE", "type": "stock", "currency": "USD", "marketCap": 530000000000, "changePercentage": 0.8},
            {"symbol": "JNJ", "name": "Johnson & Johnson", "price": 160.0, "exchange": "NYSE", "type": "stock", "currency": "USD", "marketCap": 420000000000, "changePercentage": -0.2},
            {"symbol": "WMT", "name": "Walmart Inc.", "price": 170.0, "exchange": "NYSE", "type": "stock", "currency": "USD", "marketCap": 550000000000, "changePercentage": 0.4},
            {"symbol": "PG", "name": "Procter & Gamble Co.", "price": 155.0, "exchange": "NYSE", "type": "stock", "currency": "USD", "marketCap": 365000000000, "changePercentage": 0.1},
            {"symbol": "UNH", "name": "UnitedHealth Group Inc.", "price": 520.0, "exchange": "NYSE", "type": "stock", "currency": "USD", "marketCap": 490000000000, "changePercentage": 1.8},
            {"symbol": "HD", "name": "Home Depot Inc.", "price": 380.0, "exchange": "NYSE", "type": "stock", "currency": "USD", "marketCap": 380000000000, "changePercentage": -0.7},
            {"symbol": "MA", "name": "Mastercard Inc.", "price": 420.0, "exchange": "NYSE", "type": "stock", "currency": "USD", "marketCap": 400000000000, "changePercentage": 0.9},
            {"symbol": "BAC", "name": "Bank of America Corp.", "price": 35.0, "exchange": "NYSE", "type": "stock", "currency": "USD", "marketCap": 270000000000, "changePercentage": 1.1},
            {"symbol": "ABBV", "name": "AbbVie Inc.", "price": 165.0, "exchange": "NYSE", "type": "stock", "currency": "USD", "marketCap": 290000000000, "changePercentage": -0.3},
            {"symbol": "PFE", "name": "Pfizer Inc.", "price": 28.0, "exchange": "NYSE", "type": "stock", "currency": "USD", "marketCap": 160000000000, "changePercentage": 0.6},
        ]


def _get_currency_for_exchange(exchange: str) -> str:
    """
    Determine currency based on exchange.
    
    Args:
        exchange: Exchange short name
        
    Returns:
        Currency code
    """
    if not exchange:
        return 'USD'
    
    exchange_currency_map = {
        'NASDAQ': 'USD',
        'NYSE': 'USD',
        'AMEX': 'USD',
        'LSE': 'GBP',
        'XETRA': 'EUR',
        'TSX': 'CAD',
        'ASX': 'AUD',
        'NZE': 'NZD',
        'MCX': 'RUB',
        'KSC': 'KRW',
        'KOE': 'KRW',
        'BSE': 'INR',
        'NSE': 'INR',
        'TSE': 'JPY',
        'HKSE': 'HKD',
        'SSE': 'CNY',
        'SZSE': 'CNY',
    }
    
    return exchange_currency_map.get(exchange.upper() if exchange else '', 'USD')


def search_etfs(query: str) -> List[Dict[str, Any]]:
    """
    Search for ETFs by symbol or name using the FMP ETF list endpoint.
    
    Args:
        query: Search query for ETF symbol or name
        
    Returns:
        List of matching ETFs
    """
    settings = _get_settings()
    ttl = 24 * 60 * 60  # Cache for 24 hours since ETF list doesn't change frequently
    cache_key = f"fmp:etf_search:{_sanitize_cache_key(query.strip().lower())}"

    def loader():
        # Get all ETFs from the stable endpoint
        all_etfs = _http_get_json("etf-list", use_stable=True)
        if not all_etfs:
            return []
        
        # Filter ETFs based on query
        query_lower = query.strip().lower()
        matching_etfs = []
        
        for etf in all_etfs:
            if isinstance(etf, dict):
                symbol = etf.get('symbol', '').lower()
                name = etf.get('name', '').lower()
                
                # Check if query matches symbol or name
                if query_lower in symbol or query_lower in name:
                    matching_etfs.append(etf)
        
        # Sort by relevance (exact symbol matches first, then name matches)
        def sort_key(etf):
            symbol = etf.get('symbol', '').lower()
            name = etf.get('name', '').lower()
            
            # Exact symbol match gets highest priority
            if symbol == query_lower:
                return (0, symbol)
            # Symbol starts with query gets second priority
            elif symbol.startswith(query_lower):
                return (1, symbol)
            # Name starts with query gets third priority
            elif name.startswith(query_lower):
                return (2, name)
            # Other matches
            else:
                return (3, symbol)
        
        matching_etfs.sort(key=sort_key)
        return matching_etfs[:50]  # Limit to 50 results

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error searching ETFs for {query}: {e}")
        return []


def get_commodities_quote(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Get commodities quote using FMP Commodities Quick Quote API.
    
    Args:
        symbol: Commodity symbol (e.g., GCUSD for Gold)
        
    Returns:
        Commodity quote data or None if error
    """
    settings = _get_settings()
    ttl = settings.CACHE_TTL_INTRADAY  # Use intraday cache since commodities are real-time
    cache_key = f"fmp:commodities:{symbol.upper()}"

    def loader():
        # Use the stable endpoint for commodities quote-short
        data = _http_get_json("quote-short", {"symbol": symbol}, use_stable=True)
        if isinstance(data, list):
            return data[0] if data else None
        return data

    try:
        result = _cached_call(cache_key, ttl, loader)
        return result
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting commodities quote for {symbol}: {e}")
        return None


def search_commodities(query: str = "") -> List[Dict[str, Any]]:
    """
    Get list of available commodities from FMP.
    
    Args:
        query: Optional filter query for commodity symbols/names
        
    Returns:
        List of available commodities
    """
    settings = _get_settings()
    ttl = 24 * 60 * 60  # Cache for 24 hours since commodity list doesn't change frequently
    cache_key = f"fmp:commodities_list:{query.strip().lower() if query else 'all'}"

    def loader():
        # Get commodities from FMP endpoint
        # Common commodity symbols that work with the API
        symbols = [
            "GCUSD",    # Gold Futures
            "SILUSD",   # Micro Silver Futures
            "SIUSD",    # Silver Futures
            "HGUSD",    # Copper
            "PLUSD",    # Platinum
            "PAUSD",    # Palladium
            "CLUSD",    # Crude Oil
            "BZUSD",    # Brent Crude Oil
            "NGUSD",    # Natural Gas
            "HOUSD",    # Heating Oil
            "RBUSD",    # Gasoline RBOB
            "KCUSX",    # Coffee
            "ZCUSX",    # Corn Futures
            "KEUSX",    # Wheat Futures
            "ZSUSX",    # Soybean Futures
            "CTUSX",    # Cotton
            "SBUSX",    # Sugar
            "OJUSX",    # Orange Juice
            "LEUSX",    # Live Cattle Futures
            "HEUSX",    # Lean Hogs Futures
            "LBUSD",    # Lumber Futures
            "CCUSD",    # Cocoa
            "ALIUSD",   # Aluminum Futures
            "MGCUSD",   # Micro Gold Futures
        ]
        
        commodities = []
        if query:
            query_lower = query.strip().lower()
            # Filter symbols based on query
            filtered_symbols = [s for s in symbols if query_lower in s.lower()]
            if not filtered_symbols:
                # Try to get quotes for some symbols and extract names from API response
                for symbol in symbols[:5]:  # Try first 5 to see response format
                    try:
                        quote = _http_get_json("quote-short", {"symbol": symbol}, use_stable=True)
                        if isinstance(quote, list) and quote:
                            commodities.append({
                                "symbol": symbol,
                                "name": quote[0].get("name", symbol),
                                "price": quote[0].get("price"),
                                "change": quote[0].get("change"),
                                "changePercentage": quote[0].get("changePercentage"),
                            })
                        elif isinstance(quote, dict):
                            commodities.append({
                                "symbol": symbol,
                                "name": quote.get("name", symbol),
                                "price": quote.get("price"),
                                "change": quote.get("change"),
                                "changePercentage": quote.get("changePercentage"),
                            })
                    except Exception:
                        # If API call fails, just add the symbol
                        commodities.append({
                            "symbol": symbol,
                            "name": symbol,
                        })
        else:
            # Return basic symbol list
            commodities = [{"symbol": s, "name": s} for s in symbols]
        
        return commodities[:50]  # Limit to 50 results

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error searching commodities for {query}: {e}")
        return []


def get_commodities_price_history(symbol: str, days: int = 365) -> List[Dict[str, Any]]:
    """
    Get historical price data for commodities using the FMP historical-price-eod/light endpoint.
    Uses the specific endpoint: https://financialmodelingprep.com/stable/historical-price-eod/light?symbol=GCUSD
    
    Args:
        symbol: Commodity symbol (e.g., GCUSD for Gold)
        days: Number of days of historical data to fetch
        
    Returns:
        List of historical price data
    """
    settings = _get_settings()
    ttl = settings.CACHE_TTL_EOD  # Cache for end of day
    cache_key = f"fmp:commodities_history:{symbol.upper()}:{days}"

    def loader():
        # Calculate date range
        from datetime import date, timedelta
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        # Use the historical-price-eod/light endpoint for commodities
        # This uses the stable endpoint: https://financialmodelingprep.com/stable/historical-price-eod/light
        try:
            data = _http_get_json("historical-price-eod/light", {
                "symbol": symbol,
                "from": start_date.isoformat(),
                "to": end_date.isoformat()
            }, use_stable=True)
            
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "historical" in data:
                return data["historical"]
            
            return []
            
        except Exception as e:
            logger.warning(f"Error fetching historical data for {symbol}: {e}")
            return []

    try:
        result = _cached_call(cache_key, ttl, loader)
        return result or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting commodities price history for {symbol}: {e}")
        return []


def get_cryptocurrency_list() -> List[Dict[str, Any]]:
    """
    Get list of available cryptocurrencies from FMP.
    
    Returns:
        List of available cryptocurrencies
    """
    settings = _get_settings()
    ttl = 24 * 60 * 60  # Cache for 24 hours since crypto list doesn't change frequently
    cache_key = "fmp:cryptocurrency_list"

    def loader():
        # Use the stable endpoint for cryptocurrency list
        data = _http_get_json("cryptocurrency-list", use_stable=True)
        return data or []

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting cryptocurrency list: {e}")
        return []


def search_cryptocurrencies(query: str) -> List[Dict[str, Any]]:
    """
    Search for cryptocurrencies by symbol or name.
    
    Args:
        query: Search query for cryptocurrency symbol or name
        
    Returns:
        List of matching cryptocurrencies
    """
    settings = _get_settings()
    ttl = 24 * 60 * 60  # Cache for 24 hours since crypto list doesn't change frequently
    cache_key = f"fmp:crypto_search:{_sanitize_cache_key(query.strip().lower())}"

    def loader():
        # Get all cryptocurrencies from the stable endpoint
        all_cryptos = _http_get_json("cryptocurrency-list", use_stable=True)
        if not all_cryptos:
            return []
        
        # Filter cryptocurrencies based on query
        query_lower = query.strip().lower()
        matching_cryptos = []
        
        for crypto in all_cryptos:
            if isinstance(crypto, dict):
                symbol = crypto.get('symbol', '').lower()
                name = crypto.get('name', '').lower()
                
                # Check if query matches symbol or name
                if query_lower in symbol or query_lower in name:
                    matching_cryptos.append(crypto)
        
        # Sort by relevance (exact symbol matches first, then name matches)
        def sort_key(crypto):
            symbol = crypto.get('symbol', '').lower()
            name = crypto.get('name', '').lower()
            
            # Exact symbol match gets highest priority
            if symbol == query_lower:
                return (0, symbol)
            # Symbol starts with query gets second priority
            elif symbol.startswith(query_lower):
                return (1, symbol)
            # Name starts with query gets third priority
            elif name.startswith(query_lower):
                return (2, name)
            # Other matches
            else:
                return (3, symbol)
        
        matching_cryptos.sort(key=sort_key)
        return matching_cryptos[:50]  # Limit to 50 results

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error searching cryptocurrencies for {query}: {e}")
        return []


def get_cryptocurrency_price_history(symbol: str, days: int = 365) -> List[Dict[str, Any]]:
    """
    Get historical price data for cryptocurrencies using the light endpoint.
    
    Args:
        symbol: Cryptocurrency symbol (e.g., BTCUSD for Bitcoin)
        days: Number of days of historical data to fetch
        
    Returns:
        List of historical price data
    """
    settings = _get_settings()
    ttl = settings.CACHE_TTL_EOD  # Cache for end of day
    cache_key = f"fmp:crypto_history:{symbol.upper()}:{days}"

    def loader():
        # Calculate date range
        from datetime import date, timedelta
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        # Use the historical price EOD light endpoint for cryptocurrencies
        try:
            data = _http_get_json(f"historical-price-eod/light", {
                "symbol": symbol,
                "from": start_date.isoformat(),
                "to": end_date.isoformat()
            }, use_stable=True)
            
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "historical" in data:
                return data["historical"]
            
            return []
            
        except Exception as e:
            logger.warning(f"Error fetching historical data for {symbol}: {e}")
            return []

    try:
        result = _cached_call(cache_key, ttl, loader)
        return result or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting cryptocurrency price history for {symbol}: {e}")
        return []


def get_cryptocurrency_quote(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Get cryptocurrency quote using FMP historical price endpoint (latest price).
    
    Args:
        symbol: Cryptocurrency symbol (e.g., BTCUSD for Bitcoin)
        
    Returns:
        Cryptocurrency quote data or None if error
    """
    settings = _get_settings()
    ttl = settings.CACHE_TTL_INTRADAY  # Use intraday cache since crypto quotes are real-time
    cache_key = f"fmp:crypto_quote:{symbol.upper()}"

    def loader():
        # Try the quote endpoint first
        data = _http_get_json("quote", {"symbol": symbol})
        if isinstance(data, list) and data:
            return data[0]
        elif isinstance(data, dict) and data:
            return data
        
        # If quote endpoint doesn't work, get latest price from historical data
        try:
            history_data = get_cryptocurrency_price_history(symbol, days=1)
            if history_data and len(history_data) > 0:
                latest = history_data[0]  # Most recent price
                return {
                    'symbol': symbol,
                    'name': latest.get('name', symbol),
                    'price': latest.get('price'),
                    'change': latest.get('change'),
                    'changePercentage': latest.get('changePercentage'),
                    'dayLow': latest.get('dayLow'),
                    'dayHigh': latest.get('dayHigh'),
                    'volume': latest.get('volume'),
                    'marketCap': latest.get('marketCap'),
                    'exchange': 'CCC',  # Cryptocurrency exchange
                    'currency': 'USD'
                }
        except Exception:
            pass
        
        return None

    try:
        result = _cached_call(cache_key, ttl, loader)
        return result
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting cryptocurrency quote for {symbol}: {e}")
        return None


def get_forex_list() -> List[Dict[str, Any]]:
    """
    Get list of available forex currency pairs from FMP API.
    
    Returns:
        List of available forex currency pairs
    """
    settings = _get_settings()
    ttl = 24 * 60 * 60  # Cache for 24 hours since forex list doesn't change frequently
    cache_key = "fmp:forex_list"

    def loader():
        # Use the FMP stable forex-list endpoint
        data = _http_get_json("forex-list", use_stable=True)
        if isinstance(data, list) and data:
            forex_pairs = []
            for item in data:
                if isinstance(item, dict):
                    symbol = item.get('symbol', '')
                    from_currency = item.get('fromCurrency', '')
                    to_currency = item.get('toCurrency', '')
                    from_name = item.get('fromName', '')
                    to_name = item.get('toName', '')
                    
                    if symbol and from_currency and to_currency:
                        forex_pairs.append({
                            "symbol": symbol,
                            "name": f"{from_name}/{to_name}" if from_name and to_name else f"{from_currency}/{to_currency}",
                            "base_currency": from_currency,
                            "quote_currency": to_currency,
                            "from_currency": from_currency,
                            "to_currency": to_currency,
                            "from_name": from_name,
                            "to_name": to_name,
                        })
            return forex_pairs
        
        # Fallback to hardcoded list if API fails
        logger.warning("FMP forex-list API failed, using fallback list")
        symbols = [
            "EURUSD",    # Euro / US Dollar
            "GBPUSD",    # British Pound / US Dollar
            "USDJPY",    # US Dollar / Japanese Yen
            "USDCHF",    # US Dollar / Swiss Franc
            "AUDUSD",    # Australian Dollar / US Dollar
            "USDCAD",    # US Dollar / Canadian Dollar
            "NZDUSD",    # New Zealand Dollar / US Dollar
            "EURGBP",    # Euro / British Pound
            "EURJPY",    # Euro / Japanese Yen
            "GBPJPY",    # British Pound / Japanese Yen
            "EURCHF",    # Euro / Swiss Franc
            "GBPCHF",    # British Pound / Swiss Franc
            "AUDCAD",    # Australian Dollar / Canadian Dollar
            "AUDJPY",    # Australian Dollar / Japanese Yen
            "AUDNZD",    # Australian Dollar / New Zealand Dollar
            "CADJPY",    # Canadian Dollar / Japanese Yen
            "CHFJPY",    # Swiss Franc / Japanese Yen
            "EURAUD",    # Euro / Australian Dollar
            "EURCAD",    # Euro / Canadian Dollar
            "EURNZD",    # Euro / New Zealand Dollar
            "GBPAUD",    # British Pound / Australian Dollar
            "GBPCAD",    # British Pound / Canadian Dollar
            "GBPNZD",    # British Pound / New Zealand Dollar
            "NZDCAD",    # New Zealand Dollar / Canadian Dollar
            "NZDJPY",    # New Zealand Dollar / Japanese Yen
            "USDSGD",    # US Dollar / Singapore Dollar
            "USDHKD",    # US Dollar / Hong Kong Dollar
            "USDSEK",    # US Dollar / Swedish Krona
            "USDNOK",    # US Dollar / Norwegian Krone
            "USDDKK",    # US Dollar / Danish Krone
            "USDPLN",    # US Dollar / Polish Zloty
            "USDCZK",    # US Dollar / Czech Koruna
            "USDHUF",    # US Dollar / Hungarian Forint
            "USDRUB",    # US Dollar / Russian Ruble
            "USDCNY",    # US Dollar / Chinese Yuan
            "USDINR",    # US Dollar / Indian Rupee
            "USDKRW",    # US Dollar / South Korean Won
            "USDMXN",    # US Dollar / Mexican Peso
            "USDBRL",    # US Dollar / Brazilian Real
            "USDZAR",    # US Dollar / South African Rand
            "USDTRY",    # US Dollar / Turkish Lira
        ]
        
        forex_pairs = []
        for symbol in symbols:
            # Extract base and quote currencies
            if len(symbol) == 6:
                base_currency = symbol[:3]
                quote_currency = symbol[3:]
                forex_pairs.append({
                    "symbol": symbol,
                    "name": f"{base_currency}/{quote_currency}",
                    "base_currency": base_currency,
                    "quote_currency": quote_currency,
                    "from_currency": base_currency,
                    "to_currency": quote_currency,
                })
        
        return forex_pairs

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting forex list: {e}")
        return []


def search_forex(query: str) -> List[Dict[str, Any]]:
    """
    Search for forex currency pairs by symbol or currency using database.
    
    Args:
        query: Search query for forex symbol or currency
        
    Returns:
        List of matching forex currency pairs
    """
    try:
        from apps.data.models import Forex
        
        # Search in database first
        forex_pairs = Forex.objects.filter(
            Q(symbol__icontains=query) |
            Q(name__icontains=query) |
            Q(from_currency__icontains=query) |
            Q(to_currency__icontains=query) |
            Q(base_currency__icontains=query) |
            Q(quote_currency__icontains=query) |
            Q(from_name__icontains=query) |
            Q(to_name__icontains=query),
            is_active=True
        ).order_by('symbol')[:50]
        
        if forex_pairs.exists():
            results = []
            for pair in forex_pairs:
                results.append({
                    "symbol": pair.symbol,
                    "name": pair.name,
                    "base_currency": pair.base_currency,
                    "quote_currency": pair.quote_currency,
                    "from_currency": pair.from_currency,
                    "to_currency": pair.to_currency,
                    "from_name": pair.from_name,
                    "to_name": pair.to_name,
                    "exchange": pair.exchange,
                    "asset_type": "forex"
                })
            return results
        
        # Fallback to API search if no database results
        logger.info(f"No database results for forex search '{query}', trying API fallback")
        return _search_forex_api_fallback(query)
        
    except Exception as e:
        logger.error(f"Error searching forex in database for {query}: {e}")
        return _search_forex_api_fallback(query)


def _search_forex_api_fallback(query: str) -> List[Dict[str, Any]]:
    """Fallback forex search using API."""
    settings = _get_settings()
    ttl = 24 * 60 * 60  # Cache for 24 hours since forex list doesn't change frequently
    cache_key = f"fmp:forex_search:{_sanitize_cache_key(query.strip().lower())}"

    def loader():
        # Get all forex pairs
        all_forex = get_forex_list()
        if not all_forex:
            return []
        
        # Filter forex pairs based on query
        query_lower = query.strip().lower()
        matching_forex = []
        
        for forex_pair in all_forex:
            if isinstance(forex_pair, dict):
                symbol = forex_pair.get('symbol', '').lower()
                name = forex_pair.get('name', '').lower()
                base_currency = forex_pair.get('base_currency', '').lower()
                quote_currency = forex_pair.get('quote_currency', '').lower()
                
                # Check if query matches symbol, name, or currencies
                if (query_lower in symbol or 
                    query_lower in name or 
                    query_lower in base_currency or 
                    query_lower in quote_currency):
                    forex_pair['asset_type'] = 'forex'
                    matching_forex.append(forex_pair)
        
        # Sort by relevance (exact symbol matches first, then currency matches)
        def sort_key(forex_pair):
            symbol = forex_pair.get('symbol', '').lower()
            base_currency = forex_pair.get('base_currency', '').lower()
            quote_currency = forex_pair.get('quote_currency', '').lower()
            
            # Exact symbol match gets highest priority
            if symbol == query_lower:
                return (0, symbol)
            # Symbol starts with query gets second priority
            elif symbol.startswith(query_lower):
                return (1, symbol)
            # Currency matches
            elif base_currency == query_lower or quote_currency == query_lower:
                return (2, symbol)
            # Other matches
            else:
                return (3, symbol)
        
        matching_forex.sort(key=sort_key)
        return matching_forex[:50]  # Limit to 50 results

    try:
        return _cached_call(cache_key, ttl, loader) or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error searching forex for {query}: {e}")
        return []


def get_forex_price_history(symbol: str, days: int = 365) -> List[Dict[str, Any]]:
    """
    Get historical price data for forex currency pairs using the FMP Historical Forex Light Chart API.
    Uses the specific endpoint: https://financialmodelingprep.com/stable/historical-price-eod/light?symbol=EURUSD
    
    Args:
        symbol: Forex symbol (e.g., EURUSD for Euro/USD)
        days: Number of days of historical data to fetch
        
    Returns:
        List of historical price data
    """
    settings = _get_settings()
    ttl = settings.CACHE_TTL_EOD  # Cache for end of day
    cache_key = f"fmp:forex_history:{symbol.upper()}:{days}"

    def loader():
        # Calculate date range
        from datetime import date, timedelta
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        # Use the historical-price-eod/light endpoint for forex
        # This uses the stable endpoint: https://financialmodelingprep.com/stable/historical-price-eod/light
        try:
            data = _http_get_json("historical-price-eod/light", {
                "symbol": symbol,
                "from": start_date.isoformat(),
                "to": end_date.isoformat()
            }, use_stable=True)
            
            if isinstance(data, list):
                return data
            elif isinstance(data, dict) and "historical" in data:
                return data["historical"]
            
            return []
            
        except Exception as e:
            logger.warning(f"Error fetching forex historical data for {symbol}: {e}")
            return []

    try:
        result = _cached_call(cache_key, ttl, loader)
        return result or []
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting forex price history for {symbol}: {e}")
        return []


def get_forex_quote(symbol: str) -> Optional[Dict[str, Any]]:
    """
    Get forex quote using FMP Historical Forex Light Chart API (latest price).
    
    Args:
        symbol: Forex symbol (e.g., EURUSD for Euro/USD)
        
    Returns:
        Forex quote data or None if error
    """
    settings = _get_settings()
    ttl = settings.CACHE_TTL_INTRADAY  # Use intraday cache since forex quotes are real-time
    cache_key = f"fmp:forex_quote:{symbol.upper()}"

    def loader():
        # Try the quote endpoint first
        data = _http_get_json("quote", {"symbol": symbol})
        if isinstance(data, list) and data:
            return data[0]
        elif isinstance(data, dict) and data:
            return data
        
        # If quote endpoint doesn't work, get latest price from historical data
        try:
            history_data = get_forex_price_history(symbol, days=1)
            if history_data and len(history_data) > 0:
                latest = history_data[0]  # Most recent price
                return {
                    'symbol': symbol,
                    'name': latest.get('name', symbol),
                    'price': latest.get('price'),
                    'change': latest.get('change'),
                    'changePercentage': latest.get('changePercentage'),
                    'dayLow': latest.get('dayLow'),
                    'dayHigh': latest.get('dayHigh'),
                    'volume': latest.get('volume'),
                    'exchange': 'FOREX',  # Forex exchange
                    'currency': 'USD'  # Most forex pairs are quoted against USD
                }
        except Exception:
            pass
        
        return None

    try:
        result = _cached_call(cache_key, ttl, loader)
        return result
    except Exception as e:  # noqa: BLE001
        logger.error(f"Error getting forex quote for {symbol}: {e}")
        return None