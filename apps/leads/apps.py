import logging
import sys

from django.apps import AppConfig


class LeadsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.leads"
    label = "leads"

    def ready(self):
        if any(cmd in sys.argv for cmd in ("runserver", "gunicorn", "uvicorn")):
            from django.conf import settings

            from .services import delivery_configured, smtp_setup_hint

            if not delivery_configured():
                logging.getLogger("apps.leads").warning(
                    "Contact form emails are DISABLED — %s",
                    smtp_setup_hint().replace("\n", " | "),
                )
