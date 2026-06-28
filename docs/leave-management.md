# Leave Management

Tenant-aware leave management: configurable types, balances, single/multi-level
approval, manager team scoping, reports, REST API, notifications, and audit.

## Roles at a glance

| Capability | Org Admin | HR | Manager | Employee |
|---|---|---|---|---|
| Manage leave types (create/edit/activate) | Yes | Yes | No | No |
| Configure approval workflow | Yes | No | No | No |
| Adjust balances | Yes | Yes | No | No |
| View all org leave | Yes | Yes (their staff) | Direct reports only | Own only |
| Approve/reject | Yes | Yes | Direct reports (own step) | No |
| Apply for leave | No (admins approve) | Yes | Yes | Yes |
| Reports / exports (CSV + Excel) | Yes | Yes | Team report | Own history |

## Leave types

Managed by Admin/HR from **Leave management → Organization leave policy**:
name, code (auto-generated if blank), description, days/year, max carry-forward
days, requires supporting document, gender eligibility, applicability
(All / specific departments / specific designations), paid/unpaid, active flag,
color. Deactivated types stay on history but can't be used for new requests.
`LeaveType.is_applicable_to(user)` is the single applicability check used by
the apply form, balance seeding, and submission validation.

## Approval workflow (per organization)

Fixed-order chain built from org toggles (Organization model):

```
Employee → [Manager] → [HR] → [Admin]
```

- `leave_approval_require_manager` / `_hr` / `_admin` — enable each step.
  One enabled step = single-level; two or more = multi-level.
- `leave_auto_approve_without_manager` (default **on**, legacy behavior):
  when the chain resolves no approvers (e.g. employee without a manager and no
  other steps), the request auto-approves. When **off**, such requests route to
  the employee's assigned HR (else any HR, else an admin) instead.

Configured in **Leave management** (admin panel) or **Dashboard → Settings →
Leave approval configuration**, or via the API (below). The pending stage is
shown as e.g. "Pending — Manager approval" (`LeaveRequest.current_stage_label`).

## Balances

Per user × type × year: `allocated + carried_forward + adjusted − used = remaining`.

- Auto-allocated on demand (`ensure_balances_for_user`) and when types change.
- Manual adjustment (±, with reason) by Admin/HR from the policy panel or
  `POST /api/leaves/balances/adjust/` — audited as `BALANCE_ADJUST`.
- Year rollover: `python manage.py rollover_leave_balances [--year Y] [--org CODE]`
  allocates the new year and carries forward `min(remaining, carry_forward_max)`.

## REST API

Session or JWT auth; everything scoped to the caller's organization.

| Endpoint | Who | Purpose |
|---|---|---|
| `GET /api/leaves/balances/` | any member | own balances |
| `GET /api/leaves/my-requests/` | any member | own history |
| `POST /api/leaves/apply/` | HR/Manager/Employee | submit request |
| `POST /api/leaves/{id}/cancel/` | owner (or Admin/HR) | cancel pending/draft |
| `GET /api/leaves/team/` | Manager (reports) / HR / Admin | team requests |
| `POST /api/leaves/{id}/approve/` · `/reject/` | pending-step approver; Admin/HR | decide (+comment) |
| `POST /api/leaves/balances/adjust/` | Admin/HR | adjust balance |
| `GET/POST /api/leave-types/`, `PUT /api/leave-types/{id}/` | Admin/HR | manage types |
| `GET/PUT /api/settings/leave-workflow/` | Admin | approval config |

## Reports & exports

Leave management page: filtered report export as **CSV** (`?export=csv`) or
**Excel** (`?export=xlsx`, openpyxl); Admin/HR also get a balance report
(`?export=balances_csv|balances_xlsx`). The calendar view shows employee, type,
dates, and status for the viewer's scope (own / direct reports / org).

## Notifications & audit

In-app notifications (email-ready via the `send_notification` channel seam):
submitted → first approver; approved/rejected → employee; cancelled → pending
approvers. Audit (`TeamActionAuditLog`): `LEAVE_APPLY`, `LEAVE_APPROVE`,
`LEAVE_REJECT`, `LEAVE_CANCEL`, `BALANCE_ADJUST` with actor, target, request
id, timestamp, and IP.

## Bulk staff import (related)

Admin/HR can bulk-create staff (Employee/HR/Manager) from
**Staff → Import staff**: CSV template download, full pre-validation
(org-scoped uniqueness, department existence, designation catalog matching with
free-text fallback, manager email resolution incl. same-file references, date,
password policy), **abort-on-errors** (default) or **skip-invalid-rows** modes,
import summary with success/error report downloads, and a `StaffAuditLog` BULK
entry per run. Imported users can log in immediately.

## Tests

- `apps/leaves/tests.py` — types, applicability, attachments, balances,
  rollover, workflow config, manager scoping, cancel notifications, full API.
- `apps/dashboard/tests.py` — CSV import service + views.
- `apps/team/tests.py` — manager role regression suite.

```
python manage.py test apps.leaves apps.dashboard apps.team --keepdb
```
