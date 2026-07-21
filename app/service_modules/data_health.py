from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def market_data_snapshot(store: Any) -> dict[str, Any]:
    """Return a bounded market-data health projection for any storage backend."""

    materialized = getattr(store, "market_data", {})
    materialized_count = len(materialized)
    lazy_collections = set(getattr(store, "_lazy_collections", set()) or set())
    lazy = "market_data" in lazy_collections
    query = getattr(store, "query_market_data_points", None)
    estimator = getattr(store, "estimate_market_data_points", None)
    counter = getattr(store, "count_market_data_points", None)

    count = materialized_count
    count_accuracy = "exact"
    count_source = "materialized_store.market_data"
    errors: list[str] = []
    if callable(estimator):
        try:
            count = max(0, int(estimator() or 0))
            count_accuracy = "estimated"
            count_source = "typed_market_data_backend_statistics"
        except Exception as exc:  # pragma: no cover - backend failure safety
            errors.append(f"count_estimate_failed:{type(exc).__name__}")
    elif callable(counter):
        try:
            count = max(0, int(counter() or 0))
            count_source = "typed_market_data_backend_count"
        except Exception as exc:  # pragma: no cover - backend failure safety
            errors.append(f"count_query_failed:{type(exc).__name__}")

    latest_as_of_date = ""
    latest_source = "materialized_store.market_data"
    if callable(query):
        try:
            rows = list(query(limit=1, descending=True))
            if rows:
                latest_as_of_date = str(getattr(rows[0], "as_of_date", "") or "")
            latest_source = "typed_market_data_backend_query"
        except Exception as exc:  # pragma: no cover - backend failure safety
            errors.append(f"latest_query_failed:{type(exc).__name__}")
    if not latest_as_of_date and materialized_count:
        latest_as_of_date = max(str(getattr(item, "as_of_date", "") or "") for item in materialized.values())

    # Statistics can be empty immediately after a bulk load. Only in that
    # inconsistent case do an exact count rather than scanning on every health read.
    if count == 0 and latest_as_of_date and callable(counter):
        try:
            count = max(0, int(counter() or 0))
            count_accuracy = "exact"
            count_source = "typed_market_data_backend_count_fallback"
        except Exception as exc:  # pragma: no cover - backend failure safety
            errors.append(f"count_fallback_failed:{type(exc).__name__}")

    effective_count = max(count, materialized_count)
    if errors:
        consistency_status = "unavailable"
    elif effective_count > 0 and not latest_as_of_date:
        consistency_status = "mismatch"
    elif count < materialized_count:
        consistency_status = "mismatch"
    else:
        consistency_status = "consistent"

    return {
        "count": effective_count,
        "latest_as_of_date": latest_as_of_date,
        "source_of_truth": "typed_market_data_backend" if callable(query) or callable(estimator) or callable(counter) else "materialized_store",
        "count_source": count_source,
        "latest_source": latest_source,
        "count_accuracy": count_accuracy,
        "storage_mode": "lazy_typed_backend" if lazy else ("typed_backend" if callable(query) else "materialized"),
        "materialized_cache_count": materialized_count,
        "consistency_status": consistency_status,
        "errors": errors,
    }


def source_health_row(
    *,
    source_key: str,
    domain: str,
    label: str,
    status: str,
    latest_success_at: str = "",
    latest_failure_at: str = "",
    failure_count: int = 0,
    pending_count: int = 0,
    freshness_level: str = "unknown",
    last_artifact: str = "",
    next_actions: list[dict[str, Any]] | None = None,
    evidence: Mapping[str, Any] | None = None,
    source_of_truth: str = "local_read_model",
    consistency_status: str = "not_checked",
    usage_boundary: str = "",
) -> dict[str, Any]:
    return {
        "source_key": source_key,
        "domain": domain,
        "label": label,
        "status": status,
        "latest_success_at": latest_success_at,
        "latest_failure_at": latest_failure_at,
        "failure_count": int(failure_count or 0),
        "pending_count": int(pending_count or 0),
        "freshness_level": freshness_level,
        "last_artifact": last_artifact,
        "next_actions": list(next_actions or []),
        "evidence": dict(evidence or {}),
        "source_of_truth": source_of_truth,
        "consistency_status": consistency_status,
        "usage_boundary": usage_boundary or "local_source_health_summary_no_live_trading",
    }


def build_data_health_summary(
    *,
    generated_at: Any,
    filters: Mapping[str, Any],
    runs_payload: Mapping[str, Any],
    market_snapshot: Mapping[str, Any],
    research_report_count: int,
    structured_report_count: int,
    disclosure_count: int,
    material_pending: Mapping[str, Any],
    company_profile_count: int,
    simulation_feedback_count: int,
) -> dict[str, Any]:
    runs = list(runs_payload.get("runs", []))

    def runs_for(*families: str) -> list[dict[str, Any]]:
        return [run for run in runs if run.get("run_family") in families]

    def latest_success(run_rows: list[dict[str, Any]]) -> str:
        return max([str(row.get("completed_at") or row.get("updated_at") or "") for row in run_rows if row.get("normalized_status") == "success"] or [""])

    def latest_failure(run_rows: list[dict[str, Any]]) -> str:
        return max([str(row.get("completed_at") or row.get("updated_at") or "") for row in run_rows if row.get("normalized_status") == "failed"] or [""])

    def failures(run_rows: list[dict[str, Any]]) -> int:
        return sum(1 for row in run_rows if row.get("normalized_status") == "failed")

    market_count = int(market_snapshot.get("count", 0) or 0)
    latest_market = str(market_snapshot.get("latest_as_of_date", "") or "")
    build_runs = runs_for("company_database_build_run")
    package_runs = runs_for("company_package_import_run")
    cycle_runs = runs_for("company_intelligence_cycle_run")
    ingestion_runs = runs_for("ingestion_job", "ingestion_schedule_run")
    daily_runs = runs_for("daily_data_update_pipeline")
    personal_runs = runs_for("personal_intelligence_refresh")

    source_rows = [
        source_health_row(
            source_key="market_data",
            domain="market_data",
            label="公开行情",
            status="healthy" if market_count else "missing",
            latest_success_at=latest_market or latest_success(daily_runs),
            latest_failure_at=latest_failure(daily_runs),
            failure_count=failures(daily_runs),
            freshness_level="fresh" if market_count else "missing",
            last_artifact=next((path for run in daily_runs for path in run.get("artifact_paths", []) if path), ""),
            next_actions=[{"action": "monitor_daily_update", "endpoint": "/api/data-health/runs/summary"}] if market_count else [{"action": "import_market_data", "endpoint": "/api/market-data/batch"}],
            evidence={
                "market_data_count": market_count,
                "latest_as_of_date": latest_market,
                "count_accuracy": market_snapshot.get("count_accuracy", "unknown"),
                "count_source": market_snapshot.get("count_source", ""),
                "latest_source": market_snapshot.get("latest_source", ""),
                "storage_mode": market_snapshot.get("storage_mode", "unknown"),
                "materialized_cache_count": int(market_snapshot.get("materialized_cache_count", 0) or 0),
                "backend_errors": list(market_snapshot.get("errors", []) or []),
            },
            source_of_truth=str(market_snapshot.get("source_of_truth", "materialized_store")),
            consistency_status=str(market_snapshot.get("consistency_status", "not_checked")),
            usage_boundary="public_or_local_market_data_reference_no_live_trading",
        ),
        source_health_row(
            source_key="research_reports",
            domain="research_reports",
            label="研报观点库",
            status="healthy" if research_report_count else "missing",
            latest_success_at=latest_success(package_runs + personal_runs),
            latest_failure_at=latest_failure(package_runs + personal_runs),
            failure_count=failures(package_runs + personal_runs),
            freshness_level="available" if research_report_count else "missing",
            last_artifact=next((path for run in personal_runs for path in run.get("artifact_paths", []) if path), ""),
            next_actions=[{"action": "ingest_research_reports", "endpoint": "/api/research-reports/inbox/schedule"}],
            evidence={
                "research_report_assets": research_report_count,
                "structured_reports": structured_report_count,
                "registry_scope": "application_registry_only",
                "external_filesystem_and_search_inventory_included": False,
            },
            source_of_truth="store.research_reports_registry",
            consistency_status="not_reconciled",
            usage_boundary="local_research_reports_are_opinion_reference_not_fact_source_not_training",
        ),
        source_health_row(
            source_key="official_disclosures",
            domain="disclosures",
            label="公告/披露",
            status="healthy" if disclosure_count else ("pending" if ingestion_runs else "missing"),
            latest_success_at=latest_success(ingestion_runs),
            latest_failure_at=latest_failure(ingestion_runs),
            failure_count=failures(ingestion_runs),
            freshness_level="available" if disclosure_count else "needs_ingestion",
            next_actions=[{"action": "run_ingestion_schedule", "endpoint": "/api/ingestion/schedules/run"}],
            evidence={"disclosure_events": disclosure_count, "ingestion_run_count": len(ingestion_runs)},
            source_of_truth="store.disclosure_events_registry",
            consistency_status="single_store",
            usage_boundary="official_public_disclosure_summary_no_restricted_training_no_live_trading",
        ),
        source_health_row(
            source_key="company_materials",
            domain="company_materials",
            label="IR/官网材料",
            status="pending" if material_pending.get("pending_count") else "healthy",
            pending_count=int(material_pending.get("pending_count", 0) or 0),
            freshness_level="needs_action" if material_pending.get("pending_count") else "ready",
            next_actions=list(material_pending.get("next_actions", []) or []),
            evidence={"pending_count": material_pending.get("pending_count", 0), "status_counts": material_pending.get("status_counts", {})},
            source_of_truth="company_material_inbox_pending_read_model",
            consistency_status="single_store",
            usage_boundary=str(material_pending.get("usage_boundary", "local_company_materials_summary_no_external_download_no_training_no_live_trading")),
        ),
        source_health_row(
            source_key="company_database",
            domain="company_database",
            label="公司数据库补齐",
            status="healthy" if any(row.get("normalized_status") == "success" for row in build_runs) else ("failed" if failures(build_runs) else "pending"),
            latest_success_at=latest_success(build_runs),
            latest_failure_at=latest_failure(build_runs),
            failure_count=failures(build_runs),
            freshness_level="available" if build_runs else "not_started",
            next_actions=[{"action": "build_company_database", "endpoint": "/api/company-database/batch/build"}],
            evidence={"build_run_count": len(build_runs), "company_profiles": company_profile_count},
            source_of_truth="store.company_profiles_and_build_runs",
            consistency_status="single_store",
            usage_boundary="company_database_health_is_local_operations_summary_no_live_trading",
        ),
        source_health_row(
            source_key="workflow_feedback",
            domain="workflow_feedback",
            label="闭环刷新与模拟反馈",
            status="healthy" if any(row.get("normalized_status") == "success" for row in cycle_runs) else ("failed" if failures(cycle_runs) else "pending"),
            latest_success_at=latest_success(cycle_runs),
            latest_failure_at=latest_failure(cycle_runs),
            failure_count=failures(cycle_runs),
            freshness_level="available" if cycle_runs else "not_started",
            next_actions=[{"action": "run_company_intelligence_cycle", "endpoint": "/api/company-intelligence/{symbol}/cycle/run"}],
            evidence={"cycle_run_count": len(cycle_runs), "simulation_feedback_count": simulation_feedback_count},
            source_of_truth="store.company_intelligence_cycle_runs_and_simulation_feedback",
            consistency_status="single_store",
            usage_boundary="workflow_feedback_is_paper_only_no_broker_no_auto_trading",
        ),
    ]
    if filters.get("source_key"):
        wanted = str(filters.get("source_key")).strip()
        source_rows = [row for row in source_rows if row["source_key"] == wanted]
    status_counts: dict[str, int] = {}
    consistency_counts: dict[str, int] = {}
    for row in source_rows:
        status_counts[row["status"]] = status_counts.get(row["status"], 0) + 1
        consistency = str(row.get("consistency_status", "not_checked"))
        consistency_counts[consistency] = consistency_counts.get(consistency, 0) + 1
    return {
        "schema_id": "data-health-summary-v1",
        "status": "ok",
        "generated_at": generated_at,
        "summary": {
            "source_count": len(source_rows),
            "status_counts": status_counts,
            "consistency_counts": consistency_counts,
            "failure_count": sum(row["failure_count"] for row in source_rows),
            "pending_count": sum(row["pending_count"] for row in source_rows),
            "next_action_count": sum(len(row["next_actions"]) for row in source_rows),
        },
        "sources": source_rows,
        "run_summary": dict(runs_payload.get("summary", {})),
        "run_count": int(runs_payload.get("count", 0) or 0),
        "local_only": True,
        "acceptable_for_non_local_release": False,
        "usage_boundary": "data_health_summary_is_local_read_model_no_schema_migration_no_live_trading",
    }
