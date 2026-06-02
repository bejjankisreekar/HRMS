from django import forms

from apps.accounts.hierarchy import attendance_team_for, org_active_users
from apps.accounts.models import User
from apps.attendance.models import WorkShift
from apps.organizations.models import Department, Organization
from apps.shifts.models import ShiftAssignment, ShiftRotation, ShiftRotationStep, ShiftSwapRequest


class WorkShiftManageForm(forms.ModelForm):
    weekly_off_list = forms.MultipleChoiceField(
        choices=[
            ("0", "Monday"),
            ("1", "Tuesday"),
            ("2", "Wednesday"),
            ("3", "Thursday"),
            ("4", "Friday"),
            ("5", "Saturday"),
            ("6", "Sunday"),
        ],
        required=False,
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = WorkShift
        fields = (
            "name",
            "shift_code",
            "shift_type",
            "start_time",
            "end_time",
            "break_minutes",
            "grace_minutes",
            "color",
            "description",
            "branch",
            "night_allowance_percent",
            "is_active",
            "is_default",
        )
        widgets = {
            "name": forms.TextInput(attrs={"class": "sh-input"}),
            "shift_code": forms.TextInput(attrs={"class": "sh-input"}),
            "shift_type": forms.Select(attrs={"class": "sh-input"}),
            "start_time": forms.TimeInput(attrs={"class": "sh-input", "type": "time"}),
            "end_time": forms.TimeInput(attrs={"class": "sh-input", "type": "time"}),
            "break_minutes": forms.NumberInput(attrs={"class": "sh-input", "min": 0}),
            "grace_minutes": forms.NumberInput(attrs={"class": "sh-input", "min": 0}),
            "color": forms.TextInput(attrs={"class": "sh-input", "type": "color"}),
            "description": forms.Textarea(attrs={"class": "sh-input", "rows": 2}),
            "branch": forms.TextInput(attrs={"class": "sh-input"}),
            "night_allowance_percent": forms.NumberInput(
                attrs={"class": "sh-input", "step": "0.01", "min": 0}
            ),
            "is_active": forms.CheckboxInput(),
            "is_default": forms.CheckboxInput(),
        }

    def __init__(self, *args, organization: Organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        if self.instance.pk and self.instance.weekly_off_days:
            self.fields["weekly_off_list"].initial = self.instance.weekly_off_days.split(",")

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.organization = self.organization
        offs = self.cleaned_data.get("weekly_off_list") or []
        instance.weekly_off_days = ",".join(offs)
        if commit:
            if instance.is_default:
                WorkShift.objects.filter(organization=self.organization, is_default=True).exclude(
                    pk=instance.pk
                ).update(is_default=False)
            instance.save()
        return instance


class ShiftAssignForm(forms.ModelForm):
    users = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        widget=forms.SelectMultiple(attrs={"class": "sh-input", "size": 8}),
    )

    class Meta:
        model = ShiftAssignment
        fields = ("shift", "date", "notes")
        widgets = {
            "shift": forms.Select(attrs={"class": "sh-input"}),
            "date": forms.DateInput(attrs={"class": "sh-input", "type": "date"}),
            "notes": forms.TextInput(attrs={"class": "sh-input"}),
        }

    def __init__(self, *args, organization: Organization, viewer: User, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.viewer = viewer
        self.fields["shift"].queryset = WorkShift.objects.filter(
            organization=organization, is_active=True
        )
        if viewer.role == User.Role.ADMIN:
            qs = org_active_users(organization).filter(role__in=[User.Role.HR, User.Role.EMPLOYEE])
        elif viewer.role == User.Role.HR:
            qs = attendance_team_for(viewer)
        else:
            qs = User.objects.filter(pk=viewer.pk)
        self.fields["users"].queryset = qs.order_by("first_name")


class ShiftSwapForm(forms.ModelForm):
    class Meta:
        model = ShiftSwapRequest
        fields = ("date", "current_shift", "requested_shift", "swap_with", "reason")
        widgets = {
            "date": forms.DateInput(attrs={"class": "sh-input", "type": "date"}),
            "current_shift": forms.Select(attrs={"class": "sh-input"}),
            "requested_shift": forms.Select(attrs={"class": "sh-input"}),
            "swap_with": forms.Select(attrs={"class": "sh-input"}),
            "reason": forms.Textarea(attrs={"class": "sh-input", "rows": 2}),
        }

    def __init__(self, *args, organization: Organization, requester: User, **kwargs):
        super().__init__(*args, **kwargs)
        shifts = WorkShift.objects.filter(organization=organization, is_active=True)
        self.fields["current_shift"].queryset = shifts
        self.fields["requested_shift"].queryset = shifts
        self.fields["swap_with"].queryset = org_active_users(organization).exclude(pk=requester.pk)
        self.fields["swap_with"].required = False


class RotationForm(forms.ModelForm):
    class Meta:
        model = ShiftRotation
        fields = ("name", "cycle_unit", "cycle_length", "description", "is_active")
        widgets = {
            "name": forms.TextInput(attrs={"class": "sh-input"}),
            "cycle_unit": forms.Select(attrs={"class": "sh-input"}),
            "cycle_length": forms.NumberInput(attrs={"class": "sh-input", "min": 1}),
            "description": forms.Textarea(attrs={"class": "sh-input", "rows": 2}),
            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, organization: Organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization

    def save(self, commit=True):
        inst = super().save(commit=False)
        inst.organization = self.organization
        if commit:
            inst.save()
        return inst
