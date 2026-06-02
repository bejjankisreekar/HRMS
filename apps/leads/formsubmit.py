"""
FormSubmit (https://formsubmit.co) — browser delivery via static/contact.js.

Server-side POST is blocked by Cloudflare; use the contact form in a browser to test.
"""

from __future__ import annotations

from django.conf import settings


def formsubmit_enabled() -> bool:
    return bool(getattr(settings, "FORMSUBMIT_ENABLED", True))


def formsubmit_target_email() -> str:
    return (
        getattr(settings, "FORMSUBMIT_EMAIL", None)
        or getattr(settings, "CONTACT_INBOX_EMAIL", None)
        or "sreekarbejjanki@gmail.com"
    )
