"""Organization leave approval workflow — configurable approver roles."""

from __future__ import annotations

from apps.accounts.models import User
from apps.organizations.models import Organization

APPROVAL_STEP_ORDER = ("manager", "hr", "admin")

STEP_LABELS = {
    "manager": "Manager approval",
    "hr": "HR approval",
    "admin": "Admin approval",
}

PREVIEW_ROLES = {
    "manager": "Manager",
    "hr": "HR",
    "admin": "Admin",
}


def org_enabled_approval_roles(org: Organization | None) -> list[str]:
    if not org:
        return []
    roles: list[str] = []
    if org.leave_approval_require_manager:
        roles.append("manager")
    if org.leave_approval_require_hr:
        roles.append("hr")
    if org.leave_approval_require_admin:
        roles.append("admin")
    return roles


def resolve_role_approver(user: User, role: str) -> User | None:
    org = user.organization
    if not org:
        return None
    if role == "manager":
        mgr = user.reporting_manager
        if mgr and mgr.is_active:
            return mgr
        return None
    if role == "hr":
        if user.assigned_hr_id and user.assigned_hr.is_active:
            return user.assigned_hr
        return User.objects.filter(organization=org, role=User.Role.HR, is_active=True).order_by("date_joined").first()
    if role == "admin":
        return User.objects.filter(organization=org, role=User.Role.ADMIN, is_active=True).order_by("date_joined").first()
    return None


def build_approval_chain_steps(user: User) -> list[tuple[str, str, User]]:
    """Return ordered (role_key, step_label, approver) tuples; dedupe same person."""
    org = user.organization
    if not org:
        return []

    steps: list[tuple[str, str, User]] = []
    seen_pks = {user.pk}

    for role in APPROVAL_STEP_ORDER:
        if role not in org_enabled_approval_roles(org):
            continue
        approver = resolve_role_approver(user, role)
        if not approver or approver.pk in seen_pks:
            continue
        seen_pks.add(approver.pk)
        steps.append((role, STEP_LABELS[role], approver))

    return steps


def preview_approval_chain(user: User) -> list[dict]:
    steps: list[dict] = [{"role": "Employee", "name": user.display_name, "status": "current"}]
    for role_key, _label, approver in build_approval_chain_steps(user):
        steps.append(
            {
                "role": PREVIEW_ROLES[role_key],
                "name": approver.display_name,
                "status": "pending",
            }
        )
    steps.append({"role": "Approved", "name": "Final", "status": "final"})
    return steps


def user_is_configured_approver(user: User) -> bool:
    org = user.organization
    if not org:
        return False
    roles = org_enabled_approval_roles(org)
    if "admin" in roles and user.role == User.Role.ADMIN:
        return True
    if "hr" in roles and user.role == User.Role.HR:
        return True
    if "manager" in roles and user.direct_reports.filter(is_active=True).exists():
        return True
    return False


def user_can_act_on_leave(user: User, leave_request) -> bool:
    from .models import LeaveApproval

    if leave_request.approvals.filter(approver=user, status=LeaveApproval.StepStatus.PENDING).exists():
        return True
    if user.role in (User.Role.ADMIN, User.Role.HR):
        return leave_request.approvals.filter(status=LeaveApproval.StepStatus.PENDING).exists()
    return False
