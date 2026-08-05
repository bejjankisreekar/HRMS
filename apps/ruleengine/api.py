"""JSON APIs backing the Rule Builder UI, mounted at /api/rule-engine/.

Plain Django ``View`` + ``JsonResponse``, mirroring
``apps/payroll/deductions_views.py``'s ``_DeductionsAPI`` base pattern rather
than introducing a new DRF convention for this app.
"""

from __future__ import annotations

import json

from django.http import JsonResponse
from django.shortcuts import get_object_or_404
from django.views import View

from apps.accounts.models import User

from .audit import record_rule_action
from .engine import evaluate_rules, evaluate_single_rule
from .models import Rule, RuleAuditLog, RuleExecutionLog
from .registry import OPERATOR_LABELS, OPERATORS_BY_TYPE
from .serializers import (
    actions_metadata,
    audit_log_to_dict,
    execution_log_to_dict,
    facts_metadata,
    rule_to_dict,
)


class _RuleEngineAPI(View):
    """Base: Admin/HR org members only."""

    def dispatch(self, request, *args, **kwargs):
        u = request.user
        if not (
            u.is_authenticated
            and getattr(u, "organization_id", None)
            and u.role in (User.Role.ADMIN, User.Role.HR)
        ):
            return JsonResponse({"error": "Forbidden"}, status=403)
        return super().dispatch(request, *args, **kwargs)


def _validate_rule_payload(payload: dict) -> list:
    errors = []
    if not (payload.get("name") or "").strip():
        errors.append("Name is required.")
    if payload.get("trigger_event") not in dict(Rule.Trigger.choices):
        errors.append("A valid trigger event is required.")
    if payload.get("status") and payload.get("status") not in dict(Rule.Status.choices):
        errors.append("Invalid status.")
    if not isinstance(payload.get("conditions", []), list):
        errors.append("conditions must be a list.")
    if not isinstance(payload.get("actions", []), list):
        errors.append("actions must be a list.")
    return errors


class RegistryMetadataAPI(_RuleEngineAPI):
    def get(self, request):
        return JsonResponse(
            {
                "facts": facts_metadata(),
                "actions": actions_metadata(),
                "operators": {"labels": OPERATOR_LABELS, "by_type": OPERATORS_BY_TYPE},
                "triggers": list(Rule.Trigger.choices),
            }
        )


class RuleListCreateAPI(_RuleEngineAPI):
    def get(self, request):
        org = request.user.organization
        rules = Rule.objects.filter(organization=org).order_by("priority", "created_at")
        return JsonResponse({"rules": [rule_to_dict(r) for r in rules]})

    def post(self, request):
        org = request.user.organization
        payload = json.loads(request.body or "{}")
        errors = _validate_rule_payload(payload)
        if errors:
            return JsonResponse({"errors": errors}, status=400)
        rule = Rule.objects.create(
            organization=org,
            name=payload["name"].strip(),
            description=payload.get("description", ""),
            trigger_event=payload["trigger_event"],
            status=payload.get("status", Rule.Status.DRAFT),
            priority=payload.get("priority", 100),
            conditions=payload.get("conditions", []),
            actions=payload.get("actions", []),
            is_test_mode=bool(payload.get("is_test_mode", False)),
            created_by=request.user,
            updated_by=request.user,
        )
        record_rule_action(
            org, request.user, RuleAuditLog.Action.CREATED, f"Created rule '{rule.name}'",
            rule.pk, request=request,
        )
        return JsonResponse({"rule": rule_to_dict(rule)}, status=201)


class RuleDetailAPI(_RuleEngineAPI):
    def _get_rule(self, request, pk):
        return get_object_or_404(Rule, organization=request.user.organization, pk=pk)

    def get(self, request, pk):
        return JsonResponse({"rule": rule_to_dict(self._get_rule(request, pk))})

    def put(self, request, pk):
        rule = self._get_rule(request, pk)
        payload = json.loads(request.body or "{}")
        errors = _validate_rule_payload(payload)
        if errors:
            return JsonResponse({"errors": errors}, status=400)

        old_status = rule.status
        rule.name = payload["name"].strip()
        rule.description = payload.get("description", "")
        rule.trigger_event = payload["trigger_event"]
        rule.status = payload.get("status", rule.status)
        rule.priority = payload.get("priority", rule.priority)
        rule.conditions = payload.get("conditions", [])
        rule.actions = payload.get("actions", [])
        rule.is_test_mode = bool(payload.get("is_test_mode", False))
        rule.updated_by = request.user
        rule.save()

        record_rule_action(
            rule.organization, request.user, RuleAuditLog.Action.UPDATED, f"Updated rule '{rule.name}'",
            rule.pk, request=request,
        )
        if old_status != rule.status:
            action = RuleAuditLog.Action.ENABLED if rule.status == Rule.Status.ACTIVE else RuleAuditLog.Action.DISABLED
            record_rule_action(
                rule.organization, request.user, action, f"Rule '{rule.name}' set to {rule.status}",
                rule.pk, request=request,
            )
        return JsonResponse({"rule": rule_to_dict(rule)})

    def delete(self, request, pk):
        rule = self._get_rule(request, pk)
        name, rule_pk = rule.name, rule.pk
        org = rule.organization
        rule.delete()
        record_rule_action(
            org, request.user, RuleAuditLog.Action.DELETED, f"Deleted rule '{name}'", rule_pk, request=request,
        )
        return JsonResponse({"ok": True})


class RuleStatusAPI(_RuleEngineAPI):
    """Quick enable/disable toggle from the list page."""

    def post(self, request, pk):
        rule = get_object_or_404(Rule, organization=request.user.organization, pk=pk)
        payload = json.loads(request.body or "{}")
        new_status = payload.get("status")
        if new_status not in (Rule.Status.ACTIVE, Rule.Status.DISABLED):
            return JsonResponse({"error": "status must be ACTIVE or DISABLED"}, status=400)
        rule.status = new_status
        rule.updated_by = request.user
        rule.save(update_fields=["status", "updated_by", "updated_at"])
        action = RuleAuditLog.Action.ENABLED if new_status == Rule.Status.ACTIVE else RuleAuditLog.Action.DISABLED
        record_rule_action(
            rule.organization, request.user, action, f"Rule '{rule.name}' set to {new_status}",
            rule.pk, request=request,
        )
        return JsonResponse({"rule": rule_to_dict(rule)})


class RuleReorderAPI(_RuleEngineAPI):
    """Bulk priority update: ``{"order": [{"id": "...", "priority": 10}, ...]}``."""

    def post(self, request):
        org = request.user.organization
        payload = json.loads(request.body or "{}")
        updated = []
        for item in payload.get("order", []):
            rule = Rule.objects.filter(organization=org, pk=item.get("id")).first()
            if not rule:
                continue
            rule.priority = item.get("priority", rule.priority)
            rule.updated_by = request.user
            rule.save(update_fields=["priority", "updated_by", "updated_at"])
            updated.append(rule)
        if updated:
            record_rule_action(
                org, request.user, RuleAuditLog.Action.PRIORITY_CHANGED,
                f"Reordered {len(updated)} rule(s)", None, request=request,
            )
        return JsonResponse({"rules": [rule_to_dict(r) for r in updated]})


def _resolve_test_subject(org, subject_type, subject_id):
    if not subject_type or not subject_id:
        return None
    if subject_type == "User":
        return User.objects.filter(organization=org, pk=subject_id).first()
    if subject_type == "AttendanceRecord":
        from apps.attendance.models import AttendanceRecord

        return AttendanceRecord.objects.filter(user__organization=org, pk=subject_id).first()
    if subject_type == "LeaveRequest":
        from apps.leaves.models import LeaveRequest

        return LeaveRequest.objects.filter(user__organization=org, pk=subject_id).first()
    return None


class RuleTestAPI(_RuleEngineAPI):
    """Dry-run one rule (regardless of status) or every rule for a trigger, against a sample subject."""

    def post(self, request, pk=None):
        org = request.user.organization
        payload = json.loads(request.body or "{}")
        subject = _resolve_test_subject(org, payload.get("subject_type"), payload.get("subject_id"))

        if pk:
            rule = get_object_or_404(Rule, organization=org, pk=pk)
            log = evaluate_single_rule(rule, subject=subject, dry_run=True, actor=request.user)
            record_rule_action(
                org, request.user, RuleAuditLog.Action.TESTED, f"Tested rule '{rule.name}'",
                rule.pk, request=request,
            )
            return JsonResponse({"logs": [execution_log_to_dict(log)]})

        trigger_event = payload.get("trigger_event")
        if trigger_event not in dict(Rule.Trigger.choices):
            return JsonResponse({"error": "A valid trigger_event is required."}, status=400)
        logs = evaluate_rules(org, trigger_event, subject=subject, dry_run=True, actor=request.user)
        return JsonResponse({"logs": [execution_log_to_dict(log) for log in logs]})


class ExecutionLogListAPI(_RuleEngineAPI):
    def get(self, request):
        org = request.user.organization
        qs = RuleExecutionLog.objects.filter(organization=org)
        rule_id = request.GET.get("rule")
        if rule_id:
            qs = qs.filter(rule_id=rule_id)
        matched = request.GET.get("matched")
        if matched in ("true", "false"):
            qs = qs.filter(matched=(matched == "true"))
        return JsonResponse({"logs": [execution_log_to_dict(log) for log in qs[:200]]})


class AuditLogListAPI(_RuleEngineAPI):
    def get(self, request):
        org = request.user.organization
        qs = RuleAuditLog.objects.filter(organization=org)[:200]
        return JsonResponse({"logs": [audit_log_to_dict(log) for log in qs]})
