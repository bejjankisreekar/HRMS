"""Trigger seams other apps call into — same shape as calling ``send_notification``.

Each hook is a thin, defensive wrapper: it never raises, so a rule-engine
problem can never break attendance marking or leave submission.
"""

from __future__ import annotations

from .models import Rule


def on_attendance_marked(record) -> None:
    from .engine import evaluate_rules

    org = getattr(record.user, "organization", None)
    if not org:
        return
    try:
        evaluate_rules(org, Rule.Trigger.ATTENDANCE_MARKED, subject=record)
    except Exception:
        pass


def on_leave_requested(leave_request) -> None:
    from .engine import evaluate_rules

    org = getattr(leave_request.user, "organization", None)
    if not org:
        return
    try:
        evaluate_rules(org, Rule.Trigger.LEAVE_REQUESTED, subject=leave_request)
    except Exception:
        pass
