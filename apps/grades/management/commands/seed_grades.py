from django.core.management.base import BaseCommand

from apps.grades.services.defaults import seed_organization_grades
from apps.organizations.models import Organization


class Command(BaseCommand):
    help = "Seed default job grades and designations for organizations."

    def add_arguments(self, parser):
        parser.add_argument("--org-id", type=str, help="Organization UUID (all orgs if omitted)")

    def handle(self, *args, **options):
        org_id = options.get("org_id")
        qs = Organization.objects.filter(is_active=True)
        if org_id:
            qs = qs.filter(pk=org_id)
        for org in qs:
            result = seed_organization_grades(org)
            if result.get("skipped"):
                self.stdout.write(f"{org.name}: already seeded")
            else:
                self.stdout.write(self.style.SUCCESS(f"{org.name}: {result['grades']} grades created"))
