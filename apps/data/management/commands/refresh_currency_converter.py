"""
Management command to refresh the currency converter cache.
"""

import logging
from django.core.management.base import BaseCommand
from apps.markets.smart_currency_converter import refresh_smart_currency_converter

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Refresh the currency converter cache'

    def add_arguments(self, parser):
        parser.add_argument(
            '--test-conversion',
            action='store_true',
            help='Test a sample conversion after refresh',
        )

    def handle(self, *args, **options):
        self.stdout.write('Refreshing currency converter cache...')
        
        try:
            # Refresh the converter
            converter = refresh_smart_currency_converter()
            
            self.stdout.write(
                self.style.SUCCESS('Successfully refreshed currency converter cache')
            )
            
            # Test conversion if requested
            if options['test_conversion']:
                self.stdout.write('Testing currency conversion...')
                
                from decimal import Decimal
                
                # Test RUB to USD conversion
                rate = converter.get_exchange_rate('RUB', 'USD')
                if rate:
                    self.stdout.write(f'RUB to USD rate: {rate}')
                    
                    # Test amount conversion
                    amount = converter.convert_amount(Decimal('100'), 'RUB', 'USD')
                    if amount:
                        self.stdout.write(f'100 RUB = {amount} USD')
                    else:
                        self.stdout.write(self.style.ERROR('Amount conversion failed'))
                else:
                    self.stdout.write(self.style.ERROR('Rate conversion failed'))
                
                # Test EUR to USD conversion
                rate = converter.get_exchange_rate('EUR', 'USD')
                if rate:
                    self.stdout.write(f'EUR to USD rate: {rate}')
                else:
                    self.stdout.write(self.style.ERROR('EUR to USD conversion failed'))
            
        except Exception as e:
            logger.error(f'Error refreshing currency converter: {e}')
            raise BaseCommand.CommandError(f'Failed to refresh currency converter: {e}')
