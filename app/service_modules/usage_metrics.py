from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any, Protocol

from ..models import UsageMetric
from ..utils import to_plain, utcnow


VALID_ORIGINS = frozenset({"ui", "scheduled", "acceptance", "api"})
AUTOMATION_ORIGINS = frozenset({"scheduled", "acceptance"})

USAGE_FEATURE_MAP = (
    ("/api/company-intelligence", "company_intelligence"),
    ("/api/company-profiles", "company_profile"),
    ("/api/company-events", "company_events"),
    ("/api/company-relationships", "company_relationships"),
    ("/api/company-database", "company_database"),
    ("/api/company-financial-metrics", "company_financials"),
    ("/api/graph", "knowledge_graph"),
    ("/api/hotspots", "hotspot_expansion"),
    ("/api/hotspot-lexicons", "hotspot_expansion"),
    ("/api/industry-chains", "industry_chain"),
    ("/api/macro-themes", "macro_theme"),
    ("/api/research/answers", "research_answers"),
    ("/api/research/tasks", "research_tasks"),
    ("/api/research-reports", "research_reports"),
    ("/api/research-report-viewpoints", "research_viewpoints"),
    ("/api/research-report-forecasts", "research_forecasts"),
    ("/api/analyst-profiles", "analyst_reliability"),
    ("/api/analyst-reliability-scores", "analyst_reliability"),
    ("/api/observation-items", "observation_items"),
    ("/api/analysis-conclusions", "analysis_conclusions"),
    ("/api/simulation-feedback", "simulation_feedback"),
    ("/api/market-data", "market_data"),
    ("/api/13f", "institutional_holdings"),
    ("/api/disclosure-events", "disclosure_events"),
    ("/api/portfolio", "portfolio"),
    ("/api/entity-mappings", "entity_mappings"),
    ("/api/evidence", "evidence"),
    ("/api/extractions", "evidence"),
    ("/api/search", "search"),
    ("/api/dashboard", "dashboard"),
    ("/api/analysis/latest", "latest_analysis"),
    ("/api/llm", "llm"),
    ("/api/orchestration", "orchestration"),
    ("/api/lineage", "orchestration"),
    ("/api/model-versions", "orchestration"),
    ("/api/governance", "governance"),
    ("/api/observability", "observability"),
    ("/api/readiness", "readiness"),
    ("/api/benchmarks", "benchmarks"),
    ("/api/document-parsing", "document_parsing"),
    ("/api/ingestion", "ingestion"),
    ("/api/connectors", "connectors"),
    ("/api/decision-packs", "committee"),
    ("/api/approvals", "committee"),
    ("/api/execution-intents", "paper_execution"),
    ("/api/simulated-executions", "paper_execution"),
    ("/api/operating-reports", "operating_reports"),
    ("/api/strategy-replays", "strategy_replays"),
)


class UsageStore(Protocol):
    usage_metrics: dict[str, UsageMetric]

    def commit(self) -> None: ...


def normalize_origin(value: Any) -> str:
    origin = str(value or "").strip().lower()
    return origin if origin in VALID_ORIGINS else "api"


def feature_for_path(path: Any) -> str:
    normalized = str(path or "")
    for skip in ("/api/health", "/api/metrics", "/api/usage-metrics"):
        if normalized.startswith(skip):
            return ""
    for prefix, feature in USAGE_FEATURE_MAP:
        if normalized.startswith(prefix):
            return feature
    return "other" if normalized.startswith("/api/") else ""


def record_usage(store: UsageStore, method: str, path: str, *, role: str = "", origin: str = "api") -> None:
    feature = feature_for_path(path)
    if not feature:
        return
    normalized_method = str(method or "").upper()
    normalized_origin = normalize_origin(origin)
    now = utcnow()
    metric = store.usage_metrics.get(feature)
    previous_metric = deepcopy(metric) if metric is not None else None
    if metric is None:
        metric = UsageMetric(feature=feature, first_seen_at=now)
        store.usage_metrics[feature] = metric
    try:
        metric.hit_count += 1
        if normalized_method == "GET":
            metric.read_count += 1
        else:
            metric.write_count += 1
        metric.origin_counts[normalized_origin] = int(metric.origin_counts.get(normalized_origin, 0)) + 1
        metric.last_method = normalized_method
        metric.last_path = str(path)
        metric.last_role = str(role or "")
        metric.last_origin = normalized_origin
        metric.last_seen_at = now
        mark_dirty = getattr(store, "mark_dirty_for_resource", None)
        if callable(mark_dirty):
            mark_dirty("usage_metric")
        store.commit()
    except Exception:
        if previous_metric is None:
            store.usage_metrics.pop(feature, None)
        else:
            store.usage_metrics[feature] = previous_metric
        raise


def _origin_totals(metrics: list[UsageMetric]) -> tuple[dict[str, int], int]:
    totals = {origin: 0 for origin in sorted(VALID_ORIGINS)}
    classified = 0
    for metric in metrics:
        for origin in VALID_ORIGINS:
            count = max(0, int(metric.origin_counts.get(origin, 0)))
            totals[origin] += count
            classified += count
    total_hits = sum(max(0, int(metric.hit_count)) for metric in metrics)
    return totals, max(0, total_hits - classified)


def _row(metric: UsageMetric) -> dict[str, Any]:
    row = to_plain(metric)
    classified = sum(max(0, int(metric.origin_counts.get(origin, 0))) for origin in VALID_ORIGINS)
    row["origin_counts"] = {origin: max(0, int(metric.origin_counts.get(origin, 0))) for origin in sorted(VALID_ORIGINS)}
    row["product_hit_count"] = row["origin_counts"]["ui"]
    row["automation_hit_count"] = sum(row["origin_counts"][origin] for origin in AUTOMATION_ORIGINS)
    row["unclassified_hit_count"] = max(0, int(metric.hit_count) - classified)
    return row


def payload(store: UsageStore, filters: Mapping[str, Any] | None = None, *, limit: int = 200) -> dict[str, Any]:
    metrics = list(store.usage_metrics.values())
    metrics.sort(key=lambda item: (item.hit_count, item.feature), reverse=True)
    rows = [_row(item) for item in metrics[: max(1, limit)]]
    origin_counts, unclassified_hits = _origin_totals(metrics)
    total_hits = sum(max(0, int(item.hit_count)) for item in metrics)
    product_hits = origin_counts["ui"]
    automation_hits = sum(origin_counts[origin] for origin in AUTOMATION_ORIGINS)
    return {
        "features": rows,
        "feature_count": len(metrics),
        "total_hits": total_hits,
        "origin_counts": origin_counts,
        "product_hits": product_hits,
        "automation_hits": automation_hits,
        "api_hits": origin_counts["api"],
        "unclassified_hits": unclassified_hits,
        "product_metric_definition": "product_hits_count_only_explicit_non_automated_ui_requests",
        "usage_boundary": "local_usage_telemetry_only_no_pii_no_external_transmission",
    }


def summary(store: UsageStore) -> dict[str, Any]:
    metrics = list(store.usage_metrics.values())
    origin_counts, unclassified_hits = _origin_totals(metrics)
    top = sorted(metrics, key=lambda item: item.hit_count, reverse=True)[:5]
    return {
        "feature_count": len(metrics),
        "total_hits": sum(max(0, int(item.hit_count)) for item in metrics),
        "product_hits": origin_counts["ui"],
        "automation_hits": sum(origin_counts[origin] for origin in AUTOMATION_ORIGINS),
        "api_hits": origin_counts["api"],
        "unclassified_hits": unclassified_hits,
        "origin_counts": origin_counts,
        "top_features": [
            {
                "feature": item.feature,
                "hit_count": item.hit_count,
                "product_hit_count": max(0, int(item.origin_counts.get("ui", 0))),
            }
            for item in top
        ],
    }
