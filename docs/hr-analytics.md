# HR Analytics

People-intelligence workspace for Organization Admins and HR at
`/dashboard/hr-analytics/` (`dashboard:hr_analytics`).

It is a **pure reporting layer** — no models, no migrations. Every number is
derived from the existing accounts, attendance, leaves, payroll, lifecycle and
grades tables.

## Files

| Path | Role |
| --- | --- |
| `apps/dashboard/hr_analytics.py` | Metric engine: filters, workforce snapshot, seven section builders, exports |
| `apps/dashboard/hr_analytics_views.py` | Page view, JSON section API, CSV/XLSX exports, audit |
| `templates/dashboard/hr_analytics.html` | Page scaffold (charts hydrate over AJAX) |
| `static/hr-analytics.css` | Design system, scoped to `.hra` |
| `static/hr-analytics.js` | Chart.js rendering, tabs, filters, sorting, print |

## Sections

`overview`, `workforce`, `attrition`, `attendance`, `compensation`,
`diversity`, `scorecard` — each fetched lazily from
`/dashboard/hr-analytics/data/?section=<name>` and cached for 120 s per
`(org, section, filter)` combination. `?refresh=1` bypasses the cache.

## Metric definitions

| Metric | Definition |
| --- | --- |
| Headcount (as of date `d`) | Joined on or before `d`, with no exit date before `d` |
| Attrition rate | separations ÷ average headcount over the period |
| Annualised attrition | period rate × (12 ÷ months in period) |
| Retention rate | 100 − attrition rate |
| Early attrition | share of leavers whose tenure was under 12 months |
| Voluntary / involuntary | from `OffboardingWorkflow.resignation_reason`; `TERMINATION` is involuntary, `RETIREMENT` is neutral |
| Scheduled capacity | working days × headcount, **accumulated month by month** (a single average across a long window distorts a growing org) |
| Attendance rate | (present + WFH) days ÷ scheduled capacity |
| Absenteeism rate | absent days ÷ scheduled capacity |
| Punctuality | 100 − (check-ins after shift start + grace ÷ all check-ins) |
| Average tenure | mean of (as-of date − joining date) for the active population |
| Span of control | direct reports per person who has at least one, active only |
| Leave utilisation | consumed ÷ allocated, **paid leave types only** (unpaid buckets such as Loss of Pay carry a nominal 365-day ceiling that would swamp the ratio) |
| Leave liability | unused days on **encashable** leave types only — those with `carry_forward_max > 0` — × average day rate (monthly CTC ÷ 26) |
| Cost per employee | gross payroll ÷ active headcount ÷ processed months |
| Mean gender pay gap | (male mean CTC − female mean CTC) ÷ male mean CTC |

**Population.** "Workforce" means users with role `HR` or `EMPLOYEE` in the
org — Organization Admins are excluded, matching the other analytics pages.

**Exit dates.** Taken from a non-cancelled `OffboardingWorkflow.last_working_day`;
if none exists, an inactive user's `archived_at` date is used as a fallback.

**Joining dates.** `date_of_joining`, falling back to `date_joined` when the HR
field was never filled in.

## Filters

`period` (this/last month, this/last quarter, last 6/12 months, YTD, financial
year, custom `from`/`to`), `department`, `employment_type`, `work_mode`,
`location`. All are honoured by every section and by both exports.

## Exports and audit

`?export=csv` returns the department scorecard. `?export=xlsx` returns a
three-sheet workbook (Scorecard, Headcount movement, Separations). Page views
and exports are logged to `AttendanceReportAudit` with `report="hr_analytics"`.

## Navigation

The sidebar entry is registered in two places, both of which matter:

- `apps/subscriptions/plan_catalog.py` — source of truth (`professional` →
  `analytics_basic`, `growth` → `ai_analytics`, both audiences ADMIN + HR)
- `apps/dashboard/sidebar_menu.py` — static fallback catalogs and `*_NAV_ORDER`

Real orgs are served from the DB-backed `NavigationItem` / `PlanMenuItem`
rows, which were updated in place for those two feature keys. After editing
those rows directly, call `invalidate_org_entitlements(org)`.
