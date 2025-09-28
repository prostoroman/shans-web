"""
Data models for financial instruments and market data.
"""

from django.db import models
from django.utils.translation import gettext_lazy as _


class Instrument(models.Model):
    """Financial instrument (stock, ETF, etc.)."""
    
    symbol = models.CharField(
        max_length=20,
        unique=True,
        verbose_name=_("Symbol")
    )
    name = models.CharField(
        max_length=200,
        verbose_name=_("Name")
    )
    exchange = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("Exchange")
    )
    sector = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Sector")
    )
    industry = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Industry")
    )
    market_cap = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Market Cap")
    )
    currency = models.CharField(
        max_length=3,
        default="USD",
        verbose_name=_("Currency")
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name=_("Is Active")
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At")
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Updated At")
    )
    
    class Meta:
        verbose_name = _("Instrument")
        verbose_name_plural = _("Instruments")
        ordering = ["symbol"]
    
    def __str__(self):
        return f"{self.symbol} - {self.name}"


class PriceOHLC(models.Model):
    """OHLC price data for instruments."""
    
    instrument = models.ForeignKey(
        Instrument,
        on_delete=models.CASCADE,
        related_name="prices",
        verbose_name=_("Instrument")
    )
    date = models.DateField(
        verbose_name=_("Date")
    )
    open_price = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        verbose_name=_("Open Price")
    )
    high_price = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        verbose_name=_("High Price")
    )
    low_price = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        verbose_name=_("Low Price")
    )
    close_price = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        verbose_name=_("Close Price")
    )
    volume = models.BigIntegerField(
        verbose_name=_("Volume")
    )
    adjusted_close = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name=_("Adjusted Close")
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At")
    )
    
    class Meta:
        verbose_name = _("Price OHLC")
        verbose_name_plural = _("Price OHLC")
        unique_together = ["instrument", "date"]
        ordering = ["-date"]
    
    def __str__(self):
        return f"{self.instrument.symbol} - {self.date}"


class Fundamentals(models.Model):
    """Fundamental data for instruments."""
    
    instrument = models.ForeignKey(
        Instrument,
        on_delete=models.CASCADE,
        related_name="fundamentals",
        verbose_name=_("Instrument")
    )
    period = models.DateField(
        verbose_name=_("Period")
    )
    pe_ratio = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name=_("P/E Ratio")
    )
    pb_ratio = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name=_("P/B Ratio")
    )
    debt_to_equity = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name=_("Debt to Equity")
    )
    roe = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name=_("ROE")
    )
    roa = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name=_("ROA")
    )
    current_ratio = models.DecimalField(
        max_digits=10,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name=_("Current Ratio")
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At")
    )
    
    class Meta:
        verbose_name = _("Fundamentals")
        verbose_name_plural = _("Fundamentals")
        unique_together = ["instrument", "period"]
        ordering = ["-period"]
    
    def __str__(self):
        return f"{self.instrument.symbol} - {self.period}"


class CachedWindow(models.Model):
    """Cache metadata for data windows."""
    
    instrument = models.ForeignKey(
        Instrument,
        on_delete=models.CASCADE,
        related_name="cached_windows",
        verbose_name=_("Instrument")
    )
    window_type = models.CharField(
        max_length=20,
        choices=[
            ("prices", _("Prices")),
            ("fundamentals", _("Fundamentals")),
        ],
        verbose_name=_("Window Type")
    )
    start_date = models.DateField(
        verbose_name=_("Start Date")
    )
    end_date = models.DateField(
        verbose_name=_("End Date")
    )
    last_updated = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Last Updated")
    )
    
    class Meta:
        verbose_name = _("Cached Window")
        verbose_name_plural = _("Cached Windows")
        unique_together = ["instrument", "window_type", "start_date", "end_date"]
    
    def __str__(self):
        return f"{self.instrument.symbol} - {self.window_type} ({self.start_date} to {self.end_date})"