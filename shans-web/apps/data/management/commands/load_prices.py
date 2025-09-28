from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.data.services import ensure_prices


class Command(BaseCommand):
    help = "Load historical prices for comma-separated symbols"

    def add_arguments(self, parser):
        parser.add_argument("--symbols", required=True)
        parser.add_argument("--days", type=int, default=1825)

    def handle(self, *args, **options):
        symbols = [s.strip().upper() for s in options["symbols"].split(",") if s.strip()]
        days = options["days"]
        for sym in symbols:
            inst, rows = ensure_prices(sym, days=days)
            self.stdout.write(self.style.SUCCESS(f"Loaded {len(rows)} rows for {inst.symbol}"))

