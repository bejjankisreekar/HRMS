-- ---------------------------------------------------------------------------
-- Power BI reporting layer for the HRMS.
--
-- Power BI connects straight to Postgres and therefore bypasses EVERY
-- application safeguard: no TenantSchemaMiddleware, no organization scoping,
-- no role checks, no FeatureGateMiddleware. Whatever the connecting DB role can
-- SELECT ends up cached inside the .pbix file on someone's laptop.
--
-- So do NOT point Power BI at the Django tables. Point it here.
--
-- Two things this file guarantees:
--   1. No PII leaves the database. accounts_user holds password hashes, bank
--      account numbers, PAN, Aadhaar, UAN, ESI and date of birth. None of those
--      columns appear in any view below.
--   2. Every fact row carries an explicit organization_id. payroll_payslip,
--      attendance_attendancerecord and leaves_leaverequest have NO org column of
--      their own - they inherit tenancy through a join. Miss the join and your
--      report silently mixes tenants together.
--
-- Run as a superuser (e.g. postgres) against the hrms database.
-- ---------------------------------------------------------------------------

CREATE SCHEMA IF NOT EXISTS bi;

-- --- Dimensions ------------------------------------------------------------

CREATE OR REPLACE VIEW bi.dim_organization AS
SELECT
    o.id                AS organization_id,
    o.name              AS organization_name,
    o.organization_code,
    o.industry,
    o.country,
    o.state,
    o.city,
    o.currency,
    o.timezone,
    o.subscription_plan,
    o.subscription_status,
    o.is_active,
    o.created_at
FROM organizations_organization o;

CREATE OR REPLACE VIEW bi.dim_department AS
SELECT
    d.id            AS department_id,
    d.organization_id,
    d.name          AS department_name,
    d.code          AS department_code,
    d.is_active
FROM organizations_department d;

-- Deliberately excludes: password, bank_account_number, ifsc_code, pan_number,
-- aadhaar_number, pf_account_number, uan_number, esi_number, date_of_birth,
-- personal_email, alternate_phone, emergency contacts, address, internal_notes.
CREATE OR REPLACE VIEW bi.dim_employee AS
SELECT
    u.id                AS employee_pk,
    u.organization_id,
    u.employee_id       AS employee_code,
    NULLIF(TRIM(CONCAT_WS(' ', u.first_name, u.last_name)), '') AS employee_name,
    u.role,
    u.department_id,
    u.designation,
    u.business_unit,
    u.employment_type,
    u.employment_status,
    u.work_location,
    u.work_mode,
    u.gender,
    u.date_of_joining,
    u.reporting_manager_id,
    u.is_active,
    u.date_joined       AS account_created_at
FROM accounts_user u
WHERE u.is_superuser = false;   -- keep the cross-tenant Super Admin out of headcount

CREATE OR REPLACE VIEW bi.dim_leave_type AS
SELECT
    lt.id           AS leave_type_id,
    lt.organization_id,
    lt.name         AS leave_type_name,
    lt.code         AS leave_type_code,
    lt.is_paid,
    lt.annual_quota,
    lt.is_active
FROM leaves_leavetype lt;

-- --- Facts -----------------------------------------------------------------

-- organization_id comes from the payroll run, not the payslip.
-- gross_salary is FULL monthly earnings; the absence slice is the
-- leave_deduction (LOP) line. employer_pf is NOT part of net.
CREATE OR REPLACE VIEW bi.fact_payslip AS
SELECT
    p.id                AS payslip_id,
    r.organization_id,
    p.user_id           AS employee_pk,
    r.year,
    r.month,
    MAKE_DATE(r.year, r.month, 1) AS period_start,
    r.status            AS run_status,
    p.gross_salary,
    p.total_deductions,
    p.net_salary,
    p.leave_deduction   AS lop_amount,
    p.employer_pf,
    p.bonus,
    p.reimbursements,
    p.overtime_amount,
    p.attendance_days,
    p.working_days,
    p.leave_days,
    p.payment_status,
    p.payment_date
FROM payroll_payslip p
JOIN payroll_payrollrun r ON r.id = p.payroll_run_id;

-- One row per payslip line, categorised the way deduction_breakdown does it.
CREATE OR REPLACE VIEW bi.fact_payslip_line AS
SELECT
    pl.id               AS payslip_line_id,
    r.organization_id,
    pl.payslip_id,
    p.user_id           AS employee_pk,
    r.year,
    r.month,
    MAKE_DATE(r.year, r.month, 1) AS period_start,
    pl.label,
    pl.line_type,
    sc.code             AS component_code,
    sc.category         AS component_category,
    sc.is_statutory,
    pl.amount
FROM payroll_payslipline pl
JOIN payroll_payslip   p ON p.id = pl.payslip_id
JOIN payroll_payrollrun r ON r.id = p.payroll_run_id
LEFT JOIN payroll_salarycomponent sc ON sc.id = pl.component_id;

-- organization_id comes from the employee, not the record.
CREATE OR REPLACE VIEW bi.fact_attendance AS
SELECT
    a.id                AS attendance_id,
    u.organization_id,
    a.user_id           AS employee_pk,
    u.department_id,
    a.date              AS attendance_date,
    a.status,
    a.check_in,
    a.check_out,
    a.break_minutes,
    a.attendance_source,
    CASE WHEN a.check_in IS NOT NULL AND a.check_out IS NOT NULL
         THEN ROUND(EXTRACT(EPOCH FROM (a.check_out - a.check_in)) / 3600.0, 2)
    END                 AS hours_logged
FROM attendance_attendancerecord a
JOIN accounts_user u ON u.id = a.user_id;

CREATE OR REPLACE VIEW bi.fact_leave_request AS
SELECT
    lr.id               AS leave_request_id,
    u.organization_id,
    lr.user_id          AS employee_pk,
    u.department_id,
    lr.leave_type_id,
    lr.start_date,
    lr.end_date,
    lr.total_days,
    lr.half_day,
    lr.status,
    lr.applied_at,
    lr.reviewed_at,
    CASE WHEN lr.reviewed_at IS NOT NULL
         THEN ROUND(EXTRACT(EPOCH FROM (lr.reviewed_at - lr.applied_at)) / 86400.0, 2)
    END                 AS days_to_decision
FROM leaves_leaverequest lr
JOIN accounts_user u ON u.id = lr.user_id;

CREATE OR REPLACE VIEW bi.fact_leave_balance AS
SELECT
    lb.id               AS leave_balance_id,
    u.organization_id,
    lb.user_id          AS employee_pk,
    lb.leave_type_id,
    lb.year,
    lb.allocated,
    lb.used,
    lb.adjusted,
    lb.carried_forward
FROM leaves_leavebalance lb
JOIN accounts_user u ON u.id = lb.user_id;
