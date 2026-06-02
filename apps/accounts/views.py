from django.contrib import messages
from django.contrib.auth import logout
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import redirect
from django.urls import reverse
from django.views.generic import FormView, TemplateView, View

from apps.accounts.models import User
from apps.dashboard.views import DashboardRedirectView

from apps.leads.views import ContactPageView

from .auth_utils import login_user
from .forms import LoginForm, OrganizationSignupForm
from .login_portals import DEFAULT_PORTAL, get_login_page_context
from .login_services import log_login_attempt, resolve_post_login_url
from .marketing_features import get_features_page_context
from .marketing_pricing import get_pricing_page_context


class LandingPageView(TemplateView):
    template_name = "marketing/landing.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(get_pricing_page_context())
        return context


class FeaturesPageView(TemplateView):
    template_name = "marketing/features.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(get_features_page_context())
        return context


class PricingPageView(TemplateView):
    template_name = "marketing/pricing.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(get_pricing_page_context())
        return context


class LoginView(FormView):
    template_name = "accounts/login.html"
    form_class = LoginForm

    def get_initial(self):
        initial = super().get_initial()
        portal = self.request.GET.get("portal") or self.request.POST.get("portal")
        if portal:
            initial["portal"] = portal
        return initial

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        portal_id = (
            self.request.POST.get("portal")
            or self.request.GET.get("portal")
            or (context.get("form") and context["form"].initial.get("portal"))
            or DEFAULT_PORTAL
        )
        context.update(get_login_page_context(portal_id))
        context["login_portals_json"] = [
            {
                "id": p["id"],
                "label": p["label"],
                "title": p["title"],
                "subtitle": p["subtitle"],
                "icon": p["icon"],
                "accent": p["accent"],
                "features": p["features"],
                "preview_stats": p["preview_stats"],
            }
            for p in context["login_portals"]
        ]
        return context

    def form_invalid(self, form):
        username = (form.data.get("username") or "").strip()
        portal_id = form.data.get("portal") or DEFAULT_PORTAL
        if username:
            errors = form.non_field_errors()
            log_login_attempt(
                request=self.request,
                portal_id=portal_id,
                username_attempt=username,
                success=False,
                failure_reason=str(errors[0]) if errors else "Invalid credentials",
            )
        return super().form_invalid(form)

    def form_valid(self, form):
        user = form.cleaned_data["user"]
        portal_id = form.cleaned_data.get("portal") or DEFAULT_PORTAL

        if form.cleaned_data.get("remember_me"):
            self.request.session.set_expiry(60 * 60 * 24 * 14)  # 2 weeks
        else:
            self.request.session.set_expiry(0)

        login_user(self.request, user)

        org = getattr(user, "organization", None)
        if org:
            self.request.session["workspace_code"] = org.organization_code
            self.request.session["tenant_schema"] = org.schema_name
        else:
            self.request.session.pop("workspace_code", None)
            self.request.session.pop("tenant_schema", None)

        self.request.session["login_portal"] = portal_id

        log_login_attempt(
            request=self.request,
            portal_id=portal_id,
            username_attempt=form.cleaned_data.get("username") or user.email,
            success=True,
            user=user,
        )

        return redirect(resolve_post_login_url(user, portal_id))


class LogoutView(LoginRequiredMixin, View):
    def post(self, request, *args, **kwargs):
        logout(request)
        return redirect("landing")


class RegisterOrganizationView(FormView):
    template_name = "accounts/register.html"
    form_class = OrganizationSignupForm

    _STEP1_FIELDS = {
        "organization_name",
        "organization_type",
        "organization_type_other",
        "industry",
        "organization_size",
        "official_email",
        "official_phone",
        "website",
        "employee_count",
        "country",
        "state",
        "city",
        "gst_number",
        "registration_number",
        "street_address",
        "timezone",
        "currency",
    }
    _STEP2_FIELDS = {
        "admin_first_name",
        "admin_last_name",
        "admin_username",
        "admin_email",
        "admin_password",
        "admin_confirm_password",
    }

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["register_initial_step"] = self._initial_step_for_form(context.get("form"))
        return context

    def _initial_step_for_form(self, form):
        if not form or not form.errors:
            return 1
        if any(k in form.errors for k in self._STEP2_FIELDS):
            return 2
        if any(k in form.errors for k in ("terms_accepted", "privacy_policy_accepted")):
            return 2
        if any(k in form.errors for k in self._STEP1_FIELDS):
            return 1
        return 2

    def form_valid(self, form):
        org, admin_user = form.save(request=self.request)
        login_user(self.request, admin_user)
        self.request.session["signup_success"] = {
            "organization_name": org.name,
            "organization_code": org.organization_code,
            "schema_name": org.schema_name,
        }
        return redirect("accounts:register_success")


class RegisterSuccessView(TemplateView):
    template_name = "accounts/register_success.html"

    def dispatch(self, request, *args, **kwargs):
        if not request.session.get("signup_success"):
            return redirect("accounts:register")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["signup"] = self.request.session.pop("signup_success", {})
        return context


class ProfileView(LoginRequiredMixin, TemplateView):
    template_name = "accounts/profile.html"


class RoleRedirectView(LoginRequiredMixin, View):
    def get(self, request, *args, **kwargs):
        return DashboardRedirectView.as_view()(request, *args, **kwargs)
