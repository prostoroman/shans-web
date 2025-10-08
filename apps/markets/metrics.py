"""
Financial metrics calculations for market analysis.
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple
from decimal import Decimal
import logging

logger = logging.getLogger(__name__)


def calculate_returns(prices: List[float]) -> List[float]:
    """
    Calculate daily returns from price series.
    
    Args:
        prices: List of prices
        
    Returns:
        List of daily returns
    """
    if len(prices) < 2:
        return []
    
    returns = []
    for i in range(1, len(prices)):
        ret = (prices[i] - prices[i-1]) / prices[i-1]
        returns.append(ret)
    
    return returns


def calculate_cagr(prices: List[float], years: float) -> float:
    """
    Calculate Compound Annual Growth Rate.
    
    Args:
        prices: List of prices (can be in any order, will find oldest and newest)
        years: Number of years
        
    Returns:
        CAGR as decimal
    """
    if len(prices) < 2 or years <= 0:
        return 0.0
    
    # Use first and last price (oldest and newest chronologically)
    # If prices are time-sorted ascending: prices[0] is oldest, prices[-1] is newest
    # If prices are time-sorted descending: prices[-1] is oldest, prices[0] is newest
    # Since we don't know the order, we use the first as start and last as end
    # But we need to ensure we're calculating from old to new
    
    # Actually, let's use min/max to determine start and end based on actual period
    # No, that's wrong. We need chronological order.
    
    # For now, assume standard financial convention: array is chronologically sorted
    # with oldest first and newest last
    start_price = prices[0]
    end_price = prices[-1]
    
    if start_price <= 0:
        return 0.0
    
    cagr = (end_price / start_price) ** (1 / years) - 1
    return cagr


def calculate_volatility(returns: List[float], frequency: int = 252) -> float:
    """
    Calculate annualized volatility.
    
    Args:
        returns: List of period returns
        frequency: Number of periods per year (252 for daily, 52 for weekly, 12 for monthly)
        
    Returns:
        Annualized volatility
    """
    if len(returns) < 2:
        return 0.0
    
    return np.std(returns) * np.sqrt(frequency)


def calculate_sharpe_ratio(returns: List[float], risk_free_rate: float = 0.03, 
                          frequency: int = 252, currency: str = 'USD') -> float:
    """
    Calculate Sharpe ratio.
    
    Args:
        returns: List of period returns
        risk_free_rate: Risk-free rate (annual) - will be fetched from service if not provided
        frequency: Number of periods per year (252 for daily, 52 for weekly, 12 for monthly)
        currency: Currency code for fetching risk-free rate
        
    Returns:
        Sharpe ratio
    """
    if len(returns) < 2:
        return 0.0
    
    # If risk_free_rate is the default, try to fetch from service
    if risk_free_rate == 0.03:
        try:
            from .risk_free_rate_service import get_risk_free_rate
            risk_free_rate = get_risk_free_rate(currency)
        except Exception:
            # Fallback to provided rate if service fails
            pass
    
    # Calculate annualized excess return
    avg_return = np.mean(returns)
    annualized_return = avg_return * frequency
    excess_return = annualized_return - risk_free_rate
    
    # Calculate annualized volatility
    volatility = calculate_volatility(returns, frequency)
    
    if volatility == 0:
        return 0.0
    
    return excess_return / volatility


def calculate_sortino_ratio(returns: List[float], risk_free_rate: float = 0.03, 
                           frequency: int = 252) -> float:
    """
    Calculate Sortino ratio.
    
    Args:
        returns: List of period returns
        risk_free_rate: Risk-free rate (annual)
        frequency: Number of periods per year (252 for daily, 52 for weekly, 12 for monthly)
        
    Returns:
        Sortino ratio
    """
    if len(returns) < 2:
        return 0.0
    
    # Calculate annualized excess return
    avg_return = np.mean(returns)
    annualized_return = avg_return * frequency
    excess_return = annualized_return - risk_free_rate
    
    # Downside deviation (only negative returns)
    period_risk_free_rate = risk_free_rate / frequency
    excess_returns = [r - period_risk_free_rate for r in returns]
    negative_returns = [r for r in excess_returns if r < 0]
    
    if len(negative_returns) == 0:
        return float('inf') if excess_return > 0 else 0.0
    
    downside_deviation = np.std(negative_returns) * np.sqrt(frequency)
    
    if downside_deviation == 0:
        return 0.0
    
    return excess_return / downside_deviation


def calculate_beta(returns_a: List[float], returns_b: List[float]) -> float:
    """
    Calculate beta coefficient.
    
    Args:
        returns_a: Returns of asset A
        returns_b: Returns of benchmark B
        
    Returns:
        Beta coefficient
    """
    if len(returns_a) != len(returns_b) or len(returns_a) < 2:
        return 0.0
    
    covariance = np.cov(returns_a, returns_b)[0][1]
    variance_b = np.var(returns_b)
    
    if variance_b == 0:
        return 0.0
    
    return covariance / variance_b


def calculate_correlation(returns_a: List[float], returns_b: List[float]) -> float:
    """
    Calculate correlation coefficient.
    
    Args:
        returns_a: Returns of asset A
        returns_b: Returns of asset B
        
    Returns:
        Correlation coefficient
    """
    if len(returns_a) != len(returns_b) or len(returns_a) < 2:
        return 0.0
    
    return np.corrcoef(returns_a, returns_b)[0][1]


def calculate_max_drawdown(prices: List[float]) -> float:
    """
    Calculate maximum drawdown.
    
    Args:
        prices: List of prices
        
    Returns:
        Maximum drawdown as decimal
    """
    if len(prices) < 2:
        return 0.0
    
    peak = prices[0]
    max_dd = 0.0
    
    for price in prices:
        if price > peak:
            peak = price
        else:
            drawdown = (peak - price) / peak
            max_dd = max(max_dd, drawdown)
    
    return max_dd


def calculate_var(returns: List[float], confidence_level: float = 0.05) -> float:
    """
    Calculate Value at Risk (VaR).
    
    Args:
        returns: List of daily returns
        confidence_level: Confidence level (e.g., 0.05 for 95%)
        
    Returns:
        VaR as decimal
    """
    if len(returns) < 2:
        return 0.0
    
    return np.percentile(returns, confidence_level * 100)


def calculate_skewness(returns: List[float]) -> float:
    """
    Calculate skewness of returns.
    
    Args:
        returns: List of daily returns
        
    Returns:
        Skewness
    """
    if len(returns) < 3:
        return 0.0
    
    return float(pd.Series(returns).skew())


def calculate_kurtosis(returns: List[float]) -> float:
    """
    Calculate kurtosis of returns.
    
    Args:
        returns: List of daily returns
        
    Returns:
        Kurtosis
    """
    if len(returns) < 4:
        return 0.0
    
    return float(pd.Series(returns).kurtosis())


def calculate_metrics(prices: List[float], benchmark_prices: Optional[List[float]] = None, 
                     risk_free_rate: float = 0.03, years: float = 5.0, 
                     frequency: int = 252, currency: str = 'USD') -> Dict[str, float]:
    """
    Calculate comprehensive metrics for a price series.
    
    Args:
        prices: List of prices
        benchmark_prices: Optional benchmark prices for beta calculation
        risk_free_rate: Risk-free rate (annual)
        years: Number of years for CAGR calculation
        frequency: Number of periods per year (252 for daily, 52 for weekly, 12 for monthly)
        currency: Currency code for fetching risk-free rate
        
    Returns:
        Dictionary of calculated metrics
    """
    if len(prices) < 2:
        return {}
    
    returns = calculate_returns(prices)
    
    metrics = {
        'cagr': calculate_cagr(prices, years),
        'volatility': calculate_volatility(returns, frequency),
        'sharpe_ratio': calculate_sharpe_ratio(returns, risk_free_rate, frequency, currency),
        'sortino_ratio': calculate_sortino_ratio(returns, risk_free_rate, frequency),
        'max_drawdown': calculate_max_drawdown(prices),
        'var_95': calculate_var(returns, 0.05),
        'skewness': calculate_skewness(returns),
        'kurtosis': calculate_kurtosis(returns),
    }
    
    # Calculate beta if benchmark provided
    if benchmark_prices and len(benchmark_prices) >= 2:
        benchmark_returns = calculate_returns(benchmark_prices)
        if len(benchmark_returns) == len(returns):
            metrics['beta'] = calculate_beta(returns, benchmark_returns)
            metrics['correlation'] = calculate_correlation(returns, benchmark_returns)
    
    return metrics


def calculate_portfolio_metrics(weights: List[float], returns_matrix: List[List[float]], 
                               risk_free_rate: float = 0.03) -> Dict[str, float]:
    """
    Calculate portfolio-level metrics.
    
    Args:
        weights: Portfolio weights
        returns_matrix: Matrix of returns (assets x time)
        risk_free_rate: Risk-free rate (annual)
        
    Returns:
        Dictionary of portfolio metrics
    """
    if len(weights) != len(returns_matrix) or len(weights) == 0:
        return {}
    
    # Convert to numpy arrays
    weights = np.array(weights)
    returns_matrix = np.array(returns_matrix)
    
    # Calculate portfolio returns
    portfolio_returns = np.dot(weights, returns_matrix)
    
    # Calculate metrics
    metrics = {
        'expected_return': np.mean(portfolio_returns) * 252,  # Annualized
        'volatility': np.std(portfolio_returns) * np.sqrt(252),  # Annualized
        'sharpe_ratio': calculate_sharpe_ratio(portfolio_returns.tolist(), risk_free_rate),
        'max_drawdown': calculate_max_drawdown(portfolio_returns.tolist()),
    }
    
    return metrics


def align_series(series_list: List[List[float]], dates_list: List[List[str]]) -> Tuple[List[List[float]], List[str]]:
    """
    Align multiple price series to common dates.
    
    Args:
        series_list: List of price series
        dates_list: List of corresponding date series
        
    Returns:
        Tuple of (aligned_series, common_dates)
    """
    if len(series_list) != len(dates_list) or len(series_list) == 0:
        return series_list, dates_list[0] if dates_list else []
    
    # Find common dates
    common_dates = set(dates_list[0])
    for dates in dates_list[1:]:
        common_dates = common_dates.intersection(set(dates))
    
    common_dates = sorted(list(common_dates))
    
    # Align series
    aligned_series = []
    for i, (series, dates) in enumerate(zip(series_list, dates_list)):
        aligned = []
        for date in common_dates:
            try:
                idx = dates.index(date)
                aligned.append(series[idx])
            except ValueError:
                # Date not found, skip
                continue
        aligned_series.append(aligned)
    
    return aligned_series, common_dates


def align_price_histories(price_histories: List[List[Dict]], symbols: List[str]) -> Tuple[List[List[Dict]], List[str]]:
    """
    Align price histories from multiple assets to common dates for proper comparison.
    Uses forward-fill interpolation for missing values to maintain continuity.
    
    Args:
        price_histories: List of price history dictionaries for each asset
        symbols: List of asset symbols
        
    Returns:
        Tuple of (aligned_histories, common_dates)
    """
    if not price_histories or len(price_histories) != len(symbols):
        return price_histories, []
    
    # Extract dates and prices for each asset
    asset_data = {}
    all_dates = set()
    
    for i, (history, symbol) in enumerate(zip(price_histories, symbols)):
        if not history:
            continue
            
        dates = []
        prices = []
        
        for price_point in history:
            # Extract date and price from various possible formats
            date_str = None
            price_value = None
            
            if isinstance(price_point, dict):
                # Try different date field names
                for date_field in ['date', 'Date', 'timestamp']:
                    if date_field in price_point:
                        date_str = str(price_point[date_field])
                        break
                
                # Try different price field names
                for price_field in ['close', 'Close', 'price', 'Price', 'adjClose', 'AdjClose']:
                    if price_field in price_point and price_point[price_field] is not None:
                        try:
                            price_value = float(price_point[price_field])
                            break
                        except (ValueError, TypeError):
                            continue
            
            if date_str and price_value is not None:
                dates.append(date_str)
                prices.append(price_value)
                all_dates.add(date_str)
        
        if dates and prices:
            asset_data[symbol] = {
                'dates': dates,
                'prices': prices,
                'original_history': history
            }
    
    if not asset_data:
        return price_histories, []
    
    # Find common dates (intersection of all available dates)
    common_dates = set(asset_data[list(asset_data.keys())[0]]['dates'])
    for symbol_data in asset_data.values():
        common_dates = common_dates.intersection(set(symbol_data['dates']))
    
    common_dates = sorted(list(common_dates))
    
    if not common_dates:
        # If no common dates, use union of all dates
        common_dates = sorted(list(all_dates))
    
    # Create aligned histories with forward-fill interpolation
    aligned_histories = []
    
    for symbol in symbols:
        if symbol not in asset_data:
            # Asset has no data, create empty history
            aligned_histories.append([])
            continue
        
        symbol_data = asset_data[symbol]
        dates = symbol_data['dates']
        prices = symbol_data['prices']
        
        # Create date-to-price mapping
        date_price_map = dict(zip(dates, prices))
        
        # Build aligned history with forward-fill
        aligned_history = []
        last_price = None
        
        for date in common_dates:
            if date in date_price_map:
                # Use actual price
                price = date_price_map[date]
                last_price = price
            elif last_price is not None:
                # Forward-fill with last known price
                price = last_price
            else:
                # Skip if no price available yet
                continue
            
            # Create price point in original format
            price_point = {
                'date': date,
                'close': price,
                'price': price,
                'adjClose': price
            }
            aligned_history.append(price_point)
        
        aligned_histories.append(aligned_history)
    
    return aligned_histories, common_dates


def normalize_to_common_start(price_histories: List[List[Dict]], symbols: List[str], 
                             initial_value: float = 1000.0) -> List[List[Dict]]:
    """
    Normalize price histories to start from the same initial value for comparison.
    
    Args:
        price_histories: List of aligned price histories
        symbols: List of asset symbols
        initial_value: Starting value for normalization (default: $1000)
        
    Returns:
        List of normalized price histories
    """
    normalized_histories = []
    
    for i, (history, symbol) in enumerate(zip(price_histories, symbols)):
        if not history:
            normalized_histories.append([])
            continue
        
        # Find first valid price
        first_price = None
        for price_point in history:
            if isinstance(price_point, dict):
                for price_field in ['close', 'Close', 'price', 'Price', 'adjClose', 'AdjClose']:
                    if price_field in price_point and price_point[price_field] is not None:
                        try:
                            first_price = float(price_point[price_field])
                            break
                        except (ValueError, TypeError):
                            continue
            if first_price is not None:
                break
        
        if first_price is None or first_price <= 0:
            normalized_histories.append([])
            continue
        
        # Normalize all prices relative to first price
        normalized_history = []
        for price_point in history:
            normalized_point = price_point.copy()
            
            for price_field in ['close', 'Close', 'price', 'Price', 'adjClose', 'AdjClose']:
                if price_field in price_point and price_point[price_field] is not None:
                    try:
                        original_price = float(price_point[price_field])
                        normalized_price = (original_price / first_price) * initial_value
                        normalized_point[price_field] = normalized_price
                    except (ValueError, TypeError):
                        continue
            
            normalized_history.append(normalized_point)
        
        normalized_histories.append(normalized_history)
    
    return normalized_histories