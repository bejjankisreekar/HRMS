from django import forms

from apps.orgchart.models import Team


class TeamForm(forms.ModelForm):
    class Meta:
        model = Team
        fields = ("name", "department", "lead", "description")
        widgets = {
            "name": forms.TextInput(attrs={"class": "ot-input"}),
            "department": forms.Select(attrs={"class": "ot-input"}),
            "lead": forms.Select(attrs={"class": "ot-input"}),
            "description": forms.Textarea(attrs={"class": "ot-input", "rows": 2}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        if organization:
            self.fields["department"].queryset = organization.departments.filter(is_active=True)
            from apps.accounts.hierarchy import org_active_users

            self.fields["lead"].queryset = org_active_users(organization).order_by("first_name")


class AssignManagerForm(forms.Form):
    manager = forms.ModelChoiceField(queryset=None, required=False)
