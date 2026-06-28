"""Team-management pages for users who lead a team.

Access rules:
- Team-management pages use ``TeamLeadRequiredMixin`` (user has active direct
  reports).

Every query is scoped to the viewer's direct reports within their own
organization; a team lead can never see employees outside their hierarchy or
across tenants. Mutating actions are recorded in the team audit log.
"""

from __future__ import annotations

import csv
from datetime import datetime

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.utils import timezone
from django.views import View
from django.views.generic import TemplateView

from apps.accounts.hierarchy import correction_requests_for_reviewer, direct_reports_for
from apps.attendance.models import AttendanceRecord, AttendanceRegularizationRequest
from apps.attendance.services import (
    approve_regularization,
    build_employee_attendance_stats,
    period_bounds,
    reject_regularization,
)
from apps.dashboard.mixins import (
    OrganizationRequiredMixin,
    TeamLeadRequiredMixin,
)
from apps.leaves.models import LeaveRequest
from apps.leaves.services import (
    approve_leave,
    manager_pending_leave_requests,
    manager_team_leave_requests,
    reject_leave,
)
from apps.team.audit import record_team_action
from apps.team.models import TeamActionAuditLog

_PRESENT_STATUSES = (
    AttendanceRecord.Status.PRESENT,
    AttendanceRecord.Status.WFH,
    AttendanceRecord.Status.HALF_DAY,
)


def _resolve_month(request):
    """Return (anchor_date, start, end, label) for the requested ?month=YYYY-MM."""
    raw = request.GET.get("month") or ""
    today = timezone.localdate()
    try:
        anchor = datetime.strptime(raw, "%Y-%m").date()
    except ValueError:
        anchor = today.replace(day=1)
    start, end = period_bounds(anchor, "month")
    return anchor, start, end, anchor.strftime("%B %Y")


# ── Notifications (shared, all org roles) ─────────────────────────────────────


class NotificationsPageView(OrganizationRequiredMixin, TemplateView):
    """Full-page list of the current user's notifications."""

    template_name = "dashboard/notifications.html"

    def get_context_data(self, **kwargs):
        from apps.dashboard.notification_service import get_user_notifications

        context = super().get_context_data(**kwargs)
        context["notifications"] = get_user_notifications(self.request.user)
        return context


# ── Team directory (#7) ───────────────────────────────────────────────────────


class TeamDirectoryView(TeamLeadRequiredMixin, TemplateView):
    template_name = "dashboard/team_members.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        team = direct_reports_for(self.request.user).select_related(
            "department", "work_shift", "job_grade"
        )
        context["team"] = team
        context["team_count"] = team.count()
        return context


# ── Team attendance (#6) ──────────────────────────────────────────────────────


class TeamAttendancePageView(TeamLeadRequiredMixin, TemplateView):
    """Read-only team attendance. Managers cannot edit attendance directly."""

    template_name = "dashboard/team_attendance.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        manager = self.request.user
        anchor, start, end, label = _resolve_month(self.request)
        today = timezone.localdate()

        team = list(direct_reports_for(manager).select_related("department"))
        present_today_ids = set(
            AttendanceRecord.objects.filter(
                user__in=team, date=today, status__in=_PRESENT_STATUSES
            ).values_list("user_id", flat=True)
        )
        today_status = dict(
            AttendanceRecord.objects.filter(user__in=team, date=today).values_list(
                "user_id", "status"
            )
        )

        rows = []
        for member in team:
            rows.append(
                {
                    "user": member,
                    "stats": build_employee_attendance_stats(member, start, end),
                    "present_today": member.pk in present_today_ids,
                    "today_status": today_status.get(member.pk, ""),
                }
            )

        context.update(
            {
                "rows": rows,
                "team_count": len(team),
                "month_anchor": anchor,
                "month_start": start,
                "month_end": end,
                "month_label": label,
                "today": today,
                "export_url": reverse("dashboard:team_attendance_export")
                + f"?month={anchor:%Y-%m}",
            }
        )
        return context


class TeamAttendanceExportView(TeamLeadRequiredMixin, View):
    """CSV export of the team's monthly attendance summary (#6)."""

    def get(self, request, *args, **kwargs):
        manager = request.user
        anchor, start, end, label = _resolve_month(request)
        team = direct_reports_for(manager).select_related("department")

        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            f'attachment; filename="team-attendance-{anchor:%Y-%m}.csv"'
        )
        writer = csv.writer(response)
        writer.writerow(
            [
                "Employee ID",
                "Name",
                "Department",
                "Present",
                "Absent",
                "Leave",
                "WFH",
                "Half day",
                "Late",
                "Working days",
                "Attendance %",
            ]
        )
        for member in team:
            s = build_employee_attendance_stats(member, start, end)
            writer.writerow(
                [
                    member.employee_id or "",
                    member.display_name,
                    member.department_name,
                    s["present"],
                    s["absent"],
                    s["leave"],
                    s["wfh"],
                    s["half_day"],
                    s["late"],
                    s["total_days"],
                    s["attendance_rate"],
                ]
            )
        return response


# ── Leave approvals (#5) ──────────────────────────────────────────────────────


class TeamLeaveApprovalsView(TeamLeadRequiredMixin, TemplateView):
    template_name = "dashboard/team_leave_approvals.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        manager = self.request.user
        context["pending_requests"] = manager_pending_leave_requests(manager)
        context["recent_requests"] = manager_team_leave_requests(manager).exclude(
            status=LeaveRequest.Status.PENDING
        )[:20]
        return context


class TeamLeaveDecisionView(TeamLeadRequiredMixin, View):
    """Approve / reject one direct report's leave request (#5)."""

    def post(self, request, pk, decision, *args, **kwargs):
        manager = request.user
        if decision not in ("approve", "reject"):
            messages.error(request, "Invalid action.")
            return redirect("dashboard:team_leave_approvals")

        # Authorization: only pending requests from this manager's reports that
        # are awaiting THIS manager's approval step are actionable.
        leave_request = get_object_or_404(manager_pending_leave_requests(manager), pk=pk)
        comment = (request.POST.get("comment") or "").strip()
        employee = leave_request.user

        if decision == "approve":
            msg = approve_leave(leave_request, manager, comment)
            record_team_action(
                actor=manager,
                action=TeamActionAuditLog.Action.LEAVE_APPROVE,
                target=employee,
                object_id=leave_request.pk,
                summary=f"Approved leave for {employee.display_name}",
                request=request,
                comment=comment,
                leave_type=leave_request.leave_type.code,
            )
        else:
            msg = reject_leave(leave_request, manager, comment)
            record_team_action(
                actor=manager,
                action=TeamActionAuditLog.Action.LEAVE_REJECT,
                target=employee,
                object_id=leave_request.pk,
                summary=f"Rejected leave for {employee.display_name}",
                request=request,
                comment=comment,
                leave_type=leave_request.leave_type.code,
            )
        messages.success(request, msg)
        return redirect("dashboard:team_leave_approvals")


# ── Attendance regularizations (#6) ───────────────────────────────────────────


class TeamRegularizationsView(TeamLeadRequiredMixin, TemplateView):
    template_name = "dashboard/team_regularizations.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        manager = self.request.user
        qs = correction_requests_for_reviewer(manager)
        context["pending_requests"] = qs.filter(
            status=AttendanceRegularizationRequest.Status.PENDING
        ).order_by("-created_at")
        context["recent_requests"] = qs.exclude(
            status=AttendanceRegularizationRequest.Status.PENDING
        ).order_by("-reviewed_at")[:20]
        return context


class TeamRegularizationDecisionView(TeamLeadRequiredMixin, View):
    """Approve / reject one direct report's attendance regularization (#6)."""

    def post(self, request, pk, decision, *args, **kwargs):
        manager = request.user
        if decision not in ("approve", "reject"):
            messages.error(request, "Invalid action.")
            return redirect("dashboard:team_regularizations")

        # Authorization: only pending requests from this manager's reports.
        pending = correction_requests_for_reviewer(manager).filter(
            status=AttendanceRegularizationRequest.Status.PENDING
        )
        req = get_object_or_404(pending, pk=pk)
        comment = (request.POST.get("comment") or "").strip()
        employee = req.user

        if decision == "approve":
            approve_regularization(manager, req, comment)
            record_team_action(
                actor=manager,
                action=TeamActionAuditLog.Action.REGULARIZATION_APPROVE,
                target=employee,
                object_id=req.pk,
                summary=f"Approved attendance regularization for {employee.display_name}",
                request=request,
                comment=comment,
                date=str(req.date),
            )
            messages.success(request, f"Approved correction for {employee.display_name}.")
        else:
            reject_regularization(manager, req, comment)
            record_team_action(
                actor=manager,
                action=TeamActionAuditLog.Action.REGULARIZATION_REJECT,
                target=employee,
                object_id=req.pk,
                summary=f"Rejected attendance regularization for {employee.display_name}",
                request=request,
                comment=comment,
                date=str(req.date),
            )
            messages.success(request, f"Rejected correction for {employee.display_name}.")
        return redirect("dashboard:team_regularizations")
