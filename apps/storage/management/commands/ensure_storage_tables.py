"""Ensure storage app tables exist in the public schema."""

from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Create storage tables if missing (fixes stale migration state)."

    def handle(self, *args, **options):
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT 1 FROM information_schema.tables
                WHERE table_schema = 'public' AND table_name = 'storage_storedfile'
                """
            )
            exists = cursor.fetchone() is not None

        if exists:
            self.stdout.write(self.style.SUCCESS("Storage tables already exist."))
            return

        self.stdout.write("Storage tables missing — re-applying migrations...")
        with connection.cursor() as cursor:
            cursor.execute("DELETE FROM django_migrations WHERE app = 'storage'")
        call_command("migrate", "storage", verbosity=options.get("verbosity", 1))
        self.stdout.write(self.style.SUCCESS("Storage migrations applied."))
