"""Pure source-review escalation helpers (governance domain).

Extracted from ``SystemService`` per the SystemService Modularization ADR.
These functions derive escalation policy, reasons, severity, routing channel,
target, and recommended action from plain reminder/filter mappings. They hold
no ``SystemService`` state (store, audit, permissions); ``SystemService`` keeps
the same method names as facades that delegate here.
"""

from __future__ import annotations

from typing import Any, Mapping


def escalation_policy(filters: Mapping[str, Any]) -> dict[str, Any]:
    default_channels = {
        "critical": "pager",
        "high": "source_review_outbox",
        "medium": "source_review_outbox",
        "low": "review_queue",
    }
    default_targets = {
        "critical": "risk-compliance-source-review",
        "high": "risk-compliance-source-review",
        "medium": "source-review-owner-board",
        "low": "source-review-queue",
    }
    channels = dict(default_channels)
    targets = dict(default_targets)
    channels.update({str(key): str(value) for key, value in dict(filters.get("channels", {})).items()})
    targets.update({str(key): str(value) for key, value in dict(filters.get("targets", {})).items()})
    return {
        "channels": channels,
        "targets": targets,
        "owner_roles": {
            "critical": "风险/合规",
            "high": "风险/合规",
            "medium": "数据工程",
            "low": "数据工程",
        },
        "thresholds": {
            "critical_days_overdue": int(filters.get("critical_days_overdue", 30)),
            "high_days_overdue": int(filters.get("high_days_overdue", 7)),
            "due_soon_high_risk_days": int(filters.get("due_soon_high_risk_days", 7)),
        },
        "retry_policy": {
            "max_attempts": int(filters.get("max_delivery_attempts", 3)),
            "backoff": str(filters.get("delivery_backoff", "manual_or_external_sender")),
        },
    }


def escalation_reasons(reminder: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if reminder.get("missing_review"):
        reasons.append("missing_review")
    if reminder.get("status") == "overdue":
        reasons.append("review_overdue")
    elif reminder.get("status") == "due_soon":
        reasons.append("review_due_soon")
    if reminder.get("risk_level") == "red":
        reasons.append("red_source")
    elif reminder.get("risk_level") == "yellow":
        reasons.append("yellow_source")
    for reason in reminder.get("blocked_reasons", []):
        reasons.append(str(reason))
    return sorted(set(reasons))


def primary_escalation_reason(reasons: list[str]) -> str:
    priority = [
        "red_source_manual_reference_only",
        "red_source",
        "latest_source_review_rejected",
        "latest_source_usage_scope_blocked",
        "latest_source_publicness_unclear",
        "latest_source_robots_blocked",
        "latest_source_tos_needs_review",
        "review_overdue",
        "missing_review",
        "review_due_soon",
        "yellow_source",
    ]
    for reason in priority:
        if reason in reasons:
            return reason
    return reasons[0] if reasons else "review_due_soon"


def escalation_severity(
    reminder: Mapping[str, Any],
    reasons: list[str],
    days_overdue: int,
    days_until_due: int,
    policy: Mapping[str, Any],
) -> str:
    thresholds = policy.get("thresholds", {})
    critical_days = int(thresholds.get("critical_days_overdue", 30)) if isinstance(thresholds, Mapping) else 30
    high_days = int(thresholds.get("high_days_overdue", 7)) if isinstance(thresholds, Mapping) else 7
    high_risk_due_days = int(thresholds.get("due_soon_high_risk_days", 7)) if isinstance(thresholds, Mapping) else 7
    critical_reasons = {
        "red_source",
        "red_source_manual_reference_only",
        "latest_source_review_rejected",
        "latest_source_usage_scope_blocked",
    }
    high_reasons = {
        "latest_source_publicness_unclear",
        "latest_source_robots_blocked",
        "latest_source_tos_needs_review",
    }
    if any(reason in critical_reasons for reason in reasons) or days_overdue >= critical_days:
        return "critical"
    if reminder.get("status") == "overdue" and (days_overdue >= high_days or any(reason in high_reasons for reason in reasons)):
        return "high"
    if reminder.get("risk_level") == "yellow" and reminder.get("status") == "due_soon" and days_until_due <= high_risk_due_days:
        return "high"
    if reminder.get("status") == "overdue" or any(reason in high_reasons for reason in reasons):
        return "medium"
    return "low"


def escalation_channel(severity: str, policy: Mapping[str, Any]) -> str:
    return str(policy.get("channels", {}).get(severity, "source_review_outbox"))


def escalation_target(severity: str, policy: Mapping[str, Any], reminder: Mapping[str, Any]) -> str:
    targets = policy.get("targets", {})
    default_target = str(targets.get(severity, "source-review-owner-board")) if isinstance(targets, Mapping) else "source-review-owner-board"
    return str(default_target or reminder.get("review_owner") or reminder.get("review_owner_role") or "source-review-owner-board")


def escalation_action(reminder: Mapping[str, Any], reason: str, severity: str) -> str:
    if reason in {"red_source", "red_source_manual_reference_only"}:
        return "Keep the source manual-reference-only and complete risk/compliance review before any automated use."
    if reason == "latest_source_review_rejected":
        return "Block automated use, resolve rejected review findings, and record a new approved source review."
    if reason == "latest_source_usage_scope_blocked":
        return "Clarify allowed usage scope and keep derived automation disabled until risk approval is recorded."
    if reason == "latest_source_publicness_unclear":
        return "Confirm publicness or move the source to metadata-only manual reference before continued use."
    if reason in {"latest_source_robots_blocked", "latest_source_robots_needs_review"}:
        return "Recheck robots and source terms before any automated collection or cache refresh."
    if reason == "latest_source_tos_needs_review":
        return "Review source TOS and update the governance record before the next ingestion run."
    if reason == "missing_review":
        return "Assign an owner and complete the initial source review with publicness, TOS, robots, and usage scope fields."
    if reason == "review_overdue":
        return "Complete the overdue source review and attach evidence URI or review notes for audit."
    if severity == "low":
        return "Schedule the upcoming source review before the due date."
    return "Resolve source review blockers and notify the owner board."
