"""Forms for organization work calendar (weekends + holidays)."""

from __future__ import annotations

import json

from django import forms
from django.utils import timezone

from apps.attendance.work_calendar import DEFAULT_ROTATING_PATTERNS, format_weekday_csv, parse_weekday_csv
from apps.leaves.forms import HolidayForm
from apps.organizations.models import Organization

_INP = "ar-input w-full py-2 text-sm"


class WeekendPolicyForm(forms.Form):
    weekend_policy = forms.ChoiceField(
        choices=Organization.WeekendPolicy.choices,
        widget=forms.RadioSelect(attrs={"class": "wc-policy-radio"}),
    )
    weekend_custom_days = forms.MultipleChoiceField(
        required=False,
        choices=[(str(i), label) for i, label in enumerate(("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"))],
        widget=forms.CheckboxSelectMultiple(attrs={"class": "wc-day-check"}),
    )
    rotating_off_anchor = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": _INP, "type": "date"}),
    )
    rotating_cycle_steps = forms.IntegerField(
        required=False,
        min_value=1,
        max_value=8,
        initial=2,
        widget=forms.NumberInput(attrs={"class": _INP, "min": 1, "max": 8}),
        label="Number of rotation steps",
    )
    rotating_patterns_json = forms.CharField(
        required=False,
        widget=forms.HiddenInput(),
    )
    holidays_exclude_optional = forms.BooleanField(
        required=False,
        label="Exclude optional holidays from leave & working-day counts",
    )

    def __init__(self, *args, organization: Organization, **kwargs):
        self.organization = organization
        super().__init__(*args, **kwargs)
        org = organization
        custom = parse_weekday_csv(org.weekend_custom_days or "5,6")
        self.fields["weekend_policy"].initial = org.weekend_policy or Organization.WeekendPolicy.SAT_SUN
        self.fields["weekend_custom_days"].initial = [str(d) for d in custom]
        self.fields["rotating_off_anchor"].initial = org.rotating_off_anchor or timezone.localdate().replace(day=1)
        patterns = org.rotating_off_patterns or DEFAULT_ROTATING_PATTERNS
        self.fields["rotating_cycle_steps"].initial = len(patterns)
        self.fields["rotating_patterns_json"].initial = json.dumps(patterns)
        self.fields["holidays_exclude_optional"].initial = org.holidays_exclude_optional

    def clean_rotating_patterns_json(self):
        raw = self.cleaned_data.get("rotating_patterns_json") or "[]"
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise forms.ValidationError("Invalid rotation pattern data.") from exc
        if not isinstance(data, list):
            raise forms.ValidationError("Rotation patterns must be a list.")
        cleaned = []
        for step in data:
            if not isinstance(step, dict):
                continue
            off = step.get("off_days") or []
            off_days = [int(d) for d in off if str(d).isdigit() and 0 <= int(d) <= 6]
            cleaned.append({"off_days": off_days})
        return cleaned

    def save(self) -> Organization:
        org = self.organization
        org.weekend_policy = self.cleaned_data["weekend_policy"]
        days = self.cleaned_data.get("weekend_custom_days") or []
        org.weekend_custom_days = format_weekday_csv(int(d) for d in days)
        org.rotating_off_anchor = self.cleaned_data.get("rotating_off_anchor")
        patterns = self.cleaned_data.get("rotating_patterns_json") or DEFAULT_ROTATING_PATTERNS
        org.rotating_off_patterns = patterns
        org.holidays_exclude_optional = bool(self.cleaned_data.get("holidays_exclude_optional"))
        org.save(
            update_fields=[
                "weekend_policy",
                "weekend_custom_days",
                "rotating_off_anchor",
                "rotating_off_patterns",
                "holidays_exclude_optional",
                "updated_at",
            ]
        )
        return org


__all__ = ["HolidayForm", "WeekendPolicyForm"]
