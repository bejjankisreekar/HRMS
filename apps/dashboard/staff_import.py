"""Bulk staff import via CSV.

Validates every row up front, then imports in one of two modes:

- ``abort``  (default): nothing is imported unless every row is valid.
- ``skip``: valid rows are imported, invalid rows are reported and skipped.

All lookups (departments, designations, reporting managers, uniqueness) are
scoped to the importing user's organization, so imports respect tenant
isolation. Passwords are hashed via ``User.objects.create_user``.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass, field
from datetime import date, datetime

from django.db import transaction
from django.utils.text import slugify

from apps.accounts.models import StaffAuditLog, User
from apps.accounts.role_labels import role_display_for
from apps.dashboard.staff_services import log_staff_action
from apps.grades.models import Designation, GradeStatus
from apps.leaves.services import ensure_balances_for_user
from apps.organizations.models import Department, Organization

STAFF_IMPORT_COLUMNS = [
    "employee_id",
    "first_name",
    "last_name",
    "email",
    "phone_number",
    "role",
    "department",
    "designation",
    "reporting_manager_email",
    "date_of_joining",
    "employment_type",
    "password",
    "is_active",
]

_SAMPLE_ROWS = [
    [
        "EMP001", "John", "Doe", "john@example.com", "9876543210", "HR",
        "Human Resources", "HR Manager", "", "2026-06-01", "FULL_TIME",
        "Password@123", "TRUE",
    ],
    [
        "EMP002", "Sarah", "Smith", "sarah@example.com", "9876543211", "EMPLOYEE",
        "Engineering", "Team Lead", "", "2026-06-01", "FULL_TIME",
        "Password@123", "TRUE",
    ],
    [
        "EMP003", "Rahul", "Kumar", "rahul@example.com", "9876543212", "EMPLOYEE",
        "Engineering", "Software Engineer", "sarah@example.com", "2026-06-01",
        "FULL_TIME", "Password@123", "TRUE",
    ],
]

ALLOWED_ROLES = {
    "EMPLOYEE": User.Role.EMPLOYEE,
    "HR": User.Role.HR,
}


def _resolve_role(raw: str, org: Organization | None) -> str | None:
    """Map a CSV role token to a stored role value, or None if unrecognized.

    Accepts canonical tokens (HR/EMPLOYEE), the legacy MANAGER value (mapped to
    HR for backward compatibility), and the org's configured HR label as an alias.
    """
    token = (raw or "").strip().upper()
    if token in ALLOWED_ROLES:
        return ALLOWED_ROLES[token]
    if token == "MANAGER":  # legacy CSVs from before the Manager role was removed
        return User.Role.HR
    if org and token == (org.hr_label or "").strip().upper():
        return User.Role.HR
    return None

ALLOWED_EMPLOYMENT_TYPES = {c for c, _ in User.EmploymentType.choices}

MODE_ABORT = "abort"
MODE_SKIP = "skip"

REQUIRED_FIELDS = (
    "employee_id",
    "first_name",
    "email",
    "role",
    "department",
    "designation",
    "date_of_joining",
    "employment_type",
    "password",
)


def build_template_csv(org: Organization | None = None) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(STAFF_IMPORT_COLUMNS)
    hr_label = org.hr_label if org else "HR"
    role_idx = STAFF_IMPORT_COLUMNS.index("role")
    for row in _SAMPLE_ROWS:
        row = list(row)
        if (row[role_idx] or "").upper() == "HR":
            row[role_idx] = hr_label
        w.writerow(row)
    return buf.getvalue()


def _password_errors(password: str) -> list[str]:
    errs = []
    if len(password) < 8:
        errs.append("Password must be at least 8 characters.")
    if not re.search(r"[A-Z]", password):
        errs.append("Password needs an uppercase letter.")
    if not re.search(r"[a-z]", password):
        errs.append("Password needs a lowercase letter.")
    if not re.search(r"\d", password):
        errs.append("Password needs a number.")
    return errs


@dataclass
class RowResult:
    line: int  # 1-based data row number (header excluded)
    data: dict
    errors: list[str] = field(default_factory=list)
    created_user: User | None = None
    skipped: bool = False

    @property
    def valid(self) -> bool:
        return not self.errors


@dataclass
class ImportSummary:
    mode: str = MODE_ABORT
    filename: str = ""
    aborted: bool = False
    rows: list[RowResult] = field(default_factory=list)

    @property
    def total(self) -> int:
        return len(self.rows)

    @property
    def imported(self) -> int:
        return sum(1 for r in self.rows if r.created_user is not None)

    @property
    def failed(self) -> int:
        return sum(1 for r in self.rows if r.errors)

    @property
    def skipped(self) -> int:
        return sum(1 for r in self.rows if r.skipped and not r.created_user)

    def error_report_csv(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(STAFF_IMPORT_COLUMNS + ["errors"])
        for r in self.rows:
            if r.errors:
                w.writerow([r.data.get(c, "") for c in STAFF_IMPORT_COLUMNS] + ["; ".join(r.errors)])
        return buf.getvalue()

    def success_report_csv(self) -> str:
        buf = io.StringIO()
        w = csv.writer(buf, lineterminator="\n")
        w.writerow(["employee_id", "name", "email", "role", "status"])
        for r in self.rows:
            if r.created_user:
                u = r.created_user
                role_label = role_display_for(u.role, u.organization)
                w.writerow([u.employee_id, u.display_name, u.email, role_label, "Imported"])
        return buf.getvalue()


def parse_csv(file_obj) -> tuple[list[dict], list[str]]:
    """Decode an uploaded file into row dicts. Returns (rows, file_errors)."""
    try:
        raw = file_obj.read()
        if isinstance(raw, bytes):
            text = raw.decode("utf-8-sig")
        else:
            text = raw
    except UnicodeDecodeError:
        return [], ["File is not valid UTF-8 text. Save the CSV as UTF-8 and retry."]

    reader = csv.DictReader(io.StringIO(text))
    if not reader.fieldnames:
        return [], ["The file is empty."]
    headers = [h.strip().lower() for h in reader.fieldnames]
    missing = [c for c in STAFF_IMPORT_COLUMNS if c not in headers]
    if missing:
        return [], [
            "Missing required column(s): " + ", ".join(missing)
            + ". Download the template for the expected format."
        ]

    rows = []
    for raw_row in reader:
        row = {
            (k or "").strip().lower(): (v or "").strip()
            for k, v in raw_row.items()
            if k is not None
        }
        if any(row.get(c) for c in STAFF_IMPORT_COLUMNS):  # skip fully blank lines
            rows.append(row)
    if not rows:
        return [], ["No data rows found in the file."]
    return rows, []


def validate_rows(org: Organization, rows: list[dict]) -> list[RowResult]:
    """Validate all rows against the org. Does not write anything."""
    departments = {
        d.name.strip().lower(): d
        for d in Department.objects.filter(organization=org, is_active=True)
    }
    designations = {
        d.name.strip().lower(): d
        for d in Designation.objects.filter(organization=org, status=GradeStatus.ACTIVE)
    }
    existing_emp_ids = {
        e.lower()
        for e in User.objects.filter(organization=org)
        .exclude(employee_id="")
        .values_list("employee_id", flat=True)
    }
    existing_emails = {e.lower() for e in User.objects.values_list("email", flat=True)}
    org_member_emails = {
        e.lower()
        for e in User.objects.filter(organization=org, is_active=True).values_list(
            "email", flat=True
        )
    }

    seen_emp_ids: set[str] = set()
    seen_emails: set[str] = set()
    results: list[RowResult] = []

    for i, row in enumerate(rows, start=1):
        result = RowResult(line=i, data=row)
        errs = result.errors

        for f in REQUIRED_FIELDS:
            if not row.get(f):
                errs.append(f"Missing required field: {f}.")

        emp_id = (row.get("employee_id") or "").upper()
        email = (row.get("email") or "").lower()
        row["employee_id"] = emp_id
        row["email"] = email

        if emp_id:
            if emp_id.lower() in existing_emp_ids:
                errs.append(f"Employee ID {emp_id} already exists in your organization.")
            if emp_id.lower() in seen_emp_ids:
                errs.append(f"Duplicate Employee ID {emp_id} within the file.")
            seen_emp_ids.add(emp_id.lower())

        if email:
            if "@" not in email or "." not in email.split("@")[-1]:
                errs.append("Invalid email address.")
            if email in existing_emails:
                errs.append(f"Email {email} is already registered.")
            if email in seen_emails:
                errs.append(f"Duplicate email {email} within the file.")
            seen_emails.add(email)

        resolved_role = _resolve_role(row.get("role"), org)
        if row.get("role") and resolved_role is None:
            errs.append(
                f"Invalid role '{row.get('role')}'. Allowed: EMPLOYEE, HR, {org.hr_label}."
            )
        row["_role"] = resolved_role

        dept_raw = (row.get("department") or "").lower()
        if dept_raw and dept_raw not in departments:
            errs.append(f"Department '{row.get('department')}' does not exist.")

        # Designation: matched against the catalog when possible, otherwise
        # accepted as free text (catalog is optional per org).
        desig_raw = (row.get("designation") or "").lower()
        row["_designation_obj"] = designations.get(desig_raw)

        mgr_email = (row.get("reporting_manager_email") or "").lower()
        row["reporting_manager_email"] = mgr_email
        if mgr_email:
            if mgr_email == email:
                errs.append("An employee cannot report to themselves.")
            elif mgr_email not in org_member_emails and mgr_email not in seen_emails:
                errs.append(
                    f"Reporting manager '{mgr_email}' not found in your organization "
                    "(or earlier in this file)."
                )

        doj_raw = row.get("date_of_joining") or ""
        if doj_raw:
            try:
                row["_date_of_joining"] = datetime.strptime(doj_raw, "%Y-%m-%d").date()
            except ValueError:
                errs.append(f"Invalid date_of_joining '{doj_raw}'. Use YYYY-MM-DD.")

        emp_type = (row.get("employment_type") or "").upper()
        if emp_type and emp_type not in ALLOWED_EMPLOYMENT_TYPES:
            errs.append(
                f"Invalid employment_type '{row.get('employment_type')}'. "
                "Allowed: FULL_TIME, PART_TIME, INTERN, CONTRACT."
            )

        password = row.get("password") or ""
        if password:
            errs.extend(_password_errors(password))

        is_active_raw = (row.get("is_active") or "").upper()
        if is_active_raw not in ("", "TRUE", "FALSE"):
            errs.append("is_active must be TRUE or FALSE (or empty for TRUE).")

        results.append(result)

    return results


def _unique_username(email: str, taken: set[str]) -> str:
    base = slugify(email.split("@")[0])[:42] or "user"
    candidate = base
    n = 1
    while candidate.lower() in taken or User.objects.filter(username__iexact=candidate).exists():
        candidate = f"{base}-{n}"
        n += 1
    taken.add(candidate.lower())
    return candidate


def _default_assigned_hr(org: Organization, actor: User) -> User | None:
    if actor.role == User.Role.HR:
        return actor
    return (
        User.objects.filter(organization=org, role=User.Role.HR, is_active=True)
        .order_by("date_joined")
        .first()
    )


def _create_user_from_row(org: Organization, actor: User, row: dict, taken_usernames: set[str]) -> User:
    role = row.get("_role") or _resolve_role(row.get("role"), org)
    departments = Department.objects.filter(
        organization=org, is_active=True, name__iexact=row["department"]
    )
    designation_obj = row.get("_designation_obj")
    user = User.objects.create_user(
        email=row["email"],
        password=row["password"],
        username=_unique_username(row["email"], taken_usernames),
        first_name=row.get("first_name", ""),
        last_name=row.get("last_name", ""),
        phone=row.get("phone_number", ""),
        role=role,
        organization=org,
        employee_id=row["employee_id"],
        department=departments.first(),
        designation=designation_obj.name if designation_obj else (row.get("designation") or ""),
        org_designation=designation_obj,
        date_of_joining=row.get("_date_of_joining"),
        employment_type=(row.get("employment_type") or "").upper(),
        is_active=(row.get("is_active") or "TRUE").upper() != "FALSE",
        assigned_hr=_default_assigned_hr(org, actor) if role != User.Role.HR else None,
    )
    ensure_balances_for_user(user)
    return user


def _link_managers(org: Organization, results: list[RowResult]) -> None:
    """Second pass: resolve reporting managers (existing users or same-file)."""
    created_by_email = {
        r.created_user.email.lower(): r.created_user for r in results if r.created_user
    }
    for r in results:
        if not r.created_user:
            continue
        mgr_email = r.data.get("reporting_manager_email") or ""
        if not mgr_email:
            continue
        manager = created_by_email.get(mgr_email) or User.objects.filter(
            organization=org, email__iexact=mgr_email, is_active=True
        ).first()
        if manager and manager.pk != r.created_user.pk:
            r.created_user.reporting_manager = manager
            r.created_user.save(update_fields=["reporting_manager"])


def import_rows(
    org: Organization,
    actor: User,
    rows: list[dict],
    mode: str = MODE_ABORT,
    filename: str = "",
) -> ImportSummary:
    """Validate then import. Abort mode imports nothing if any row fails."""
    results = validate_rows(org, rows)
    summary = ImportSummary(mode=mode, filename=filename, rows=results)

    if mode == MODE_ABORT and any(r.errors for r in results):
        summary.aborted = True
        for r in results:
            if not r.errors:
                r.skipped = True
        _log_import(org, actor, summary)
        return summary

    taken_usernames: set[str] = set()
    to_create = [r for r in results if not r.errors]

    if mode == MODE_ABORT:
        try:
            with transaction.atomic():
                for r in to_create:
                    r.created_user = _create_user_from_row(org, actor, r.data, taken_usernames)
                _link_managers(org, results)
        except Exception as exc:  # e.g. uniqueness race — nothing was imported
            summary.aborted = True
            for r in to_create:
                r.created_user = None
                if not r.errors:
                    r.errors.append(f"Import aborted by a database error: {exc}")
    else:
        for r in to_create:
            try:
                with transaction.atomic():
                    r.created_user = _create_user_from_row(org, actor, r.data, taken_usernames)
            except Exception as exc:  # row-level safety net (e.g. race on uniqueness)
                r.errors.append(f"Could not create user: {exc}")
        _link_managers(org, results)

    _log_import(org, actor, summary)
    return summary


def _log_import(org: Organization, actor: User, summary: ImportSummary) -> None:
    log_staff_action(
        organization=org,
        actor=actor,
        target=None,
        action=StaffAuditLog.Action.BULK,
        summary=(
            f"Bulk staff import ({summary.filename or 'upload.csv'}): "
            f"{summary.imported} imported, {summary.failed} failed"
            + (", aborted" if summary.aborted else "")
        ),
        details={
            "filename": summary.filename,
            "mode": summary.mode,
            "total_rows": summary.total,
            "imported": summary.imported,
            "failed": summary.failed,
            "skipped": summary.skipped,
            "aborted": summary.aborted,
        },
    )
