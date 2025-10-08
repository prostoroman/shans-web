#!/usr/bin/env python3
"""
Example script demonstrating the new risk-free rate functionality.
Shows how to use currency-specific risk-free rates for Sharpe ratio calculations.
"""

import sys
import os
import django
from datetime import date

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'shans_web.settings')
django.setup()

from apps.markets.risk_free_rate_service import get_risk_free_rate, get_risk_free_rate_service
from apps.markets.chart_service import get_chart_service
from apps.markets.metrics import calculate_sharpe_ratio, calculate_volatility

def demonstrate_risk_free_rates():
    """Demonstrate the risk-free rate service."""
    
    print("=== Risk-Free Rate Service Demo ===")
    
    service = get_risk_free_rate_service()
    
    # Show supported currencies
    print(f"Supported currencies: {len(service.get_supported_currencies())}")
    print("Major currencies:")
    for currency in ['USD', 'EUR', 'GBP', 'JPY', 'CHF']:
        rate = get_risk_free_rate(currency)
        print(f"  {currency}: {rate:.4f} ({rate*100:.2f}%)")
    
    print()

def demonstrate_currency_specific_sharpe():
    """Demonstrate currency-specific Sharpe ratio calculations."""
    
    print("=== Currency-Specific Sharpe Ratio Demo ===")
    
    # Sample returns data (weekly returns for 6 months)
    returns = [
        0.02, -0.01, 0.03, -0.02, 0.01, 0.04, -0.01, 0.02, 0.01, -0.03,
        0.02, 0.01, -0.01, 0.03, 0.01, -0.02, 0.02, 0.01, 0.01, -0.01,
        0.02, 0.01, 0.01, -0.01, 0.02, 0.01
    ]
    
    frequency = 52  # Weekly data
    
    print("Sharpe ratios for the same returns with different currency risk-free rates:")
    for currency in ['USD', 'EUR', 'GBP', 'JPY']:
        sharpe = calculate_sharpe_ratio(returns, frequency=frequency, currency=currency)
        risk_free = get_risk_free_rate(currency)
        volatility = calculate_volatility(returns, frequency)
        
        print(f"  {currency}: Sharpe = {sharpe:.4f}, Risk-free = {risk_free:.4f}, Volatility = {volatility:.4f}")
    
    print()

def demonstrate_chart_service_integration():
    """Demonstrate the chart service with risk-free rates."""
    
    print("=== Chart Service Integration Demo ===")
    
    chart_service = get_chart_service()
    
    # Compare GOOGL YTD with risk-free rates
    result = chart_service.compare_assets(
        symbols=['GOOGL'],
        base_currency='USD',
        include_dividends=True,
        period='YTD',
        normalize_mode='index100'
    )
    
    if result.get('success'):
        metrics = result.get('metrics', {}).get('GOOGL', {})
        print("GOOGL YTD Performance (with USD risk-free rate):")
        print(f"  Total Return: {metrics.get('total_return', 0)*100:.2f}%")
        print(f"  Annualized Return: {metrics.get('annualized_return', 0)*100:.2f}%")
        print(f"  Volatility: {metrics.get('volatility', 0)*100:.2f}%")
        print(f"  Sharpe Ratio: {metrics.get('sharpe_ratio', 0):.4f}")
        print(f"  Max Drawdown: {metrics.get('max_drawdown', 0)*100:.2f}%")
    else:
        print(f"Error: {result.get('error', 'Unknown error')}")
    
    print()

def demonstrate_ytd_vs_other_periods():
    """Demonstrate YTD vs other period risk-free rate handling."""
    
    print("=== YTD vs Other Periods Demo ===")
    
    service = get_risk_free_rate_service()
    
    # Compare YTD vs 1-year rates
    usd_ytd = service.get_risk_free_rate_for_ytd('USD')
    usd_current = service.get_risk_free_rate('USD')
    
    print(f"USD Risk-free rates:")
    print(f"  Current: {usd_current:.4f} ({usd_current*100:.2f}%)")
    print(f"  YTD (mid-year): {usd_ytd:.4f} ({usd_ytd*100:.2f}%)")
    
    # Show how this affects Sharpe ratio calculations
    print("\nNote: YTD Sharpe ratios use mid-year risk-free rates for consistency")
    print("while other periods use rates from the middle of their respective periods.")

if __name__ == '__main__':
    demonstrate_risk_free_rates()
    demonstrate_currency_specific_sharpe()
    demonstrate_chart_service_integration()
    demonstrate_ytd_vs_other_periods()
    
    print("=== Summary ===")
    print("✓ Risk-free rate service supports 32+ currencies")
    print("✓ Currency-specific Sharpe ratio calculations")
    print("✓ FMP Treasury Rates API integration with fallbacks")
    print("✓ YTD and period-specific risk-free rate handling")
    print("✓ Chart service integration with automatic currency detection")
