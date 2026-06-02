"""Super-admin organization hierarchy views."""

from __future__ import annotations

import csv
import json

from django.contrib import messages
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import TemplateView

from django.db.models import Q

from apps.accounts.hierarchy import org_active_users
from apps.accounts.models import User
from apps.dashboard.mixins import SuperAdminRequiredMixin
from apps.orgchart.analytics import build_global_platform_summary, build_insights, build_summary
from apps.orgchart.page_context import build_org_tree_context
from apps.orgchart.services import (
    OrgTreeFilters,
    build_chart_data,
    employee_detail_payload,
    export_chart_csv,
    get_tree_queryset_for_org,
)
from apps.organizations.models import Organization


class SuperAdminOrgTreeMixin(SuperAdminRequiredMixin):
    """Resolve target organization from query string for super-admin tree APIs."""

    def get_organization(self) -> Organization | None:
        org_id = (self.request.GET.get("org") or "").strip()
        if org_id:
            return get_object_or_404(Organization, pk=org_id)
        return None


class SuperAdminGlobalHierarchyView(SuperAdminRequiredMixin, TemplateView):
    """Landing page: all organizations with workforce stats."""

    template_name = "dashboard/super_org_global.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        orgs = Organization.objects.filter(is_active=True).order_by("name")
        org_rows = []
        for org in orgs:
            users = list(org_active_users(org))
            summary = build_summary(users, org)
            org_rows.append(
                {
                    "organization": org,
                    "summary": summary,
                    "tree_url": reverse("dashboard:super_org_tree") + f"?org={org.pk}",
                }
            )
        context["organizations"] = org_rows
        context["platform_summary"] = build_global_platform_summary()
        return context


class SuperAdminOrgTreeView(SuperAdminOrgTreeMixin, TemplateView):
    template_name = "dashboard/org_tree.html"

    def get(self, request, *args, **kwargs):
        org = self.get_organization()
        if not org:
            messages.info(request, "Select an organization to view its hierarchy.")
            return redirect("dashboard:super_org_global")
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        org = self.get_organization()
        context.update(build_org_tree_context(self.request, organization=org))
        emp_pk = "00000000-0000-0000-0000-000000000000"
        emp_tpl = reverse("dashboard:super_org_tree_api_employee", kwargs={"pk": emp_pk}).replace(
            emp_pk, "__ID__"
        )
        context["api_employee_template"] = emp_tpl
        context["organizations"] = Organization.objects.filter(is_active=True).order_by("name")
        context["tree_base_url"] = reverse("dashboard:super_org_tree")
        org_q = f"org={org.pk}"
        context["api_urls"] = {
            "data": reverse("dashboard:super_org_tree_api_data") + f"?{org_q}",
            "search": reverse("dashboard:super_org_tree_api_search") + f"?{org_q}",
            "export": reverse("dashboard:super_org_tree_export") + f"?{org_q}",
            "employeeTemplate": emp_tpl,
        }
        return context


class SuperAdminOrgTreeDataAPIView(SuperAdminOrgTreeMixin, View):
    def get(self, request):
        org = self.get_organization()
        if not org:
            return JsonResponse({"error": "Organization required."}, status=400)
        filters = OrgTreeFilters.from_request(request)
        users = list(get_tree_queryset_for_org(org, request.user, filters))
        chart = build_chart_data(users, filters.view)
        return JsonResponse(
            {
                "chart": chart,
                "summary": build_summary(users, org),
                "insights": build_insights(users, org),
            }
        )


class SuperAdminOrgTreeSearchAPIView(SuperAdminOrgTreeMixin, View):
    def get(self, request):
        q = (request.GET.get("q") or "").strip()
        org = self.get_organization()
        if not q:
            return JsonResponse({"results": []})
        if org:
            filters = OrgTreeFilters.from_request(request)
            filters.q = q
            users = get_tree_queryset_for_org(org, request.user, filters)[:20]
        else:
            users = (
                User.objects.filter(organization__is_active=True, is_active=True)
                .exclude(role=User.Role.SUPER_ADMIN)
                .filter(
                    Q(first_name__icontains=q)
                    | Q(last_name__icontains=q)
                    | Q(employee_id__icontains=q)
                    | Q(email__icontains=q)
                    | Q(designation__icontains=q)
                )
                .select_related("organization", "department")[:20]
            )
        results = [
            {
                "id": str(u.pk),
                "name": u.display_name,
                "employeeId": u.employee_id or "",
                "department": u.department_name,
                "designation": u.designation or "",
                "organization": u.organization.name if u.organization_id else "",
            }
            for u in users
        ]
        return JsonResponse({"results": results})


class SuperAdminOrgTreeExportView(SuperAdminOrgTreeMixin, View):
    def get(self, request):
        org = self.get_organization()
        if not org:
            return JsonResponse({"error": "Organization required."}, status=400)
        filters = OrgTreeFilters.from_request(request)
        users = list(get_tree_queryset_for_org(org, request.user, filters))
        chart = build_chart_data(users, filters.view)
        rows = export_chart_csv(chart["nodes"])
        response = HttpResponse(content_type="text/csv")
        safe_name = org.name.replace(" ", "-").lower()[:40]
        response["Content-Disposition"] = f'attachment; filename="{safe_name}-org-chart.csv"'
        writer = csv.writer(response)
        writer.writerows(rows)
        return response


class SuperAdminOrgTreeEmployeeAPIView(SuperAdminOrgTreeMixin, View):
    def get(self, request, pk):
        org = self.get_organization()
        employee = get_object_or_404(User, pk=pk, is_active=True)
        if org and employee.organization_id != org.pk:
            return JsonResponse({"error": "Employee not in selected organization."}, status=404)
        return JsonResponse(employee_detail_payload(employee, request.user))
