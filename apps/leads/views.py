from django.conf import settings
from django.contrib import messages
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views import View

from .forms import ContactLeadForm, NewsletterForm
from .marketing_contact import get_contact_page_context
from .formsubmit import formsubmit_enabled
from .services import delivery_configured, send_contact_emails, smtp_setup_hint


class ContactPageView(View):
    template_name = "marketing/contact.html"

    def get(self, request):
        return render(
            request,
            self.template_name,
            self._context(request, ContactLeadForm(), NewsletterForm()),
        )

    def post(self, request):
        form_type = request.POST.get("form_type", "contact")

        if form_type == "newsletter":
            newsletter_form = NewsletterForm(request.POST)
            if newsletter_form.is_valid():
                newsletter_form.save()
                messages.success(request, "You're subscribed! Check your inbox for HR insights.")
            else:
                messages.error(request, "Please enter a valid email address.")
            return redirect(reverse("accounts:contact") + "#newsletter")

        form = ContactLeadForm(request.POST)
        if form.is_valid():
            lead = form.save(commit=False)
            lead.ip_address = _client_ip(request)
            lead.user_agent = (request.META.get("HTTP_USER_AGENT") or "")[:255]
            lead.save()
            email_status = send_contact_emails(lead)
            messages.success(
                request,
                "Thank you! We've received your message and will respond within 4 business hours.",
            )
            if not email_status["inbox_sent"] and not formsubmit_enabled():
                import logging

                logging.getLogger("apps.leads.services").warning(smtp_setup_hint())
            return redirect(reverse("accounts:contact") + "?sent=1#contact-form")

        messages.error(request, "Please correct the errors below and try again.")
        return render(
            request,
            self.template_name,
            self._context(request, form, NewsletterForm()),
        )

    def _context(self, request, contact_form, newsletter_form):
        ctx = get_contact_page_context()
        ctx.update(
            {
                "contact_form": contact_form,
                "newsletter_form": newsletter_form,
                "form_sent": request.GET.get("sent") == "1",
                "delivery_configured": delivery_configured(),
            }
        )
        return ctx


def _client_ip(request) -> str | None:
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")
