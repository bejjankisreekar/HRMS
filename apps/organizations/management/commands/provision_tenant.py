"""Provision per-tenant PostgreSQL schemas and migrate operational data into them.

Shared users + isolated data model:
  python manage.py provision_tenant --all --reset    # (re)build every org schema
  python manage.py provision_tenant --org A1F93B2C   # one org
  python manage.py provision_tenant --rollback --org A1F93B2C  # drop the schema

Additive & safe: this does NOT change how the live app reads data. The cutover
(routing requests into the schema) is a separate, explicit switch.
"""
from django.core.management.base import BaseCommand, CommandError

from apps.organizations.models import Organization
from apps.organizations.tenant_data import provision_org_schema
from apps.organizations.utils import drop_tenant_schema, schema_exists


class Command(BaseCommand):
    help = "Create tenant schemas and copy each organization's operational data into them."

    def add_arguments(self, parser):
        parser.add_argument("--org", help="Organization code to provision.")
        parser.add_argument("--all", action="store_true", help="Provision all organizations.")
        parser.add_argument("--reset", action="store_true", help="Drop & rebuild the schema first.")
        parser.add_argument("--rollback", action="store_true", help="Drop the tenant schema(s).")

    def handle(self, *args, **opts):
        if opts["org"]:
            orgs = list(Organization.objects.filter(organization_code=opts["org"]))
            if not orgs:
                raise CommandError(f"No organization with code {opts['org']}.")
        elif opts["all"]:
            orgs = list(Organization.objects.exclude(schema_name__isnull=True).exclude(schema_name=""))
        else:
            raise CommandError("Pass --org <code> or --all.")

        if opts["rollback"]:
            for org in orgs:
                if org.schema_name and schema_exists(org.schema_name):
                    drop_tenant_schema(org.schema_name)
                    self.stdout.write(self.style.WARNING(f"Dropped schema {org.schema_name} ({org.name})."))
                else:
                    self.stdout.write(f"  no schema for {org.name}")
            return

        grand_ok = grand_mismatch = grand_rows = 0
        for org in orgs:
            self.stdout.write(self.style.MIGRATE_HEADING(
                f"\n>> {org.name} ({org.organization_code}) -> schema '{org.schema_name}'"
            ))
            try:
                report = provision_org_schema(org, reset=opts["reset"])
            except Exception as exc:
                # Roll back this tenant's schema so a partial copy never lingers.
                if opts["reset"] and org.schema_name and schema_exists(org.schema_name):
                    drop_tenant_schema(org.schema_name)
                raise CommandError(f"Failed for {org.name}: {exc}") from exc

            ok = sum(1 for r in report if r["status"] == "OK")
            mism = [r for r in report if r["status"] == "MISMATCH"]
            rows = sum(r["copied"] for r in report)
            for r in report:
                if r["status"] == "MISMATCH":
                    self.stdout.write(self.style.ERROR(
                        f"   [X] {r['table']}: expected {r['expected']} copied {r['copied']}"))
                elif r["status"] == "OK" and r["copied"]:
                    self.stdout.write(f"   [OK] {r['table']}: {r['copied']} rows")
            self.stdout.write(
                f"   {ok} tables validated, {rows} rows copied"
                + (self.style.ERROR(f", {len(mism)} MISMATCH") if mism else self.style.SUCCESS(", 0 mismatches"))
            )
            grand_ok += ok
            grand_mismatch += len(mism)
            grand_rows += rows

        style = self.style.SUCCESS if grand_mismatch == 0 else self.style.ERROR
        self.stdout.write(style(
            f"\nDone: {len(orgs)} org(s), {grand_rows} rows copied, "
            f"{grand_mismatch} mismatch(es). "
            + ("Counts validated [OK]" if grand_mismatch == 0 else "REVIEW MISMATCHES [X]")
        ))
