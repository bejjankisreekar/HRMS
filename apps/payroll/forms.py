from django import forms

from .models import (
    EmployeeLoan,
    PayrollCycleConfig,
    PayrollSettings,
    Reimbursement,
    SalaryComponent,
    SalaryRevision,
    TaxConfiguration,
)


class ReimbursementForm(forms.ModelForm):
    class Meta:
        model = Reimbursement
        fields = ["category", "amount", "description", "receipt"]
        widgets = {
            "category": forms.Select(attrs={"class": "pr-input"}),
            "amount": forms.NumberInput(attrs={"class": "pr-input", "step": "0.01", "min": "0"}),
            "description": forms.TextInput(attrs={"class": "pr-input", "placeholder": "Expense details"}),
            "receipt": forms.FileInput(attrs={"class": "pr-input"}),
        }


class SalaryRevisionForm(forms.ModelForm):
    class Meta:
        model = SalaryRevision
        fields = ["new_ctc", "effective_date", "reason"]
        widgets = {
            "new_ctc": forms.NumberInput(attrs={"class": "pr-input", "step": "0.01"}),
            "effective_date": forms.DateInput(attrs={"class": "pr-input", "type": "date"}),
            "reason": forms.Textarea(attrs={"class": "pr-input", "rows": 2}),
        }


class SalaryComponentForm(forms.ModelForm):
    class Meta:
        model = SalaryComponent
        fields = [
            "name", "code", "component_type", "category", "calc_type",
            "default_amount", "default_percent", "is_taxable", "is_statutory", "is_active",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": "pr-input"}),
            "code": forms.TextInput(attrs={"class": "pr-input"}),
            "component_type": forms.Select(attrs={"class": "pr-input"}),
            "category": forms.Select(attrs={"class": "pr-input"}),
            "calc_type": forms.Select(attrs={"class": "pr-input"}),
            "default_amount": forms.NumberInput(attrs={"class": "pr-input", "step": "0.01"}),
            "default_percent": forms.NumberInput(attrs={"class": "pr-input", "step": "0.01"}),
        }


class EmployeeLoanForm(forms.ModelForm):
    class Meta:
        model = EmployeeLoan
        fields = ["principal", "interest_rate", "tenure_months", "emi_amount", "start_date"]
        widgets = {
            "principal": forms.NumberInput(attrs={"class": "pr-input", "step": "0.01"}),
            "interest_rate": forms.NumberInput(attrs={"class": "pr-input", "step": "0.01"}),
            "tenure_months": forms.NumberInput(attrs={"class": "pr-input"}),
            "emi_amount": forms.NumberInput(attrs={"class": "pr-input", "step": "0.01"}),
            "start_date": forms.DateInput(attrs={"class": "pr-input", "type": "date"}),
        }


class PayrollCycleConfigForm(forms.ModelForm):
    class Meta:
        model = PayrollCycleConfig
        fields = [
            "frequency", "payroll_day", "salary_day",
            "attendance_cutoff_day", "leave_cutoff_day", "approval_deadline_day",
        ]
        widgets = {
            "frequency": forms.Select(attrs={"class": "pr-input"}),
            "payroll_day": forms.NumberInput(attrs={"class": "pr-input", "min": 1, "max": 31}),
            "salary_day": forms.NumberInput(attrs={"class": "pr-input", "min": 1, "max": 31}),
            "attendance_cutoff_day": forms.NumberInput(attrs={"class": "pr-input", "min": 1, "max": 31}),
            "leave_cutoff_day": forms.NumberInput(attrs={"class": "pr-input", "min": 1, "max": 31}),
            "approval_deadline_day": forms.NumberInput(attrs={"class": "pr-input", "min": 1, "max": 31}),
        }


class PayrollSettingsForm(forms.ModelForm):
    class Meta:
        model = PayrollSettings
        fields = [
            "currency", "decimal_precision", "rounding_rule",
            "auto_payroll_enabled", "payslip_email_enabled", "approval_workflow_enabled",
            "payslip_format", "default_salary_structure",
        ]
        widgets = {
            "currency": forms.TextInput(attrs={"class": "pr-input", "maxlength": 3}),
            "decimal_precision": forms.NumberInput(attrs={"class": "pr-input", "min": 0, "max": 4}),
            "rounding_rule": forms.Select(attrs={"class": "pr-input"}),
            "payslip_format": forms.Select(attrs={"class": "pr-input"}),
            "default_salary_structure": forms.Select(attrs={"class": "pr-input"}),
        }

    def __init__(self, *args, organization=None, **kwargs):
        super().__init__(*args, **kwargs)
        if organization is not None:
            from .models import SalaryStructure

            self.fields["default_salary_structure"].queryset = SalaryStructure.objects.filter(
                organization=organization, is_active=True
            )


class TaxConfigurationForm(forms.ModelForm):
    class Meta:
        model = TaxConfiguration
        fields = ["regime", "standard_deduction"]
        widgets = {
            "regime": forms.TextInput(attrs={"class": "pr-input"}),
            "standard_deduction": forms.NumberInput(attrs={"class": "pr-input", "step": "0.01"}),
        }
