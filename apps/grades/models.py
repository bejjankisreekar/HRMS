"""Dynamic job grades, designations, and internal hierarchy (not auth roles)."""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class GradeCategory(models.TextChoices):
    HR = "HR", "HR Grades"
    EMPLOYEE = "EMPLOYEE", "Employee Grades"
    MANAGEMENT = "MANAGEMENT", "Management Grades"
    EXECUTIVE = "EXECUTIVE", "Executive Grades"
    TECHNICAL = "TECHNICAL", "Technical Grades"
    CONTRACTUAL = "CONTRACTUAL", "Contractual Grades"


class GradeStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    ARCHIVED = "ARCHIVED", "Archived"


class Grade(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="job_grades",
    )
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=40, blank=True)
    level_number = models.PositiveSmallIntegerField(default=5, help_text="1 = highest seniority")
    category = models.CharField(max_length=20, choices=GradeCategory.choices, default=GradeCategory.EMPLOYEE)
    description = models.TextField(blank=True)
    parent_grade = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="child_grades",
    )
    reporting_grade = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="reports_from",
    )
    priority_order = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=12, choices=GradeStatus.choices, default=GradeStatus.ACTIVE)
    salary_band_min = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    salary_band_max = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    departments = models.ManyToManyField(
        "organizations.Department",
        blank=True,
        related_name="linked_grades",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["category", "level_number", "priority_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"],
                condition=~models.Q(code=""),
                name="unique_grade_code_per_org",
            ),
        ]
        indexes = [
            models.Index(fields=["organization", "category", "status"]),
        ]

    def __str__(self) -> str:
        return self.name


class Designation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="designations",
    )
    name = models.CharField(max_length=120)
    code = models.CharField(max_length=40, blank=True)
    description = models.TextField(blank=True)
    grade = models.ForeignKey(
        Grade,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="designations",
    )
    priority_order = models.PositiveSmallIntegerField(default=0)
    status = models.CharField(max_length=12, choices=GradeStatus.choices, default=GradeStatus.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["priority_order", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["organization", "code"],
                condition=~models.Q(code=""),
                name="unique_designation_code_per_org",
            ),
        ]

    def __str__(self) -> str:
        return self.name


class GradePermission(models.Model):
    """Permission bundles mapped to a job grade (internal access, not Django auth)."""

    class PermissionKey(models.TextChoices):
        HR_FULL = "hr.full", "Full HR access"
        HR_LIMITED = "hr.limited", "Limited HR access"
        ATTENDANCE_VIEW = "attendance.view", "View attendance"
        ATTENDANCE_MANAGE = "attendance.manage", "Manage attendance"
        LEAVE_APPROVE = "leave.approve", "Approve leave"
        PAYROLL_VIEW = "payroll.view", "View payroll"
        PAYROLL_MANAGE = "payroll.manage", "Manage payroll"
        TEAM_APPROVE = "team.approve", "Team approval access"
        REPORTS = "reports.view", "View reports"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    grade = models.ForeignKey(Grade, on_delete=models.CASCADE, related_name="permissions")
    permission_key = models.CharField(max_length=40, choices=PermissionKey.choices)
    notes = models.CharField(max_length=255, blank=True)

    class Meta:
        unique_together = [("grade", "permission_key")]

    def __str__(self) -> str:
        return f"{self.grade.name} · {self.get_permission_key_display()}"


class CareerPathStep(models.Model):
    """Promotion path between grades."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey(
        "organizations.Organization",
        on_delete=models.CASCADE,
        related_name="career_path_steps",
    )
    from_grade = models.ForeignKey(
        Grade,
        on_delete=models.CASCADE,
        related_name="promotion_from_steps",
    )
    to_grade = models.ForeignKey(
        Grade,
        on_delete=models.CASCADE,
        related_name="promotion_to_steps",
    )
    sort_order = models.PositiveSmallIntegerField(default=0)
    requirements = models.TextField(blank=True, help_text="Eligibility criteria for promotion")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["sort_order"]
        unique_together = [("organization", "from_grade", "to_grade")]

    def __str__(self) -> str:
        return f"{self.from_grade.name} → {self.to_grade.name}"


class GradeChangeLog(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    organization = models.ForeignKey("organizations.Organization", on_delete=models.CASCADE)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="grade_change_logs",
    )
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="grade_changes_made",
    )
    from_grade = models.ForeignKey(
        Grade,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    to_grade = models.ForeignKey(
        Grade,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="+",
    )
    summary = models.CharField(max_length=255)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
