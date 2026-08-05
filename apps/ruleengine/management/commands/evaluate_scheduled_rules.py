"""Evaluate SCHEDULED-trigger rules for every active employee.

Covers threshold rules that aren't tied to a single event (e.g. "Late Count >
3 in the last 30 days"). This codebase has no async task queue (see
apps/leaves/management/commands/rollover_leave_balances.py for the same
management-command pattern), so this is intended to be run periodically by
the OS scheduler / cron, not a new background worker.

Usage:
    python manage.py evaluate_scheduled_rules [--org ORGCODE]
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.accounts.models import User
from apps.accounts.role_labels import STAFF_SELF_SERVICE_ROLES
from apps.organizations.models import Organization
from apps.ruleengine.engine import evaluate_rules
from apps.ruleengine.models import Rule


class Command(BaseCommand):
    help = "Evaluate SCHEDULED rule-engine rules against every active employee."

    def add_arguments(self, parser):
        parser.add_argument(
            "--org",
            type=str,
            default=None,
            help="Limit to one organization code (default: all active orgs).",
        )

    def handle(self, *args, **options):
        orgs = Organization.objects.filter(is_active=True)
        if options["org"]:
            orgs = orgs.filter(organization_code__iexact=options["org"])

        total_matched = 0
        for org in orgs:
            if not Rule.objects.filter(
                organization=org, trigger_event=Rule.Trigger.SCHEDULED, status=Rule.Status.ACTIVE
            ).exists():
                continue
            staff = User.objects.filter(organization=org, is_active=True, role__in=STAFF_SELF_SERVICE_ROLES)
            for member in staff:
                logs = evaluate_rules(org, Rule.Trigger.SCHEDULED, subject=member)
                total_matched += sum(1 for log in logs if log.matched)
            self.stdout.write(f"{org.name}: evaluated {staff.count()} staff.")

        self.stdout.write(self.style.SUCCESS(f"{total_matched} rule match(es) actioned."))
