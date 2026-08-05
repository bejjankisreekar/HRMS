"""Plain dict serializers shared by the server-rendered pages and JSON APIs."""

from __future__ import annotations

from .registry import ACTIONS, FACTS


def rule_to_dict(rule) -> dict:
    return {
        "id": str(rule.pk),
        "name": rule.name,
        "description": rule.description,
        "trigger_event": rule.trigger_event,
        "trigger_event_display": rule.get_trigger_event_display(),
        "status": rule.status,
        "priority": rule.priority,
        "conditions": rule.conditions,
        "actions": rule.actions,
        "is_test_mode": rule.is_test_mode,
        "created_at": rule.created_at.isoformat(),
        "updated_at": rule.updated_at.isoformat(),
    }


def facts_metadata() -> list:
    return [
        {"key": key, "label": defn.label, "value_type": defn.value_type, "choices": list(defn.choices)}
        for key, defn in FACTS.items()
    ]


def actions_metadata() -> list:
    return [
        {"key": key, "label": defn.label, "param_schema": defn.param_schema}
        for key, defn in ACTIONS.items()
    ]


def execution_log_to_dict(log) -> dict:
    return {
        "id": str(log.pk),
        "rule_id": str(log.rule_id) if log.rule_id else None,
        "rule_name": log.rule_name_snapshot,
        "trigger_event": log.trigger_event,
        "subject_type": log.subject_type,
        "subject_id": log.subject_id,
        "facts": log.facts,
        "matched": log.matched,
        "is_test_run": log.is_test_run,
        "actions_result": log.actions_result,
        "error": log.error,
        "duration_ms": log.duration_ms,
        "created_at": log.created_at.isoformat(),
    }


def audit_log_to_dict(log) -> dict:
    return {
        "id": str(log.pk),
        "action": log.action,
        "action_display": log.get_action_display(),
        "actor": (log.actor.display_name or log.actor.username) if log.actor else None,
        "object_id": str(log.object_id) if log.object_id else None,
        "summary": log.summary,
        "details": log.details,
        "created_at": log.created_at.isoformat(),
    }
