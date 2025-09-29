"""
Portfolio API views for DRF endpoints.
"""

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, serializers
from rest_framework.permissions import IsAuthenticated
from django.utils.translation import gettext_lazy as _
import logging

from .models import Portfolio, PortfolioPosition
from .mpt import (
    calculate_mean_returns, calculate_covariance_matrix,
    optimize_portfolio, calculate_efficient_frontier
)
from .forecast import calculate_portfolio_forecast
from .llm import generate_portfolio_commentary
from apps.data.services import get_instrument_data
from django.conf import settings
from apps.core.throttling import PlanRateThrottle, BasicAnonThrottle
from apps.analytics.metrics import diversification_score

logger = logging.getLogger(__name__)


class PortfolioAnalyzeAPIView(APIView):
    """POST /api/v1/portfolio/analyze"""
    throttle_classes = [PlanRateThrottle, BasicAnonThrottle]

    class Payload(serializers.Serializer):
        weights = serializers.DictField(child=serializers.FloatField(min_value=0.0))
        benchmark = serializers.CharField(required=False, allow_blank=True)

    def post(self, request):
        """Analyze a portfolio."""
        try:
            payload = self.Payload(data=request.data)
            payload.is_valid(raise_exception=True)
            weights_map = payload.validated_data['weights']
            symbols = list(weights_map.keys())
            weights = list(weights_map.values())
            analysis_type = 'basic'
            
            if not symbols or not weights:
                return Response(
                    {'error': _('Symbols and weights are required')},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            if len(symbols) != len(weights):
                return Response(
                    {'error': _('Number of symbols and weights must match')},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Check if weights sum to 1
            total_weight = sum(weights)
            if abs(total_weight - 1.0) > 0.01:
                return Response(
                    {'error': _('Weights must sum to 1.0')},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Get price data for all symbols
            returns_matrix = []
            instruments_data = {}
            
            for symbol in symbols:
                data = get_instrument_data(symbol, include_prices=True)
                if not data or not data['prices']:
                    return Response(
                        {'error': _('No price data available for {}').format(symbol)},
                        status=status.HTTP_400_BAD_REQUEST
                    )
                
                instruments_data[symbol] = data
                prices = [float(p.close_price) for p in data['prices']]
                
                # Calculate returns
                returns = []
                for i in range(1, len(prices)):
                    ret = (prices[i] - prices[i-1]) / prices[i-1]
                    returns.append(ret)
                
                returns_matrix.append(returns)
            
            # Align returns (use minimum length)
            min_length = min(len(returns) for returns in returns_matrix)
            aligned_returns = [returns[:min_length] for returns in returns_matrix]
            
            # Calculate portfolio metrics
            mean_returns = calculate_mean_returns(aligned_returns)
            cov_matrix = calculate_covariance_matrix(aligned_returns)
            
            # Portfolio optimization
            optimization_results = {}
            
            if analysis_type in ['advanced', 'pro']:
                # Efficient frontier
                efficient_frontier = calculate_efficient_frontier(mean_returns, cov_matrix, num_portfolios=50)
                optimization_results['efficient_frontier'] = efficient_frontier
            
            # Current portfolio metrics
            current_metrics = {
                'expected_return': sum(weights[i] * mean_returns[i] for i in range(len(weights))),
                'volatility': 0.0,
            }
            
            # Calculate portfolio volatility
            portfolio_variance = 0
            for i in range(len(weights)):
                for j in range(len(weights)):
                    portfolio_variance += weights[i] * weights[j] * cov_matrix[i][j]
            
            current_metrics['volatility'] = portfolio_variance ** 0.5
            current_metrics['sharpe_ratio'] = (current_metrics['expected_return'] - settings.DEFAULT_RF) / current_metrics['volatility']
            
            # Generate forecast
            forecast_results = {}
            if analysis_type in ['advanced', 'pro']:
                forecast_results = calculate_portfolio_forecast(
                    weights, aligned_returns, periods=30, method='ewma'
                )
            
            # Diversification score (corr matrix simple proxy using cov -> corr)
            corr = []
            for i in range(len(weights)):
                row = []
                for j in range(len(weights)):
                    try:
                        row.append(cov_matrix[i][j] / ((cov_matrix[i][i] ** 0.5) * (cov_matrix[j][j] ** 0.5)))
                    except Exception:
                        row.append(0.0)
                corr.append(row)
            div_score = diversification_score(corr)
            
            # Prepare response
            response_data = {
                'symbols': symbols,
                'weights': {s: w for s, w in zip(symbols, weights)},
                'current_metrics': current_metrics,
                'optimization_results': optimization_results,
                'forecast_results': forecast_results,
                'diversification_score': div_score,
                'rebalance': 'Consider trimming the overweight, highly correlated asset to improve Sharpe.',
            }
            
            return Response(response_data)
            
        except Exception as e:
            logger.error(f"Error in portfolio analysis API: {e}")
            return Response(
                {'error': _('Internal server error')},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PortfolioListAPIView(APIView):
    """Portfolio list API endpoint."""
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Get user's portfolios."""
        portfolios = Portfolio.objects.filter(user=request.user).order_by('-created_at')
        
        portfolio_data = []
        for portfolio in portfolios:
            positions = portfolio.positions.all()
            portfolio_data.append({
                'id': portfolio.id,
                'name': portfolio.name,
                'description': portfolio.description,
                'created_at': portfolio.created_at.isoformat(),
                'expected_return': float(portfolio.expected_return) if portfolio.expected_return else None,
                'volatility': float(portfolio.volatility) if portfolio.volatility else None,
                'sharpe_ratio': float(portfolio.sharpe_ratio) if portfolio.sharpe_ratio else None,
                'positions': [
                    {
                        'symbol': pos.symbol,
                        'weight': float(pos.weight),
                        'shares': float(pos.shares) if pos.shares else None,
                        'price': float(pos.price) if pos.price else None,
                    }
                    for pos in positions
                ]
            })
        
        return Response({'portfolios': portfolio_data})


class PortfolioDetailAPIView(APIView):
    """Portfolio detail API endpoint."""
    permission_classes = [IsAuthenticated]
    
    def get(self, request, portfolio_id):
        """Get portfolio details."""
        try:
            portfolio = Portfolio.objects.get(id=portfolio_id, user=request.user)
            positions = portfolio.positions.all()
            
            portfolio_data = {
                'id': portfolio.id,
                'name': portfolio.name,
                'description': portfolio.description,
                'created_at': portfolio.created_at.isoformat(),
                'updated_at': portfolio.updated_at.isoformat(),
                'expected_return': float(portfolio.expected_return) if portfolio.expected_return else None,
                'volatility': float(portfolio.volatility) if portfolio.volatility else None,
                'sharpe_ratio': float(portfolio.sharpe_ratio) if portfolio.sharpe_ratio else None,
                'max_drawdown': float(portfolio.max_drawdown) if portfolio.max_drawdown else None,
                'positions': [
                    {
                        'symbol': pos.symbol,
                        'weight': float(pos.weight),
                        'shares': float(pos.shares) if pos.shares else None,
                        'price': float(pos.price) if pos.price else None,
                    }
                    for pos in positions
                ]
            }
            
            return Response(portfolio_data)
            
        except Portfolio.DoesNotExist:
            return Response(
                {'error': _('Portfolio not found')},
                status=status.HTTP_404_NOT_FOUND
            )