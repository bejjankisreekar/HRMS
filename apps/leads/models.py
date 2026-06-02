import uuid

from django.db import models
from django.utils import timezone


class LeadStatus(models.TextChoices):
    NEW = "NEW", "New"
    CONTACTED = "CONTACTED", "Contacted"
    QUALIFIED = "QUALIFIED", "Qualified"
    CLOSED = "CLOSED", "Closed"
    SPAM = "SPAM", "Spam"


class ContactLead(models.Model):
    """CRM-ready inbound lead from the marketing contact page."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    full_name = models.CharField(max_length=120)
    company_name = models.CharField(max_length=160)
    work_email = models.EmailField()
    phone_number = models.CharField(max_length=30, blank=True)
    employee_count = models.CharField(max_length=40)
    interested_modules = models.JSONField(default=list, blank=True)
    message = models.TextField()
    status = models.CharField(max_length=20, choices=LeadStatus.choices, default=LeadStatus.NEW)
    source = models.CharField(max_length=40, default="contact_page")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=255, blank=True)
    crm_external_id = models.CharField(max_length=120, blank=True, help_text="HubSpot/Zoho CRM ID when synced")
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.full_name} — {self.company_name}"


class NewsletterSubscriber(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    email = models.EmailField(unique=True)
    source = models.CharField(max_length=40, default="contact_page")
    is_active = models.BooleanField(default=True)
    subscribed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ["-subscribed_at"]

    def __str__(self) -> str:
        return self.email
