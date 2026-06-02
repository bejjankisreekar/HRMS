from django import forms
from django.utils.text import slugify

from apps.organizations.models import Department

_INP = "platform-input w-full"


class DepartmentForm(forms.ModelForm):
    class Meta:
        model = Department
        fields = ("name", "code", "description", "is_active", "sort_order")
        widgets = {
            "name": forms.TextInput(attrs={"class": _INP, "placeholder": "e.g. Science, Kitchen, Level 1"}),
            "code": forms.TextInput(attrs={"class": _INP, "placeholder": "Optional short code"}),
            "description": forms.Textarea(attrs={"class": _INP, "rows": 2}),
            "is_active": forms.CheckboxInput(),
            "sort_order": forms.NumberInput(attrs={"class": _INP, "min": 0}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.fields["sort_order"].required = False
        self.fields["code"].required = False

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if not name:
            raise forms.ValidationError("Name is required.")
        qs = Department.objects.filter(organization=self.organization, name__iexact=name)
        if self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("This name already exists.")
        return name

    def clean_code(self):
        code = (self.cleaned_data.get("code") or "").strip()
        if not code:
            return ""
        return slugify(code)[:40]

    def save(self, commit=True):
        dept = super().save(commit=False)
        dept.organization = self.organization
        if commit:
            dept.save()
        return dept
