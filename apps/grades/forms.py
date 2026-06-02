from django import forms

from apps.grades.models import CareerPathStep, Designation, Grade, GradeCategory, GradePermission, GradeStatus
from apps.organizations.models import Department, Organization

_INP = "platform-input w-full"


class GradeForm(forms.ModelForm):
    class Meta:
        model = Grade
        fields = [
            "name",
            "code",
            "level_number",
            "category",
            "description",
            "parent_grade",
            "reporting_grade",
            "priority_order",
            "status",
            "salary_band_min",
            "salary_band_max",
            "departments",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": _INP}),
            "code": forms.TextInput(attrs={"class": _INP}),
            "level_number": forms.NumberInput(attrs={"class": _INP, "min": 1}),
            "category": forms.Select(attrs={"class": _INP}),
            "description": forms.Textarea(attrs={"class": _INP, "rows": 3}),
            "parent_grade": forms.Select(attrs={"class": _INP}),
            "reporting_grade": forms.Select(attrs={"class": _INP}),
            "priority_order": forms.NumberInput(attrs={"class": _INP}),
            "status": forms.Select(attrs={"class": _INP}),
            "salary_band_min": forms.NumberInput(attrs={"class": _INP, "step": "0.01"}),
            "salary_band_max": forms.NumberInput(attrs={"class": _INP, "step": "0.01"}),
            "departments": forms.SelectMultiple(attrs={"class": _INP, "size": 4}),
        }

    def __init__(self, *args, organization: Organization, instance=None, **kwargs):
        super().__init__(*args, instance=instance, **kwargs)
        self.organization = organization
        grade_qs = Grade.objects.filter(organization=organization).order_by("category", "level_number")
        self.fields["parent_grade"].queryset = grade_qs
        self.fields["reporting_grade"].queryset = grade_qs
        self.fields["parent_grade"].required = False
        self.fields["reporting_grade"].required = False
        self.fields["departments"].queryset = Department.objects.filter(organization=organization, is_active=True)
        if not instance:
            self.fields["status"].initial = GradeStatus.ACTIVE

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.organization = self.organization
        if commit:
            obj.save()
            self.save_m2m()
        return obj


class DesignationForm(forms.ModelForm):
    class Meta:
        model = Designation
        fields = ["name", "code", "description", "grade", "priority_order", "status"]
        widgets = {
            "name": forms.TextInput(attrs={"class": _INP}),
            "code": forms.TextInput(attrs={"class": _INP}),
            "description": forms.Textarea(attrs={"class": _INP, "rows": 2}),
            "grade": forms.Select(attrs={"class": _INP}),
            "priority_order": forms.NumberInput(attrs={"class": _INP}),
            "status": forms.Select(attrs={"class": _INP}),
        }

    def __init__(self, *args, organization: Organization, instance=None, **kwargs):
        super().__init__(*args, instance=instance, **kwargs)
        self.organization = organization
        self.fields["grade"].queryset = Grade.objects.filter(
            organization=organization, status=GradeStatus.ACTIVE
        ).order_by("category", "level_number")
        self.fields["grade"].required = False

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.organization = self.organization
        if commit:
            obj.save()
        return obj


class CareerPathForm(forms.ModelForm):
    class Meta:
        model = CareerPathStep
        fields = ["from_grade", "to_grade", "sort_order", "requirements", "is_active"]
        widgets = {
            "from_grade": forms.Select(attrs={"class": _INP}),
            "to_grade": forms.Select(attrs={"class": _INP}),
            "sort_order": forms.NumberInput(attrs={"class": _INP}),
            "requirements": forms.Textarea(attrs={"class": _INP, "rows": 2}),
            "is_active": forms.CheckboxInput(),
        }

    def __init__(self, *args, organization: Organization, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        qs = Grade.objects.filter(organization=organization, status=GradeStatus.ACTIVE)
        self.fields["from_grade"].queryset = qs
        self.fields["to_grade"].queryset = qs


class GradePermissionForm(forms.Form):
    permission_key = forms.ChoiceField(
        choices=GradePermission.PermissionKey.choices,
        widget=forms.Select(attrs={"class": _INP}),
    )
