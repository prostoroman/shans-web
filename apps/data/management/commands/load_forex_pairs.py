"""
Management command to load forex currency pairs from FMP API into the database.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.translation import gettext_lazy as _

from apps.data.models import Forex
from apps.data.fmp_client import get_forex_list

import logging

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Load forex currency pairs from FMP API into the database'

    def add_arguments(self, parser):
        parser.add_argument(
            '--clear',
            action='store_true',
            help='Clear existing forex pairs before loading new ones',
        )
        parser.add_argument(
            '--update',
            action='store_true',
            help='Update existing forex pairs with new data',
        )

    def handle(self, *args, **options):
        try:
            # Get forex pairs from FMP API
            self.stdout.write('Fetching forex pairs from FMP API...')
            forex_pairs = get_forex_list()
            
            if not forex_pairs:
                raise CommandError('No forex pairs received from FMP API')
            
            self.stdout.write(f'Received {len(forex_pairs)} forex pairs from FMP API')
            
            # Clear existing data if requested
            if options['clear']:
                self.stdout.write('Clearing existing forex pairs...')
                Forex.objects.all().delete()
                self.stdout.write(self.style.SUCCESS('Cleared existing forex pairs'))
            
            # Process forex pairs
            created_count = 0
            updated_count = 0
            
            with transaction.atomic():
                for pair_data in forex_pairs:
                    symbol = pair_data.get('symbol', '').upper()
                    if not symbol:
                        continue
                    
                    # Extract data
                    name = pair_data.get('name', '')
                    base_currency = pair_data.get('base_currency', '')
                    quote_currency = pair_data.get('quote_currency', '')
                    from_currency = pair_data.get('from_currency', '')
                    to_currency = pair_data.get('to_currency', '')
                    from_name = pair_data.get('from_name', '')
                    to_name = pair_data.get('to_name', '')
                    
                    # Create or update forex pair
                    forex_pair, created = Forex.objects.get_or_create(
                        symbol=symbol,
                        defaults={
                            'name': name,
                            'base_currency': base_currency,
                            'quote_currency': quote_currency,
                            'from_currency': from_currency,
                            'to_currency': to_currency,
                            'from_name': from_name,
                            'to_name': to_name,
                            'exchange': 'FOREX',
                            'is_active': True,
                        }
                    )
                    
                    if created:
                        created_count += 1
                        self.stdout.write(f'Created: {symbol} - {name}')
                    elif options['update']:
                        # Update existing pair
                        forex_pair.name = name
                        forex_pair.base_currency = base_currency
                        forex_pair.quote_currency = quote_currency
                        forex_pair.from_currency = from_currency
                        forex_pair.to_currency = to_currency
                        forex_pair.from_name = from_name
                        forex_pair.to_name = to_name
                        forex_pair.exchange = 'FOREX'
                        forex_pair.is_active = True
                        forex_pair.save()
                        updated_count += 1
                        self.stdout.write(f'Updated: {symbol} - {name}')
            
            # Report results
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully processed {len(forex_pairs)} forex pairs: '
                    f'{created_count} created, {updated_count} updated'
                )
            )
            
            # Show some examples
            self.stdout.write('\nSample forex pairs:')
            sample_pairs = Forex.objects.filter(is_active=True)[:10]
            for pair in sample_pairs:
                self.stdout.write(f'  {pair.symbol}: {pair.name} ({pair.from_currency} → {pair.to_currency})')
            
        except Exception as e:
            logger.error(f'Error loading forex pairs: {e}')
            raise CommandError(f'Failed to load forex pairs: {e}')