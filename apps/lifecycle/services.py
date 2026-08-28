"""Onboarding & offboarding business logic."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.accounts.hierarchy import org_active_users
from apps.accounts.models import User
from apps.lifecycle.models import (
    AssetAllocation,
    ClearanceApproval,
    EmployeeDocument,
    ExitInterview,
    GeneratedLetter,
    OffboardingWorkflow,
    OnboardingTask,
    OnboardingWorkflow,
    OrientationSession,
    PolicyAcceptance,
    SettlementRecord,
)
from apps.organizations.models import Organization


DEFAULT_ONBOARDING_TASKS = [
    ("Send welcome email", OnboardingTask.Category.HR, OnboardingTask.Priority.HIGH),
    ("Collect documents", OnboardingTask.Category.HR, OnboardingTask.Priority.HIGH),
    ("Create email account", OnboardingTask.Category.IT, OnboardingTask.Priority.HIGH),
    ("Allocate laptop", OnboardingTask.Category.IT, OnboardingTask.Priority.MEDIUM),
    ("Issue ID card", OnboardingTask.Category.HR, OnboardingTask.Priority.MEDIUM),
    ("Manager introduction", OnboardingTask.Category.MANAGER, OnboardingTask.Priority.MEDIUM),
    ("Security access setup", OnboardingTask.Category.SECURITY, OnboardingTask.Priority.HIGH),
    ("Team orientation", OnboardingTask.Category.TEAM, OnboardingTask.Priority.LOW),
]

DEFAULT_POLICIES = [
    "HR Policies",
    "Security Policies",
    "NDA Agreement",
    "IT Acceptable Use",
    "Attendance Policy",
    "Leave Policy",
]

CLEARANCE_DEPARTMENTS = [
    ClearanceApproval.Department.HR,
    ClearanceApproval.Department.IT,
    ClearanceApproval.Department.FINANCE,
    ClearanceApproval.Department.ADMIN,
    ClearanceApproval.Department.SECURITY,
]

DEFAULT_DOC_TYPES = [
    EmployeeDocument.DocType.AADHAAR,
    EmployeeDocument.DocType.PAN,
    EmployeeDocument.DocType.RESUME,
    EmployeeDocument.DocType.BANK,
    EmployeeDocument.DocType.PHOTO,
]


@dataclass
class LifecycleFilters:
    department: str = ""
    branch: str = ""
    employee_status: str = ""
    joining_from: date | None = None
    joining_to: date | None = None
    exit_from: date | None = None
    exit_to: date | None = None
    workflow_status: str = ""

    @classmethod
    def from_request(cls, request, *, mode: str = "onboarding") -> LifecycleFilters:
        g = request.GET
        today = timezone.localdate()
        jf = g.get("joining_from") or ""
        jt = g.get("joining_to") or ""
        ef = g.get("exit_from") or ""
        et = g.get("exit_to") or ""

        def parse_d(val, default):
            try:
                return date.fromisoformat(val) if val else default
            except ValueError:
                return default

        month_start = today.replace(day=1)

        if mode == "onboarding":
            return cls(
                department=(g.get("department") or "").strip(),
                branch=(g.get("branch") or "").strip(),
                employee_status=(g.get("employee_status") or "").strip(),
                joining_from=parse_d(jf, month_start),
                joining_to=parse_d(jt, today),
                workflow_status=(g.get("workflow_status") or "").strip(),
            )
        return cls(
            department=(g.get("department") or "").strip(),
            branch=(g.get("branch") or "").strip(),
            employee_status=(g.get("employee_status") or "").strip(),
            exit_from=parse_d(ef, month_start),
            exit_to=parse_d(et, today + timedelta(days=90)),
            workflow_status=(g.get("workflow_status") or "").strip(),
        )


def can_manage_lifecycle(user: User) -> bool:
    return user.role in (User.Role.ADMIN, User.Role.HR)


def recalc_onboarding_progress(workflow: OnboardingWorkflow) -> None:
    tasks = list(workflow.tasks.all())
    docs = list(workflow.documents.all())
    policies = list(workflow.policy_acceptances.all())
    total = len(tasks) + len(docs) + len(policies) + 2
    done = sum(1 for t in tasks if t.status == OnboardingTask.Status.DONE)
    done += sum(1 for d in docs if d.verify_status == EmployeeDocument.VerifyStatus.VERIFIED)
    done += sum(1 for p in policies if p.accepted)
    if workflow.welcome_sent:
        done += 1
    orient_done = workflow.orientation_sessions.filter(completed=True).exists()
    if orient_done:
        done += 1
    pct = int((done / max(total, 1)) * 100)
    workflow.progress_percent = min(pct, 100)
    if pct >= 100 and workflow.status != OnboardingWorkflow.Status.COMPLETED:
        workflow.status = OnboardingWorkflow.Status.COMPLETED
        workflow.completed_at = timezone.now()
    workflow.save(update_fields=["progress_percent", "status", "completed_at"])


def recalc_offboarding_progress(workflow: OffboardingWorkflow) -> None:
    clearances = list(workflow.clearances.all())
    total = len(clearances) + 3
    done = sum(1 for c in clearances if c.status == ClearanceApproval.Status.APPROVED)
    if hasattr(workflow, "exit_interview") and workflow.exit_interview.feedback:
        done += 1
    assets = workflow.asset_returns.filter(status=AssetAllocation.Status.RETURNED).count()
    pending_assets = workflow.asset_returns.exclude(status=AssetAllocation.Status.RETURNED).count()
    if pending_assets == 0 and workflow.asset_returns.exists():
        done += 1
    if hasattr(workflow, "settlement") and workflow.settlement.status in (
        SettlementRecord.Status.APPROVED,
        SettlementRecord.Status.PAID,
    ):
        done += 1
    pct = int((done / max(total, 1)) * 100)
    workflow.progress_percent = min(pct, 100)
    if all(c.status == ClearanceApproval.Status.APPROVED for c in clearances) and pct >= 90:
        workflow.status = OffboardingWorkflow.Status.COMPLETED
        workflow.completed_at = timezone.now()
    workflow.save(update_fields=["progress_percent", "status", "completed_at"])


@transaction.atomic
def start_onboarding(
    *,
    organization: Organization,
    user: User,
    joining_date: date,
    created_by: User,
    branch: str = "",
) -> OnboardingWorkflow:
    workflow, created = OnboardingWorkflow.objects.get_or_create(
        organization=organization,
        user=user,
        defaults={
            "joining_date": joining_date,
            "branch": branch or user.work_location or "",
            "created_by": created_by,
            "status": OnboardingWorkflow.Status.IN_PROGRESS,
        },
    )
    if created:
        for doc_type in DEFAULT_DOC_TYPES:
            EmployeeDocument.objects.get_or_create(
                onboarding=workflow, doc_type=doc_type, defaults={"verify_status": EmployeeDocument.VerifyStatus.MISSING}
            )
        for title, cat, pri in DEFAULT_ONBOARDING_TASKS:
            OnboardingTask.objects.get_or_create(
                onboarding=workflow,
                title=title,
                defaults={
                    "category": cat,
                    "priority": pri,
                    "due_date": joining_date + timedelta(days=7),
                },
            )
        for policy in DEFAULT_POLICIES:
            PolicyAcceptance.objects.get_or_create(onboarding=workflow, policy_name=policy)
        OrientationSession.objects.create(
            onboarding=workflow,
            title="Company orientation",
            scheduled_at=timezone.now() + timedelta(days=2),
        )
    return workflow


@transaction.atomic
def start_offboarding(
    *,
    organization: Organization,
    user: User,
    last_working_day: date,
    reason: str,
    created_by: User,
    notes: str = "",
) -> OffboardingWorkflow:
    workflow = OffboardingWorkflow.objects.create(
        organization=organization,
        user=user,
        last_working_day=last_working_day,
        resignation_reason=reason,
        notes=notes,
        created_by=created_by,
        status=OffboardingWorkflow.Status.REQUESTED,
    )
    for dept in CLEARANCE_DEPARTMENTS:
        ClearanceApproval.objects.create(offboarding=workflow, department=dept)
    ExitInterview.objects.create(offboarding=workflow)
    SettlementRecord.objects.create(offboarding=workflow)
    for asset in AssetAllocation.objects.filter(user=user, status=AssetAllocation.Status.ALLOCATED):
        asset.offboarding = workflow
        asset.save(update_fields=["offboarding"])
    return workflow


def generate_letter(
    offboarding: OffboardingWorkflow,
    letter_type: str,
    generated_by: User,
) -> GeneratedLetter:
    user = offboarding.user
    org = offboarding.organization
    if letter_type == GeneratedLetter.LetterType.EXPERIENCE:
        content = f"""
EXPERIENCE CERTIFICATE

This is to certify that {user.display_name} (Employee ID: {user.employee_id or 'N/A'})
was employed with {org.name} in the capacity of {user.designation or user.get_role_display()}.

Date of joining: {user.date_of_joining or 'As per records'}
Last working day: {offboarding.last_working_day}

During their tenure, they performed their duties satisfactorily. We wish them success in future endeavors.

For {org.name}
HR Department
{timezone.localdate()}
"""
    else:
        content = f"""
RELIEVING LETTER

Date: {timezone.localdate()}

To Whom It May Concern,

This is to confirm that {user.display_name} has been relieved from their services at {org.name}
effective {offboarding.last_working_day}, following completion of exit formalities.

Employee ID: {user.employee_id or 'N/A'}
Department: {user.department_name or 'N/A'}

We thank them for their contributions to the organization.

Authorized Signatory
{org.name}
"""
    return GeneratedLetter.objects.create(
        offboarding=offboarding,
        letter_type=letter_type,
        content=content.strip(),
        generated_by=generated_by,
    )


def compute_settlement(offboarding: OffboardingWorkflow) -> SettlementRecord:
    settlement, _ = SettlementRecord.objects.get_or_create(offboarding=offboarding)
    user = offboarding.user
    base = Decimal("45000") if user.role == User.Role.EMPLOYEE else Decimal("65000")
    settlement.pending_salary = base
    settlement.leave_encashment = Decimal("5000")
    settlement.bonus = Decimal("0")
    settlement.deductions = Decimal("2000")
    settlement.reimbursements = Decimal("1500")
    settlement.total_payable = (
        settlement.pending_salary
        + settlement.leave_encashment
        + settlement.bonus
        + settlement.reimbursements
        - settlement.deductions
    )
    settlement.save()
    return settlement


def avg_onboarding_days(org: Organization) -> float:
    completed = OnboardingWorkflow.objects.filter(
        organization=org, status=OnboardingWorkflow.Status.COMPLETED, completed_at__isnull=False
    )
    if not completed.exists():
        return 0
    total = 0
    count = 0
    for w in completed:
        if w.completed_at:
            days = (w.completed_at.date() - w.joining_date).days
            total += max(days, 0)
            count += 1
    return round(total / max(count, 1), 1)
