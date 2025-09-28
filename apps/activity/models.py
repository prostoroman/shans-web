"""
Activity models for user viewing history and saved sets.
"""

from django.contrib.auth.models import User
from django.db import models
from django.utils.translation import gettext_lazy as _


class ViewEvent(models.Model):
    """User viewing history for symbols."""
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="view_events",
        verbose_name=_("User")
    )
    symbol = models.CharField(
        max_length=20,
        verbose_name=_("Symbol")
    )
    view_type = models.CharField(
        max_length=20,
        choices=[
            ("info", _("Info")),
            ("compare", _("Compare")),
            ("portfolio", _("Portfolio")),
        ],
        default="info",
        verbose_name=_("View Type")
    )
    timestamp = models.DateTimeField(
        auto_now_add=True,
        verbose_name=_("Timestamp")
    )
    
    class Meta:
        verbose_name = _("View Event")
        verbose_name_plural = _("View Events")
        ordering = ["-timestamp"]
        indexes = [
            models.Index(fields=["user", "-timestamp"]),
            models.Index(fields=["symbol", "-timestamp"]),
        ]
    
    def __str__(self):
        return f"{self.user.email} viewed {self.symbol} ({self.view_type})"


class SavedSet(models.Model):
    """User saved comparison sets and portfolios."""
    
    SET_TYPE_CHOICES = [
        ("compare", _("Compare Set")),
        ("portfolio", _("Portfolio")),
        ("watchlist", _("Watchlist")),
    ]
    
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="saved_sets",
        verbose_name=_("User")
    )
    name = models.CharField(
        max_length=100,
        verbose_name=_("Name")
    )
    set_type = models.CharField(
        max_length=20,
        choices=SET_TYPE_CHOICES,
        verbose_name=_("Set Type")
    )
    payload = models.JSONField(
        verbose_name=_("Payload")
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
    
    class Meta:
        verbose_name = _("Saved Set")
        verbose_name_plural = _("Saved Sets")
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "set_type"]),
        ]
    
    def __str__(self):
        return f"{self.user.email} - {self.name} ({self.set_type})"
    
    @property
    def symbols(self):
        """Extract symbols from payload."""
        if self.set_type == "compare":
            return self.payload.get("symbols", [])
        elif self.set_type == "portfolio":
            return [pos["symbol"] for pos in self.payload.get("positions", [])]
        return []
    
    @property
    def symbol_count(self):
        """Get number of symbols in the set."""
        return len(self.symbols)