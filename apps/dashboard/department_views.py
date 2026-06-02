from django.contrib import messages
from django.db.models import Count
from django.shortcuts import get_object_or_404, redirect
from django.views.generic import TemplateView

from apps.accounts.models import User
from apps.organizations.models import Department

from .department_forms import DepartmentForm
from .mixins import AdminRequiredMixin


class DepartmentManageView(AdminRequiredMixin, TemplateView):
    template_name = "dashboard/departments.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        org = self.request.user.organization
        context["organization"] = org
        context["dept_label"] = org.department_label
        context["dept_label_plural"] = org.department_label_plural
        dept_qs = (
            Department.objects.filter(organization=org)
            .annotate(member_count=Count("members"))
            .order_by("sort_order", "name")
        )
        context["departments"] = dept_qs
        context["staff_assigned_count"] = User.objects.filter(
            organization=org, department__isnull=False
        ).count()
        context["form"] = DepartmentForm(organization=org)
        edit_id = self.request.GET.get("edit")
        if edit_id:
            dept = get_object_or_404(Department, pk=edit_id, organization=org)
            context["edit_department"] = dept
            context["edit_form"] = DepartmentForm(instance=dept, organization=org)
        return context

    def post(self, request, *args, **kwargs):
        org = request.user.organization
        action = request.POST.get("action", "create")

        if action == "delete":
            dept = get_object_or_404(Department, pk=request.POST.get("department_id"), organization=org)
            name = dept.name
            User.objects.filter(department=dept).update(department=None)
            dept.delete()
            messages.success(request, f"Removed {name}. Staff assignments were cleared.")
            return redirect("dashboard:departments")

        if action == "edit":
            dept = get_object_or_404(Department, pk=request.POST.get("department_id"), organization=org)
            form = DepartmentForm(request.POST, instance=dept, organization=org)
        else:
            form = DepartmentForm(request.POST, organization=org)

        if form.is_valid():
            dept = form.save()
            messages.success(request, f"Saved {dept.name}.")
            return redirect("dashboard:departments")

        messages.error(request, "Please fix the errors below.")
        context = self.get_context_data(**kwargs)
        context["form"] = form if action != "edit" else DepartmentForm(organization=org)
        if action == "edit":
            context["edit_form"] = form
            context["edit_department"] = get_object_or_404(
                Department, pk=request.POST.get("department_id"), organization=org
            )
        return self.render_to_response(context)
