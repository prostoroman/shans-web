"""
Portfolio forecasting using time series methods.
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
import logging

logger = logging.getLogger(__name__)


def calculate_ewma_forecast(returns: List[float], alpha: float = 0.1, 
                           periods: int = 30) -> List[float]:
    """
    Calculate EWMA (Exponentially Weighted Moving Average) forecast.
    
    Args:
        returns: Historical returns
        alpha: Smoothing parameter (0 < alpha < 1)
        periods: Number of periods to forecast
        
    Returns:
        List of forecasted returns
    """
    if len(returns) < 2:
        return [0.0] * periods
    
    # Calculate EWMA
    ewma_values = [returns[0]]
    for i in range(1, len(returns)):
        ewma = alpha * returns[i] + (1 - alpha) * ewma_values[-1]
        ewma_values.append(ewma)
    
    # Forecast using the last EWMA value
    last_ewma = ewma_values[-1]
    forecast = [last_ewma] * periods
    
    return forecast


def calculate_arima_forecast(returns: List[float], periods: int = 30) -> List[float]:
    """
    Simple ARIMA(1,0,0) forecast (stub implementation).
    
    Args:
        returns: Historical returns
        periods: Number of periods to forecast
        
    Returns:
        List of forecasted returns
    """
    if len(returns) < 3:
        return [0.0] * periods
    
    # Simple AR(1) model: r_t = c + φ * r_{t-1} + ε_t
    # Estimate parameters using OLS
    y = np.array(returns[1:])
    x = np.array(returns[:-1])
    
    # Add constant term
    X = np.column_stack([np.ones(len(x)), x])
    
    try:
        # OLS estimation
        beta = np.linalg.lstsq(X, y, rcond=None)[0]
        c, phi = beta[0], beta[1]
        
        # Forecast
        forecast = []
        last_return = returns[-1]
        
        for _ in range(periods):
            next_return = c + phi * last_return
            forecast.append(next_return)
            last_return = next_return
        
        return forecast
        
    except np.linalg.LinAlgError:
        logger.warning("ARIMA estimation failed, using mean forecast")
        mean_return = np.mean(returns)
        return [mean_return] * periods


def calculate_monte_carlo_forecast(returns: List[float], periods: int = 30, 
                                 simulations: int = 1000) -> Dict[str, List[float]]:
    """
    Calculate Monte Carlo forecast with confidence intervals.
    
    Args:
        returns: Historical returns
        periods: Number of periods to forecast
        simulations: Number of Monte Carlo simulations
        
    Returns:
        Dictionary with forecast statistics
    """
    if len(returns) < 2:
        return {
            'mean': [0.0] * periods,
            'std': [0.0] * periods,
            'percentile_5': [0.0] * periods,
            'percentile_95': [0.0] * periods
        }
    
    # Calculate historical statistics
    mean_return = np.mean(returns)
    std_return = np.std(returns)
    
    # Generate Monte Carlo simulations
    simulations_matrix = np.random.normal(
        mean_return, std_return, (simulations, periods)
    )
    
    # Calculate statistics
    forecast_mean = np.mean(simulations_matrix, axis=0)
    forecast_std = np.std(simulations_matrix, axis=0)
    forecast_5th = np.percentile(simulations_matrix, 5, axis=0)
    forecast_95th = np.percentile(simulations_matrix, 95, axis=0)
    
    return {
        'mean': forecast_mean.tolist(),
        'std': forecast_std.tolist(),
        'percentile_5': forecast_5th.tolist(),
        'percentile_95': forecast_95th.tolist()
    }


def calculate_volatility_forecast(returns: List[float], periods: int = 30) -> List[float]:
    """
    Calculate volatility forecast using GARCH-like approach.
    
    Args:
        returns: Historical returns
        periods: Number of periods to forecast
        
    Returns:
        List of forecasted volatilities
    """
    if len(returns) < 10:
        return [0.0] * periods
    
    # Calculate rolling volatility
    window = min(20, len(returns) // 2)
    rolling_vol = []
    
    for i in range(window, len(returns)):
        vol = np.std(returns[i-window:i])
        rolling_vol.append(vol)
    
    if not rolling_vol:
        return [0.0] * periods
    
    # Simple EWMA of volatility
    alpha = 0.1
    ewma_vol = [rolling_vol[0]]
    
    for i in range(1, len(rolling_vol)):
        ewma = alpha * rolling_vol[i] + (1 - alpha) * ewma_vol[-1]
        ewma_vol.append(ewma)
    
    # Forecast using last EWMA value
    last_vol = ewma_vol[-1]
    forecast = [last_vol] * periods
    
    return forecast


def calculate_portfolio_forecast(weights: List[float], returns_matrix: List[List[float]], 
                               periods: int = 30, method: str = 'ewma') -> Dict[str, Any]:
    """
    Calculate portfolio-level forecast.
    
    Args:
        weights: Portfolio weights
        returns_matrix: Matrix of returns (assets x time)
        periods: Number of periods to forecast
        method: Forecasting method ('ewma', 'arima', 'monte_carlo')
        
    Returns:
        Dictionary with portfolio forecast
    """
    if len(weights) != len(returns_matrix) or len(weights) == 0:
        return {}
    
    # Calculate portfolio returns
    portfolio_returns = []
    for t in range(len(returns_matrix[0])):
        portfolio_ret = sum(weights[i] * returns_matrix[i][t] for i in range(len(weights)))
        portfolio_returns.append(portfolio_ret)
    
    # Generate forecast based on method
    if method == 'ewma':
        forecast_returns = calculate_ewma_forecast(portfolio_returns, periods=periods)
        forecast_vol = calculate_volatility_forecast(portfolio_returns, periods=periods)
        
        return {
            'method': 'ewma',
            'forecast_returns': forecast_returns,
            'forecast_volatility': forecast_vol,
            'expected_return': np.mean(forecast_returns) * 252,  # Annualized
            'expected_volatility': np.mean(forecast_vol) * np.sqrt(252)  # Annualized
        }
    
    elif method == 'arima':
        forecast_returns = calculate_arima_forecast(portfolio_returns, periods=periods)
        forecast_vol = calculate_volatility_forecast(portfolio_returns, periods=periods)
        
        return {
            'method': 'arima',
            'forecast_returns': forecast_returns,
            'forecast_volatility': forecast_vol,
            'expected_return': np.mean(forecast_returns) * 252,  # Annualized
            'expected_volatility': np.mean(forecast_vol) * np.sqrt(252)  # Annualized
        }
    
    elif method == 'monte_carlo':
        mc_forecast = calculate_monte_carlo_forecast(portfolio_returns, periods=periods)
        
        return {
            'method': 'monte_carlo',
            'forecast_returns': mc_forecast['mean'],
            'forecast_volatility': mc_forecast['std'],
            'confidence_intervals': {
                'lower': mc_forecast['percentile_5'],
                'upper': mc_forecast['percentile_95']
            },
            'expected_return': np.mean(mc_forecast['mean']) * 252,  # Annualized
            'expected_volatility': np.mean(mc_forecast['std']) * np.sqrt(252)  # Annualized
        }
    
    else:
        logger.error(f"Unknown forecasting method: {method}")
        return {}


def calculate_scenario_analysis(weights: List[float], returns_matrix: List[List[float]], 
                              scenarios: Dict[str, List[float]]) -> Dict[str, float]:
    """
    Calculate portfolio performance under different scenarios.
    
    Args:
        weights: Portfolio weights
        returns_matrix: Matrix of returns (assets x time)
        scenarios: Dictionary of scenario names and return adjustments
        
    Returns:
        Dictionary with scenario analysis results
    """
    if len(weights) != len(returns_matrix) or len(weights) == 0:
        return {}
    
    # Calculate baseline portfolio return
    baseline_return = 0
    for i in range(len(weights)):
        asset_return = np.mean(returns_matrix[i]) * 252  # Annualized
        baseline_return += weights[i] * asset_return
    
    results = {'baseline': baseline_return}
    
    # Calculate scenario returns
    for scenario_name, adjustments in scenarios.items():
        if len(adjustments) != len(weights):
            continue
        
        scenario_return = 0
        for i in range(len(weights)):
            asset_return = np.mean(returns_matrix[i]) * 252  # Annualized
            adjusted_return = asset_return + adjustments[i]
            scenario_return += weights[i] * adjusted_return
        
        results[scenario_name] = scenario_return
    
    return results