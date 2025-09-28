from __future__ import annotations

from django import forms
from .models import UserProfile


class ProfileForm(forms.ModelForm):
    class Meta:
        model = UserProfile
        fields = ["locale", "marketing_opt_in"]

