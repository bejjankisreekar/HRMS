from django.core.management.base import BaseCommand

from apps.storage.scanner import sync_all_organizations, sync_organization_files
from apps.organizations.models import Organization


class Command(BaseCommand):
    help = "Index uploaded files into StoredFile for storage analytics."

    def add_arguments(self, parser):
        parser.add_argument("--org", type=str, help="Organization UUID")

    def handle(self, *args, **options):
        org_id = options.get("org")
        if org_id:
            org = Organization.objects.get(pk=org_id)
            n = sync_organization_files(org)
            self.stdout.write(f"Synced {n} files for {org.name}")
        else:
            n = sync_all_organizations()
            self.stdout.write(self.style.SUCCESS(f"Synced {n} file records platform-wide"))
