"""
User profile and account models.
"""

from django.contrib.auth.models import User
from django.db import models
from django.utils.translation import gettext_lazy as _


class UserProfile(models.Model):
    """Extended user profile with plan status and preferences."""
    
    PLAN_CHOICES = [
        ("basic", _("Basic")),
        ("pro", _("Pro")),
    ]
    
    LOCALE_CHOICES = [
        ("en", _("English")),
        ("ru", _("Русский")),
    ]
    
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name="profile",
        verbose_name=_("User")
    )
    status = models.CharField(
        max_length=10,
        choices=PLAN_CHOICES,
        default="basic",
        verbose_name=_("Plan Status")
    )
    locale = models.CharField(
        max_length=5,
        choices=LOCALE_CHOICES,
        default="en",
        verbose_name=_("Locale")
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
        verbose_name = _("User Profile")
        verbose_name_plural = _("User Profiles")
    
    def __str__(self):
        return f"{self.user.email} ({self.status})"
    
    @property
    def is_pro(self):
        """Check if user has pro plan."""
        return self.status == "pro"
    
    @property
    def portfolio_limit(self):
        """Get portfolio limit based on plan."""
        return 50 if self.is_pro else 3
    
    @property
    def compare_limit(self):
        """Get compare symbols limit based on plan."""
        return 10 if self.is_pro else 4
    
    @property
    def history_retention_days(self):
        """Get history retention days based on plan."""
        return 365 if self.is_pro else 30