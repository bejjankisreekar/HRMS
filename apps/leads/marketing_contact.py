"""Static marketing content for the contact page."""

from urllib.parse import quote

from django.conf import settings

from .formsubmit import formsubmit_enabled, formsubmit_target_email


def _inbox_email() -> str:
    return (
        getattr(settings, "CONTACT_INBOX_EMAIL", None)
        or getattr(settings, "SALES_INBOX_EMAIL", None)
        or "sreekarbejjanki@gmail.com"
    )


CONTACT_FAQ = [
    (
        "How quickly will I get a response?",
        "We respond to all inquiries within 4 business hours during Mon–Fri, 10:00–18:00 IST. Growth plan inquiries are prioritized.",
    ),
    (
        "Can I schedule a personalized demo?",
        "Yes. Use the Book Demo button or mention it in your message — we'll send a calendar link within one business day.",
    ),
    (
        "Do you offer implementation support?",
        "Professional and Growth plans include onboarding assistance. We also offer paid migration packages for large teams.",
    ),
    (
        "Is my data secure when I submit this form?",
        "All submissions are encrypted in transit (HTTPS) and stored securely. We never share your information with third parties.",
    ),
]

def _support_channels() -> list[dict]:
    inbox = _inbox_email()
    return [
        {
            "title": "General inquiry",
            "description": "Questions about HRMS Suite, demos, and getting started.",
            "email": inbox,
            "icon": "mail",
        },
        {
            "title": "Sales & pricing",
            "description": "Plans, quotes, and recommendations for your team size.",
            "email": inbox,
            "icon": "briefcase",
        },
        {
            "title": "Support",
            "description": "Help with login, bugs, and platform issues.",
            "email": inbox,
            "icon": "life-buoy",
        },
    ]

CONTACT_TESTIMONIALS = [
    {
        "quote": "The sales team responded within 2 hours and had us live in a week.",
        "name": "Arjun Mehta",
        "role": "COO, UrbanBuild",
    },
    {
        "quote": "Professional onboarding from day one — exactly what we expected from an enterprise HR platform.",
        "name": "Sarah Lopez",
        "role": "HR Lead, MedCore",
    },
]


def get_contact_page_context() -> dict:
    inbox = formsubmit_target_email() if formsubmit_enabled() else _inbox_email()
    return {
        "contact_faq": CONTACT_FAQ,
        "support_channels": _support_channels(),
        "contact_inbox_email": _inbox_email(),
        "contact_testimonials": CONTACT_TESTIMONIALS,
        "trust_stats": [
            ("4 hrs", "Avg. response time"),
            ("500+", "Companies trust us"),
            ("256-bit", "SSL encryption"),
        ],
        "formsubmit_enabled": formsubmit_enabled(),
        "formsubmit_ajax_url": f"https://formsubmit.co/ajax/{quote(inbox, safe='')}",
        "site_url": getattr(settings, "SITE_URL", "http://127.0.0.1:8000").rstrip("/"),
    }
