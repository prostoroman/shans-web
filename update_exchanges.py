#!/usr/bin/env python
"""
Script to update exchange data from Financial Modeling Prep API.
This can be run periodically (e.g., daily) to keep exchange data up to date.

Usage:
    python update_exchanges.py --api-key YOUR_API_KEY
    python update_exchanges.py --api-key YOUR_API_KEY --dry-run
"""

import os
import sys
import django

# Add the project root to Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'shans_web.settings')
django.setup()

from django.core.management import call_command

if __name__ == '__main__':
    import argparse
    
    parser = argparse.ArgumentParser(description='Update exchange data from FMP API')
    parser.add_argument('--api-key', required=True, help='FMP API key')
    parser.add_argument('--dry-run', action='store_true', help='Show what would be updated without making changes')
    
    args = parser.parse_args()
    
    try:
        call_command('update_exchanges', api_key=args.api_key, dry_run=args.dry_run)
        print("Exchange data update completed successfully!")
    except Exception as e:
        print(f"Error updating exchange data: {e}")
        sys.exit(1)
