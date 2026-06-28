"""Staff edit form — mirrors create fields for updates."""

from django import forms
from django.core.exceptions import ValidationError
from django.utils.text import slugify

from apps.accounts.hierarchy import hr_choices_qs, manager_choices_qs
from apps.accounts.models import User
from apps.accounts.role_labels import MANAGED_STAFF_ROLES, role_display_for
from apps.attendance.models import WorkShift
from apps.dashboard.forms import ADMIN_ASSIGNABLE_ROLE_CHOICES
from apps.grades.models import Designation, Grade, GradeStatus
from apps.organizations.models import Department, Organization

_INP = "se-input w-full"


class StaffEditForm(forms.Form):
    role = forms.ChoiceField(
        choices=ADMIN_ASSIGNABLE_ROLE_CHOICES,
        widget=forms.Select(attrs={"class": _INP}),
    )
    username = forms.SlugField(max_length=50, widget=forms.TextInput(attrs={"class": _INP}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": _INP}))
    is_active = forms.BooleanField(required=False)
    employment_status = forms.ChoiceField(
        choices=User.EmploymentStatus.choices,
        widget=forms.Select(attrs={"class": _INP}),
    )

    first_name = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    last_name = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    employee_id = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    gender = forms.ChoiceField(
        choices=(("", "Select gender"),) + tuple(User.Gender.choices),
        required=False,
        widget=forms.Select(attrs={"class": _INP}),
    )
    date_of_birth = forms.DateField(required=False, widget=forms.DateInput(attrs={"class": _INP, "type": "date"}))
    blood_group = forms.CharField(max_length=10, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    marital_status = forms.ChoiceField(
        choices=(("", "Select"),) + tuple(User.MaritalStatus.choices),
        required=False,
        widget=forms.Select(attrs={"class": _INP}),
    )
    nationality = forms.CharField(max_length=80, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    profile_picture = forms.ImageField(required=False, widget=forms.FileInput(attrs={"class": _INP, "accept": "image/*"}))

    phone = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    alternate_phone = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    personal_email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={"class": _INP}))
    emergency_contact_name = forms.CharField(max_length=120, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    emergency_contact_phone = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    emergency_contact_relation = forms.CharField(max_length=60, required=False, widget=forms.TextInput(attrs={"class": _INP}))

    department = forms.ModelChoiceField(
        queryset=Department.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": _INP}),
    )
    designation = forms.CharField(max_length=120, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    job_grade = forms.ModelChoiceField(
        queryset=Grade.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": _INP}),
    )
    org_designation = forms.ModelChoiceField(
        queryset=Designation.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": _INP}),
    )
    business_unit = forms.CharField(max_length=120, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    employment_type = forms.ChoiceField(
        choices=(("", "Select type"),) + tuple(User.EmploymentType.choices),
        required=False,
        widget=forms.Select(attrs={"class": _INP}),
    )
    date_of_joining = forms.DateField(required=False, widget=forms.DateInput(attrs={"class": _INP, "type": "date"}))
    reporting_manager = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": _INP}),
    )
    assigned_hr = forms.ModelChoiceField(
        queryset=User.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": _INP}),
    )
    work_shift = forms.ModelChoiceField(
        queryset=WorkShift.objects.none(),
        required=False,
        widget=forms.Select(attrs={"class": _INP}),
    )
    work_location = forms.CharField(max_length=120, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    work_mode = forms.ChoiceField(
        choices=(("", "Select mode"),) + tuple(User.WorkMode.choices),
        required=False,
        widget=forms.Select(attrs={"class": _INP}),
    )

    address_line = forms.CharField(max_length=255, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    city = forms.CharField(max_length=80, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    state = forms.CharField(max_length=80, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    country = forms.CharField(max_length=80, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    postal_code = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={"class": _INP}))

    bank_name = forms.CharField(max_length=120, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    bank_account_holder = forms.CharField(max_length=120, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    bank_account_number = forms.CharField(max_length=40, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    ifsc_code = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    pan_number = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    aadhaar_number = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    internal_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"class": _INP, "rows": 3}))

    new_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={"class": _INP, "autocomplete": "new-password"}),
        help_text="Leave blank to keep current password",
    )
    can_access_compliance = forms.BooleanField(required=False)

    def __init__(self, *args, instance: User, organization: Organization, editor: User, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = instance
        self.organization = organization
        self.editor = editor

        self.fields["role"].choices = (
            (User.Role.HR, role_display_for(User.Role.HR, organization)),
            (User.Role.EMPLOYEE, "Employee"),
        )
        self.fields["reporting_manager"].queryset = manager_choices_qs(organization).exclude(pk=instance.pk)
        self.fields["assigned_hr"].queryset = hr_choices_qs(organization)
        self.fields["work_shift"].queryset = WorkShift.objects.filter(organization=organization)
        self.fields["department"].queryset = Department.objects.filter(organization=organization, is_active=True)
        self.fields["job_grade"].queryset = Grade.objects.filter(organization=organization, status=GradeStatus.ACTIVE)
        self.fields["org_designation"].queryset = Designation.objects.filter(
            organization=organization, status=GradeStatus.ACTIVE
        )

        if editor.role == User.Role.HR:
            self.fields["role"].choices = ((User.Role.EMPLOYEE, "Employee"),)
            self.fields["role"].disabled = True

        if instance.role == User.Role.ADMIN:
            self.fields["role"].choices = ((User.Role.ADMIN, "Organization Admin"),)
            self.fields["role"].disabled = True

        # Compliance-access grant is only meaningful for HR accounts, and only an Admin may set it.
        if not (editor.role == User.Role.ADMIN and instance.role == User.Role.HR):
            del self.fields["can_access_compliance"]

        if not args:
            self._populate_initial()

    def _populate_initial(self):
        u = self.instance
        for name in self.fields:
            if name == "new_password":
                continue
            if hasattr(u, name):
                self.fields[name].initial = getattr(u, name)

    def clean_username(self):
        username = slugify(self.cleaned_data["username"]).strip()
        if not username:
            raise ValidationError("Username is required.")
        clash = User.objects.filter(username__iexact=username).exclude(pk=self.instance.pk)
        if clash.exists():
            raise ValidationError("This username is already taken.")
        return username

    def clean_email(self):
        return self.cleaned_data["email"].lower().strip()

    def clean_employee_id(self):
        eid = (self.cleaned_data.get("employee_id") or "").strip().upper()
        if not eid:
            return ""
        clash = User.objects.filter(organization=self.organization, employee_id__iexact=eid).exclude(
            pk=self.instance.pk
        )
        if clash.exists():
            raise ValidationError("This employee ID is already used.")
        return eid

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("role") or self.instance.role
        if role in MANAGED_STAFF_ROLES and not cleaned.get("assigned_hr"):
            self.add_error("assigned_hr", "Select the HR owner for this employee.")
        rm = cleaned.get("reporting_manager")
        if rm and rm.pk == self.instance.pk:
            self.add_error("reporting_manager", "Employee cannot report to themselves.")
        return cleaned

    def save(self) -> User:
        u = self.instance
        data = self.cleaned_data
        skip = {"new_password", "profile_picture"}
        for key, val in data.items():
            if key in skip or key not in self.fields:
                continue
            if self.fields[key].disabled:
                continue
            setattr(u, key, val)

        if data.get("org_designation"):
            u.designation = data["org_designation"].name
        elif data.get("designation"):
            u.designation = data["designation"]

        if data["role"] == User.Role.HR:
            u.assigned_hr = None

        if data.get("profile_picture"):
            u.profile_picture = data["profile_picture"]

        if data.get("new_password"):
            u.set_password(data["new_password"])

        u.save()
        return u
