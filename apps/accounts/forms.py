from django import forms
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.text import slugify

from apps.organizations.models import Organization
from apps.organizations.services import create_organization_with_tenant_schema_and_admin

from apps.accounts.login_portals import DEFAULT_PORTAL, LOGIN_PORTALS, get_portal
from apps.accounts.login_services import user_allowed_for_portal

from .models import User

PORTAL_CHOICES = [(p["id"], p["label"]) for p in LOGIN_PORTALS]

PAIN_POINT_CHOICES = [
    ("ATTENDANCE", "Attendance tracking"),
    ("PAYROLL", "Payroll processing"),
    ("LEAVE", "Leave management"),
    ("REPORTING", "Reporting & analytics"),
]


class LoginForm(forms.Form):
    portal = forms.ChoiceField(
        choices=PORTAL_CHOICES,
        initial=DEFAULT_PORTAL,
        widget=forms.HiddenInput(),
    )
    username = forms.CharField(
        label="Email or username",
        widget=forms.TextInput(attrs={"autocomplete": "username"}),
    )
    password = forms.CharField(widget=forms.PasswordInput(attrs={"autocomplete": "current-password"}))
    remember_me = forms.BooleanField(required=False, label="Keep me signed in")

    def clean(self):
        cleaned = super().clean()
        username = (cleaned.get("username") or "").strip()
        password = cleaned.get("password")
        portal_id = cleaned.get("portal") or DEFAULT_PORTAL

        if portal_id not in {p["id"] for p in LOGIN_PORTALS}:
            portal_id = DEFAULT_PORTAL
            cleaned["portal"] = portal_id

        if not username or not password:
            return cleaned

        user = authenticate(username=username, password=password)
        if user is None:
            raise forms.ValidationError("Invalid email/username or password.")
        if not user.is_active:
            raise forms.ValidationError("This account is inactive.")

        if not user_allowed_for_portal(user, portal_id):
            portal = get_portal(portal_id)
            raise forms.ValidationError(portal["role_mismatch_message"])

        cleaned["user"] = user
        cleaned["portal"] = portal_id
        return cleaned


class OrganizationSignupForm(forms.Form):
    # --- Required ---
    organization_name = forms.CharField(max_length=255, label="Organization name")
    admin_username = forms.SlugField(max_length=50, label="Username")
    admin_email = forms.EmailField(label="Email")
    admin_password = forms.CharField(
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        label="Password",
    )
    admin_confirm_password = forms.CharField(
        widget=forms.PasswordInput(attrs={"autocomplete": "new-password"}),
        label="Confirm password",
    )
    terms_accepted = forms.BooleanField(required=True, label="I accept the Terms of Service")
    privacy_policy_accepted = forms.BooleanField(required=True, label="I accept the Privacy Policy")

    # --- Step 1: Organization (optional) ---
    organization_type = forms.ChoiceField(
        choices=Organization.OrganizationType.choices,
        required=False,
        initial=Organization.OrganizationType.COMPANY,
    )
    organization_type_other = forms.CharField(max_length=120, required=False, label="Specify organization type")
    industry = forms.CharField(max_length=120, required=False)
    tagline = forms.CharField(max_length=255, required=False)
    description = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 3}))
    logo = forms.ImageField(required=False)
    website = forms.URLField(required=False)
    established_year = forms.IntegerField(required=False, min_value=1800, max_value=2200)
    employee_count = forms.IntegerField(required=False, min_value=0)
    organization_size = forms.ChoiceField(
        choices=(("", "Select size"),) + tuple(Organization.OrganizationSize.choices),
        required=False,
    )
    annual_revenue_range = forms.ChoiceField(
        choices=(("", "Select range"),) + tuple(Organization.RevenueRange.choices),
        required=False,
    )

    official_email = forms.EmailField(required=False)
    support_email = forms.EmailField(required=False)
    official_phone = forms.CharField(max_length=30, required=False)
    alternate_phone = forms.CharField(max_length=30, required=False)
    whatsapp_number = forms.CharField(max_length=30, required=False)

    country = forms.CharField(max_length=80, required=False)
    state = forms.CharField(max_length=80, required=False)
    city = forms.CharField(max_length=80, required=False)
    area = forms.CharField(max_length=120, required=False)
    street_address = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))
    postal_code = forms.CharField(max_length=20, required=False)

    # --- Step 3: HRMS config (optional) ---
    timezone = forms.CharField(max_length=64, required=False, initial="Asia/Kolkata")
    currency = forms.ChoiceField(
        choices=(("INR", "INR"), ("USD", "USD"), ("EUR", "EUR"), ("GBP", "GBP")),
        required=False,
        initial="INR",
    )
    language = forms.ChoiceField(
        choices=(("en", "English"), ("hi", "Hindi")),
        required=False,
        initial="en",
    )
    date_format = forms.ChoiceField(
        choices=(("", "Select"),) + tuple(Organization.DateFormat.choices),
        required=False,
    )
    attendance_type = forms.ChoiceField(
        choices=(("", "Select"),) + tuple(Organization.AttendanceType.choices),
        required=False,
    )
    payroll_cycle = forms.ChoiceField(
        choices=(("", "Select"),) + tuple(Organization.PayrollCycle.choices),
        required=False,
    )
    week_start_day = forms.ChoiceField(
        choices=(("", "Select"),) + tuple(Organization.WeekStartDay.choices),
        required=False,
    )
    financial_year_start = forms.DateField(required=False, widget=forms.DateInput(attrs={"type": "date"}))
    shift_enabled = forms.BooleanField(required=False)
    biometric_enabled = forms.BooleanField(required=False)
    leave_management_enabled = forms.BooleanField(required=False, initial=True)
    payroll_enabled = forms.BooleanField(required=False, initial=True)

    subscription_plan = forms.ChoiceField(
        choices=Organization.SubscriptionPlan.choices,
        required=False,
        initial=Organization.SubscriptionPlan.FREE,
    )

    how_did_you_hear_about_us = forms.ChoiceField(
        choices=(("", "Select"),) + tuple(Organization.HearAboutUs.choices),
        required=False,
    )
    expected_employee_growth = forms.ChoiceField(
        choices=(("", "Select"),) + tuple(Organization.ExpectedGrowth.choices),
        required=False,
    )
    current_hrms_used = forms.CharField(max_length=120, required=False)
    pain_points = forms.MultipleChoiceField(choices=PAIN_POINT_CHOICES, required=False)
    onboarding_notes = forms.CharField(required=False, widget=forms.Textarea(attrs={"rows": 2}))

    # School fields
    board_type = forms.ChoiceField(
        choices=(("", "Select"),) + tuple(Organization.BoardType.choices),
        required=False,
    )
    total_students = forms.IntegerField(required=False, min_value=0)
    total_teachers = forms.IntegerField(required=False, min_value=0)
    classes_available = forms.IntegerField(required=False, min_value=0)
    transport_enabled = forms.BooleanField(required=False)
    hostel_enabled = forms.BooleanField(required=False)
    library_enabled = forms.BooleanField(required=False)

    # Company fields
    gst_number = forms.CharField(max_length=30, required=False)
    tax_number = forms.CharField(max_length=120, required=False)
    registration_number = forms.CharField(max_length=120, required=False)
    company_type = forms.ChoiceField(
        choices=(("", "Select"),) + tuple(Organization.CompanyType.choices),
        required=False,
    )
    departments_count = forms.IntegerField(required=False, min_value=0)
    branch_count = forms.IntegerField(required=False, min_value=0)

    # --- Step 2: Admin (optional except required above) ---
    admin_first_name = forms.CharField(max_length=150, required=False)
    admin_last_name = forms.CharField(max_length=150, required=False)
    admin_mobile_number = forms.CharField(max_length=30, required=False)
    admin_designation = forms.CharField(max_length=120, required=False)
    admin_profile_photo = forms.ImageField(required=False)

    def clean_organization_name(self):
        name = self.cleaned_data["organization_name"].strip()
        if len(name) < 2:
            raise ValidationError("Organization name is too short.")
        return name

    def clean_admin_username(self):
        username = slugify(self.cleaned_data["admin_username"]).strip()
        if not username:
            raise ValidationError("Username is required.")
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError(
                "This username is already taken. Pick a different username, or remove the "
                "existing account from the platform console (Super Admin → All users)."
            )
        return username

    def clean_admin_email(self):
        return self.cleaned_data["admin_email"].lower().strip()

    def clean_admin_password(self):
        pwd = self.cleaned_data["admin_password"]
        validate_password(pwd)
        return pwd

    def clean(self):
        cleaned = super().clean()
        pwd = cleaned.get("admin_password")
        confirm = cleaned.get("admin_confirm_password")
        if pwd and confirm and pwd != confirm:
            raise ValidationError("Passwords do not match.")

        name = (cleaned.get("organization_name") or "").strip()
        if name and Organization.objects.filter(name__iexact=name).exists():
            raise ValidationError("An organization with this name already exists.")
        return cleaned

    def _val(self, key, default=""):
        v = self.cleaned_data.get(key)
        if v is None:
            return default
        return v

    def save(self, request=None):
        now = timezone.now()
        org_data = {
            "name": self.cleaned_data["organization_name"].strip(),
            "organization_type": self._val("organization_type") or Organization.OrganizationType.COMPANY,
            "organization_type_other": self._val("organization_type_other"),
            "industry": self._val("industry"),
            "tagline": self._val("tagline"),
            "description": self._val("description"),
            "logo": self.cleaned_data.get("logo"),
            "website": self._val("website"),
            "established_year": self.cleaned_data.get("established_year"),
            "employee_count": self.cleaned_data.get("employee_count"),
            "organization_size": self._val("organization_size"),
            "annual_revenue_range": self._val("annual_revenue_range"),
            "official_email": self._val("official_email") or self.cleaned_data["admin_email"],
            "support_email": self._val("support_email"),
            "official_phone": self._val("official_phone"),
            "alternate_phone": self._val("alternate_phone"),
            "whatsapp_number": self._val("whatsapp_number"),
            "country": self._val("country"),
            "state": self._val("state"),
            "city": self._val("city"),
            "area": self._val("area"),
            "street_address": self._val("street_address"),
            "postal_code": self._val("postal_code"),
            "timezone": self._val("timezone") or "Asia/Kolkata",
            "currency": self._val("currency") or "INR",
            "language": self._val("language") or "en",
            "date_format": self._val("date_format"),
            "attendance_type": self._val("attendance_type"),
            "payroll_cycle": self._val("payroll_cycle"),
            "week_start_day": self._val("week_start_day"),
            "financial_year_start": self.cleaned_data.get("financial_year_start"),
            "shift_enabled": bool(self.cleaned_data.get("shift_enabled")),
            "biometric_enabled": bool(self.cleaned_data.get("biometric_enabled")),
            "leave_management_enabled": bool(self.cleaned_data.get("leave_management_enabled", True)),
            "payroll_enabled": bool(self.cleaned_data.get("payroll_enabled", True)),
            "subscription_plan": self._val("subscription_plan") or Organization.SubscriptionPlan.FREE,
            "trial_start_date": now,
            "subscription_status": Organization.SubscriptionStatus.TRIAL,
            "onboarding_status": Organization.OnboardingStatus.COMPLETED,
            "how_did_you_hear_about_us": self._val("how_did_you_hear_about_us"),
            "expected_employee_growth": self._val("expected_employee_growth"),
            "current_hrms_used": self._val("current_hrms_used"),
            "pain_points": list(self.cleaned_data.get("pain_points") or []),
            "required_modules": [],
            "onboarding_notes": self._val("onboarding_notes"),
            "board_type": self._val("board_type"),
            "total_students": self.cleaned_data.get("total_students"),
            "total_teachers": self.cleaned_data.get("total_teachers"),
            "classes_available": self.cleaned_data.get("classes_available"),
            "transport_enabled": bool(self.cleaned_data.get("transport_enabled")),
            "hostel_enabled": bool(self.cleaned_data.get("hostel_enabled")),
            "library_enabled": bool(self.cleaned_data.get("library_enabled")),
            "gst_number": self._val("gst_number"),
            "tax_number": self._val("tax_number"),
            "registration_number": self._val("registration_number"),
            "company_type": self._val("company_type"),
            "departments_count": self.cleaned_data.get("departments_count"),
            "branch_count": self.cleaned_data.get("branch_count"),
            "email": self.cleaned_data["admin_email"],
            "phone": self._val("official_phone") or self._val("admin_mobile_number"),
        }

        if request:
            org_data["signup_ip"] = request.META.get("REMOTE_ADDR")
            ua = request.META.get("HTTP_USER_AGENT", "")[:120]
            org_data["signup_browser"] = ua
            org_data["signup_device"] = "mobile" if "Mobile" in ua else "desktop"

        admin_data = {
            "first_name": self._val("admin_first_name"),
            "last_name": self._val("admin_last_name"),
            "username": self.cleaned_data["admin_username"],
            "email": self.cleaned_data["admin_email"],
            "mobile_number": self._val("admin_mobile_number"),
            "designation": self._val("admin_designation"),
            "password": self.cleaned_data["admin_password"],
            "profile_picture": self.cleaned_data.get("admin_profile_photo"),
            "terms_accepted": bool(self.cleaned_data.get("terms_accepted")),
            "privacy_policy_accepted": bool(self.cleaned_data.get("privacy_policy_accepted")),
        }

        return create_organization_with_tenant_schema_and_admin(org_data=org_data, admin_data=admin_data)
