"""Test contact email delivery (SMTP). FormSubmit is tested via the contact form in a browser."""

from django.conf import settings
from django.core.mail import EmailMessage
from django.core.management.base import BaseCommand, CommandError

from apps.leads.formsubmit import formsubmit_enabled, formsubmit_target_email
from apps.leads.services import contact_inbox_email, smtp_configured


class Command(BaseCommand):
    help = (
        "Test SMTP contact notifications. "
        "FormSubmit is sent from the browser — submit /accounts/contact/ to test it."
    )

    def handle(self, *args, **options):
        if formsubmit_enabled() and not smtp_configured():
            self.stdout.write(
                self.style.SUCCESS(
                    f"FormSubmit is enabled for {formsubmit_target_email()}.\n"
                    "Open the contact page in your browser, submit the form, then check your inbox.\n"
                    "On first use, click the activation link from submissions@formsubmit.co"
                )
            )
            return

        if not smtp_configured():
            raise CommandError(
                "SMTP not configured (EMAIL_HOST_PASSWORD empty). "
                "Enable FORMSUBMIT_ENABLED=True or set EMAIL_HOST_PASSWORD in hrms/.env."
            )

        inbox = contact_inbox_email()
        self.stdout.write(f"Sending test email via SMTP to {inbox}…")
        try:
            msg = EmailMessage(
                subject="[HRMS] SMTP test",
                body="SMTP contact notifications are working.",
                from_email=settings.DEFAULT_FROM_EMAIL,
                to=[inbox],
            )
            msg.send(fail_silently=False)
        except Exception as exc:
            raise CommandError(f"SMTP failed: {exc}") from exc

        self.stdout.write(self.style.SUCCESS(f"SMTP test email sent to {inbox}."))
