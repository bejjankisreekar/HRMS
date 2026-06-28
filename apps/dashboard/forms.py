from django import forms
from django.core.exceptions import ValidationError
from django.utils.text import slugify

from apps.accounts.hierarchy import hr_choices_qs, manager_choices_qs
from apps.accounts.models import User
from apps.accounts.role_labels import MANAGED_STAFF_ROLES, role_display_for
from apps.attendance.models import WorkShift
from apps.grades.models import Designation, Grade, GradeStatus
from apps.organizations.models import Department, Organization

_INP = "se-input w-full"

# Roles an Organization Admin may assign when creating/editing staff.
ADMIN_ASSIGNABLE_ROLE_CHOICES = (
    (User.Role.HR, "HR"),
    (User.Role.EMPLOYEE, "Employee"),
)


def _user_choice_label(user: User) -> str:
    return user.choice_label


class StaffCreateForm(forms.Form):
    # --- Role & account ---
    role = forms.ChoiceField(
        choices=ADMIN_ASSIGNABLE_ROLE_CHOICES,
        widget=forms.Select(attrs={"class": _INP}),
    )
    username = forms.SlugField(max_length=50, widget=forms.TextInput(attrs={"class": _INP}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"class": _INP}))
    password = forms.CharField(widget=forms.PasswordInput(attrs={"class": _INP}))
    is_active = forms.BooleanField(required=False, initial=True)

    # --- Personal ---
    first_name = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    last_name = forms.CharField(max_length=150, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    employee_id = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    gender = forms.ChoiceField(
        choices=(("", "Select gender"),) + tuple(User.Gender.choices),
        required=False,
        widget=forms.Select(attrs={"class": _INP}),
    )
    date_of_birth = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": _INP, "type": "date"}),
    )
    blood_group = forms.CharField(
        max_length=10,
        required=False,
        widget=forms.TextInput(attrs={"class": _INP, "placeholder": "e.g. O+"}),
    )
    marital_status = forms.ChoiceField(
        choices=(("", "Select"),) + tuple(User.MaritalStatus.choices),
        required=False,
        widget=forms.Select(attrs={"class": _INP}),
    )
    nationality = forms.CharField(max_length=80, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    profile_picture = forms.ImageField(
        required=False,
        widget=forms.FileInput(attrs={"class": _INP, "accept": "image/*"}),
    )

    # --- Contact ---
    phone = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    alternate_phone = forms.CharField(max_length=30, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    personal_email = forms.EmailField(required=False, widget=forms.EmailInput(attrs={"class": _INP}))
    emergency_contact_name = forms.CharField(
        max_length=120, required=False, widget=forms.TextInput(attrs={"class": _INP})
    )
    emergency_contact_phone = forms.CharField(
        max_length=30, required=False, widget=forms.TextInput(attrs={"class": _INP})
    )
    emergency_contact_relation = forms.CharField(
        max_length=60, required=False, widget=forms.TextInput(attrs={"class": _INP})
    )

    # --- Job ---
    department = forms.ModelChoiceField(
        queryset=Department.objects.none(),
        required=False,
        empty_label="Select",
        widget=forms.Select(attrs={"class": _INP}),
    )
    designation = forms.CharField(max_length=120, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    job_grade = forms.ModelChoiceField(
        queryset=Grade.objects.none(),
        required=False,
        empty_label="Select grade (optional)",
        widget=forms.Select(attrs={"class": _INP}),
    )
    org_designation = forms.ModelChoiceField(
        queryset=Designation.objects.none(),
        required=False,
        empty_label="Select designation (optional)",
        widget=forms.Select(attrs={"class": _INP}),
    )
    business_unit = forms.CharField(max_length=120, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    employment_type = forms.ChoiceField(
        choices=(("", "Select type"),) + tuple(User.EmploymentType.choices),
        required=False,
        widget=forms.Select(attrs={"class": _INP}),
    )
    date_of_joining = forms.DateField(
        required=False,
        widget=forms.DateInput(attrs={"class": _INP, "type": "date"}),
    )
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

    # --- Address ---
    address_line = forms.CharField(
        max_length=255, required=False, widget=forms.TextInput(attrs={"class": _INP})
    )
    city = forms.CharField(max_length=80, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    state = forms.CharField(max_length=80, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    country = forms.CharField(max_length=80, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    postal_code = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={"class": _INP}))

    # --- Payroll / documents ---
    bank_name = forms.CharField(max_length=120, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    bank_account_holder = forms.CharField(
        max_length=120, required=False, widget=forms.TextInput(attrs={"class": _INP})
    )
    bank_account_number = forms.CharField(
        max_length=40, required=False, widget=forms.TextInput(attrs={"class": _INP})
    )
    ifsc_code = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    pan_number = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={"class": _INP}))
    aadhaar_number = forms.CharField(max_length=20, required=False, widget=forms.TextInput(attrs={"class": _INP}))

    internal_notes = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={"class": _INP, "rows": 3}),
    )

    def __init__(self, *args, organization: Organization, created_by: User | None = None, **kwargs):
        super().__init__(*args, **kwargs)
        self.organization = organization
        self.created_by = created_by
        if "role" in self.fields:
            self.fields["role"].choices = (
                (User.Role.HR, role_display_for(User.Role.HR, organization)),
                (User.Role.EMPLOYEE, "Employee"),
            )
        self.fields["reporting_manager"].queryset = manager_choices_qs(organization)
        self.fields["reporting_manager"].empty_label = "Select reporting manager (optional)"
        self.fields["assigned_hr"].queryset = hr_choices_qs(organization)
        self.fields["assigned_hr"].empty_label = "Select HR owner"
        self.fields["reporting_manager"].label_from_instance = _user_choice_label
        self.fields["assigned_hr"].label_from_instance = _user_choice_label
        from apps.dashboard.attendance_utils import ensure_default_shift

        ensure_default_shift(organization)
        self.fields["work_shift"].queryset = WorkShift.objects.filter(organization=organization)
        self.fields["work_shift"].empty_label = "Default shift (org-wide)"
        self.fields["department"].queryset = Department.objects.filter(
            organization=organization, is_active=True
        ).order_by("sort_order", "name")
        self.fields["department"].empty_label = f"Select {organization.department_label.lower()}"
        self.fields["job_grade"].queryset = Grade.objects.filter(
            organization=organization, status=GradeStatus.ACTIVE
        ).order_by("category", "level_number")
        self.fields["org_designation"].queryset = Designation.objects.filter(
            organization=organization, status=GradeStatus.ACTIVE
        ).order_by("name")
        if created_by and created_by.role == User.Role.HR:
            self.fields["assigned_hr"].initial = created_by.pk
            if "role" in self.fields:
                self.fields["role"].choices = ((User.Role.EMPLOYEE, "Employee"),)
                self.fields["role"].initial = User.Role.EMPLOYEE

    def clean_username(self):
        username = slugify(self.cleaned_data["username"]).strip()
        if not username:
            raise ValidationError("Username is required.")
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("This username is already taken.")
        return username

    def clean_email(self):
        return self.cleaned_data["email"].lower().strip()

    def clean_employee_id(self):
        eid = (self.cleaned_data.get("employee_id") or "").strip().upper()
        if not eid:
            return ""
        if User.objects.filter(organization=self.organization, employee_id__iexact=eid).exists():
            raise ValidationError("This employee ID is already used in your organization.")
        return eid

    def clean(self):
        cleaned = super().clean()
        role = cleaned.get("role")
        assigned_hr = cleaned.get("assigned_hr")
        reporting_manager = cleaned.get("reporting_manager")

        # Employees and Managers are owned by an HR person (enables HR oversight
        # and the Employee → Manager → HR two-level leave approval chain).
        if role in MANAGED_STAFF_ROLES:
            if not assigned_hr:
                self.add_error("assigned_hr", "Select the HR person responsible for this employee.")
            elif assigned_hr.role != User.Role.HR or assigned_hr.organization_id != self.organization.pk:
                self.add_error("assigned_hr", "Invalid HR selection.")
        elif assigned_hr:
            cleaned["assigned_hr"] = None

        if reporting_manager and reporting_manager.organization_id != self.organization.pk:
            self.add_error("reporting_manager", "Manager must belong to your organization.")

        return cleaned

    def _val(self, key, default=""):
        v = self.cleaned_data.get(key)
        return default if v is None else v

    def save(self) -> User:
        data = self.cleaned_data
        return User.objects.create_user(
            email=data["email"],
            password=data["password"],
            username=data["username"],
            first_name=data.get("first_name", ""),
            last_name=data.get("last_name", ""),
            phone=data.get("phone", ""),
            role=data["role"],
            organization=self.organization,
            is_staff=False,
            is_active=data.get("is_active", True),
            employee_id=data.get("employee_id", ""),
            gender=data.get("gender", ""),
            date_of_birth=data.get("date_of_birth"),
            blood_group=data.get("blood_group", ""),
            marital_status=data.get("marital_status", ""),
            nationality=data.get("nationality", ""),
            alternate_phone=data.get("alternate_phone", ""),
            personal_email=data.get("personal_email", ""),
            emergency_contact_name=data.get("emergency_contact_name", ""),
            emergency_contact_phone=data.get("emergency_contact_phone", ""),
            emergency_contact_relation=data.get("emergency_contact_relation", ""),
            department=data.get("department"),
            designation=data.get("designation", "") or (
                data.get("org_designation").name if data.get("org_designation") else ""
            ),
            job_grade=data.get("job_grade"),
            org_designation=data.get("org_designation"),
            business_unit=data.get("business_unit", ""),
            employment_type=data.get("employment_type", ""),
            date_of_joining=data.get("date_of_joining"),
            reporting_manager=data.get("reporting_manager"),
            assigned_hr=data.get("assigned_hr") if data["role"] in MANAGED_STAFF_ROLES else None,
            work_shift=data.get("work_shift"),
            work_location=data.get("work_location", ""),
            work_mode=data.get("work_mode", ""),
            address_line=data.get("address_line", ""),
            city=data.get("city", ""),
            state=data.get("state", ""),
            country=data.get("country", ""),
            postal_code=data.get("postal_code", ""),
            bank_name=data.get("bank_name", ""),
            bank_account_holder=data.get("bank_account_holder", ""),
            bank_account_number=data.get("bank_account_number", ""),
            ifsc_code=data.get("ifsc_code", ""),
            pan_number=data.get("pan_number", ""),
            aadhaar_number=data.get("aadhaar_number", ""),
            internal_notes=data.get("internal_notes", ""),
            profile_picture=data.get("profile_picture"),
            employment_status=User.EmploymentStatus.ACTIVE if data.get("is_active", True) else User.EmploymentStatus.INACTIVE,
        )
