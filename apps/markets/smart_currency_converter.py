"""
Smart currency conversion service using forex pairs from database and FMP API.
Implements cross-currency conversion and intelligent pair selection.
"""

import logging
from typing import Dict, Optional, List, Tuple
from decimal import Decimal
from datetime import date, timedelta
from django.db.models import Q

from apps.data.models import Forex
from apps.data.fmp_client import _http_get_json, _get_api_key, _get_cache, _cached_call

logger = logging.getLogger(__name__)


class SmartCurrencyConverter:
    """Smart currency conversion service using forex pairs from database."""
    
    def __init__(self):
        self._cache = _get_cache()
        self._api_key = _get_api_key()
        self._forex_pairs_cache = None
        self._conversion_attempts = set()  # Track conversion attempts to prevent loops
    
    def _get_forex_pairs(self) -> List[Forex]:
        """Get all active forex pairs from database."""
        if self._forex_pairs_cache is None:
            self._forex_pairs_cache = list(Forex.objects.filter(is_active=True))
        return self._forex_pairs_cache
    
    def refresh_forex_pairs_cache(self):
        """Refresh the forex pairs cache from database."""
        self._forex_pairs_cache = None
        self._get_forex_pairs()
    
    def _find_direct_pair(self, from_currency: str, to_currency: str) -> Optional[Forex]:
        """Find direct forex pair for conversion."""
        pairs = self._get_forex_pairs()
        
        # Look for direct pair (from_currency -> to_currency)
        for pair in pairs:
            if (pair.from_currency == from_currency and pair.to_currency == to_currency) or \
               (pair.base_currency == from_currency and pair.quote_currency == to_currency):
                return pair
        
        return None
    
    def _find_inverse_pair(self, from_currency: str, to_currency: str) -> Optional[Forex]:
        """Find inverse forex pair for conversion."""
        pairs = self._get_forex_pairs()
        
        # Look for inverse pair (to_currency -> from_currency)
        for pair in pairs:
            if (pair.from_currency == to_currency and pair.to_currency == from_currency) or \
               (pair.base_currency == to_currency and pair.quote_currency == from_currency):
                return pair
        
        return None
    
    def _find_cross_currency_path(self, from_currency: str, to_currency: str) -> Optional[List[Forex]]:
        """
        Find a path for cross-currency conversion using common intermediate currencies.
        Tries USD, EUR, GBP, JPY in order of preference.
        """
        pairs = self._get_forex_pairs()
        
        # Common intermediate currencies in order of preference
        intermediate_currencies = ['USD', 'EUR', 'GBP', 'JPY']
        
        for intermediate in intermediate_currencies:
            if intermediate == from_currency or intermediate == to_currency:
                continue
                
            # Find pairs that involve the intermediate currency
            intermediate_pairs = []
            for pair in pairs:
                if (pair.from_currency == intermediate or pair.to_currency == intermediate or 
                    pair.base_currency == intermediate or pair.quote_currency == intermediate):
                    intermediate_pairs.append(pair)
            
            # Look for path: from_currency -> intermediate -> to_currency
            from_to_intermediate = None
            intermediate_to_target = None
            
            for pair in intermediate_pairs:
                # Check if pair converts from_currency to intermediate
                if ((pair.from_currency == from_currency and pair.to_currency == intermediate) or
                    (pair.base_currency == from_currency and pair.quote_currency == intermediate)):
                    from_to_intermediate = pair
                
                # Check if pair converts intermediate to to_currency
                if ((pair.from_currency == intermediate and pair.to_currency == to_currency) or
                    (pair.base_currency == intermediate and pair.quote_currency == to_currency)):
                    intermediate_to_target = pair
            
            if from_to_intermediate and intermediate_to_target:
                logger.info(f"Found cross-currency path: {from_currency} -> {intermediate} -> {to_currency}")
                return [from_to_intermediate, intermediate_to_target]
        
        # Try reverse paths (to_currency -> intermediate -> from_currency)
        for intermediate in intermediate_currencies:
            if intermediate == from_currency or intermediate == to_currency:
                continue
                
            intermediate_pairs = []
            for pair in pairs:
                if (pair.from_currency == intermediate or pair.to_currency == intermediate or 
                    pair.base_currency == intermediate or pair.quote_currency == intermediate):
                    intermediate_pairs.append(pair)
            
            # Look for reverse path: to_currency -> intermediate -> from_currency
            to_to_intermediate = None
            intermediate_to_from = None
            
            for pair in intermediate_pairs:
                # Check if pair converts to_currency to intermediate
                if ((pair.from_currency == to_currency and pair.to_currency == intermediate) or
                    (pair.base_currency == to_currency and pair.quote_currency == intermediate)):
                    to_to_intermediate = pair
                
                # Check if pair converts intermediate to from_currency
                if ((pair.from_currency == intermediate and pair.to_currency == from_currency) or
                    (pair.base_currency == intermediate and pair.quote_currency == from_currency)):
                    intermediate_to_from = pair
            
            if to_to_intermediate and intermediate_to_from:
                logger.info(f"Found reverse cross-currency path: {to_currency} -> {intermediate} -> {from_currency}")
                return [to_to_intermediate, intermediate_to_from]
        
        return None
    
    def get_exchange_rate(self, from_currency: str, to_currency: str, date_str: Optional[str] = None) -> Optional[Decimal]:
        """
        Get exchange rate between two currencies using smart conversion logic.
        
        Args:
            from_currency: Source currency code (e.g., 'EUR')
            to_currency: Target currency code (e.g., 'USD')
            date_str: Date in YYYY-MM-DD format (optional, defaults to latest)
            
        Returns:
            Exchange rate as Decimal or None if error
        """
        if from_currency == to_currency:
            return Decimal('1.0')
        
        # Prevent infinite loops by tracking conversion attempts
        conversion_key = f"{from_currency}:{to_currency}:{date_str or 'latest'}"
        if conversion_key in self._conversion_attempts:
            logger.warning(f"Conversion loop detected for {from_currency} to {to_currency}, returning None")
            return None
        
        self._conversion_attempts.add(conversion_key)
        
        try:
            # Use cached exchange rate
            cache_key = f"smart_forex_rate:{from_currency}:{to_currency}:{date_str or 'latest'}"
            if self._cache:
                cached_rate = self._cache.get(cache_key)
                if cached_rate:
                    return Decimal(str(cached_rate))
            
            # Try direct pair first
            direct_pair = self._find_direct_pair(from_currency, to_currency)
            if direct_pair:
                rate = self._get_pair_rate(direct_pair, date_str)
                if rate:
                    if self._cache:
                        self._cache.set(cache_key, float(rate), 300)  # Cache for 5 minutes
                    return rate
            
            # Try inverse pair
            inverse_pair = self._find_inverse_pair(from_currency, to_currency)
            if inverse_pair:
                rate = self._get_pair_rate(inverse_pair, date_str)
                if rate:
                    # Invert the rate
                    inverted_rate = Decimal('1') / rate
                    if self._cache:
                        self._cache.set(cache_key, float(inverted_rate), 300)
                    return inverted_rate
            
            # Try cross-currency conversion
            cross_path = self._find_cross_currency_path(from_currency, to_currency)
            if cross_path:
                rate = self._calculate_cross_rate(cross_path, date_str)
                if rate:
                    if self._cache:
                        self._cache.set(cache_key, float(rate), 300)
                    return rate
            
            logger.warning(f"No conversion path found for {from_currency} to {to_currency}")
            return None
            
        except Exception as e:
            logger.error(f"Error getting exchange rate {from_currency} to {to_currency}: {e}")
            return None
        finally:
            # Clean up conversion attempt tracking
            self._conversion_attempts.discard(conversion_key)
    
    def _get_pair_rate(self, pair: Forex, date_str: Optional[str] = None) -> Optional[Decimal]:
        """Get exchange rate for a specific forex pair."""
        try:
            if date_str:
                # Historical rate
                rate = self._get_historical_rate(pair.symbol, date_str)
            else:
                # Current rate
                rate = self._get_latest_rate(pair.symbol)
            
            return rate
            
        except Exception as e:
            logger.error(f"Error getting rate for pair {pair.symbol}: {e}")
            return None
    
    def _calculate_cross_rate(self, path: List[Forex], date_str: Optional[str] = None) -> Optional[Decimal]:
        """Calculate cross rate using a path of forex pairs."""
        try:
            total_rate = Decimal('1')
            
            for pair in path:
                rate = self._get_pair_rate(pair, date_str)
                if not rate:
                    return None
                
                # Determine if we need to invert the rate
                if (pair.from_currency == pair.base_currency and pair.to_currency == pair.quote_currency):
                    # Direct conversion
                    total_rate *= rate
                else:
                    # Inverse conversion
                    total_rate *= (Decimal('1') / rate)
            
            return total_rate
            
        except Exception as e:
            logger.error(f"Error calculating cross rate: {e}")
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
            }, use_stable=True)
            
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
        Convert amount from one currency to another using smart conversion.
        
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
        Normalize a list of price data to a target currency using smart conversion.
        
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
            
            # Get historical forex data in batch
            start_date = min(dates)
            end_date = max(dates)
            
            forex_history = self._get_forex_history_batch(forex_pair, start_date, end_date)
            
            if not forex_history:
                # Try cross-currency conversion
                logger.info(f"Trying cross-currency conversion for {from_currency} to {to_currency}")
                return self._normalize_with_cross_currency(prices, from_currency, to_currency)
            
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
    
    def get_historical_rates_batch(self, from_currency: str, to_currency: str, 
                                  start_date: str, end_date: str) -> Dict[str, Decimal]:
        """
        Get historical exchange rates for a date range in batch.
        
        Args:
            from_currency: Source currency code
            to_currency: Target currency code
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            
        Returns:
            Dictionary mapping date strings to exchange rates
        """
        if from_currency == to_currency:
            return {}
        
        try:
            # Check cache first
            cache_key = f"forex_batch:{from_currency}:{to_currency}:{start_date}:{end_date}"
            cached_rates = self._cache.get(cache_key) if self._cache else None
            if cached_rates:
                logger.info(f"Cache hit for batch forex rates: {from_currency} to {to_currency}")
                return cached_rates
            
            # Get forex pair for conversion
            forex_pair = f"{from_currency}{to_currency}"
            
            # Get historical forex data in batch
            forex_history = self._get_forex_history_batch(forex_pair, start_date, end_date)
            
            if not forex_history:
                # Try cross-currency conversion
                logger.info(f"Trying cross-currency conversion for batch rates: {from_currency} to {to_currency}")
                return self._get_cross_currency_rates_batch(from_currency, to_currency, start_date, end_date)
            
            # Cache the results for 1 hour
            if self._cache:
                self._cache.set(cache_key, forex_history, 3600)
            
            return forex_history
            
        except Exception as e:
            logger.error(f"Error getting batch forex rates: {e}")
            return {}
    
    def _get_cross_currency_rates_batch(self, from_currency: str, to_currency: str, 
                                       start_date: str, end_date: str) -> Dict[str, Decimal]:
        """Get cross-currency rates in batch using USD as intermediate currency."""
        try:
            # Convert through USD: from_currency -> USD -> to_currency
            usd_from_rates = self.get_historical_rates_batch(from_currency, 'USD', start_date, end_date)
            usd_to_rates = self.get_historical_rates_batch('USD', to_currency, start_date, end_date)
            
            # Combine rates
            combined_rates = {}
            for date_str in usd_from_rates:
                if date_str in usd_to_rates:
                    # Cross rate = (1 / USD_from_rate) * USD_to_rate
                    from_rate = usd_from_rates[date_str]
                    to_rate = usd_to_rates[date_str]
                    combined_rates[date_str] = (Decimal('1') / from_rate) * to_rate
            
            return combined_rates
            
        except Exception as e:
            logger.error(f"Error getting cross-currency rates batch: {e}")
            return {}
    
    def _normalize_with_cross_currency(self, prices: List[Dict], from_currency: str, to_currency: str) -> List[Dict]:
        """Normalize prices using cross-currency conversion."""
        try:
            # Find cross-currency path
            cross_path = self._find_cross_currency_path(from_currency, to_currency)
            if not cross_path:
                logger.error(f"No cross-currency path found for {from_currency} to {to_currency}")
                return prices
            
            # Convert prices using cross-currency rates
            normalized_prices = []
            for price_data in prices:
                try:
                    date_str = price_data.get('date')
                    rate = self._calculate_cross_rate(cross_path, date_str)
                    
                    if not rate:
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
                        converted_price = price * rate
                        
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
                    logger.warning(f"Error normalizing price data point with cross-currency: {e}")
                    normalized_prices.append(price_data)
            
            return normalized_prices
            
        except Exception as e:
            logger.error(f"Error in cross-currency normalization: {e}")
            return prices
    
    def _get_forex_history_batch(self, forex_pair: str, start_date: str, end_date: str) -> Dict[str, Decimal]:
        """Get historical forex rates for a date range."""
        try:
            # Check cache first
            cache_key = f"smart_forex_history:{forex_pair}:{start_date}:{end_date}"
            if self._cache:
                cached_history = self._cache.get(cache_key)
                if cached_history:
                    return {date_str: Decimal(str(rate)) for date_str, rate in cached_history.items()}
            
            # Get historical data from FMP
            data = _http_get_json("historical-price-eod/light", {
                "symbol": forex_pair,
                "from": start_date,
                "to": end_date
            }, use_stable=True)
            
            forex_history = {}
            
            if isinstance(data, list) and data:
                for item in data:
                    date_str = item.get('date')
                    price = item.get('price')
                    if date_str and price:
                        forex_history[date_str] = Decimal(str(price))
            
            # Cache the result for 1 hour
            if forex_history and self._cache:
                cache_data = {date_str: float(rate) for date_str, rate in forex_history.items()}
                self._cache.set(cache_key, cache_data, 3600)
            
            return forex_history
            
        except Exception as e:
            logger.error(f"Error getting forex history for {forex_pair}: {e}")
            return {}
    
    def _find_closest_rate(self, target_date: str, forex_history: Dict[str, Decimal]) -> Optional[Decimal]:
        """Find the closest available forex rate for a given date."""
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
        """Get list of supported currencies from forex pairs."""
        pairs = self._get_forex_pairs()
        currencies = set()
        
        for pair in pairs:
            currencies.add(pair.from_currency)
            currencies.add(pair.to_currency)
            currencies.add(pair.base_currency)
            currencies.add(pair.quote_currency)
        
        return sorted(list(currencies))
    
    def is_currency_supported(self, currency: str) -> bool:
        """Check if a currency is supported."""
        return currency.upper() in self.get_supported_currencies()


# Global converter instance
_smart_currency_converter = None


def get_smart_currency_converter() -> SmartCurrencyConverter:
    """Get global smart currency converter instance."""
    global _smart_currency_converter
    if _smart_currency_converter is None:
        _smart_currency_converter = SmartCurrencyConverter()
    return _smart_currency_converter


def refresh_smart_currency_converter():
    """Refresh the global smart currency converter instance."""
    global _smart_currency_converter
    _smart_currency_converter = None
    return get_smart_currency_converter()


def convert_currency_smart(amount: Decimal, from_currency: str, to_currency: str, date_str: Optional[str] = None) -> Optional[Decimal]:
    """
    Convenience function for smart currency conversion.
    
    Args:
        amount: Amount to convert
        from_currency: Source currency code
        to_currency: Target currency code
        date_str: Date in YYYY-MM-DD format (optional)
        
    Returns:
        Converted amount as Decimal or None if error
    """
    converter = get_smart_currency_converter()
    return converter.convert_amount(amount, from_currency, to_currency, date_str)


def normalize_prices_to_currency_smart(prices: List[Dict], from_currency: str, to_currency: str) -> List[Dict]:
    """
    Convenience function for smart price normalization.
    
    Args:
        prices: List of price dictionaries
        from_currency: Source currency code
        to_currency: Target currency code
        
    Returns:
        List of normalized price dictionaries
    """
    converter = get_smart_currency_converter()
    return converter.normalize_prices(prices, from_currency, to_currency)
