"""Safe rule evaluation core.

Loads active rules for an organization/trigger, resolves facts, matches
conditions (AND within a group, OR across groups), and runs actions — every
action is individually try/excepted so one failing action never blocks its
siblings, and one failing rule never blocks other rules. A depth guard stops
an action that re-triggers evaluation (e.g. an UPDATE_STATUS action) from
looping forever.
"""

from __future__ import annotations

import time

from django.db import transaction

from .models import Rule, RuleExecutionLog
from .registry import ACTIONS, FACTS, OPERATORS, RuleContext

MAX_DEPTH = 3


def _condition_fact_keys(conditions) -> set:
    keys = set()
    for group in conditions or []:
        for cond in group or []:
            field = cond.get("field")
            if field:
                keys.add(field)
    return keys


def resolve_facts(context: RuleContext, fact_keys) -> dict:
    """Resolve each requested fact, catching exceptions per-fact.

    A fact that fails to resolve becomes ``None`` rather than crashing the
    whole evaluation — conditions on a ``None`` fact simply never match.
    """
    facts: dict = {}
    for key in fact_keys:
        defn = FACTS.get(key)
        if not defn:
            facts[key] = None
            continue
        try:
            facts[key] = defn.resolver(context)
        except Exception:
            facts[key] = None
    return facts


def evaluate_condition(cond: dict, facts: dict) -> bool:
    field = cond.get("field")
    value = facts.get(field)
    if value is None:
        return False
    op_fn = OPERATORS.get(cond.get("operator"))
    if not op_fn:
        return False
    try:
        return bool(op_fn(value, cond.get("value"), cond.get("value2")))
    except Exception:
        return False


def rule_matches(rule: Rule, facts: dict) -> bool:
    """AND within a condition group, OR across groups."""
    groups = rule.conditions or []
    for group in groups:
        if group and all(evaluate_condition(cond, facts) for cond in group):
            return True
    return False


def run_action(action_config: dict, context: RuleContext) -> dict:
    action_type = action_config.get("type")
    params = action_config.get("params") or {}
    defn = ACTIONS.get(action_type)
    if not defn:
        return {"type": action_type, "status": "failed", "detail": f"Unknown action type '{action_type}'."}
    if context.dry_run:
        return {
            "type": action_type,
            "status": "simulated",
            "detail": f"Would run {defn.label} with params {params}.",
        }
    try:
        result = dict(defn.handler(context, params) or {})
    except Exception as exc:
        return {"type": action_type, "status": "failed", "detail": str(exc)}
    result.setdefault("status", "success")
    result["type"] = action_type
    return result


def _evaluate_one(rule: Rule, organization, trigger_event: str, subject, extra: dict, dry_run: bool, actor) -> RuleExecutionLog:
    start = time.monotonic()
    subject_type = subject.__class__.__name__ if subject is not None else ""
    subject_id = str(getattr(subject, "pk", "")) if subject is not None else ""

    rule_extra = dict(extra)
    rule_extra["_depth"] = int(extra.get("_depth", 0)) + 1
    rule_extra["rule_id"] = str(rule.pk)
    rule_extra["subject_key"] = subject_id

    context = RuleContext(
        organization=organization,
        trigger_event=trigger_event,
        subject=subject,
        actor=actor,
        extra=rule_extra,
        dry_run=dry_run or rule.is_test_mode,
    )
    facts = resolve_facts(context, _condition_fact_keys(rule.conditions))
    matched = rule_matches(rule, facts)

    actions_result = []
    error = ""
    if matched:
        try:
            with transaction.atomic():
                for action_config in rule.actions or []:
                    actions_result.append(run_action(action_config, context))
        except Exception as exc:
            error = str(exc)

    return RuleExecutionLog.objects.create(
        organization=organization,
        rule=rule,
        rule_name_snapshot=rule.name,
        trigger_event=trigger_event,
        subject_type=subject_type,
        subject_id=subject_id,
        facts=facts,
        matched=matched,
        is_test_run=context.dry_run,
        actions_result=actions_result,
        error=error,
        duration_ms=int((time.monotonic() - start) * 1000),
    )


def evaluate_rules(
    organization,
    trigger_event: str,
    subject=None,
    *,
    extra: dict | None = None,
    dry_run: bool = False,
    actor=None,
) -> list:
    """Evaluate every ACTIVE rule for (organization, trigger_event) against subject.

    Always writes one ``RuleExecutionLog`` per rule considered (matched or
    not) — this is the execution-log requirement. Rule CRUD audit entries
    live separately in ``RuleAuditLog``.
    """
    if not organization:
        return []

    extra = dict(extra or {})
    if int(extra.get("_depth", 0)) >= MAX_DEPTH:
        return []

    rules = list(
        Rule.objects.filter(
            organization=organization, trigger_event=trigger_event, status=Rule.Status.ACTIVE
        ).order_by("priority", "created_at")
    )
    return [_evaluate_one(rule, organization, trigger_event, subject, extra, dry_run, actor) for rule in rules]


def evaluate_single_rule(rule: Rule, subject=None, *, dry_run: bool = True, actor=None) -> RuleExecutionLog:
    """Evaluate one rule regardless of its status — used by the Test page so a
    DRAFT rule can be tried out before it's ever turned on."""
    return _evaluate_one(rule, rule.organization, rule.trigger_event, subject, {}, dry_run, actor)
