#!/usr/bin/env python3
"""
Debug script to check why metrics are not showing in comparison.
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

from apps.markets.comparison_service import get_comparison_service
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def debug_comparison_result():
    """Debug the comparison result to see what's missing."""
    
    print("Debugging comparison result...")
    
    comparison_service = get_comparison_service()
    
    # Test with GOOGL and AAPL
    symbols = ['GOOGL', 'AAPL']
    
    try:
        result = comparison_service.compare_assets(
            symbols=symbols,
            base_currency='USD',
            include_dividends=True,
            period='YTD',
            normalize_mode='index100'
        )
        
        print(f"Result type: {type(result)}")
        print(f"Result keys: {list(result.keys()) if isinstance(result, dict) else 'Not a dict'}")
        
        if isinstance(result, dict):
            print(f"Success: {result.get('success', 'Not found')}")
            print(f"Error: {result.get('error', 'Not found')}")
            print(f"Metrics: {result.get('metrics', 'Not found')}")
            print(f"Chart data: {result.get('chart_data', 'Not found')}")
            print(f"Assets: {result.get('assets', 'Not found')}")
            
            if 'metrics' in result:
                print(f"Metrics type: {type(result['metrics'])}")
                print(f"Metrics keys: {list(result['metrics'].keys()) if isinstance(result['metrics'], dict) else 'Not a dict'}")
                
                for symbol in symbols:
                    if symbol in result['metrics']:
                        print(f"{symbol} metrics: {result['metrics'][symbol]}")
                    else:
                        print(f"{symbol} metrics: Not found")
            
            if 'chart_data' in result:
                print(f"Chart data type: {type(result['chart_data'])}")
                print(f"Chart data keys: {list(result['chart_data'].keys()) if isinstance(result['chart_data'], dict) else 'Not a dict'}")
        
    except Exception as e:
        print(f"Error during comparison: {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    debug_comparison_result()
