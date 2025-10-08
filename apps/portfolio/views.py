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
from .enhanced_service import get_portfolio_service

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
    """Process portfolio analysis form submission using enhanced service."""
    try:
        # Get form data
        symbols = request.POST.get('symbols', '').strip()
        weights = request.POST.get('weights', '').strip()
        analysis_type = request.POST.get('analysis_type', 'basic')
        base_currency = request.POST.get('base_currency', 'USD').upper()
        include_dividends = request.POST.get('include_dividends', 'true').lower() == 'true'
        days = int(request.POST.get('days', 365))
        
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
        
        # Use enhanced portfolio service
        portfolio_service = get_portfolio_service()
        analysis_result = portfolio_service.analyze_portfolio(
            symbol_list, weight_list, base_currency, include_dividends, days
        )
        
        if 'error' in analysis_result:
            messages.error(request, analysis_result['error'])
            return redirect('portfolio:form')
        
        # Generate forecast
        forecast_results = {}
        if analysis_type in ['advanced', 'pro']:
            # Use existing forecast function with aligned returns
            returns_matrix = []
            for symbol in symbol_list:
                # Get returns from analysis result
                if symbol in analysis_result.get('asset_metrics', {}):
                    # We need to get the actual returns for forecasting
                    from apps.markets.assets import AssetFactory
                    asset = AssetFactory.create_asset(symbol)
                    price_history = asset.get_price_history(days)
                    if price_history:
                        returns = []
                        price_history.sort(key=lambda x: x.get('date', ''))
                        for i in range(1, len(price_history)):
                            prev_price = float(price_history[i-1].get('price', price_history[i-1].get('close', 0)))
                            curr_price = float(price_history[i].get('price', price_history[i].get('close', 0)))
                            if prev_price > 0:
                                returns.append((curr_price - prev_price) / prev_price)
                        returns_matrix.append(returns)
            
            if returns_matrix:
                # Align returns
                min_length = min(len(returns) for returns in returns_matrix)
                aligned_returns = [returns[:min_length] for returns in returns_matrix]
                
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
                'metrics': analysis_result.get('portfolio_metrics', {}),
                'optimization': analysis_result.get('optimization_results', {}),
            }
            commentary = generate_portfolio_commentary(portfolio_data, user_plan)
        
        # Save portfolio for authenticated users
        saved_portfolio = None
        if request.user.is_authenticated:
            try:
                portfolio_metrics = analysis_result.get('portfolio_metrics', {})
                saved_portfolio = Portfolio.objects.create(
                    user=request.user,
                    name=f"Analysis {len(symbol_list)} assets",
                    expected_return=portfolio_metrics.get('expected_return'),
                    volatility=portfolio_metrics.get('volatility'),
                    sharpe_ratio=portfolio_metrics.get('sharpe_ratio'),
                    max_drawdown=portfolio_metrics.get('max_drawdown')
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
            'base_currency': base_currency,
            'include_dividends': include_dividends,
            'days': days,
            'analysis_result': analysis_result,
            'portfolio_metrics': analysis_result.get('portfolio_metrics', {}),
            'asset_metrics': analysis_result.get('asset_metrics', {}),
            'optimization_results': analysis_result.get('optimization_results', {}),
            'correlation_matrix': analysis_result.get('correlation_matrix', {}),
            'forecast_results': forecast_results,
            'commentary': commentary,
            'saved_portfolio': saved_portfolio,
        }
        
        return render(request, 'portfolio/result.html', context)
        
    except Exception as e:
        logger.error(f"Error processing portfolio analysis: {e}")
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
    except Exception as e:
        logger.error(f"Error deleting portfolio: {e}")
        messages.error(request, _('Error deleting portfolio'))
    
    return redirect('portfolio:list')