"""
Abstract asset classes for unified handling of different asset types.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
from datetime import date, datetime
from enum import Enum
import logging

from django.utils.translation import gettext_lazy as _

from apps.data.models import Instrument, Commodity, Cryptocurrency, Forex
from apps.data.fmp_client import (
    get_profile, get_price_series, get_dividend_history,
    get_commodities_quote, get_commodities_price_history,
    get_cryptocurrency_quote, get_cryptocurrency_price_history,
    get_forex_quote, get_forex_price_history
)

logger = logging.getLogger(__name__)


class AssetType(Enum):
    """Asset type enumeration."""
    STOCK = "stock"
    ETF = "etf"
    COMMODITY = "commodity"
    CRYPTOCURRENCY = "cryptocurrency"
    FOREX = "forex"


class BaseAsset(ABC):
    """Abstract base class for all asset types."""
    
    def __init__(self, symbol: str):
        self.symbol = symbol.upper()
        self._quote_data: Optional[Dict[str, Any]] = None
        self._price_history: Optional[List[Dict[str, Any]]] = None
        self._dividend_history: Optional[List[Dict[str, Any]]] = None
    
    @property
    @abstractmethod
    def asset_type(self) -> AssetType:
        """Return the asset type."""
        pass
    
    @property
    @abstractmethod
    def name(self) -> str:
        """Return the asset name."""
        pass
    
    @property
    @abstractmethod
    def currency(self) -> str:
        """Return the base currency."""
        pass
    
    @property
    @abstractmethod
    def exchange(self) -> str:
        """Return the exchange."""
        pass
    
    @abstractmethod
    def get_quote(self) -> Optional[Dict[str, Any]]:
        """Get current quote data."""
        pass
    
    @abstractmethod
    def get_price_history(self, days: int = 365, include_dividends: bool = False) -> List[Dict[str, Any]]:
        """Get historical price data."""
        pass
    
    @abstractmethod
    def get_dividend_history(self) -> List[Dict[str, Any]]:
        """Get dividend history (if applicable)."""
        pass
    
    def get_current_price(self) -> Optional[Decimal]:
        """Get current price."""
        quote = self.get_quote()
        if quote:
            # Try different possible price field names
            price_value = (quote.get('price') or 
                         quote.get('close') or 
                         quote.get('close_price') or 
                         quote.get('adjClose') or 
                         None)
            if price_value:
                try:
                    return Decimal(str(price_value))
                except (ValueError, TypeError):
                    return None
        return None
    
    def get_price_change(self) -> Optional[Decimal]:
        """Get price change."""
        quote = self.get_quote()
        if quote and quote.get('change'):
            try:
                return Decimal(str(quote['change']))
            except (ValueError, TypeError):
                return None
        return None
    
    def get_price_change_percentage(self) -> Optional[Decimal]:
        """Get price change percentage."""
        quote = self.get_quote()
        if quote:
            # Try different possible field names for change percentage
            change_pct_value = (quote.get('changePercentage') or 
                              quote.get('changePercent') or 
                              quote.get('change_percentage') or 
                              quote.get('change_percent') or 
                              None)
            if change_pct_value:
                try:
                    return Decimal(str(change_pct_value))
                except (ValueError, TypeError):
                    return None
        return None
    
    def get_market_cap(self) -> Optional[int]:
        """Get market capitalization."""
        quote = self.get_quote()
        if quote:
            # Try different possible field names for market cap
            market_cap_value = (quote.get('marketCap') or 
                               quote.get('market_cap') or 
                               quote.get('mktCap') or 
                               quote.get('mkt_cap') or 
                               None)
            if market_cap_value:
                try:
                    return int(market_cap_value)
                except (ValueError, TypeError):
                    return None
        return None
    
    def get_volume(self) -> Optional[int]:
        """Get trading volume."""
        quote = self.get_quote()
        if quote and quote.get('volume'):
            try:
                return int(quote['volume'])
            except (ValueError, TypeError):
                return None
        return None
    
    def calculate_cumulative_return(self, days: int = 365, include_dividends: bool = True) -> Optional[Decimal]:
        """
        Calculate cumulative return over specified period.
        
        Args:
            days: Number of days to look back
            include_dividends: Whether to include dividend payments
            
        Returns:
            Cumulative return as decimal (e.g., 0.15 for 15%)
        """
        try:
            price_history = self.get_price_history(days, include_dividends)
            if not price_history or len(price_history) < 2:
                return None
            
            # Sort by date (oldest first)
            price_history.sort(key=lambda x: x.get('date', ''))
            
            # Get first and last prices
            # For dividend-adjusted data, prefer adjClose; for regular data, prefer close
            first_price = Decimal(str(price_history[0].get('adjClose', price_history[0].get('close', price_history[0].get('price', 0)))))
            last_price = Decimal(str(price_history[-1].get('adjClose', price_history[-1].get('close', price_history[-1].get('price', 0)))))
            
            if first_price <= 0:
                return None
            
            # Calculate price return
            price_return = (last_price - first_price) / first_price
            
            # Add dividend return if applicable and requested
            # Note: If include_dividends=True, we're already using dividend-adjusted prices,
            # so we don't need to add additional dividend return
            dividend_return = Decimal('0')
            if include_dividends and self.asset_type in [AssetType.STOCK, AssetType.ETF]:
                # Only add dividend return if we're using regular prices (not dividend-adjusted)
                # This is determined by checking if we have dividend-adjusted data
                price_history_regular = self.get_price_history(days, False)
                if price_history_regular and len(price_history_regular) > 1:
                    # We have regular prices available, so we're using dividend-adjusted prices
                    # and don't need to add dividend return
                    dividend_return = Decimal('0')
                else:
                    # We don't have regular prices, so add dividend return manually
                    dividend_history = self.get_dividend_history()
                    if dividend_history:
                        # Calculate total dividends over the period
                        total_dividends = sum(
                            Decimal(str(d.get('dividend', 0))) 
                            for d in dividend_history 
                            if d.get('dividend')
                        )
                        dividend_return = total_dividends / first_price
            
            return price_return + dividend_return
            
        except Exception:
            return None
    
    def calculate_volatility(self, days: int = 365) -> Optional[Decimal]:
        """
        Calculate annualized volatility.
        
        Args:
            days: Number of days to look back
            
        Returns:
            Annualized volatility as decimal (e.g., 0.20 for 20%)
        """
        try:
            price_history = self.get_price_history(days, False)  # Volatility calculation doesn't need dividend adjustment
            if not price_history or len(price_history) < 2:
                return None
            
            # Sort by date (oldest first)
            price_history.sort(key=lambda x: x.get('date', ''))
            
            # Calculate daily returns
            returns = []
            for i in range(1, len(price_history)):
                prev_price = Decimal(str(price_history[i-1].get('adjClose', price_history[i-1].get('close', price_history[i-1].get('price', 0)))))
                curr_price = Decimal(str(price_history[i].get('adjClose', price_history[i].get('close', price_history[i].get('price', 0)))))
                
                if prev_price > 0:
                    daily_return = (curr_price - prev_price) / prev_price
                    returns.append(daily_return)
            
            if not returns:
                return None
            
            # Calculate standard deviation
            mean_return = sum(returns) / len(returns)
            variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
            std_dev = variance ** Decimal('0.5')
            
            # Annualize (assuming 252 trading days)
            annualized_volatility = std_dev * (Decimal('252') ** Decimal('0.5'))
            
            return annualized_volatility
            
        except Exception:
            return None
    
    def get_price_range(self, days: int = 365) -> Optional[Dict[str, Decimal]]:
        """
        Get price range over specified period.
        
        Args:
            days: Number of days to look back
            
        Returns:
            Dictionary with 'high' and 'low' prices
        """
        try:
            price_history = self.get_price_history(days, False)  # Price range doesn't need dividend adjustment
            if not price_history:
                return None
            
            prices = [
                Decimal(str(p.get('adjClose', p.get('close', p.get('price', 0))))) 
                for p in price_history 
                if p.get('adjClose') or p.get('close') or p.get('price')
            ]
            
            if not prices:
                return None
            
            return {
                'high': max(prices),
                'low': min(prices)
            }
            
        except Exception:
            return None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert asset to dictionary representation."""
        return {
            'symbol': self.symbol,
            'asset_type': self.asset_type.value,
            'name': self.name,
            'currency': self.currency,
            'exchange': self.exchange,
            'current_price': self.get_current_price(),
            'price_change': self.get_price_change(),
            'price_change_percentage': self.get_price_change_percentage(),
            'market_cap': self.get_market_cap(),
            'volume': self.get_volume(),
            'cumulative_return': self.calculate_cumulative_return(),
            'volatility': self.calculate_volatility(),
            'price_range': self.get_price_range()
        }


class StockAsset(BaseAsset):
    """Stock asset implementation."""
    
    def __init__(self, symbol: str):
        super().__init__(symbol)
        self._instrument: Optional[Instrument] = None
    
    @property
    def asset_type(self) -> AssetType:
        return AssetType.STOCK
    
    @property
    def name(self) -> str:
        if self._instrument:
            return self._instrument.name
        quote = self.get_quote()
        return quote.get('name', self.symbol) if quote else self.symbol
    
    @property
    def currency(self) -> str:
        if self._instrument and self._instrument.currency:
            return self._instrument.currency
        
        # Try to get currency from quote data
        quote = self.get_quote()
        if quote and quote.get('currency'):
            return quote.get('currency')
        
        # Fallback: detect currency based on exchange or symbol patterns
        exchange = self.exchange
        symbol_upper = self.symbol.upper()
        
        # Known exchange-to-currency mappings
        exchange_currency_map = {
            'MOEX': 'RUB',      # Moscow Exchange
            'LSE': 'GBP',       # London Stock Exchange
            'TSE': 'JPY',       # Tokyo Stock Exchange
            'FSE': 'EUR',       # Frankfurt Stock Exchange
            'EPA': 'EUR',       # Euronext Paris
            'AMS': 'EUR',       # Euronext Amsterdam
            'BRU': 'EUR',       # Euronext Brussels
            'LIS': 'EUR',       # Euronext Lisbon
            'OSL': 'NOK',       # Oslo Stock Exchange
            'STO': 'SEK',       # Stockholm Stock Exchange
            'CPH': 'DKK',       # Copenhagen Stock Exchange
            'HEL': 'EUR',       # Helsinki Stock Exchange
            'WSE': 'PLN',       # Warsaw Stock Exchange
            'BSE': 'INR',       # Bombay Stock Exchange
            'NSE': 'INR',       # National Stock Exchange of India
            'HKEX': 'HKD',      # Hong Kong Exchange
            'SSE': 'CNY',       # Shanghai Stock Exchange
            'SZSE': 'CNY',      # Shenzhen Stock Exchange
            'KRX': 'KRW',       # Korea Exchange
            'TSE': 'TWD',       # Taiwan Stock Exchange
            'SGX': 'SGD',       # Singapore Exchange
            'ASX': 'AUD',       # Australian Securities Exchange
            'TSX': 'CAD',       # Toronto Stock Exchange
            'BMV': 'MXN',       # Mexican Stock Exchange
            'BOVESPA': 'BRL',   # Brazilian Stock Exchange
        }
        
        # Check exchange mapping first
        if exchange in exchange_currency_map:
            return exchange_currency_map[exchange]
        
        # Check symbol patterns for specific markets
        if symbol_upper.endswith('.ME'):  # Moscow Exchange
            return 'RUB'
        elif symbol_upper.endswith('.L'):  # London Stock Exchange
            return 'GBP'
        elif symbol_upper.endswith('.T'):  # Tokyo Stock Exchange
            return 'JPY'
        elif symbol_upper.endswith('.F'):  # Frankfurt Stock Exchange
            return 'EUR'
        elif symbol_upper.endswith('.PA'):  # Euronext Paris
            return 'EUR'
        elif symbol_upper.endswith('.AS'):  # Euronext Amsterdam
            return 'EUR'
        elif symbol_upper.endswith('.BR'):  # Euronext Brussels
            return 'EUR'
        elif symbol_upper.endswith('.LS'):  # Euronext Lisbon
            return 'EUR'
        elif symbol_upper.endswith('.OL'):  # Oslo Stock Exchange
            return 'NOK'
        elif symbol_upper.endswith('.ST'):  # Stockholm Stock Exchange
            return 'SEK'
        elif symbol_upper.endswith('.CO'):  # Copenhagen Stock Exchange
            return 'DKK'
        elif symbol_upper.endswith('.HE'):  # Helsinki Stock Exchange
            return 'EUR'
        elif symbol_upper.endswith('.WA'):  # Warsaw Stock Exchange
            return 'PLN'
        elif symbol_upper.endswith('.BO'):  # Bombay Stock Exchange
            return 'INR'
        elif symbol_upper.endswith('.NS'):  # National Stock Exchange of India
            return 'INR'
        elif symbol_upper.endswith('.HK'):  # Hong Kong Exchange
            return 'HKD'
        elif symbol_upper.endswith('.SS'):  # Shanghai Stock Exchange
            return 'CNY'
        elif symbol_upper.endswith('.SZ'):  # Shenzhen Stock Exchange
            return 'CNY'
        elif symbol_upper.endswith('.KS'):  # Korea Exchange
            return 'KRW'
        elif symbol_upper.endswith('.TW'):  # Taiwan Stock Exchange
            return 'TWD'
        elif symbol_upper.endswith('.SI'):  # Singapore Exchange
            return 'SGD'
        elif symbol_upper.endswith('.AX'):  # Australian Securities Exchange
            return 'AUD'
        elif symbol_upper.endswith('.TO'):  # Toronto Stock Exchange
            return 'CAD'
        elif symbol_upper.endswith('.MX'):  # Mexican Stock Exchange
            return 'MXN'
        elif symbol_upper.endswith('.SA'):  # Brazilian Stock Exchange
            return 'BRL'
        
        # Default to USD for US exchanges and unknown
        return 'USD'
    
    @property
    def exchange(self) -> str:
        if self._instrument:
            return self._instrument.exchange
        quote = self.get_quote()
        return quote.get('exchange', '') if quote else ''
    
    def get_quote(self) -> Optional[Dict[str, Any]]:
        """Get current quote data."""
        if self._quote_data is None:
            self._quote_data = get_profile(self.symbol)
        return self._quote_data
    
    def get_price_history(self, days: int = 365, include_dividends: bool = False) -> List[Dict[str, Any]]:
        """Get historical price data."""
        # Calculate start date based on days parameter
        from datetime import datetime, timedelta
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        
        # Always fetch fresh data to ensure correct period
        # Don't cache to avoid issues with different day parameters
        return get_price_series(self.symbol, start_date, end_date, include_dividends) or []
    
    def get_dividend_history(self) -> List[Dict[str, Any]]:
        """Get dividend history."""
        if self._dividend_history is None:
            self._dividend_history = get_dividend_history(self.symbol)
        return self._dividend_history or []
    
    def get_market_cap(self) -> Optional[int]:
        """Get market capitalization with fallback to dedicated API."""
        # First try the base implementation (from profile data)
        market_cap = super().get_market_cap()
        if market_cap:
            return market_cap
        
        # Fallback: try the dedicated market cap API
        try:
            from apps.data.fmp_client import get_market_cap
            fallback_market_cap = get_market_cap(self.symbol)
            if fallback_market_cap:
                return int(fallback_market_cap)
        except Exception as e:
            # Log the error for debugging
            import logging
            logger = logging.getLogger(__name__)
            logger.warning(f"Failed to get market cap for {self.symbol}: {e}")
        
        return None


class ETFAsset(StockAsset):
    """ETF asset implementation (inherits from StockAsset)."""
    
    @property
    def asset_type(self) -> AssetType:
        return AssetType.ETF


class CommodityAsset(BaseAsset):
    """Commodity asset implementation."""
    
    def __init__(self, symbol: str):
        super().__init__(symbol)
        self._commodity: Optional[Commodity] = None
    
    @property
    def asset_type(self) -> AssetType:
        return AssetType.COMMODITY
    
    @property
    def name(self) -> str:
        if self._commodity:
            return self._commodity.name
        quote = self.get_quote()
        return quote.get('name', self.symbol) if quote else self.symbol
    
    @property
    def currency(self) -> str:
        if self._commodity:
            return self._commodity.currency
        return 'USD'  # Most commodities are quoted in USD
    
    @property
    def exchange(self) -> str:
        if self._commodity:
            return self._commodity.exchange
        return 'COMEX'  # Default commodity exchange
    
    def get_quote(self) -> Optional[Dict[str, Any]]:
        """Get current quote data."""
        if self._quote_data is None:
            self._quote_data = get_commodities_quote(self.symbol)
        return self._quote_data
    
    def get_price_history(self, days: int = 365, include_dividends: bool = False) -> List[Dict[str, Any]]:
        """Get historical price data."""
        # Always fetch fresh data to ensure correct period
        # Don't cache to avoid issues with different day parameters
        return get_commodities_price_history(self.symbol, days) or []
    
    def get_dividend_history(self) -> List[Dict[str, Any]]:
        """Commodities don't pay dividends."""
        return []


class CryptocurrencyAsset(BaseAsset):
    """Cryptocurrency asset implementation."""
    
    def __init__(self, symbol: str):
        super().__init__(symbol)
        self._cryptocurrency: Optional[Cryptocurrency] = None
    
    @property
    def asset_type(self) -> AssetType:
        return AssetType.CRYPTOCURRENCY
    
    @property
    def name(self) -> str:
        if self._cryptocurrency:
            return self._cryptocurrency.name
        quote = self.get_quote()
        return quote.get('name', self.symbol) if quote else self.symbol
    
    @property
    def currency(self) -> str:
        if self._cryptocurrency:
            return self._cryptocurrency.currency
        return 'USD'  # Most cryptocurrencies are quoted in USD
    
    @property
    def exchange(self) -> str:
        return 'CCC'  # Cryptocurrency exchange
    
    def get_quote(self) -> Optional[Dict[str, Any]]:
        """Get current quote data."""
        if self._quote_data is None:
            self._quote_data = get_cryptocurrency_quote(self.symbol)
        return self._quote_data
    
    def get_price_history(self, days: int = 365, include_dividends: bool = False) -> List[Dict[str, Any]]:
        """Get historical price data."""
        # Always fetch fresh data to ensure correct period
        # Don't cache to avoid issues with different day parameters
        return get_cryptocurrency_price_history(self.symbol, days) or []
    
    def get_dividend_history(self) -> List[Dict[str, Any]]:
        """Cryptocurrencies don't pay traditional dividends."""
        return []


class ForexAsset(BaseAsset):
    """Forex asset implementation."""
    
    def __init__(self, symbol: str):
        super().__init__(symbol)
        self._forex: Optional[Forex] = None
    
    @property
    def asset_type(self) -> AssetType:
        return AssetType.FOREX
    
    @property
    def name(self) -> str:
        if self._forex:
            return self._forex.name
        # Extract currencies from symbol (e.g., EURUSD -> EUR/USD)
        if len(self.symbol) == 6:
            base = self.symbol[:3]
            quote = self.symbol[3:]
            return f"{base}/{quote}"
        return self.symbol
    
    @property
    def currency(self) -> str:
        if self._forex:
            return self._forex.base_currency
        # Return base currency from symbol
        if len(self.symbol) == 6:
            return self.symbol[:3]
        return 'USD'
    
    @property
    def exchange(self) -> str:
        return 'FOREX'
    
    def get_quote(self) -> Optional[Dict[str, Any]]:
        """Get current quote data."""
        if self._quote_data is None:
            self._quote_data = get_forex_quote(self.symbol)
        return self._quote_data
    
    def get_price_history(self, days: int = 365, include_dividends: bool = False) -> List[Dict[str, Any]]:
        """Get historical price data."""
        try:
            # Always fetch fresh data to ensure correct period
            # Don't cache to avoid issues with different day parameters
            result = get_forex_price_history(self.symbol, days)
            if result is None:
                logger.warning(f"get_forex_price_history returned None for {self.symbol}")
                return []
            return result
        except Exception as e:
            logger.error(f"Error getting forex price history for {self.symbol}: {e}")
            return []
    
    def get_dividend_history(self) -> List[Dict[str, Any]]:
        """Forex doesn't pay dividends."""
        return []


class AssetFactory:
    """Factory class for creating asset instances."""
    
    @staticmethod
    def create_asset(symbol: str, asset_type: Optional[AssetType] = None) -> BaseAsset:
        """
        Create an asset instance based on symbol or explicit type.
        
        Args:
            symbol: Asset symbol
            asset_type: Explicit asset type (optional)
            
        Returns:
            Asset instance
        """
        symbol_upper = symbol.upper()
        
        # If explicit type is provided, use it
        if asset_type:
            if asset_type == AssetType.STOCK:
                return StockAsset(symbol_upper)
            elif asset_type == AssetType.ETF:
                return ETFAsset(symbol_upper)
            elif asset_type == AssetType.COMMODITY:
                return CommodityAsset(symbol_upper)
            elif asset_type == AssetType.CRYPTOCURRENCY:
                return CryptocurrencyAsset(symbol_upper)
            elif asset_type == AssetType.FOREX:
                return ForexAsset(symbol_upper)
        
        # Auto-detect asset type based on symbol patterns
        if len(symbol_upper) == 6:
            # Check if it's a forex pair (6 characters: EURUSD, GBPUSD, RUBUSD, etc.)
            forex_base_currencies = ['EUR', 'GBP', 'JPY', 'CHF', 'AUD', 'CAD', 'NZD', 'RUB', 'CNY', 'INR', 'BRL', 'MXN', 'KRW', 'SGD', 'HKD', 'NOK', 'SEK', 'DKK', 'PLN', 'CZK', 'HUF', 'TRY', 'ZAR', 'ILS', 'AED', 'SAR', 'QAR', 'KWD', 'BHD', 'OMR', 'JOD', 'LBP', 'EGP', 'MAD', 'TND', 'DZD', 'LYD', 'SDG', 'ETB', 'KES', 'UGX', 'TZS', 'ZMW', 'BWP', 'SZL', 'LSL', 'NAD', 'MUR', 'SCR', 'MVR', 'NPR', 'PKR', 'BDT', 'LKR', 'MMK', 'THB', 'VND', 'IDR', 'MYR', 'PHP', 'TWD', 'KHR', 'LAK', 'BND', 'FJD', 'PGK', 'WST', 'TOP', 'VUV', 'SBD', 'NZD', 'AUD', 'CAD', 'USD']
            forex_quote_currencies = ['USD', 'EUR', 'GBP', 'JPY', 'CHF', 'AUD', 'CAD', 'NZD', 'RUB', 'CNY', 'INR', 'BRL', 'MXN', 'KRW', 'SGD', 'HKD', 'NOK', 'SEK', 'DKK', 'PLN', 'CZK', 'HUF', 'TRY', 'ZAR', 'ILS', 'AED', 'SAR', 'QAR', 'KWD', 'BHD', 'OMR', 'JOD', 'LBP', 'EGP', 'MAD', 'TND', 'DZD', 'LYD', 'SDG', 'ETB', 'KES', 'UGX', 'TZS', 'ZMW', 'BWP', 'SZL', 'LSL', 'NAD', 'MUR', 'SCR', 'MVR', 'NPR', 'PKR', 'BDT', 'LKR', 'MMK', 'THB', 'VND', 'IDR', 'MYR', 'PHP', 'TWD', 'KHR', 'LAK', 'BND', 'FJD', 'PGK', 'WST', 'TOP', 'VUV', 'SBD']
            
            base_currency = symbol_upper[:3]
            quote_currency = symbol_upper[3:]
            
            if base_currency in forex_base_currencies and quote_currency in forex_quote_currencies:
                return ForexAsset(symbol_upper)
            # Check if it's a cryptocurrency (6 characters: BTCUSD, ETHUSD, etc.)
            elif base_currency in ['BTC', 'ETH', 'ADA', 'DOT', 'LINK', 'LTC', 'BCH', 'XLM', 'BNB', 'EOS', 'XRP', 'TRX', 'XMR', 'DASH', 'NEO', 'IOTA', 'ETC', 'ZEC', 'DOGE', 'SHIB', 'MATIC', 'AVAX', 'SOL', 'ATOM']:
                return CryptocurrencyAsset(symbol_upper)
        elif symbol_upper.endswith('USD') and len(symbol_upper) == 5:
            # Check if it's a commodity (5 characters: GCUSD, SIUSD, etc.)
            if symbol_upper[:2] in ['GC', 'SI', 'CL', 'NG', 'HG', 'PL', 'PA']:
                return CommodityAsset(symbol_upper)
        
        # Check for ETF patterns
        if any(symbol_upper.startswith(prefix) for prefix in ['SPY', 'QQQ', 'IWM', 'VTI', 'VEA', 'VWO', 'AGG', 'TLT', 'GLD', 'SLV']):
            return ETFAsset(symbol_upper)
        
        # Default to stock
        return StockAsset(symbol_upper)
    
    @staticmethod
    def create_assets(symbols: List[str], asset_types: Optional[List[AssetType]] = None) -> List[BaseAsset]:
        """
        Create multiple asset instances.
        
        Args:
            symbols: List of asset symbols
            asset_types: List of asset types (optional)
            
        Returns:
            List of asset instances
        """
        assets = []
        for i, symbol in enumerate(symbols):
            asset_type = asset_types[i] if asset_types and i < len(asset_types) else None
            assets.append(AssetFactory.create_asset(symbol, asset_type))
        return assets
