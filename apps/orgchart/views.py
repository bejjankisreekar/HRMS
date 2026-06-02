import csv

import json



from django.contrib import messages

from django.http import HttpResponse, JsonResponse

from django.shortcuts import get_object_or_404

from django.urls import reverse

from django.views import View

from django.views.generic import TemplateView



from apps.accounts.hierarchy import org_active_users

from apps.accounts.models import User

from apps.dashboard.mixins import AdminOrHRRequiredMixin, OrganizationRequiredMixin

from apps.orgchart.analytics import build_insights, build_summary

from apps.orgchart.forms import TeamForm

from apps.orgchart.page_context import build_org_tree_context

from apps.orgchart.services import (

    OrgTreeFilters,

    build_chart_data,

    can_edit_hierarchy,

    employee_detail_payload,

    export_chart_csv,

    get_tree_queryset,

    update_reporting_manager,

    validate_manager_change,

)





class OrgTreeView(OrganizationRequiredMixin, TemplateView):

    template_name = "dashboard/org_tree.html"



    def get_context_data(self, **kwargs):

        context = super().get_context_data(**kwargs)

        context.update(build_org_tree_context(self.request))

        context["api_urls"] = self._api_urls()

        return context



    def _api_urls(self) -> dict:
        emp_tpl = reverse(
            "dashboard:orgchart:api_employee",
            kwargs={"pk": "00000000-0000-0000-0000-000000000000"},
        ).replace("00000000-0000-0000-0000-000000000000", "__ID__")
        return {
            "data": reverse("dashboard:orgchart:api_data"),
            "move": reverse("dashboard:orgchart:api_move"),
            "search": reverse("dashboard:orgchart:api_search"),
            "export": reverse("dashboard:orgchart:export"),
            "team": reverse("dashboard:orgchart:api_team"),
            "employeeTemplate": emp_tpl,
        }





class OrgTreeDataAPIView(OrganizationRequiredMixin, View):

    """JSON tree for live refresh / filters."""



    def get(self, request):

        filters = OrgTreeFilters.from_request(request)

        users = list(get_tree_queryset(request.user, filters))

        chart = build_chart_data(users, filters.view)

        return JsonResponse(

            {

                "chart": chart,

                "summary": build_summary(users, request.user.organization),

                "insights": build_insights(users, request.user.organization),

            }

        )





class OrgTreeEmployeeAPIView(OrganizationRequiredMixin, View):

    def get(self, request, pk):

        employee = get_object_or_404(

            get_tree_queryset(request.user, OrgTreeFilters()),

            pk=pk,

        )

        return JsonResponse(employee_detail_payload(employee, request.user))





class OrgTreeMoveAPIView(OrganizationRequiredMixin, View):

    def post(self, request):

        if not can_edit_hierarchy(request.user):

            return JsonResponse({"ok": False, "error": "Permission denied."}, status=403)



        try:

            body = json.loads(request.body.decode() or "{}")

        except json.JSONDecodeError:

            return JsonResponse({"ok": False, "error": "Invalid JSON."}, status=400)



        employee_id = body.get("employeeId")

        manager_id = body.get("managerId") or None



        employee = get_object_or_404(

            org_active_users(request.user.organization),

            pk=employee_id,

        )

        new_manager = None

        if manager_id:

            new_manager = get_object_or_404(

                org_active_users(request.user.organization),

                pk=manager_id,

            )



        err = validate_manager_change(employee, new_manager, request.user.organization)

        if err:

            return JsonResponse({"ok": False, "error": err}, status=400)



        update_reporting_manager(

            employee=employee,

            new_manager=new_manager,

            changed_by=request.user,

            note=body.get("note", ""),

        )

        return JsonResponse({"ok": True, "message": "Reporting line updated."})





class OrgTreeSearchAPIView(OrganizationRequiredMixin, View):

    def get(self, request):

        q = (request.GET.get("q") or "").strip()

        if not q:

            return JsonResponse({"results": []})

        filters = OrgTreeFilters.from_request(request)

        filters.q = q

        users = get_tree_queryset(request.user, filters)[:20]

        results = [

            {

                "id": str(u.pk),

                "name": u.display_name,

                "employeeId": u.employee_id or "",

                "department": u.department_name,

                "designation": u.designation or "",

            }

            for u in users

        ]

        return JsonResponse({"results": results})





class OrgTreeExportView(OrganizationRequiredMixin, View):

    def get(self, request):

        filters = OrgTreeFilters.from_request(request)

        users = list(get_tree_queryset(request.user, filters))

        chart = build_chart_data(users, filters.view)

        rows = export_chart_csv(chart["nodes"])

        response = HttpResponse(content_type="text/csv")

        response["Content-Disposition"] = 'attachment; filename="organization-chart.csv"'

        writer = csv.writer(response)

        writer.writerows(rows)

        return response





class OrgTreeTeamCreateView(AdminOrHRRequiredMixin, View):

    def post(self, request):

        form = TeamForm(request.POST, organization=request.user.organization)

        if form.is_valid():

            team = form.save(commit=False)

            team.organization = request.user.organization

            team.save()

            messages.success(request, f"Team “{team.name}” created.")

        else:

            messages.error(request, "Could not create team. Check the form.")

        return JsonResponse({"ok": form.is_valid(), "errors": form.errors if not form.is_valid else {}})

