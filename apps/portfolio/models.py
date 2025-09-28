"""
Portfolio models for analysis and optimization.
"""

from django.contrib.auth.models import User
from django.db import models
from django.utils.translation import gettext_lazy as _


class Portfolio(models.Model):
    """User portfolio for analysis."""
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="portfolios",
        null=True,
        blank=True,
        verbose_name=_("User")
    )
    name = models.CharField(
        max_length=100,
        verbose_name=_("Portfolio Name")
    )
    description = models.TextField(
        blank=True,
        verbose_name=_("Description")
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At")
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name=_("Updated At")
    )
    
    # Analysis results
    expected_return = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name=_("Expected Return")
    )
    volatility = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name=_("Volatility")
    )
    sharpe_ratio = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name=_("Sharpe Ratio")
    )
    max_drawdown = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        null=True,
        blank=True,
        verbose_name=_("Max Drawdown")
    )
    
    class Meta:
        verbose_name = _("Portfolio")
        verbose_name_plural = _("Portfolios")
        ordering = ["-created_at"]
    
    def __str__(self):
        return self.name
    
    @property
    def total_weight(self):
        """Calculate total weight of all positions."""
        return sum(pos.weight for pos in self.positions.all())
    
    @property
    def position_count(self):
        """Get number of positions."""
        return self.positions.count()


class PortfolioPosition(models.Model):
    """Individual position in a portfolio."""
    
    portfolio = models.ForeignKey(
        Portfolio,
        on_delete=models.CASCADE,
        related_name="positions",
        verbose_name=_("Portfolio")
    )
    symbol = models.CharField(
        max_length=20,
        verbose_name=_("Symbol")
    )
    weight = models.DecimalField(
        max_digits=8,
        decimal_places=6,
        verbose_name=_("Weight")
    )
    shares = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name=_("Shares")
    )
    price = models.DecimalField(
        max_digits=12,
        decimal_places=4,
        null=True,
        blank=True,
        verbose_name=_("Price")
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Created At")
    )
    
    class Meta:
        verbose_name = _("Portfolio Position")
        verbose_name_plural = _("Portfolio Positions")
        unique_together = ["portfolio", "symbol"]
        ordering = ["-weight"]
    
    def __str__(self):
        return f"{self.portfolio.name} - {self.symbol} ({self.weight:.2%})"
    
    @property
    def value(self):
        """Calculate position value."""
        if self.shares and self.price:
            return self.shares * self.price
        return None