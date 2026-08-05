"""Fact / operator / action registries — the extensibility seam of the rule engine.

Adding a new *rule* (a new combination of existing facts/conditions/actions) is
100% data-driven through the Rule Builder UI/API — zero code, zero deploys.
Adding a brand-new *fact* or *action type* means registering a new entry here,
the same way this codebase adds a new notification channel
(``apps/dashboard/notification_service.py``) or a new audit action.
"""

from __future__ import annotations

import dataclasses
from datetime import date, timedelta
from typing import Any, Callable

from django.utils import timezone


@dataclasses.dataclass
class RuleContext:
    """Everything a fact resolver or action handler needs to do its job."""

    organization: Any
    trigger_event: str
    subject: Any = None
    actor: Any = None
    extra: dict = dataclasses.field(default_factory=dict)
    dry_run: bool = False

    @property
    def depth(self) -> int:
        return int(self.extra.get("_depth", 0))


@dataclasses.dataclass
class FactDefinition:
    key: str
    label: str
    value_type: str  # "string" | "number" | "date" | "boolean" | "enum"
    resolver: Callable[[RuleContext], Any]
    choices: tuple = ()


@dataclasses.dataclass
class ActionDefinition:
    key: str
    label: str
    param_schema: dict
    handler: Callable[["RuleContext", dict], dict]


# ---------------------------------------------------------------------------
# Subject helpers
# ---------------------------------------------------------------------------

def employee_of(context: RuleContext):
    """Resolve the employee (User) a fact/action should act on, from any subject."""
    subject = context.subject
    if subject is None:
        return None
    if subject.__class__.__name__ == "User":
        return subject
    return getattr(subject, "user", None)


def leave_request_of(context: RuleContext):
    subject = context.subject
    if subject is not None and subject.__class__.__name__ == "LeaveRequest":
        return subject
    return None


def attendance_record_of(context: RuleContext):
    subject = context.subject
    if subject is not None and subject.__class__.__name__ == "AttendanceRecord":
        return subject
    return None


# ---------------------------------------------------------------------------
# Facts
# ---------------------------------------------------------------------------

def _fact_department(context):
    user = employee_of(context)
    return user.department.name if user and user.department_id else None


def _fact_designation(context):
    user = employee_of(context)
    return user.designation_label if user else None


def _fact_employment_type(context):
    user = employee_of(context)
    return user.employment_type if user else None


def _fact_employment_status(context):
    user = employee_of(context)
    return user.employment_status if user else None


def _fact_role(context):
    user = employee_of(context)
    return user.role if user else None


def _fact_work_mode(context):
    user = employee_of(context)
    return user.work_mode if user else None


def _fact_experience_years(context):
    user = employee_of(context)
    if not user or not user.date_of_joining:
        return None
    delta_days = (date.today() - user.date_of_joining).days
    return round(delta_days / 365.25, 2)


def _make_late_count_resolver(window_days: int):
    def _resolve(context):
        from apps.attendance.models import AttendanceRecord
        from apps.dashboard.attendance_utils import analyze_lateness, get_effective_shift

        user = employee_of(context)
        if not user:
            return None
        since = timezone.localdate() - timedelta(days=window_days)
        shift = get_effective_shift(user)
        count = 0
        for rec in AttendanceRecord.objects.filter(
            user=user, date__gte=since, status=AttendanceRecord.Status.PRESENT
        ):
            if analyze_lateness(rec, shift, rec.date).get("is_late"):
                count += 1
        return count

    return _resolve


def _make_absent_count_resolver(window_days: int):
    def _resolve(context):
        from apps.attendance.models import AttendanceRecord

        user = employee_of(context)
        if not user:
            return None
        since = timezone.localdate() - timedelta(days=window_days)
        return AttendanceRecord.objects.filter(
            user=user, date__gte=since, status=AttendanceRecord.Status.ABSENT
        ).count()

    return _resolve


def _fact_attendance_status_today(context):
    from apps.attendance.models import AttendanceRecord

    user = employee_of(context)
    if not user:
        return None
    rec = AttendanceRecord.objects.filter(user=user, date=timezone.localdate()).first()
    return rec.status if rec else None


def _fact_leave_type(context):
    req = leave_request_of(context)
    return req.leave_type.code if req else None


def _fact_leave_days_requested(context):
    req = leave_request_of(context)
    return float(req.total_days) if req else None


FACTS: dict[str, FactDefinition] = {}


def _register_fact(defn: FactDefinition) -> None:
    FACTS[defn.key] = defn


def _employment_type_choices():
    from apps.accounts.models import User

    return tuple(User.EmploymentType.choices)


def _employment_status_choices():
    from apps.accounts.models import User

    return tuple(User.EmploymentStatus.choices)


def _role_choices():
    from apps.accounts.models import User

    return tuple(User.Role.choices)


def _work_mode_choices():
    from apps.accounts.models import User

    return tuple(User.WorkMode.choices)


_register_fact(FactDefinition("employee.department", "Department", "string", _fact_department))
_register_fact(FactDefinition("employee.designation", "Designation", "string", _fact_designation))
_register_fact(FactDefinition(
    "employee.employment_type", "Employment type", "enum", _fact_employment_type,
    choices=_employment_type_choices(),
))
_register_fact(FactDefinition(
    "employee.employment_status", "Employment status", "enum", _fact_employment_status,
    choices=_employment_status_choices(),
))
_register_fact(FactDefinition("employee.role", "Role", "enum", _fact_role, choices=_role_choices()))
_register_fact(FactDefinition(
    "employee.work_mode", "Work mode", "enum", _fact_work_mode, choices=_work_mode_choices(),
))
_register_fact(FactDefinition("employee.experience_years", "Experience (years)", "number", _fact_experience_years))
_register_fact(FactDefinition(
    "attendance.late_count_30d", "Late count (last 30 days)", "number", _make_late_count_resolver(30),
))
_register_fact(FactDefinition(
    "attendance.late_count_90d", "Late count (last 90 days)", "number", _make_late_count_resolver(90),
))
_register_fact(FactDefinition(
    "attendance.absent_count_30d", "Absent count (last 30 days)", "number", _make_absent_count_resolver(30),
))
_register_fact(FactDefinition(
    "attendance.status_today", "Attendance status today", "enum", _fact_attendance_status_today,
))
_register_fact(FactDefinition("leave.type", "Leave type code", "string", _fact_leave_type))
_register_fact(FactDefinition("leave.days_requested", "Leave days requested", "number", _fact_leave_days_requested))


# ---------------------------------------------------------------------------
# Operators
# ---------------------------------------------------------------------------

def _to_number(value):
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        from decimal import Decimal

        if isinstance(value, Decimal):
            return float(value)
    except Exception:
        pass
    if isinstance(value, date):
        return float(value.toordinal())
    text = str(value).strip()
    try:
        return float(text)
    except ValueError:
        pass
    try:
        return float(date.fromisoformat(text).toordinal())
    except ValueError:
        return None


def _op_equals(value, target, target2=None):
    return str(value).strip().lower() == str(target).strip().lower()


def _op_not_equals(value, target, target2=None):
    return str(value).strip().lower() != str(target).strip().lower()


def _op_greater(value, target, target2=None):
    a, b = _to_number(value), _to_number(target)
    return a is not None and b is not None and a > b


def _op_less(value, target, target2=None):
    a, b = _to_number(value), _to_number(target)
    return a is not None and b is not None and a < b


def _op_contains(value, target, target2=None):
    return str(target).strip().lower() in str(value).strip().lower()


def _op_between(value, target, target2=None):
    a, lo, hi = _to_number(value), _to_number(target), _to_number(target2)
    if a is None or lo is None or hi is None:
        return False
    lo, hi = min(lo, hi), max(lo, hi)
    return lo <= a <= hi


OPERATORS: dict[str, Callable] = {
    "EQUALS": _op_equals,
    "NOT_EQUALS": _op_not_equals,
    "GREATER": _op_greater,
    "LESS": _op_less,
    "CONTAINS": _op_contains,
    "BETWEEN": _op_between,
}

OPERATOR_LABELS = {
    "EQUALS": "Equals",
    "NOT_EQUALS": "Not equals",
    "GREATER": "Greater than",
    "LESS": "Less than",
    "CONTAINS": "Contains",
    "BETWEEN": "Between",
}

# Which operators make sense for each fact value_type.
OPERATORS_BY_TYPE = {
    "string": ("EQUALS", "NOT_EQUALS", "CONTAINS"),
    "enum": ("EQUALS", "NOT_EQUALS"),
    "number": ("EQUALS", "NOT_EQUALS", "GREATER", "LESS", "BETWEEN"),
    "date": ("EQUALS", "NOT_EQUALS", "GREATER", "LESS", "BETWEEN"),
    "boolean": ("EQUALS", "NOT_EQUALS"),
}


# ---------------------------------------------------------------------------
# Actions
# ---------------------------------------------------------------------------

def _resolve_target_user(context: RuleContext, target: str):
    employee = employee_of(context)
    if not employee:
        return None
    if target == "self":
        return employee
    if target == "manager":
        return employee.reporting_manager
    if target == "hr":
        if employee.assigned_hr_id:
            return employee.assigned_hr
        from apps.accounts.models import User

        return (
            User.objects.filter(organization=context.organization, role=User.Role.HR, is_active=True)
            .order_by("date_joined")
            .first()
        )
    if target == "admin":
        from apps.accounts.models import User

        return (
            User.objects.filter(organization=context.organization, role=User.Role.ADMIN, is_active=True)
            .order_by("date_joined")
            .first()
        )
    return None


def _action_add_leave(context: RuleContext, params: dict) -> dict:
    return _adjust_leave_balance(context, params, sign=1)


def _action_deduct_leave(context: RuleContext, params: dict) -> dict:
    return _adjust_leave_balance(context, params, sign=-1)


def _adjust_leave_balance(context: RuleContext, params: dict, *, sign: int) -> dict:
    from decimal import Decimal

    from apps.leaves.models import LeaveType
    from apps.leaves.services import get_balance

    employee = employee_of(context)
    if not employee:
        return {"status": "skipped", "detail": "No employee could be resolved from the subject."}

    leave_type_code = params.get("leave_type_code")
    days = params.get("days")
    if not leave_type_code or days in (None, ""):
        return {"status": "failed", "detail": "leave_type_code and days are required."}

    leave_type = LeaveType.objects.filter(organization=context.organization, code=leave_type_code).first()
    if not leave_type:
        return {"status": "failed", "detail": f"Leave type '{leave_type_code}' not found."}

    amount = Decimal(str(days)) * sign
    bal = get_balance(employee, leave_type)
    bal.adjusted = bal.adjusted + amount
    bal.save(update_fields=["adjusted"])
    return {
        "status": "success",
        "detail": f"{'Added' if sign > 0 else 'Deducted'} {abs(amount)} day(s) of {leave_type.name} "
        f"for {employee.display_name or employee.username} (new adjusted={bal.adjusted}).",
    }


def _action_send_notification(context: RuleContext, params: dict) -> dict:
    from apps.dashboard.notification_service import send_notification

    target_user = _resolve_target_user(context, params.get("target", "self"))
    if not target_user:
        return {"status": "skipped", "detail": "No target user resolved for notification."}

    title = params.get("title") or "Rule notification"
    message = params.get("message") or ""
    send_notification(
        target_user,
        channels=("in_app",),
        source_key=f"rule:{context.extra.get('rule_id')}:{context.extra.get('subject_key')}",
        title=title,
        message=message,
        url=params.get("url", ""),
        icon=params.get("icon", "bell"),
        notification_type="rule",
    )
    return {"status": "success", "detail": f"Notified {target_user.display_name or target_user.username}: {title}"}


def _action_create_approval(context: RuleContext, params: dict) -> dict:
    from .models import RuleApprovalRequest

    employee = employee_of(context)
    if not employee:
        return {"status": "skipped", "detail": "No employee could be resolved from the subject."}

    approver = _resolve_target_user(context, params.get("approver", "manager"))
    subject = context.subject
    approval = RuleApprovalRequest.objects.create(
        organization=context.organization,
        rule_id=context.extra.get("rule_id"),
        subject_type=subject.__class__.__name__ if subject is not None else "",
        subject_id=str(getattr(subject, "pk", "")),
        requested_for=employee,
        approver=approver,
        comment=params.get("comment", ""),
    )
    if approver:
        from apps.dashboard.notification_service import send_notification

        send_notification(
            approver,
            channels=("in_app",),
            source_key=f"rule-approval:{approval.pk}",
            title="Approval requested",
            message=f"A rule needs your approval for {employee.display_name or employee.username}.",
            url="",
            icon="check-circle",
            notification_type="rule",
        )
    return {"status": "success", "detail": f"Approval request created (id={approval.pk})."}


# subject class name -> {field: allowed target values}, used by REJECT_REQUEST / UPDATE_STATUS
# so a rule can only ever set a known-safe field to a known-safe value, never arbitrary attributes.
_STATUS_WHITELIST = {
    "LeaveRequest": {
        "status": ["APPROVED", "REJECTED", "CANCELLED"],
    },
    "User": {
        "employment_status": ["ACTIVE", "INACTIVE", "PROBATION", "NOTICE", "SUSPENDED"],
    },
    "AttendanceRecord": {
        "status": ["PRESENT", "ABSENT", "HALF_DAY", "WFH"],
    },
}


def _action_update_status(context: RuleContext, params: dict) -> dict:
    subject = context.subject
    if subject is None:
        return {"status": "skipped", "detail": "No subject to update."}
    class_name = subject.__class__.__name__
    field = params.get("field", "status")
    value = params.get("value")
    allowed = _STATUS_WHITELIST.get(class_name, {}).get(field)
    if allowed is None:
        return {"status": "failed", "detail": f"Field '{field}' is not whitelisted for {class_name}."}
    if value not in allowed:
        return {"status": "failed", "detail": f"Value '{value}' is not allowed for {class_name}.{field}."}
    setattr(subject, field, value)
    subject.save(update_fields=[field])
    return {"status": "success", "detail": f"{class_name}.{field} set to {value}."}


def _action_reject_request(context: RuleContext, params: dict) -> dict:
    req = leave_request_of(context)
    if req is None:
        return {"status": "skipped", "detail": "REJECT_REQUEST currently only supports leave requests."}
    from apps.leaves.models import LeaveRequest

    req.status = LeaveRequest.Status.REJECTED
    req.review_comment = params.get("comment", "Rejected by rule engine.")
    req.reviewed_at = timezone.now()
    req.save(update_fields=["status", "review_comment", "reviewed_at", "updated_at"])
    return {"status": "success", "detail": "Leave request rejected."}


def _action_assign_shift(context: RuleContext, params: dict) -> dict:
    from apps.attendance.models import WorkShift
    from apps.shifts.models import ShiftAssignment

    employee = employee_of(context)
    if not employee:
        return {"status": "skipped", "detail": "No employee could be resolved from the subject."}

    shift = WorkShift.objects.filter(organization=context.organization, shift_code=params.get("shift_code")).first()
    if not shift:
        return {"status": "failed", "detail": f"Shift '{params.get('shift_code')}' not found."}

    when = params.get("date", "today")
    target_date = timezone.localdate() if when == "today" else timezone.localdate() + timedelta(days=1)
    if when not in ("today", "tomorrow"):
        try:
            target_date = date.fromisoformat(when)
        except ValueError:
            pass

    ShiftAssignment.objects.update_or_create(
        organization=context.organization,
        user=employee,
        date=target_date,
        defaults={"shift": shift, "assigned_by": context.actor},
    )
    return {"status": "success", "detail": f"Assigned {shift.name} to {employee.username} on {target_date}."}


# Extension point for multi-step server-side logic a rule can invoke by name.
# Kept as a whitelisted registry (never free-form code) to stay safely sandboxed.
WORKFLOWS: dict[str, Callable[[RuleContext, dict], dict]] = {}


def _action_execute_workflow(context: RuleContext, params: dict) -> dict:
    key = params.get("workflow_key")
    workflow = WORKFLOWS.get(key)
    if not workflow:
        return {"status": "failed", "detail": f"Workflow '{key}' is not registered."}
    return workflow(context, params)


ACTIONS: dict[str, ActionDefinition] = {}


def _register_action(defn: ActionDefinition) -> None:
    ACTIONS[defn.key] = defn


_register_action(ActionDefinition(
    "ADD_LEAVE", "Add leave",
    {"leave_type_code": "string", "days": "number"},
    _action_add_leave,
))
_register_action(ActionDefinition(
    "DEDUCT_LEAVE", "Deduct leave",
    {"leave_type_code": "string", "days": "number"},
    _action_deduct_leave,
))
_register_action(ActionDefinition(
    "SEND_NOTIFICATION", "Send notification",
    {"target": "enum:self,manager,hr,admin", "title": "string", "message": "string", "url": "string"},
    _action_send_notification,
))
_register_action(ActionDefinition(
    "CREATE_APPROVAL", "Create approval",
    {"approver": "enum:manager,hr,admin", "comment": "string"},
    _action_create_approval,
))
_register_action(ActionDefinition(
    "REJECT_REQUEST", "Reject request",
    {"comment": "string"},
    _action_reject_request,
))
_register_action(ActionDefinition(
    "UPDATE_STATUS", "Update status",
    {"field": "string", "value": "string"},
    _action_update_status,
))
_register_action(ActionDefinition(
    "ASSIGN_SHIFT", "Assign shift",
    {"shift_code": "string", "date": "string"},
    _action_assign_shift,
))
_register_action(ActionDefinition(
    "EXECUTE_WORKFLOW", "Execute workflow",
    {"workflow_key": "string"},
    _action_execute_workflow,
))
