"""
Management command to load price data for symbols.
"""

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.data.services import ensure_prices, ensure_fundamentals


class Command(BaseCommand):
    help = 'Load price and fundamental data for specified symbols'

    def add_arguments(self, parser):
        parser.add_argument(
            '--symbols',
            type=str,
            help='Comma-separated list of symbols to load',
            default='AAPL,MSFT,GOOGL,AMZN,TSLA'
        )
        parser.add_argument(
            '--days',
            type=int,
            help='Number of days of historical data to load',
            default=1825
        )
        parser.add_argument(
            '--fundamentals',
            action='store_true',
            help='Also load fundamental data',
        )

    def handle(self, *args, **options):
        symbols = [s.strip().upper() for s in options['symbols'].split(',')]
        days = options['days']
        load_fundamentals = options['fundamentals']

        self.stdout.write(
            self.style.SUCCESS(f'Loading data for {len(symbols)} symbols...')
        )

        success_count = 0
        for symbol in symbols:
            try:
                self.stdout.write(f'Loading {symbol}...')
                
                # Load price data
                if ensure_prices(symbol, days):
                    self.stdout.write(
                        self.style.SUCCESS(f'✓ Price data loaded for {symbol}')
                    )
                    success_count += 1
                else:
                    self.stdout.write(
                        self.style.ERROR(f'✗ Failed to load price data for {symbol}')
                    )
                
                # Load fundamental data if requested
                if load_fundamentals:
                    if ensure_fundamentals(symbol):
                        self.stdout.write(
                            self.style.SUCCESS(f'✓ Fundamental data loaded for {symbol}')
                        )
                    else:
                        self.stdout.write(
                            self.style.WARNING(f'⚠ Failed to load fundamental data for {symbol}')
                        )
                        
            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'✗ Error loading {symbol}: {e}')
                )

        self.stdout.write(
            self.style.SUCCESS(f'Completed! Successfully loaded {success_count}/{len(symbols)} symbols')
        )