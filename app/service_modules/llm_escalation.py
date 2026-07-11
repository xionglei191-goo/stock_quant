"""Pure LLM task review / escalation helpers (research and AI workflows domain).

Extracted from ``SystemService`` per the SystemService Modularization ADR.
These functions derive review reasons, severity, escalation policy, and routing
for LLM task runs from plain run/template/filter inputs. They hold no
``SystemService`` state; ``SystemService`` keeps the same method names as
facades that delegate here.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Mapping

from ..utils import env_float

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..models import LLMTaskRun, LLMTaskTemplate


def task_review_reasons(run: "LLMTaskRun", template: "LLMTaskTemplate | None") -> list[str]:
    reasons: list[str] = []
    if run.human_review_required:
        reasons.append("human_review_required")
    if run.status != "succeeded":
        reasons.append(f"status_{run.status}")
    if run.fallback_used:
        reasons.append(f"fallback_{run.fallback_used}")
    if run.error:
        reasons.append("upstream_error")
    if template and template.risk_level in {"high", "critical"}:
        reasons.append(f"risk_{template.risk_level}")
    if template and template.max_latency_ms and run.latency_ms > template.max_latency_ms:
        reasons.append("latency_sla_breach")
    if run.estimated_cost > env_float("AI_QUANT_LLM_REVIEW_COST_THRESHOLD", 1.0, minimum=0.0):
        reasons.append("cost_threshold_breach")
    return sorted(set(reasons))


def task_review_severity(reasons: list[str], template: "LLMTaskTemplate | None") -> str:
    if "risk_critical" in reasons or "status_failed" in reasons:
        return "critical"
    if template and template.risk_level == "high":
        return "high"
    if any(item in reasons for item in {"status_needs_review", "fallback_manual_review", "latency_sla_breach", "cost_threshold_breach"}):
        return "high"
    if any(item.startswith("fallback_") or item == "upstream_error" for item in reasons):
        return "medium"
    return "low"


def escalation_policy(filters: Mapping[str, Any]) -> dict[str, Any]:
    default_channels = {
        "critical": "pager",
        "high": "slack",
        "medium": "email",
        "low": "review_queue",
    }
    default_targets = {
        "critical": "nlp-ml-oncall",
        "high": "llm-ops-risk",
        "medium": "llm-review-queue",
        "low": "analyst-review-queue",
    }
    channels = dict(default_channels)
    targets = dict(default_targets)
    channels.update({str(key): str(value) for key, value in dict(filters.get("channels", {})).items()})
    targets.update({str(key): str(value) for key, value in dict(filters.get("targets", {})).items()})
    return {
        "channels": channels,
        "targets": targets,
        "owner_roles": {
            "critical": "NLP/ML 负责人",
            "high": "NLP/ML 负责人",
            "medium": "分析师",
            "low": "分析师",
        },
        "retry_policy": {
            "max_attempts": int(filters.get("max_delivery_attempts", 3)),
            "backoff": str(filters.get("delivery_backoff", "manual_or_external_sender")),
        },
    }


def primary_escalation_reason(reasons: list[str]) -> str:
    priority = [
        "risk_critical",
        "status_failed",
        "latency_sla_breach",
        "cost_threshold_breach",
        "risk_high",
        "status_needs_review",
        "fallback_manual_review",
        "fallback_rule_summary",
        "upstream_error",
        "human_review_required",
    ]
    for item in priority:
        if item in reasons:
            return item
    return reasons[0] if reasons else ""


def escalation_owner(severity: str, policy: Mapping[str, Any]) -> str:
    return str(policy.get("owner_roles", {}).get(severity, "NLP/ML 负责人"))


def escalation_channel(severity: str, policy: Mapping[str, Any]) -> str:
    return str(policy.get("channels", {}).get(severity, "review_queue"))


def escalation_target(severity: str, policy: Mapping[str, Any]) -> str:
    return str(policy.get("targets", {}).get(severity, "llm-review-queue"))
