from django import forms

from apps.attendance.models import AttendanceRecord, AttendanceRegularizationRequest

_INP = "platform-input w-full"


class RegularizationRequestForm(forms.ModelForm):
    class Meta:
        model = AttendanceRegularizationRequest
        fields = ["date", "requested_check_in", "requested_check_out", "requested_status", "reason"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date", "class": _INP}),
            "requested_check_in": forms.TimeInput(attrs={"type": "time", "class": _INP}),
            "requested_check_out": forms.TimeInput(attrs={"type": "time", "class": _INP}),
            "requested_status": forms.Select(attrs={"class": _INP}),
            "reason": forms.Textarea(attrs={"class": _INP, "rows": 3, "placeholder": "Why do you need this correction?"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["requested_check_in"].required = False
        self.fields["requested_check_out"].required = False
        self.fields["requested_status"].required = False
        self.fields["requested_status"].choices = [("", "— Keep current —")] + list(
            AttendanceRecord.Status.choices
        )

    def clean(self):
        cleaned = super().clean()
        if not cleaned.get("requested_check_in") and not cleaned.get("requested_check_out") and not cleaned.get(
            "requested_status"
        ):
            raise forms.ValidationError("Enter at least a check-in, check-out, or status.")
        if not (cleaned.get("reason") or "").strip():
            raise forms.ValidationError("Please provide a reason.")
        return cleaned
