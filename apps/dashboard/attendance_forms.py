from django import forms

from apps.accounts.models import User
from apps.attendance.models import WorkShift
from apps.organizations.models import Organization

_INP = "platform-input w-full"


class WorkShiftForm(forms.ModelForm):
    class Meta:
        model = WorkShift
        fields = ("name", "start_time", "end_time", "grace_minutes", "is_default")
        widgets = {
            "name": forms.TextInput(attrs={"class": _INP, "placeholder": "e.g. Morning Shift"}),
            "start_time": forms.TimeInput(attrs={"class": _INP, "type": "time"}),
            "end_time": forms.TimeInput(attrs={"class": _INP, "type": "time"}),
            "grace_minutes": forms.NumberInput(
                attrs={"class": _INP, "min": 0, "max": 120, "placeholder": "15"}
            ),
            "is_default": forms.CheckboxInput(),
        }

    def __init__(self, *args, organization: Organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.fields["grace_minutes"].help_text = "Buffer minutes after shift start before marking late."

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.organization = self.organization
        if commit:
            if instance.is_default:
                # Clear existing default before insert/update to satisfy unique constraint.
                WorkShift.objects.filter(
                    organization=self.organization, is_default=True
                ).exclude(pk=instance.pk).update(is_default=False)
            instance.save()
        return instance


def _staff_for_shift_assign(organization: Organization):
    return User.objects.filter(
        organization=organization,
        is_active=True,
        role__in=[User.Role.HR, User.Role.EMPLOYEE],
    ).order_by("first_name", "last_name", "username")


class AssignShiftForm(forms.Form):
    shift = forms.ModelChoiceField(
        queryset=WorkShift.objects.none(),
        widget=forms.Select(attrs={"class": _INP}),
    )
    users = forms.ModelMultipleChoiceField(
        queryset=User.objects.none(),
        widget=forms.CheckboxSelectMultiple(),
        required=False,
    )

    def __init__(self, *args, organization: Organization, selected_shift_id=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        staff_qs = _staff_for_shift_assign(organization)
        self.fields["shift"].queryset = WorkShift.objects.filter(organization=organization)
        self.fields["users"].queryset = staff_qs
        self.fields["users"].label_from_instance = lambda u: u.choice_label
        if selected_shift_id:
            try:
                shift = WorkShift.objects.get(pk=selected_shift_id, organization=organization)
                self.fields["shift"].initial = shift.pk
                self.fields["users"].initial = staff_qs.filter(work_shift=shift)
            except WorkShift.DoesNotExist:
                pass

    def save(self):
        shift = self.cleaned_data["shift"]
        selected = list(self.cleaned_data["users"].values_list("pk", flat=True))
        User.objects.filter(pk__in=selected).update(work_shift=shift)
        User.objects.filter(organization=self.organization, work_shift=shift).exclude(
            pk__in=selected
        ).update(work_shift=None)
