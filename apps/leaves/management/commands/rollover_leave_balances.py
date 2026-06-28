"""Year-start leave balance rollover.

Creates the new year's balances for every active staff member and carries
forward unused days up to each leave type's ``carry_forward_max``.

Usage:
    python manage.py rollover_leave_balances [--year 2027] [--org ORGCODE]
"""

from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.role_labels import STAFF_SELF_SERVICE_ROLES
from apps.leaves.models import LeaveBalance, LeaveType
from apps.organizations.models import Organization


class Command(BaseCommand):
    help = "Allocate next-year leave balances with carry-forward for all active staff."

    def add_arguments(self, parser):
        parser.add_argument(
            "--year",
            type=int,
            default=None,
            help="Target year to allocate (default: current year).",
        )
        parser.add_argument(
            "--org",
            type=str,
            default=None,
            help="Limit to one organization code (default: all active orgs).",
        )

    def handle(self, *args, **options):
        year = options["year"] or timezone.localdate().year
        prev_year = year - 1

        orgs = Organization.objects.filter(is_active=True)
        if options["org"]:
            orgs = orgs.filter(organization_code__iexact=options["org"])

        total_created = 0
        for org in orgs:
            staff = User.objects.filter(
                organization=org,
                is_active=True,
                role__in=STAFF_SELF_SERVICE_ROLES,
            )
            types = list(LeaveType.objects.filter(organization=org, is_active=True))
            for member in staff:
                for lt in types:
                    if not lt.is_applicable_to(member):
                        continue
                    carry = Decimal("0")
                    prev = LeaveBalance.objects.filter(
                        user=member, leave_type=lt, year=prev_year
                    ).first()
                    if prev and lt.carry_forward_max > 0:
                        carry = max(min(prev.remaining, lt.carry_forward_max), Decimal("0"))
                    _, created = LeaveBalance.objects.get_or_create(
                        user=member,
                        leave_type=lt,
                        year=year,
                        defaults={
                            "allocated": lt.annual_quota or Decimal("0"),
                            "carried_forward": carry,
                        },
                    )
                    if created:
                        total_created += 1
            self.stdout.write(f"{org.name}: processed {staff.count()} staff.")

        self.stdout.write(self.style.SUCCESS(f"Created {total_created} balance rows for {year}."))
