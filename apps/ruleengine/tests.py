from datetime import date, timedelta
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.attendance.models import AttendanceRecord, WorkShift
from apps.leaves.models import LeaveBalance, LeaveRequest, LeaveType
from apps.leaves.services import get_balance
from apps.organizations.models import Department, Organization

from .engine import evaluate_rules, evaluate_single_rule, rule_matches
from .models import Rule, RuleAuditLog, RuleExecutionLog
from .registry import OPERATORS


def _make_org(name: str, code: str, **flags) -> Organization:
    defaults = dict(
        name=name,
        organization_code=code,
        code=code.lower(),
        schema_name=code.lower(),
        leave_approval_require_manager=True,
        leave_approval_require_hr=False,
        leave_approval_require_admin=False,
    )
    defaults.update(flags)
    return Organization.objects.create(**defaults)


def _make_user(org, email, role, **extra) -> User:
    return User.objects.create_user(
        email=email,
        password="Passw0rd!",
        username=email.replace("@", "-").replace(".", "-"),
        first_name=email.split("@")[0].title(),
        role=role,
        organization=org,
        **extra,
    )


def _make_leave_type(org, name="Casual", code="casual", **extra) -> LeaveType:
    defaults = dict(annual_quota=Decimal("12"), is_paid=True)
    defaults.update(extra)
    return LeaveType.objects.create(organization=org, name=name, code=code, **defaults)


class OperatorTests(TestCase):
    def test_equals_and_not_equals(self):
        self.assertTrue(OPERATORS["EQUALS"]("IT", "IT"))
        self.assertFalse(OPERATORS["EQUALS"]("IT", "HR"))
        self.assertTrue(OPERATORS["NOT_EQUALS"]("IT", "HR"))

    def test_greater_and_less(self):
        self.assertTrue(OPERATORS["GREATER"](5, 3))
        self.assertFalse(OPERATORS["GREATER"](2, 3))
        self.assertTrue(OPERATORS["LESS"](2, 3))

    def test_contains(self):
        self.assertTrue(OPERATORS["CONTAINS"]("Information Technology", "tech"))
        self.assertFalse(OPERATORS["CONTAINS"]("Sales", "tech"))

    def test_between(self):
        self.assertTrue(OPERATORS["BETWEEN"](5, 1, 10))
        self.assertFalse(OPERATORS["BETWEEN"](15, 1, 10))


class RuleMatchingTests(TestCase):
    def test_and_within_group(self):
        rule = Rule(conditions=[[
            {"field": "employee.department", "operator": "EQUALS", "value": "IT"},
            {"field": "employee.experience_years", "operator": "GREATER", "value": 5},
        ]])
        facts = {"employee.department": "IT", "employee.experience_years": 6}
        self.assertTrue(rule_matches(rule, facts))

        facts_fail = {"employee.department": "IT", "employee.experience_years": 2}
        self.assertFalse(rule_matches(rule, facts_fail))

    def test_or_across_groups(self):
        rule = Rule(conditions=[
            [{"field": "employee.department", "operator": "EQUALS", "value": "IT"}],
            [{"field": "employee.department", "operator": "EQUALS", "value": "Sales"}],
        ])
        self.assertTrue(rule_matches(rule, {"employee.department": "Sales"}))
        self.assertFalse(rule_matches(rule, {"employee.department": "HR"}))

    def test_missing_fact_never_matches(self):
        rule = Rule(conditions=[[{"field": "employee.department", "operator": "EQUALS", "value": "IT"}]])
        self.assertFalse(rule_matches(rule, {"employee.department": None}))


class RuleEngineTestBase(TestCase):
    def setUp(self):
        self.org = _make_org("Acme", "RUA")
        self.admin = _make_user(self.org, "admin@rua.com", User.Role.ADMIN)
        self.hr = _make_user(self.org, "hr@rua.com", User.Role.HR, assigned_hr=None)
        self.it_dept = Department.objects.create(organization=self.org, name="IT", code="it")
        self.casual = _make_leave_type(self.org)


class DepartmentExperienceRuleTests(RuleEngineTestBase):
    """Spec example 2: IF Department = IT AND Experience > 5 THEN Add 2 Casual Leaves."""

    def setUp(self):
        super().setUp()
        self.employee = _make_user(
            self.org, "emp@rua.com", User.Role.EMPLOYEE,
            department=self.it_dept,
            date_of_joining=date.today() - timedelta(days=365 * 6),
            assigned_hr=self.hr,
        )
        self.rule = Rule.objects.create(
            organization=self.org,
            name="IT senior leave grant",
            trigger_event=Rule.Trigger.LEAVE_REQUESTED,
            status=Rule.Status.ACTIVE,
            priority=10,
            conditions=[[
                {"field": "employee.department", "operator": "EQUALS", "value": "IT"},
                {"field": "employee.experience_years", "operator": "GREATER", "value": 5},
            ]],
            actions=[{"type": "ADD_LEAVE", "params": {"leave_type_code": "casual", "days": 2}}],
        )

    def _make_leave_request(self):
        return LeaveRequest.objects.create(
            user=self.employee,
            leave_type=self.casual,
            start_date=date.today(),
            end_date=date.today(),
            total_days=Decimal("1"),
            reason="test",
        )

    def test_matches_and_adds_leave(self):
        req = self._make_leave_request()
        before = get_balance(self.employee, self.casual).adjusted

        logs = evaluate_rules(self.org, Rule.Trigger.LEAVE_REQUESTED, subject=req)

        self.assertEqual(len(logs), 1)
        self.assertTrue(logs[0].matched)
        self.assertEqual(logs[0].actions_result[0]["status"], "success")
        bal = get_balance(self.employee, self.casual)
        self.assertEqual(bal.adjusted, before + 2)

    def test_no_match_for_junior_employee(self):
        self.employee.date_of_joining = date.today() - timedelta(days=365)
        self.employee.save(update_fields=["date_of_joining"])
        req = self._make_leave_request()

        logs = evaluate_rules(self.org, Rule.Trigger.LEAVE_REQUESTED, subject=req)

        self.assertEqual(len(logs), 1)
        self.assertFalse(logs[0].matched)
        bal = get_balance(self.employee, self.casual)
        self.assertEqual(bal.adjusted, Decimal("0"))

    def test_disabled_rule_is_skipped(self):
        self.rule.status = Rule.Status.DISABLED
        self.rule.save(update_fields=["status"])
        req = self._make_leave_request()

        logs = evaluate_rules(self.org, Rule.Trigger.LEAVE_REQUESTED, subject=req)

        self.assertEqual(logs, [])

    def test_dry_run_makes_no_mutation(self):
        req = self._make_leave_request()
        logs = evaluate_rules(self.org, Rule.Trigger.LEAVE_REQUESTED, subject=req, dry_run=True)

        self.assertTrue(logs[0].matched)
        self.assertTrue(logs[0].is_test_run)
        self.assertEqual(logs[0].actions_result[0]["status"], "simulated")
        bal = get_balance(self.employee, self.casual)
        self.assertEqual(bal.adjusted, Decimal("0"))

    def test_evaluate_single_rule_works_for_draft(self):
        self.rule.status = Rule.Status.DRAFT
        self.rule.save(update_fields=["status"])
        req = self._make_leave_request()

        log = evaluate_single_rule(self.rule, subject=req, dry_run=True)

        self.assertTrue(log.matched)
        self.assertTrue(log.is_test_run)

    def test_priority_ordering(self):
        second = Rule.objects.create(
            organization=self.org,
            name="Low priority notice",
            trigger_event=Rule.Trigger.LEAVE_REQUESTED,
            status=Rule.Status.ACTIVE,
            priority=999,
            conditions=[[{"field": "employee.department", "operator": "EQUALS", "value": "IT"}]],
            actions=[],
        )
        req = self._make_leave_request()
        logs = evaluate_rules(self.org, Rule.Trigger.LEAVE_REQUESTED, subject=req)
        self.assertEqual(logs[0].rule_id, self.rule.pk)
        self.assertEqual(logs[1].rule_id, second.pk)

    def test_failing_action_does_not_block_siblings(self):
        self.rule.actions = [
            {"type": "BOGUS_ACTION", "params": {}},
            {"type": "ADD_LEAVE", "params": {"leave_type_code": "casual", "days": 2}},
        ]
        self.rule.save(update_fields=["actions"])
        req = self._make_leave_request()

        logs = evaluate_rules(self.org, Rule.Trigger.LEAVE_REQUESTED, subject=req)

        results = logs[0].actions_result
        self.assertEqual(results[0]["status"], "failed")
        self.assertEqual(results[1]["status"], "success")
        bal = get_balance(self.employee, self.casual)
        self.assertEqual(bal.adjusted, Decimal("2"))

    def test_depth_guard_stops_recursion(self):
        req = self._make_leave_request()
        logs = evaluate_rules(self.org, Rule.Trigger.LEAVE_REQUESTED, subject=req, extra={"_depth": 3})
        self.assertEqual(logs, [])

    def test_submit_leave_request_triggers_rule(self):
        from apps.leaves.services import submit_leave_request

        # Pick a weekday so it counts as a working day regardless of today's weekday.
        next_monday = date.today() + timedelta(days=(7 - date.today().weekday()) % 7 or 7)
        req, message = submit_leave_request(
            user=self.employee,
            leave_type=self.casual,
            start_date=next_monday,
            end_date=next_monday,
            half_day=LeaveRequest.HalfDay.NONE,
            reason="Vacation",
        )
        self.assertIsNotNone(req)
        bal = get_balance(self.employee, self.casual)
        self.assertEqual(bal.adjusted, Decimal("2"))
        self.assertTrue(RuleExecutionLog.objects.filter(organization=self.org, rule=self.rule, matched=True).exists())


class LateCountDeductionRuleTests(RuleEngineTestBase):
    """Spec example 1: IF Late Count > 3 THEN Deduct Half Day."""

    def setUp(self):
        super().setUp()
        self.shift = WorkShift.objects.create(
            organization=self.org,
            name="General",
            shift_code="GEN",
            is_default=True,
        )
        self.employee = _make_user(self.org, "late@rua.com", User.Role.EMPLOYEE, work_shift=self.shift)
        self.rule = Rule.objects.create(
            organization=self.org,
            name="Late count deduction",
            trigger_event=Rule.Trigger.ATTENDANCE_MARKED,
            status=Rule.Status.ACTIVE,
            conditions=[[{"field": "attendance.late_count_30d", "operator": "GREATER", "value": 3}]],
            actions=[{"type": "DEDUCT_LEAVE", "params": {"leave_type_code": "casual", "days": 0.5}}],
        )

    def _mark_late(self, days_ago: int) -> AttendanceRecord:
        on_date = timezone.localdate() - timedelta(days=days_ago)
        check_in = timezone.make_aware(
            timezone.datetime.combine(on_date, self.shift.start_time) + timedelta(hours=2)
        )
        return AttendanceRecord.objects.create(
            user=self.employee, date=on_date, status=AttendanceRecord.Status.PRESENT, check_in=check_in,
        )

    def test_fourth_late_mark_triggers_deduction(self):
        get_balance(self.employee, self.casual)  # ensure balance row exists at zero first
        for i in range(1, 4):
            self._mark_late(i)
        record = self._mark_late(4)  # 4th late record -> attendance.late_count_30d becomes 4 (> 3)

        self.assertTrue(
            RuleExecutionLog.objects.filter(organization=self.org, rule=self.rule, matched=True).exists()
        )
        bal = get_balance(self.employee, self.casual)
        self.assertEqual(bal.adjusted, Decimal("-0.5"))
        self.assertIsNotNone(record.pk)


class RuleAuditAndApiTests(TestCase):
    def setUp(self):
        self.org = _make_org("Acme", "RUB")
        self.admin = _make_user(self.org, "admin@rub.com", User.Role.ADMIN)
        self.employee = _make_user(self.org, "emp@rub.com", User.Role.EMPLOYEE)

    def test_create_rule_via_api_records_audit(self):
        self.client.force_login(self.admin)
        payload = {
            "name": "Test rule",
            "description": "",
            "trigger_event": Rule.Trigger.MANUAL,
            "status": Rule.Status.DRAFT,
            "priority": 100,
            "conditions": [],
            "actions": [],
            "is_test_mode": False,
        }
        resp = self.client.post(
            reverse("ruleengine_api:rules"), data=payload, content_type="application/json",
        )
        self.assertEqual(resp.status_code, 201)
        self.assertTrue(Rule.objects.filter(organization=self.org, name="Test rule").exists())
        self.assertTrue(RuleAuditLog.objects.filter(organization=self.org, action=RuleAuditLog.Action.CREATED).exists())

    def test_employee_forbidden_from_api(self):
        self.client.force_login(self.employee)
        resp = self.client.get(reverse("ruleengine_api:rules"))
        self.assertEqual(resp.status_code, 403)

    def test_status_toggle_records_audit(self):
        rule = Rule.objects.create(
            organization=self.org, name="Toggle me", trigger_event=Rule.Trigger.MANUAL, status=Rule.Status.DRAFT,
        )
        self.client.force_login(self.admin)
        resp = self.client.post(
            reverse("ruleengine_api:rule_status", args=[rule.pk]),
            data={"status": "ACTIVE"},
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 200)
        rule.refresh_from_db()
        self.assertEqual(rule.status, Rule.Status.ACTIVE)
        self.assertTrue(RuleAuditLog.objects.filter(organization=self.org, action=RuleAuditLog.Action.ENABLED).exists())


class RuleEnginePageRenderTests(TestCase):
    def setUp(self):
        self.org = _make_org("Acme", "RUC")
        self.admin = _make_user(self.org, "admin@ruc.com", User.Role.ADMIN)
        self.rule = Rule.objects.create(
            organization=self.org, name="Sample", trigger_event=Rule.Trigger.MANUAL, status=Rule.Status.DRAFT,
        )

    def test_management_page_renders(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("ruleengine:management"))
        self.assertEqual(resp.status_code, 200)

    def test_builder_create_page_renders(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("ruleengine:builder_create"))
        self.assertEqual(resp.status_code, 200)

    def test_builder_edit_page_renders(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("ruleengine:builder_edit", args=[self.rule.pk]))
        self.assertEqual(resp.status_code, 200)

    def test_test_page_renders(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("ruleengine:test"))
        self.assertEqual(resp.status_code, 200)

    def test_logs_page_renders(self):
        self.client.force_login(self.admin)
        resp = self.client.get(reverse("ruleengine:logs"))
        self.assertEqual(resp.status_code, 200)

    def test_employee_cannot_access(self):
        employee = _make_user(self.org, "emp@ruc.com", User.Role.EMPLOYEE)
        self.client.force_login(employee)
        resp = self.client.get(reverse("ruleengine:management"))
        self.assertEqual(resp.status_code, 302)
