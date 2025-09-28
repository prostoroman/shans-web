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
        prices: List of prices
        years: Number of years
        
    Returns:
        CAGR as decimal
    """
    if len(prices) < 2 or years <= 0:
        return 0.0
    
    start_price = prices[0]
    end_price = prices[-1]
    
    if start_price <= 0:
        return 0.0
    
    cagr = (end_price / start_price) ** (1 / years) - 1
    return cagr


def calculate_volatility(returns: List[float]) -> float:
    """
    Calculate annualized volatility.
    
    Args:
        returns: List of daily returns
        
    Returns:
        Annualized volatility
    """
    if len(returns) < 2:
        return 0.0
    
    return np.std(returns) * np.sqrt(252)  # 252 trading days per year


def calculate_sharpe_ratio(returns: List[float], risk_free_rate: float = 0.03) -> float:
    """
    Calculate Sharpe ratio.
    
    Args:
        returns: List of daily returns
        risk_free_rate: Risk-free rate (annual)
        
    Returns:
        Sharpe ratio
    """
    if len(returns) < 2:
        return 0.0
    
    excess_returns = [r - risk_free_rate/252 for r in returns]  # Daily risk-free rate
    avg_excess_return = np.mean(excess_returns)
    volatility = calculate_volatility(returns)
    
    if volatility == 0:
        return 0.0
    
    return (avg_excess_return * 252) / volatility  # Annualized


def calculate_sortino_ratio(returns: List[float], risk_free_rate: float = 0.03) -> float:
    """
    Calculate Sortino ratio.
    
    Args:
        returns: List of daily returns
        risk_free_rate: Risk-free rate (annual)
        
    Returns:
        Sortino ratio
    """
    if len(returns) < 2:
        return 0.0
    
    excess_returns = [r - risk_free_rate/252 for r in returns]
    avg_excess_return = np.mean(excess_returns)
    
    # Downside deviation (only negative returns)
    negative_returns = [r for r in excess_returns if r < 0]
    if len(negative_returns) == 0:
        return float('inf') if avg_excess_return > 0 else 0.0
    
    downside_deviation = np.std(negative_returns) * np.sqrt(252)
    
    if downside_deviation == 0:
        return 0.0
    
    return (avg_excess_return * 252) / downside_deviation


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
                     risk_free_rate: float = 0.03, years: float = 5.0) -> Dict[str, float]:
    """
    Calculate comprehensive metrics for a price series.
    
    Args:
        prices: List of prices
        benchmark_prices: Optional benchmark prices for beta calculation
        risk_free_rate: Risk-free rate (annual)
        years: Number of years for CAGR calculation
        
    Returns:
        Dictionary of calculated metrics
    """
    if len(prices) < 2:
        return {}
    
    returns = calculate_returns(prices)
    
    metrics = {
        'cagr': calculate_cagr(prices, years),
        'volatility': calculate_volatility(returns),
        'sharpe_ratio': calculate_sharpe_ratio(returns, risk_free_rate),
        'sortino_ratio': calculate_sortino_ratio(returns, risk_free_rate),
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