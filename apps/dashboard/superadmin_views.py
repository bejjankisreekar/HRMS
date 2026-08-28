import json

from django.contrib import messages
from django.db.models import Count, Max, Q
from django.db.utils import ProgrammingError
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, FormView, ListView, UpdateView

from apps.accounts.models import User
from apps.organizations.models import Organization
from apps.organizations.services import delete_organization_and_tenant
from apps.storage.analytics import build_org_storage_context
from apps.storage.scanner import sync_organization_files
from apps.subscriptions import plan_features
from apps.subscriptions.models import Subscription
from apps.subscriptions.services.org_features import build_org_feature_matrix

from .mixins import SuperAdminRequiredMixin
from .superadmin_forms import (
    OrganizationFilterForm,
    OrganizationManageForm,
    PlatformUserFilterForm,
    PlatformUserManageForm,
    SuperAdminOrganizationCreateForm,
)


class SuperAdminDashboardView(SuperAdminRequiredMixin, ListView):
    """Platform overview with live metrics."""
    template_name = "dashboard/superadmin/overview.html"
    context_object_name = "recent_organizations"

    def get_queryset(self):
        return Organization.objects.order_by("-created_at")[:8]

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        orgs = Organization.objects.all()
        context["stats"] = {
            "organizations_total": orgs.count(),
            "organizations_active": orgs.filter(is_active=True).count(),
            "users_total": User.objects.count(),
            "tenant_users": User.objects.exclude(role=User.Role.SUPER_ADMIN).count(),
            "subscriptions_active": orgs.filter(
                subscription_status=Organization.SubscriptionStatus.ACTIVE
            ).count(),
            "trials": orgs.filter(subscription_status=Organization.SubscriptionStatus.TRIAL).count(),
            "growth": Subscription.objects.filter(
                plan__slug=plan_features.GROWTH_SLUG, plan__is_active=True
            ).count(),
        }
        context["plan_breakdown"] = (
            orgs.values("subscription_plan")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        context["recent_users"] = User.objects.select_related("organization").order_by("-date_joined")[:10]
        return context


class OrganizationListView(SuperAdminRequiredMixin, ListView):
    template_name = "dashboard/superadmin/organization_list.html"
    context_object_name = "organizations"
    paginate_by = 20

    def get_queryset(self):
        qs = Organization.objects.annotate(user_count=Count("users")).order_by("-created_at")
        self.filter_form = OrganizationFilterForm(self.request.GET or None)
        if self.filter_form.is_valid():
            q = self.filter_form.cleaned_data.get("q")
            plan = self.filter_form.cleaned_data.get("plan")
            status = self.filter_form.cleaned_data.get("status")
            active = self.filter_form.cleaned_data.get("active")
            if q:
                qs = qs.filter(
                    Q(name__icontains=q)
                    | Q(organization_code__icontains=q)
                    | Q(official_email__icontains=q)
                    | Q(schema_name__icontains=q)
                )
            if plan:
                qs = qs.filter(subscription_plan=plan)
            if status:
                qs = qs.filter(subscription_status=status)
            if active == "1":
                qs = qs.filter(is_active=True)
            elif active == "0":
                qs = qs.filter(is_active=False)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = getattr(self, "filter_form", OrganizationFilterForm())
        return context


class OrganizationDetailView(SuperAdminRequiredMixin, DetailView):
    model = Organization
    template_name = "dashboard/superadmin/organization_detail.html"
    context_object_name = "organization"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        org = self.object
        context["org_users"] = User.objects.filter(organization=org).order_by("role", "email")
        context["user_count"] = context["org_users"].count()
        context["storage_api"] = reverse("dashboard:storage:api_action")
        context["organization_id"] = org.pk
        context["last_activity"] = self._org_last_activity(org)

        try:
            if self.request.GET.get("sync_storage") == "1":
                sync_organization_files(org)
            elif not org.stored_files.exists():
                sync_organization_files(org)
            storage_ctx = build_org_storage_context(org)
        except ProgrammingError:
            storage_ctx = self._empty_storage_context()
            messages.warning(
                self.request,
                "Storage analytics tables are not ready. Run: python manage.py migrate storage",
            )

        context.update(storage_ctx)
        context["upload_trend_json"] = json.dumps(storage_ctx["upload_trend_json"])
        context["role_chart_json"] = json.dumps(storage_ctx["role_chart_json"])
        context["category_chart_json"] = json.dumps(storage_ctx["category_chart_json"])
        context["dept_chart_json"] = json.dumps(storage_ctx["dept_chart_json"])

        try:
            org_matrix = build_org_feature_matrix(org)
            context["org_feature_matrix"] = org_matrix
            context["org_plan"] = org_matrix["plan"]
            context["org_feature_summary"] = org_matrix["summary"]
            context["org_feature_groups"] = org_matrix["groups"]
            context["org_features_api"] = reverse(
                "dashboard:super_organization_features_api",
                kwargs={"pk": org.pk},
            )
        except ProgrammingError:
            context["org_feature_matrix"] = None
            context["org_feature_groups"] = []

        return context

    @staticmethod
    def _org_last_activity(org: Organization):
        candidates = [org.updated_at]
        user_login = User.objects.filter(organization=org).aggregate(m=Max("last_login"))["m"]
        if user_login:
            candidates.append(user_login)
        return max(candidates)

    @staticmethod
    def _empty_storage_context() -> dict:
        empty_trend = {"labels": [], "uploads": [], "bytes": []}
        empty_chart = {"labels": [], "values": []}
        return {
            "storage": {
                "total_label": "0 MB",
                "remaining_label": "—",
                "limit_label": "—",
                "usage_percent": 0,
                "file_count": 0,
                "upload_growth_percent": 0,
                "uploads_this_month": 0,
                "largest_consumer": "—",
                "active_files": 0,
                "cloud_usage_percent": 0,
                "threshold": "ok",
            },
            "role_breakdown": [],
            "user_storage_rows": [],
            "category_breakdown": [],
            "dept_breakdown": [],
            "upload_trend_json": empty_trend,
            "role_chart_json": empty_chart,
            "category_chart_json": empty_chart,
            "dept_chart_json": empty_chart,
            "plan_limits": {},
            "health": {"score": 100, "risks": []},
            "insights": [],
            "audit_logs": [],
            "large_files": [],
            "org_files": [],
            "duplicate_groups": 0,
            "storage_unavailable": True,
        }


class OrganizationCreateView(SuperAdminRequiredMixin, FormView):
    template_name = "dashboard/superadmin/organization_form.html"
    form_class = SuperAdminOrganizationCreateForm
    success_url = reverse_lazy("dashboard:super_organizations")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["form_title"] = "Create organization"
        context["form_subtitle"] = "Provision workspace, schema, and admin account"
        context["submit_label"] = "Create organization"
        return context

    def form_valid(self, form):
        org, admin = form.save()
        messages.success(
            self.request,
            f"Created {org.name} (workspace {org.organization_code}). Admin: {admin.username}",
        )
        return redirect("dashboard:super_organization_detail", pk=org.pk)


class OrganizationUpdateView(SuperAdminRequiredMixin, UpdateView):
    model = Organization
    form_class = OrganizationManageForm
    template_name = "dashboard/superadmin/organization_edit.html"
    context_object_name = "organization"

    def form_valid(self, form):
        form._actor = self.request.user
        form._request = self.request
        return super().form_valid(form)

    def get_success_url(self):
        messages.success(self.request, f"Updated settings for {self.object.name}.")
        return reverse("dashboard:super_organization_detail", kwargs={"pk": self.object.pk})


class OrganizationDeleteView(SuperAdminRequiredMixin, DeleteView):
    model = Organization
    template_name = "dashboard/superadmin/organization_confirm_delete.html"
    context_object_name = "organization"
    success_url = reverse_lazy("dashboard:super_organizations")

    def delete(self, request, *args, **kwargs):
        org = self.get_object()
        name = org.name
        try:
            delete_organization_and_tenant(org)
        except Exception as exc:
            messages.error(self.request, f"Could not delete organization: {exc}")
            return redirect("dashboard:super_organization_detail", pk=org.pk)
        messages.success(self.request, f"Deleted organization {name} and its tenant schema.")
        return redirect(self.success_url)


class PlatformUserListView(SuperAdminRequiredMixin, ListView):
    template_name = "dashboard/superadmin/user_list.html"
    context_object_name = "user_list"
    paginate_by = 25

    def get_queryset(self):
        qs = User.objects.select_related("organization").order_by("-date_joined")
        self.filter_form = PlatformUserFilterForm(self.request.GET or None)
        if self.filter_form.is_valid():
            q = self.filter_form.cleaned_data.get("q")
            role = self.filter_form.cleaned_data.get("role")
            organization = self.filter_form.cleaned_data.get("organization")
            active = self.filter_form.cleaned_data.get("active")
            if q:
                qs = qs.filter(
                    Q(email__icontains=q)
                    | Q(username__icontains=q)
                    | Q(first_name__icontains=q)
                    | Q(last_name__icontains=q)
                )
            if role:
                qs = qs.filter(role=role)
            if organization:
                qs = qs.filter(organization=organization)
            if active == "1":
                qs = qs.filter(is_active=True)
            elif active == "0":
                qs = qs.filter(is_active=False)
        return qs

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["filter_form"] = getattr(self, "filter_form", PlatformUserFilterForm())
        context["total_all_users"] = User.objects.count()
        paginator = context.get("paginator")
        context["results_count"] = paginator.count if paginator else len(context.get("object_list", []))
        return context


class PlatformUserUpdateView(SuperAdminRequiredMixin, UpdateView):
    model = User
    form_class = PlatformUserManageForm
    template_name = "dashboard/superadmin/user_edit.html"
    context_object_name = "platform_user"

    def get_success_url(self):
        messages.success(self.request, f"Updated user {self.object.display_name}.")
        return reverse("dashboard:super_users")


class PlatformUserDeleteView(SuperAdminRequiredMixin, DeleteView):
    model = User
    template_name = "dashboard/superadmin/user_confirm_delete.html"
    context_object_name = "platform_user"
    success_url = reverse_lazy("dashboard:super_users")

    def dispatch(self, request, *args, **kwargs):
        target = get_object_or_404(User, pk=kwargs["pk"])
        if target.pk == request.user.pk:
            messages.error(request, "You cannot delete your own account.")
            return redirect("dashboard:super_users")
        return super().dispatch(request, *args, **kwargs)

    def delete(self, request, *args, **kwargs):
        user = self.get_object()
        name = user.display_name
        user.delete()
        messages.success(request, f"Deleted user {name}.")
        return redirect(self.success_url)
