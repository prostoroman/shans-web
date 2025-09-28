"""
Modern Portfolio Theory calculations.
"""

import numpy as np
import pandas as pd
from typing import List, Dict, Any, Optional, Tuple
from scipy.optimize import minimize
import logging

logger = logging.getLogger(__name__)


def calculate_mean_returns(returns_matrix: List[List[float]]) -> np.ndarray:
    """
    Calculate mean returns for each asset.
    
    Args:
        returns_matrix: Matrix of returns (assets x time)
        
    Returns:
        Array of mean returns
    """
    returns_array = np.array(returns_matrix)
    return np.mean(returns_array, axis=1) * 252  # Annualized


def calculate_covariance_matrix(returns_matrix: List[List[float]]) -> np.ndarray:
    """
    Calculate covariance matrix.
    
    Args:
        returns_matrix: Matrix of returns (assets x time)
        
    Returns:
        Covariance matrix
    """
    returns_array = np.array(returns_matrix)
    return np.cov(returns_array) * 252  # Annualized


def portfolio_return(weights: np.ndarray, mean_returns: np.ndarray) -> float:
    """
    Calculate portfolio expected return.
    
    Args:
        weights: Portfolio weights
        mean_returns: Mean returns for each asset
        
    Returns:
        Portfolio expected return
    """
    return np.dot(weights, mean_returns)


def portfolio_volatility(weights: np.ndarray, cov_matrix: np.ndarray) -> float:
    """
    Calculate portfolio volatility.
    
    Args:
        weights: Portfolio weights
        cov_matrix: Covariance matrix
        
    Returns:
        Portfolio volatility
    """
    return np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))


def negative_sharpe_ratio(weights: np.ndarray, mean_returns: np.ndarray, 
                         cov_matrix: np.ndarray, risk_free_rate: float = 0.03) -> float:
    """
    Calculate negative Sharpe ratio for optimization.
    
    Args:
        weights: Portfolio weights
        mean_returns: Mean returns for each asset
        cov_matrix: Covariance matrix
        risk_free_rate: Risk-free rate
        
    Returns:
        Negative Sharpe ratio
    """
    portfolio_ret = portfolio_return(weights, mean_returns)
    portfolio_vol = portfolio_volatility(weights, cov_matrix)
    
    if portfolio_vol == 0:
        return 0
    
    return -(portfolio_ret - risk_free_rate) / portfolio_vol


def optimize_portfolio(mean_returns: np.ndarray, cov_matrix: np.ndarray, 
                      risk_free_rate: float = 0.03) -> Dict[str, Any]:
    """
    Optimize portfolio for maximum Sharpe ratio.
    
    Args:
        mean_returns: Mean returns for each asset
        cov_matrix: Covariance matrix
        risk_free_rate: Risk-free rate
        
    Returns:
        Dictionary with optimization results
    """
    num_assets = len(mean_returns)
    
    # Constraints: weights sum to 1
    constraints = {'type': 'eq', 'fun': lambda x: np.sum(x) - 1}
    
    # Bounds: weights between 0 and 1
    bounds = tuple((0, 1) for _ in range(num_assets))
    
    # Initial guess: equal weights
    initial_guess = np.array([1/num_assets] * num_assets)
    
    # Optimize
    result = minimize(
        negative_sharpe_ratio,
        initial_guess,
        args=(mean_returns, cov_matrix, risk_free_rate),
        method='SLSQP',
        bounds=bounds,
        constraints=constraints
    )
    
    if result.success:
        optimal_weights = result.x
        optimal_return = portfolio_return(optimal_weights, mean_returns)
        optimal_volatility = portfolio_volatility(optimal_weights, cov_matrix)
        optimal_sharpe = (optimal_return - risk_free_rate) / optimal_volatility
        
        return {
            'weights': optimal_weights.tolist(),
            'expected_return': optimal_return,
            'volatility': optimal_volatility,
            'sharpe_ratio': optimal_sharpe,
            'success': True
        }
    else:
        logger.error(f"Portfolio optimization failed: {result.message}")
        return {'success': False, 'message': result.message}


def calculate_efficient_frontier(mean_returns: np.ndarray, cov_matrix: np.ndarray, 
                               num_portfolios: int = 100) -> List[Dict[str, float]]:
    """
    Calculate efficient frontier.
    
    Args:
        mean_returns: Mean returns for each asset
        cov_matrix: Covariance matrix
        num_portfolios: Number of portfolios to generate
        
    Returns:
        List of portfolios on efficient frontier
    """
    num_assets = len(mean_returns)
    portfolios = []
    
    # Generate random portfolios
    for _ in range(num_portfolios):
        # Generate random weights
        weights = np.random.random(num_assets)
        weights = weights / np.sum(weights)  # Normalize to sum to 1
        
        # Calculate portfolio metrics
        portfolio_ret = portfolio_return(weights, mean_returns)
        portfolio_vol = portfolio_volatility(weights, cov_matrix)
        
        portfolios.append({
            'weights': weights.tolist(),
            'expected_return': portfolio_ret,
            'volatility': portfolio_vol
        })
    
    # Sort by volatility
    portfolios.sort(key=lambda x: x['volatility'])
    
    return portfolios


def calculate_minimum_variance_portfolio(cov_matrix: np.ndarray) -> Dict[str, Any]:
    """
    Calculate minimum variance portfolio.
    
    Args:
        cov_matrix: Covariance matrix
        
    Returns:
        Dictionary with minimum variance portfolio
    """
    num_assets = len(cov_matrix)
    
    # Objective function: minimize portfolio variance
    def portfolio_variance(weights):
        return portfolio_volatility(weights, cov_matrix) ** 2
    
    # Constraints: weights sum to 1
    constraints = {'type': 'eq', 'fun': lambda x: np.sum(x) - 1}
    
    # Bounds: weights between 0 and 1
    bounds = tuple((0, 1) for _ in range(num_assets))
    
    # Initial guess: equal weights
    initial_guess = np.array([1/num_assets] * num_assets)
    
    # Optimize
    result = minimize(
        portfolio_variance,
        initial_guess,
        method='SLSQP',
        bounds=bounds,
        constraints=constraints
    )
    
    if result.success:
        min_var_weights = result.x
        min_var_volatility = portfolio_volatility(min_var_weights, cov_matrix)
        
        return {
            'weights': min_var_weights.tolist(),
            'volatility': min_var_volatility,
            'success': True
        }
    else:
        logger.error(f"Minimum variance optimization failed: {result.message}")
        return {'success': False, 'message': result.message}


def calculate_tangency_portfolio(mean_returns: np.ndarray, cov_matrix: np.ndarray, 
                               risk_free_rate: float = 0.03) -> Dict[str, Any]:
    """
    Calculate tangency portfolio (maximum Sharpe ratio).
    
    Args:
        mean_returns: Mean returns for each asset
        cov_matrix: Covariance matrix
        risk_free_rate: Risk-free rate
        
    Returns:
        Dictionary with tangency portfolio
    """
    return optimize_portfolio(mean_returns, cov_matrix, risk_free_rate)


def calculate_portfolio_risk_metrics(weights: np.ndarray, cov_matrix: np.ndarray) -> Dict[str, float]:
    """
    Calculate additional risk metrics for portfolio.
    
    Args:
        weights: Portfolio weights
        cov_matrix: Covariance matrix
        
    Returns:
        Dictionary of risk metrics
    """
    portfolio_vol = portfolio_volatility(weights, cov_matrix)
    
    # Calculate contribution to risk for each asset
    risk_contributions = []
    for i in range(len(weights)):
        contribution = weights[i] * np.dot(cov_matrix[i], weights) / portfolio_vol
        risk_contributions.append(contribution)
    
    # Calculate diversification ratio
    weighted_vol = np.dot(weights, np.sqrt(np.diag(cov_matrix)))
    diversification_ratio = weighted_vol / portfolio_vol if portfolio_vol > 0 else 0
    
    return {
        'portfolio_volatility': portfolio_vol,
        'risk_contributions': risk_contributions,
        'diversification_ratio': diversification_ratio,
        'concentration_risk': np.sum(np.array(risk_contributions) ** 2)
    }