"""
Enhanced comparison service for multiple asset types.
"""

import logging
from typing import Dict, List, Optional, Any, Tuple
from decimal import Decimal
from datetime import date, timedelta

from .chart_service import get_chart_service
from .efficient_frontier import get_efficient_frontier_service
from .risk_free_rate_service import get_risk_free_rate_service

logger = logging.getLogger(__name__)


class AssetComparisonService:
    """Service for comparing multiple asset types."""
    
    def __init__(self):
        self.efficient_frontier_service = get_efficient_frontier_service()
        self.risk_free_rate_service = get_risk_free_rate_service()
    
    def compare_assets(self, symbols: List[str], base_currency: str = 'USD', 
                     include_dividends: bool = True, period: str = '1Y',
                     normalize_mode: str = 'index100') -> Dict[str, Any]:
        """
        Compare multiple assets using the enhanced chart service.
        
        Args:
            symbols: List of asset symbols
            base_currency: Base currency for normalization
            include_dividends: Whether to include dividends in returns
            period: Period preset (1M, 3M, 6M, YTD, 1Y, 3Y, 5Y, 10Y, MAX)
            normalize_mode: Normalization mode (index100, percent_change)
            
        Returns:
            Dictionary with comparison results
        """
        try:
            # Use the enhanced chart service
            chart_service = get_chart_service()
            result = chart_service.compare_assets(
                symbols=symbols,
                base_currency=base_currency,
                include_dividends=include_dividends,
                period=period,
                normalize_mode=normalize_mode
            )
            
            # Add Efficient Frontier calculation if we have successful results
            if result.get('success') and len(result.get('successful_symbols', [])) >= 2:
                try:
                    # Get risk-free rate for the base currency
                    risk_free_rate = self.risk_free_rate_service.get_risk_free_rate(base_currency)
                    
                    # Calculate Efficient Frontier
                    efficient_frontier = self.efficient_frontier_service.calculate_efficient_frontier(
                        symbols=result['successful_symbols'],
                        chart_data=result['chart_data'],
                        base_currency=base_currency,
                        risk_free_rate=risk_free_rate
                    )
                    
                    result['efficient_frontier'] = efficient_frontier
                    logger.info(f"Efficient Frontier calculation completed: {efficient_frontier.get('success', False)}")
                except Exception as e:
                    logger.error(f"Error calculating Efficient Frontier: {e}")
                    result['efficient_frontier'] = {'error': str(e)}
            else:
                result['efficient_frontier'] = None
            
            return result
            
        except Exception as e:
            logger.error(f"Error comparing assets: {e}")
            return {'error': str(e)}


# Global service instance
_comparison_service = None


def get_comparison_service() -> AssetComparisonService:
    """Get the global comparison service instance."""
    global _comparison_service
    if _comparison_service is None:
        _comparison_service = AssetComparisonService()
    return _comparison_service


def compare_assets(symbols: List[str], base_currency: str = 'USD', 
                  include_dividends: bool = True, period: str = '1Y',
                  normalize_mode: str = 'index100') -> Dict[str, Any]:
    """
    Convenience function to compare assets.
    
    Args:
        symbols: List of asset symbols
        base_currency: Base currency for normalization
        include_dividends: Whether to include dividends in returns
        period: Period preset (1M, 3M, 6M, YTD, 1Y, 3Y, 5Y, 10Y, MAX)
        normalize_mode: Normalization mode (index100, percent_change)
        
    Returns:
        Dictionary with comparison results
    """
    service = get_comparison_service()
    return service.compare_assets(symbols, base_currency, include_dividends, period, normalize_mode)