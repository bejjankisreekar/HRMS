# Power BI setup

Power BI reads Postgres directly. It does not go through Django, so **none** of the
app's protections apply: no tenant scoping, no role checks, no feature gating.
Whatever the connecting database role can `SELECT` gets copied into a `.pbix`
file that lives on someone's laptop and gets emailed around.

Two consequences drive this whole setup:

- `accounts_user` holds password hashes, bank account numbers, IFSC, PAN,
  Aadhaar, UAN, ESI and date of birth. Importing that table puts all of it in
  the report file.
- `payroll_payslip`, `attendance_attendancerecord` and `leaves_leaverequest`
  have **no `organization_id` column**. They inherit tenancy through a join
  (payslip → payroll run; attendance and leave → user). Miss the join and the
  report silently mixes tenants.

So Power BI connects to a `bi` schema of curated views, as a role that can read
nothing else.

## 1. Create the views

```bash
psql -U postgres -d hrms -f docs/powerbi/bi_views.sql
```

Every view carries an explicit `organization_id`, and no PII column appears in
any of them. Re-running the file is safe (`CREATE OR REPLACE`).

## 2. Create the read-only role

Pick a real password — this is a database credential that will sit in Power BI.

```sql
CREATE ROLE powerbi_ro LOGIN PASSWORD 'put-a-strong-password-here';

GRANT CONNECT ON DATABASE hrms TO powerbi_ro;
GRANT USAGE ON SCHEMA bi TO powerbi_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA bi TO powerbi_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA bi GRANT SELECT ON TABLES TO powerbi_ro;

-- Deny everything else, including the Django tables.
REVOKE ALL ON SCHEMA public FROM powerbi_ro;
```

Views run with the *owner's* privileges, so `powerbi_ro` reads through them
without any access to `accounts_user` itself. Verify:

```sql
SET ROLE powerbi_ro;
SELECT count(*) FROM bi.dim_employee;   -- works
SELECT count(*) FROM accounts_user;     -- must fail: permission denied
RESET ROLE;
```

## 3. Connect Power BI Desktop

Power BI Desktop is Windows-only and free to build with.

1. **Get Data → PostgreSQL database**
2. Server `localhost:5432`, Database `hrms`
3. Choose **Import**, not DirectQuery. The dataset is small (~20k attendance
   rows) and Import is far faster.
4. Sign in with `powerbi_ro` and the password from step 2.
5. Select the `bi` schema views. Take the dimensions and only the facts you
   need — `fact_payslip_line` is the largest.

If the connector errors about a missing provider, install the **Npgsql** data
provider (the ADO.NET one, with the GAC option enabled) and restart Power BI.

## 4. Model it

Relationships to create (all one-to-many, single direction, filtering from the
dimension into the fact):

| From | To |
|---|---|
| `dim_employee[employee_pk]` | `fact_payslip[employee_pk]` |
| `dim_employee[employee_pk]` | `fact_attendance[employee_pk]` |
| `dim_employee[employee_pk]` | `fact_leave_request[employee_pk]` |
| `dim_employee[employee_pk]` | `fact_leave_balance[employee_pk]` |
| `dim_department[department_id]` | `dim_employee[department_id]` |
| `dim_organization[organization_id]` | `dim_employee[organization_id]` |
| `dim_leave_type[leave_type_id]` | `fact_leave_request[leave_type_id]` |

Then add a date table (`Modeling → New table`) and relate it to
`fact_attendance[attendance_date]` and `fact_payslip[period_start]`:

```
DimDate = CALENDAR(DATE(2024,1,1), DATE(2030,12,31))
```

**Put `dim_organization[organization_name]` on every report page as a slicer,
and set it as a required filter.** Without it, a headcount card sums across
every tenant in the database.

## 5. Measures that match the app

The payroll model is conventional: `gross_salary` is FULL monthly earnings and
absence is a Loss-of-Pay *deduction* (`lop_amount`), not a reduced gross. Net is
already `gross − deductions + reimbursements`, floored at zero. Employer PF is
**not** part of net — it is employer cost, so never add it to a payout total.

```
Total Gross      = SUM(fact_payslip[gross_salary])
Total Net Payout = SUM(fact_payslip[net_salary])
Total LOP        = SUM(fact_payslip[lop_amount])
Employer Cost    = [Total Gross] + SUM(fact_payslip[employer_pf])

Headcount        = CALCULATE(DISTINCTCOUNT(dim_employee[employee_pk]),
                             dim_employee[is_active] = TRUE)

Attendance %     = DIVIDE(
                       CALCULATE(COUNTROWS(fact_attendance),
                                 fact_attendance[status] = "PRESENT"),
                       COUNTROWS(fact_attendance))
```

That attendance ratio is *present ÷ records*, which is not the definition the
app uses. `apps/dashboard/attendance_analytics.py` computes
**present ÷ (active employees × working days)** so that a missing record counts
against the rate. If you want the two to agree, reproduce that denominator —
otherwise Power BI will read consistently higher than the in-app report and
someone will eventually ask why.

## 6. Sharing costs money

Building is free. Publishing to the Power BI Service so other people can open
the report needs **Power BI Pro, roughly $14/user/month** — for viewers as well
as authors, unless the workspace sits on Premium/Fabric capacity.

Scheduled refresh against a database on `localhost` also needs the
**on-premises data gateway** installed on a machine that is always on. Once the
app moves to hosted Postgres, point the gateway (or a direct cloud connection)
at that instead.

## What this does not cover

Row-level security. Every user with the report sees every organization in it.
For an internal single-company deployment that is fine. If you ever hand a
report to a *customer* org, you need Power BI RLS roles filtering
`dim_organization[organization_id]`, mapped to their identity — and at that
point re-read the licensing question, because each of their viewers needs a Pro
seat.
