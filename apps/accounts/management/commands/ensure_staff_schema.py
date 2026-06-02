"""Ensure staff management columns and audit table exist in every schema."""

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection

from apps.organizations.models import Organization
from apps.organizations.utils import tenant_schema_has_user_table


def _schemas_with_user_table(cursor) -> list[str]:
    cursor.execute(
        """
        SELECT DISTINCT table_schema
        FROM information_schema.tables
        WHERE table_name = 'accounts_user'
          AND table_schema NOT IN ('pg_catalog', 'information_schema')
        ORDER BY table_schema
        """
    )
    return [row[0] for row in cursor.fetchall()]


def _column_exists(cursor, schema: str, column: str) -> bool:
    cursor.execute(
        """
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = %s AND table_name = 'accounts_user' AND column_name = %s
        """,
        [schema, column],
    )
    return cursor.fetchone() is not None


def _table_exists(cursor, schema: str, table: str) -> bool:
    cursor.execute(
        """
        SELECT 1 FROM information_schema.tables
        WHERE table_schema = %s AND table_name = %s
        """,
        [schema, table],
    )
    return cursor.fetchone() is not None


class Command(BaseCommand):
    help = "Add employment_status / archived_at and StaffAuditLog across public and tenant schemas."

    def handle(self, *args, **options):
        verbosity = options.get("verbosity", 1)

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1 FROM information_schema.columns
                WHERE table_schema = 'public' AND table_name = 'accounts_user'
                  AND column_name = 'employment_status'
                """
            )
            public_ok = cursor.fetchone() is not None

        if not public_ok:
            if verbosity:
                self.stdout.write("Applying accounts migrations on public schema…")
            call_command("migrate", "accounts", verbosity=verbosity)

        altered = 0
        with connection.cursor() as cursor:
            for schema in _schemas_with_user_table(cursor):
                if not _column_exists(cursor, schema, "employment_status"):
                    cursor.execute(
                        f'ALTER TABLE "{schema}".accounts_user '
                        "ADD COLUMN IF NOT EXISTS employment_status varchar(20) NOT NULL DEFAULT 'ACTIVE'"
                    )
                    altered += 1
                    if verbosity:
                        self.stdout.write(f"  + {schema}.accounts_user.employment_status")

                if not _column_exists(cursor, schema, "archived_at"):
                    cursor.execute(
                        f'ALTER TABLE "{schema}".accounts_user '
                        "ADD COLUMN IF NOT EXISTS archived_at timestamp with time zone NULL"
                    )
                    altered += 1
                    if verbosity:
                        self.stdout.write(f"  + {schema}.accounts_user.archived_at")

                if not _table_exists(cursor, schema, "accounts_staffauditlog"):
                    if schema == "public":
                        if verbosity:
                            self.stdout.write("StaffAuditLog missing in public — running migrate…")
                        call_command("migrate", "accounts", verbosity=verbosity)
                    else:
                        if verbosity:
                            self.stdout.write(
                                self.style.WARNING(
                                    f"  ! {schema} has accounts_user but no StaffAuditLog "
                                    "(audit logs use public schema)"
                                )
                            )

        org_count = Organization.objects.exclude(schema_name__isnull=True).exclude(schema_name="").count()
        tenant_schema_has_user_table.cache_clear()
        if verbosity:
            self.stdout.write(self.style.SUCCESS(
                f"Staff schema check complete ({altered} column(s) added, {org_count} tenant schema(s))."
            ))
