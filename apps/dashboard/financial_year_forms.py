from django import forms
from django.core.exceptions import ValidationError

from apps.organizations.models import FinancialYear


class FinancialYearForm(forms.ModelForm):
    class Meta:
        model = FinancialYear
        fields = ["label", "start_date", "end_date", "is_active", "is_default"]
        widgets = {
            "start_date": forms.DateInput(attrs={"type": "date"}),
            "end_date": forms.DateInput(attrs={"type": "date"}),
            "label": forms.TextInput(attrs={"placeholder": "Auto-generated if blank"}),
        }

    def __init__(self, *args, org=None, **kwargs):
        self.org = org
        super().__init__(*args, **kwargs)
        self.fields["label"].required = False

    def clean(self):
        cleaned = super().clean()
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")

        if start and end:
            if end <= start:
                raise ValidationError("End date must be after start date.")

            qs = FinancialYear.objects.filter(organization=self.org)
            if self.instance.pk:
                qs = qs.exclude(pk=self.instance.pk)

            if qs.filter(start_date__lt=end, end_date__gt=start).exists():
                overlap = qs.filter(start_date__lt=end, end_date__gt=start).first()
                raise ValidationError(
                    f"Date range overlaps with existing financial year '{overlap.label}'."
                )

        return cleaned

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.organization = self.org

        if not instance.label:
            sy, ey = instance.start_date.year, instance.end_date.year
            instance.label = f"FY {sy}" if sy == ey else f"FY {sy}-{str(ey)[2:]}"

        if commit:
            if instance.is_default:
                FinancialYear.objects.filter(organization=self.org).exclude(
                    pk=instance.pk
                ).update(is_default=False)
            instance.save()

        return instance
