from django import forms

from .models import Reimbursement, SalaryRevision


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
