import json

from django.core.paginator import Paginator
from django.http import JsonResponse
from django.shortcuts import redirect
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.models import User

from .attendance_analytics import (
    AnalyticsFilters,
    build_table_rows,
    employee_detail_payload,
    export_rows_csv,
    get_analytics_context,
)
from .mixins import AdminOrHRRequiredMixin


class AttendanceAnalyticsView(AdminOrHRRequiredMixin, TemplateView):
    """Enterprise attendance analytics dashboard."""

    template_name = "dashboard/attendance_analytics.html"
    paginate_by = 25

    def get(self, request, *args, **kwargs):
        export = request.GET.get("export")
        if export in ("csv", "excel"):
            filters = AnalyticsFilters.from_request(request)
            rows = build_table_rows(request.user, filters)
            response = export_rows_csv(rows)
            if export == "excel":
                response["Content-Type"] = "application/vnd.ms-excel; charset=utf-8"
                response["Content-Disposition"] = 'attachment; filename="attendance_report.xls"'
            return response
        return super().get(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        ctx = get_analytics_context(self.request.user, self.request)
        rows = ctx.pop("table_rows")
        paginator = Paginator(rows, self.paginate_by)
        page_num = self.request.GET.get("page") or 1
        page = paginator.get_page(page_num)
        ctx["page_obj"] = page
        ctx["table_rows"] = page.object_list

        query = self.request.GET.copy()
        query.pop("page", None)
        query.pop("export", None)
        ctx["filter_query"] = query.urlencode()
        ctx["filters_get"] = self.request.GET
        ctx["today"] = timezone.localdate()
        ctx["status_choices"] = [
            ("PRESENT", "Present"),
            ("ABSENT", "Absent"),
            ("LEAVE", "Leave"),
            ("HALF_DAY", "Half day"),
            ("WFH", "Work from home"),
        ]
        return ctx


class AttendanceAnalyticsEmployeeView(AdminOrHRRequiredMixin, View):
    """JSON payload for employee detail modal."""

    def get(self, request, pk):
        month = request.GET.get("month")
        year = request.GET.get("year")
        try:
            month_i = int(month) if month else None
            year_i = int(year) if year else None
        except ValueError:
            month_i = year_i = None
        data = employee_detail_payload(request.user, str(pk), month_i, year_i)
        if not data:
            return JsonResponse({"error": "Not found"}, status=404)
        return JsonResponse(data)


class AttendanceReportLegacyRedirectView(AdminOrHRRequiredMixin, View):
    """Redirect old dashboard report URL to new analytics page."""

    def get(self, request):
        q = request.GET.urlencode()
        url = "/attendance/reports/"
        if q:
            url = f"{url}?{q}"
        return redirect(url)
