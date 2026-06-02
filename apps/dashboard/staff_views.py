"""Staff management views — list, detail, edit, delete, bulk API, export."""

from __future__ import annotations

import json

from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import DetailView, FormView, ListView, TemplateView

from apps.accounts.models import User
from apps.accounts.role_labels import role_display_for
from apps.attendance.models import WorkShift
from apps.dashboard.mixins import AdminOrHRRequiredMixin
from apps.dashboard.staff_filters import (
    apply_staff_list_filters,
    staff_filter_options,
    staff_list_base_queryset,
)
from apps.dashboard.staff_forms import StaffEditForm
from apps.dashboard.staff_services import (
    bulk_action,
    can_manage_staff,
    export_staff_csv,
    get_staff_edit_context,
    get_staff_kpis,
    get_staff_profile_context,
    log_staff_action,
    staff_queryset_for,
)
from apps.accounts.models import StaffAuditLog
from apps.grades.models import Designation, Grade, GradeStatus
from apps.organizations.models import Department


class StaffListView(AdminOrHRRequiredMixin, ListView):
    template_name = "dashboard/staff_list.html"
    context_object_name = "staff"
    paginate_by = 25

    def get_queryset(self):
        user = self.request.user
        is_hr_view = user.role == User.Role.HR
        qs = staff_list_base_queryset(user).select_related(
            "reporting_manager",
            "assigned_hr",
            "work_shift",
            "department",
            "job_grade",
            "org_designation",
        )
        qs = apply_staff_list_filters(qs, self.request.GET, is_hr_view=is_hr_view)
        return qs.order_by("role", "first_name", "last_name", "username")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        is_hr_view = user.role == User.Role.HR
        org = user.organization
        context["organization"] = org
        context["is_hr_view"] = is_hr_view
        context["can_create"] = user.role in (User.Role.ADMIN, User.Role.HR)
        context["is_org_admin"] = user.role == User.Role.ADMIN
        get = self.request.GET
        context["filters"] = get
        context["has_active_filters"] = any(
            get.get(k)
            for k in ("q", "role", "department", "shift", "hr", "grade", "designation", "manager", "employment_status")
        ) or (get.get("status") not in (None, "", "active"))
        query = get.copy()
        query.pop("page", None)
        context["filter_query"] = query.urlencode()
        base_qs = staff_list_base_queryset(user)
        context["kpis"] = get_staff_kpis(org, base_qs)
        context["default_shift"] = WorkShift.objects.filter(organization=org, is_default=True).first()
        opts = staff_filter_options(org, is_hr_view)
        context.update({f"filter_{k}": v for k, v in opts.items() if k.startswith(("dept", "role", "hr", "shift")) or k in ("departments", "shifts", "hr_users", "role_choices", "grades", "designations", "managers", "employment_statuses")})
        context["filter_departments"] = opts["departments"]
        context["filter_shifts"] = opts["shifts"]
        context["filter_hr_users"] = opts["hr_users"]
        context["filter_role_choices"] = opts["role_choices"]
        context["filter_grades"] = opts.get("grades", [])
        context["filter_designations"] = opts.get("designations", [])
        context["filter_managers"] = opts.get("managers", [])
        context["dept_label"] = opts["dept_label"]
        context["dept_label_plural"] = opts["dept_label_plural"]
        context["employment_status_choices"] = User.EmploymentStatus.choices
        context["staff_api"] = reverse("dashboard:staff_api_bulk")
        context["role_display_for"] = role_display_for
        paginator = context.get("paginator")
        context["result_count"] = paginator.count if paginator else 0
        page_staff = context.get("staff") or []
        context["manageable_ids"] = {
            str(u.pk) for u in page_staff if can_manage_staff(user, u)
        }
        return context


class StaffDetailView(AdminOrHRRequiredMixin, DetailView):
    model = User
    template_name = "dashboard/staff_detail.html"
    context_object_name = "staff_member"
    pk_url_kwarg = "pk"

    def dispatch(self, request, *args, **kwargs):
        pk = kwargs.get(self.pk_url_kwarg)
        if pk and request.user.is_authenticated:
            allowed = staff_queryset_for(request.user).filter(pk=pk).exists()
            if not allowed:
                target = User.objects.filter(
                    pk=pk,
                    organization_id=request.user.organization_id,
                ).first()
                if target:
                    messages.info(
                        request,
                        "This profile is not available in staff management.",
                    )
                    return redirect("dashboard:staff_list")
        return super().dispatch(request, *args, **kwargs)

    def get_queryset(self):
        return staff_queryset_for(self.request.user)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        staff = self.object
        ctx.update(get_staff_profile_context(staff))
        ctx["can_edit"] = can_manage_staff(self.request.user, staff)
        ctx["role_label"] = role_display_for(staff.role)
        return ctx


class StaffUpdateView(AdminOrHRRequiredMixin, FormView):
    template_name = "dashboard/staff_edit.html"
    form_class = StaffEditForm

    def dispatch(self, request, *args, **kwargs):
        self.staff_member = get_object_or_404(staff_queryset_for(request.user), pk=kwargs["pk"])
        if not can_manage_staff(request.user, self.staff_member):
            messages.error(request, "You cannot edit this team member.")
            return redirect("dashboard:staff_list")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        kw = super().get_form_kwargs()
        kw["instance"] = self.staff_member
        kw["organization"] = self.request.user.organization
        kw["editor"] = self.request.user
        return kw

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        staff = self.staff_member
        ctx["staff_member"] = staff
        ctx["role_label"] = role_display_for(staff.role)
        org = self.request.user.organization
        if org:
            ctx["dept_label"] = org.department_label
            ctx["dept_label_plural"] = org.department_label_plural
        ctx.update(get_staff_edit_context(staff))
        ctx["delete_url"] = reverse("dashboard:staff_delete", kwargs={"pk": staff.pk})
        ctx["detail_url"] = reverse("dashboard:staff_detail", kwargs={"pk": staff.pk})
        return ctx

    def form_valid(self, form):
        user = form.save()
        log_staff_action(
            organization=self.request.user.organization,
            actor=self.request.user,
            target=user,
            action=StaffAuditLog.Action.UPDATE,
            summary=f"Updated profile for {user.display_name}",
        )
        messages.success(self.request, f"Saved changes for {user.display_name}.")
        return redirect("dashboard:staff_detail", pk=user.pk)

    def form_invalid(self, form):
        messages.error(self.request, "Please fix the errors below.")
        return super().form_invalid(form)


class StaffDeleteView(AdminOrHRRequiredMixin, TemplateView):
    template_name = "dashboard/staff_confirm_delete.html"

    def dispatch(self, request, *args, **kwargs):
        self.staff_member = get_object_or_404(staff_queryset_for(request.user), pk=kwargs["pk"])
        if not can_manage_staff(request.user, self.staff_member):
            messages.error(request, "You cannot remove this team member.")
            return redirect("dashboard:staff_list")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["staff_member"] = self.staff_member
        ctx["role_label"] = role_display_for(self.staff_member.role)
        return ctx

    def post(self, request, *args, **kwargs):
        action = request.POST.get("action", "deactivate")
        staff = self.staff_member
        org = request.user.organization
        name = staff.display_name

        if action == "permanent":
            staff.delete()
            log_staff_action(
                organization=org,
                actor=request.user,
                target=None,
                action=StaffAuditLog.Action.DELETE,
                summary=f"Permanently deleted {name}",
            )
            messages.success(request, f"Permanently removed {name}.")
        elif action == "archive":
            from django.utils import timezone

            staff.is_active = False
            staff.employment_status = User.EmploymentStatus.ARCHIVED
            staff.archived_at = timezone.now()
            staff.save(update_fields=["is_active", "employment_status", "archived_at"])
            log_staff_action(
                organization=org,
                actor=request.user,
                target=staff,
                action=StaffAuditLog.Action.DEACTIVATE,
                summary=f"Archived {name}",
            )
            messages.success(request, f"Archived {name}.")
        else:
            staff.is_active = False
            staff.employment_status = User.EmploymentStatus.INACTIVE
            staff.save(update_fields=["is_active", "employment_status"])
            log_staff_action(
                organization=org,
                actor=request.user,
                target=staff,
                action=StaffAuditLog.Action.DEACTIVATE,
                summary=f"Deactivated {name}",
            )
            messages.success(request, f"Deactivated {name}.")

        return redirect("dashboard:staff_list")


class StaffExportView(AdminOrHRRequiredMixin, View):
    def get(self, request):
        ids = request.GET.getlist("ids")
        qs = staff_queryset_for(request.user)
        if ids:
            qs = qs.filter(pk__in=ids)
        else:
            qs = apply_staff_list_filters(qs, request.GET, is_hr_view=request.user.role == User.Role.HR)
        csv_data = export_staff_csv(qs.order_by("first_name"))
        response = HttpResponse(csv_data, content_type="text/csv")
        response["Content-Disposition"] = 'attachment; filename="staff_export.csv"'
        return response


class StaffBulkAPIView(AdminOrHRRequiredMixin, View):
    def post(self, request):
        try:
            body = json.loads(request.body.decode() or "{}")
        except json.JSONDecodeError:
            return JsonResponse({"ok": False, "error": "Invalid JSON"}, status=400)
        result = bulk_action(
            actor=request.user,
            action=body.get("action", ""),
            user_ids=body.get("userIds", []),
            payload=body.get("payload", {}),
        )
        return JsonResponse({"ok": True, **result})
