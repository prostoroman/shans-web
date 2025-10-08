"""
Enhanced portfolio service supporting multiple asset types.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
from datetime import date, timedelta

from .models import Portfolio, PortfolioPosition
from apps.markets.assets import AssetFactory, BaseAsset, AssetType
from apps.markets.currency_converter import get_currency_converter
from .mpt import (
    calculate_mean_returns, calculate_covariance_matrix,
    optimize_portfolio, calculate_efficient_frontier,
    calculate_minimum_variance_portfolio, calculate_tangency_portfolio
)

logger = logging.getLogger(__name__)


class EnhancedPortfolioService:
    """Enhanced portfolio service supporting multiple asset types."""
    
    def __init__(self):
        self.currency_converter = get_currency_converter()
    
    def analyze_portfolio(self, symbols: List[str], weights: List[float], 
                         base_currency: str = 'USD', include_dividends: bool = True,
                         days: int = 365) -> Dict[str, Any]:
        """
        Analyze a portfolio with multiple asset types.
        
        Args:
            symbols: List of asset symbols
            weights: List of weights (must sum to 1.0)
            base_currency: Base currency for analysis
            include_dividends: Whether to include dividends in returns
            days: Number of days to analyze
            
        Returns:
            Dictionary with portfolio analysis results
        """
        try:
            # Validate inputs
            if len(symbols) != len(weights):
                return {'error': 'Number of symbols and weights must match'}
            
            if abs(sum(weights) - 1.0) > 0.01:
                return {'error': 'Weights must sum to 1.0'}
            
            # Create asset instances
            assets = AssetFactory.create_assets(symbols)
            
            # Get data for all assets
            asset_data = {}
            returns_matrix = []
            
            for i, asset in enumerate(assets):
                try:
                    # Get price history
                    price_history = asset.get_price_history(days)
                    if not price_history or len(price_history) < 2:
                        return {'error': f'No price data available for {asset.symbol}'}
                    
                    # Calculate returns
                    returns = self._calculate_returns(price_history, include_dividends)
                    if not returns:
                        return {'error': f'Unable to calculate returns for {asset.symbol}'}
                    
                    returns_matrix.append(returns)
                    
                    # Store asset data
                    asset_data[asset.symbol] = {
                        'asset': asset,
                        'price_history': price_history,
                        'returns': returns,
                        'weight': weights[i]
                    }
                    
                except Exception as e:
                    logger.error(f"Error processing asset {asset.symbol}: {e}")
                    return {'error': f'Error processing asset {asset.symbol}'}
            
            # Align returns (use minimum length)
            min_length = min(len(returns) for returns in returns_matrix)
            aligned_returns = [returns[:min_length] for returns in returns_matrix]
            
            # Calculate portfolio metrics
            portfolio_metrics = self._calculate_portfolio_metrics(
                aligned_returns, weights, base_currency
            )
            
            # Calculate individual asset metrics
            asset_metrics = {}
            for symbol, data in asset_data.items():
                asset_metrics[symbol] = self._calculate_asset_metrics(
                    data['asset'], data['returns'], base_currency
                )
            
            # Calculate optimization results
            optimization_results = self._calculate_optimization_results(
                aligned_returns, weights
            )
            
            # Calculate correlation matrix
            correlation_matrix = self._calculate_correlation_matrix(aligned_returns, symbols)
            
            return {
                'portfolio_metrics': portfolio_metrics,
                'asset_metrics': asset_metrics,
                'optimization_results': optimization_results,
                'correlation_matrix': correlation_matrix,
                'base_currency': base_currency,
                'analysis_period_days': days,
                'include_dividends': include_dividends,
                'positions': [
                    {
                        'symbol': symbol,
                        'weight': weight,
                        'asset_type': asset_data[symbol]['asset'].asset_type.value
                    }
                    for symbol, weight in zip(symbols, weights)
                ]
            }
            
        except Exception as e:
            logger.error(f"Error analyzing portfolio: {e}")
            return {'error': str(e)}
    
    def _calculate_returns(self, price_history: List[Dict], include_dividends: bool) -> List[float]:
        """Calculate returns from price history."""
        try:
            # Sort by date (oldest first)
            price_history.sort(key=lambda x: x.get('date', ''))
            
            returns = []
            for i in range(1, len(price_history)):
                prev_price = float(price_history[i-1].get('price', price_history[i-1].get('close', 0)))
                curr_price = float(price_history[i].get('price', price_history[i].get('close', 0)))
                
                if prev_price > 0:
                    price_return = (curr_price - prev_price) / prev_price
                    returns.append(price_return)
            
            return returns
            
        except Exception as e:
            logger.error(f"Error calculating returns: {e}")
            return []
    
    def _calculate_portfolio_metrics(self, returns_matrix: List[List[float]], 
                                   weights: List[float], base_currency: str) -> Dict[str, Any]:
        """Calculate portfolio-level metrics."""
        try:
            # Calculate mean returns
            mean_returns = calculate_mean_returns(returns_matrix)
            
            # Calculate covariance matrix
            cov_matrix = calculate_covariance_matrix(returns_matrix)
            
            # Calculate portfolio expected return
            portfolio_return = sum(w * r for w, r in zip(weights, mean_returns))
            
            # Calculate portfolio variance
            portfolio_variance = 0
            for i in range(len(weights)):
                for j in range(len(weights)):
                    portfolio_variance += weights[i] * weights[j] * cov_matrix[i][j]
            
            # Calculate portfolio volatility
            portfolio_volatility = portfolio_variance ** 0.5
            
            # Calculate Sharpe ratio (assuming risk-free rate of 3%)
            risk_free_rate = 0.03
            sharpe_ratio = (portfolio_return - risk_free_rate) / portfolio_volatility if portfolio_volatility > 0 else 0
            
            # Calculate maximum drawdown
            max_drawdown = self._calculate_max_drawdown(returns_matrix, weights)
            
            return {
                'expected_return': portfolio_return,
                'volatility': portfolio_volatility,
                'sharpe_ratio': sharpe_ratio,
                'max_drawdown': max_drawdown,
                'variance': portfolio_variance,
                'risk_free_rate': risk_free_rate
            }
            
        except Exception as e:
            logger.error(f"Error calculating portfolio metrics: {e}")
            return {}
    
    def _calculate_asset_metrics(self, asset: BaseAsset, returns: List[float], 
                               base_currency: str) -> Dict[str, Any]:
        """Calculate metrics for individual assets."""
        try:
            # Basic metrics
            mean_return = sum(returns) / len(returns) if returns else 0
            volatility = (sum((r - mean_return) ** 2 for r in returns) / len(returns)) ** 0.5 if returns else 0
            
            # Calculate Sharpe ratio
            risk_free_rate = 0.03
            sharpe_ratio = (mean_return - risk_free_rate) / volatility if volatility > 0 else 0
            
            # Calculate maximum drawdown
            max_drawdown = self._calculate_asset_max_drawdown(returns)
            
            # Get current price and other metrics
            current_price = asset.get_current_price()
            price_change = asset.get_price_change_percentage()
            market_cap = asset.get_market_cap()
            
            return {
                'expected_return': mean_return,
                'volatility': volatility,
                'sharpe_ratio': sharpe_ratio,
                'max_drawdown': max_drawdown,
                'current_price': float(current_price) if current_price else None,
                'price_change_percentage': float(price_change) if price_change else None,
                'market_cap': market_cap,
                'asset_type': asset.asset_type.value,
                'currency': base_currency
            }
            
        except Exception as e:
            logger.error(f"Error calculating asset metrics for {asset.symbol}: {e}")
            return {}
    
    def _calculate_optimization_results(self, returns_matrix: List[List[float]], 
                                     current_weights: List[float]) -> Dict[str, Any]:
        """Calculate portfolio optimization results."""
        try:
            # Calculate mean returns and covariance matrix
            mean_returns = calculate_mean_returns(returns_matrix)
            cov_matrix = calculate_covariance_matrix(returns_matrix)
            
            # Calculate minimum variance portfolio
            min_var_portfolio = calculate_minimum_variance_portfolio(cov_matrix)
            
            # Calculate tangency portfolio (maximum Sharpe ratio)
            tangency_portfolio = calculate_tangency_portfolio(mean_returns, cov_matrix, 0.03)
            
            # Calculate efficient frontier
            efficient_frontier = calculate_efficient_frontier(mean_returns, cov_matrix, 0.03)
            
            return {
                'minimum_variance_portfolio': {
                    'weights': min_var_portfolio['weights'],
                    'expected_return': min_var_portfolio['expected_return'],
                    'volatility': min_var_portfolio['volatility']
                },
                'tangency_portfolio': {
                    'weights': tangency_portfolio['weights'],
                    'expected_return': tangency_portfolio['expected_return'],
                    'volatility': tangency_portfolio['volatility'],
                    'sharpe_ratio': tangency_portfolio['sharpe_ratio']
                },
                'efficient_frontier': efficient_frontier,
                'current_portfolio': {
                    'weights': current_weights,
                    'expected_return': sum(w * r for w, r in zip(current_weights, mean_returns)),
                    'volatility': self._calculate_portfolio_volatility(current_weights, cov_matrix)
                }
            }
            
        except Exception as e:
            logger.error(f"Error calculating optimization results: {e}")
            return {}
    
    def _calculate_correlation_matrix(self, returns_matrix: List[List[float]], 
                                   symbols: List[str]) -> Dict[str, float]:
        """Calculate correlation matrix between assets."""
        try:
            correlation_matrix = {}
            
            for i, symbol1 in enumerate(symbols):
                for j, symbol2 in enumerate(symbols):
                    if i < j:
                        correlation = self._calculate_correlation(
                            returns_matrix[i], returns_matrix[j]
                        )
                        if correlation is not None:
                            correlation_matrix[f"{symbol1}_{symbol2}"] = correlation
            
            return correlation_matrix
            
        except Exception as e:
            logger.error(f"Error calculating correlation matrix: {e}")
            return {}
    
    def _calculate_correlation(self, returns1: List[float], returns2: List[float]) -> Optional[float]:
        """Calculate correlation coefficient between two return series."""
        try:
            if len(returns1) != len(returns2) or len(returns1) < 2:
                return None
            
            # Calculate correlation coefficient
            n = len(returns1)
            sum1 = sum(returns1)
            sum2 = sum(returns2)
            sum1_sq = sum(x * x for x in returns1)
            sum2_sq = sum(x * x for x in returns2)
            sum_product = sum(x * y for x, y in zip(returns1, returns2))
            
            numerator = n * sum_product - sum1 * sum2
            denominator = ((n * sum1_sq - sum1 * sum1) * (n * sum2_sq - sum2 * sum2)) ** 0.5
            
            if denominator == 0:
                return None
            
            correlation = numerator / denominator
            return correlation
            
        except Exception as e:
            logger.error(f"Error calculating correlation: {e}")
            return None
    
    def _calculate_max_drawdown(self, returns_matrix: List[List[float]], 
                              weights: List[float]) -> float:
        """Calculate maximum drawdown for the portfolio."""
        try:
            # Calculate portfolio returns
            portfolio_returns = []
            for i in range(len(returns_matrix[0])):
                portfolio_return = sum(w * returns[i] for w, returns in zip(weights, returns_matrix))
                portfolio_returns.append(portfolio_return)
            
            # Calculate cumulative returns
            cumulative_returns = [1.0]
            for ret in portfolio_returns:
                cumulative_returns.append(cumulative_returns[-1] * (1 + ret))
            
            # Calculate maximum drawdown
            peak = cumulative_returns[0]
            max_drawdown = 0
            
            for value in cumulative_returns:
                if value > peak:
                    peak = value
                drawdown = (peak - value) / peak
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
            
            return max_drawdown
            
        except Exception as e:
            logger.error(f"Error calculating max drawdown: {e}")
            return 0.0
    
    def _calculate_asset_max_drawdown(self, returns: List[float]) -> float:
        """Calculate maximum drawdown for a single asset."""
        try:
            # Calculate cumulative returns
            cumulative_returns = [1.0]
            for ret in returns:
                cumulative_returns.append(cumulative_returns[-1] * (1 + ret))
            
            # Calculate maximum drawdown
            peak = cumulative_returns[0]
            max_drawdown = 0
            
            for value in cumulative_returns:
                if value > peak:
                    peak = value
                drawdown = (peak - value) / peak
                if drawdown > max_drawdown:
                    max_drawdown = drawdown
            
            return max_drawdown
            
        except Exception as e:
            logger.error(f"Error calculating asset max drawdown: {e}")
            return 0.0
    
    def _calculate_portfolio_volatility(self, weights: List[float], 
                                     cov_matrix: List[List[float]]) -> float:
        """Calculate portfolio volatility."""
        try:
            portfolio_variance = 0
            for i in range(len(weights)):
                for j in range(len(weights)):
                    portfolio_variance += weights[i] * weights[j] * cov_matrix[i][j]
            
            return portfolio_variance ** 0.5
            
        except Exception as e:
            logger.error(f"Error calculating portfolio volatility: {e}")
            return 0.0
    
    def create_portfolio(self, user, name: str, symbols: List[str], weights: List[float],
                        description: str = '') -> Optional[Portfolio]:
        """Create a new portfolio with positions."""
        try:
            # Create portfolio
            portfolio = Portfolio.objects.create(
                user=user,
                name=name,
                description=description
            )
            
            # Create positions
            for symbol, weight in zip(symbols, weights):
                PortfolioPosition.objects.create(
                    portfolio=portfolio,
                    symbol=symbol,
                    weight=weight
                )
            
            return portfolio
            
        except Exception as e:
            logger.error(f"Error creating portfolio: {e}")
            return None


# Global service instance
_portfolio_service = None


def get_portfolio_service() -> EnhancedPortfolioService:
    """Get global portfolio service instance."""
    global _portfolio_service
    if _portfolio_service is None:
        _portfolio_service = EnhancedPortfolioService()
    return _portfolio_service


def analyze_portfolio(symbols: List[str], weights: List[float], 
                     base_currency: str = 'USD', include_dividends: bool = True,
                     days: int = 365) -> Dict[str, Any]:
    """
    Convenience function for portfolio analysis.
    
    Args:
        symbols: List of asset symbols
        weights: List of weights (must sum to 1.0)
        base_currency: Base currency for analysis
        include_dividends: Whether to include dividends in returns
        days: Number of days to analyze
        
    Returns:
        Dictionary with portfolio analysis results
    """
    service = get_portfolio_service()
    return service.analyze_portfolio(symbols, weights, base_currency, include_dividends, days)
