#!/usr/bin/env python
"""
Test script to analyze comparison performance for P911.DE and CHIP.L
"""

import os
import sys
import django
import time
import logging

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'shans_web.settings')
django.setup()

from apps.markets.comparison_service import get_comparison_service

# Set up logging to see what's happening
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_comparison_performance():
    """Test the comparison performance for P911.DE and CHIP.L"""
    
    symbols = ['P911.DE', 'CHIP.L']
    base_currency = 'EUR'
    period = '1Y'
    
    print(f'Testing comparison for {symbols} with {base_currency} base currency and {period} period...')
    print('Starting comparison...')
    
    start_time = time.time()
    
    try:
        comparison_service = get_comparison_service()
        result = comparison_service.compare_assets(
            symbols=symbols,
            base_currency=base_currency,
            include_dividends=True,
            period=period,
            normalize_mode='index100'
        )
        
        end_time = time.time()
        
        print(f'Comparison completed in {end_time - start_time:.2f} seconds')
        print(f'Result type: {type(result)}')
        
        if isinstance(result, dict):
            print(f'Result keys: {list(result.keys())}')
            if 'error' in result:
                print(f'Error: {result["error"]}')
            elif 'successful_symbols' in result:
                print(f'Successful symbols: {result["successful_symbols"]}')
                print(f'Failed symbols: {result.get("failed_symbols", [])}')
                
                # Check if we have chart data
                if 'chart_data' in result:
                    chart_data = result['chart_data']
                    print(f'Chart data keys: {list(chart_data.keys()) if chart_data else "None"}')
                    if chart_data:
                        for symbol, data in chart_data.items():
                            print(f'  {symbol}: {len(data)} data points')
        else:
            print(f'Unexpected result type: {result}')
            
    except Exception as e:
        end_time = time.time()
        print(f'Error occurred after {end_time - start_time:.2f} seconds: {e}')
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_comparison_performance()
