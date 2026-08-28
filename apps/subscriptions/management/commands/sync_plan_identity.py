"""Push plan names from `plan_features.py` onto the database.

Editing `PLAN_TIERS` in apps/subscriptions/plan_features.py changes what the CODE
calls each plan. The public pricing page, Super Admin and the plan matrix read
`Plan.name` out of the database, so a rename is only half-applied until those rows
are updated too. This command does that.

    python manage.py sync_plan_identity --dry-run     # show what would change
    python manage.py sync_plan_identity               # apply

Renaming the display name needs nothing else. Changing a `slug` is a different
matter — the database still holds the old slug, so tell the command about it:

    python manage.py sync_plan_identity --rename basic=starter

Aliases in plan_features (e.g. "essential" -> basic) are picked up automatically,
so a plan whose row still carries a historic slug is adopted without --rename.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.organizations.models import Organization
from apps.subscriptions import plan_features
from apps.subscriptions.models import Plan


class Command(BaseCommand):
    help = "Sync plan slugs/names/descriptions from plan_features.py to the database."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Report what would change without writing anything.",
        )
        parser.add_argument(
            "--rename",
            action="append",
            default=[],
            metavar="OLD=NEW",
            help="Rename a plan slug, e.g. --rename basic=starter. Repeatable.",
        )

    def handle(self, *args, **options):
        dry_run: bool = options["dry_run"]
        renames = self._parse_renames(options["rename"])

        problems = plan_features.check()
        if any(problems.values()):
            self.stdout.write(self.style.WARNING(f"plan_features.check(): {problems}"))

        changes: list[str] = []
        with transaction.atomic():
            for old_slug, new_slug in renames.items():
                row = Plan.objects.filter(slug=old_slug).first()
                if not row:
                    self.stdout.write(
                        self.style.WARNING(f"  rename: no plan with slug '{old_slug}' - skipped")
                    )
                    continue
                if Plan.objects.filter(slug=new_slug).exclude(pk=row.pk).exists():
                    raise CommandError(
                        f"cannot rename '{old_slug}' -> '{new_slug}': slug already taken"
                    )
                changes.append(f"  slug   {old_slug} -> {new_slug}")
                if not dry_run:
                    row.slug = new_slug
                    row.save(update_fields=["slug"])

            for order, tier in enumerate(plan_features.PLAN_TIERS, start=1):
                row = self._find_row(tier)
                if row is None:
                    changes.append(f"  MISSING  no database row for '{tier.slug}' ({tier.name})")
                    continue

                updates: dict[str, object] = {}
                if row.slug != tier.slug:
                    updates["slug"] = tier.slug
                    changes.append(f"  slug   {row.slug} -> {tier.slug}  (matched via alias)")
                if row.name != tier.name:
                    updates["name"] = tier.name
                    changes.append(f"  name   {row.slug}: '{row.name}' -> '{tier.name}'")
                if row.description != tier.description:
                    updates["description"] = tier.description
                    changes.append(f"  desc   {row.slug}: updated")
                if row.sort_order != order:
                    updates["sort_order"] = order
                    changes.append(f"  order  {row.slug}: {row.sort_order} -> {order}")

                if updates and not dry_run:
                    for field, value in updates.items():
                        setattr(row, field, value)
                    row.save(update_fields=list(updates))

            if dry_run:
                transaction.set_rollback(True)

        self._report_orphans()
        self._report_org_enum_drift()

        if not changes:
            self.stdout.write(self.style.SUCCESS("Database already matches plan_features.py."))
            return

        self.stdout.write("Changes:" if not dry_run else "Would change:")
        for line in changes:
            self.stdout.write(line)

        if dry_run:
            self.stdout.write(self.style.WARNING("\nDry run - nothing written."))
            return

        self._invalidate_caches()
        self.stdout.write(self.style.SUCCESS(f"\nApplied {len(changes)} change(s)."))

    # ── helpers ────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_renames(raw: list[str]) -> dict[str, str]:
        renames: dict[str, str] = {}
        for item in raw:
            if "=" not in item:
                raise CommandError(f"--rename expects OLD=NEW, got '{item}'")
            old, new = (part.strip().lower() for part in item.split("=", 1))
            if not old or not new:
                raise CommandError(f"--rename expects OLD=NEW, got '{item}'")
            renames[old] = new
        return renames

    @staticmethod
    def _find_row(tier: plan_features.PlanTier) -> Plan | None:
        """Locate the row for a tier by slug, then by any historic alias."""
        row = Plan.objects.filter(slug=tier.slug).first()
        if row:
            return row
        for alias in tier.aliases:
            row = Plan.objects.filter(slug=alias).first()
            if row:
                return row
        return None

    def _report_orphans(self) -> None:
        known = {t.slug for t in plan_features.PLAN_TIERS}
        known |= {a for t in plan_features.PLAN_TIERS for a in t.aliases}
        orphans = list(Plan.objects.exclude(slug__in=known).values_list("slug", "name"))
        for slug, name in orphans:
            self.stdout.write(
                self.style.WARNING(f"  ORPHAN   plan '{slug}' ({name}) is not in plan_features.py")
            )

    def _report_org_enum_drift(self) -> None:
        """Organizations whose stored subscription_plan is not a known tier."""
        known = {t.enum_value for t in plan_features.PLAN_TIERS}
        stray = (
            Organization.objects.exclude(subscription_plan__in=known)
            .values_list("subscription_plan", flat=True)
            .distinct()
        )
        for value in stray:
            count = Organization.objects.filter(subscription_plan=value).count()
            self.stdout.write(
                self.style.WARNING(
                    f"  DRIFT    {count} org(s) have subscription_plan='{value}', "
                    f"which no tier declares - they fall back to "
                    f"{plan_features.DEFAULT_TIER.name}"
                )
            )

    def _invalidate_caches(self) -> None:
        from apps.subscriptions.services.entitlements import invalidate_org_entitlements

        count = 0
        for org in Organization.objects.all().only("id"):
            invalidate_org_entitlements(org)
            count += 1
        self.stdout.write(f"Invalidated entitlement cache for {count} organization(s).")
