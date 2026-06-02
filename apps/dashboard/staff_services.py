"""Staff management services — permissions, bulk ops, export, analytics."""

from __future__ import annotations

import csv
import io
import secrets
import string
from datetime import timedelta

from django.db.models import Count, Q, QuerySet
from django.utils import timezone

from apps.accounts.models import StaffAuditLog, User
from apps.accounts.role_labels import role_display_for
from apps.attendance.models import AttendanceRecord
from apps.grades.models import Designation, Grade
from apps.leaves.models import LeaveRequest
from apps.organizations.models import Department, Organization


def can_manage_staff(actor: User, target: User) -> bool:
    if not actor.organization_id or actor.organization_id != target.organization_id:
        return False
    if actor.role == User.Role.ADMIN:
        return target.role != User.Role.SUPER_ADMIN and target.pk != actor.pk
    if actor.role == User.Role.HR:
        return target.role == User.Role.EMPLOYEE and target.assigned_hr_id == actor.pk
    return False


def staff_queryset_for(actor: User) -> QuerySet[User]:
    from apps.dashboard.staff_filters import staff_list_base_queryset

    return staff_list_base_queryset(actor).select_related(
        "department",
        "reporting_manager",
        "assigned_hr",
        "work_shift",
        "job_grade",
        "org_designation",
    )


def staff_detail_url_for(actor: User, target: User) -> str | None:
    """Staff detail URL when target is visible in the actor's staff module."""
    if staff_queryset_for(actor).filter(pk=target.pk).exists():
        from django.urls import reverse

        return reverse("dashboard:staff_detail", kwargs={"pk": target.pk})
    return None


def user_notification_url(viewer: User, target: User) -> str:
    """Resolve a notification link that the viewer is allowed to open."""
    from django.urls import reverse

    if viewer.role == User.Role.SUPER_ADMIN:
        return reverse("dashboard:super_user_edit", kwargs={"pk": target.pk})
    staff_url = staff_detail_url_for(viewer, target)
    if staff_url:
        return staff_url
    if viewer.pk == target.pk:
        return reverse("accounts:profile")
    return reverse("dashboard:staff_list")


def log_staff_action(
    *,
    organization: Organization,
    actor: User,
    target: User | None,
    action: str,
    summary: str,
    details: dict | None = None,
) -> None:
    StaffAuditLog.objects.create(
        organization=organization,
        actor=actor,
        target_user=target,
        action=action,
        summary=summary,
        details=details or {},
    )


def get_staff_kpis(org: Organization, base_qs: QuerySet[User]) -> dict:
    today = timezone.localdate()
    month_start = today.replace(day=1)
    return {
        "total": base_qs.count(),
        "active": base_qs.filter(is_active=True, employment_status=User.EmploymentStatus.ACTIVE).count(),
        "hr_count": base_qs.filter(role=User.Role.HR).count(),
        "employee_count": base_qs.filter(role=User.Role.EMPLOYEE).count(),
        "departments": Department.objects.filter(organization=org, is_active=True).count(),
        "recent_joins": base_qs.filter(date_of_joining__gte=month_start).count(),
        "on_leave": LeaveRequest.objects.filter(
            user__in=base_qs,
            status=LeaveRequest.Status.APPROVED,
            start_date__lte=today,
            end_date__gte=today,
        ).count(),
    }


def get_staff_profile_context(staff: User) -> dict:
    today = timezone.localdate()
    month_start = today.replace(day=1)
    attendance = AttendanceRecord.objects.filter(user=staff, date__gte=month_start)
    present = attendance.filter(status=AttendanceRecord.Status.PRESENT).count()
    leaves = LeaveRequest.objects.filter(user=staff).order_by("-created_at")[:8]
    direct_reports = User.objects.filter(reporting_manager=staff, is_active=True).count()
    audit = StaffAuditLog.objects.filter(target_user=staff).select_related("actor")[:12]
    return {
        "attendance_month": {
            "present": present,
            "total_days": attendance.count(),
        },
        "recent_leaves": leaves,
        "direct_reports_count": direct_reports,
        "audit_logs": audit,
        "role_label": role_display_for(staff.role),
    }


def get_reporting_chain(staff: User, *, limit: int = 6) -> list[User]:
    """Walk up reporting_manager chain for hierarchy preview."""
    chain: list[User] = []
    current = staff.reporting_manager
    seen: set = set()
    while current and len(chain) < limit and current.pk not in seen:
        seen.add(current.pk)
        chain.append(current)
        current = current.reporting_manager
    return list(reversed(chain))


def get_staff_create_context(organization: Organization, creator: User) -> dict:
    """Context for the new-employee workspace."""
    admin = (
        User.objects.filter(organization=organization, role=User.Role.ADMIN, is_active=True)
        .order_by("date_joined")
        .first()
    )
    return {
        "org_admin_name": admin.display_name if admin else organization.name,
        "creator_name": creator.display_name,
    }


def get_staff_edit_context(staff: User) -> dict:
    """Extended context for the employee edit workspace."""
    from apps.leaves.models import LeaveBalance

    today = timezone.localdate()
    month_start = today.replace(day=1)
    attendance_qs = AttendanceRecord.objects.filter(user=staff, date__gte=month_start)
    total_marked = attendance_qs.count()
    present = attendance_qs.filter(status=AttendanceRecord.Status.PRESENT).count()
    attendance_pct = round((present / total_marked) * 100) if total_marked else 0

    leave_balances = LeaveBalance.objects.filter(user=staff).select_related("leave_type")[:6]
    leave_balance_total = sum(float(lb.remaining) for lb in leave_balances)

    audit_logs = StaffAuditLog.objects.filter(target_user=staff).select_related("actor")[:15]
    reporting_chain = get_reporting_chain(staff)

    employment_timeline = []
    if staff.date_of_joining:
        employment_timeline.append(
            {"date": staff.date_of_joining, "label": "Joined organization", "icon": "calendar"}
        )
    if staff.archived_at:
        employment_timeline.append(
            {"date": staff.archived_at.date(), "label": "Archived", "icon": "archive"}
        )

    return {
        **get_staff_profile_context(staff),
        "reporting_chain": reporting_chain,
        "attendance_pct": attendance_pct,
        "leave_balances": leave_balances,
        "leave_balance_total": leave_balance_total,
        "last_login": staff.last_login,
        "employment_timeline": employment_timeline,
    }


def export_staff_csv(staff_qs: QuerySet[User]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "Employee ID",
            "First Name",
            "Last Name",
            "Username",
            "Email",
            "Phone",
            "Role",
            "Grade",
            "Department",
            "Designation",
            "Manager",
            "Joining Date",
            "Employment Status",
            "Active",
        ]
    )
    for u in staff_qs:
        writer.writerow(
            [
                u.employee_id,
                u.first_name,
                u.last_name,
                u.username,
                u.email,
                u.phone,
                role_display_for(u.role),
                u.grade_name,
                u.department_name,
                u.designation_label,
                u.reporting_manager.display_name if u.reporting_manager else "",
                u.date_of_joining.isoformat() if u.date_of_joining else "",
                u.get_employment_status_display(),
                "Yes" if u.is_active else "No",
            ]
        )
    return buf.getvalue()


def _random_password(length: int = 12) -> str:
    alphabet = string.ascii_letters + string.digits + "!@#$%"
    return "".join(secrets.choice(alphabet) for _ in range(length))


def bulk_action(
    *,
    actor: User,
    action: str,
    user_ids: list,
    payload: dict | None = None,
) -> dict:
    org = actor.organization
    qs = staff_queryset_for(actor).filter(pk__in=user_ids)
    payload = payload or {}
    affected = 0
    temp_password = None

    if action == "deactivate":
        for u in qs:
            if not can_manage_staff(actor, u):
                continue
            u.is_active = False
            u.employment_status = User.EmploymentStatus.INACTIVE
            u.save(update_fields=["is_active", "employment_status"])
            log_staff_action(
                organization=org,
                actor=actor,
                target=u,
                action=StaffAuditLog.Action.DEACTIVATE,
                summary=f"Deactivated {u.display_name}",
            )
            affected += 1

    elif action == "activate":
        for u in qs:
            if not can_manage_staff(actor, u):
                continue
            u.is_active = True
            u.employment_status = User.EmploymentStatus.ACTIVE
            u.archived_at = None
            u.save(update_fields=["is_active", "employment_status", "archived_at"])
            log_staff_action(
                organization=org,
                actor=actor,
                target=u,
                action=StaffAuditLog.Action.ACTIVATE,
                summary=f"Activated {u.display_name}",
            )
            affected += 1

    elif action == "archive":
        now = timezone.now()
        for u in qs:
            if not can_manage_staff(actor, u):
                continue
            u.is_active = False
            u.employment_status = User.EmploymentStatus.ARCHIVED
            u.archived_at = now
            u.save(update_fields=["is_active", "employment_status", "archived_at"])
            log_staff_action(
                organization=org,
                actor=actor,
                target=u,
                action=StaffAuditLog.Action.DEACTIVATE,
                summary=f"Archived {u.display_name}",
            )
            affected += 1

    elif action == "delete":
        for u in qs:
            if not can_manage_staff(actor, u):
                continue
            name = u.display_name
            u.is_active = False
            u.employment_status = User.EmploymentStatus.TERMINATED
            u.archived_at = timezone.now()
            u.save(update_fields=["is_active", "employment_status", "archived_at"])
            log_staff_action(
                organization=org,
                actor=actor,
                target=u,
                action=StaffAuditLog.Action.DELETE,
                summary=f"Terminated {name}",
            )
            affected += 1

    elif action == "assign_department":
        dept = Department.objects.filter(pk=payload.get("departmentId"), organization=org).first()
        if dept:
            for u in qs:
                if can_manage_staff(actor, u):
                    u.department = dept
                    u.save(update_fields=["department"])
                    affected += 1

    elif action == "assign_manager":
        mgr = User.objects.filter(pk=payload.get("managerId"), organization=org).first()
        if mgr:
            for u in qs:
                if can_manage_staff(actor, u) and u.pk != mgr.pk:
                    u.reporting_manager = mgr
                    u.save(update_fields=["reporting_manager"])
                    affected += 1

    elif action == "assign_grade":
        grade = Grade.objects.filter(pk=payload.get("gradeId"), organization=org).first()
        if grade:
            for u in qs:
                if can_manage_staff(actor, u):
                    u.job_grade = grade
                    u.save(update_fields=["job_grade"])
                    affected += 1

    elif action == "change_status":
        status = payload.get("status")
        if status in User.EmploymentStatus.values:
            for u in qs:
                if not can_manage_staff(actor, u):
                    continue
                u.employment_status = status
                u.is_active = status in (
                    User.EmploymentStatus.ACTIVE,
                    User.EmploymentStatus.PROBATION,
                    User.EmploymentStatus.NOTICE,
                )
                u.save(update_fields=["employment_status", "is_active"])
                affected += 1

    elif action == "reset_password":
        temp_password = _random_password()
        for u in qs:
            if can_manage_staff(actor, u):
                u.set_password(temp_password)
                u.save(update_fields=["password"])
                log_staff_action(
                    organization=org,
                    actor=actor,
                    target=u,
                    action=StaffAuditLog.Action.PASSWORD_RESET,
                    summary=f"Password reset for {u.display_name}",
                )
                affected += 1

    if affected and action not in ("reset_password",):
        log_staff_action(
            organization=org,
            actor=actor,
            target=None,
            action=StaffAuditLog.Action.BULK,
            summary=f"Bulk {action}: {affected} staff",
            details={"action": action, "count": affected},
        )

    return {"affected": affected, "tempPassword": temp_password}
