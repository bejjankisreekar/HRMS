from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils.text import slugify

from apps.accounts.models import User
from apps.accounts.signals import _allocate_superadmin_username


class Command(BaseCommand):
    help = "Create or repair the platform super admin from SUPERADMIN_* settings."

    def handle(self, *args, **options):
        email = getattr(settings, "SUPERADMIN_EMAIL", None)
        password = getattr(settings, "SUPERADMIN_PASSWORD", None)
        if not email or not password:
            self.stderr.write(
                "No superadmin credentials configured. Set superadmin.email and "
                "superadmin.password in config.json (see config.json.example), or "
                "SUPERADMIN_EMAIL / SUPERADMIN_PASSWORD in the environment."
            )
            return

        base = slugify(getattr(settings, "SUPERADMIN_USERNAME", "") or "superadmin")[:50] or "superadmin"
        user = User.objects.filter(email__iexact=email).first()

        if user:
            if not user.username:
                user.username = _allocate_superadmin_username(base)
            user.role = User.Role.SUPER_ADMIN
            user.is_superuser = True
            user.is_staff = True
            user.is_active = True
            user.set_password(password)
            user.save()
            self.stdout.write(self.style.SUCCESS(f"Repaired super admin: username={user.username}"))
            return

        username = _allocate_superadmin_username(base)
        User.objects.create_superuser(
            email=email,
            password=password,
            username=username,
            first_name="Super",
            last_name="Admin",
        )
        self.stdout.write(self.style.SUCCESS(f"Created super admin: username={username}, email={email}"))
