"""
Efficient Frontier calculation service for portfolio optimization.
Uses monthly total return historical data to calculate optimized portfolio points.
"""

import logging
import numpy as np
from typing import Dict, List, Optional, Any, Tuple
from datetime import date, timedelta
from scipy.optimize import minimize
import math

logger = logging.getLogger(__name__)


class EfficientFrontierService:
    """Service for calculating Efficient Frontier and optimal portfolios."""
    
    def __init__(self):
        pass
    
    def calculate_efficient_frontier(self, symbols: List[str], chart_data: Dict[str, List[Any]], 
                                   base_currency: str = 'USD', risk_free_rate: float = 0.02) -> Dict[str, Any]:
        """
        Calculate Efficient Frontier using monthly total return historical data.
        
        Args:
            symbols: List of asset symbols
            chart_data: Chart data from comparison service
            base_currency: Base currency for calculations
            risk_free_rate: Annual risk-free rate
            
        Returns:
            Dictionary with Efficient Frontier results
        """
        try:
            # Extract monthly returns for each symbol
            monthly_returns = self._extract_monthly_returns(symbols, chart_data)
            
            if not monthly_returns or len(monthly_returns) < 2:
                return {
                    'error': 'Insufficient data for Efficient Frontier calculation. Need at least 2 assets with monthly return data.'
                }
            
            # Calculate expected returns and covariance matrix
            expected_returns, cov_matrix = self._calculate_portfolio_statistics(monthly_returns)
            
            if expected_returns is None or cov_matrix is None:
                return {
                    'error': 'Failed to calculate portfolio statistics'
                }
            
            # Calculate optimal portfolios
            min_risk_portfolio = self._calculate_min_risk_portfolio(expected_returns, cov_matrix)
            max_return_portfolio = self._calculate_max_return_portfolio(expected_returns, cov_matrix)
            max_sharpe_portfolio = self._calculate_max_sharpe_portfolio(expected_returns, cov_matrix, risk_free_rate)
            
            # Calculate Efficient Frontier curve
            efficient_frontier = self._calculate_efficient_frontier_curve(expected_returns, cov_matrix, risk_free_rate)
            
            # Individual Asset Statistics removed - no longer needed
            
            result = {
                'success': True,
                'symbols': symbols,
                'base_currency': base_currency,
                'risk_free_rate': risk_free_rate,
                'monthly_returns': monthly_returns,
                'expected_returns': expected_returns.tolist(),
                'covariance_matrix': cov_matrix.tolist(),
                'min_risk_portfolio': min_risk_portfolio,
                'max_return_portfolio': max_return_portfolio,
                'max_sharpe_portfolio': max_sharpe_portfolio,
                'efficient_frontier': efficient_frontier
            }
            
            logger.info(f"Efficient Frontier calculated successfully for {len(symbols)} assets")
            return result
            
        except Exception as e:
            logger.error(f"Error calculating Efficient Frontier: {e}")
            return {'error': str(e)}
    
    def _extract_monthly_returns(self, symbols: List[str], chart_data: Dict[str, List[Any]]) -> Dict[str, List[float]]:
        """Extract monthly returns from chart data."""
        monthly_returns = {}
        
        for symbol in symbols:
            if symbol not in chart_data or not chart_data[symbol]:
                logger.warning(f"No chart data for {symbol}")
                continue
            
            points = chart_data[symbol]
            returns = []
            
            # Calculate monthly returns from price data
            for i in range(1, len(points)):
                if (hasattr(points[i], 'value') and hasattr(points[i-1], 'value') and 
                    points[i].value is not None and points[i-1].value is not None and 
                    points[i-1].value != 0):
                    
                    # Calculate monthly return
                    monthly_return = (points[i].value - points[i-1].value) / points[i-1].value
                    
                    # Cap extreme monthly returns to prevent unrealistic values
                    monthly_return = np.clip(monthly_return, -0.5, 0.5)  # ±50% monthly max
                    
                    returns.append(monthly_return)
            
            if len(returns) >= 12:  # Need at least 12 months of data
                monthly_returns[symbol] = returns
                logger.info(f"Extracted {len(returns)} monthly returns for {symbol}")
            else:
                logger.warning(f"Insufficient monthly returns for {symbol}: {len(returns)}")
        
        return monthly_returns
    
    def _extract_dividend_adjusted_returns(self, symbols: List[str], chart_data: Dict[str, List[Any]]) -> Dict[str, List[float]]:
        """Extract returns from chart data using the same method as metrics calculation for consistency."""
        monthly_returns = {}
        
        for symbol in symbols:
            if symbol not in chart_data or not chart_data[symbol]:
                logger.warning(f"No chart data for {symbol}")
                continue
            
            points = chart_data[symbol]
            returns = []
            
            # Use the same calculation method as chart service metrics for consistency
            # This ensures Individual Asset Statistics match the Metrics section
            for i in range(1, len(points)):
                if (hasattr(points[i], 'value') and hasattr(points[i-1], 'value') and 
                    points[i].value is not None and points[i-1].value is not None and 
                    points[i-1].value != 0):
                    
                    # Use normalized values (same as metrics calculation)
                    # This ensures consistency with the main metrics section
                    period_return = (points[i].value - points[i-1].value) / points[i-1].value
                    
                    # Cap extreme returns to prevent unrealistic values
                    period_return = np.clip(period_return, -0.5, 0.5)  # ±50% max
                    
                    returns.append(period_return)
            
            if len(returns) >= 12:  # Need at least 12 periods of data
                monthly_returns[symbol] = returns
                logger.info(f"Extracted {len(returns)} normalized returns for {symbol} (consistent with metrics)")
            else:
                logger.warning(f"Insufficient returns for {symbol}: {len(returns)}")
        
        return monthly_returns
    
    def _calculate_portfolio_statistics(self, monthly_returns: Dict[str, List[float]]) -> Tuple[Optional[np.ndarray], Optional[np.ndarray]]:
        """Calculate expected returns and covariance matrix."""
        try:
            symbols = list(monthly_returns.keys())
            n_assets = len(symbols)
            
            if n_assets < 2:
                return None, None
            
            # Align all return series to the same length (use minimum length)
            min_length = min(len(returns) for returns in monthly_returns.values())
            aligned_returns = []
            
            for symbol in symbols:
                # Use the last min_length returns to align all series
                aligned_returns.append(monthly_returns[symbol][-min_length:])
            
            # Convert to numpy arrays
            returns_matrix = np.array(aligned_returns)
            
            # Calculate expected returns (mean monthly returns)
            expected_returns = np.mean(returns_matrix, axis=1)
            
            # Calculate covariance matrix (monthly)
            cov_matrix = np.cov(returns_matrix)
            
            # Validate and clean extreme values
            # Cap extreme returns to reasonable bounds (±50% monthly = ±600% annual)
            expected_returns = np.clip(expected_returns, -0.5, 0.5)
            
            # Ensure covariance matrix is positive definite
            # Add small regularization to diagonal if needed
            min_eigenvalue = np.min(np.linalg.eigvals(cov_matrix))
            if min_eigenvalue <= 0:
                regularization = abs(min_eigenvalue) + 1e-6
                cov_matrix += np.eye(n_assets) * regularization
                logger.warning(f"Added regularization {regularization:.6f} to covariance matrix")
            
            # Annualize the statistics
            expected_returns_annual = expected_returns * 12  # 12 months per year
            cov_matrix_annual = cov_matrix * 12  # Annualize covariance
            
            logger.info(f"Calculated portfolio statistics for {n_assets} assets")
            logger.info(f"Expected returns (annual): {expected_returns_annual}")
            logger.info(f"Covariance matrix shape: {cov_matrix_annual.shape}")
            
            return expected_returns_annual, cov_matrix_annual
            
        except Exception as e:
            logger.error(f"Error calculating portfolio statistics: {e}")
            return None, None
    
    def _calculate_min_risk_portfolio(self, expected_returns: np.ndarray, cov_matrix: np.ndarray) -> Dict[str, Any]:
        """Calculate minimum risk portfolio."""
        try:
            n_assets = len(expected_returns)
            
            # Objective function: minimize portfolio variance
            def objective(weights):
                return np.dot(weights.T, np.dot(cov_matrix, weights))
            
            # Constraints: weights sum to 1
            constraints = {'type': 'eq', 'fun': lambda x: np.sum(x) - 1}
            
            # Bounds: weights between 0 and 1 (no short selling)
            bounds = tuple((0, 1) for _ in range(n_assets))
            
            # Initial guess: equal weights
            x0 = np.array([1/n_assets] * n_assets)
            
            # Optimize
            result = minimize(objective, x0, method='SLSQP', bounds=bounds, constraints=constraints)
            
            if result.success:
                weights = result.x
                # Normalize weights to ensure they sum to 1 (handle numerical precision issues)
                weights = weights / np.sum(weights)
                portfolio_return = np.dot(weights, expected_returns)
                portfolio_risk = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
                
                # Ensure weights are properly formatted as floats
                weights_list = [float(w) for w in weights.tolist()]
                
                return {
                    'weights': weights_list,
                    'expected_return': float(portfolio_return),
                    'risk': float(portfolio_risk),
                    'sharpe_ratio': float(portfolio_return / portfolio_risk) if portfolio_risk > 0 else 0.0
                }
            else:
                logger.error(f"Min risk optimization failed: {result.message}")
                return {'error': 'Optimization failed'}
                
        except Exception as e:
            logger.error(f"Error calculating min risk portfolio: {e}")
            return {'error': str(e)}
    
    def _calculate_max_return_portfolio(self, expected_returns: np.ndarray, cov_matrix: np.ndarray) -> Dict[str, Any]:
        """Calculate maximum return portfolio."""
        try:
            n_assets = len(expected_returns)
            
            # Objective function: maximize portfolio return (minimize negative return)
            def objective(weights):
                return -np.dot(weights, expected_returns)
            
            # Constraints: weights sum to 1
            constraints = {'type': 'eq', 'fun': lambda x: np.sum(x) - 1}
            
            # Bounds: weights between 0 and 1 (no short selling)
            bounds = tuple((0, 1) for _ in range(n_assets))
            
            # Initial guess: equal weights
            x0 = np.array([1/n_assets] * n_assets)
            
            # Optimize
            result = minimize(objective, x0, method='SLSQP', bounds=bounds, constraints=constraints)
            
            if result.success:
                weights = result.x
                # Normalize weights to ensure they sum to 1 (handle numerical precision issues)
                weights = weights / np.sum(weights)
                portfolio_return = np.dot(weights, expected_returns)
                portfolio_risk = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
                
                # Ensure weights are properly formatted as floats
                weights_list = [float(w) for w in weights.tolist()]
                
                return {
                    'weights': weights_list,
                    'expected_return': float(portfolio_return),
                    'risk': float(portfolio_risk),
                    'sharpe_ratio': float(portfolio_return / portfolio_risk) if portfolio_risk > 0 else 0.0
                }
            else:
                logger.error(f"Max return optimization failed: {result.message}")
                return {'error': 'Optimization failed'}
                
        except Exception as e:
            logger.error(f"Error calculating max return portfolio: {e}")
            return {'error': str(e)}
    
    def _calculate_max_sharpe_portfolio(self, expected_returns: np.ndarray, cov_matrix: np.ndarray, 
                                       risk_free_rate: float) -> Dict[str, Any]:
        """Calculate maximum Sharpe ratio portfolio."""
        try:
            n_assets = len(expected_returns)
            
            # Objective function: minimize negative Sharpe ratio
            def objective(weights):
                portfolio_return = np.dot(weights, expected_returns)
                portfolio_risk = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
                if portfolio_risk == 0:
                    return float('inf')
                sharpe_ratio = (portfolio_return - risk_free_rate) / portfolio_risk
                return -sharpe_ratio  # Minimize negative Sharpe ratio
            
            # Constraints: weights sum to 1
            constraints = {'type': 'eq', 'fun': lambda x: np.sum(x) - 1}
            
            # Bounds: weights between 0 and 1 (no short selling)
            bounds = tuple((0, 1) for _ in range(n_assets))
            
            # Initial guess: equal weights
            x0 = np.array([1/n_assets] * n_assets)
            
            # Optimize
            result = minimize(objective, x0, method='SLSQP', bounds=bounds, constraints=constraints)
            
            if result.success:
                weights = result.x
                # Normalize weights to ensure they sum to 1 (handle numerical precision issues)
                weights = weights / np.sum(weights)
                portfolio_return = np.dot(weights, expected_returns)
                portfolio_risk = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
                sharpe_ratio = (portfolio_return - risk_free_rate) / portfolio_risk if portfolio_risk > 0 else 0.0
                
                # Ensure weights are properly formatted as floats
                weights_list = [float(w) for w in weights.tolist()]
                
                return {
                    'weights': weights_list,
                    'expected_return': float(portfolio_return),
                    'risk': float(portfolio_risk),
                    'sharpe_ratio': float(sharpe_ratio)
                }
            else:
                logger.error(f"Max Sharpe optimization failed: {result.message}")
                return {'error': 'Optimization failed'}
                
        except Exception as e:
            logger.error(f"Error calculating max Sharpe portfolio: {e}")
            return {'error': str(e)}
    
    def _calculate_efficient_frontier_curve(self, expected_returns: np.ndarray, cov_matrix: np.ndarray, 
                                           risk_free_rate: float) -> List[Dict[str, float]]:
        """Calculate Efficient Frontier curve points."""
        try:
            n_assets = len(expected_returns)
            
            # Get min and max expected returns
            min_return = np.min(expected_returns)
            max_return = np.max(expected_returns)
            
            # Create target returns between min and max
            target_returns = np.linspace(min_return, max_return, 50)
            
            efficient_frontier = []
            
            for target_return in target_returns:
                # Objective function: minimize portfolio variance
                def objective(weights):
                    return np.dot(weights.T, np.dot(cov_matrix, weights))
                
                # Constraints: weights sum to 1, expected return equals target
                constraints = [
                    {'type': 'eq', 'fun': lambda x: np.sum(x) - 1},
                    {'type': 'eq', 'fun': lambda x: np.dot(x, expected_returns) - target_return}
                ]
                
                # Bounds: weights between 0 and 1 (no short selling)
                bounds = tuple((0, 1) for _ in range(n_assets))
                
                # Initial guess: equal weights
                x0 = np.array([1/n_assets] * n_assets)
                
                # Optimize
                result = minimize(objective, x0, method='SLSQP', bounds=bounds, constraints=constraints)
                
                if result.success:
                    weights = result.x
                    portfolio_return = np.dot(weights, expected_returns)
                    portfolio_risk = np.sqrt(np.dot(weights.T, np.dot(cov_matrix, weights)))
                    sharpe_ratio = (portfolio_return - risk_free_rate) / portfolio_risk if portfolio_risk > 0 else 0.0
                    
                    efficient_frontier.append({
                        'expected_return': float(portfolio_return),
                        'risk': float(portfolio_risk),
                        'sharpe_ratio': float(sharpe_ratio)
                    })
            
            logger.info(f"Calculated {len(efficient_frontier)} Efficient Frontier points")
            return efficient_frontier
            
        except Exception as e:
            logger.error(f"Error calculating Efficient Frontier curve: {e}")
            return []
    
    def _calculate_individual_asset_stats(self, monthly_returns: Dict[str, List[float]], 
                                        risk_free_rate: float) -> Dict[str, Dict[str, float]]:
        """Calculate individual asset statistics using same method as metrics for consistency."""
        individual_stats = {}
        
        for symbol, returns in monthly_returns.items():
            try:
                # Calculate statistics using same method as chart service metrics
                mean_return = np.mean(returns)
                
                # Calculate variance and volatility using same method as metrics
                variance = np.var(returns)
                
                # Use same frequency logic as chart service (assuming monthly data for EF)
                frequency = 12  # Monthly frequency for efficient frontier
                volatility = np.sqrt(variance * frequency) if variance > 0 else 0
                
                # Calculate annualized return using same method as metrics
                # For efficient frontier, we assume monthly returns, so annualize by multiplying by 12
                annualized_return = mean_return * frequency
                
                # Cap extreme values to reasonable bounds
                annualized_return = np.clip(annualized_return, -6.0, 6.0)  # ±600% annual
                volatility = np.clip(volatility, 0.0, 3.0)  # Max 300% annual volatility
                
                # Calculate Sharpe ratio using same method as metrics
                sharpe_ratio = (annualized_return - risk_free_rate) / volatility if volatility > 0 else 0.0
                sharpe_ratio = np.clip(sharpe_ratio, -5.0, 5.0)  # Cap Sharpe ratio
                
                individual_stats[symbol] = {
                    'expected_return': float(annualized_return),
                    'risk': float(volatility),
                    'sharpe_ratio': float(sharpe_ratio),
                    'monthly_returns_count': len(returns)
                }
                
                logger.info(f"Individual stats for {symbol}: return={annualized_return:.4f}, risk={volatility:.4f}, sharpe={sharpe_ratio:.4f}")
                
            except Exception as e:
                logger.error(f"Error calculating stats for {symbol}: {e}")
                individual_stats[symbol] = {
                    'expected_return': 0.0,
                    'risk': 0.0,
                    'sharpe_ratio': 0.0,
                    'monthly_returns_count': 0
                }
        
        return individual_stats


# Global service instance
_efficient_frontier_service = None


def get_efficient_frontier_service() -> EfficientFrontierService:
    """Get the global Efficient Frontier service instance."""
    global _efficient_frontier_service
    if _efficient_frontier_service is None:
        _efficient_frontier_service = EfficientFrontierService()
    return _efficient_frontier_service


def calculate_efficient_frontier(symbols: List[str], chart_data: Dict[str, List[Any]], 
                               base_currency: str = 'USD', risk_free_rate: float = 0.02) -> Dict[str, Any]:
    """
    Convenience function to calculate Efficient Frontier.
    
    Args:
        symbols: List of asset symbols
        chart_data: Chart data from comparison service
        base_currency: Base currency for calculations
        risk_free_rate: Annual risk-free rate
        
    Returns:
        Dictionary with Efficient Frontier results
    """
    service = get_efficient_frontier_service()
    return service.calculate_efficient_frontier(symbols, chart_data, base_currency, risk_free_rate)
