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
    
    def get_currency_symbol(self):
        """Get currency symbol for display."""
        currency_symbols = {
            'USD': '$',
            'EUR': '€',
            'GBP': '£',
            'JPY': '¥',
            'CAD': 'C$',
            'AUD': 'A$',
            'CHF': 'CHF',
            'CNY': '¥',
            'RUB': '₽',
            'INR': '₹',
            'KRW': '₩',
            'SEK': 'kr',
            'NOK': 'kr',
            'DKK': 'kr',
            'PLN': 'zł',
            'CZK': 'Kč',
            'HUF': 'Ft',
            'BRL': 'R$',
            'MXN': '$',
            'SGD': 'S$',
            'HKD': 'HK$',
            'NZD': 'NZ$',
            'ZAR': 'R',
            'ILS': '₪',
            'AED': 'د.إ',
            'SAR': '﷼',
            'QAR': '﷼',
            'KWD': 'د.ك',
            'BHD': 'د.ب',
            'OMR': '﷼',
            'JOD': 'د.ا',
        }
        return currency_symbols.get(self.currency, self.currency)
    
    def get_market_cap_formatted(self):
        """Get formatted market cap with currency symbol and unit abbreviations."""
        if not self.market_cap:
            return 'N/A'
        
        symbol = self.get_currency_symbol()
        num = float(self.market_cap)
        
        if num >= 1_000_000_000_000:
            return f"{symbol}{num / 1_000_000_000_000:.2f}T"
        elif num >= 1_000_000_000:
            return f"{symbol}{num / 1_000_000_000:.2f}B"
        elif num >= 1_000_000:
            return f"{symbol}{num / 1_000_000:.2f}M"
        elif num >= 1_000:
            return f"{symbol}{num / 1_000:.2f}K"
        else:
            # Format with thousands separators using spaces
            formatted = f"{num:,.2f}".replace(',', ' ')
            return f"{symbol}{formatted}"
    
    @property
    def currency_symbol(self):
        """Property for accessing currency symbol in templates."""
        return self.get_currency_symbol()
    
    @property
    def market_cap_formatted(self):
        """Property for accessing formatted market cap in templates."""
        return self.get_market_cap_formatted()


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
    
    @property
    def open_price_formatted(self):
        """Get formatted open price with currency symbol."""
        symbol = self.instrument.get_currency_symbol()
        formatted = f"{float(self.open_price):,.2f}".replace(',', ' ')
        return f"{symbol}{formatted}"
    
    @property
    def high_price_formatted(self):
        """Get formatted high price with currency symbol."""
        symbol = self.instrument.get_currency_symbol()
        formatted = f"{float(self.high_price):,.2f}".replace(',', ' ')
        return f"{symbol}{formatted}"
    
    @property
    def low_price_formatted(self):
        """Get formatted low price with currency symbol."""
        symbol = self.instrument.get_currency_symbol()
        formatted = f"{float(self.low_price):,.2f}".replace(',', ' ')
        return f"{symbol}{formatted}"
    
    @property
    def close_price_formatted(self):
        """Get formatted close price with currency symbol."""
        symbol = self.instrument.get_currency_symbol()
        formatted = f"{float(self.close_price):,.2f}".replace(',', ' ')
        return f"{symbol}{formatted}"


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


class Commodity(models.Model):
    """Commodity instrument (Gold, Silver, Oil, etc.)."""
    
    symbol = models.CharField(
        max_length=20,
        unique=True,
        verbose_name=_("Symbol")
    )
    name = models.CharField(
        max_length=200,
        verbose_name=_("Name")
    )
    category = models.CharField(
        max_length=50,
        choices=[
            ("precious_metals", _("Precious Metals")),
            ("energy", _("Energy")),
            ("agriculture", _("Agriculture")),
            ("industrial", _("Industrial")),
            ("livestock", _("Livestock")),
            ("other", _("Other")),
        ],
        default="other",
        verbose_name=_("Category")
    )
    currency = models.CharField(
        max_length=3,
        default="USD",
        verbose_name=_("Currency")
    )
    unit = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("Unit")  # e.g., "per troy ounce", "per barrel"
    )
    exchange = models.CharField(
        max_length=50,
        blank=True,
        null=True,
        verbose_name=_("Exchange")
    )
    trade_month = models.CharField(
        max_length=10,
        blank=True,
        verbose_name=_("Trade Month")
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
        verbose_name = _("Commodity")
        verbose_name_plural = _("Commodities")
        ordering = ["symbol"]
    
    def __str__(self):
        return f"{self.symbol} - {self.name}"
    
    def get_currency_symbol(self):
        """Get currency symbol for display."""
        currency_symbols = {
            'USD': '$',
            'EUR': '€',
            'GBP': '£',
            'JPY': '¥',
            'CAD': 'C$',
            'AUD': 'A$',
            'CHF': 'CHF',
            'CNY': '¥',
            'RUB': '₽',
            'INR': '₹',
            'KRW': '₩',
            'SEK': 'kr',
            'NOK': 'kr',
            'DKK': 'kr',
            'PLN': 'zł',
            'CZK': 'Kč',
            'HUF': 'Ft',
            'BRL': 'R$',
            'MXN': '$',
            'SGD': 'S$',
            'HKD': 'HK$',
            'NZD': 'NZ$',
            'ZAR': 'R',
            'ILS': '₪',
            'AED': 'د.إ',
            'SAR': '﷼',
            'QAR': '﷼',
            'KWD': 'د.ك',
            'BHD': 'د.ب',
            'OMR': '﷼',
            'JOD': 'د.ا',
        }
        return currency_symbols.get(self.currency, self.currency)


class CommoditiesQuote(models.Model):
    """`. OHLC price data for commodities."""
    
    commodity = models.ForeignKey(
        Commodity,
        on_delete=models.CASCADE,
        related_name="quotes",
        verbose_name=_("Commodity")
    )
    timestamp = models.DateTimeField(
        verbose_name=_("Timestamp")
    )
    price = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        verbose_name=_("Price")
    )
    change = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name=_("Change")
    )
    change_percentage = models.DecimalField(
        max_digits=8,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name=_("Change Percentage")
    )
    day_low = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name=_("Day Low")
    )
    day_high = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name=_("Day High")
    )
    volume = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Volume")
    )
    market_cap = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Market Cap")
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At")
    )
    
    class Meta:
        verbose_name = _("Commodity Quote")
        verbose_name_plural = _("Commodity Quotes")
        unique_together = ["commodity", "timestamp"]
        ordering = ["-timestamp"]
    
    def __str__(self):
        return f"{self.commodity.symbol} - {self.timestamp}"
    
    @property
    def price_formatted(self):
        """Get formatted price with currency symbol."""
        symbol = self.commodity.get_currency_symbol()
        unit_text = f" / {self.commodity.unit}" if self.commodity.unit else ""
        formatted = f"{float(self.price):,.2f}".replace(',', ' ')
        return f"{symbol}{formatted}{unit_text}"


class Cryptocurrency(models.Model):
    """Cryptocurrency instrument (Bitcoin, Ethereum, etc.)."""
    
    symbol = models.CharField(
        max_length=20,
        unique=True,
        verbose_name=_("Symbol")
    )
    name = models.CharField(
        max_length=200,
        verbose_name=_("Name")
    )
    currency = models.CharField(
        max_length=3,
        default="USD",
        verbose_name=_("Currency")
    )
    market_cap = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Market Cap")
    )
    circulating_supply = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Circulating Supply")
    )
    total_supply = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Total Supply")
    )
    max_supply = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Max Supply")
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
        verbose_name = _("Cryptocurrency")
        verbose_name_plural = _("Cryptocurrencies")
        ordering = ["symbol"]
    
    def __str__(self):
        return f"{self.symbol} - {self.name}"
    
    def get_currency_symbol(self):
        """Get currency symbol for display."""
        currency_symbols = {
            "USD": "$",
            "EUR": "€",
            "GBP": "£",
            "JPY": "¥",
            "CAD": "C$",
            "AUD": "A$",
            "CHF": "CHF",
            "CNY": "¥",
        }
        return currency_symbols.get(self.currency, self.currency)
    
    def get_market_cap_formatted(self):
        """Get formatted market cap."""
        if not self.market_cap:
            return "N/A"
        
        if self.market_cap >= 1_000_000_000_000:
            return f"{self.get_currency_symbol()}{self.market_cap / 1_000_000_000_000:.2f}T"
        elif self.market_cap >= 1_000_000_000:
            return f"{self.get_currency_symbol()}{self.market_cap / 1_000_000_000:.2f}B"
        elif self.market_cap >= 1_000_000:
            return f"{self.get_currency_symbol()}{self.market_cap / 1_000_000:.2f}M"
        else:
            return f"{self.get_currency_symbol()}{self.market_cap:,}"
    
    @property
    def market_cap_formatted(self):
        return self.get_market_cap_formatted()


class CryptocurrencyQuote(models.Model):
    """OHLC price data for cryptocurrencies."""
    
    cryptocurrency = models.ForeignKey(
        Cryptocurrency,
        on_delete=models.CASCADE,
        related_name="quotes",
        verbose_name=_("Cryptocurrency")
    )
    timestamp = models.DateTimeField(
        verbose_name=_("Timestamp")
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
        null=True,
        blank=True,
        verbose_name=_("Volume")
    )
    market_cap = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Market Cap")
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At")
    )
    
    class Meta:
        verbose_name = _("Cryptocurrency Quote")
        verbose_name_plural = _("Cryptocurrency Quotes")
        unique_together = ["cryptocurrency", "timestamp"]
        ordering = ["-timestamp"]
    
    def __str__(self):
        return f"{self.cryptocurrency.symbol} - {self.timestamp}"
    
    @property
    def open_price_formatted(self):
        """Get formatted open price with currency symbol."""
        symbol = self.cryptocurrency.get_currency_symbol()
        formatted = f"{float(self.open_price):,.2f}".replace(',', ' ')
        return f"{symbol}{formatted}"
    
    @property
    def high_price_formatted(self):
        """Get formatted high price with currency symbol."""
        symbol = self.cryptocurrency.get_currency_symbol()
        formatted = f"{float(self.high_price):,.2f}".replace(',', ' ')
        return f"{symbol}{formatted}"
    
    @property
    def low_price_formatted(self):
        """Get formatted low price with currency symbol."""
        symbol = self.cryptocurrency.get_currency_symbol()
        formatted = f"{float(self.low_price):,.2f}".replace(',', ' ')
        return f"{symbol}{formatted}"
    
    @property
    def close_price_formatted(self):
        """Get formatted close price with currency symbol."""
        symbol = self.cryptocurrency.get_currency_symbol()
        formatted = f"{float(self.close_price):,.2f}".replace(',', ' ')
        return f"{symbol}{formatted}"


class Forex(models.Model):
    """Forex currency pair instrument (EURUSD, GBPUSD, etc.)."""
    
    symbol = models.CharField(
        max_length=20,
        unique=True,
        verbose_name=_("Symbol")
    )
    name = models.CharField(
        max_length=200,
        verbose_name=_("Name")
    )
    base_currency = models.CharField(
        max_length=3,
        verbose_name=_("Base Currency")
    )
    quote_currency = models.CharField(
        max_length=3,
        verbose_name=_("Quote Currency")
    )
    exchange = models.CharField(
        max_length=50,
        blank=True,
        verbose_name=_("Exchange")
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
        verbose_name = _("Forex")
        verbose_name_plural = _("Forex")
        ordering = ["symbol"]
    
    def __str__(self):
        return f"{self.symbol} - {self.name}"
    
    def get_base_currency_symbol(self):
        """Get currency symbol for base currency."""
        currency_symbols = {
            'USD': '$',
            'EUR': '€',
            'GBP': '£',
            'JPY': '¥',
            'CAD': 'C$',
            'AUD': 'A$',
            'CHF': 'CHF',
            'CNY': '¥',
            'RUB': '₽',
            'INR': '₹',
            'KRW': '₩',
            'SEK': 'kr',
            'NOK': 'kr',
            'DKK': 'kr',
            'PLN': 'zł',
            'CZK': 'Kč',
            'HUF': 'Ft',
            'BRL': 'R$',
            'MXN': '$',
            'SGD': 'S$',
            'HKD': 'HK$',
            'NZD': 'NZ$',
            'ZAR': 'R',
            'ILS': '₪',
            'AED': 'د.إ',
            'SAR': '﷼',
            'QAR': '﷼',
            'KWD': 'د.ك',
            'BHD': 'د.ب',
            'OMR': '﷼',
            'JOD': 'د.ا',
        }
        return currency_symbols.get(self.base_currency, self.base_currency)
    
    def get_quote_currency_symbol(self):
        """Get currency symbol for quote currency."""
        currency_symbols = {
            'USD': '$',
            'EUR': '€',
            'GBP': '£',
            'JPY': '¥',
            'CAD': 'C$',
            'AUD': 'A$',
            'CHF': 'CHF',
            'CNY': '¥',
            'RUB': '₽',
            'INR': '₹',
            'KRW': '₩',
            'SEK': 'kr',
            'NOK': 'kr',
            'DKK': 'kr',
            'PLN': 'zł',
            'CZK': 'Kč',
            'HUF': 'Ft',
            'BRL': 'R$',
            'MXN': '$',
            'SGD': 'S$',
            'HKD': 'HK$',
            'NZD': 'NZ$',
            'ZAR': 'R',
            'ILS': '₪',
            'AED': 'د.إ',
            'SAR': '﷼',
            'QAR': '﷼',
            'KWD': 'د.ك',
            'BHD': 'د.ب',
            'OMR': '﷼',
            'JOD': 'د.ا',
        }
        return currency_symbols.get(self.quote_currency, self.quote_currency)


class ForexQuote(models.Model):
    """OHLC price data for forex currency pairs."""
    
    forex = models.ForeignKey(
        Forex,
        on_delete=models.CASCADE,
        related_name="quotes",
        verbose_name=_("Forex")
    )
    timestamp = models.DateTimeField(
        verbose_name=_("Timestamp")
    )
    open_price = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        verbose_name=_("Open Price")
    )
    high_price = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        verbose_name=_("High Price")
    )
    low_price = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        verbose_name=_("Low Price")
    )
    close_price = models.DecimalField(
        max_digits=12,
        decimal_places=6,
        verbose_name=_("Close Price")
    )
    volume = models.BigIntegerField(
        null=True,
        blank=True,
        verbose_name=_("Volume")
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At")
    )
    
    class Meta:
        verbose_name = _("Forex Quote")
        verbose_name_plural = _("Forex Quotes")
        unique_together = ["forex", "timestamp"]
        ordering = ["-timestamp"]
    
    def __str__(self):
        return f"{self.forex.symbol} - {self.timestamp}"
    
    @property
    def open_price_formatted(self):
        """Get formatted open price."""
        return f"{float(self.open_price):,.6f}"
    
    @property
    def high_price_formatted(self):
        """Get formatted high price."""
        return f"{float(self.high_price):,.6f}"
    
    @property
    def low_price_formatted(self):
        """Get formatted low price."""
        return f"{float(self.low_price):,.6f}"
    
    @property
    def close_price_formatted(self):
        """Get formatted close price."""
        return f"{float(self.close_price):,.6f}"
    
    @property
    def volume_formatted(self):
        """Get formatted volume."""
        return f"{int(self.volume):,}"


class Exchange(models.Model):
    """Stock exchange information."""
    
    code = models.CharField(
        max_length=10,
        unique=True,
        verbose_name=_("Exchange Code")
    )
    name = models.CharField(
        max_length=200,
        verbose_name=_("Exchange Name")
    )
    country_name = models.CharField(
        max_length=100,
        blank=True,
        verbose_name=_("Country Name")
    )
    country_code = models.CharField(
        max_length=2,
        blank=True,
        verbose_name=_("Country Code")
    )
    symbol_suffix = models.CharField(
        max_length=10,
        blank=True,
        verbose_name=_("Symbol Suffix")
    )
    delay = models.CharField(
        max_length=20,
        blank=True,
        verbose_name=_("Data Delay")
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
        verbose_name = _("Exchange")
        verbose_name_plural = _("Exchanges")
        ordering = ['name']
    
    def __str__(self):
        return f"{self.name} ({self.code})"
    
    @property
    def display_name(self):
        """Get display name for the exchange."""
        return self.name or self.code