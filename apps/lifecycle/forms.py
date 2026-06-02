from django import forms

from apps.accounts.hierarchy import org_active_users
from apps.accounts.models import User
from apps.lifecycle.models import (
    AssetAllocation,
    EmployeeDocument,
    ExitInterview,
    OffboardingWorkflow,
    OnboardingTask,
    OnboardingWorkflow,
)
from apps.organizations.models import Organization


class StartOnboardingForm(forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.none(), widget=forms.Select(attrs={"class": "lc-input"}))
    joining_date = forms.DateField(widget=forms.DateInput(attrs={"class": "lc-input", "type": "date"}))
    branch = forms.CharField(required=False, widget=forms.TextInput(attrs={"class": "lc-input"}))

    def __init__(self, *args, organization: Organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].queryset = org_active_users(organization).filter(
            role__in=[User.Role.HR, User.Role.EMPLOYEE]
        )


class StartOffboardingForm(forms.Form):
    user = forms.ModelChoiceField(queryset=User.objects.none(), widget=forms.Select(attrs={"class": "lc-input"}))
    last_working_day = forms.DateField(widget=forms.DateInput(attrs={"class": "lc-input", "type": "date"}))
    resignation_reason = forms.ChoiceField(
        choices=OffboardingWorkflow.ResignationReason.choices,
        widget=forms.Select(attrs={"class": "lc-input"}),
    )
    notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": "lc-input", "rows": 2}))

    def __init__(self, *args, organization: Organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["user"].queryset = org_active_users(organization).filter(
            role__in=[User.Role.HR, User.Role.EMPLOYEE]
        )


class OnboardingTaskForm(forms.ModelForm):
    class Meta:
        model = OnboardingTask
        fields = ("title", "category", "priority", "due_date", "assigned_to")
        widgets = {
            "title": forms.TextInput(attrs={"class": "lc-input"}),
            "category": forms.Select(attrs={"class": "lc-input"}),
            "priority": forms.Select(attrs={"class": "lc-input"}),
            "due_date": forms.DateInput(attrs={"class": "lc-input", "type": "date"}),
            "assigned_to": forms.Select(attrs={"class": "lc-input"}),
        }


class DocumentUploadForm(forms.ModelForm):
    class Meta:
        model = EmployeeDocument
        fields = ("doc_type", "file", "expires_at")
        widgets = {
            "doc_type": forms.Select(attrs={"class": "lc-input"}),
            "file": forms.FileInput(attrs={"class": "lc-input"}),
            "expires_at": forms.DateInput(attrs={"class": "lc-input", "type": "date"}),
        }


class AssetForm(forms.ModelForm):
    class Meta:
        model = AssetAllocation
        fields = ("asset_type", "serial_number", "description", "status")
        widgets = {
            "asset_type": forms.Select(attrs={"class": "lc-input"}),
            "serial_number": forms.TextInput(attrs={"class": "lc-input"}),
            "description": forms.TextInput(attrs={"class": "lc-input"}),
            "status": forms.Select(attrs={"class": "lc-input"}),
        }


class ExitInterviewForm(forms.ModelForm):
    class Meta:
        model = ExitInterview
        fields = ("feedback", "reason_detail", "hr_comments", "manager_comments", "is_anonymous", "sentiment")
        widgets = {
            "feedback": forms.Textarea(attrs={"class": "lc-input", "rows": 3}),
            "reason_detail": forms.Textarea(attrs={"class": "lc-input", "rows": 2}),
            "hr_comments": forms.Textarea(attrs={"class": "lc-input", "rows": 2}),
            "manager_comments": forms.Textarea(attrs={"class": "lc-input", "rows": 2}),
            "is_anonymous": forms.CheckboxInput(),
            "sentiment": forms.TextInput(attrs={"class": "lc-input", "placeholder": "positive / neutral / negative"}),
        }
