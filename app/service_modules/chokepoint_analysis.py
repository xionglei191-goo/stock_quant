"""Pure chokepoint-research helpers (research/AI workflows domain).

Extracted from ``SystemService`` per the SystemService Modularization ADR.
These are deterministic functions of their arguments only (candidate/issue
shaping, step summaries, prior-output stitching, light evidence matching,
step indexing). They hold no ``SystemService`` state; ``SystemService`` keeps
the same method names as thin facades that delegate here.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any, Mapping

from ..errors import NotFoundError
from ..models import ChokepointResearchRun
from ..research_reports import safe_source_part
from ..utils import utcnow

if TYPE_CHECKING:  # pragma: no cover - typing only
    from ..models import Evidence


def verification_candidates(run: ChokepointResearchRun) -> list[dict[str, Any]]:
    candidates: dict[str, dict[str, Any]] = {}
    for issue in run.issues:
        if issue.get("status") == "closed":
            continue
        reason = f"{issue.get('step')}: {issue.get('message')} {issue.get('suggestion')}"
        task_type = "chokepoint_verification"
        task_id = f"rtask_{safe_source_part(run.run_id + '|' + str(issue.get('issue_id', reason)))}"
        candidates[task_id] = {
            "task_id": task_id,
            "task_type": task_type,
            "source": "chokepoint_research",
            "reason": reason,
            "status": "open",
            "priority": 80 if issue.get("severity") == "block" else 60,
            "required_slots": ["source_url", "published_date", "source_type", "confidence", "fact_layer"],
            "metadata": {
                "run_id": run.run_id,
                "topic": run.topic,
                "step_id": issue.get("step_id", ""),
                "usage_boundary": "research_only_not_trade_signal",
                "automation_allowed": False,
                "live_execution_allowed": False,
            },
        }
    for step in run.steps:
        text = str(step.get("output_text", ""))
        for index, line in enumerate([line.strip() for line in text.splitlines() if re.search(r"unknown|未知|待验证|无法确认|needs_verification|P0", line, re.I)][:8]):
            task_id = f"rtask_{safe_source_part(run.run_id + '|' + str(step.get('step_id')) + '|' + str(index) + '|' + line[:80])}"
            candidates.setdefault(
                task_id,
                {
                    "task_id": task_id,
                    "task_type": "chokepoint_verification",
                    "source": "chokepoint_research",
                    "reason": line[:500],
                    "status": "open",
                    "priority": 70,
                    "required_slots": ["official_source", "source_url", "published_date", "verification_result"],
                    "metadata": {
                        "run_id": run.run_id,
                        "topic": run.topic,
                        "step_id": step.get("step_id", ""),
                        "usage_boundary": "research_only_not_trade_signal",
                        "automation_allowed": False,
                        "live_execution_allowed": False,
                    },
                },
            )
    if not candidates:
        task_id = f"rtask_{safe_source_part(run.run_id + '|manual_review')}"
        candidates[task_id] = {
            "task_id": task_id,
            "task_type": "chokepoint_verification",
            "source": "chokepoint_research",
            "reason": "人工复核瓶颈研究来源台账、事实分层和证伪条件。",
            "status": "open",
            "priority": 50,
            "required_slots": ["source_ledger_review", "falsification_review"],
            "metadata": {"run_id": run.run_id, "topic": run.topic, "usage_boundary": "research_only_not_trade_signal"},
        }
    return list(candidates.values())


def steps_summary(run: ChokepointResearchRun) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for step in run.steps:
        quality = dict(step.get("evidence_quality") or {})
        rows.append(
            {
                "step_id": step.get("step_id", ""),
                "label": step.get("label", ""),
                "status": step.get("status", "pending"),
                "summary": step.get("summary", ""),
                "llm_run_id": step.get("llm_run_id", ""),
                "url_count": quality.get("url_count", 0),
                "confirmed_count": quality.get("confirmed_count", 0),
                "inferred_count": quality.get("inferred_count", 0),
                "speculative_count": quality.get("speculative_count", 0),
                "unknown_count": quality.get("unknown_count", 0),
                "fallback_used": quality.get("fallback_used", ""),
                "issue_count": len(step.get("issues") or []),
            }
        )
    return rows


def research_context(run: "ChokepointResearchRun | Mapping[str, Any]") -> dict[str, Any]:
    if isinstance(run, ChokepointResearchRun):
        return {
            "topic": run.topic,
            "ticker": run.ticker,
            "theme": run.theme,
            "chokepoint_node": run.chokepoint_node,
            "playbook": run.playbook,
            "mode": run.mode,
        }
    return {
        "topic": str(run.get("topic", run.get("theme", ""))),
        "ticker": str(run.get("ticker", "")),
        "theme": str(run.get("theme", "")),
        "chokepoint_node": str(run.get("chokepoint_node", run.get("node", ""))),
        "playbook": str(run.get("playbook", "generic")),
        "mode": str(run.get("mode", "strict")),
    }


def light_evidence_match(evidence: "Evidence", topic_terms: list[str]) -> bool:
    haystack = " ".join(
        [
            evidence.section,
            evidence.document_id,
            evidence.security_id,
            evidence.issuer_id,
            evidence.chain_id,
            " ".join(evidence.evidence_topics[:8]),
            " ".join(evidence.risk_tags[:8]),
            " ".join(evidence.financial_metric_tags[:8]),
        ]
    ).lower()
    return any(term in haystack for term in topic_terms)


def issue(step: Mapping[str, Any], severity: str, message: str, suggestion: str) -> dict[str, Any]:
    basis = f"{step.get('step_id')}|{severity}|{message}"
    return {
        "issue_id": f"cpissue_{safe_source_part(basis)}",
        "step_id": str(step.get("step_id", "")),
        "step": str(step.get("label", step.get("step_id", ""))),
        "severity": severity,
        "message": message,
        "suggestion": suggestion,
        "status": "open",
        "created_at": utcnow(),
    }


def prior_outputs(run: ChokepointResearchRun, step_index: int) -> str:
    blocks = []
    for step in run.steps[:step_index]:
        output = str(step.get("output_text", "")).strip()
        if output:
            blocks.append(f"## {step.get('label')}\n{output[:2500]}")
    return "\n\n".join(blocks) if blocks else "无"


def step_index(run: ChokepointResearchRun, step_id: str) -> int:
    for index, step in enumerate(run.steps):
        if step.get("step_id") == step_id:
            return index
    raise NotFoundError(f"chokepoint research step {step_id} not found")


def completed(steps: list[dict[str, Any]]) -> bool:
    return all(str(step.get("status")) in {"done", "review"} for step in steps)
