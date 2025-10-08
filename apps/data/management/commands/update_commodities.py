"""
Management command to update commodity data from Financial Modeling Prep API.
"""

import requests
import logging
from django.core.management.base import BaseCommand, CommandError
from django.conf import settings
from apps.data.models import Commodity

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = 'Update commodity data from Financial Modeling Prep API'

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
            self.update_commodities(api_key, dry_run)
        except Exception as e:
            logger.error(f"Error updating commodities: {e}")
            raise CommandError(f"Failed to update commodities: {e}")

    def update_commodities(self, api_key, dry_run=False):
        """Fetch and update commodity data from FMP API."""
        
        url = f"https://financialmodelingprep.com/stable/commodities-list?apikey={api_key}"
        
        self.stdout.write(f"Fetching commodity data from: {url}")
        
        try:
            response = requests.get(url, timeout=30)
            response.raise_for_status()
            commodities_data = response.json()
        except requests.exceptions.RequestException as e:
            raise CommandError(f"Failed to fetch data from FMP API: {e}")
        except ValueError as e:
            raise CommandError(f"Invalid JSON response from FMP API: {e}")

        if not isinstance(commodities_data, list):
            raise CommandError("Expected list of commodities from API")

        self.stdout.write(f"Found {len(commodities_data)} commodities")

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for commodity_data in commodities_data:
            if not isinstance(commodity_data, dict):
                self.stdout.write(
                    self.style.WARNING(f"Skipping invalid commodity data: {commodity_data}")
                )
                skipped_count += 1
                continue

            symbol = commodity_data.get('symbol', '').strip()
            if not symbol:
                self.stdout.write(
                    self.style.WARNING("Skipping commodity with empty symbol")
                )
                skipped_count += 1
                continue

            name = (commodity_data.get('name') or '').strip()
            exchange = commodity_data.get('exchange')
            trade_month = (commodity_data.get('tradeMonth') or '').strip()
            currency = (commodity_data.get('currency') or 'USD').strip()

            # Determine category based on name
            category = self.determine_category(name)

            if dry_run:
                self.stdout.write(
                    f"Would {'create' if not Commodity.objects.filter(symbol=symbol).exists() else 'update'}: "
                    f"{symbol} - {name}"
                )
                continue

            commodity, created = Commodity.objects.update_or_create(
                symbol=symbol,
                defaults={
                    'name': name,
                    'exchange': exchange,
                    'trade_month': trade_month,
                    'currency': currency,
                    'category': category,
                    'is_active': True,
                }
            )

            if created:
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f"Created: {symbol} - {name}")
                )
            else:
                updated_count += 1
                self.stdout.write(
                    self.style.SUCCESS(f"Updated: {symbol} - {name}")
                )

        if dry_run:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Dry run complete. Would process {len(commodities_data)} commodities "
                    f"(skipped {skipped_count} invalid entries)"
                )
            )
        else:
            self.stdout.write(
                self.style.SUCCESS(
                    f"Commodity update complete: "
                    f"{created_count} created, {updated_count} updated, {skipped_count} skipped"
                )
            )

    def determine_category(self, name):
        """Determine commodity category based on name."""
        name_lower = name.lower()
        
        if any(word in name_lower for word in ['gold', 'silver', 'platinum', 'palladium']):
            return 'precious_metals'
        elif any(word in name_lower for word in ['oil', 'gas', 'gasoline', 'heating', 'natural gas', 'crude', 'brent']):
            return 'energy'
        elif any(word in name_lower for word in ['corn', 'wheat', 'soybean', 'cotton', 'sugar', 'coffee', 'cocoa', 'rice', 'oat', 'orange']):
            return 'agriculture'
        elif any(word in name_lower for word in ['copper', 'aluminum', 'lumber']):
            return 'industrial'
        elif any(word in name_lower for word in ['cattle', 'hogs', 'milk', 'feeder']):
            return 'livestock'
        elif any(word in name_lower for word in ['treasury', 'bond', 'note', 'fed fund', 'dollar', 'nasdaq', 'dow', 's&p', 'russell']):
            return 'financial'
        else:
            return 'other'
