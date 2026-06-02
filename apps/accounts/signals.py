from django.conf import settings
from django.db.models.signals import post_migrate
from django.dispatch import receiver
from django.utils.text import slugify

from .models import User


def _allocate_superadmin_username(base: str) -> str:
    username = base
    i = 1
    while User.objects.filter(username__iexact=username).exists():
        i += 1
        username = f"{base}{i}"[:50]
    return username


@receiver(post_migrate)
def ensure_default_superadmin(sender, **kwargs):
    """
    Bootstrap a default platform Super Admin using environment variables.
    Runs after migrations; repairs existing superadmin if username is missing.
    """
    email = getattr(settings, "SUPERADMIN_EMAIL", None)
    password = getattr(settings, "SUPERADMIN_PASSWORD", None)
    if not email or not password:
        return

    base = slugify(getattr(settings, "SUPERADMIN_USERNAME", "") or "superadmin")[:50] or "superadmin"

    existing = User.objects.filter(email__iexact=email).first()
    if existing:
        changed = False
        if not existing.username:
            existing.username = _allocate_superadmin_username(base)
            changed = True
        if existing.role != User.Role.SUPER_ADMIN:
            existing.role = User.Role.SUPER_ADMIN
            changed = True
        if not existing.is_superuser:
            existing.is_superuser = True
            existing.is_staff = True
            changed = True
        if changed:
            existing.save(update_fields=["username", "role", "is_superuser", "is_staff"])
        return

    username = _allocate_superadmin_username(base)
    User.objects.create_superuser(
        email=email,
        password=password,
        username=username,
        first_name="Super",
        last_name="Admin",
    )

