"""Read-only longitudinal reporting for local paper-allocation operations."""

from __future__ import annotations

from calendar import monthrange
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence

from .paper import PaperDecisionSnapshot
from .performance import BOUNDARY as PERFORMANCE_BOUNDARY
from .performance import METHODOLOGY_VERSION as PERFORMANCE_METHODOLOGY_VERSION
from .performance import SCHEMA_VERSION as PERFORMANCE_SCHEMA_VERSION


GATE_MONTHS = (3, 6, 12)


def load_daily_reports(paths: Iterable[str | Path]) -> list[dict[str, Any]]:
    """Load governed daily reports without changing their source files."""

    reports: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_symlink():
            raise ValueError(f"daily report must not be a symbolic link: {path}")
        payload = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"daily report must be a JSON object: {path}")
        _assert_local_paper_boundary(payload, path)
        status = str(payload.get("status", ""))
        if status not in {"completed", "failed", "preview"}:
            raise ValueError(f"daily report has unsupported status: {path}")
        generated_at = _aware(payload.get("generated_at"), f"{path} generated_at")
        as_of = _aware(payload.get("as_of", generated_at.isoformat()), f"{path} as_of")
        identity = (as_of.isoformat(), status)
        if identity in seen:
            continue
        item = dict(payload)
        item["_source_path"] = str(path)
        reports.append(item)
        seen.add(identity)
    return sorted(reports, key=lambda item: (_aware(item.get("as_of"), "as_of"), item["status"]))


def discover_daily_reports(directory: str | Path) -> list[Path]:
    path = Path(directory)
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise ValueError("daily report directory must be a real directory")
    if not path.exists():
        return []
    return sorted(item for item in path.glob("*.json") if item.is_file() and not item.is_symlink())


def build_longitudinal_report(
    snapshots: Sequence[PaperDecisionSnapshot],
    daily_reports: Sequence[Mapping[str, Any]],
    *,
    as_of: datetime,
    performance_evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Aggregate ledger decisions and daily health without inferring returns."""

    now = _aware(as_of, "as_of")
    ordered_snapshots = sorted(snapshots, key=lambda item: _aware(item.as_of, "snapshot as_of"))
    ordered_reports = sorted(daily_reports, key=lambda item: _aware(item.get("as_of"), "report as_of"))
    snapshot_dates = [_aware(item.as_of, "snapshot as_of") for item in ordered_snapshots]
    report_dates = [_aware(item.get("as_of"), "report as_of") for item in ordered_reports]
    all_dates = snapshot_dates + report_dates
    first_at = min(all_dates) if all_dates else None
    last_at = max(all_dates) if all_dates else None

    months: dict[str, dict[str, Any]] = {}
    for snapshot, observed_at in zip(ordered_snapshots, snapshot_dates):
        bucket = _month_bucket(months, observed_at)
        bucket["ledger_decisions"] += 1
        bucket["latest_allocation"] = dict(snapshot.allocation)
        bucket["latest_regime"] = snapshot.model.get("regime")
        bucket["warning_count"] += len(snapshot.warnings)
    for report, observed_at in zip(ordered_reports, report_dates):
        bucket = _month_bucket(months, observed_at)
        bucket["daily_reports"] += 1
        status = str(report.get("status"))
        bucket[f"{status}_runs"] += 1
        decision = report.get("decision", {})
        if isinstance(decision, Mapping) and decision.get("ready") is False:
            bucket["not_ready_runs"] += 1
        refresh = report.get("refresh", {})
        pipeline = refresh.get("pipeline", {}) if isinstance(refresh, Mapping) else {}
        upsert = refresh.get("upsert", {}) if isinstance(refresh, Mapping) else {}
        missing = pipeline.get("missing_series", []) if isinstance(pipeline, Mapping) else []
        errors = pipeline.get("source_errors", {}) if isinstance(pipeline, Mapping) else {}
        conflicts = upsert.get("conflicts", 0) if isinstance(upsert, Mapping) else 0
        failure = report.get("failure", {})
        failure_health = bool(
            isinstance(failure, Mapping)
            and (
                failure.get("missing_series")
                or failure.get("source_error_series")
                or failure.get("insert_conflicts")
                or failure.get("decision_ready") is False
            )
        )
        if missing or errors or conflicts or failure_health:
            bucket["data_health_failure_runs"] += 1
        auditability = report.get("auditability", {})
        if isinstance(auditability, Mapping):
            configured = auditability.get("configured_series_count")
            fresh = auditability.get("fresh_series_count")
            if isinstance(configured, int) and isinstance(fresh, int):
                bucket["latest_configured_series_count"] = configured
                bucket["latest_fresh_series_count"] = fresh

    monthly = [months[key] for key in sorted(months)]
    observed_months = len({value.strftime("%Y-%m") for value in all_dates})
    completed_runs = sum(str(item.get("status")) == "completed" for item in ordered_reports)
    failed_runs = sum(str(item.get("status")) == "failed" for item in ordered_reports)
    data_health_failure_runs = sum(item["data_health_failure_runs"] for item in monthly)
    gates = [
        _gate(first_at, now, months_required, observed_months, performance_evidence)
        for months_required in GATE_MONTHS
    ]
    evidence_present = performance_evidence is not None
    performance_ready = bool(performance_evidence and performance_evidence.get("performance_evidence_ready"))
    efficacy_proven = any(item["efficacy_proven"] for item in gates)

    return {
        "schema_version": "dynamic-allocation-longitudinal-operations/v1",
        "status": "no_observations" if first_at is None else "accumulating",
        "generated_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "as_of": now.isoformat().replace("+00:00", "Z"),
        "classification": "local-only",
        "acceptable_for_non_local_release_gate": False,
        "paper_only": True,
        "live_execution_allowed": False,
        "broker_connected": False,
        "order_execution_allowed": False,
        "period": {
            "first_observation_at": _iso(first_at),
            "last_observation_at": _iso(last_at),
            "calendar_elapsed_days": (now.date() - first_at.date()).days if first_at else 0,
            "observed_calendar_months": observed_months,
        },
        "ledger": {
            "integrity_validated": True,
            "record_count": len(ordered_snapshots),
            "first_run_id": ordered_snapshots[0].run_id if ordered_snapshots else None,
            "latest_run_id": ordered_snapshots[-1].run_id if ordered_snapshots else None,
        },
        "daily_operations": {
            "report_count": len(ordered_reports),
            "completed_runs": completed_runs,
            "failed_runs": failed_runs,
            "preview_runs": sum(str(item.get("status")) == "preview" for item in ordered_reports),
            "data_health_failure_runs": data_health_failure_runs,
            "latest_status": ordered_reports[-1].get("status") if ordered_reports else None,
            "latest_source_path": ordered_reports[-1].get("_source_path") if ordered_reports else None,
        },
        "monthly_operations": monthly,
        "review_gates": gates,
        "performance_evidence": performance_evidence,
        "efficacy_evidence": {
            "status": "human_reviewed_effective" if efficacy_proven else "not_proven",
            "performance_series_present": evidence_present,
            "performance_evidence_ready": performance_ready,
            "financial_benefit_claimed": efficacy_proven,
            "note": "Operational continuity and calculated paper performance do not prove efficacy. Only a completed, due, governed human review can change a gate's efficacy_proven field.",
        },
    }


def _month_bucket(months: dict[str, dict[str, Any]], observed_at: datetime) -> dict[str, Any]:
    key = observed_at.strftime("%Y-%m")
    return months.setdefault(
        key,
        {
            "month": key,
            "ledger_decisions": 0,
            "daily_reports": 0,
            "completed_runs": 0,
            "failed_runs": 0,
            "preview_runs": 0,
            "not_ready_runs": 0,
            "data_health_failure_runs": 0,
            "warning_count": 0,
            "latest_configured_series_count": None,
            "latest_fresh_series_count": None,
            "latest_regime": None,
            "latest_allocation": None,
        },
    )


def _gate(
    first_at: datetime | None,
    as_of: datetime,
    months: int,
    observed_months: int,
    performance: Mapping[str, Any] | None,
) -> dict[str, Any]:
    due_at = _add_months(first_at, months) if first_at else None
    time_elapsed = bool(due_at and as_of >= due_at)
    coverage_ready = observed_months >= months
    performance_ready = _performance_covers_gate(performance, first_at, due_at)
    review = _review_for_gate(performance, months)
    human_review_complete = _review_is_valid(review, due_at, as_of)
    efficacy_proven = bool(human_review_complete and review.get("outcome") == "effective" and performance_ready)
    if first_at is None:
        status = "not_started"
    elif not time_elapsed:
        status = "awaiting_elapsed_time"
    elif not coverage_ready:
        status = "insufficient_monthly_coverage"
    elif not performance_ready:
        status = "insufficient_performance_evidence"
    elif not review or review.get("status") == "not_started":
        status = "human_review_required"
    elif review.get("status") == "pending":
        status = "human_review_pending"
    elif human_review_complete:
        status = "human_review_completed"
    else:
        status = "invalid_human_review"
    return {
        "gate_months": months,
        "due_at": _iso(due_at),
        "status": status,
        "elapsed_time_satisfied": time_elapsed,
        "observed_calendar_months": observed_months,
        "minimum_observed_months": months,
        "operational_coverage_satisfied": coverage_ready,
        "performance_evidence_satisfied": performance_ready,
        "human_review": review,
        "efficacy_proven": efficacy_proven,
    }


def _performance_covers_gate(
    performance: Mapping[str, Any] | None,
    first_at: datetime | None,
    due_at: datetime | None,
) -> bool:
    if (
        not performance
        or not first_at
        or not due_at
        or performance.get("schema_version") != PERFORMANCE_SCHEMA_VERSION
        or performance.get("methodology_version") != PERFORMANCE_METHODOLOGY_VERSION
        or any(performance.get(key) != expected for key, expected in PERFORMANCE_BOUNDARY.items())
        or performance.get("performance_evidence_ready") is not True
    ):
        return False
    coverage = performance.get("coverage")
    if not isinstance(coverage, Mapping):
        return False
    try:
        start = _aware(coverage.get("evidence_start_at"), "performance evidence_start_at")
        end = _aware(coverage.get("evidence_end_at"), "performance evidence_end_at")
    except ValueError:
        return False
    return start <= first_at and end >= due_at


def _review_for_gate(performance: Mapping[str, Any] | None, months: int) -> dict[str, Any] | None:
    reviews = performance.get("reviews", []) if performance else []
    if not isinstance(reviews, Sequence) or isinstance(reviews, (str, bytes)):
        return None
    for item in reviews:
        if isinstance(item, Mapping) and item.get("gate_months") == months:
            return dict(item)
    return None


def _review_is_valid(review: Mapping[str, Any] | None, due_at: datetime | None, as_of: datetime) -> bool:
    if not review or not due_at or review.get("status") != "completed":
        return False
    if review.get("outcome") not in {"effective", "not_effective", "inconclusive"}:
        return False
    if not str(review.get("reviewer", "")).strip() or not str(review.get("rationale", "")).strip():
        return False
    try:
        reviewed_at = _aware(review.get("reviewed_at"), "reviewed_at")
    except ValueError:
        return False
    return due_at <= reviewed_at <= as_of


def _add_months(value: datetime, months: int) -> datetime:
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _assert_local_paper_boundary(payload: Mapping[str, Any], path: Path) -> None:
    required = {
        "classification": "local-only",
        "acceptable_for_non_local_release_gate": False,
        "paper_only": True,
        "live_execution_allowed": False,
        "broker_connected": False,
        "order_execution_allowed": False,
    }
    for key, expected in required.items():
        if payload.get(key) != expected:
            raise ValueError(f"daily report violates {key} boundary: {path}")


def _aware(value: Any, name: str) -> datetime:
    try:
        parsed = value if isinstance(value, datetime) else datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an ISO-8601 datetime") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return value.astimezone(timezone.utc).isoformat().replace("+00:00", "Z") if value else None
