"""Views for bulk staff import via CSV (Admin/HR only)."""

from __future__ import annotations

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from apps.dashboard.mixins import AdminOrHRRequiredMixin
from apps.dashboard.staff_import import (
    MODE_ABORT,
    MODE_SKIP,
    STAFF_IMPORT_COLUMNS,
    build_template_csv,
    import_rows,
    parse_csv,
)

_SESSION_ERROR_KEY = "staff_import_error_csv"
_SESSION_SUCCESS_KEY = "staff_import_success_csv"
_MAX_REPORT_CHARS = 500_000  # cap session storage
_MAX_UPLOAD_BYTES = 2 * 1024 * 1024  # 2 MB ≈ thousands of rows
_MAX_ROWS = 1000


class StaffImportTemplateView(AdminOrHRRequiredMixin, View):
    """Download the CSV template with header + sample rows."""

    def get(self, request, *args, **kwargs):
        resp = HttpResponse(
            build_template_csv(request.user.organization), content_type="text/csv; charset=utf-8"
        )
        resp["Content-Disposition"] = 'attachment; filename="staff_import_template.csv"'
        return resp


class StaffImportReportView(AdminOrHRRequiredMixin, View):
    """Download the success/error report from the last import in this session."""

    def get(self, request, *args, **kwargs):
        kind = request.GET.get("kind", "error")
        key = _SESSION_SUCCESS_KEY if kind == "success" else _SESSION_ERROR_KEY
        content = request.session.get(key)
        if not content:
            messages.info(request, "No import report available. Run an import first.")
            return redirect("dashboard:staff_import")
        resp = HttpResponse(content, content_type="text/csv; charset=utf-8")
        resp["Content-Disposition"] = f'attachment; filename="staff_import_{kind}_report.csv"'
        return resp


class StaffImportView(AdminOrHRRequiredMixin, TemplateView):
    template_name = "dashboard/staff_import.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(
            {
                "columns": STAFF_IMPORT_COLUMNS,
                "summary": kwargs.get("summary"),
                "file_errors": kwargs.get("file_errors") or [],
                "selected_mode": kwargs.get("selected_mode", MODE_ABORT),
            }
        )
        return context

    def post(self, request, *args, **kwargs):
        mode = request.POST.get("mode") or MODE_ABORT
        if mode not in (MODE_ABORT, MODE_SKIP):
            mode = MODE_ABORT

        upload = request.FILES.get("csv_file")
        if not upload:
            messages.error(request, "Choose a CSV file to import.")
            return self.render_to_response(self.get_context_data(selected_mode=mode))
        if upload.size > _MAX_UPLOAD_BYTES:
            messages.error(request, "File too large (max 2 MB).")
            return self.render_to_response(self.get_context_data(selected_mode=mode))

        rows, file_errors = parse_csv(upload)
        if file_errors:
            return self.render_to_response(
                self.get_context_data(file_errors=file_errors, selected_mode=mode)
            )
        if len(rows) > _MAX_ROWS:
            return self.render_to_response(
                self.get_context_data(
                    file_errors=[f"Too many rows ({len(rows)}). Max {_MAX_ROWS} per import."],
                    selected_mode=mode,
                )
            )

        summary = import_rows(
            request.user.organization,
            request.user,
            rows,
            mode=mode,
            filename=upload.name,
        )

        request.session[_SESSION_ERROR_KEY] = summary.error_report_csv()[:_MAX_REPORT_CHARS]
        request.session[_SESSION_SUCCESS_KEY] = summary.success_report_csv()[:_MAX_REPORT_CHARS]

        if summary.aborted:
            messages.error(
                request,
                f"Import aborted: {summary.failed} row(s) failed validation. "
                "Fix the errors below or switch to 'Skip invalid rows'.",
            )
        elif summary.failed:
            messages.warning(
                request,
                f"Imported {summary.imported} of {summary.total} rows; "
                f"{summary.failed} failed (see error report).",
            )
        else:
            messages.success(request, f"Successfully imported {summary.imported} staff member(s).")

        return self.render_to_response(
            self.get_context_data(summary=summary, selected_mode=mode)
        )
