from __future__ import annotations

from typing import Any, Mapping


def status_from_counts(*, blocking: int = 0, warning: int = 0, healthy: bool = False) -> str:
    if blocking > 0:
        return "needs_action"
    if warning > 0:
        return "watch"
    if healthy:
        return "ready"
    return "pending"


def build_personal_research_loop(
    *,
    generated_at: Any,
    data_health: Mapping[str, Any],
    coverage: Mapping[str, Any],
    cycle_runs: Mapping[str, Any],
    feedback_preview: Mapping[str, Any],
    quality_preview: Mapping[str, Any],
    latest_analysis: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    data_summary = data_health.get("summary", {}) if isinstance(data_health.get("summary"), Mapping) else {}
    coverage_missing = coverage.get("missing_counts", {}) if isinstance(coverage.get("missing_counts"), Mapping) else {}
    cycle_summary = cycle_runs.get("summary", {}) if isinstance(cycle_runs.get("summary"), Mapping) else {}
    feedback_rows = feedback_preview.get("feedback", []) if isinstance(feedback_preview.get("feedback"), list) else []
    quality_totals = quality_preview.get("totals", {}) if isinstance(quality_preview.get("totals"), Mapping) else {}
    latest_analysis = latest_analysis or {}

    data_failure_count = int(data_summary.get("failure_count", 0) or 0)
    data_pending_count = int(data_summary.get("pending_count", 0) or 0)
    coverage_missing_total = sum(int(value or 0) for value in coverage_missing.values())
    feedback_pending = int(feedback_preview.get("feedback_planned", 0) or 0) + int(feedback_preview.get("feedback_skipped", 0) or 0)
    graph_noise = int(quality_totals.get("event_duplicates", 0) or 0) + int(quality_totals.get("relationship_duplicates", 0) or 0) + int(quality_totals.get("entity_merge_candidates", 0) or 0)

    sections = [
        {
            "section": "data_health",
            "title": "数据健康中心",
            "status": status_from_counts(blocking=data_failure_count, warning=data_pending_count, healthy=bool(data_health.get("sources"))),
            "summary": {
                "source_count": data_summary.get("source_count", 0),
                "failure_count": data_failure_count,
                "pending_count": data_pending_count,
                "next_action_count": data_summary.get("next_action_count", 0),
            },
            "primary_action": {"action": "review_data_health", "endpoint": "/api/data-health/summary"},
        },
        {
            "section": "personal_workspace",
            "title": "个人研究桌面",
            "status": status_from_counts(warning=coverage_missing_total, healthy=bool(coverage.get("issuer_count", 0))),
            "summary": {
                "issuer_count": coverage.get("issuer_count", 0),
                "average_coverage_score": coverage.get("average_coverage_score", 0),
                "missing_section_count": coverage_missing_total,
                "latest_cycle_run_id": cycle_summary.get("latest_run_id", ""),
            },
            "primary_action": {"action": "open_company_workspace", "endpoint": "/api/company-intelligence/{symbol}"},
        },
        {
            "section": "realization_scoring",
            "title": "结论兑现评分",
            "status": status_from_counts(warning=feedback_pending, healthy=bool(feedback_rows)),
            "summary": {
                "target_count": feedback_preview.get("target_count", 0),
                "feedback_planned": feedback_preview.get("feedback_planned", 0),
                "feedback_skipped": feedback_preview.get("feedback_skipped", 0),
                "sample_statuses": [row.get("realization_status") or row.get("status") for row in feedback_rows[:5]],
            },
            "primary_action": {"action": "score_simulation_feedback", "endpoint": "/api/simulation-feedback/performance/update"},
        },
        {
            "section": "relationship_denoise",
            "title": "关系图谱降噪",
            "status": status_from_counts(warning=graph_noise, healthy=bool(quality_preview.get("issuer_count", 0))),
            "summary": {
                "issuer_count": quality_preview.get("issuer_count", 0),
                "event_duplicates": quality_totals.get("event_duplicates", 0),
                "relationship_duplicates": quality_totals.get("relationship_duplicates", 0),
                "entity_merge_candidates": quality_totals.get("entity_merge_candidates", 0),
                "source_quality_scored": quality_totals.get("source_quality_scored", 0),
            },
            "primary_action": {"action": "preview_quality_reconciliation", "endpoint": "/api/company-database/quality/reconcile"},
        },
    ]
    blocking_sections = [section["section"] for section in sections if section["status"] == "needs_action"]
    warning_sections = [section["section"] for section in sections if section["status"] == "watch"]
    return {
        "schema_id": "personal-research-loop-overview-v1",
        "status": "needs_action" if blocking_sections else ("watch" if warning_sections else "ready"),
        "generated_at": generated_at,
        "sections": sections,
        "summary": {
            "section_count": len(sections),
            "blocking_sections": blocking_sections,
            "warning_sections": warning_sections,
            "latest_analysis_status": latest_analysis.get("status", ""),
            "latest_market_date": latest_analysis.get("latest_market_date", ""),
        },
        "source_payloads": {
            "data_health": data_health,
            "coverage": coverage,
            "cycle_runs": cycle_runs,
            "feedback_preview": feedback_preview,
            "quality_preview": quality_preview,
            "latest_analysis": latest_analysis,
        },
        "paper_only": True,
        "live_execution_allowed": False,
        "usage_boundary": "personal_research_loop_overview_is_local_research_read_model_paper_feedback_only_no_broker_execution",
    }
