"""Populate one tenant with a full, realistic demo dataset.

Every module the product ships is given something to show: staff and org
structure, shifts and holidays, a year of attendance, leave balances and
requests, twelve processed payroll runs with statutory deductions and
recoveries, salary revisions, onboarding/offboarding (which is what makes the
attrition analytics non-empty), assets, regularizations and notifications.

    python manage.py seed_demo_data --org "TATA Motors"
    python manage.py seed_demo_data --org "TATA Motors" --months 18
    python manage.py seed_demo_data --org "TATA Motors" --purge   # remove it again

Everything it creates is deterministic (fixed RNG seed) and idempotent — the
command can be re-run without duplicating people or attendance rows.
Seeded users are recognised by the ``tm-`` username prefix, which is also what
``--purge`` keys off, so hand-made accounts are never touched.
"""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.organizations.models import Department, Organization
from apps.organizations.utils import set_schema_search_path

USERNAME_PREFIX = "tm-"
DEMO_PASSWORD = "Demo@12345"
EMAIL_DOMAIN = "tatamotors-demo.in"

RNG = random.Random(20260825)


# ── roster source material ────────────────────────────────────────────────────

MALE_NAMES = [
    "Arjun", "Rohan", "Vikram", "Aditya", "Karthik", "Siddharth", "Nikhil", "Rahul",
    "Manish", "Pranav", "Harsh", "Devan", "Aniket", "Gaurav", "Yash", "Sandeep",
    "Rajat", "Tarun", "Varun", "Abhishek", "Kunal", "Sameer", "Naveen", "Ashwin",
]
FEMALE_NAMES = [
    "Ananya", "Priya", "Meera", "Divya", "Sneha", "Kavya", "Ritika", "Nisha",
    "Pooja", "Shreya", "Aarti", "Tanvi", "Ishita", "Lakshmi", "Neha", "Swati",
    "Rekha", "Payal", "Aditi", "Sanjana",
]
SURNAMES = [
    "Mehta", "Sharma", "Iyer", "Reddy", "Nair", "Patil", "Deshmukh", "Kulkarni",
    "Chatterjee", "Banerjee", "Joshi", "Rao", "Gupta", "Verma", "Kapoor", "Malhotra",
    "Pillai", "Bhatt", "Sinha", "Chauhan", "Menon", "Shetty", "Agarwal", "Bose",
]

LOCATIONS = ["Pune Plant", "Mumbai HQ", "Jamshedpur Plant", "Bengaluru Tech Centre", "Lucknow Plant"]

# (department, headcount, primary location, designation pool)
DEPARTMENT_PLAN = [
    ("Engineering", 12, "Bengaluru Tech Centre",
     ["Software Engineer", "Senior Software Engineer", "QA Engineer", "DevOps Engineer", "Engineering Manager"]),
    ("Manufacturing", 10, "Pune Plant",
     ["Production Operator", "Shift Supervisor", "Process Engineer", "Plant Manager"]),
    ("Quality Assurance", 6, "Pune Plant",
     ["Quality Inspector", "Quality Engineer", "QA Lead"]),
    ("Supply Chain", 6, "Jamshedpur Plant",
     ["Procurement Executive", "Logistics Coordinator", "Supply Chain Analyst", "Sourcing Manager"]),
    ("Sales", 8, "Mumbai HQ",
     ["Sales Executive", "Territory Manager", "Key Account Manager", "Regional Sales Head"]),
    ("Marketing", 4, "Mumbai HQ",
     ["Marketing Executive", "Brand Manager", "Digital Marketing Specialist"]),
    ("Finance", 5, "Mumbai HQ",
     ["Accounts Executive", "Financial Analyst", "Finance Manager"]),
    ("Human Resources", 4, "Mumbai HQ",
     ["HR Executive", "Senior HR Manager", "Payroll Manager", "Recruiter"]),
    ("Information Technology", 5, "Bengaluru Tech Centre",
     ["IT Support Engineer", "Systems Administrator", "IT Manager"]),
    ("Customer Support", 6, "Lucknow Plant",
     ["Support Associate", "Support Team Lead", "Service Advisor"]),
]

# Grade ladder used inside each department, most senior first.
DEPT_LADDER = ["EMP-SM", "EMP-MGR", "EMP-AM", "EMP-TL", "EMP-SA", "EMP-ASC", "EMP-JR", "EMP-INT"]

# Monthly CTC by grade code, before jitter.
GRADE_CTC = {
    "EMP-DIR": 350000, "EMP-SM": 215000, "EMP-MGR": 148000, "EMP-AM": 104000,
    "EMP-TL": 78000, "EMP-SA": 57000, "EMP-ASC": 41000, "EMP-JR": 29000, "EMP-INT": 17000,
    "HR-ADM": 195000, "HR-SM": 160000, "HR-MGR": 118000, "HR-EXE": 62000,
    "HR-PAY": 58000, "HR-REC": 47000,
}

HOLIDAYS = [
    ("New Year's Day", 1, 1, "PUBLIC"),
    ("Republic Day", 1, 26, "NATIONAL"),
    ("Maha Shivaratri", 2, 26, "RELIGIOUS"),
    ("Holi", 3, 14, "RELIGIOUS"),
    ("Gudi Padwa", 3, 30, "REGIONAL"),
    ("Good Friday", 4, 18, "RELIGIOUS"),
    ("Maharashtra Day", 5, 1, "REGIONAL"),
    ("Independence Day", 8, 15, "NATIONAL"),
    ("Ganesh Chaturthi", 8, 27, "RELIGIOUS"),
    ("Gandhi Jayanti", 10, 2, "NATIONAL"),
    ("Dussehra", 10, 2, "RELIGIOUS"),
    ("Diwali", 10, 21, "RELIGIOUS"),
    ("Christmas", 12, 25, "PUBLIC"),
]

EXIT_REASONS = [
    ("BETTER_OPPORTUNITY", 5),
    ("PERSONAL", 2),
    ("RELOCATION", 2),
    ("TERMINATION", 1),
    ("HEALTH", 1),
]


# ── helpers ───────────────────────────────────────────────────────────────────

def _slug(value: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "-" for ch in value).strip("-")


def _jitter(base: int, spread: float = 0.08) -> Decimal:
    factor = 1 + RNG.uniform(-spread, spread)
    return Decimal(str(round(base * factor / 500) * 500))


def _weighted(pairs):
    """Pick from [(value, weight), ...]."""
    total = sum(w for _, w in pairs)
    roll = RNG.uniform(0, total)
    upto = 0.0
    for value, weight in pairs:
        upto += weight
        if roll <= upto:
            return value
    return pairs[-1][0]


def _aware(d: date, t: time):
    return timezone.make_aware(datetime.combine(d, t), timezone.get_current_timezone())


def _month_iter(start: date, end: date):
    y, m = start.year, start.month
    while (y, m) <= (end.year, end.month):
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


class Command(BaseCommand):
    help = "Populate one organization with a complete, realistic demo dataset."

    def add_arguments(self, parser):
        parser.add_argument("--org", default="TATA Motors", help="Organization name")
        parser.add_argument("--months", type=int, default=12,
                            help="How many months of attendance and payroll history to build")
        parser.add_argument("--skip-payroll", action="store_true",
                            help="Skip payroll processing (much faster)")
        parser.add_argument("--purge", action="store_true",
                            help="Delete previously seeded demo users and their data, then stop")

    # ── entry point ───────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        try:
            org = Organization.objects.get(name=options["org"])
        except Organization.DoesNotExist:
            raise CommandError(f'No organization named "{options["org"]}".')

        set_schema_search_path(org.schema_name)
        self.org = org
        self.today = timezone.localdate()
        self.months = max(3, min(36, options["months"]))
        self.window_start = (self.today.replace(day=1) - timedelta(days=31 * (self.months - 1))).replace(day=1)

        if options["purge"]:
            self._purge()
            return

        self._say(f"Seeding {org.name} ({org.schema_name}) — {self.months} months of history")
        self._stage("Departments", self.seed_departments)
        self._stage("Grades & designations", self.seed_grades)
        self._stage("Work shifts", self.seed_shifts)
        self._stage("Holidays", self.seed_holidays)
        self._stage("Leave types", self.seed_leave_types)
        self._stage("People", self.seed_people)
        self._stage("Reporting hierarchy", self.seed_hierarchy)
        self._stage("Salary structures & CTC", self.seed_salaries)
        self._stage("Leave balances & requests", self.seed_leaves)
        self._stage("Attendance history", self.seed_attendance)
        self._stage("Regularization requests", self.seed_regularizations)
        self._stage("Loans, advances & reimbursements", self.seed_recoveries)
        self._stage("Salary revisions", self.seed_revisions)
        self._stage("Onboarding & offboarding", self.seed_lifecycle)
        if not options["skip_payroll"]:
            self._stage("Payroll runs", self.seed_payroll)
        self._stage("Closing out exits", self.finalize_exits)
        self._stage("Notifications", self.seed_notifications)
        self._stage("Automation rules", self.seed_rules)
        self._stage("Letter templates & documents", self.seed_documents)
        self._summary()

    # ── output helpers ────────────────────────────────────────────────────────

    def _say(self, message):
        self.stdout.write(self.style.SUCCESS(message))

    def _stage(self, label, fn):
        self.stdout.write(f"  {label} ... ", ending="")
        self.stdout.flush()
        result = fn()
        self.stdout.write(self.style.SUCCESS(result or "done"))

    # ── purge ─────────────────────────────────────────────────────────────────

    def _purge(self):
        """Remove everything this command generates, for a clean re-seed.

        Seeded people go entirely (their records cascade). For the org's
        hand-made accounts only the generated artefacts are removed — the
        accounts themselves are left alone.
        """
        from apps.attendance.models import AttendanceRecord, AttendanceRegularizationRequest
        from apps.leaves.models import LeaveRequest
        from apps.lifecycle.models import AssetAllocation, OffboardingWorkflow, OnboardingWorkflow
        from apps.payroll.models import (
            EmployeeDeduction, EmployeeLoan, PayrollRun, Reimbursement, SalaryRevision,
        )

        seeded = User.objects.filter(organization=self.org, username__startswith=USERNAME_PREFIX)
        count = seeded.count()
        AttendanceRecord.objects.filter(user__in=seeded).delete()
        seeded.delete()

        org_users = User.objects.filter(organization=self.org)
        runs = PayrollRun.objects.filter(organization=self.org)
        run_count = runs.count()
        runs.delete()
        for model in (OnboardingWorkflow, OffboardingWorkflow, AssetAllocation):
            model.objects.filter(organization=self.org).delete()
        for model in (EmployeeLoan, EmployeeDeduction, Reimbursement, SalaryRevision):
            model.objects.filter(user__in=org_users).delete()
        AttendanceRegularizationRequest.objects.filter(user__in=org_users).delete()
        LeaveRequest.objects.filter(user__in=org_users).delete()

        # Anyone the seeder retired gets their account back.
        org_users.filter(archived_at__isnull=False, is_active=False).update(
            is_active=True, archived_at=None, employment_status=User.EmploymentStatus.ACTIVE,
        )
        Department.objects.filter(
            organization=self.org,
            name__in=[d[0] for d in DEPARTMENT_PLAN],
        ).exclude(members__isnull=False).delete()
        self._say(f"Purged {count} demo users and {run_count} payroll runs from {self.org.name}.")

    # ── stage 1: departments ──────────────────────────────────────────────────

    def seed_departments(self):
        self.departments = {}
        created = 0
        for order, (name, _hc, _loc, _desigs) in enumerate(DEPARTMENT_PLAN):
            dept, made = Department.objects.get_or_create(
                organization=self.org,
                name=name,
                defaults={"code": _slug(name)[:40], "sort_order": order, "is_active": True,
                          "description": f"{name} function at {self.org.name}."},
            )
            self.departments[name] = dept
            created += int(made)
        # Keep whatever the org already had usable.
        for dept in Department.objects.filter(organization=self.org):
            self.departments.setdefault(dept.name, dept)
        return f"{created} new, {len(self.departments)} total"

    # ── stage 2: grades ───────────────────────────────────────────────────────

    def seed_grades(self):
        from apps.grades.models import Designation, Grade, GradeStatus
        from apps.grades.services.defaults import seed_organization_grades

        seed_organization_grades(self.org)
        self.grades = {g.code: g for g in Grade.objects.filter(organization=self.org)}

        wanted = sorted({d for _n, _h, _l, pool in DEPARTMENT_PLAN for d in pool})
        grade_for_designation = {
            "Engineering Manager": "EMP-MGR", "Plant Manager": "EMP-MGR",
            "Sourcing Manager": "EMP-MGR", "Finance Manager": "EMP-MGR",
            "IT Manager": "EMP-MGR", "Brand Manager": "EMP-AM",
            "Regional Sales Head": "EMP-SM", "Key Account Manager": "EMP-AM",
            "Territory Manager": "EMP-AM", "QA Lead": "EMP-TL",
            "Shift Supervisor": "EMP-TL", "Support Team Lead": "EMP-TL",
            "Senior Software Engineer": "EMP-SA", "Senior HR Manager": "HR-SM",
            "Payroll Manager": "HR-PAY", "HR Executive": "HR-EXE", "Recruiter": "HR-REC",
        }
        made = 0
        for name in wanted:
            code = grade_for_designation.get(name, "EMP-ASC")
            _obj, created = Designation.objects.get_or_create(
                organization=self.org,
                name=name,
                defaults={"code": _slug(name)[:40], "grade": self.grades.get(code),
                          "status": GradeStatus.ACTIVE},
            )
            made += int(created)
        self.designations = {d.name: d for d in Designation.objects.filter(organization=self.org)}
        return f"{len(self.grades)} grades, {made} new designations"

    # ── stage 3: shifts ───────────────────────────────────────────────────────

    def seed_shifts(self):
        from apps.attendance.models import WorkShift

        plan = [
            ("General Shift", "GEN", time(9, 0), time(18, 0), 60, 15, True, "#7c3aed"),
            ("Morning Shift", "MRN", time(6, 0), time(14, 0), 30, 10, False, "#0ea5e9"),
            ("Evening Shift", "EVE", time(14, 0), time(22, 0), 30, 10, False, "#f59e0b"),
            ("Night Shift", "NGT", time(22, 0), time(6, 0), 45, 10, False, "#6366f1"),
        ]
        has_default = WorkShift.objects.filter(organization=self.org, is_default=True).exists()
        made = 0
        for name, code, start, end, brk, grace, is_default, color in plan:
            _obj, created = WorkShift.objects.get_or_create(
                organization=self.org,
                name=name,
                defaults={
                    "shift_code": code, "start_time": start, "end_time": end,
                    "break_minutes": brk, "grace_minutes": grace, "color": color,
                    "is_default": is_default and not has_default,
                    "weekly_off_days": "6", "is_active": True,
                    "description": f"{name} ({start:%H:%M}–{end:%H:%M})",
                },
            )
            if created and is_default and not has_default:
                has_default = True
            made += int(created)
        self.shifts = {s.name: s for s in WorkShift.objects.filter(organization=self.org)}
        self.default_shift = (
            WorkShift.objects.filter(organization=self.org, is_default=True).first()
            or next(iter(self.shifts.values()))
        )
        return f"{made} new, {len(self.shifts)} total"

    # ── stage 4: holidays ─────────────────────────────────────────────────────

    def seed_holidays(self):
        from apps.leaves.models import Holiday

        made = 0
        years = sorted({self.window_start.year, self.today.year, self.today.year + 1})
        for year in years:
            for name, month, day, kind in HOLIDAYS:
                try:
                    on = date(year, month, day)
                except ValueError:
                    continue
                _obj, created = Holiday.objects.get_or_create(
                    organization=self.org, name=name, date=on,
                    defaults={"holiday_type": kind, "is_optional": kind == "REGIONAL"},
                )
                made += int(created)
        return f"{made} new across {len(years)} years"

    # ── stage 5: leave types ──────────────────────────────────────────────────

    def seed_leave_types(self):
        from apps.leaves.models import LeaveType
        from apps.leaves.services import ensure_leave_types

        ensure_leave_types(self.org)
        self.leave_types = list(LeaveType.objects.filter(organization=self.org, is_active=True))
        return f"{len(self.leave_types)} active"

    # ── stage 6: people ───────────────────────────────────────────────────────

    def _name_pool(self):
        """Deterministic, collision-free (first, last, gender) triples."""
        pool = []
        for first in MALE_NAMES:
            pool.append((first, "MALE"))
        for first in FEMALE_NAMES:
            pool.append((first, "FEMALE"))
        combos = [(f, s, g) for f, g in pool for s in SURNAMES]
        RNG.shuffle(combos)
        seen, out = set(), []
        for first, last, gender in combos:
            key = (first, last)
            if key in seen:
                continue
            seen.add(key)
            out.append((first, last, gender))
        return out

    def seed_people(self):
        from apps.grades.models import Designation

        pool = iter(self._name_pool())
        existing = {
            u.username: u
            for u in User.objects.filter(organization=self.org, username__startswith=USERNAME_PREFIX)
        }
        self.people = []
        created = 0
        seq = 1000

        # Who leaves, and when — spread across the history window so the
        # attrition trend has shape instead of a single spike.
        exit_slots = []
        for reason, count in EXIT_REASONS:
            exit_slots.extend([reason] * count)
        RNG.shuffle(exit_slots)

        for dept_name, headcount, location, desig_pool in DEPARTMENT_PLAN:
            dept = self.departments[dept_name]
            is_hr_dept = dept_name == "Human Resources"
            for index in range(headcount):
                first, last, gender = next(pool)
                seq += 1
                username = f"{USERNAME_PREFIX}{_slug(first)}-{_slug(last)}"
                if username in existing:
                    self.people.append(existing[username])
                    continue

                grade_code = self._grade_for(index, headcount, is_hr_dept)
                designation = self._designation_for(index, desig_pool, is_hr_dept)
                seniority = self.grades[grade_code].level_number if grade_code in self.grades else 6
                join_date = self._join_date_for(seniority)
                employment_type = _weighted([
                    (User.EmploymentType.FULL_TIME, 84),
                    (User.EmploymentType.CONTRACT, 8),
                    (User.EmploymentType.INTERN, 5),
                    (User.EmploymentType.PART_TIME, 3),
                ]) if seniority >= 6 else User.EmploymentType.FULL_TIME
                work_mode = _weighted([
                    (User.WorkMode.ONSITE, 55), (User.WorkMode.HYBRID, 33), (User.WorkMode.REMOTE, 12),
                ]) if dept_name in ("Engineering", "Information Technology", "Marketing", "Sales") \
                    else User.WorkMode.ONSITE

                user = User.objects.create_user(
                    email=f"{_slug(first)}.{_slug(last)}@{EMAIL_DOMAIN}",
                    password=DEMO_PASSWORD,
                    username=username,
                    role=User.Role.HR if is_hr_dept else User.Role.EMPLOYEE,
                    organization=self.org,
                    first_name=first,
                    last_name=last,
                    employee_id=f"TM{seq}",
                    gender=gender,
                    date_of_birth=self._dob_for(seniority),
                    marital_status=_weighted([
                        (User.MaritalStatus.SINGLE, 45), (User.MaritalStatus.MARRIED, 52),
                        (User.MaritalStatus.OTHER, 3),
                    ]),
                    nationality="Indian",
                    phone=f"9{RNG.randint(100000000, 899999999)}",
                    personal_email=f"{_slug(first)}.{_slug(last)}{RNG.randint(10, 99)}@gmail.com",
                    emergency_contact_name=f"{RNG.choice(SURNAMES)} family",
                    emergency_contact_phone=f"8{RNG.randint(100000000, 899999999)}",
                    emergency_contact_relation=RNG.choice(["Spouse", "Parent", "Sibling"]),
                    department=dept,
                    designation=designation,
                    job_grade=self.grades.get(grade_code),
                    org_designation=self.designations.get(designation),
                    business_unit=RNG.choice(["Passenger Vehicles", "Commercial Vehicles", "Corporate"]),
                    employment_type=employment_type,
                    date_of_joining=join_date,
                    work_shift=self._shift_for(dept_name),
                    work_location=location,
                    work_mode=work_mode,
                    city=location.split()[0],
                    state=RNG.choice(["Maharashtra", "Karnataka", "Jharkhand", "Uttar Pradesh"]),
                    country="India",
                    postal_code=str(RNG.randint(110000, 799999)),
                    address_line=f"{RNG.randint(1, 220)}, {RNG.choice(['MG Road', 'Station Road', 'Park Street', 'Ring Road'])}",
                    bank_name=RNG.choice(["HDFC Bank", "ICICI Bank", "State Bank of India", "Axis Bank"]),
                    bank_account_holder=f"{first} {last}",
                    bank_account_number=str(RNG.randint(10**11, 10**12 - 1)),
                    ifsc_code=f"{RNG.choice(['HDFC', 'ICIC', 'SBIN', 'UTIB'])}0{RNG.randint(100000, 999999)}",
                    pan_number=f"{''.join(RNG.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ') for _ in range(5))}"
                               f"{RNG.randint(1000, 9999)}{RNG.choice('ABCDEFGHIJKLMNOPQRSTUVWXYZ')}",
                    uan_number=str(RNG.randint(10**11, 10**12 - 1)),
                    pf_account_number=f"MH/PUN/{RNG.randint(10000, 99999)}/{RNG.randint(100, 999)}",
                    esi_number=str(RNG.randint(10**9, 10**10 - 1)),
                    employment_status=User.EmploymentStatus.ACTIVE,
                    email_verified=True,
                    terms_accepted=True,
                    privacy_policy_accepted=True,
                )
                created += 1
                self.people.append(user)

        # A demo Organization Admin, so all three login portals have a known account.
        admin_username = f"{USERNAME_PREFIX}admin"
        if not User.objects.filter(username=admin_username).exists():
            User.objects.create_user(
                email=f"admin@{EMAIL_DOMAIN}",
                password=DEMO_PASSWORD,
                username=admin_username,
                role=User.Role.ADMIN,
                organization=self.org,
                first_name="Ishaan",
                last_name="Raghavan",
                employee_id="TM0001",
                gender=User.Gender.MALE,
                date_of_birth=date(self.today.year - 46, 4, 17),
                designation="Head of People Operations",
                job_grade=self.grades.get("EMP-DIR"),
                employment_type=User.EmploymentType.FULL_TIME,
                date_of_joining=self.today - timedelta(days=2400),
                work_location="Mumbai HQ",
                work_mode=User.WorkMode.HYBRID,
                work_shift=self.default_shift,
                city="Mumbai", state="Maharashtra", country="India",
                phone="9820011223",
                employment_status=User.EmploymentStatus.ACTIVE,
                email_verified=True, terms_accepted=True, privacy_policy_accepted=True,
            )
            created += 1

        # Enrich the org's pre-existing accounts so no profile page looks empty.
        self._backfill_existing()

        # Mark a slice of people as probation / notice so those pipelines show data.
        actives = [u for u in self.people if u.is_active]
        for user in RNG.sample(actives, min(5, len(actives))):
            if user.date_of_joining and (self.today - user.date_of_joining).days < 200:
                user.employment_status = User.EmploymentStatus.PROBATION
                user.save(update_fields=["employment_status"])
        for user in RNG.sample(actives, min(3, len(actives))):
            if user.employment_status == User.EmploymentStatus.ACTIVE:
                user.employment_status = User.EmploymentStatus.NOTICE
                user.save(update_fields=["employment_status"])

        self._choose_leavers(exit_slots)
        return f"{created} created, {len(self.people)} in roster, {len(self.leavers)} scheduled exits"

    def _choose_leavers(self, exit_slots):
        """Pick who leaves and when.

        Exits already on file win, so a second run of this command reuses the
        same people instead of retiring a fresh batch every time.
        """
        from apps.lifecycle.models import OffboardingWorkflow

        on_file = {
            w.user_id: w
            for w in OffboardingWorkflow.objects
            .filter(organization=self.org)
            .exclude(status=OffboardingWorkflow.Status.CANCELLED)
        }
        self.leavers = []
        for user in self.people:
            workflow = on_file.get(user.pk)
            if not workflow:
                continue
            user._exit_date = workflow.last_working_day
            user._exit_reason = workflow.resignation_reason or "PERSONAL"
            self.leavers.append(user)

        target = len(exit_slots)
        eligible = [
            u for u in self.people
            if u.is_active and u.date_of_joining and u not in self.leavers
            and (self.today - u.date_of_joining).days > 200
            and u.role == User.Role.EMPLOYEE
        ]
        for reason in exit_slots[len(self.leavers):target]:
            candidates = [u for u in eligible if u not in self.leavers]
            if not candidates:
                break
            user = RNG.choice(candidates)
            span = (self.today - max(self.window_start, user.date_of_joining)).days
            if span < 30:
                continue
            user._exit_date = self.today - timedelta(days=RNG.randint(10, max(11, span - 10)))
            user._exit_reason = reason
            self.leavers.append(user)

    def _grade_for(self, index, headcount, is_hr_dept):
        if is_hr_dept:
            return ["HR-SM", "HR-MGR", "HR-EXE", "HR-PAY", "HR-REC"][min(index, 4)]
        if index == 0:
            return "EMP-SM"
        if index in (1, 2) and headcount >= 8:
            return "EMP-MGR"
        if index <= 3:
            return "EMP-AM"
        if index <= 5:
            return "EMP-TL"
        return _weighted([("EMP-SA", 30), ("EMP-ASC", 40), ("EMP-JR", 22), ("EMP-INT", 8)])

    def _designation_for(self, index, pool, is_hr_dept):
        if is_hr_dept:
            return ["Senior HR Manager", "HR Executive", "Payroll Manager", "Recruiter"][min(index, 3)]
        if index == 0:
            return pool[-1]
        return pool[min(index, len(pool) - 1)] if index <= 2 else RNG.choice(pool[:-1] or pool)

    def _join_date_for(self, seniority):
        """Senior people joined longer ago — that is what makes tenure bands realistic."""
        max_years = {1: 11, 2: 9, 3: 8, 4: 6, 5: 5}.get(seniority, 4)
        days = RNG.randint(45, int(max_years * 365))
        return self.today - timedelta(days=days)

    def _dob_for(self, seniority):
        base_age = {1: 48, 2: 44, 3: 40, 4: 36, 5: 33}.get(seniority, 27)
        age = base_age + RNG.randint(-4, 6)
        return date(self.today.year - age, RNG.randint(1, 12), RNG.randint(1, 28))

    def _shift_for(self, dept_name):
        if dept_name in ("Manufacturing", "Quality Assurance"):
            return self.shifts.get(RNG.choice(["General Shift", "Morning Shift", "Evening Shift"]))
        if dept_name == "Customer Support":
            return self.shifts.get(RNG.choice(["General Shift", "Evening Shift"]))
        return self.default_shift

    def _backfill_existing(self):
        """Give the org's hand-made accounts a full profile too."""
        legacy = User.objects.filter(organization=self.org).exclude(
            username__startswith=USERNAME_PREFIX
        ).exclude(role=User.Role.SUPER_ADMIN)
        eng = self.departments.get("Engineering")
        hr_dept = self.departments.get("Human Resources")
        for user in legacy:
            fields = []
            if not user.first_name:
                user.first_name = (user.username or "Team").split("_")[-1].title()
                fields.append("first_name")
            if not user.last_name:
                user.last_name = "Motors"
                fields.append("last_name")
            if not user.employee_id:
                user.employee_id = f"TM{RNG.randint(100, 999)}"
                fields.append("employee_id")
            if not user.date_of_joining:
                user.date_of_joining = self.today - timedelta(days=RNG.randint(400, 1500))
                fields.append("date_of_joining")
            if not user.department_id and user.role != User.Role.ADMIN:
                user.department = hr_dept if user.role == User.Role.HR else eng
                fields.append("department")
            if not user.designation:
                user.designation = "Senior HR Manager" if user.role == User.Role.HR else "Software Engineer"
                fields.append("designation")
            if not user.job_grade_id:
                user.job_grade = self.grades.get("HR-SM" if user.role == User.Role.HR else "EMP-SA")
                fields.append("job_grade")
            if not user.gender:
                user.gender = _weighted([("MALE", 60), ("FEMALE", 40)])
                fields.append("gender")
            if not user.date_of_birth:
                user.date_of_birth = self._dob_for(4)
                fields.append("date_of_birth")
            if not user.employment_type:
                user.employment_type = User.EmploymentType.FULL_TIME
                fields.append("employment_type")
            if not user.work_mode:
                user.work_mode = User.WorkMode.HYBRID
                fields.append("work_mode")
            if not user.work_location:
                user.work_location = "Mumbai HQ"
                fields.append("work_location")
            if not user.work_shift_id:
                user.work_shift = self.default_shift
                fields.append("work_shift")
            if fields:
                user.save(update_fields=fields)
            if user.role in (User.Role.HR, User.Role.EMPLOYEE):
                self.people.append(user)

    # ── stage 7: hierarchy ────────────────────────────────────────────────────

    def seed_hierarchy(self):
        """Department head → managers → leads → everyone else."""
        assigned = 0
        by_dept = {}
        for user in self.people:
            by_dept.setdefault(user.department_id, []).append(user)

        hr_pool = [u for u in self.people if u.role == User.Role.HR] or self.people[:1]

        for _dept_id, members in by_dept.items():
            members.sort(key=lambda u: (u.job_grade.level_number if u.job_grade else 9))
            head = members[0]
            leads = [m for m in members[1:] if m.job_grade and m.job_grade.level_number <= 5]
            rest = [m for m in members[1:] if m not in leads]

            updates = []
            for lead in leads:
                if lead.reporting_manager_id != head.pk:
                    lead.reporting_manager = head
                    updates.append(lead)
            for member in rest:
                manager = RNG.choice(leads) if leads else head
                if member.reporting_manager_id != manager.pk:
                    member.reporting_manager = manager
                    updates.append(member)
            for member in members:
                hr_partner = RNG.choice(hr_pool)
                if member.assigned_hr_id != hr_partner.pk and member.pk != hr_partner.pk:
                    member.assigned_hr = hr_partner
                    if member not in updates:
                        updates.append(member)
            for member in updates:
                member.save(update_fields=["reporting_manager", "assigned_hr"])
            assigned += len(updates)
        return f"{assigned} reporting links"

    # ── stage 8: salaries ─────────────────────────────────────────────────────

    def seed_salaries(self):
        from apps.payroll.models import EmployeeSalary, SalaryStructure
        from apps.payroll.services import ensure_payroll_setup, seed_employee_components

        ensure_payroll_setup(self.org)

        structures = {}
        for code, ctc in GRADE_CTC.items():
            grade = self.grades.get(code)
            if not grade:
                continue
            structure, _ = SalaryStructure.objects.get_or_create(
                organization=self.org,
                code=_slug(code),
                defaults={"name": f"{grade.name} band", "grade": grade,
                          "monthly_ctc": Decimal(ctc), "is_active": True},
            )
            structures[code] = structure

        made = 0
        for user in self.people:
            if EmployeeSalary.objects.filter(user=user, is_active=True).exists():
                continue
            code = user.job_grade.code if user.job_grade else "EMP-ASC"
            salary = EmployeeSalary.objects.create(
                user=user,
                structure=structures.get(code),
                monthly_ctc=_jitter(GRADE_CTC.get(code, 41000)),
                effective_from=max(user.date_of_joining or self.window_start, self.today - timedelta(days=365 * 3)),
                is_active=True,
            )
            seed_employee_components(salary)
            made += 1
        return f"{len(structures)} bands, {made} salary records"

    # ── stage 9: leave balances and requests ──────────────────────────────────

    def seed_leaves(self):
        from apps.leaves.models import LeaveApproval, LeaveBalance, LeaveRequest
        from apps.leaves.services import create_approval_chain, ensure_balances_for_user

        year = self.today.year
        for user in self.people:
            ensure_balances_for_user(user, year)
            if self.window_start.year != year:
                ensure_balances_for_user(user, self.window_start.year)

        paid_types = [t for t in self.leave_types if t.is_paid] or self.leave_types
        self.leave_days = {}          # user_id -> set(date) that must read as LEAVE
        made = 0

        if LeaveRequest.objects.filter(user__organization=self.org).count() > 40:
            self._collect_leave_days()
            return "already populated"

        for user in self.people:
            if not user.date_of_joining:
                continue
            earliest = max(self.window_start, user.date_of_joining + timedelta(days=15))
            if earliest >= self.today:
                continue
            for _ in range(RNG.randint(1, 4)):
                leave_type = RNG.choice(paid_types)
                span = (self.today - earliest).days
                if span < 5:
                    continue
                start = earliest + timedelta(days=RNG.randint(0, span - 2))
                length = _weighted([(1, 40), (2, 25), (3, 18), (5, 12), (8, 5)])
                end = start + timedelta(days=length - 1)
                if self._overlaps(user, start, end):
                    continue

                # Anything in the future stays pending so the approvals inbox has work.
                if start > self.today:
                    status = LeaveRequest.Status.PENDING
                else:
                    status = _weighted([
                        (LeaveRequest.Status.APPROVED, 78),
                        (LeaveRequest.Status.REJECTED, 9),
                        (LeaveRequest.Status.PENDING, 13),
                    ])
                applied = _aware(start - timedelta(days=RNG.randint(2, 12)), time(10, 30))
                request = LeaveRequest.objects.create(
                    user=user,
                    leave_type=leave_type,
                    start_date=start,
                    end_date=end,
                    total_days=Decimal(length),
                    half_day=LeaveRequest.HalfDay.NONE,
                    reason=RNG.choice([
                        "Family function out of town.",
                        "Planned personal time off.",
                        "Medical consultation and rest.",
                        "Travelling home for the festival.",
                        "Child's school event.",
                        "Recovering from viral fever.",
                    ]),
                    status=status,
                    applied_at=applied,
                    emergency_contact=user.emergency_contact_phone or "",
                )
                create_approval_chain(request)
                if status in (LeaveRequest.Status.APPROVED, LeaveRequest.Status.REJECTED):
                    reviewer = user.reporting_manager or user.assigned_hr
                    request.reviewed_by = reviewer
                    request.reviewed_at = applied + timedelta(hours=RNG.randint(3, 40))
                    request.review_comment = (
                        "Approved. Please hand over ongoing work."
                        if status == LeaveRequest.Status.APPROVED
                        else "Cannot approve — peak delivery window."
                    )
                    request.save(update_fields=["reviewed_by", "reviewed_at", "review_comment"])
                    LeaveApproval.objects.filter(leave_request=request).update(
                        status=(LeaveApproval.StepStatus.APPROVED
                                if status == LeaveRequest.Status.APPROVED
                                else LeaveApproval.StepStatus.REJECTED),
                        acted_at=request.reviewed_at,
                    )
                if status == LeaveRequest.Status.APPROVED and start <= self.today:
                    balance = LeaveBalance.objects.filter(
                        user=user, leave_type=leave_type, year=start.year
                    ).first()
                    if balance:
                        balance.used = (balance.used or Decimal("0")) + Decimal(length)
                        balance.save(update_fields=["used"])
                made += 1

        self._collect_leave_days()
        return f"{made} requests across {len(self.people)} people"

    def _overlaps(self, user, start, end):
        from apps.leaves.models import LeaveRequest

        return LeaveRequest.objects.filter(
            user=user, start_date__lte=end, end_date__gte=start
        ).exists()

    def _collect_leave_days(self):
        """Dates that attendance must mark as LEAVE, so the two modules agree."""
        from apps.leaves.models import LeaveRequest

        self.leave_days = {}
        approved = LeaveRequest.objects.filter(
            user__organization=self.org, status=LeaveRequest.Status.APPROVED
        ).values("user_id", "start_date", "end_date")
        for row in approved:
            days = self.leave_days.setdefault(row["user_id"], set())
            cursor = row["start_date"]
            while cursor <= row["end_date"]:
                days.add(cursor)
                cursor += timedelta(days=1)

    # ── stage 10: attendance ──────────────────────────────────────────────────

    def _working_dates(self):
        from apps.attendance.work_calendar import get_org_off_weekdays
        from apps.leaves.models import Holiday

        holidays = set(
            Holiday.objects.filter(
                organization=self.org, date__gte=self.window_start, date__lte=self.today
            ).values_list("date", flat=True)
        )
        off_days = get_org_off_weekdays(self.org, self.today)
        dates, cursor = [], self.window_start
        while cursor <= self.today:
            if cursor.weekday() not in off_days and cursor not in holidays:
                dates.append(cursor)
            cursor += timedelta(days=1)
        return dates

    def seed_attendance(self):
        from apps.attendance.models import AttendanceRecord

        working_dates = self._working_dates()
        existing = set(
            AttendanceRecord.objects
            .filter(user__organization=self.org, date__gte=self.window_start)
            .values_list("user_id", "date")
        )

        batch, total = [], 0
        for user in self.people:
            if not user.date_of_joining:
                continue
            exit_date = getattr(user, "_exit_date", None)
            shift = user.work_shift or self.default_shift
            start_time = shift.start_time if shift else time(9, 0)
            grace = (shift.grace_minutes if shift else 15) or 15
            on_leave = self.leave_days.get(user.pk, set())
            # A couple of people are habitually late; most are not.
            lateness_bias = _weighted([(0.05, 55), (0.14, 30), (0.28, 15)])

            for day in working_dates:
                if day < user.date_of_joining:
                    continue
                if exit_date and day > exit_date:
                    continue
                if (user.pk, day) in existing:
                    continue

                if day in on_leave:
                    status = AttendanceRecord.Status.LEAVE
                else:
                    status = _weighted([
                        (AttendanceRecord.Status.PRESENT, 84),
                        (AttendanceRecord.Status.WFH, 7 if user.work_mode != User.WorkMode.ONSITE else 2),
                        (AttendanceRecord.Status.ABSENT, 3),
                        (AttendanceRecord.Status.HALF_DAY, 3),
                        (AttendanceRecord.Status.LEAVE, 3),
                    ])

                check_in = check_out = None
                break_minutes = 0
                note = ""
                if status in (AttendanceRecord.Status.PRESENT,
                              AttendanceRecord.Status.WFH,
                              AttendanceRecord.Status.HALF_DAY):
                    late = RNG.random() < lateness_bias
                    offset = RNG.randint(grace + 1, grace + 62) if late else RNG.randint(-25, grace - 2)
                    in_at = _aware(day, start_time) + timedelta(minutes=offset)
                    worked = 270 if status == AttendanceRecord.Status.HALF_DAY else RNG.randint(505, 585)
                    break_minutes = 30 if status == AttendanceRecord.Status.HALF_DAY else (shift.break_minutes or 60)
                    check_in = in_at
                    check_out = in_at + timedelta(minutes=worked + break_minutes)
                    if late:
                        note = RNG.choice(["Traffic delay", "Late check-in", "Client call from home"])
                elif status == AttendanceRecord.Status.ABSENT:
                    note = RNG.choice(["Unplanned absence", "No intimation", "Called in sick"])

                batch.append(AttendanceRecord(
                    user=user, date=day, status=status,
                    check_in=check_in, check_out=check_out, break_minutes=break_minutes,
                    attendance_source=_weighted([
                        ("WEB", 55), ("BIOMETRIC", 30), ("MOBILE", 10), ("MANUAL", 5),
                    ]),
                    note=note,
                ))
                if len(batch) >= 2000:
                    AttendanceRecord.objects.bulk_create(batch, ignore_conflicts=True)
                    total += len(batch)
                    batch = []
        if batch:
            AttendanceRecord.objects.bulk_create(batch, ignore_conflicts=True)
            total += len(batch)
        return f"{total} records over {len(working_dates)} working days"

    # ── stage 11: regularizations ─────────────────────────────────────────────

    def seed_regularizations(self):
        from apps.attendance.models import AttendanceRecord, AttendanceRegularizationRequest

        if AttendanceRegularizationRequest.objects.filter(user__organization=self.org).count() >= 15:
            return "already populated"

        candidates = list(
            AttendanceRecord.objects
            .filter(user__organization=self.org,
                    status__in=["ABSENT", "HALF_DAY"],
                    date__gte=self.today - timedelta(days=75))
            .select_related("user")[:400]
        )
        RNG.shuffle(candidates)
        made = 0
        for record in candidates[:22]:
            status = _weighted([("PENDING", 40), ("APPROVED", 45), ("REJECTED", 15)])
            reviewer = record.user.reporting_manager or record.user.assigned_hr
            AttendanceRegularizationRequest.objects.create(
                user=record.user,
                date=record.date,
                requested_check_in=time(9, RNG.choice([0, 5, 12, 20])),
                requested_check_out=time(18, RNG.choice([0, 10, 25, 40])),
                requested_status=AttendanceRecord.Status.PRESENT,
                reason=RNG.choice([
                    "Biometric did not register my punch.",
                    "Was at the client site all day.",
                    "Worked from the plant floor, no terminal access.",
                    "System outage during check-out.",
                ]),
                status=status,
                reviewed_by=reviewer if status != "PENDING" else None,
                reviewed_at=timezone.now() - timedelta(days=RNG.randint(1, 20)) if status != "PENDING" else None,
                review_comment="Verified with the supervisor." if status == "APPROVED" else "",
            )
            made += 1
        return f"{made} requests"

    # ── stage 12: loans, advances, reimbursements ─────────────────────────────

    def seed_recoveries(self):
        from apps.payroll.models import EmployeeDeduction, EmployeeLoan, Reimbursement

        actives = [u for u in self.people if u.is_active]
        loans = advances = reimb = 0
        scope = {"user__organization": self.org}
        if (EmployeeLoan.objects.filter(**scope).count() >= 6
                and EmployeeDeduction.objects.filter(**scope).count() >= 8
                and Reimbursement.objects.filter(**scope).count() >= 20):
            return "already populated"

        for user in RNG.sample(actives, min(8, len(actives))):
            if EmployeeLoan.objects.filter(user=user).exists():
                continue
            principal = Decimal(RNG.choice([60000, 100000, 150000, 240000]))
            tenure = RNG.choice([12, 18, 24])
            emi = (principal / tenure).quantize(Decimal("1"))
            EmployeeLoan.objects.create(
                user=user, principal=principal, interest_rate=Decimal("6.00"),
                tenure_months=tenure, emi_amount=emi,
                balance=principal - emi * RNG.randint(1, max(1, tenure // 3)),
                status=EmployeeLoan.Status.ACTIVE,
                start_date=self.today - timedelta(days=RNG.randint(60, 400)),
                approved_at=timezone.now() - timedelta(days=RNG.randint(60, 400)),
            )
            loans += 1

        for user in RNG.sample(actives, min(10, len(actives))):
            if EmployeeDeduction.objects.filter(user=user, is_active=True).exists():
                continue
            kind = _weighted([("ADVANCE", 55), ("OTHER", 30), ("NOTICE", 15)])
            amount = Decimal(RNG.choice([2000, 3500, 5000, 7500]))
            EmployeeDeduction.objects.create(
                user=user,
                deduction_type=kind,
                label={"ADVANCE": "Salary advance recovery",
                       "NOTICE": "Short notice recovery",
                       "OTHER": "Canteen & transport recovery"}[kind],
                amount=amount,
                balance=amount * RNG.randint(2, 6),
                remarks="Auto-recovered with monthly payroll.",
            )
            advances += 1

        for user in RNG.sample(actives, min(18, len(actives))):
            for _ in range(RNG.randint(1, 2)):
                Reimbursement.objects.create(
                    user=user,
                    category=_weighted([("TRAVEL", 40), ("FOOD", 20), ("INTERNET", 20),
                                        ("MEDICAL", 12), ("OTHER", 8)]),
                    amount=Decimal(RNG.choice([850, 1200, 2400, 3600, 5200])),
                    description=RNG.choice([
                        "Client visit cab fare", "Monthly broadband bill",
                        "Team lunch with vendor", "Diagnostic tests",
                        "Plant travel — fuel reimbursement",
                    ]),
                    status=_weighted([("APPROVED", 45), ("PAID", 30), ("PENDING", 20), ("REJECTED", 5)]),
                    reviewed_at=timezone.now() - timedelta(days=RNG.randint(2, 60)),
                )
                reimb += 1
        return f"{loans} loans, {advances} recoveries, {reimb} reimbursements"

    # ── stage 13: salary revisions ────────────────────────────────────────────

    def seed_revisions(self):
        from apps.payroll.models import EmployeeSalary, SalaryRevision

        made = 0
        if SalaryRevision.objects.filter(user__organization=self.org).count() >= 12:
            return "already populated"
        eligible = [
            u for u in self.people
            if u.is_active and u.date_of_joining
            and (self.today - u.date_of_joining).days > 400
        ]
        for user in RNG.sample(eligible, min(16, len(eligible))):
            if SalaryRevision.objects.filter(user=user).exists():
                continue
            salary = EmployeeSalary.objects.filter(user=user, is_active=True).first()
            if not salary:
                continue
            hike = Decimal(str(RNG.choice([6, 8, 10, 12, 15, 18])))
            previous = (salary.monthly_ctc / (1 + hike / 100)).quantize(Decimal("1"))
            SalaryRevision.objects.create(
                user=user,
                previous_ctc=previous,
                new_ctc=salary.monthly_ctc,
                effective_date=self.today - timedelta(days=RNG.randint(30, 330)),
                reason=RNG.choice([
                    "Annual appraisal cycle", "Promotion to next grade",
                    "Market correction", "Retention adjustment",
                ]),
                status=SalaryRevision.Status.APPROVED,
            )
            made += 1
        return f"{made} revisions"

    # ── stage 14: onboarding, assets, offboarding ─────────────────────────────

    def seed_lifecycle(self):
        from apps.lifecycle.models import (
            AssetAllocation, ClearanceApproval, EmployeeDocument, OffboardingWorkflow,
            OnboardingTask, OnboardingWorkflow, PolicyAcceptance,
        )
        from apps.lifecycle.services import (
            recalc_offboarding_progress, recalc_onboarding_progress,
            start_offboarding, start_onboarding,
        )

        admin = self._admin()
        onboarded = offboarded = assets = 0

        # Onboarding for anyone who joined inside the history window.
        recent = [
            u for u in self.people
            if u.date_of_joining and u.date_of_joining >= self.window_start
        ]
        for user in recent:
            if OnboardingWorkflow.objects.filter(organization=self.org, user=user).exists():
                continue
            workflow = start_onboarding(
                organization=self.org, user=user,
                joining_date=user.date_of_joining, created_by=admin,
                branch=user.work_location,
            )
            age_days = (self.today - user.date_of_joining).days
            # The longer someone has been here, the further along their checklist is.
            completion = 1.0 if age_days > 60 else max(0.2, age_days / 60)
            tasks = list(OnboardingTask.objects.filter(onboarding=workflow))
            done = int(len(tasks) * completion)
            for task in tasks[:done]:
                task.status = OnboardingTask.Status.DONE
                task.completed_at = _aware(user.date_of_joining + timedelta(days=RNG.randint(1, 8)), time(15, 0))
                task.assigned_to = user.assigned_hr or admin
                task.save(update_fields=["status", "completed_at", "assigned_to"])
            for task in tasks[done:]:
                task.status = OnboardingTask.Status.IN_PROGRESS
                task.assigned_to = user.assigned_hr or admin
                task.save(update_fields=["status", "assigned_to"])
            for doc in EmployeeDocument.objects.filter(onboarding=workflow):
                doc.verify_status = (
                    EmployeeDocument.VerifyStatus.VERIFIED if completion >= 1.0
                    else _weighted([("VERIFIED", 50), ("PENDING", 35), ("MISSING", 15)])
                )
                doc.verified_by = admin if doc.verify_status == "VERIFIED" else None
                doc.save(update_fields=["verify_status", "verified_by"])
            PolicyAcceptance.objects.filter(onboarding=workflow).update(
                accepted=completion >= 1.0, accepted_at=timezone.now() if completion >= 1.0 else None,
            )
            if completion >= 1.0:
                workflow.status = OnboardingWorkflow.Status.COMPLETED
                workflow.completed_at = _aware(user.date_of_joining + timedelta(days=12), time(17, 0))
                workflow.welcome_sent = True
                workflow.save(update_fields=["status", "completed_at", "welcome_sent"])
            recalc_onboarding_progress(workflow)
            onboarded += 1

        # Assets for everyone active — laptops, ID cards, access.
        for user in self.people:
            if AssetAllocation.objects.filter(user=user).exists():
                continue
            workflow = OnboardingWorkflow.objects.filter(organization=self.org, user=user).first()
            for asset_type, description in [
                ("LAPTOP", RNG.choice(["Dell Latitude 5450", "Lenovo ThinkPad T14", "HP EliteBook 840"])),
                ("ID_CARD", "Photo ID with plant access"),
                ("EMAIL", f"{user.username}@{EMAIL_DOMAIN}"),
                ("SYSTEM_ACCESS", "SAP + HRMS access"),
            ]:
                AssetAllocation.objects.create(
                    organization=self.org, user=user, onboarding=workflow,
                    asset_type=asset_type,
                    serial_number=f"TM-{asset_type[:3]}-{RNG.randint(10000, 99999)}",
                    description=description,
                    status=AssetAllocation.Status.ALLOCATED,
                )
                assets += 1

        # Offboarding for the people picked as leavers in the people stage.
        for user in self.leavers:
            if OffboardingWorkflow.objects.filter(organization=self.org, user=user).exists():
                continue
            workflow = start_offboarding(
                organization=self.org, user=user,
                last_working_day=user._exit_date,
                reason=user._exit_reason,
                created_by=admin,
                notes="Resignation accepted; knowledge transfer in progress.",
            )
            if user._exit_date < self.today - timedelta(days=5):
                workflow.status = OffboardingWorkflow.Status.COMPLETED
                workflow.completed_at = _aware(user._exit_date, time(18, 0))
                workflow.save(update_fields=["status", "completed_at"])
                workflow.clearances.update(
                    status=ClearanceApproval.Status.APPROVED,
                    approved_by=admin,
                    note="Cleared during exit formalities.",
                )
                AssetAllocation.objects.filter(user=user).update(
                    status=AssetAllocation.Status.RETURNED, returned_at=timezone.now(),
                    offboarding=workflow,
                )
            recalc_offboarding_progress(workflow)
            offboarded += 1

        return f"{onboarded} onboardings, {assets} assets, {offboarded} exits"

    # ── stage 15: payroll ─────────────────────────────────────────────────────

    def seed_payroll(self):
        from apps.payroll.models import PayrollApproval, PayrollRun, Payslip
        from apps.payroll.services import (
            approve_payroll_run, generate_payslip_numbers, get_or_create_payroll_run,
            lock_payroll_run, mark_payroll_paid, process_payroll_run, record_payroll_action,
        )

        admin = self._admin()
        exits = {u.pk: getattr(u, "_exit_date", None) for u in self.people}
        joins = {u.pk: u.date_of_joining for u in self.people}

        processed = 0
        months = list(_month_iter(self.window_start, self.today))
        for index, (year, month) in enumerate(months):
            run = get_or_create_payroll_run(self.org, year, month)
            if run.status == PayrollRun.Status.LOCKED:
                continue
            process_payroll_run(run, admin)

            # process_payroll_run pays every active employee; drop the payslips for
            # months a person had not joined yet or had already left.
            month_end = (date(year, month, 28) + timedelta(days=6)).replace(day=1) - timedelta(days=1)
            month_start = date(year, month, 1)
            stale = []
            for slip in Payslip.objects.filter(payroll_run=run).only("id", "user_id"):
                joined = joins.get(slip.user_id)
                left = exits.get(slip.user_id)
                if (joined and joined > month_end) or (left and left < month_start):
                    stale.append(slip.pk)
            if stale:
                Payslip.objects.filter(pk__in=stale).delete()
                self._recalc_run(run)

            generate_payslip_numbers(run)

            # Older cycles are closed out; the two most recent stay open so the
            # approval and payment screens have something live to act on.
            remaining = len(months) - index
            if remaining > 2:
                approve_payroll_run(run, admin, "Approved by Finance.")
                mark_payroll_paid(run)
                Payslip.objects.filter(payroll_run=run).update(
                    payment_date=month_end + timedelta(days=1),
                    bank_reference=f"NEFT{year}{month:02d}{RNG.randint(1000, 9999)}",
                )
                if remaining > 3:
                    lock_payroll_run(run)
            elif remaining == 2:
                approve_payroll_run(run, admin, "Approved, payout scheduled.")
            record_payroll_action(
                self.org, admin, "PROCESSED",
                f"Demo seed processed payroll for {month:02d}/{year}",
                period=f"{month:02d}/{year}",
            )
            processed += 1
        return f"{processed} monthly runs"

    def _recalc_run(self, run):
        from django.db.models import Count, Sum
        from apps.payroll.models import Payslip

        agg = Payslip.objects.filter(payroll_run=run).aggregate(
            gross=Sum("gross_salary"), net=Sum("net_salary"),
            ded=Sum("total_deductions"), bonus=Sum("bonus"),
            reimb=Sum("reimbursements"), count=Count("id"),
        )
        run.total_gross = agg["gross"] or Decimal("0")
        run.total_net = agg["net"] or Decimal("0")
        run.total_deductions = agg["ded"] or Decimal("0")
        run.total_bonus = agg["bonus"] or Decimal("0")
        run.total_reimbursements = agg["reimb"] or Decimal("0")
        run.employee_count = agg["count"] or 0
        run.save(update_fields=[
            "total_gross", "total_net", "total_deductions",
            "total_bonus", "total_reimbursements", "employee_count",
        ])

    # ── stage 16: close out the exits ─────────────────────────────────────────

    def finalize_exits(self):
        """Deactivate people whose last working day has passed.

        Runs after payroll so their historical payslips still exist — which is
        exactly how a real system behaves.
        """
        closed = 0
        for user in self.leavers:
            last_day = getattr(user, "_exit_date", None)
            if not last_day or last_day > self.today:
                continue
            user.is_active = False
            user.employment_status = (
                User.EmploymentStatus.TERMINATED
                if user._exit_reason == "TERMINATION"
                else User.EmploymentStatus.INACTIVE
            )
            user.archived_at = _aware(last_day, time(18, 0))
            user.save(update_fields=["is_active", "employment_status", "archived_at"])
            closed += 1
        return f"{closed} employees deactivated"

    # ── stage 17: notifications ───────────────────────────────────────────────

    def seed_notifications(self):
        from apps.dashboard.notification_service import send_notification

        admin = self._admin()
        hr_users = [u for u in self.people if u.role == User.Role.HR][:3]
        made = 0
        messages = [
            ("demo-payroll", "bell", "Payroll processed",
             "Last month's payroll has been processed and paid.", "/payroll/"),
            ("demo-leave-approvals", "palmtree", "Leave approvals pending",
             "You have leave requests waiting for review.", "/leaves/"),
            ("demo-regularizations", "clock", "Attendance regularizations",
             "New regularization requests need a decision.", "/dashboard/attendance/corrections/"),
            ("demo-joiners", "user-plus", "New joiners this month",
             "Onboarding checklists are in progress.", "/lifecycle/"),
        ]
        for user in [admin, *hr_users]:
            if not user:
                continue
            for source_key, icon, title, message, url in messages:
                send_notification(user, source_key=source_key, icon=icon,
                                  title=title, message=message, url=url)
                made += 1
        actives = [u for u in self.people if u.is_active]
        for user in RNG.sample(actives, min(12, len(actives))):
            send_notification(
                user,
                source_key="demo-payslip",
                icon="receipt",
                title="Payslip available",
                message="Your latest payslip is ready to download.",
                url="/payroll/payslips/",
            )
            made += 1
        return f"{made} notifications"

    # ── stage 18: automation rules ────────────────────────────────────────────

    def seed_rules(self):
        try:
            from apps.ruleengine.models import Rule
        except Exception:
            return "rule engine unavailable"

        presets = [
            {
                "name": "Flag repeated late arrivals",
                "description": "Notify HR when an employee is late three times in a month.",
                "trigger_event": "ATTENDANCE_MARKED",
            },
            {
                "name": "Auto-approve single-day casual leave",
                "description": "Casual leave of one day from confirmed employees is approved automatically.",
                "trigger_event": "LEAVE_REQUESTED",
            },
            {
                "name": "Escalate unapproved leave after 48 hours",
                "description": "Escalate to the assigned HR partner when a request sits unactioned.",
                "trigger_event": "LEAVE_REQUESTED",
            },
        ]
        made = 0
        for order, preset in enumerate(presets):
            if Rule.objects.filter(organization=self.org, name=preset["name"]).exists():
                continue
            try:
                Rule.objects.create(
                    organization=self.org,
                    name=preset["name"],
                    description=preset["description"],
                    trigger_event=preset["trigger_event"],
                    conditions=[],
                    actions=[],
                    priority=order + 1,
                    status="DRAFT",
                    is_test_mode=True,
                )
                made += 1
            except Exception:
                return "skipped (schema mismatch)"
        return f"{made} sample rules"

    # ── stage 19: HR letter templates & generated documents ──────────────────

    def seed_documents(self):
        try:
            from apps.documents.models import DocumentTemplate, GeneratedDocument
            from apps.documents.services import create_generated_document, get_default_body
        except Exception:
            return "document generator unavailable"

        admin = self._admin()
        made = 0
        for template_type, label in DocumentTemplate.TemplateType.choices:
            if DocumentTemplate.objects.filter(
                organization=self.org, template_type=template_type
            ).exists():
                continue
            DocumentTemplate.objects.create(
                organization=self.org,
                template_type=template_type,
                name=f"{self.org.name} — {label}",
                description=f"Standard {label.lower()} issued by HR.",
                body=get_default_body(template_type),
                created_by=admin,
                updated_by=admin,
            )
            made += 1

        # A few real PDFs so the generated-documents list is not empty.
        generated = 0
        if GeneratedDocument.objects.filter(organization=self.org).count() < 5:
            templates = {
                t.template_type: t
                for t in DocumentTemplate.objects.filter(organization=self.org, is_active=True)
            }
            recent = [u for u in self.people
                      if u.is_active and u.date_of_joining and u.date_of_joining >= self.window_start]
            leavers = [u for u in self.leavers if getattr(u, "_exit_date", None)]
            plan = [(templates.get("OFFER"), u) for u in recent[:2]]
            plan += [(templates.get("APPOINTMENT"), u) for u in recent[:1]]
            plan += [(templates.get("RELIEVING"), u) for u in leavers[:2]]
            plan += [(templates.get("EXPERIENCE"), u) for u in leavers[:1]]
            plan += [(templates.get("SALARY_CERT"), u) for u in self.people[:1]]
            for template, employee in plan:
                if not template or not employee:
                    continue
                try:
                    create_generated_document(template, employee, admin, {})
                    generated += 1
                except Exception:
                    continue
        return f"{made} templates, {generated} documents"

    # ── helpers & summary ─────────────────────────────────────────────────────

    def _admin(self):
        return (
            User.objects.filter(organization=self.org, role=User.Role.ADMIN, is_active=True)
            .order_by("date_joined").first()
        )

    def _summary(self):
        from apps.attendance.models import AttendanceRecord
        from apps.leaves.models import LeaveRequest
        from apps.payroll.models import PayrollRun, Payslip

        active = User.objects.filter(
            organization=self.org, role__in=[User.Role.HR, User.Role.EMPLOYEE], is_active=True
        ).count()
        self.stdout.write("")
        self._say(f"{self.org.name} is now populated:")
        self.stdout.write(f"    active workforce   {active}")
        self.stdout.write(f"    departments        {Department.objects.filter(organization=self.org).count()}")
        self.stdout.write(f"    attendance records {AttendanceRecord.objects.filter(user__organization=self.org).count()}")
        self.stdout.write(f"    leave requests     {LeaveRequest.objects.filter(user__organization=self.org).count()}")
        self.stdout.write(f"    payroll runs       {PayrollRun.objects.filter(organization=self.org).count()}")
        self.stdout.write(f"    payslips           {Payslip.objects.filter(payroll_run__organization=self.org).count()}")
        self.stdout.write("")
        self.stdout.write("  Demo logins (username / password):")
        self.stdout.write(f"    password for every seeded account: {DEMO_PASSWORD}")
        for label, role in (("Admin", User.Role.ADMIN), ("HR", User.Role.HR), ("Employee", User.Role.EMPLOYEE)):
            sample = User.objects.filter(
                organization=self.org, role=role, is_active=True,
                username__startswith=USERNAME_PREFIX,
            ).order_by("username")[:3]
            for user in sample:
                self.stdout.write(f"    {label:9s} {user.username:26s} {user.display_name}")
