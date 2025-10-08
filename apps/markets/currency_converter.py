"""
Currency conversion service using FMP Forex API.
"""

import logging
from typing import Dict, Optional, List
from decimal import Decimal
from datetime import date, timedelta

from apps.data.fmp_client import _http_get_json, _get_api_key, _get_cache, _cached_call

logger = logging.getLogger(__name__)


class CurrencyConverter:
    """Currency conversion service using FMP Forex API."""
    
    def __init__(self):
        self._cache = _get_cache()
        self._api_key = _get_api_key()
    
    def get_exchange_rate(self, from_currency: str, to_currency: str, date_str: Optional[str] = None) -> Optional[Decimal]:
        """
        Get exchange rate between two currencies.
        
        Args:
            from_currency: Source currency code (e.g., 'EUR')
            to_currency: Target currency code (e.g., 'USD')
            date_str: Date in YYYY-MM-DD format (optional, defaults to latest)
            
        Returns:
            Exchange rate as Decimal or None if error
        """
        if from_currency == to_currency:
            return Decimal('1.0')
        
        try:
            # Create forex pair symbol
            forex_pair = f"{from_currency}{to_currency}"
            
            # Use cached exchange rate
            cache_key = f"forex_rate:{forex_pair}:{date_str or 'latest'}"
            if self._cache:
                cached_rate = self._cache.get(cache_key)
                if cached_rate:
                    return Decimal(str(cached_rate))
            
            # Get exchange rate from FMP
            if date_str:
                # Historical rate
                rate = self._get_historical_rate(forex_pair, date_str)
            else:
                # Current rate - try to get latest available rate
                rate = self._get_latest_rate(forex_pair)
            
            if rate:
                # Cache the result
                if self._cache:
                    self._cache.set(cache_key, float(rate), 300)  # Cache for 5 minutes
                return rate
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting exchange rate {from_currency} to {to_currency}: {e}")
            return None
    
    def _get_latest_rate(self, forex_pair: str) -> Optional[Decimal]:
        """Get latest available exchange rate."""
        try:
            # Try to get the latest rate from historical data
            from datetime import datetime, timedelta
            
            # Get data for the last 7 days
            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')
            
            data = _http_get_json("historical-price-eod/light", {
                "symbol": forex_pair,
                "from": start_date,
                "to": end_date
            }, use_stable=True)
            
            if isinstance(data, list) and data:
                # Get the most recent rate
                latest_item = data[0]  # Data is usually sorted by date descending
                price = latest_item.get('price')
                if price:
                    return Decimal(str(price))
            
            # If direct pair doesn't work, try inverse
            inverse_pair = forex_pair[3:] + forex_pair[:3]
            data = _http_get_json("historical-price-eod/light", {
                "symbol": inverse_pair,
                "from": start_date,
                "to": end_date
            }, use_stable=True)
            
            if isinstance(data, list) and data:
                latest_item = data[0]
                price = latest_item.get('price')
                if price and float(price) != 0:
                    # Return inverse of the rate
                    return Decimal('1') / Decimal(str(price))
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting latest rate for {forex_pair}: {e}")
            return None
    
    def _get_historical_rate(self, forex_pair: str, date_str: str) -> Optional[Decimal]:
        """Get historical exchange rate."""
        try:
            # Get historical data for the specific date
            data = _http_get_json("historical-price-eod/light", {
                "symbol": forex_pair,
                "from": date_str,
                "to": date_str
            })
            
            if isinstance(data, list) and data:
                price = data[0].get('price')
                if price:
                    return Decimal(str(price))
            
            return None
            
        except Exception as e:
            logger.error(f"Error getting historical rate for {forex_pair} on {date_str}: {e}")
            return None
    
    def convert_amount(self, amount: Decimal, from_currency: str, to_currency: str, date_str: Optional[str] = None) -> Optional[Decimal]:
        """
        Convert amount from one currency to another.
        
        Args:
            amount: Amount to convert
            from_currency: Source currency code
            to_currency: Target currency code
            date_str: Date in YYYY-MM-DD format (optional)
            
        Returns:
            Converted amount as Decimal or None if error
        """
        try:
            rate = self.get_exchange_rate(from_currency, to_currency, date_str)
            if rate:
                return amount * rate
            
            logger.error(f"No exchange rate available for {from_currency} to {to_currency}")
            return None
            
        except Exception as e:
            logger.error(f"Error converting {amount} from {from_currency} to {to_currency}: {e}")
            return None
    
    def normalize_prices(self, prices: List[Dict], from_currency: str, to_currency: str) -> List[Dict]:
        """
        Normalize a list of price data to a target currency.
        Uses batch conversion with historical forex data for efficiency.
        
        Args:
            prices: List of price dictionaries with 'price' and 'date' keys
            from_currency: Source currency code
            to_currency: Target currency code
            
        Returns:
            List of normalized price dictionaries
        """
        if from_currency == to_currency:
            return prices
        
        if not prices:
            return []
        
        try:
            # Extract dates and build forex history cache
            dates = [p.get('date') for p in prices if p.get('date')]
            if not dates:
                logger.warning("No dates found in price data, cannot convert currency")
                return prices
            
            # Get forex pair for conversion
            forex_pair = f"{from_currency}{to_currency}"
            
            # Get historical forex data in batch (much more efficient than per-date API calls)
            start_date = min(dates)
            end_date = max(dates)
            
            forex_history = self._get_forex_history_batch(forex_pair, start_date, end_date)
            
            if not forex_history:
                logger.error(f"No forex history available for {forex_pair}")
                raise ValueError(f"Currency conversion not available: {from_currency} to {to_currency}")
            
            # Convert prices using cached forex rates
            normalized_prices = []
            for price_data in prices:
                try:
                    date_str = price_data.get('date')
                    
                    # Get forex rate for this date
                    forex_rate = forex_history.get(date_str)
                    if not forex_rate:
                        # Try to find closest date
                        forex_rate = self._find_closest_rate(date_str, forex_history)
                    
                    if not forex_rate:
                        # If no rate available, keep original data
                        normalized_prices.append(price_data)
                        continue
                    
                    # Get price value
                    price_value = (price_data.get('price') or 
                                 price_data.get('close') or 
                                 price_data.get('close_price') or 
                                 price_data.get('adjClose') or 
                                 0)
                    
                    if price_value > 0:
                        # Convert price
                        price = Decimal(str(price_value))
                        converted_price = price * forex_rate
                        
                        # Create normalized data
                        normalized_data = price_data.copy()
                        
                        # Update the price field that was used for conversion
                        if 'price' in price_data:
                            normalized_data['price'] = float(converted_price)
                        elif 'close' in price_data:
                            normalized_data['close'] = float(converted_price)
                        elif 'close_price' in price_data:
                            normalized_data['close_price'] = float(converted_price)
                        elif 'adjClose' in price_data:
                            normalized_data['adjClose'] = float(converted_price)
                        else:
                            normalized_data['price'] = float(converted_price)
                        
                        normalized_data['original_currency'] = from_currency
                        normalized_data['converted_currency'] = to_currency
                        normalized_prices.append(normalized_data)
                    else:
                        normalized_prices.append(price_data)
                        
                except Exception as e:
                    logger.warning(f"Error normalizing price data point: {e}")
                    normalized_prices.append(price_data)
            
            return normalized_prices
            
        except Exception as e:
            logger.error(f"Error in batch normalization: {e}")
            return prices
    
    def _get_forex_history_batch(self, forex_pair: str, start_date: str, end_date: str) -> Dict[str, Decimal]:
        """
        Get historical forex rates for a date range in a single API call.
        
        Args:
            forex_pair: Forex pair symbol (e.g., 'USDRUB')
            start_date: Start date in YYYY-MM-DD format
            end_date: End date in YYYY-MM-DD format
            
        Returns:
            Dictionary mapping date strings to exchange rates
        """
        try:
            # Check cache first
            cache_key = f"forex_history:{forex_pair}:{start_date}:{end_date}"
            if self._cache:
                cached_history = self._cache.get(cache_key)
                if cached_history:
                    return {date_str: Decimal(str(rate)) for date_str, rate in cached_history.items()}
            
            # Get historical data from FMP using the correct endpoint
            data = _http_get_json("historical-price-eod/light", {
                "symbol": forex_pair,
                "from": start_date,
                "to": end_date
            }, use_stable=True)
            
            forex_history = {}
            
            # Process data from historical-price-eod/light endpoint
            if isinstance(data, list) and data:
                for item in data:
                    date_str = item.get('date')
                    price = item.get('price')  # Эндпоинт возвращает 'price', а не 'close'
                    if date_str and price:
                        forex_history[date_str] = Decimal(str(price))
            
            # If direct pair doesn't work, try inverse
            if not forex_history:
                inverse_pair = forex_pair[3:] + forex_pair[:3]
                data = _http_get_json("historical-price-eod/light", {
                    "symbol": inverse_pair,
                    "from": start_date,
                    "to": end_date
                }, use_stable=True)
                
                if isinstance(data, list) and data:
                    for item in data:
                        date_str = item.get('date')
                        price = item.get('price')  # Эндпоинт возвращает 'price', а не 'close'
                        if date_str and price and float(price) != 0:
                            # Invert the rate
                            forex_history[date_str] = Decimal('1') / Decimal(str(price))
            
            # Cache the result for 1 hour
            if forex_history and self._cache:
                # Convert Decimal to float for caching
                cache_data = {date_str: float(rate) for date_str, rate in forex_history.items()}
                self._cache.set(cache_key, cache_data, 3600)
            
            return forex_history
            
        except Exception as e:
            logger.error(f"Error getting forex history for {forex_pair}: {e}")
            return {}
    
    def _find_closest_rate(self, target_date: str, forex_history: Dict[str, Decimal]) -> Optional[Decimal]:
        """
        Find the closest available forex rate for a given date.
        
        Args:
            target_date: Target date in YYYY-MM-DD format
            forex_history: Dictionary of available rates
            
        Returns:
            Closest forex rate or None
        """
        if not forex_history:
            return None
        
        try:
            from datetime import datetime, timedelta
            
            target = datetime.strptime(target_date, '%Y-%m-%d')
            
            # Look for rates within +/- 7 days
            for days_offset in range(8):
                for offset in [days_offset, -days_offset]:
                    check_date = (target + timedelta(days=offset)).strftime('%Y-%m-%d')
                    if check_date in forex_history:
                        return forex_history[check_date]
            
            # If no close date found, return any available rate
            return next(iter(forex_history.values()))
            
        except Exception as e:
            logger.warning(f"Error finding closest rate for {target_date}: {e}")
            return None
    
    def get_supported_currencies(self) -> List[str]:
        """
        Get list of supported currencies.
        
        Returns:
            List of currency codes
        """
        return [
            'USD', 'EUR', 'GBP', 'JPY', 'CHF', 'AUD', 'CAD', 'NZD',
            'SGD', 'HKD', 'SEK', 'NOK', 'DKK', 'PLN', 'CZK', 'HUF',
            'RUB', 'CNY', 'INR', 'KRW', 'MXN', 'BRL', 'ZAR', 'TRY'
        ]
    
    def is_currency_supported(self, currency: str) -> bool:
        """
        Check if a currency is supported.
        
        Args:
            currency: Currency code to check
            
        Returns:
            True if supported, False otherwise
        """
        return currency.upper() in self.get_supported_currencies()


# Global converter instance
_currency_converter = None


def get_currency_converter() -> CurrencyConverter:
    """Get global currency converter instance."""
    global _currency_converter
    if _currency_converter is None:
        _currency_converter = CurrencyConverter()
    return _currency_converter


def convert_currency(amount: Decimal, from_currency: str, to_currency: str, date_str: Optional[str] = None) -> Optional[Decimal]:
    """
    Convenience function for currency conversion.
    
    Args:
        amount: Amount to convert
        from_currency: Source currency code
        to_currency: Target currency code
        date_str: Date in YYYY-MM-DD format (optional)
        
    Returns:
        Converted amount as Decimal or None if error
    """
    converter = get_currency_converter()
    return converter.convert_amount(amount, from_currency, to_currency, date_str)


def normalize_prices_to_currency(prices: List[Dict], from_currency: str, to_currency: str) -> List[Dict]:
    """
    Convenience function for price normalization.
    
    Args:
        prices: List of price dictionaries
        from_currency: Source currency code
        to_currency: Target currency code
        
    Returns:
        List of normalized price dictionaries
    """
    converter = get_currency_converter()
    return converter.normalize_prices(prices, from_currency, to_currency)
