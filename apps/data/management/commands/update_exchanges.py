"""
Management command to update exchange data from Financial Modeling Prep API.
"""

import requests
import logging
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from apps.data.models import Exchange

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Update exchange data from Financial Modeling Prep API'

    def add_arguments(self, parser):
        parser.add_argument(
            '--api-key',
            type=str,
            help='FMP API key (if not provided, uses FMP_API_KEY from settings)',
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be updated without making changes',
        )

    def handle(self, *args, **options):
        api_key = options.get('api_key') or getattr(settings, 'FMP_API_KEY', None)
        
        if not api_key:
            raise CommandError(
                'FMP API key is required. Provide --api-key or set FMP_API_KEY in settings.'
            )

        dry_run = options.get('dry_run', False)
        
        if dry_run:
            self.stdout.write(
                self.style.WARNING('DRY RUN MODE - No changes will be made')
            )

        try:
            self.update_exchanges(api_key, dry_run)
        except Exception as e:
            logger.error(f"Error updating exchanges: {e}")
            raise CommandError(f"Failed to update exchanges: {e}")

    def update_exchanges(self, api_key, dry_run=False):
        """Fetch and update exchange data from FMP API."""
        
        url = f"https://financialmodelingprep.com/stable/available-exchanges?apikey={api_key}"
        
        self.stdout.write(f"Fetching exchange data from: {url}")
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            exchanges_data = response.json()
        except requests.exceptions.RequestException as e:
            raise CommandError(f"Failed to fetch data from FMP API: {e}")
        except ValueError as e:
            raise CommandError(f"Invalid JSON response from FMP API: {e}")

        if not isinstance(exchanges_data, list):
            raise CommandError("Expected list of exchanges from API")

        self.stdout.write(f"Found {len(exchanges_data)} exchanges")

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for exchange_data in exchanges_data:
            if not isinstance(exchange_data, dict):
                self.stdout.write(
                    self.style.WARNING(f"Skipping invalid exchange data: {exchange_data}")
                )
                skipped_count += 1
                continue

            exchange_code = exchange_data.get('exchange', '').strip()
            if not exchange_code:
                self.stdout.write(
                    self.style.WARNING("Skipping exchange with empty code")
                )
                skipped_count += 1
                continue

            exchange_name = (exchange_data.get('name') or '').strip()
            country_name = (exchange_data.get('countryName') or '').strip()
            country_code = (exchange_data.get('countryCode') or '').strip()
            symbol_suffix = (exchange_data.get('symbolSuffix') or '').strip()
            delay = (exchange_data.get('delay') or '').strip()

            if dry_run:
                self.stdout.write(
                    f"Would {'create' if not Exchange.objects.filter(code=exchange_code).exists() else 'update'}: "
                    f"{exchange_code} - {exchange_name}"
                )
                continue

            exchange, created = Exchange.objects.update_or_create(
                code=exchange_code,
                defaults={
                    'name': exchange_name,
                    'country_name': country_name,
                    'country_code': country_code,
                    'symbol_suffix': symbol_suffix,
                    'delay': delay,
                    'is_active': True,
                }
            )

            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f"Created: {exchange_code} - {exchange_name}")
                )
            else:
                updated_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f"Updated: {exchange_code} - {exchange_name}")
                )

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Dry run complete. Would process {len(exchanges_data)} exchanges "
                    f"(skipped {skipped_count} invalid entries)"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Exchange update complete: "
                    f"{created_count} created, {updated_count} updated, {skipped_count} skipped"
                )
            )
