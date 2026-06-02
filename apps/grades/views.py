"""Organization Admin — grades, designations, hierarchy."""

from __future__ import annotations

import json

from django.contrib import messages
from django.db.models import Count
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.dashboard.mixins import AdminRequiredMixin
from apps.grades.forms import CareerPathForm, DesignationForm, GradeForm, GradePermissionForm
from apps.grades.models import CareerPathStep, Designation, Grade, GradePermission, GradeStatus
from apps.grades.services.defaults import seed_organization_grades
from apps.grades.services.hierarchy import (
    build_analytics_context,
    build_grade_tree,
    build_hierarchy_context,
    get_career_path_for_grade,
    hub_context,
)


GRADES_NAV = [
    ("hub", "Overview", "layout-dashboard", "dashboard:grades:hub"),
    ("grades", "Grades", "layers", "dashboard:grades:list"),
    ("designations", "Designations", "badge-check", "dashboard:grades:designations"),
    ("hierarchy", "Hierarchy", "git-branch", "dashboard:grades:hierarchy"),
    ("career", "Career paths", "trending-up", "dashboard:grades:career"),
    ("analytics", "Analytics", "bar-chart-3", "dashboard:grades:analytics"),
]


class GradesContextMixin(AdminRequiredMixin):
    section = "hub"

    def get_grades_nav(self):
        return [
            {
                "id": sid,
                "label": label,
                "icon": icon,
                "url": reverse(url_name),
                "active": sid == self.section,
            }
            for sid, label, icon, url_name in GRADES_NAV
        ]

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.request.user.organization
        ctx["organization"] = org
        ctx["grades_nav"] = self.get_grades_nav()
        ctx["grades_section"] = self.section
        ctx["grades_api"] = reverse("dashboard:grades:api_action")
        from apps.grades.models import GradeCategory

        ctx["grade_category_choices"] = GradeCategory.choices
        return ctx


class GradesHubView(GradesContextMixin, TemplateView):
    template_name = "dashboard/grades/hub.html"
    section = "hub"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.update(hub_context(self.request.user.organization))
        ctx["hr_tree"] = build_grade_tree(self.request.user.organization, "HR")[:3]
        ctx["emp_tree"] = build_grade_tree(self.request.user.organization, "EMPLOYEE")[:3]
        return ctx


class GradeListView(GradesContextMixin, TemplateView):
    template_name = "dashboard/grades/grade_list.html"
    section = "grades"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.request.user.organization
        category = self.request.GET.get("category", "")
        qs = Grade.objects.filter(organization=org).annotate(
            member_count=Count("members")
        ).prefetch_related("departments", "permissions")
        if category:
            qs = qs.filter(category=category)
        ctx["grades"] = qs.order_by("category", "level_number", "priority_order")
        ctx["filter_category"] = category
        ctx["form"] = GradeForm(organization=org)
        edit_id = self.request.GET.get("edit")
        if edit_id:
            grade = get_object_or_404(Grade, pk=edit_id, organization=org)
            ctx["edit_grade"] = grade
            ctx["edit_form"] = GradeForm(instance=grade, organization=org)
            ctx["permission_form"] = GradePermissionForm()
            ctx["grade_permissions"] = grade.permissions.all()
        return ctx

    def post(self, request, *args, **kwargs):
        org = request.user.organization
        action = request.POST.get("action", "create")

        if action == "delete":
            grade = get_object_or_404(Grade, pk=request.POST.get("grade_id"), organization=org)
            User.objects.filter(job_grade=grade).update(job_grade=None)
            name = grade.name
            grade.delete()
            messages.success(request, f"Deleted grade {name}.")
            return redirect("dashboard:grades:list")

        if action == "archive":
            grade = get_object_or_404(Grade, pk=request.POST.get("grade_id"), organization=org)
            grade.status = GradeStatus.ARCHIVED
            grade.save(update_fields=["status", "updated_at"])
            messages.success(request, f"Archived {grade.name}.")
            return redirect("dashboard:grades:list")

        if action == "restore":
            grade = get_object_or_404(Grade, pk=request.POST.get("grade_id"), organization=org)
            grade.status = GradeStatus.ACTIVE
            grade.save(update_fields=["status", "updated_at"])
            messages.success(request, f"Restored {grade.name}.")
            return redirect("dashboard:grades:list")

        if action == "add_permission":
            grade = get_object_or_404(Grade, pk=request.POST.get("grade_id"), organization=org)
            pf = GradePermissionForm(request.POST)
            if pf.is_valid():
                GradePermission.objects.get_or_create(
                    grade=grade, permission_key=pf.cleaned_data["permission_key"]
                )
                messages.success(request, "Permission added.")
            return redirect(f"{reverse('dashboard:grades:list')}?edit={grade.pk}")

        if action == "remove_permission":
            GradePermission.objects.filter(pk=request.POST.get("permission_id"), grade__organization=org).delete()
            gid = request.POST.get("grade_id")
            return redirect(f"{reverse('dashboard:grades:list')}?edit={gid}" if gid else "dashboard:grades:list")

        if action == "edit":
            grade = get_object_or_404(Grade, pk=request.POST.get("grade_id"), organization=org)
            form = GradeForm(request.POST, instance=grade, organization=org)
        else:
            form = GradeForm(request.POST, organization=org)

        if form.is_valid():
            form.save()
            messages.success(request, f"Saved {form.instance.name}.")
            return redirect("dashboard:grades:list")

        messages.error(request, "Please fix the errors below.")
        ctx = self.get_context_data(**kwargs)
        ctx["form"] = form if action != "edit" else GradeForm(organization=org)
        if action == "edit":
            ctx["edit_form"] = form
            ctx["edit_grade"] = get_object_or_404(Grade, pk=request.POST.get("grade_id"), organization=org)
        return self.render_to_response(ctx)


class DesignationListView(GradesContextMixin, TemplateView):
    template_name = "dashboard/grades/designations.html"
    section = "designations"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.request.user.organization
        ctx["designations"] = (
            Designation.objects.filter(organization=org)
            .select_related("grade")
            .annotate(holder_count=Count("holders"))
            .order_by("priority_order", "name")
        )
        ctx["form"] = DesignationForm(organization=org)
        edit_id = self.request.GET.get("edit")
        if edit_id:
            d = get_object_or_404(Designation, pk=edit_id, organization=org)
            ctx["edit_designation"] = d
            ctx["edit_form"] = DesignationForm(instance=d, organization=org)
        return ctx

    def post(self, request, *args, **kwargs):
        org = request.user.organization
        action = request.POST.get("action", "create")

        if action == "delete":
            d = get_object_or_404(Designation, pk=request.POST.get("designation_id"), organization=org)
            User.objects.filter(org_designation=d).update(org_designation=None)
            d.delete()
            messages.success(request, "Designation removed.")
            return redirect("dashboard:grades:designations")

        if action == "edit":
            d = get_object_or_404(Designation, pk=request.POST.get("designation_id"), organization=org)
            form = DesignationForm(request.POST, instance=d, organization=org)
        else:
            form = DesignationForm(request.POST, organization=org)

        if form.is_valid():
            des = form.save()
            User.objects.filter(org_designation=des).update(designation=des.name)
            messages.success(request, f"Saved {des.name}.")
            return redirect("dashboard:grades:designations")

        messages.error(request, "Please fix the errors below.")
        ctx = self.get_context_data(**kwargs)
        ctx["form"] = form
        return self.render_to_response(ctx)


class HierarchyView(GradesContextMixin, TemplateView):
    template_name = "dashboard/grades/hierarchy.html"
    section = "hierarchy"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.request.user.organization
        ctx.update(build_hierarchy_context(org))
        ctx["hierarchy_json"] = json.dumps(build_hierarchy_context(org))
        ctx["staff_mapping"] = (
            User.objects.filter(organization=org)
            .exclude(role=User.Role.SUPER_ADMIN)
            .select_related("job_grade", "org_designation", "department", "reporting_manager")
            .order_by("job_grade__level_number", "first_name")[:50]
        )
        return ctx


class CareerPathView(GradesContextMixin, TemplateView):
    template_name = "dashboard/grades/career.html"
    section = "career"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        org = self.request.user.organization
        ctx["steps"] = CareerPathStep.objects.filter(organization=org).select_related(
            "from_grade", "to_grade"
        )
        ctx["form"] = CareerPathForm(organization=org)
        return ctx

    def post(self, request, *args, **kwargs):
        org = request.user.organization
        if request.POST.get("action") == "delete":
            CareerPathStep.objects.filter(pk=request.POST.get("step_id"), organization=org).delete()
            messages.success(request, "Career path step removed.")
            return redirect("dashboard:grades:career")
        form = CareerPathForm(request.POST, organization=org)
        if form.is_valid():
            step = form.save(commit=False)
            step.organization = org
            step.save()
            messages.success(request, "Career path step saved.")
            return redirect("dashboard:grades:career")
        messages.error(request, "Invalid career path.")
        return redirect("dashboard:grades:career")


class GradesAnalyticsView(GradesContextMixin, TemplateView):
    template_name = "dashboard/grades/analytics.html"
    section = "analytics"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        data = build_analytics_context(self.request.user.organization)
        ctx.update(data)
        ctx["category_chart_json"] = json.dumps(data["category_chart"])
        ctx["employee_chart_json"] = json.dumps(data["employee_chart"])
        return ctx


class GradesActionAPIView(AdminRequiredMixin, View):
    def post(self, request):
        org = request.user.organization
        body = json.loads(request.body.decode() or "{}")
        action = body.get("action")

        if action == "reorder":
            for item in body.get("items", []):
                Grade.objects.filter(pk=item["id"], organization=org).update(
                    priority_order=item.get("order", 0),
                    parent_grade_id=item.get("parentId") or None,
                )
            return JsonResponse({"ok": True})

        if action == "seed_defaults":
            result = seed_organization_grades(org)
            return JsonResponse({"ok": True, **result})

        if action == "assign_user_grade":
            user = get_object_or_404(User, pk=body.get("userId"), organization=org)
            grade = get_object_or_404(Grade, pk=body.get("gradeId"), organization=org)
            user.job_grade = grade
            user.save(update_fields=["job_grade"])
            return JsonResponse({"ok": True})

        if action == "career_path":
            grade = get_object_or_404(Grade, pk=body.get("gradeId"), organization=org)
            return JsonResponse({"ok": True, "path": get_career_path_for_grade(grade)})

        return JsonResponse({"ok": False, "error": "Unknown action"}, status=400)
