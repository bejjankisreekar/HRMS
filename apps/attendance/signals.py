"""Attendance post-save signals."""

from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import AttendanceRecord

_ABSENT_STATUSES = {AttendanceRecord.Status.ABSENT, AttendanceRecord.Status.HALF_DAY}


@receiver(post_save, sender=AttendanceRecord)
def handle_absent_attendance(sender, instance, **kwargs):
    """On every save, sync the absent-deduction for this record.

    Always reverse any prior deduction first, then re-apply if the new status
    warrants it.  This handles all transitions (ABSENT→PRESENT, ABSENT→HALF_DAY,
    PRESENT→ABSENT, etc.) correctly without double-deducting.
    """
    try:
        from apps.leaves.services import apply_absent_deduction, reverse_absent_deduction

        # Reverse whatever existed before (no-op if nothing exists)
        reverse_absent_deduction(instance.pk)

        # Re-apply if status still requires a deduction
        if instance.status in _ABSENT_STATUSES:
            apply_absent_deduction(instance)
    except Exception:
        # Never let a signal crash the attendance save
        pass

    try:
        from apps.ruleengine.hooks import on_attendance_marked

        on_attendance_marked(instance)
    except Exception:
        # Never let a signal crash the attendance save
        pass
