from django import forms
from django.utils.text import slugify

from .models import Holiday, LeaveRequest, LeaveType

_INP = "ar-input w-full"
_LA_INP = "la-input"


class OptionalFileField(forms.FileField):
    """File upload that treats missing or zero-byte files as no attachment."""

    def clean(self, data, initial=None):
        if data in self.empty_values:
            return None
        if hasattr(data, "size") and data.size == 0:
            return None
        return super().clean(data, initial)


class LeaveApplyForm(forms.Form):
    leave_type = forms.ModelChoiceField(queryset=LeaveType.objects.none(), widget=forms.Select())
    start_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    end_date = forms.DateField(widget=forms.DateInput(attrs={"type": "date"}))
    half_day = forms.ChoiceField(
        choices=LeaveRequest.HalfDay.choices,
        initial=LeaveRequest.HalfDay.NONE,
        required=False,
        widget=forms.RadioSelect(),
    )
    reason = forms.CharField(max_length=500, widget=forms.Textarea(attrs={"rows": 5}))
    emergency_contact = forms.CharField(required=False, widget=forms.TextInput())
    attachment = OptionalFileField(required=False, widget=forms.FileInput())
    save_draft = forms.BooleanField(required=False, widget=forms.HiddenInput())

    def __init__(self, *args, organization=None, user=None, apply_page=False, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.user = user
        inp = _LA_INP if apply_page else _INP

        self.fields["leave_type"].widget.attrs["class"] = inp
        self.fields["start_date"].widget.attrs["class"] = inp
        self.fields["end_date"].widget.attrs["class"] = inp
        self.fields["reason"].widget.attrs.update(
            {"class": inp, "placeholder": "Brief reason for your leave request…", "maxlength": "500"}
        )
        self.fields["emergency_contact"].widget.attrs.update(
            {"class": inp, "placeholder": "Optional contact while on leave"}
        )
        self.fields["attachment"].widget.attrs.update(
            {
                "class": "la-file-input",
                "accept": ".pdf,.jpg,.jpeg,.png,.doc,.docx",
            }
        )
        self.fields["attachment"].required = False
        if apply_page:
            self.fields["attachment"].label = "Attachments (optional)"
            self.fields["half_day"].widget = forms.RadioSelect(attrs={"class": "la-half-radio"})

        if organization:
            qs = LeaveType.objects.filter(organization=organization, is_active=True).order_by("sort_order")
            if user:
                # Gender + All/Department/Designation applicability in one place.
                applicable = [lt.pk for lt in qs if lt.is_applicable_to(user)]
                qs = qs.filter(pk__in=applicable)
            self.fields["leave_type"].queryset = qs

    def clean_half_day(self):
        value = self.cleaned_data.get("half_day")
        if not value:
            return LeaveRequest.HalfDay.NONE
        return value

    def clean(self):
        cleaned = super().clean()
        if self.errors:
            return cleaned
        start = cleaned.get("start_date")
        end = cleaned.get("end_date")
        if start and end and end < start:
            self.add_error("end_date", "End date must be on or after start date.")
        return cleaned


class LeaveTypeForm(forms.ModelForm):
    class Meta:
        model = LeaveType
        fields = (
            "name",
            "code",
            "description",
            "annual_quota",
            "carry_forward_max",
            "requires_attachment",
            "gender_eligibility",
            "applicable_to",
            "applicable_departments",
            "applicable_designations",
            "is_paid",
            "is_active",
            "color",
        )
        widgets = {
            "name": forms.TextInput(attrs={"class": _INP, "placeholder": "e.g. Sick Leave"}),
            "code": forms.TextInput(attrs={"class": _INP, "placeholder": "Auto-generated if empty"}),
            "description": forms.Textarea(attrs={"class": _INP, "rows": 2}),
            "annual_quota": forms.NumberInput(
                attrs={"class": _INP, "placeholder": "Days per year (optional)", "min": 0, "step": 0.5}
            ),
            "carry_forward_max": forms.NumberInput(attrs={"class": _INP, "min": 0, "step": 0.5}),
            "requires_attachment": forms.CheckboxInput(),
            "gender_eligibility": forms.Select(attrs={"class": _INP}),
            "applicable_to": forms.Select(attrs={"class": _INP}),
            "applicable_departments": forms.SelectMultiple(attrs={"class": _INP, "size": 4}),
            "applicable_designations": forms.SelectMultiple(attrs={"class": _INP, "size": 4}),
            "is_paid": forms.CheckboxInput(),
            "is_active": forms.CheckboxInput(),
            "color": forms.TextInput(attrs={"class": _INP, "placeholder": "#0ea5e9"}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.fields["annual_quota"].required = False
        self.fields["code"].required = False
        self.fields["color"].required = False
        self.fields["carry_forward_max"].required = False
        self.fields["is_paid"].initial = True
        self.fields["is_active"].initial = True
        if organization:
            from apps.grades.models import Designation, GradeStatus
            from apps.organizations.models import Department

            self.fields["applicable_departments"].queryset = Department.objects.filter(
                organization=organization, is_active=True
            ).order_by("name")
            self.fields["applicable_designations"].queryset = Designation.objects.filter(
                organization=organization, status=GradeStatus.ACTIVE
            ).order_by("name")

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Name is required.")
        return name

    def clean_annual_quota(self):
        q = self.cleaned_data.get("annual_quota")
        if q is None or q == "":
            return None
        return q

    def clean_carry_forward_max(self):
        from decimal import Decimal

        q = self.cleaned_data.get("carry_forward_max")
        return Decimal("0") if q in (None, "") else q

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.organization = self.organization
        if not obj.code:
            base = slugify(obj.name)[:40] or "leave-type"
            code = base
            n = 1
            while LeaveType.objects.filter(organization=self.organization, code=code).exclude(pk=obj.pk).exists():
                code = f"{base}-{n}"
                n += 1
            obj.code = code
        if not obj.color:
            obj.color = "#0ea5e9"
        if commit:
            obj.save()
            self.save_m2m()
        return obj


class HolidayForm(forms.ModelForm):
    class Meta:
        model = Holiday
        fields = ("name", "date", "holiday_type", "branch", "is_optional")
        widgets = {
            "name": forms.TextInput(attrs={"class": _INP}),
            "date": forms.DateInput(attrs={"class": _INP, "type": "date"}),
            "holiday_type": forms.Select(attrs={"class": _INP}),
            "branch": forms.TextInput(attrs={"class": _INP, "placeholder": "All branches if empty"}),
            "is_optional": forms.CheckboxInput(),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.organization = self.organization
        if commit:
            obj.save()
        return obj
