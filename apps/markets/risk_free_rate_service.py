"""
Risk-free rate service for multiple currencies using FMP Treasury Rates API.
Supports USD, EUR, GBP and other major currencies with proper caching.
"""

import logging
from typing import Dict, Optional, Any, List
from datetime import date, datetime, timedelta
from decimal import Decimal
import requests

from apps.data.fmp_client import _get_api_key, _get_cache, _retry_with_backoff

logger = logging.getLogger(__name__)

# Currency to FMP Treasury endpoint mapping
CURRENCY_TREASURY_MAPPING = {
    'USD': {
        'endpoint': 'treasury',
        'maturity_field': 'yield_1_year',  # Use 1-year yield as default
        'backup_maturities': ['yield_3_month', 'yield_6_month', 'yield_2_year', 'yield_5_year', 'yield_10_year']
    },
    'EUR': {
        'endpoint': 'treasury',  # FMP may have Eurozone government bonds
        'maturity_field': 'yield_1_year',
        'backup_maturities': ['yield_3_month', 'yield_6_month', 'yield_2_year', 'yield_5_year', 'yield_10_year']
    },
    'GBP': {
        'endpoint': 'treasury',  # FMP may have UK government bonds
        'maturity_field': 'yield_1_year',
        'backup_maturities': ['yield_3_month', 'yield_6_month', 'yield_2_year', 'yield_5_year', 'yield_10_year']
    }
}

# Default risk-free rates by currency (fallback values)
DEFAULT_RISK_FREE_RATES = {
    'USD': 0.03,  # 3% annual
    'EUR': 0.025,  # 2.5% annual
    'GBP': 0.035,  # 3.5% annual
    'JPY': 0.01,   # 1% annual
    'CHF': 0.02,  # 2% annual
    'CAD': 0.03,   # 3% annual
    'AUD': 0.035,  # 3.5% annual
    'NZD': 0.04,   # 4% annual
    'SEK': 0.03,   # 3% annual
    'NOK': 0.035,  # 3.5% annual
    'DKK': 0.025,  # 2.5% annual
    'PLN': 0.04,   # 4% annual
    'CZK': 0.035,  # 3.5% annual
    'HUF': 0.05,   # 5% annual
    'RUB': 0.08,   # 8% annual
    'BRL': 0.06,   # 6% annual
    'MXN': 0.05,   # 5% annual
    'SGD': 0.03,   # 3% annual
    'HKD': 0.03,   # 3% annual
    'INR': 0.05,   # 5% annual
    'KRW': 0.03,   # 3% annual
    'CNY': 0.025,  # 2.5% annual
    'TRY': 0.08,   # 8% annual
    'ZAR': 0.06,   # 6% annual
    'ILS': 0.04,   # 4% annual
    'AED': 0.03,   # 3% annual
    'SAR': 0.03,   # 3% annual
    'QAR': 0.03,   # 3% annual
    'KWD': 0.03,   # 3% annual
    'BHD': 0.03,   # 3% annual
    'OMR': 0.03,   # 3% annual
    'JOD': 0.03,   # 3% annual
}


class RiskFreeRateService:
    """Service for fetching and caching risk-free rates by currency."""
    
    def __init__(self):
        self._cache = self._get_cache()
        self._cache_ttl = 24 * 60 * 60  # Cache for 24 hours
    
    def _get_cache(self):
        """Get Django cache instance."""
        try:
            from django.core.cache import cache
            return cache
        except Exception:
            # Fallback to simple dict cache for testing
            return {}
    
    def _get_cached_rate(self, currency: str, date_str: str) -> Optional[float]:
        """Get cached risk-free rate."""
        if isinstance(self._cache, dict):
            return self._cache.get(f"risk_free_rate:{currency}:{date_str}")
        else:
            return self._cache.get(f"risk_free_rate:{currency}:{date_str}")
    
    def _set_cached_rate(self, currency: str, date_str: str, rate: float):
        """Set cached risk-free rate."""
        if isinstance(self._cache, dict):
            self._cache[f"risk_free_rate:{currency}:{date_str}"] = rate
        else:
            self._cache.set(f"risk_free_rate:{currency}:{date_str}", rate, self._cache_ttl)
    
    def _fetch_treasury_rates(self, currency: str, target_date: Optional[date] = None) -> Optional[float]:
        """Fetch treasury rates from FMP API for a specific currency and date."""
        api_key = _get_api_key()
        if not api_key:
            logger.warning("FMP_API_KEY not configured, using default risk-free rate")
            return DEFAULT_RISK_FREE_RATES.get(currency, 0.03)
        
        # Use today's date if no target date provided
        if target_date is None:
            target_date = date.today()
        
        # Get date range (last 30 days to ensure we get recent data)
        start_date = target_date - timedelta(days=30)
        end_date = target_date
        
        try:
            # For USD, use the standard treasury endpoint
            if currency == 'USD':
                url = "https://financialmodelingprep.com/api/v4/treasury"
                params = {
                    "apikey": api_key,
                    "from": start_date.isoformat(),
                    "to": end_date.isoformat()
                }
                
                def fetch_data():
                    response = requests.get(url, params=params, timeout=10)
                    response.raise_for_status()
                    return response.json()
                
                data = _retry_with_backoff(fetch_data)
                
                if isinstance(data, list) and data:
                    # Find the most recent data point
                    latest_data = None
                    for item in reversed(data):  # Start from most recent
                        if isinstance(item, dict) and item.get('value') is not None:
                            latest_data = item
                            break
                    
                    if latest_data:
                        # Try different maturity fields
                        maturity_fields = ['yield_1_year', 'yield_3_month', 'yield_6_month', 'yield_2_year']
                        for field in maturity_fields:
                            try:
                                yield_value = latest_data.get(field)
                                if yield_value is not None:
                                    rate = float(yield_value) / 100.0  # Convert percentage to decimal
                                    logger.info(f"Fetched {currency} risk-free rate: {rate:.4f} from {field}")
                                    return rate
                            except (ValueError, TypeError):
                                continue
                
                logger.warning(f"No valid treasury data found for {currency}, using default")
                return DEFAULT_RISK_FREE_RATES.get(currency, 0.03)
            
            else:
                # For non-USD currencies, FMP may not have treasury data
                # We'll use default rates for now, but this could be extended
                # to use other data sources like ECB, Bank of England, etc.
                logger.info(f"Using default risk-free rate for {currency}: {DEFAULT_RISK_FREE_RATES.get(currency, 0.03)}")
                return DEFAULT_RISK_FREE_RATES.get(currency, 0.03)
                
        except Exception as e:
            logger.error(f"Error fetching treasury rates for {currency}: {e}")
            return DEFAULT_RISK_FREE_RATES.get(currency, 0.03)
    
    def get_risk_free_rate(self, currency: str, target_date: Optional[date] = None) -> float:
        """
        Get risk-free rate for a specific currency and date.
        
        Args:
            currency: Currency code (e.g., 'USD', 'EUR', 'GBP')
            target_date: Target date for the rate (defaults to today)
            
        Returns:
            Risk-free rate as decimal (e.g., 0.03 for 3%)
        """
        currency = currency.upper()
        
        # Use today's date if no target date provided
        if target_date is None:
            target_date = date.today()
        
        date_str = target_date.isoformat()
        
        # Check cache first
        cached_rate = self._get_cached_rate(currency, date_str)
        if cached_rate is not None:
            logger.debug(f"Cache hit for {currency} risk-free rate: {cached_rate:.4f}")
            return cached_rate
        
        # Fetch from API
        rate = self._fetch_treasury_rates(currency, target_date)
        
        # Cache the result
        self._set_cached_rate(currency, date_str, rate)
        
        logger.info(f"Risk-free rate for {currency} on {date_str}: {rate:.4f}")
        return rate
    
    def get_risk_free_rate_for_period(self, currency: str, start_date: date, end_date: date) -> float:
        """
        Get average risk-free rate for a period.
        
        Args:
            currency: Currency code
            start_date: Period start date
            end_date: Period end date
            
        Returns:
            Average risk-free rate for the period
        """
        currency = currency.upper()
        
        # For simplicity, use the rate from the middle of the period
        # In a more sophisticated implementation, we could average multiple rates
        period_length = (end_date - start_date).days
        middle_date = start_date + timedelta(days=period_length // 2)
        
        return self.get_risk_free_rate(currency, middle_date)
    
    def get_risk_free_rate_for_ytd(self, currency: str, year: Optional[int] = None) -> float:
        """
        Get risk-free rate for year-to-date period.
        
        Args:
            currency: Currency code
            year: Year (defaults to current year)
            
        Returns:
            Risk-free rate for YTD period
        """
        if year is None:
            year = date.today().year
        
        # Use the rate from the middle of the year
        middle_date = date(year, 6, 15)  # Mid-year
        return self.get_risk_free_rate(currency, middle_date)
    
    def get_supported_currencies(self) -> List[str]:
        """Get list of supported currencies."""
        return list(DEFAULT_RISK_FREE_RATES.keys())
    
    def is_currency_supported(self, currency: str) -> bool:
        """Check if a currency is supported."""
        return currency.upper() in DEFAULT_RISK_FREE_RATES


# Global service instance
_risk_free_rate_service = None


def get_risk_free_rate_service() -> RiskFreeRateService:
    """Get the global risk-free rate service instance."""
    global _risk_free_rate_service
    if _risk_free_rate_service is None:
        _risk_free_rate_service = RiskFreeRateService()
    return _risk_free_rate_service


def get_risk_free_rate(currency: str, target_date: Optional[date] = None) -> float:
    """
    Convenience function to get risk-free rate.
    
    Args:
        currency: Currency code (e.g., 'USD', 'EUR', 'GBP')
        target_date: Target date for the rate (defaults to today)
        
    Returns:
        Risk-free rate as decimal (e.g., 0.03 for 3%)
    """
    service = get_risk_free_rate_service()
    return service.get_risk_free_rate(currency, target_date)


def get_risk_free_rate_for_period(currency: str, start_date: date, end_date: date) -> float:
    """
    Convenience function to get risk-free rate for a period.
    
    Args:
        currency: Currency code
        start_date: Period start date
        end_date: Period end date
        
    Returns:
        Average risk-free rate for the period
    """
    service = get_risk_free_rate_service()
    return service.get_risk_free_rate_for_period(currency, start_date, end_date)


def get_risk_free_rate_for_ytd(currency: str, year: Optional[int] = None) -> float:
    """
    Convenience function to get risk-free rate for YTD period.
    
    Args:
        currency: Currency code
        year: Year (defaults to current year)
        
    Returns:
        Risk-free rate for YTD period
    """
    service = get_risk_free_rate_service()
    return service.get_risk_free_rate_for_ytd(currency, year)
