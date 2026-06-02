from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.utils.text import slugify

from apps.accounts.models import User
from apps.organizations.models import Organization
from apps.organizations.services import create_organization_with_tenant_schema_and_admin
from apps.subscriptions.models import FeatureControlAuditLog, OrganizationLimit
from apps.subscriptions.services.billing import sync_subscription_from_org_plan
from apps.subscriptions.services.entitlements import get_org_plan
from apps.subscriptions.services.feature_control import invalidate_org_entitlements, log_feature_action


_field_widget = forms.TextInput(
    attrs={"class": "w-full rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-white/10 dark:bg-white/5 dark:text-white"}
)
_select_widget = forms.Select(
    attrs={"class": "w-full rounded-xl border border-slate-200 px-3 py-2 text-sm dark:border-white/10 dark:bg-white/5 dark:text-white"}
)


class OrganizationFilterForm(forms.Form):
    q = forms.CharField(required=False, label="Search", widget=_field_widget)
    plan = forms.ChoiceField(
        required=False,
        label="Plan",
        choices=(("", "All plans"),) + tuple(Organization.SubscriptionPlan.choices),
        widget=_select_widget,
    )
    status = forms.ChoiceField(
        required=False,
        label="Status",
        choices=(("", "All statuses"),) + tuple(Organization.SubscriptionStatus.choices),
        widget=_select_widget,
    )
    active = forms.ChoiceField(
        required=False,
        label="Active",
        choices=(("", "All"), ("1", "Active only"), ("0", "Inactive only")),
        widget=_select_widget,
    )


_PLATFORM_INPUT = "platform-input"
_PLATFORM_SELECT = "platform-input"
_PLATFORM_TEXTAREA = "platform-input"


class OrganizationManageForm(forms.ModelForm):
    employee_limit = forms.IntegerField(
        required=False,
        min_value=1,
        label="Employee limit",
        widget=forms.NumberInput(
            attrs={"class": _PLATFORM_INPUT, "min": 1, "placeholder": "Use plan default"}
        ),
    )

    class Meta:
        model = Organization
        fields = [
            "name",
            "is_active",
            "organization_type",
            "industry",
            "official_email",
            "official_phone",
            "country",
            "city",
            "currency",
            "employee_count",
            "annual_revenue_range",
            "subscription_plan",
            "subscription_status",
            "trial_start_date",
            "trial_end_date",
            "storage_limit_mb",
            "payroll_enabled",
            "leave_management_enabled",
            "biometric_enabled",
            "onboarding_notes",
        ]
        widgets = {
            "name": forms.TextInput(attrs={"class": _PLATFORM_INPUT, "placeholder": "Organization legal name"}),
            "industry": forms.TextInput(attrs={"class": _PLATFORM_INPUT, "placeholder": "e.g. Technology"}),
            "official_email": forms.EmailInput(attrs={"class": _PLATFORM_INPUT, "placeholder": "billing@company.com"}),
            "official_phone": forms.TextInput(attrs={"class": _PLATFORM_INPUT, "placeholder": "+91 98765 43210"}),
            "country": forms.TextInput(attrs={"class": _PLATFORM_INPUT}),
            "city": forms.TextInput(attrs={"class": _PLATFORM_INPUT}),
            "currency": forms.TextInput(attrs={"class": _PLATFORM_INPUT}),
            "employee_count": forms.NumberInput(attrs={"class": _PLATFORM_INPUT, "min": 0}),
            "storage_limit_mb": forms.NumberInput(attrs={"class": _PLATFORM_INPUT, "min": 100, "placeholder": "e.g. 5120"}),
            "trial_start_date": forms.DateTimeInput(
                attrs={"class": _PLATFORM_INPUT, "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "trial_end_date": forms.DateTimeInput(
                attrs={"class": _PLATFORM_INPUT, "type": "datetime-local"},
                format="%Y-%m-%dT%H:%M",
            ),
            "onboarding_notes": forms.Textarea(
                attrs={"class": _PLATFORM_TEXTAREA, "rows": 4, "placeholder": "Internal notes for support or billing…"}
            ),
            "is_active": forms.CheckboxInput(attrs={"class": "rounded border-slate-300 text-violet-600 focus:ring-violet-500"}),
            "payroll_enabled": forms.CheckboxInput(),
            "leave_management_enabled": forms.CheckboxInput(),
            "biometric_enabled": forms.CheckboxInput(),
        }
        labels = {
            "is_active": "Workspace active",
            "storage_limit_mb": "Storage limit (MB)",
            "annual_revenue_range": "Annual revenue range",
            "subscription_plan": "Subscription plan",
            "subscription_status": "Billing status",
        }
        help_texts = {
            "is_active": "Inactive workspaces cannot be used by tenant users.",
            "storage_limit_mb": "Document and file storage quota for this tenant.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        select_fields = (
            "organization_type",
            "annual_revenue_range",
            "subscription_plan",
            "subscription_status",
        )
        for name in select_fields:
            self.fields[name].widget.attrs["class"] = _PLATFORM_SELECT

        dt_formats = ["%Y-%m-%dT%H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"]
        for dt_field in ("trial_start_date", "trial_end_date"):
            self.fields[dt_field].input_formats = dt_formats
            if self.instance and self.instance.pk:
                val = getattr(self.instance, dt_field, None)
                if val:
                    self.initial[dt_field] = val.strftime("%Y-%m-%dT%H:%M")

        if self.instance and self.instance.pk:
            plan = get_org_plan(self.instance)
            plan_default = plan.employee_limit if plan else None
            plan_label = str(plan_default) if plan_default else "Unlimited"
            self.fields["employee_limit"].help_text = (
                f"Override the subscription plan limit for this organization. "
                f"Plan default: {plan_label}. Leave empty to use the plan default."
            )
            try:
                override = self.instance.feature_limits.employee_limit
            except OrganizationLimit.DoesNotExist:
                override = None
            if override is not None:
                self.initial["employee_limit"] = override

    def save(self, commit=True):
        org = super().save(commit=False)
        employee_limit = self.cleaned_data.get("employee_limit")
        old_plan = None
        if self.instance.pk:
            old_plan = (
                Organization.objects.filter(pk=self.instance.pk)
                .values_list("subscription_plan", flat=True)
                .first()
            )

        if commit:
            org.max_users_allowed = employee_limit
            org.save()

            plan_changed = old_plan is not None and old_plan != org.subscription_plan
            if plan_changed:
                sync_subscription_from_org_plan(
                    org=org,
                    actor=getattr(self, "_actor", None),
                    request=getattr(self, "_request", None),
                )

            limits, _ = OrganizationLimit.objects.get_or_create(organization=org)
            old_val = limits.employee_limit
            limits.employee_limit = employee_limit
            limits.save(update_fields=["employee_limit", "updated_at"])
            if employee_limit is not None:
                org.max_users_allowed = employee_limit
                org.save(update_fields=["max_users_allowed", "updated_at"])
            invalidate_org_entitlements(org)
            if old_val != employee_limit:
                log_feature_action(
                    actor=getattr(self, "_actor", None),
                    action=FeatureControlAuditLog.Action.LIMIT_UPDATE,
                    organization=org,
                    summary=f"Updated employee limit for {org.name}",
                    old_value={"employee_limit": old_val},
                    new_value={"employee_limit": employee_limit},
                    request=getattr(self, "_request", None),
                )
        return org


class SuperAdminOrganizationCreateForm(forms.Form):
    name = forms.CharField(max_length=255, label="Organization name")
    official_email = forms.EmailField(required=False)
    official_phone = forms.CharField(max_length=30, required=False)
    subscription_plan = forms.ChoiceField(choices=Organization.SubscriptionPlan.choices)
    subscription_status = forms.ChoiceField(choices=Organization.SubscriptionStatus.choices)
    max_users_allowed = forms.IntegerField(required=False, min_value=1)
    storage_limit_mb = forms.IntegerField(required=False, min_value=100)
    admin_username = forms.SlugField(max_length=50)
    admin_email = forms.EmailField()
    admin_password = forms.CharField(widget=forms.PasswordInput)
    admin_first_name = forms.CharField(max_length=150, required=False)
    admin_last_name = forms.CharField(max_length=150, required=False)

    def clean_name(self):
        name = self.cleaned_data["name"].strip()
        if Organization.objects.filter(name__iexact=name).exists():
            raise ValidationError("An organization with this name already exists.")
        return name

    def clean_admin_username(self):
        username = slugify(self.cleaned_data["admin_username"]).strip()
        if not username:
            raise ValidationError("Username is required.")
        if User.objects.filter(username__iexact=username).exists():
            raise ValidationError("This username is already taken.")
        return username

    def clean_admin_email(self):
        return self.cleaned_data["admin_email"].lower().strip()

    def save(self):
        now = timezone.now()
        data = self.cleaned_data
        org_data = {
            "name": data["name"],
            "official_email": data.get("official_email") or data["admin_email"],
            "official_phone": data.get("official_phone", ""),
            "subscription_plan": data["subscription_plan"],
            "subscription_status": data["subscription_status"],
            "max_users_allowed": data.get("max_users_allowed"),
            "storage_limit_mb": data.get("storage_limit_mb"),
            "trial_start_date": now,
            "onboarding_status": Organization.OnboardingStatus.COMPLETED,
            "email": data["admin_email"],
        }
        admin_data = {
            "first_name": data.get("admin_first_name", ""),
            "last_name": data.get("admin_last_name", ""),
            "username": data["admin_username"],
            "email": data["admin_email"],
            "password": data["admin_password"],
            "terms_accepted": True,
            "privacy_policy_accepted": True,
        }
        return create_organization_with_tenant_schema_and_admin(org_data=org_data, admin_data=admin_data)


class PlatformUserFilterForm(forms.Form):
    q = forms.CharField(required=False, label="Search", widget=_field_widget)
    role = forms.ChoiceField(
        required=False,
        label="Role",
        choices=(("", "All roles"),) + tuple(User.Role.choices),
        widget=_select_widget,
    )
    organization = forms.ModelChoiceField(
        queryset=Organization.objects.order_by("name"),
        required=False,
        empty_label="All organizations",
        widget=_select_widget,
    )
    active = forms.ChoiceField(
        required=False,
        label="Status",
        choices=(("", "All"), ("1", "Active"), ("0", "Inactive")),
        widget=_select_widget,
    )


class PlatformUserManageForm(forms.ModelForm):
    new_password = forms.CharField(
        required=False,
        widget=forms.PasswordInput(attrs={"class": _PLATFORM_INPUT, "placeholder": "Leave blank to keep current"}),
        label="New password",
    )

    class Meta:
        model = User
        fields = [
            "first_name",
            "last_name",
            "username",
            "email",
            "phone",
            "designation",
            "role",
            "organization",
            "is_active",
            "is_staff",
        ]
        widgets = {
            "first_name": forms.TextInput(attrs={"class": _PLATFORM_INPUT}),
            "last_name": forms.TextInput(attrs={"class": _PLATFORM_INPUT}),
            "username": forms.TextInput(attrs={"class": _PLATFORM_INPUT}),
            "email": forms.EmailInput(attrs={"class": _PLATFORM_INPUT}),
            "phone": forms.TextInput(attrs={"class": _PLATFORM_INPUT}),
            "designation": forms.TextInput(attrs={"class": _PLATFORM_INPUT}),
            "role": forms.Select(attrs={"class": _PLATFORM_SELECT}),
            "organization": forms.Select(attrs={"class": _PLATFORM_SELECT}),
            "is_active": forms.CheckboxInput(attrs={"class": "rounded border-slate-300 text-violet-600"}),
            "is_staff": forms.CheckboxInput(attrs={"class": "rounded border-slate-300 text-violet-600"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["organization"].required = False
        self.fields["organization"].queryset = Organization.objects.order_by("name")

    def clean_username(self):
        username = slugify(self.cleaned_data.get("username") or "").strip()
        if not username:
            raise ValidationError("Username is required.")
        qs = User.objects.filter(username__iexact=username)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise ValidationError("This username is already taken.")
        return username

    def clean_email(self):
        return (self.cleaned_data.get("email") or "").lower().strip()

    def save(self, commit=True):
        user = super().save(commit=False)
        password = self.cleaned_data.get("new_password")
        if password:
            user.set_password(password)
        if commit:
            user.save()
        return user
