"""
Enhanced charting service for server-driven asset comparison.
Implements granularity selection, aggregation, and normalization logic.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
from datetime import date, timedelta, datetime
from enum import Enum
import math
import hashlib
import concurrent.futures
import threading

from .assets import AssetFactory, BaseAsset, AssetType
from .smart_currency_converter import get_smart_currency_converter, refresh_smart_currency_converter, normalize_prices_to_currency_smart
from .risk_free_rate_service import get_risk_free_rate_service

logger = logging.getLogger(__name__)


class Granularity(Enum):
    """Data granularity levels."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    QUARTERLY = "quarterly"


class NormalizeMode(Enum):
    """Normalization modes for comparison."""
    INDEX_100 = "index100"
    PERCENT_CHANGE = "percent_change"


class PeriodPreset(Enum):
    """Period presets for comparison."""
    ONE_MONTH = "1M"
    THREE_MONTHS = "3M"
    SIX_MONTHS = "6M"
    YEAR_TO_DATE = "YTD"
    ONE_YEAR = "1Y"
    THREE_YEARS = "3Y"
    FIVE_YEARS = "5Y"
    TEN_YEARS = "10Y"
    MAXIMUM = "MAX"


class ChartDataPoint:
    """Represents a single data point in the chart."""
    
    def __init__(self, date: date, value: float, raw_value: Optional[float] = None):
        self.date = date
        self.value = value  # Normalized value
        self.raw_value = raw_value  # Original price value


class AggregatedDataPoint:
    """Represents an aggregated OHLC data point."""
    
    def __init__(self, date: date, open_price: float, high_price: float, 
                 low_price: float, close_price: float, volume: int = 0):
        self.date = date
        self.open_price = open_price
        self.high_price = high_price
        self.low_price = low_price
        self.close_price = close_price
        self.volume = volume


class ChartService:
    """Enhanced charting service with server-driven aggregation and normalization."""
    
    def __init__(self):
        self.currency_converter = refresh_smart_currency_converter()
        self.risk_free_rate_service = get_risk_free_rate_service()
        self._cache = self._get_cache()
        self._non_trading_symbols = set()  # Cache for symbols known to be non-actively trading
    
    def _get_cache(self):
        """Get Django cache instance."""
        try:
            from django.core.cache import cache
            return cache
        except Exception:
            # Fallback to simple dict cache for testing
            return {}
    
    def _is_symbol_actively_trading(self, asset: BaseAsset) -> bool:
        """Check if a symbol is actively trading to avoid unnecessary API calls."""
        symbol = asset.symbol
        
        # Check cache first
        if symbol in self._non_trading_symbols:
            return False
        
        try:
            quote = asset.get_quote()
            # Only skip if we have a quote and it explicitly says not actively trading
            # AND we don't have any price data available
            if quote and quote.get('isActivelyTrading') is False:
                # Check if we have any price data available despite being marked as not actively trading
                try:
                    # Try to get recent price data to see if it's actually available
                    recent_data = asset.get_price_history(days=7, include_dividends=False)
                    if recent_data and len(recent_data) > 0:
                        # We have price data, so treat as actively trading
                        logger.info(f"Symbol {symbol} marked as not actively trading but has price data - proceeding")
                        return True
                    else:
                        # No price data available, skip this symbol
                        self._non_trading_symbols.add(symbol)
                        return False
                except Exception:
                    # If we can't check price data, assume it might be trading
                    return True
            return True
        except Exception:
            # If we can't determine, assume it might be trading
            return True
    
    def _get_cache_key(self, prefix: str, *args) -> str:
        """Generate cache key from arguments."""
        key_string = f"chart_service:{prefix}:{':'.join(str(arg) for arg in args)}"
        return hashlib.md5(key_string.encode()).hexdigest()
    
    def _get_cached_data(self, cache_key: str) -> Optional[Any]:
        """Get data from cache."""
        if isinstance(self._cache, dict):
            return self._cache.get(cache_key)
        else:
            return self._cache.get(cache_key)
    
    def _set_cached_data(self, cache_key: str, data: Any, ttl: int = 900):
        """Set data in cache with TTL."""
        if isinstance(self._cache, dict):
            self._cache[cache_key] = data
        else:
            self._cache.set(cache_key, data, ttl)
    
    def compare_assets(self, symbols: List[str], base_currency: str = 'USD', 
                      include_dividends: bool = True, period: str = '1Y',
                      normalize_mode: str = 'index100') -> Dict[str, Any]:
        """
        Compare multiple assets with server-driven charting.
        
        Args:
            symbols: List of asset symbols
            base_currency: Base currency for normalization
            include_dividends: Whether to include dividends in returns
            period: Period preset (1M, 3M, 6M, YTD, 1Y, 3Y, 5Y, 10Y, MAX)
            normalize_mode: Normalization mode (index100, percent_change)
            
        Returns:
            Dictionary with comparison results including aggregated chart data
        """
        try:
            logger.info(f"compare_assets called with symbols: {symbols}, normalize_mode: {normalize_mode} (type: {type(normalize_mode)})")
            # Check cache first with optimized strategy
            symbols_key = sorted(symbols)  # Sort for consistent cache key
            # Temporarily disable caching to debug
            cached_result = None  # self._get_cached_data_optimized(symbols_key, base_currency, include_dividends, period, normalize_mode)
            if cached_result:
                logger.info(f"Cache hit for comparison: {symbols_key}")
                return cached_result
            
            # Parse parameters
            period_preset = PeriodPreset(period)
            normalize_mode_enum = NormalizeMode(normalize_mode)
            
            logger.info(f"Parsed parameters - period_preset: {type(period_preset)}, normalize_mode_enum: {type(normalize_mode_enum)}")
            
            # Create asset instances
            assets = AssetFactory.create_assets(symbols)
            
            # Debug: Check asset creation
            logger.info(f"Created {len(assets)} assets for symbols: {symbols}")
            for i, asset in enumerate(assets):
                logger.info(f"Asset {i}: {asset.symbol} - {type(asset)}")
            
            # Get date range for the period
            start_date, end_date = self._get_date_range(period_preset)
            
            # Determine granularity based on period
            granularity = self._determine_granularity(period_preset)
            logger.info(f"Determined granularity: {type(granularity)}, value: {getattr(granularity, 'value', 'NO_VALUE_ATTR')}")
            
            # Get raw price data for all assets in parallel
            asset_data, failed_symbols = self._get_raw_price_data_parallel(
                assets, start_date, end_date, include_dividends
            )
            
            if not asset_data:
                return {
                    'error': 'No data available for any of the provided symbols',
                    'failed_symbols': failed_symbols
                }
            
            # Process data in streamlined pipeline: normalize + aggregate + reduce + normalize for comparison
            chart_data = self._process_data_streamlined(asset_data, base_currency, granularity, normalize_mode_enum)
            
            # Calculate metrics
            metrics = self._calculate_metrics(chart_data, period_preset, asset_data)
            
            # Calculate correlation matrix
            correlation_matrix = self._calculate_correlation_matrix(chart_data, symbols)
            
            result = {
                'success': True,
                'symbols': symbols,
                'period': period,
                'normalize_mode': normalize_mode,
                'granularity': granularity.value,
                'chart_data': chart_data,
                'metrics': metrics,
                'correlation_matrix': correlation_matrix,
                'failed_symbols': failed_symbols,
                'successful_symbols': list(asset_data.keys()),
                'assets': self._get_asset_info(asset_data, base_currency)
            }
            
            logger.info(f"Comparison result prepared with {len(metrics)} metrics and {len(result['assets'])} assets")
            
            # Cache the result with optimized strategy
            self._set_cached_data_optimized(result, symbols_key, base_currency, include_dividends, period, normalize_mode)
            
            return result
            
        except Exception as e:
            logger.error(f"Error in chart service: {e}")
            return {'error': str(e)}
    
    def _get_raw_price_data_parallel(self, assets: List[BaseAsset], start_date: date, 
                                   end_date: date, include_dividends: bool) -> Tuple[Dict[str, Any], List[str]]:
        """
        Load price data for multiple assets in parallel.
        
        Args:
            assets: List of asset instances
            start_date: Start date for data
            end_date: End date for data
            include_dividends: Whether to include dividends
            
        Returns:
            Tuple of (asset_data_dict, failed_symbols_list)
        """
        asset_data = {}
        failed_symbols = []
        
        def load_asset_data(asset):
            """Load data for a single asset."""
            try:
                # Check if symbol is actively trading before attempting data fetch
                if not self._is_symbol_actively_trading(asset):
                    logger.info(f"Symbol {asset.symbol} is not actively trading - skipping data fetch")
                    return asset.symbol, None
                
                logger.info(f"Getting data for {asset.symbol} (type: {asset.asset_type.value})")
                raw_data = self._get_raw_price_data(asset, start_date, end_date, include_dividends)
                if raw_data:
                    logger.info(f"Successfully got {len(raw_data)} data points for {asset.symbol}")
                    return asset.symbol, {
                        'asset': asset,
                        'raw_data': raw_data
                    }
                else:
                    logger.warning(f"No data available for {asset.symbol}")
                    return asset.symbol, None
            except Exception as e:
                logger.error(f"Error getting data for {asset.symbol}: {e}", exc_info=True)
                return asset.symbol, None
        
        # Use ThreadPoolExecutor for parallel loading
        max_workers = min(len(assets), 3)  # Limit to 3 concurrent requests to avoid overwhelming the API
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all tasks
            future_to_asset = {executor.submit(load_asset_data, asset): asset for asset in assets}
            
            # Collect results as they complete
            for future in concurrent.futures.as_completed(future_to_asset):
                try:
                    symbol, data = future.result()
                    if data:
                        asset_data[symbol] = data
                    else:
                        failed_symbols.append(symbol)
                except Exception as e:
                    asset = future_to_asset[future]
                    logger.error(f"Error loading asset data for {asset.symbol}: {e}")
                    failed_symbols.append(asset.symbol)
        
        logger.info(f"Parallel loading completed: {len(asset_data)} successful, {len(failed_symbols)} failed")
        return asset_data, failed_symbols
    
    def _get_cached_data_optimized(self, symbols: List[str], base_currency: str, 
                                 include_dividends: bool, period: str, normalize_mode: str) -> Optional[Dict[str, Any]]:
        """
        Get cached data with optimized cache key strategy.
        
        Args:
            symbols: List of symbols
            base_currency: Base currency
            include_dividends: Whether dividends are included
            period: Time period
            normalize_mode: Normalization mode
            
        Returns:
            Cached data or None
        """
        try:
            # Try multiple cache keys for better hit rates
            cache_keys = self._generate_cache_keys(symbols, base_currency, include_dividends, period, normalize_mode)
            
            for cache_key in cache_keys:
                cached_data = self._get_cached_data(cache_key)
                if cached_data:
                    logger.info(f"Cache hit with key: {cache_key}")
                    return cached_data
            
            return None
            
        except Exception as e:
            logger.error(f"Error in optimized cache lookup: {e}")
            return None
    
    def _generate_cache_keys(self, symbols: List[str], base_currency: str, 
                           include_dividends: bool, period: str, normalize_mode: str) -> List[str]:
        """
        Generate multiple cache keys for better hit rates.
        
        Args:
            symbols: List of symbols
            base_currency: Base currency
            include_dividends: Whether dividends are included
            period: Time period
            normalize_mode: Normalization mode
            
        Returns:
            List of cache keys to try
        """
        cache_keys = []
        symbols_key = '_'.join(sorted(symbols))
        
        # Primary cache key (exact match)
        primary_key = self._get_cache_key(
            'compare_v6', 
            symbols_key, 
            base_currency, 
            include_dividends, 
            period, 
            normalize_mode
        )
        cache_keys.append(primary_key)
        
        # Broader cache keys for partial matches
        if len(symbols) >= 2:
            # Try with broader period matches
            if period in ['1Y', '3Y', '5Y']:
                broader_period = 'Y'  # Group all year-based periods
                broader_key = self._get_cache_key(
                    'compare_v6', 
                    symbols_key, 
                    base_currency, 
                    include_dividends, 
                    broader_period, 
                    normalize_mode
                )
                cache_keys.append(broader_key)
        
        # Try individual asset cache keys
        for symbol in symbols:
            individual_key = self._get_cache_key(
                'compare_v6', 
                symbol, 
                base_currency, 
                include_dividends, 
                period, 
                normalize_mode
            )
            cache_keys.append(individual_key)
        
        return cache_keys
    
    def _set_cached_data_optimized(self, data: Dict[str, Any], symbols: List[str], 
                                  base_currency: str, include_dividends: bool, 
                                  period: str, normalize_mode: str, ttl: int = 900) -> None:
        """
        Set cached data with optimized cache key strategy.
        
        Args:
            data: Data to cache
            symbols: List of symbols
            base_currency: Base currency
            include_dividends: Whether dividends are included
            period: Time period
            normalize_mode: Normalization mode
            ttl: Time to live in seconds
        """
        try:
            # Generate cache keys
            cache_keys = self._generate_cache_keys(symbols, base_currency, include_dividends, period, normalize_mode)
            
            # Cache with multiple keys for better hit rates
            for cache_key in cache_keys:
                self._set_cached_data(cache_key, data, ttl)
            
            logger.info(f"Cached data with {len(cache_keys)} keys")
            
        except Exception as e:
            logger.error(f"Error in optimized cache setting: {e}")
    
    def _process_data_streamlined(self, asset_data: Dict[str, Any], base_currency: str, 
                                granularity: Granularity, normalize_mode: NormalizeMode) -> Dict[str, Any]:
        """
        Streamlined data processing pipeline that combines normalization, aggregation, 
        reduction, and comparison normalization in optimized passes.
        
        Args:
            asset_data: Raw asset data
            base_currency: Base currency for normalization
            granularity: Data granularity
            normalize_mode: Normalization mode for comparison
            
        Returns:
            Processed chart data ready for comparison
        """
        try:
            processed_data = {}
            
            # Pre-calculate currency conversion rates for batch processing
            currency_rates_cache = {}
            
            for symbol, data in asset_data.items():
                asset = data['asset']
                raw_data = data['raw_data']
                
                if not raw_data:
                    continue
                
                # Get currency conversion rates in batch if needed
                if asset.currency and asset.currency != base_currency:
                    dates = [price.get('date') for price in raw_data if price.get('date')]
                    if dates:
                        cache_key = f"{asset.currency}:{base_currency}:{min(dates)}:{max(dates)}"
                        if cache_key not in currency_rates_cache:
                            currency_rates_cache[cache_key] = self.currency_converter.get_historical_rates_batch(
                                asset.currency, base_currency, min(dates), max(dates)
                            )
                
                # Process data in single pass: normalize + aggregate + reduce
                processed_prices = []
                current_period_data = []
                
                for price in raw_data:
                    # Normalize currency
                    normalized_price = self._normalize_price_currency_optimized(
                        price, asset, base_currency, currency_rates_cache
                    )
                    if not normalized_price:
                        continue
                    
                    # Add to current period
                    current_period_data.append(normalized_price)
                    
                    # Check if we should aggregate this period
                    if self._should_aggregate_period(current_period_data, granularity):
                        aggregated = self._aggregate_period_data(current_period_data)
                        processed_prices.append(aggregated)
                        current_period_data = []
                
                # Add remaining data
                if current_period_data:
                    aggregated = self._aggregate_period_data(current_period_data)
                    processed_prices.append(aggregated)
                
                # Reduce data points to target ~180 points
                if len(processed_prices) > 180:
                    processed_prices = self._reduce_data_points_single(processed_prices, target_points=180)
                
                processed_data[symbol] = processed_prices
            
            # Normalize for comparison in final pass
            chart_data = self._normalize_for_comparison_streamlined(processed_data, normalize_mode)
            
            logger.info(f"Streamlined processing completed for {len(processed_data)} assets")
            return chart_data
            
        except Exception as e:
            logger.error(f"Error in streamlined data processing: {e}")
            return {}
    
    def _normalize_price_currency_optimized(self, price: Dict[str, Any], asset: BaseAsset, 
                                          base_currency: str, currency_rates_cache: Dict[str, Dict[str, Decimal]]) -> Optional[Dict[str, Any]]:
        """Optimized currency normalization using pre-cached rates."""
        try:
            # Ensure price is a dictionary
            if not isinstance(price, dict):
                return None
            
            # Get the price value (prefer adjusted close if available)
            price_value = price.get('adjClose') or price.get('close') or price.get('price')
            if price_value is None:
                return None
            
            # Ensure price_value is a valid number
            try:
                price_value = float(price_value)
                if price_value <= 0:
                    return None
            except (ValueError, TypeError):
                return None
            
            # Convert to base currency if needed using cached rates
            if asset.currency and asset.currency != base_currency:
                date_str = price.get('date')
                if date_str:
                    cache_key = f"{asset.currency}:{base_currency}:{date_str}"
                    # Find the cache entry that contains this date
                    forex_rate = None
                    for key, rates in currency_rates_cache.items():
                        if date_str in rates:
                            forex_rate = rates[date_str]
                            break
                    
                    if forex_rate is None:
                        logger.warning(f"No forex rate available for {asset.currency} to {base_currency} on {date_str}")
                        return None
                    
                    price_value = float(Decimal(str(price_value)) * forex_rate)
            
            # Create normalized price data
            normalized_price = price.copy()
            
            # Update price fields
            if 'adjClose' in price:
                normalized_price['adjClose'] = price_value
            elif 'close' in price:
                normalized_price['close'] = price_value
            elif 'price' in price:
                normalized_price['price'] = price_value
            else:
                normalized_price['close'] = price_value
            
            # Add currency conversion metadata
            if asset.currency != base_currency:
                normalized_price['original_currency'] = asset.currency
                normalized_price['converted_currency'] = base_currency
            
            return normalized_price
            
        except Exception as e:
            logger.warning(f"Error normalizing price currency: {e}")
            return None
    
    def _should_aggregate_period(self, period_data: List[Dict[str, Any]], granularity: Granularity) -> bool:
        """Check if current period data should be aggregated."""
        if not period_data:
            return False
        
        if granularity == Granularity.DAILY:
            return len(period_data) >= 1
        elif granularity == Granularity.WEEKLY:
            return len(period_data) >= 5  # ~1 week of daily data
        elif granularity == Granularity.MONTHLY:
            return len(period_data) >= 20  # ~1 month of daily data
        elif granularity == Granularity.QUARTERLY:
            return len(period_data) >= 60  # ~1 quarter of daily data
        
        return False
    
    def _aggregate_period_data(self, period_data: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Aggregate data for a single period."""
        if not period_data:
            return {}
        
        # Use the last date in the period
        last_price = period_data[-1]
        
        # Calculate aggregated values
        prices = []
        volumes = []
        
        for price_data in period_data:
            price_value = price_data.get('adjClose') or price_data.get('close') or price_data.get('price')
            if price_value:
                prices.append(float(price_value))
            
            volume = price_data.get('volume', 0)
            if volume:
                volumes.append(float(volume))
        
        if not prices:
            return last_price
        
        # Create aggregated data point
        aggregated = last_price.copy()
        aggregated['close'] = prices[-1]  # Use last price as close
        aggregated['open'] = prices[0] if len(prices) > 1 else prices[0]  # Use first price as open
        aggregated['high'] = max(prices)  # Highest price
        aggregated['low'] = min(prices)   # Lowest price
        aggregated['volume'] = sum(volumes) if volumes else 0
        
        return aggregated
    
    def _reduce_data_points_single(self, data_points: List[Dict[str, Any]], target_points: int = 180) -> List[Dict[str, Any]]:
        """Reduce data points to target number using sampling."""
        if len(data_points) <= target_points:
            return data_points
        
        # Use simple sampling to reduce points
        step = len(data_points) / target_points
        reduced_points = []
        
        for i in range(target_points):
            index = int(i * step)
            if index < len(data_points):
                reduced_points.append(data_points[index])
        
        return reduced_points
    
    def _normalize_for_comparison_streamlined(self, processed_data: Dict[str, Any], 
                                           normalize_mode: NormalizeMode) -> Dict[str, Any]:
        """Streamlined normalization for comparison."""
        try:
            chart_data = {}
            
            for symbol, prices in processed_data.items():
                if not prices:
                    continue
                
                # Sort by date
                sorted_prices = sorted(prices, key=lambda x: x.get('date', ''))
                
                if normalize_mode == NormalizeMode.INDEX_100:
                    # Normalize to index starting at 1000
                    first_price = sorted_prices[0].get('close') or sorted_prices[0].get('price', 1)
                    if first_price <= 0:
                        first_price = 1
                    
                    chart_points = []
                    for price_data in sorted_prices:
                        current_price = price_data.get('close') or price_data.get('price', first_price)
                        index_value = (current_price / first_price) * 1000
                        
                        chart_points.append(ChartDataPoint(
                            date=datetime.strptime(price_data.get('date'), '%Y-%m-%d').date() if isinstance(price_data.get('date'), str) else price_data.get('date'),
                            value=index_value,
                            raw_value=current_price
                        ))
                    
                    chart_data[symbol] = chart_points
                
                elif normalize_mode == NormalizeMode.PERCENT_CHANGE:
                    # Normalize to percentage change from start
                    first_price = sorted_prices[0].get('close') or sorted_prices[0].get('price', 1)
                    if first_price <= 0:
                        first_price = 1
                    
                    chart_points = []
                    for price_data in sorted_prices:
                        current_price = price_data.get('close') or price_data.get('price', first_price)
                        percent_change = ((current_price - first_price) / first_price) * 100
                        
                        chart_points.append(ChartDataPoint(
                            date=datetime.strptime(price_data.get('date'), '%Y-%m-%d').date() if isinstance(price_data.get('date'), str) else price_data.get('date'),
                            value=percent_change,
                            raw_value=current_price
                        ))
                    
                    chart_data[symbol] = chart_points
            
            return chart_data
            
        except Exception as e:
            logger.error(f"Error in streamlined comparison normalization: {e}")
            return {}
    
    def _get_date_range(self, period: PeriodPreset) -> Tuple[date, date]:
        """Get start and end dates for the given period."""
        today = date.today()
        
        if period == PeriodPreset.ONE_MONTH:
            return today - timedelta(days=30), today
        elif period == PeriodPreset.THREE_MONTHS:
            return today - timedelta(days=90), today
        elif period == PeriodPreset.SIX_MONTHS:
            return today - timedelta(days=180), today
        elif period == PeriodPreset.YEAR_TO_DATE:
            return date(today.year, 1, 1), today
        elif period == PeriodPreset.ONE_YEAR:
            return today - timedelta(days=365), today
        elif period == PeriodPreset.THREE_YEARS:
            return today - timedelta(days=1095), today
        elif period == PeriodPreset.FIVE_YEARS:
            return today - timedelta(days=1825), today
        elif period == PeriodPreset.TEN_YEARS:
            return today - timedelta(days=3650), today
        elif period == PeriodPreset.MAXIMUM:
            # For MAX, we'll get all available data
            return date(2000, 1, 1), today
        else:
            raise ValueError(f"Unknown period: {period}")
    
    def _determine_granularity(self, period: PeriodPreset) -> Granularity:
        """Determine appropriate granularity based on period length."""
        if period in [PeriodPreset.ONE_MONTH, PeriodPreset.THREE_MONTHS, PeriodPreset.SIX_MONTHS]:
            return Granularity.DAILY
        elif period in [PeriodPreset.YEAR_TO_DATE, PeriodPreset.ONE_YEAR, PeriodPreset.THREE_YEARS]:
            return Granularity.WEEKLY
        elif period in [PeriodPreset.FIVE_YEARS, PeriodPreset.TEN_YEARS]:
            return Granularity.MONTHLY
        elif period == PeriodPreset.MAXIMUM:
            return Granularity.MONTHLY  # Could be quarterly for very long history
        else:
            return Granularity.DAILY
    
    def _get_raw_price_data(self, asset: BaseAsset, start_date: date, 
                           end_date: date, include_dividends: bool) -> List[Dict[str, Any]]:
        """Get raw price data for an asset with caching."""
        try:
            # Check if symbol is actively trading
            if not self._is_symbol_actively_trading(asset):
                logger.info(f"Symbol {asset.symbol} is not actively trading - no price data available")
                return []
            
            # Check cache for raw data
            cache_key = self._get_cache_key(
                'raw_data',
                asset.symbol,
                start_date.isoformat(),
                end_date.isoformat(),
                include_dividends,
                'v5'  # Version to bust cache after fixing data sorting
            )
            
            cached_data = self._get_cached_data(cache_key)
            if cached_data:
                logger.info(f"Cache hit for raw data: {asset.symbol}")
                return cached_data
            
            # Calculate days for the period
            days = (end_date - start_date).days
            
            # Get price history using the asset's method
            raw_prices = asset.get_price_history(days=days, include_dividends=include_dividends)
            
            # Debug: Check what we got
            logger.info(f"Raw prices type for {asset.symbol}: {type(raw_prices)}")
            if isinstance(raw_prices, str):
                logger.error(f"get_price_history returned string for {asset.symbol}: {raw_prices[:100]}...")
                return []
            
            if not raw_prices:
                # Check if symbol is actively trading to provide better error message
                quote = asset.get_quote()
                if quote and quote.get('isActivelyTrading') is False:
                    logger.info(f"No price data for {asset.symbol} - symbol is not actively trading")
                else:
                    logger.warning(f"No price data available for {asset.symbol}")
                return []
            
            # Ensure we have a list of dictionaries
            if not isinstance(raw_prices, list):
                logger.error(f"Expected list, got {type(raw_prices)} for {asset.symbol}")
                return []
            
            if raw_prices and not isinstance(raw_prices[0], dict):
                logger.error(f"Expected list of dicts, got list of {type(raw_prices[0])} for {asset.symbol}")
                return []
            
            # Filter by date range and validate data quality
            filtered_prices = []
            for price in raw_prices:
                # Skip if price is not a dictionary
                if not isinstance(price, dict):
                    logger.warning(f"Skipping non-dict price data for {asset.symbol}: {type(price)}")
                    continue
                
                # Skip if essential fields are missing or None
                price_date = self._parse_date(price.get('date'))
                if not price_date:
                    logger.warning(f"Skipping price with invalid date for {asset.symbol}: {price.get('date')}")
                    continue
                
                # Check if we have valid price data
                price_value = price.get('adjClose') or price.get('close') or price.get('price')
                if price_value is None:
                    logger.warning(f"Skipping price with None value for {asset.symbol} on {price_date}")
                    continue
                
                # Only include if date is in range
                if start_date <= price_date <= end_date:
                    filtered_prices.append(price)
            
            # Cache raw data for 1 hour
            self._set_cached_data(cache_key, filtered_prices, ttl=3600)
            
            return filtered_prices
            
        except Exception as e:
            logger.error(f"Error getting raw price data for {asset.symbol}: {e}")
            return []
    
    def _parse_date(self, date_str: str) -> Optional[date]:
        """Parse date string to date object."""
        if isinstance(date_str, date):
            return date_str
        
        try:
            if isinstance(date_str, datetime):
                return date_str.date()
            
            # Try different date formats
            for fmt in ['%Y-%m-%d', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%dT%H:%M:%S.%f']:
                try:
                    return datetime.strptime(date_str, fmt).date()
                except ValueError:
                    continue
            
            return None
        except Exception:
            return None
    
    def _normalize_asset_data(self, asset_data: Dict[str, Any], 
                             base_currency: str) -> Dict[str, Any]:
        """Normalize asset data to base currency."""
        normalized = {}
        
        for symbol, data in asset_data.items():
            asset = data['asset']
            raw_data = data['raw_data']
            
            # Convert prices to base currency
            normalized_prices = []
            for price in raw_data:
                try:
                    # Ensure price is a dictionary
                    if not isinstance(price, dict):
                        logger.warning(f"Price data is not a dict for {symbol}: {type(price)}")
                        continue
                    
                    # Get the price value (prefer adjusted close if available)
                    price_value = price.get('adjClose') or price.get('close') or price.get('price')
                    if price_value is None:
                        logger.warning(f"Skipping price with None value for {symbol}")
                        continue
                    
                    # Ensure price_value is a valid number
                    try:
                        price_value = float(price_value)
                        if price_value <= 0:
                            logger.warning(f"Skipping price with invalid value for {symbol}: {price_value}")
                            continue
                    except (ValueError, TypeError):
                        logger.warning(f"Skipping price with non-numeric value for {symbol}: {price_value}")
                        continue
                    
                    # Convert to base currency if needed using smart conversion
                    if asset.currency and asset.currency != base_currency:
                        converted_price = self.currency_converter.convert_amount(
                            Decimal(str(price_value)), asset.currency, base_currency, price.get('date')
                        )
                        if converted_price is None:
                            logger.warning(f"Currency conversion failed for {symbol}: {asset.currency} to {base_currency}")
                            continue
                        price_value = float(converted_price)
                    
                    # Handle different data structures for different asset types
                    if asset.asset_type.value in ['cryptocurrency', 'commodity']:
                        # Cryptocurrency and commodity data typically only has 'price' field
                        normalized_price = {
                            'date': price.get('date'),
                            'close': price_value,
                            'open': price_value,  # Use price as fallback for missing OHLC
                            'high': price_value,
                            'low': price_value,
                            'volume': price.get('volume', 0)
                        }
                    else:
                        # Standard OHLC data for stocks, ETFs, etc.
                        # Convert OHLC values to base currency if needed
                        open_price = price.get('open')
                        high_price = price.get('high')
                        low_price = price.get('low')
                        
                        if asset.currency and asset.currency != base_currency:
                            # Convert OHLC values to base currency
                            if open_price is not None:
                                try:
                                    converted_open = self.currency_converter.convert_amount(
                                        Decimal(str(open_price)), asset.currency, base_currency
                                    )
                                    open_price = float(converted_open) if converted_open is not None else None
                                except (ValueError, TypeError):
                                    open_price = None
                            
                            if high_price is not None:
                                try:
                                    converted_high = self.currency_converter.convert_amount(
                                        Decimal(str(high_price)), asset.currency, base_currency
                                    )
                                    high_price = float(converted_high) if converted_high is not None else None
                                except (ValueError, TypeError):
                                    high_price = None
                            
                            if low_price is not None:
                                try:
                                    converted_low = self.currency_converter.convert_amount(
                                        Decimal(str(low_price)), asset.currency, base_currency
                                    )
                                    low_price = float(converted_low) if converted_low is not None else None
                                except (ValueError, TypeError):
                                    low_price = None
                        
                        # Final validation - require at least close price, others are optional
                        if price_value is not None and price_value > 0:
                            # Use close price as fallback for missing OHLC values
                            if open_price is None or open_price <= 0:
                                open_price = price_value
                            if high_price is None or high_price <= 0:
                                high_price = price_value
                            if low_price is None or low_price <= 0:
                                low_price = price_value
                            
                            normalized_price = {
                                'date': price.get('date'),
                                'close': price_value,
                                'open': open_price,
                                'high': high_price,
                                'low': low_price,
                                'volume': price.get('volume', 0)
                            }
                        else:
                            logger.warning(f"Skipping price with invalid close value for {symbol}: close={price_value}")
                            continue
                    # Only append if normalized_price is valid
                    if normalized_price and isinstance(normalized_price, dict):
                        normalized_prices.append(normalized_price)
                    
                except Exception as e:
                    logger.warning(f"Error normalizing price for {symbol}: {e}")
                    continue
            
            # Only include if we have valid normalized prices
            if normalized_prices:
                normalized[symbol] = {
                    'asset': asset,
                    'normalized_data': normalized_prices
                }
            else:
                logger.warning(f"No valid normalized prices for {symbol}")
        
        return normalized
    
    def _aggregate_data(self, normalized_data: Dict[str, Any], 
                       granularity: Granularity) -> Dict[str, List[AggregatedDataPoint]]:
        """Aggregate data based on granularity."""
        aggregated = {}
        
        for symbol, data in normalized_data.items():
            normalized_prices = data['normalized_data']
            
            if granularity == Granularity.DAILY:
                # No aggregation needed for daily data, but we need to sort by date
                aggregated_points = []
                for price in normalized_prices:
                    date_val = self._parse_date(price['date'])
                    if date_val:
                        # Debug: Check price structure
                        logger.info(f"Daily price type for {symbol}: {type(price)}")
                        if isinstance(price, str):
                            logger.error(f"Daily price is string for {symbol}: {price[:100]}...")
                            continue
                        
                        # Ensure we have valid OHLC data before creating AggregatedDataPoint
                        open_price = price.get('open')
                        high_price = price.get('high')
                        low_price = price.get('low')
                        close_price = price['close']
                        
                        # Use close price as fallback for missing OHLC data, but only if close is not None
                        if close_price is not None:
                            if open_price is None:
                                open_price = close_price
                            if high_price is None:
                                high_price = close_price
                            if low_price is None:
                                low_price = close_price
                            
                            # Final safety check - ensure all values are valid numbers
                            try:
                                open_price = float(open_price) if open_price is not None else None
                                high_price = float(high_price) if high_price is not None else None
                                low_price = float(low_price) if low_price is not None else None
                                close_price = float(close_price) if close_price is not None else None
                                
                                # Only create if all values are valid
                                if (open_price is not None and high_price is not None and 
                                    low_price is not None and close_price is not None and
                                    open_price > 0 and high_price > 0 and low_price > 0 and close_price > 0):
                                    
                                    aggregated_points.append(AggregatedDataPoint(
                                        date=date_val,
                                        open_price=open_price,
                                        high_price=high_price,
                                        low_price=low_price,
                                        close_price=close_price,
                                        volume=price.get('volume', 0)
                                    ))
                                else:
                                    logger.warning(f"Skipping price with invalid OHLC values for {symbol} on {date_val}")
                            except (ValueError, TypeError) as e:
                                logger.warning(f"Skipping price with conversion error for {symbol} on {date_val}: {e}")
                                continue
                
                # Sort daily data points by date to ensure chronological order
                aggregated_points.sort(key=lambda point: point.date)
            
            elif granularity == Granularity.WEEKLY:
                aggregated_points = self._aggregate_weekly(normalized_prices)
            
            elif granularity == Granularity.MONTHLY:
                aggregated_points = self._aggregate_monthly(normalized_prices)
            
            elif granularity == Granularity.QUARTERLY:
                aggregated_points = self._aggregate_quarterly(normalized_prices)
            
            aggregated[symbol] = aggregated_points
        
        return aggregated
    
    def _aggregate_weekly(self, prices: List[Dict[str, Any]]) -> List[AggregatedDataPoint]:
        """Aggregate daily prices to weekly (end-of-week)."""
        weekly_data = {}
        
        for price in prices:
            date_val = self._parse_date(price['date'])
            if not date_val:
                continue
            
            # Skip prices with None close values
            if price.get('close') is None:
                continue
            
            # Get the end of the week (Sunday)
            days_since_sunday = date_val.weekday() + 1  # Monday = 0, Sunday = 6
            week_end = date_val + timedelta(days=6 - date_val.weekday())
            
            if week_end not in weekly_data:
                # Ensure we have valid OHLC data before creating the initial structure
                open_price = price.get('open')
                high_price = price.get('high')
                low_price = price.get('low')
                close_price = price['close']
                
                # Use close price as fallback for missing OHLC data, but only if close is not None
                if close_price is not None:
                    if open_price is None:
                        open_price = close_price
                    if high_price is None:
                        high_price = close_price
                    if low_price is None:
                        low_price = close_price
                    
                    weekly_data[week_end] = {
                        'open': open_price,
                        'high': high_price,
                        'low': low_price,
                        'close': close_price,
                        'volume': price.get('volume', 0)
                    }
            else:
                # Update OHLC for the week
                week_data = weekly_data[week_end]
                current_high = price.get('high')
                current_low = price.get('low')
                current_close = price['close']
                
                # Only update if we have valid data
                if current_close is not None:
                    # Handle None values in max/min operations
                    if current_high is not None and week_data['high'] is not None:
                        week_data['high'] = max(week_data['high'], current_high)
                    elif current_high is not None:
                        week_data['high'] = current_high
                    
                    if current_low is not None and week_data['low'] is not None:
                        week_data['low'] = min(week_data['low'], current_low)
                    elif current_low is not None:
                        week_data['low'] = current_low
                    
                    week_data['close'] = current_close  # Last close of the week
                    week_data['volume'] += price.get('volume', 0)
        
        # Convert to AggregatedDataPoint objects
        aggregated_points = []
        for week_end, data in sorted(weekly_data.items()):
            # Validate that we have valid OHLC data
            if (data['open'] is not None and data['high'] is not None and 
                data['low'] is not None and data['close'] is not None):
                aggregated_points.append(AggregatedDataPoint(
                    date=week_end,
                    open_price=data['open'],
                    high_price=data['high'],
                    low_price=data['low'],
                    close_price=data['close'],
                    volume=data['volume']
                ))
        
        return aggregated_points
    
    def _aggregate_monthly(self, prices: List[Dict[str, Any]]) -> List[AggregatedDataPoint]:
        """Aggregate daily prices to monthly (end-of-month)."""
        monthly_data = {}
        
        for price in prices:
            date_val = self._parse_date(price['date'])
            if not date_val:
                continue
            
            # Skip prices with None close values
            if price.get('close') is None:
                continue
            
            # Get the end of the month
            if date_val.month == 12:
                month_end = date(date_val.year + 1, 1, 1) - timedelta(days=1)
            else:
                month_end = date(date_val.year, date_val.month + 1, 1) - timedelta(days=1)
            
            if month_end not in monthly_data:
                # Ensure we have valid OHLC data before creating the initial structure
                open_price = price.get('open')
                high_price = price.get('high')
                low_price = price.get('low')
                close_price = price['close']
                
                # Use close price as fallback for missing OHLC data, but only if close is not None
                if close_price is not None:
                    if open_price is None:
                        open_price = close_price
                    if high_price is None:
                        high_price = close_price
                    if low_price is None:
                        low_price = close_price
                    
                    monthly_data[month_end] = {
                        'open': open_price,
                        'high': high_price,
                        'low': low_price,
                        'close': close_price,
                        'volume': price.get('volume', 0)
                    }
            else:
                # Update OHLC for the month
                month_data = monthly_data[month_end]
                current_high = price.get('high')
                current_low = price.get('low')
                current_close = price['close']
                
                # Only update if we have valid data
                if current_close is not None:
                    # Handle None values in max/min operations
                    if current_high is not None and month_data['high'] is not None:
                        month_data['high'] = max(month_data['high'], current_high)
                    elif current_high is not None:
                        month_data['high'] = current_high
                    
                    if current_low is not None and month_data['low'] is not None:
                        month_data['low'] = min(month_data['low'], current_low)
                    elif current_low is not None:
                        month_data['low'] = current_low
                    
                    month_data['close'] = current_close  # Last close of the month
                    month_data['volume'] += price.get('volume', 0)
        
        # Convert to AggregatedDataPoint objects
        aggregated_points = []
        for month_end, data in sorted(monthly_data.items()):
            # Validate that we have valid OHLC data
            if (data['open'] is not None and data['high'] is not None and 
                data['low'] is not None and data['close'] is not None):
                aggregated_points.append(AggregatedDataPoint(
                    date=month_end,
                    open_price=data['open'],
                    high_price=data['high'],
                    low_price=data['low'],
                    close_price=data['close'],
                    volume=data['volume']
                ))
        
        return aggregated_points
    
    def _aggregate_quarterly(self, prices: List[Dict[str, Any]]) -> List[AggregatedDataPoint]:
        """Aggregate daily prices to quarterly (end-of-quarter)."""
        quarterly_data = {}
        
        for price in prices:
            date_val = self._parse_date(price['date'])
            if not date_val:
                continue
            
            # Skip prices with None close values
            if price.get('close') is None:
                continue
            
            # Get the end of the quarter
            quarter = (date_val.month - 1) // 3 + 1
            if quarter == 4:
                quarter_end = date(date_val.year + 1, 1, 1) - timedelta(days=1)
            else:
                quarter_end = date(date_val.year, quarter * 3 + 1, 1) - timedelta(days=1)
            
            if quarter_end not in quarterly_data:
                # Ensure we have valid OHLC data before creating the initial structure
                open_price = price.get('open')
                high_price = price.get('high')
                low_price = price.get('low')
                close_price = price['close']
                
                # Use close price as fallback for missing OHLC data, but only if close is not None
                if close_price is not None:
                    if open_price is None:
                        open_price = close_price
                    if high_price is None:
                        high_price = close_price
                    if low_price is None:
                        low_price = close_price
                    
                    quarterly_data[quarter_end] = {
                        'open': open_price,
                        'high': high_price,
                        'low': low_price,
                        'close': close_price,
                        'volume': price.get('volume', 0)
                    }
            else:
                # Update OHLC for the quarter
                quarter_data = quarterly_data[quarter_end]
                current_high = price.get('high')
                current_low = price.get('low')
                current_close = price['close']
                
                # Only update if we have valid data
                if current_close is not None:
                    # Handle None values in max/min operations
                    if current_high is not None and quarter_data['high'] is not None:
                        quarter_data['high'] = max(quarter_data['high'], current_high)
                    elif current_high is not None:
                        quarter_data['high'] = current_high
                    
                    if current_low is not None and quarter_data['low'] is not None:
                        quarter_data['low'] = min(quarter_data['low'], current_low)
                    elif current_low is not None:
                        quarter_data['low'] = current_low
                    
                    quarter_data['close'] = current_close  # Last close of the quarter
                    quarter_data['volume'] += price.get('volume', 0)
        
        # Convert to AggregatedDataPoint objects
        aggregated_points = []
        for quarter_end, data in sorted(quarterly_data.items()):
            # Validate that we have valid OHLC data
            if (data['open'] is not None and data['high'] is not None and 
                data['low'] is not None and data['close'] is not None):
                aggregated_points.append(AggregatedDataPoint(
                    date=quarter_end,
                    open_price=data['open'],
                    high_price=data['high'],
                    low_price=data['low'],
                    close_price=data['close'],
                    volume=data['volume']
                ))
        
        return aggregated_points
    
    def _reduce_data_points(self, aggregated_data: Dict[str, List[AggregatedDataPoint]], 
                           target_points: int = 180) -> Dict[str, List[AggregatedDataPoint]]:
        """Reduce data points to target number using LTTB algorithm."""
        reduced = {}
        
        for symbol, points in aggregated_data.items():
            if len(points) <= target_points:
                reduced[symbol] = points
            else:
                # Use LTTB (Largest Triangle Three Buckets) algorithm
                reduced[symbol] = self._lttb_downsample(points, target_points)
        
        return reduced
    
    def _lttb_downsample(self, points: List[AggregatedDataPoint], 
                        target_points: int) -> List[AggregatedDataPoint]:
        """Downsample using Largest Triangle Three Buckets algorithm."""
        if len(points) <= target_points:
            return points
        
        # Always keep first and last points
        result = [points[0]]
        
        # Calculate bucket size
        bucket_size = (len(points) - 2) / (target_points - 2)
        
        # Safety check for bucket_size
        if bucket_size is None or bucket_size <= 0:
            logger.warning(f"Invalid bucket_size: {bucket_size}, len(points)={len(points)}, target_points={target_points}")
            return points  # Return original points if bucket calculation fails
        
        for i in range(1, target_points - 1):
            # Calculate bucket boundaries
            bucket_start = int(i * bucket_size) + 1
            bucket_end = int((i + 1) * bucket_size) + 1
            
            # Safety check for bucket boundaries
            if bucket_start is None or bucket_end is None or len(points) is None:
                logger.warning(f"Invalid bucket boundaries: bucket_start={bucket_start}, bucket_end={bucket_end}, len(points)={len(points)}")
                continue
            
            # Find the point with the largest triangle area
            max_area = 0
            selected_point = points[bucket_start]
            
            # Safety check for bucket_end and len(points)
            safe_bucket_end = min(bucket_end, len(points))
            if safe_bucket_end is None:
                logger.warning(f"safe_bucket_end is None: bucket_end={bucket_end}, len(points)={len(points)}")
                continue
            
            for j in range(bucket_start, safe_bucket_end):
                # Calculate safe indices for triangle area calculation
                safe_end_index = min(bucket_end, len(points) - 1)
                if safe_end_index is None:
                    continue
                
                # Skip points with None close_price values
                if (result[-1].close_price is None or 
                    points[j].close_price is None or 
                    points[safe_end_index].close_price is None):
                    continue
                
                # Calculate triangle area
                area = self._triangle_area(
                    result[-1].close_price, result[-1].date,
                    points[j].close_price, points[j].date,
                    points[safe_end_index].close_price,
                    points[safe_end_index].date
                )
                
                if area is not None and area > max_area:
                    max_area = area
                    selected_point = points[j]
            
            result.append(selected_point)
        
        result.append(points[-1])
        return result
    
    def _triangle_area(self, x1: float, y1: date, x2: float, y2: date, 
                      x3: float, y3: date) -> float:
        """Calculate triangle area for LTTB algorithm."""
        # Check for None values
        if x1 is None or x2 is None or x3 is None:
            return None
        
        # Convert dates to numeric values for calculation
        d1 = (y1 - date(2000, 1, 1)).days
        d2 = (y2 - date(2000, 1, 1)).days
        d3 = (y3 - date(2000, 1, 1)).days
        
        return abs((x1 * (d2 - d3) + x2 * (d3 - d1) + x3 * (d1 - d2)) / 2)
    
    def _normalize_for_comparison(self, aggregated_data: Dict[str, List[AggregatedDataPoint]], 
                                 normalize_mode: NormalizeMode) -> Dict[str, List[ChartDataPoint]]:
        """Normalize data for comparison based on the selected mode."""
        chart_data = {}
        
        for symbol, points in aggregated_data.items():
            if not points:
                chart_data[symbol] = []
                continue
            
            # Find the common start date (first available data point)
            start_price = points[0].close_price
            if start_price is None or start_price == 0:
                chart_data[symbol] = []
                continue
            
            normalized_points = []
            for point in points:
                if point.close_price is None:
                    continue  # Skip points with None prices
                    
                if normalize_mode == NormalizeMode.INDEX_100:
                    # Normalize to start at 1000
                    normalized_value = (point.close_price / start_price) * 1000
                elif normalize_mode == NormalizeMode.PERCENT_CHANGE:
                    # Show percentage change from start
                    normalized_value = ((point.close_price - start_price) / start_price) * 100
                else:
                    normalized_value = point.close_price
                
                normalized_points.append(ChartDataPoint(
                    date=point.date,
                    value=normalized_value,
                    raw_value=point.close_price
                ))
            
            chart_data[symbol] = normalized_points
        
        return chart_data
    
    def _calculate_metrics(self, chart_data: Dict[str, List[ChartDataPoint]], 
                          period: PeriodPreset, asset_data: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
        """Calculate performance metrics for each asset."""
        logger.info(f"_calculate_metrics called with period type: {type(period)}, value: {getattr(period, 'value', 'NO_VALUE_ATTR')}")
        metrics = {}
        
        for symbol, points in chart_data.items():
            if not points:
                logger.warning(f"No chart data points for {symbol}")
                continue
            
            logger.info(f"Calculating metrics for {symbol} with {len(points)} data points")
            
            # Calculate basic metrics based on normalized values
            start_value = points[0].value
            end_value = points[-1].value
            
            # Calculate actual time period
            days = (points[-1].date - points[0].date).days
            years = days / 365.25
            
            # For percent_change mode, the values are already percentages
            # For index100 mode, we need to convert back to percentage change
            if start_value == 1000:  # index100 mode
                # Convert from index values to percentage change
                total_return = (end_value - start_value) / start_value
            else:  # percent_change mode
                # Values are already percentage changes from start (which is 0)
                total_return = end_value / 100.0  # Convert from percentage to decimal
            
            # Annualized return
            annualized_return = (1 + total_return) ** (1 / years) - 1 if years > 0 else 0
            
            # Calculate returns from normalized values
            returns = []
            for i in range(1, len(points)):
                if points[i].value is not None and points[i-1].value is not None and points[i-1].value != 0:
                    if start_value == 1000:  # index100 mode
                        # Calculate percentage change between index values
                        period_return = (points[i].value - points[i-1].value) / points[i-1].value
                    else:  # percent_change mode
                        # Calculate change in percentage points
                        period_return = (points[i].value - points[i-1].value) / 100.0
                    returns.append(period_return)
            
            if not returns:
                metrics[symbol] = {
                    'total_return': total_return,
                    'annualized_return': annualized_return,
                    'volatility': 0.0,
                    'sharpe_ratio': 0.0,
                    'max_drawdown': 0.0
                }
                continue
            
            # Determine data frequency based on period and granularity
            # For YTD, we need to be more careful about the frequency
            if period == PeriodPreset.YEAR_TO_DATE:
                # For YTD, calculate the actual frequency based on data points
                if len(points) > 1:
                    avg_days_between_points = days / (len(points) - 1)
                    if avg_days_between_points <= 2:
                        frequency = 252  # Daily data
                    elif avg_days_between_points <= 7:
                        frequency = 52   # Weekly data
                    elif avg_days_between_points <= 15:
                        frequency = 24   # Bi-weekly data
                    else:
                        frequency = 12   # Monthly data
                else:
                    frequency = 252
            else:
                # For other periods, use standard frequency based on granularity
                granularity = self._determine_granularity(period)
                if granularity == Granularity.DAILY:
                    frequency = 252
                elif granularity == Granularity.WEEKLY:
                    frequency = 52
                elif granularity == Granularity.MONTHLY:
                    frequency = 12
                else:
                    frequency = 4  # Quarterly
            
            # Calculate volatility (annualized)
            mean_return = sum(returns) / len(returns)
            variance = sum((r - mean_return) ** 2 for r in returns) / len(returns)
            volatility = math.sqrt(variance * frequency) if variance > 0 else 0
            
            # Calculate Sharpe ratio using currency-specific risk-free rate
            # Get the base currency from the asset data
            base_currency = 'USD'  # Default fallback
            if symbol in asset_data:
                asset = asset_data[symbol]['asset']
                base_currency = asset.currency
            
            # Get risk-free rate for the specific currency and period
            if period == PeriodPreset.YEAR_TO_DATE:
                risk_free_rate = self.risk_free_rate_service.get_risk_free_rate_for_ytd(base_currency)
            else:
                # For other periods, use the rate for the middle of the period
                middle_date = points[0].date + timedelta(days=days // 2)
                risk_free_rate = self.risk_free_rate_service.get_risk_free_rate(base_currency, middle_date)
            
            if volatility > 0:
                excess_return = annualized_return - risk_free_rate
                sharpe_ratio = excess_return / volatility
            else:
                sharpe_ratio = 0.0
            
            # Maximum drawdown
            max_drawdown = 0
            peak = start_value
            for point in points:
                if point.value is not None and point.value > peak:
                    peak = point.value
                if point.value is not None and peak != 0:
                    drawdown = (peak - point.value) / peak
                    if drawdown is not None and max_drawdown is not None:
                        max_drawdown = max(max_drawdown, drawdown)
                    elif drawdown is not None:
                        max_drawdown = drawdown
            
            metrics[symbol] = {
                'total_return': total_return,
                'annualized_return': annualized_return,
                'volatility': volatility,
                'sharpe_ratio': sharpe_ratio,
                'max_drawdown': max_drawdown
            }
            
            logger.info(f"Metrics calculated for {symbol}: total_return={total_return:.4f}, annualized_return={annualized_return:.4f}, volatility={volatility:.4f}, sharpe_ratio={sharpe_ratio:.4f}")
            logger.info(f"  Period: {period.value}, Data points: {len(points)}, Days: {days}, Frequency: {frequency}")
            logger.info(f"  Returns count: {len(returns)}, Mean return: {mean_return:.6f}, Variance: {variance:.6f}")
            logger.info(f"  Currency: {base_currency}, Risk-free rate: {risk_free_rate:.4f} ({risk_free_rate*100:.2f}%)")
        
        logger.info(f"Calculated metrics for {len(metrics)} symbols")
        return metrics
        
    def _get_asset_info(self, asset_data: Dict[str, Any], base_currency: str) -> Dict[str, Any]:
        """Get asset information for display."""
        assets_info = {}
        
        for symbol, data in asset_data.items():
            asset = data['asset']
            quote = asset.get_quote()
            
            # Debug: Check quote structure
            logger.info(f"Quote type for {symbol}: {type(quote)}")
            if isinstance(quote, str):
                logger.error(f"Quote is string for {symbol}: {quote[:100]}...")
                quote = None
            
            # Get current price
            current_price = asset.get_current_price()
            if current_price and asset.currency != base_currency:
                # Convert to base currency
                converted_price = self.currency_converter.convert_amount(
                    current_price, asset.currency, base_currency
                )
                if converted_price:
                    current_price = converted_price
            
            # Get market cap using the asset's method (which checks multiple field names)
            market_cap = asset.get_market_cap()
            if market_cap and asset.currency != base_currency:
                # Convert market cap to base currency
                converted_market_cap = self.currency_converter.convert_amount(
                    Decimal(str(market_cap)), asset.currency, base_currency
                )
                if converted_market_cap:
                    market_cap = int(converted_market_cap)
            
            assets_info[symbol] = {
                'name': asset.name,
                'asset_type': asset.asset_type.value,
                'current_price': float(current_price) if current_price else None,
                'market_cap': market_cap,
                'currency': base_currency,
                'original_currency': asset.currency,
                'exchange': asset.exchange
            }
        
        return assets_info
    
    def _calculate_correlation_matrix(self, chart_data: Dict[str, List[ChartDataPoint]], 
                                    symbols: List[str]) -> Dict[str, Dict[str, float]]:
        """Calculate correlation matrix between all pairs of assets."""
        correlation_matrix = {}
        
        # Only calculate correlations if we have at least 2 symbols
        if len(symbols) < 2:
            return correlation_matrix
        
        # Extract returns for each symbol
        symbol_returns = {}
        for symbol in symbols:
            if symbol in chart_data and chart_data[symbol]:
                points = chart_data[symbol]
                returns = []
                
                logger.info(f"Processing {symbol}: {len(points)} data points")
                
                # Calculate returns from normalized values
                for i in range(1, len(points)):
                    if (points[i].value is not None and 
                        points[i-1].value is not None and 
                        points[i-1].value != 0):
                        period_return = (points[i].value - points[i-1].value) / points[i-1].value
                        returns.append(period_return)
                
                logger.info(f"{symbol}: calculated {len(returns)} returns")
                
                if len(returns) >= 2:  # Need at least 2 returns for correlation
                    symbol_returns[symbol] = returns
                    logger.info(f"{symbol}: added to symbol_returns with {len(returns)} returns")
                else:
                    logger.warning(f"{symbol}: insufficient returns ({len(returns)}) for correlation calculation")
            else:
                logger.warning(f"{symbol}: no chart data available")
        
        logger.info(f"Symbols with sufficient returns: {list(symbol_returns.keys())}")
        
        # Calculate correlations between all pairs
        for i, symbol1 in enumerate(symbols):
            correlation_matrix[symbol1] = {}
            
            for j, symbol2 in enumerate(symbols):
                if i == j:
                    # Self-correlation is always 1.0
                    correlation_matrix[symbol1][symbol2] = 1.0
                elif symbol1 not in symbol_returns or symbol2 not in symbol_returns:
                    # If either symbol doesn't have enough data, correlation is 0.0
                    correlation_matrix[symbol1][symbol2] = 0.0
                    logger.info(f"{symbol1} -> {symbol2}: 0.0 (insufficient data)")
                else:
                    # Calculate correlation between the two return series
                    correlation = self._calculate_correlation(
                        symbol_returns[symbol1], 
                        symbol_returns[symbol2]
                    )
                    correlation_matrix[symbol1][symbol2] = correlation
                    logger.info(f"{symbol1} -> {symbol2}: {correlation:.6f}")
        
        logger.info(f"Correlation matrix calculated for {len(symbol_returns)} symbols")
        return correlation_matrix
    
    def _calculate_correlation(self, returns1: List[float], returns2: List[float]) -> float:
        """Calculate correlation coefficient between two return series."""
        try:
            if len(returns1) < 2 or len(returns2) < 2:
                return 0.0
            
            # Align the series to the minimum length
            min_length = min(len(returns1), len(returns2))
            returns1_aligned = returns1[-min_length:]
            returns2_aligned = returns2[-min_length:]
            
            # Calculate means
            mean1 = sum(returns1_aligned) / len(returns1_aligned)
            mean2 = sum(returns2_aligned) / len(returns2_aligned)
            
            # Calculate covariance and standard deviations
            covariance = 0.0
            variance1 = 0.0
            variance2 = 0.0
            
            for i in range(len(returns1_aligned)):
                diff1 = returns1_aligned[i] - mean1
                diff2 = returns2_aligned[i] - mean2
                
                covariance += diff1 * diff2
                variance1 += diff1 * diff1
                variance2 += diff2 * diff2
            
            # Normalize by degrees of freedom
            n = len(returns1_aligned)
            covariance /= (n - 1) if n > 1 else 1
            variance1 /= (n - 1) if n > 1 else 1
            variance2 /= (n - 1) if n > 1 else 1
            
            # Calculate standard deviations
            std1 = variance1 ** 0.5
            std2 = variance2 ** 0.5
            
            # Calculate correlation coefficient
            if std1 == 0 or std2 == 0:
                return 0.0
            
            correlation = covariance / (std1 * std2)
            
            # Clamp correlation to [-1, 1] range
            correlation = max(-1.0, min(1.0, correlation))
            
            return correlation
            
        except Exception as e:
            logger.error(f"Error calculating correlation: {e}")
            return 0.0


# Global service instance
_chart_service = None


def get_chart_service() -> ChartService:
    """Get the global chart service instance."""
    global _chart_service
    if _chart_service is None:
        _chart_service = ChartService()
    return _chart_service
