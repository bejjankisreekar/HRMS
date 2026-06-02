"""Contact lead notifications — FormSubmit (portfolio) and/or Gmail SMTP."""

from __future__ import annotations

import logging

from django.conf import settings
from django.core.mail import EmailMessage, send_mail

from .formsubmit import formsubmit_enabled

logger = logging.getLogger(__name__)


def contact_inbox_email() -> str:
    return (
        getattr(settings, "CONTACT_INBOX_EMAIL", None)
        or getattr(settings, "SALES_INBOX_EMAIL", None)
        or "sreekarbejjanki@gmail.com"
    )


def smtp_configured() -> bool:
    password = getattr(settings, "EMAIL_HOST_PASSWORD", None)
    return bool(
        getattr(settings, "EMAIL_HOST", None)
        and getattr(settings, "EMAIL_HOST_USER", None)
        and password
        and str(password).strip()
    )


def delivery_configured() -> bool:
    return formsubmit_enabled() or smtp_configured()


def smtp_setup_hint() -> str:
    return (
        "Contact delivery is not configured. "
        "Set FORMSUBMIT_ENABLED=True (browser delivery, no SMTP) or EMAIL_HOST_PASSWORD for Gmail."
    )


def _notify_via_smtp(lead) -> bool:
    inbox = contact_inbox_email()
    modules = ", ".join(lead.interested_modules) if lead.interested_modules else "—"
    subject = f"[HRMS Contact] {lead.company_name} — {lead.full_name}"
    body = (
        f"New message from the HRMS contact page\n"
        f"{'=' * 40}\n\n"
        f"Name:        {lead.full_name}\n"
        f"Company:     {lead.company_name}\n"
        f"Email:       {lead.work_email}\n"
        f"Phone:       {lead.phone_number or '—'}\n"
        f"Team size:   {lead.employee_count or '—'}\n"
        f"Modules:     {modules}\n"
        f"Submitted:   {lead.created_at:%d %b %Y, %H:%M %Z}\n"
    )
    if lead.ip_address:
        body += f"IP:          {lead.ip_address}\n"
    body += f"\nMessage:\n{'-' * 40}\n{lead.message}\n"

    try:
        msg = EmailMessage(
            subject=subject,
            body=body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=[inbox],
            reply_to=[lead.work_email],
        )
        msg.send(fail_silently=False)
        logger.info("SMTP notification sent to %s for lead %s", inbox, lead.pk)
        return True
    except Exception:
        logger.exception("SMTP failed for lead %s", lead.pk)
        return False


def notify_contact_inbox(lead) -> bool:
    """
    Notify site owner via SMTP when configured.

    FormSubmit runs in the browser (contact.js) — Cloudflare blocks server-side POSTs.
    """
    if smtp_configured():
        return _notify_via_smtp(lead)
    if formsubmit_enabled():
        return True
    logger.warning(
        "Contact saved (lead %s) but no delivery — enable FORMSUBMIT_ENABLED or configure SMTP.",
        lead.pk,
    )
    return False


def send_lead_confirmation(lead) -> bool:
    """Optional auto-reply to visitor (requires SMTP)."""
    if not smtp_configured():
        return False

    subject = "We received your message — HRMS Suite"
    message = (
        f"Hi {lead.full_name},\n\n"
        f"Thank you for contacting HRMS Suite. Our team typically responds within 4 business hours.\n\n"
        f"Your inquiry:\n{lead.message[:500]}\n\n"
        f"— The HRMS Suite Team"
    )
    try:
        send_mail(
            subject,
            message,
            settings.DEFAULT_FROM_EMAIL,
            [lead.work_email],
            fail_silently=False,
        )
        return True
    except Exception:
        logger.exception("Failed to send lead confirmation to %s", lead.work_email)
        return False


def send_contact_emails(lead) -> dict:
    inbox_ok = notify_contact_inbox(lead)
    return {
        "inbox_sent": inbox_ok,
        "confirmation_sent": send_lead_confirmation(lead),
        "smtp_configured": smtp_configured(),
        "formsubmit_enabled": formsubmit_enabled(),
        "via_formsubmit": formsubmit_enabled() and not smtp_configured(),
    }


notify_sales_team = notify_contact_inbox
