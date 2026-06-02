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
            if user and user.gender:
                from apps.accounts.models import User as U

                filtered = []
                for lt in qs:
                    if lt.gender_eligibility == LeaveType.GenderEligibility.ALL:
                        filtered.append(lt.pk)
                    elif lt.gender_eligibility == LeaveType.GenderEligibility.MALE and user.gender == U.Gender.MALE:
                        filtered.append(lt.pk)
                    elif lt.gender_eligibility == LeaveType.GenderEligibility.FEMALE and user.gender == U.Gender.FEMALE:
                        filtered.append(lt.pk)
                qs = qs.filter(pk__in=filtered) if filtered else qs.none()
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
        fields = ("name", "annual_quota", "is_paid", "color")
        widgets = {
            "name": forms.TextInput(attrs={"class": _INP, "placeholder": "e.g. Sick Leave"}),
            "annual_quota": forms.NumberInput(
                attrs={"class": _INP, "placeholder": "Days per year (optional)", "min": 0, "step": 0.5}
            ),
            "is_paid": forms.CheckboxInput(),
            "color": forms.TextInput(attrs={"class": _INP, "placeholder": "#0ea5e9"}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.fields["annual_quota"].required = False
        self.fields["color"].required = False
        self.fields["is_paid"].initial = True

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
