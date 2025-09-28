"""
Portfolio views for analysis and optimization.
"""

from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods
from django.utils.translation import gettext_lazy as _
from django.conf import settings
import logging

from .models import Portfolio, PortfolioPosition
from .mpt import (
    calculate_mean_returns, calculate_covariance_matrix,
    optimize_portfolio, calculate_efficient_frontier,
    calculate_minimum_variance_portfolio, calculate_tangency_portfolio
)
from .forecast import calculate_portfolio_forecast
from .llm import generate_portfolio_commentary
from apps.data.services import get_instrument_data

logger = logging.getLogger(__name__)


def portfolio_form(request):
    """Portfolio analysis form."""
    if request.method == 'POST':
        return _process_portfolio_analysis(request)
    
    context = {
        'title': _('Portfolio Analysis'),
    }
    return render(request, 'portfolio/form.html', context)


def _process_portfolio_analysis(request):
    """Process portfolio analysis form submission."""
    try:
        # Get form data
        symbols = request.POST.get('symbols', '').strip()
        weights = request.POST.get('weights', '').strip()
        analysis_type = request.POST.get('analysis_type', 'basic')
        
        if not symbols or not weights:
            messages.error(request, _('Symbols and weights are required'))
            return redirect('portfolio:form')
        
        # Parse symbols and weights
        symbol_list = [s.strip().upper() for s in symbols.split(',') if s.strip()]
        weight_list = [float(w.strip()) for w in weights.split(',') if w.strip()]
        
        if len(symbol_list) != len(weight_list):
            messages.error(request, _('Number of symbols and weights must match'))
            return redirect('portfolio:form')
        
        # Check if weights sum to 1
        total_weight = sum(weight_list)
        if abs(total_weight - 1.0) > 0.01:
            messages.error(request, _('Weights must sum to 1.0'))
            return redirect('portfolio:form')
        
        # Get price data for all symbols
        returns_matrix = []
        instruments_data = {}
        
        for symbol in symbol_list:
            data = get_instrument_data(symbol, include_prices=True)
            if not data or not data['prices']:
                messages.error(request, _('No price data available for {}').format(symbol))
                return redirect('portfolio:form')
            
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
            # Minimum variance portfolio
            min_var_result = calculate_minimum_variance_portfolio(cov_matrix)
            if min_var_result.get('success'):
                optimization_results['minimum_variance'] = min_var_result
            
            # Tangency portfolio (max Sharpe)
            tangency_result = calculate_tangency_portfolio(mean_returns, cov_matrix, settings.DEFAULT_RF)
            if tangency_result.get('success'):
                optimization_results['tangency'] = tangency_result
            
            # Efficient frontier
            efficient_frontier = calculate_efficient_frontier(mean_returns, cov_matrix, num_portfolios=50)
            optimization_results['efficient_frontier'] = efficient_frontier
        
        # Current portfolio metrics
        current_metrics = {
            'expected_return': sum(weight_list[i] * mean_returns[i] for i in range(len(weight_list))),
            'volatility': 0.0,  # Calculate portfolio volatility
        }
        
        # Calculate portfolio volatility
        portfolio_variance = 0
        for i in range(len(weight_list)):
            for j in range(len(weight_list)):
                portfolio_variance += weight_list[i] * weight_list[j] * cov_matrix[i][j]
        
        current_metrics['volatility'] = portfolio_variance ** 0.5
        current_metrics['sharpe_ratio'] = (current_metrics['expected_return'] - settings.DEFAULT_RF) / current_metrics['volatility']
        
        # Generate forecast
        forecast_results = {}
        if analysis_type in ['advanced', 'pro']:
            forecast_results = calculate_portfolio_forecast(
                weight_list, aligned_returns, periods=30, method='ewma'
            )
        
        # Generate LLM commentary
        commentary = None
        if request.user.is_authenticated:
            user_plan = request.user.profile.status
            portfolio_data = {
                'positions': [
                    {'symbol': symbol, 'weight': weight}
                    for symbol, weight in zip(symbol_list, weight_list)
                ],
                'metrics': current_metrics,
                'optimization': optimization_results,
            }
            commentary = generate_portfolio_commentary(portfolio_data, user_plan)
        
        # Save portfolio for authenticated users
        saved_portfolio = None
        if request.user.is_authenticated:
            try:
                saved_portfolio = Portfolio.objects.create(
                    user=request.user,
                    name=f"Analysis {len(symbol_list)} symbols",
                    expected_return=current_metrics['expected_return'],
                    volatility=current_metrics['volatility'],
                    sharpe_ratio=current_metrics['sharpe_ratio']
                )
                
                # Create positions
                for symbol, weight in zip(symbol_list, weight_list):
                    PortfolioPosition.objects.create(
                        portfolio=saved_portfolio,
                        symbol=symbol,
                        weight=weight
                    )
            except Exception as e:
                logger.error(f"Error saving portfolio: {e}")
        
        context = {
            'title': _('Portfolio Analysis Results'),
            'symbols': symbol_list,
            'weights': weight_list,
            'instruments_data': instruments_data,
            'current_metrics': current_metrics,
            'optimization_results': optimization_results,
            'forecast_results': forecast_results,
            'commentary': commentary,
            'saved_portfolio': saved_portfolio,
            'analysis_type': analysis_type,
        }
        
        return render(request, 'portfolio/result.html', context)
        
    except Exception as e:
        logger.error(f"Error in portfolio analysis: {e}")
        messages.error(request, _('Error processing portfolio analysis'))
        return redirect('portfolio:form')


@login_required
def portfolio_list(request):
    """List user's saved portfolios."""
    portfolios = Portfolio.objects.filter(user=request.user).order_by('-created_at')
    
    context = {
        'title': _('My Portfolios'),
        'portfolios': portfolios,
    }
    
    return render(request, 'portfolio/list.html', context)


@login_required
def portfolio_detail(request, portfolio_id):
    """View portfolio details."""
    portfolio = Portfolio.objects.get(id=portfolio_id, user=request.user)
    positions = portfolio.positions.all()
    
    context = {
        'title': f'Portfolio: {portfolio.name}',
        'portfolio': portfolio,
        'positions': positions,
    }
    
    return render(request, 'portfolio/detail.html', context)


@login_required
@require_http_methods(["POST"])
def delete_portfolio(request, portfolio_id):
    """Delete a portfolio."""
    try:
        portfolio = Portfolio.objects.get(id=portfolio_id, user=request.user)
        portfolio.delete()
        messages.success(request, _('Portfolio deleted successfully'))
    except Portfolio.DoesNotExist:
        messages.error(request, _('Portfolio not found'))
    
    return redirect('portfolio:list')