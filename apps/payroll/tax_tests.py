"""Tests for the TDS engine, investment declarations and Form 16.

This code decides how much money is withheld from salaries and produces a legal
certificate, so the cases below pin the arithmetic to hand-computed values rather
than to whatever the implementation happens to return.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from apps.accounts.models import User
from apps.organizations.models import Organization

from . import form16 as f16
from . import tax_engine as te
from .models import (
    EmployeeSalary,
    Form16Certificate,
    PayrollRun,
    Payslip,
    PayslipLine,
    SalaryComponent,
    TaxConfiguration,
    TaxDeclaration,
    TaxRegime,
    TaxSlab,
)
from .services import ensure_payroll_setup, ensure_tax_configuration

FY = date(2026, 4, 1)


def _make_org(name, code) -> Organization:
    return Organization.objects.create(
        name=name, organization_code=code, code=code.lower(), schema_name=code.lower()
    )


def _make_user(org, email, role=User.Role.EMPLOYEE, **extra) -> User:
    return User.objects.create_user(
        email=email,
        password="Passw0rd!",
        username=email.replace("@", "-").replace(".", "-"),
        role=role,
        organization=org,
        **extra,
    )


class SlabArithmeticTests(TestCase):
    """Slab tax must be progressive: each band taxes only its own slice."""

    def setUp(self):
        self.org = _make_org("SlabCo", "SLB")
        ensure_tax_configuration(self.org)
        self.new = te.get_tax_config(self.org, FY, "NEW")
        self.old = te.get_tax_config(self.org, FY, "OLD")

    def test_new_regime_bands(self):
        # 0-3L nil, 3-7L @5%, 7-10L @10%, 10-12L @15%, 12-15L @20%, 15L+ @30%.
        cases = [
            ("300000", "0"),
            ("700000", "20000"),        # 5% of 4L
            ("1000000", "50000"),       # + 10% of 3L
            ("1200000", "80000"),       # + 15% of 2L
            ("1500000", "140000"),      # + 20% of 3L
            ("2000000", "290000"),      # + 30% of 5L
        ]
        for taxable, expected in cases:
            with self.subTest(taxable=taxable):
                self.assertEqual(
                    te.slab_tax(Decimal(taxable), self.new), Decimal(expected).quantize(Decimal("0.01"))
                )

    def test_old_regime_bands(self):
        cases = [("250000", "0"), ("500000", "12500"), ("1000000", "112500"), ("1500000", "262500")]
        for taxable, expected in cases:
            with self.subTest(taxable=taxable):
                self.assertEqual(
                    te.slab_tax(Decimal(taxable), self.old), Decimal(expected).quantize(Decimal("0.01"))
                )

    def test_bands_are_contiguous(self):
        """A gap between bands would leave income untaxed at every boundary."""
        slabs = sorted(self.new.slabs.all(), key=lambda s: s.min_income)
        for lower, upper in zip(slabs, slabs[1:]):
            self.assertEqual(
                lower.max_income,
                upper.min_income,
                f"gap between {lower.max_income} and {upper.min_income}",
            )

    def test_zero_and_negative_income_pay_nothing(self):
        self.assertEqual(te.slab_tax(Decimal("0"), self.new), Decimal("0"))
        self.assertEqual(te.slab_tax(Decimal("-5000"), self.new), Decimal("0"))

    def test_no_config_yields_no_tax_rather_than_crashing(self):
        self.assertEqual(te.slab_tax(Decimal("900000"), None), Decimal("0"))

    def test_slab_tax_from_matches_slab_tax(self):
        slabs = list(self.new.slabs.all())
        for taxable in ("450000", "1234567", "5000000"):
            with self.subTest(taxable=taxable):
                self.assertEqual(
                    te.slab_tax_from(Decimal(taxable), slabs),
                    te.slab_tax(Decimal(taxable), self.new),
                )


class HraExemptionTests(TestCase):
    """HRA exemption is the least of three statutory tests."""

    def test_metro_uses_fifty_percent_of_basic(self):
        # min(HRA 240000, rent 300000 - 10% of 480000 = 252000, 50% of 480000 = 240000)
        self.assertEqual(
            te.hra_exemption(Decimal("480000"), Decimal("240000"), Decimal("300000"), True),
            Decimal("240000.00"),
        )

    def test_non_metro_uses_forty_percent_of_basic(self):
        self.assertEqual(
            te.hra_exemption(Decimal("480000"), Decimal("240000"), Decimal("300000"), False),
            Decimal("192000.00"),
        )

    def test_rent_over_ten_percent_can_be_the_binding_test(self):
        # Low rent → rent - 10% of basic is smallest.
        self.assertEqual(
            te.hra_exemption(Decimal("480000"), Decimal("240000"), Decimal("100000"), True),
            Decimal("52000.00"),
        )

    def test_no_rent_means_no_exemption(self):
        self.assertEqual(te.hra_exemption(Decimal("480000"), Decimal("240000"), Decimal("0"), True), Decimal("0"))

    def test_no_hra_component_means_no_exemption(self):
        self.assertEqual(te.hra_exemption(Decimal("480000"), Decimal("0"), Decimal("300000"), True), Decimal("0"))

    def test_exemption_never_negative(self):
        self.assertGreaterEqual(
            te.hra_exemption(Decimal("900000"), Decimal("10000"), Decimal("1000"), False), Decimal("0")
        )


class FinancialYearHelperTests(TestCase):
    def test_fy_starts_in_april(self):
        self.assertEqual(te.financial_year_start_for(date(2026, 4, 1)), date(2026, 4, 1))
        self.assertEqual(te.financial_year_start_for(date(2026, 12, 31)), date(2026, 4, 1))

    def test_jan_to_mar_belong_to_the_previous_fy(self):
        self.assertEqual(te.financial_year_start_for(date(2027, 3, 31)), date(2026, 4, 1))
        self.assertEqual(te.financial_year_start_for(date(2027, 1, 1)), date(2026, 4, 1))

    def test_months_remaining_counts_the_current_month(self):
        self.assertEqual(te.months_remaining_in_fy(2026, 4), 12)
        self.assertEqual(te.months_remaining_in_fy(2026, 9), 7)
        self.assertEqual(te.months_remaining_in_fy(2027, 1), 3)
        self.assertEqual(te.months_remaining_in_fy(2027, 3), 1)


class DeclarationEffectTests(TestCase):
    """Only an approved declaration may reduce taxable income."""

    def setUp(self):
        self.org = _make_org("DeclCo", "DEC")
        ensure_tax_configuration(self.org)
        self.emp = _make_user(self.org, "decl@x.com")

    def _declare(self, status, **kwargs):
        defaults = dict(
            organization=self.org,
            user=self.emp,
            financial_year_start=FY,
            regime=TaxRegime.OLD,
            section_80c=Decimal("150000"),
            status=status,
        )
        defaults.update(kwargs)
        return TaxDeclaration.objects.create(**defaults)

    def _tds(self):
        return te.monthly_tds_for(
            self.emp,
            monthly_gross=Decimal("100000"),
            monthly_basic=Decimal("40000"),
            monthly_hra=Decimal("20000"),
            year=2026,
            month=4,
        )

    def test_draft_declaration_does_not_reduce_tax(self):
        self._declare(TaxDeclaration.Status.DRAFT)
        self.assertEqual(self._tds().breakdown.get("section_80c"), None)

    def test_submitted_declaration_does_not_reduce_tax(self):
        """Unverified claims must not cut TDS before HR has seen the proof."""
        self._declare(TaxDeclaration.Status.SUBMITTED)
        self.assertEqual(self._tds().breakdown.get("section_80c"), None)

    def test_rejected_declaration_does_not_reduce_tax(self):
        self._declare(TaxDeclaration.Status.REJECTED)
        self.assertEqual(self._tds().breakdown.get("section_80c"), None)

    def test_approved_declaration_reduces_tax(self):
        self._declare(TaxDeclaration.Status.APPROVED)
        self.assertEqual(self._tds().breakdown.get("section_80c"), 150000.0)

    def test_approval_lowers_the_monthly_figure(self):
        d = self._declare(TaxDeclaration.Status.SUBMITTED)
        before = self._tds().monthly_tds
        d.status = TaxDeclaration.Status.APPROVED
        d.save()
        self.assertLess(self._tds().monthly_tds, before)

    def test_statutory_caps_are_enforced_by_the_engine(self):
        """Employees may over-declare; the engine clamps to the legal maximum."""
        self._declare(
            TaxDeclaration.Status.APPROVED,
            section_80c=Decimal("500000"),
            section_80d=Decimal("500000"),
            section_80ccd_1b=Decimal("500000"),
            home_loan_interest=Decimal("900000"),
        )
        detail = self._tds().breakdown
        self.assertEqual(detail["section_80c"], float(te.CAP_80C))
        self.assertEqual(detail["section_80d"], float(te.CAP_80D))
        self.assertEqual(detail["section_80ccd_1b"], float(te.CAP_80CCD_1B))
        self.assertEqual(detail["home_loan_interest"], float(te.CAP_HOME_LOAN_INTEREST))

    def test_new_regime_ignores_chapter_via_deductions(self):
        self._declare(TaxDeclaration.Status.APPROVED, regime=TaxRegime.NEW)
        detail = self._tds().breakdown
        self.assertNotIn("section_80c", detail)
        self.assertIn("standard_deduction", detail)


class TaxComputationTests(TestCase):
    def setUp(self):
        self.org = _make_org("CalcCo", "CLC")
        ensure_tax_configuration(self.org)
        self.emp = _make_user(self.org, "calc@x.com")

    def _tds(self, gross, month=4, year=2026):
        return te.monthly_tds_for(
            self.emp,
            monthly_gross=Decimal(gross),
            monthly_basic=Decimal(gross) / 4,
            monthly_hra=Decimal(gross) / 8,
            year=year,
            month=month,
        )

    def test_new_regime_annual_tax_matches_hand_calculation(self):
        # 102500 x 12 = 1,230,000 gross; less 75,000 standard deduction = 1,155,000.
        # Tax = 20,000 + 30,000 + 15% of 155,000 (23,250) = 73,250; +4% cess = 76,180.
        result = self._tds("102500")
        self.assertEqual(result.projected_gross, Decimal("1230000.00"))
        self.assertEqual(result.taxable_income, Decimal("1155000.00"))
        self.assertEqual(result.annual_tax, Decimal("76180.00"))

    def test_rebate_87a_zeroes_small_incomes(self):
        # 50,000 x 12 = 600,000; less 75,000 = 525,000 taxable, under the 700,000 limit.
        result = self._tds("50000")
        self.assertEqual(result.taxable_income, Decimal("525000.00"))
        self.assertEqual(result.rebate_applied, Decimal("11250.00"))
        self.assertEqual(result.annual_tax, Decimal("0.00"))
        self.assertEqual(result.monthly_tds, Decimal("0.00"))

    def test_rebate_does_not_apply_above_the_limit(self):
        result = self._tds("102500")
        self.assertEqual(result.rebate_applied, Decimal("0"))

    def test_liability_is_spread_over_remaining_months(self):
        """The annual figure is constant; the monthly one rises as the year runs out."""
        april = self._tds("102500", month=4)
        october = self._tds("102500", month=10)
        march = self._tds("102500", month=3, year=2027)
        self.assertEqual(april.annual_tax, october.annual_tax)
        self.assertEqual(april.months_remaining, 12)
        self.assertEqual(october.months_remaining, 6)
        self.assertEqual(march.months_remaining, 1)
        self.assertLess(april.monthly_tds, october.monthly_tds)
        self.assertLess(october.monthly_tds, march.monthly_tds)

    def test_a_full_year_of_deductions_settles_exactly(self):
        """Walking April to March must withhold the annual liability to the paisa.

        Instalments are deliberately not identical: each month recomputes
        (annual - paid so far) / months left, so the final one absorbs the rounding
        that a flat annual/12 would leave behind.
        """
        withheld = Decimal("0")
        months = [(2026, m) for m in range(4, 13)] + [(2027, m) for m in (1, 2, 3)]
        for year, month in months:
            result = te.monthly_tds_for(
                self.emp,
                monthly_gross=Decimal("102500"),
                monthly_basic=Decimal("41000"),
                monthly_hra=Decimal("20500"),
                year=year,
                month=month,
                tds_paid=withheld,
            )
            withheld += result.monthly_tds

        annual = self._tds("102500", month=4).annual_tax
        self.assertEqual(withheld, annual)

    def test_the_final_instalment_absorbs_the_rounding(self):
        """March differs from April by the accumulated rounding, and never by more."""
        april = self._tds("102500", month=4)
        withheld = april.monthly_tds * 11
        march = te.monthly_tds_for(
            self.emp,
            monthly_gross=Decimal("102500"),
            monthly_basic=Decimal("41000"),
            monthly_hra=Decimal("20500"),
            year=2027,
            month=3,
            tds_paid=withheld,
        )
        self.assertEqual(withheld + march.monthly_tds, april.annual_tax)
        self.assertLess(abs(march.monthly_tds - april.monthly_tds), Decimal("1"))

    def test_zero_salary_produces_zero_tds(self):
        self.assertEqual(self._tds("0").monthly_tds, Decimal("0.00"))


class CatchUpTests(TestCase):
    """Tax already withheld this year must reduce what is still to be withheld."""

    def setUp(self):
        self.org = _make_org("CatchCo", "CTC")
        ensure_payroll_setup(self.org)
        ensure_tax_configuration(self.org)
        self.admin = _make_user(self.org, "a@catch.com", User.Role.ADMIN)
        self.emp = _make_user(self.org, "e@catch.com", employee_id="C1")
        self.tax_component = SalaryComponent.objects.get(organization=self.org, code="tax")

    def _record_tds(self, year, month, amount):
        run = PayrollRun.objects.create(organization=self.org, year=year, month=month)
        slip = Payslip.objects.create(
            payroll_run=run, user=self.emp, gross_salary=Decimal("100000"), net_salary=Decimal("90000")
        )
        PayslipLine.objects.create(
            payslip=slip,
            component=self.tax_component,
            label="Income Tax (TDS)",
            line_type=SalaryComponent.ComponentType.DEDUCTION,
            amount=Decimal(amount),
        )
        return slip

    def test_paid_tds_is_counted_within_the_financial_year(self):
        self._record_tds(2026, 5, "5000")
        self._record_tds(2027, 2, "3000")
        self.assertEqual(te.tds_paid_this_fy(self.emp, FY), Decimal("8000.00"))

    def test_tds_outside_the_financial_year_is_excluded(self):
        self._record_tds(2026, 3, "9999")   # belongs to FY 2025-26
        self._record_tds(2027, 4, "8888")   # belongs to FY 2027-28
        self.assertEqual(te.tds_paid_this_fy(self.emp, FY), Decimal("0.00"))

    def test_bulk_lookup_matches_per_user_lookup(self):
        self._record_tds(2026, 5, "5000")
        bulk = te.tds_paid_by_user(self.org, FY, users=[self.emp])
        self.assertEqual(bulk[self.emp.pk], te.tds_paid_this_fy(self.emp, FY))

    def test_over_withholding_stops_further_deduction(self):
        self._record_tds(2026, 4, "500000")
        result = te.monthly_tds_for(
            self.emp,
            monthly_gross=Decimal("100000"),
            monthly_basic=Decimal("40000"),
            monthly_hra=Decimal("20000"),
            year=2026,
            month=5,
        )
        self.assertGreater(result.annual_tax, Decimal("0"))
        self.assertEqual(result.monthly_tds, Decimal("0.00"))


class StatutoryProrationTests(TestCase):
    """Income tax and professional tax are owed in full regardless of attendance."""

    def setUp(self):
        self.org = _make_org("ProCo", "PRO")
        ensure_payroll_setup(self.org)

    def _amount(self, code, factor):
        comp = SalaryComponent.objects.get(organization=self.org, code=code)
        from .services import _resolve_component_amount

        comp.mode = comp.calc_type  # FIXED
        comp.value = Decimal("5000")
        return _resolve_component_amount(comp, Decimal("100000"), Decimal("40000"), factor)

    def test_income_tax_is_not_prorated(self):
        self.assertEqual(self._amount("tax", Decimal("0.5")), self._amount("tax", Decimal("1")))

    def test_professional_tax_is_not_prorated(self):
        self.assertEqual(self._amount("pt", Decimal("0.5")), self._amount("pt", Decimal("1")))

    def test_ordinary_earnings_are_still_prorated(self):
        half = self._amount("special", Decimal("0.5"))
        full = self._amount("special", Decimal("1"))
        self.assertEqual(half * 2, full)


class TaxConfigFallbackTests(TestCase):
    """A year without its own slabs must not compute a zero liability in silence."""

    def setUp(self):
        self.org = _make_org("FallCo", "FAL")
        ensure_tax_configuration(self.org)

    def test_earlier_year_falls_back_to_the_nearest_config(self):
        older = date(2020, 4, 1)
        self.assertFalse(te.has_exact_tax_config(self.org, older, "NEW"))
        self.assertIsNotNone(te.get_tax_config(self.org, older, "NEW"))

    def test_current_year_reports_an_exact_config(self):
        today_fy = te.financial_year_start_for(date.today())
        self.assertTrue(te.has_exact_tax_config(self.org, today_fy, "NEW"))


class Form16Tests(TestCase):
    def setUp(self):
        self.org = _make_org("F16Co", "F16")
        ensure_payroll_setup(self.org)
        ensure_tax_configuration(self.org)
        self.admin = _make_user(self.org, "admin@f16.com", User.Role.ADMIN)
        self.emp = _make_user(self.org, "emp@f16.com", employee_id="F1", pan_number="ABCDE1234F")
        self.tax_component = SalaryComponent.objects.get(organization=self.org, code="tax")
        self.pt_component = SalaryComponent.objects.get(organization=self.org, code="pt")

    def _slip(self, year, month, gross="100000", tds="5000", pt="200"):
        run = PayrollRun.objects.create(organization=self.org, year=year, month=month)
        slip = Payslip.objects.create(
            payroll_run=run,
            user=self.emp,
            gross_salary=Decimal(gross),
            net_salary=Decimal(gross) - Decimal(tds),
        )
        PayslipLine.objects.create(
            payslip=slip, component=self.tax_component, label="Income Tax (TDS)",
            line_type=SalaryComponent.ComponentType.DEDUCTION, amount=Decimal(tds),
        )
        PayslipLine.objects.create(
            payslip=slip, component=self.pt_component, label="Professional Tax",
            line_type=SalaryComponent.ComponentType.DEDUCTION, amount=Decimal(pt),
        )
        return slip

    def test_only_payslips_inside_the_financial_year_are_included(self):
        self._slip(2026, 5)
        self._slip(2027, 2)
        self._slip(2026, 3)   # previous FY
        self._slip(2027, 4)   # next FY
        data = f16.build_form16_data(self.emp, FY)
        self.assertEqual(data["months_paid"], 2)
        self.assertEqual(data["gross_salary"], Decimal("200000.00"))

    def test_quarterly_totals_reconcile_to_total_tds(self):
        self._slip(2026, 5, tds="1000")    # Q1
        self._slip(2026, 8, tds="2000")    # Q2
        self._slip(2026, 11, tds="3000")   # Q3
        self._slip(2027, 1, tds="4000")    # Q4
        data = f16.build_form16_data(self.emp, FY)
        by_code = {q["code"]: q["amount"] for q in data["quarters"]}
        self.assertEqual(by_code["Q1"], Decimal("1000.00"))
        self.assertEqual(by_code["Q2"], Decimal("2000.00"))
        self.assertEqual(by_code["Q3"], Decimal("3000.00"))
        self.assertEqual(by_code["Q4"], Decimal("4000.00"))
        self.assertEqual(sum(by_code.values()), data["tds_deducted"])

    def test_monthly_rows_sum_to_the_totals(self):
        self._slip(2026, 5, tds="1000")
        self._slip(2026, 6, tds="2000")
        data = f16.build_form16_data(self.emp, FY)
        self.assertEqual(sum(r["tds"] for r in data["monthly_rows"]), data["tds_deducted"])
        self.assertEqual(sum(r["gross"] for r in data["monthly_rows"]), data["gross_salary"])

    def test_professional_tax_is_deducted_from_taxable_income(self):
        self._slip(2026, 5, gross="100000", pt="200")
        data = f16.build_form16_data(self.emp, FY)
        self.assertEqual(data["professional_tax"], Decimal("200.00"))
        expected = data["gross_salary"] - data["total_exemptions"] - data["professional_tax"]
        self.assertEqual(data["taxable_income"], expected)

    def test_balance_is_tax_due_less_tds_deducted(self):
        self._slip(2026, 5, tds="1000")
        data = f16.build_form16_data(self.emp, FY)
        self.assertEqual(data["balance_payable"], data["total_tax"] - data["tds_deducted"])

    def test_no_payslips_yields_an_empty_certificate(self):
        data = f16.build_form16_data(self.emp, FY)
        self.assertEqual(data["months_paid"], 0)
        self.assertEqual(data["gross_salary"], Decimal("0.00"))
        self.assertEqual(data["tds_deducted"], Decimal("0.00"))

    def test_is_complete_only_for_a_full_year(self):
        for month in list(range(4, 13)) + [1, 2]:
            year = 2026 if month >= 4 else 2027
            self._slip(year, month)
        self.assertFalse(f16.build_form16_data(self.emp, FY)["is_complete"])
        self._slip(2027, 3)
        self.assertTrue(f16.build_form16_data(self.emp, FY)["is_complete"])

    def test_context_and_per_user_paths_agree(self):
        """The bulk path must produce exactly what the single path produces."""
        self._slip(2026, 5)
        self._slip(2026, 6)
        solo = f16.build_form16_data(self.emp, FY)
        ctx = f16.FYContext(self.org, FY, users=[self.emp])
        bulk = f16.build_form16_data(self.emp, FY, ctx=ctx)
        for key in ("gross_salary", "taxable_income", "total_tax", "tds_deducted", "months_paid"):
            self.assertEqual(solo[key], bulk[key], key)

    def test_issuing_snapshots_the_figures(self):
        self._slip(2026, 5, tds="1000")
        cert = f16.issue_certificate(self.emp, FY, issued_by=self.admin)
        self.assertTrue(cert.certificate_number.startswith("F16-2026-27-"))
        self.assertEqual(cert.tds_deducted, Decimal("1000.00"))
        original_gross = cert.gross_salary

        # A later payroll correction must not move an issued certificate.
        self._slip(2026, 6, tds="9999")
        cert.refresh_from_db()
        self.assertEqual(cert.gross_salary, original_gross)

    def test_snapshot_is_json_serialisable(self):
        self._slip(2026, 5)
        cert = f16.issue_certificate(self.emp, FY, issued_by=self.admin)
        self.assertIn("fy_label", cert.snapshot)
        self.assertIsInstance(cert.snapshot["gross_salary"], float)


class Form16ViewTests(TestCase):
    def setUp(self):
        self.org = _make_org("ViewCo", "VWC")
        ensure_payroll_setup(self.org)
        ensure_tax_configuration(self.org)
        self.admin = _make_user(self.org, "admin@view.com", User.Role.ADMIN)
        self.hr = _make_user(self.org, "hr@view.com", User.Role.HR)
        self.emp = _make_user(self.org, "emp@view.com", employee_id="V1")
        self.other = _make_user(self.org, "other@view.com", employee_id="V2")

    def test_admin_can_open_the_register(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get(reverse("payroll:form16")).status_code, 200)

    def test_hr_can_open_the_register(self):
        self.client.force_login(self.hr)
        self.assertEqual(self.client.get(reverse("payroll:form16")).status_code, 200)

    def test_employee_cannot_open_the_register(self):
        self.client.force_login(self.emp)
        self.assertNotEqual(self.client.get(reverse("payroll:form16")).status_code, 200)

    def test_employee_can_open_their_own_certificate(self):
        self.client.force_login(self.emp)
        self.assertEqual(self.client.get(reverse("payroll:form16_mine")).status_code, 200)

    def test_employee_cannot_open_someone_elses_certificate(self):
        self.client.force_login(self.emp)
        url = reverse("payroll:form16_detail", args=[self.other.pk])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_admin_can_open_any_certificate(self):
        self.client.force_login(self.admin)
        url = reverse("payroll:form16_detail", args=[self.emp.pk])
        self.assertEqual(self.client.get(url).status_code, 200)

    def test_pdf_download_returns_a_pdf(self):
        self.client.force_login(self.admin)
        url = reverse("payroll:form16_pdf", args=[self.emp.pk])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertTrue(response.content.startswith(b"%PDF-"))

    def test_issue_and_withdraw(self):
        self.client.force_login(self.admin)
        run = PayrollRun.objects.create(organization=self.org, year=2026, month=5)
        Payslip.objects.create(
            payroll_run=run, user=self.emp, gross_salary=Decimal("100000"), net_salary=Decimal("95000")
        )
        url = reverse("payroll:form16")
        self.client.post(url, {"fy": "2026", "user_id": str(self.emp.pk), "action": "issue"})
        self.assertTrue(Form16Certificate.objects.filter(user=self.emp).exists())
        self.client.post(url, {"fy": "2026", "user_id": str(self.emp.pk), "action": "revoke"})
        self.assertFalse(Form16Certificate.objects.filter(user=self.emp).exists())


class DeclarationWorkflowViewTests(TestCase):
    def setUp(self):
        self.org = _make_org("FlowCo", "FLW")
        ensure_tax_configuration(self.org)
        self.admin = _make_user(self.org, "admin@flow.com", User.Role.ADMIN)
        self.emp = _make_user(self.org, "emp@flow.com")

    def _post_declaration(self, action):
        return self.client.post(
            reverse("payroll:tax_declaration"),
            {
                "regime": "OLD",
                "hra_rent_paid": "240000",
                "section_80c": "150000",
                "section_80d": "25000",
                "section_80ccd_1b": "50000",
                "home_loan_interest": "200000",
                "other_exemptions": "0",
                "other_income": "0",
                "action": action,
            },
        )

    def test_employee_saves_then_submits(self):
        self.client.force_login(self.emp)
        self._post_declaration("save")
        d = TaxDeclaration.objects.get(user=self.emp)
        self.assertEqual(d.status, TaxDeclaration.Status.DRAFT)
        self._post_declaration("submit")
        d.refresh_from_db()
        self.assertEqual(d.status, TaxDeclaration.Status.SUBMITTED)
        self.assertIsNotNone(d.submitted_at)

    def test_hr_approval_records_the_reviewer(self):
        self.client.force_login(self.emp)
        self._post_declaration("submit")
        d = TaxDeclaration.objects.get(user=self.emp)

        self.client.force_login(self.admin)
        self.client.post(
            reverse("payroll:tax_declaration_review"),
            {"declaration_id": str(d.pk), "action": "approve", "review_note": "Proofs seen"},
        )
        d.refresh_from_db()
        self.assertEqual(d.status, TaxDeclaration.Status.APPROVED)
        self.assertEqual(d.reviewed_by, self.admin)
        self.assertEqual(d.review_note, "Proofs seen")

    def test_approved_declaration_is_locked_to_the_employee(self):
        self.client.force_login(self.emp)
        self._post_declaration("submit")
        d = TaxDeclaration.objects.get(user=self.emp)
        d.status = TaxDeclaration.Status.APPROVED
        d.save()

        self.client.force_login(self.emp)
        self.client.post(
            reverse("payroll:tax_declaration"),
            {"regime": "NEW", "section_80c": "0", "action": "save"},
        )
        d.refresh_from_db()
        self.assertEqual(d.status, TaxDeclaration.Status.APPROVED)
        self.assertEqual(d.section_80c, Decimal("150000.00"))
        self.assertEqual(d.regime, TaxRegime.OLD)

    def test_employee_cannot_reach_the_review_queue(self):
        self.client.force_login(self.emp)
        self.assertNotEqual(
            self.client.get(reverse("payroll:tax_declaration_review")).status_code, 200
        )

    def test_negative_amounts_are_clamped_to_zero(self):
        self.client.force_login(self.emp)
        self.client.post(
            reverse("payroll:tax_declaration"),
            {"regime": "OLD", "section_80c": "-50000", "action": "save"},
        )
        self.assertEqual(TaxDeclaration.objects.get(user=self.emp).section_80c, Decimal("0.00"))

    def test_garbage_input_does_not_crash(self):
        self.client.force_login(self.emp)
        response = self.client.post(
            reverse("payroll:tax_declaration"),
            {"regime": "OLD", "section_80c": "not-a-number", "action": "save"},
        )
        self.assertEqual(response.status_code, 302)
        self.assertEqual(TaxDeclaration.objects.get(user=self.emp).section_80c, Decimal("0.00"))


class TenantIsolationTests(TestCase):
    """Tax data must never cross an organization boundary."""

    def setUp(self):
        self.org_a = _make_org("OrgA", "OGA")
        self.org_b = _make_org("OrgB", "OGB")
        ensure_tax_configuration(self.org_a)
        ensure_tax_configuration(self.org_b)
        self.admin_a = _make_user(self.org_a, "admin@a.com", User.Role.ADMIN)
        self.emp_b = _make_user(self.org_b, "emp@b.com")

    def test_admin_cannot_open_another_orgs_certificate(self):
        self.client.force_login(self.admin_a)
        url = reverse("payroll:form16_detail", args=[self.emp_b.pk])
        self.assertEqual(self.client.get(url).status_code, 404)

    def test_register_lists_only_the_admins_own_org(self):
        self.client.force_login(self.admin_a)
        response = self.client.get(reverse("payroll:form16"))
        self.assertNotContains(response, "emp@b.com")
