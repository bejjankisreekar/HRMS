from django import forms

from .models import ContactLead, NewsletterSubscriber

EMPLOYEE_COUNT_CHOICES = [
    ("1-10", "1-10 employees"),
    ("11-50", "11-50 employees"),
    ("51-250", "51-250 employees"),
    ("251-1000", "251-1,000 employees"),
    ("1000+", "1,000+ employees"),
]

EMPLOYEE_COUNT_FIELD_CHOICES = [("", "Select team size")] + EMPLOYEE_COUNT_CHOICES

MODULE_CHOICES = [
    ("core_hr", "Core HR"),
    ("attendance", "Attendance & shifts"),
    ("payroll", "Payroll"),
    ("leave", "Leave management"),
    ("performance", "Performance"),
    ("analytics", "Reports & analytics"),
    ("growth", "Growth / API"),
]

FIELD_CLASS = "hrms-field__input"
SELECT_CLASS = "hrms-field__input hrms-field__select"
TEXTAREA_CLASS = "hrms-field__input hrms-field__textarea"
CHECKBOX_CLASS = "hrms-field__checkbox"


class ContactLeadForm(forms.ModelForm):
    employee_count = forms.ChoiceField(
        choices=EMPLOYEE_COUNT_FIELD_CHOICES,
        required=True,
        label="Employee count",
        widget=forms.Select(attrs={"class": SELECT_CLASS}),
    )
    interested_modules = forms.MultipleChoiceField(
        choices=MODULE_CHOICES,
        required=False,
        widget=forms.CheckboxSelectMultiple(attrs={"class": CHECKBOX_CLASS}),
        label="Interested modules",
    )

    class Meta:
        model = ContactLead
        fields = [
            "full_name",
            "company_name",
            "work_email",
            "phone_number",
            "employee_count",
            "interested_modules",
            "message",
        ]
        widgets = {
            "full_name": forms.TextInput(
                attrs={"class": FIELD_CLASS, "placeholder": " ", "autocomplete": "name"}
            ),
            "company_name": forms.TextInput(
                attrs={"class": FIELD_CLASS, "placeholder": " ", "autocomplete": "organization"}
            ),
            "work_email": forms.EmailInput(
                attrs={"class": FIELD_CLASS, "placeholder": " ", "autocomplete": "email"}
            ),
            "phone_number": forms.TextInput(
                attrs={"class": FIELD_CLASS, "placeholder": " ", "autocomplete": "tel"}
            ),
            "message": forms.Textarea(
                attrs={"class": TEXTAREA_CLASS, "placeholder": " ", "rows": 4}
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["full_name"].required = True
        self.fields["company_name"].required = True
        self.fields["work_email"].required = True
        self.fields["message"].required = True

    def clean_work_email(self):
        email = self.cleaned_data["work_email"].strip().lower()
        if email.endswith(("@gmail.com", "@yahoo.com", "@hotmail.com")):
            pass  # allow but business emails preferred — no hard block
        return email

    def save(self, commit=True):
        instance = super().save(commit=False)
        instance.interested_modules = self.cleaned_data.get("interested_modules") or []
        if commit:
            instance.save()
        return instance


class NewsletterForm(forms.ModelForm):
    class Meta:
        model = NewsletterSubscriber
        fields = ["email"]
        widgets = {
            "email": forms.EmailInput(
                attrs={
                    "class": FIELD_CLASS,
                    "placeholder": " ",
                    "autocomplete": "email",
                }
            ),
        }
