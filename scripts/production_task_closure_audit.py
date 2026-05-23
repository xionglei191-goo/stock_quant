from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.readiness_artifacts import is_production_artifact_uri
from scripts.production_closure import (
    validate_production_closure_manifest,
)
from scripts.readiness_evidence_package_check import (
    REQUIRED_CHECK_IDS,
    REQUIRED_EXTERNAL_VALIDATION_SCOPES,
)


TASKS_WITH_EXTERNAL_EVIDENCE = {
    "T-402": [
        "300-500 real CN filing/report samples",
        "English SEC sample set",
        "human annotation manual",
        "OCR bbox/table cell gold labels",
        "summary quality samples",
        "regression baseline report",
    ],
    "T-404": [
        "PostgreSQL/S3/OpenSearch real environment smoke",
        "capacity and latency baseline",
        "backup restore drill",
    ],
    "T-405": [
        "real Form 13F large sample parse run",
        "CUSIP/FIGI/issuer gold mapping accuracy evidence",
    ],
    "T-406": [
        "ADR/Chinese ADR real batch mapping evidence",
        "entity page browser acceptance",
        "Neo4j external sync evidence",
        "Qdrant external sync evidence",
    ],
    "T-406A": [
        "real hotspot query/gold reference LLM rerank evaluation",
    ],
    "T-407": [
        "non-local real-volume UI workflow acceptance",
        "desktop/mobile cross-browser matrix artifact",
    ],
    "T-408": [
        "performance reconciliation",
        "NAV/ledger reconciliation",
        "board pack artifact",
        "large replay acceptance",
    ],
    "T-409": [
        "production PyPortfolioOpt/CVXPY solver comparison",
        "solver version/parameter artifact",
    ],
    "T-410": [
        "real model quality evaluation",
        "fallback comparison at scale",
    ],
    "T-411": [
        "non-local OTel collector backend query evidence",
        "retention policy execution",
        "external alert delivery evidence",
    ],
    "T-412": [
        "production parameter confirmation",
        "external secret manager integration",
        "backup restore artifact",
        "release checklist",
        "canary/rollback artifact",
    ],
    "T-414": [
        "citation boundary policy review artifact",
        "source review artifact",
        "manual reference reviewed-empty artifact where applicable",
    ],
    "T-416": [
        "connector endpoint availability artifacts",
        "endpoint stability artifacts",
        "rate-limit/quota verification",
        "license/TOS reviews",
        "field sample artifacts for every approved connector",
    ],
    "T-418": [
        "real model quality evaluation",
        "fallback comparison at scale",
        "LLM gateway smoke",
        "budget sync artifact",
    ],
    "T-419": [
        "Neo4j/Qdrant non-local sync artifact",
        "batch throughput baseline",
        "failure injection/retry recovery evidence",
    ],
    "T-420": [
        "Airflow/Dagster/Cron deployment evidence",
        "external sensor connectivity",
        "distributed worker queue isolation",
        "large-window backfill drill",
        "OpenLineage/MLflow real client evidence",
    ],
    "T-421": [
        "external KMS/secret manager evidence",
        "external API key least privilege review",
        "object store/search external delete executor evidence",
    ],
}

TASK_ARTIFACT_KEYS = {
    "T-404": ["storage"],
    "T-407": ["ui", "cross_browser_acceptance", "production_ui_screenshot_acceptance"],
    "T-411": ["observability", "otel_collector_drill"],
    "T-412": ["deployment", "launch_checklist", "backup_restore_drill", "capacity_latency_report"],
    "T-416": ["astock_connectors"],
    "T-419": ["graph_vector_semantic_search"],
    "T-420": ["lineage_model_registry"],
    "T-421": ["security", "kms_rotation_cache_retention_external_delete", "permission_red_team_test"],
}

TASK_CODE_MARKERS = {
    "T-402": [
        ("app/services.py", "def benchmark_readiness_report("),
        ("app/api.py", "/api/benchmarks/(?P<benchmark_id>[^/]+)/readiness-report"),
        ("tests/test_system.py", "benchmark_readiness_report_tracks_real_sample"),
    ],
    "T-404": [
        ("app/services.py", "def storage_readiness_report("),
        ("app/api.py", "/api/governance/storage-readiness-report"),
        ("tests/test_system.py", "test_storage_readiness_report_requires_external_storage_search_and_restore_evidence"),
    ],
    "T-405": [
        ("app/services.py", "def form13f_mapping_readiness_report("),
        ("app/api.py", "/api/13f/filings/mapping-readiness"),
        ("tests/test_system.py", "mapping-readiness"),
    ],
    "T-406": [
        ("app/services.py", "def entity_mapping_readiness_report("),
        ("app/api.py", "/api/entity-mappings/readiness-report"),
        ("tests/test_system.py", "test_entity_mapping_readiness_report_requires_ahu_graph_and_adapter_evidence"),
    ],
    "T-406A": [
        ("app/services.py", "def hotspot_readiness_report("),
        ("app/api.py", "/api/hotspots/readiness-report"),
        ("tests/test_system.py", "test_hotspot_readiness_report_requires_layer_boundaries_tasks_and_rerank_evidence"),
    ],
    "T-407": [
        ("app/services.py", "def ui_readiness_report("),
        ("app/api.py", "/api/readiness/ui-report"),
        ("scripts/ui_cross_browser_matrix_check.py", "def validate_cross_browser_matrix("),
    ],
    "T-408": [
        ("app/services.py", "def portfolio_attribution_readiness_report("),
        ("app/api.py", "/api/portfolio/attribution/readiness-report"),
        ("tests/test_system.py", "test_portfolio_attribution_readiness_report_tracks_reports_replays_and_ledger"),
    ],
    "T-409": [
        ("app/services.py", "def portfolio_optimizer_readiness_report("),
        ("app/api.py", "/api/portfolio/optimizer/readiness-report"),
        ("tests/test_system.py", "portfolio_optimizer_readiness_archives_paper_solver_comparison"),
    ],
    "T-410": [
        ("app/services.py", "def research_answer_readiness_report("),
        ("app/api.py", "/api/research/answers/readiness-report"),
        ("tests/test_system.py", "test_research_answer_readiness_report_requires_model_and_fallback_quality_evidence"),
    ],
    "T-411": [
        ("app/services.py", "def observability_readiness_report("),
        ("app/api.py", "/api/observability/readiness-report"),
        ("scripts/staging_otel_acceptance.py", "def run_staging_otel_acceptance("),
    ],
    "T-412": [
        ("app/services.py", "def readiness_deployment_report("),
        ("app/api.py", "/api/readiness/deployment-report"),
        ("scripts/production_closure.py", "def run_production_closure("),
    ],
    "T-414": [
        ("app/services.py", "def citation_boundary_readiness_report("),
        ("app/api.py", "/api/research/citation-boundary/readiness-report"),
        ("tests/test_system.py", "test_citation_boundary_readiness_report_requires_reviews_and_policy_artifacts"),
    ],
    "T-416": [
        ("app/connectors.py", "class AStockSupplementalRegistry"),
        ("app/services.py", "def astock_connector_verification_readiness("),
        ("tests/test_system.py", "test_astock_supplemental_connector_registry_and_fetch"),
    ],
    "T-418": [
        ("app/services.py", "def llm_readiness_report("),
        ("app/api.py", "/api/llm/readiness-report"),
        ("tests/test_system.py", "test_llm_readiness_report_tracks_prompt_quality_budget_and_challenger_evidence"),
    ],
    "T-419": [
        ("app/services.py", "def graph_vector_readiness_report("),
        ("app/api.py", "/api/graph-vector/readiness-report"),
        ("scripts/staging_graph_vector_acceptance.py", "def run_staging_graph_vector_acceptance("),
    ],
    "T-420": [
        ("app/services.py", "def orchestration_readiness_report("),
        ("app/api.py", "/api/orchestration/readiness-report"),
        ("scripts/staging_lineage_registry_acceptance.py", "def run_staging_lineage_registry_acceptance("),
    ],
    "T-421": [
        ("app/services.py", "def security_readiness_report("),
        ("app/api.py", "/api/governance/security-readiness-report"),
        ("scripts/staging_security_acceptance.py", "def run_staging_security_acceptance("),
    ],
}

TASK_EVIDENCE_COLLECTION_PLAN = {
    "T-402": {
        "owner_role": "NLP/ML 负责人",
        "readiness_endpoint": "/api/benchmarks/{benchmark_id}/readiness-report",
        "artifact_fields": [
            "sample_manifest_uri",
            "chinese_sample_set_uri",
            "english_sample_set_uri",
            "annotation_manual_uri",
            "bbox_gold_uri",
            "table_cell_gold_uri",
            "summary_quality_uri",
            "regression_baseline_uri",
        ],
    },
    "T-404": {
        "owner_role": "平台负责人",
        "readiness_endpoint": "/api/governance/storage-readiness-report",
        "artifact_fields": [
            "postgres_smoke_uri",
            "s3_smoke_uri",
            "opensearch_smoke_uri",
            "capacity_baseline_uri",
            "backup_restore_uri",
            "least_privilege_policy_uri",
        ],
    },
    "T-405": {
        "owner_role": "数据工程",
        "readiness_endpoint": "/api/13f/filings/mapping-readiness",
        "artifact_fields": [
            "batch_parse_artifact_uri",
            "gold_mapping_uri",
            "unmapped_review_queue_uri",
        ],
    },
    "T-406": {
        "owner_role": "数据工程",
        "readiness_endpoint": "/api/entity-mappings/readiness-report",
        "artifact_fields": [
            "batch_mapping_artifact_uri",
            "entity_page_acceptance_uri",
            "neo4j_sync_artifact_uri",
            "qdrant_sync_artifact_uri",
        ],
    },
    "T-406A": {
        "owner_role": "分析师",
        "readiness_endpoint": "/api/hotspots/readiness-report",
        "artifact_fields": [
            "query_gold_refs_uri",
            "llm_rerank_eval_uri",
            "research_task_queue_uri",
        ],
    },
    "T-407": {
        "owner_role": "平台负责人",
        "readiness_endpoint": "/api/readiness/ui-report",
        "artifact_fields": [
            "browser_acceptance_uri",
            "screenshot_manifest_uri",
            "cross_browser_matrix_uri",
            "real_data_workflow_uri",
            "visual_overflow_review_uri",
            "access_control_review_uri",
        ],
    },
    "T-408": {
        "owner_role": "CIO",
        "readiness_endpoint": "/api/portfolio/attribution/readiness-report",
        "artifact_fields": [
            "performance_reconciliation_uri",
            "ledger_extract_uri",
            "board_pack_uri",
            "strategy_replay_uri",
        ],
    },
    "T-409": {
        "owner_role": "CIO",
        "readiness_endpoint": "/api/portfolio/optimizer/readiness-report",
        "artifact_fields": [
            "solver_artifact_uri",
            "comparison_report_uri",
            "constraint_report_uri",
        ],
    },
    "T-410": {
        "owner_role": "NLP/ML 负责人",
        "readiness_endpoint": "/api/research/answers/readiness-report",
        "artifact_fields": [
            "model_quality_eval_uri",
            "fallback_comparison_uri",
            "summary_rubric_uri",
        ],
    },
    "T-411": {
        "owner_role": "平台负责人",
        "readiness_endpoint": "/api/observability/readiness-report",
        "artifact_fields": [
            "collector_evidence_uri",
            "logs_backend_uri",
            "query_evidence_uri",
            "retention_policy_uri",
            "external_alert_evidence_uri",
            "drill_evidence_uri",
        ],
    },
    "T-412": {
        "owner_role": "平台负责人",
        "readiness_endpoint": "/api/readiness/deployment-report",
        "artifact_fields": [
            "production_parameters_uri",
            "secret_manager_evidence_uri",
            "backup_restore_evidence_uri",
            "capacity_baseline_uri",
            "release_checklist_uri",
            "canary_plan_uri",
            "rollback_plan_uri",
        ],
    },
    "T-414": {
        "owner_role": "风险/合规",
        "readiness_endpoint": "/api/research/citation-boundary/readiness-report",
        "artifact_fields": [
            "policy_review_uri",
            "source_review_uri",
            "manual_reference_review_uri",
            "research_governance_uri",
        ],
    },
    "T-416": {
        "owner_role": "数据工程",
        "readiness_endpoint": "/api/connectors/astock/verification-readiness",
        "artifact_fields": [
            "endpoint_artifact_uri",
            "stability_artifact_uri",
            "rate_limit_artifact_uri",
            "license_review_uri",
            "field_sample_uri",
        ],
    },
    "T-418": {
        "owner_role": "NLP/ML 负责人",
        "readiness_endpoint": "/api/llm/readiness-report",
        "artifact_fields": [
            "real_model_quality_uri",
            "fallback_quality_uri",
            "llm_gateway_smoke_uri",
            "budget_sync_evidence_uri",
        ],
    },
    "T-419": {
        "owner_role": "平台负责人",
        "readiness_endpoint": "/api/graph-vector/readiness-report",
        "artifact_fields": [
            "neo4j_sync_artifact_uri",
            "qdrant_sync_artifact_uri",
            "throughput_baseline_uri",
            "failure_recovery_uri",
        ],
    },
    "T-420": {
        "owner_role": "平台负责人",
        "readiness_endpoint": "/api/orchestration/readiness-report",
        "artifact_fields": [
            "scheduler_deployment_uri",
            "worker_pool_uri",
            "external_sensor_uri",
            "backfill_drill_uri",
            "openlineage_client_uri",
            "mlflow_registry_uri",
        ],
    },
    "T-421": {
        "owner_role": "风险/合规",
        "readiness_endpoint": "/api/governance/security-readiness-report",
        "artifact_fields": [
            "secret_manager_evidence_uri",
            "least_privilege_policy_uri",
            "external_delete_evidence_uri",
            "permission_review_uri",
        ],
    },
}


def _atomic_write_text(path: str | Path, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f".{output_path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(output_path)


def parse_open_tasks(todo_path: str | Path = ROOT / "tasks/todo.md") -> list[str]:
    text = Path(todo_path).read_text(encoding="utf-8")
    return re.findall(r"^- `(?:DOING|BLOCKED)` (T-\d+[A-Z]?)\b", text, flags=re.M)


def parse_tasks_by_status(todo_path: str | Path = ROOT / "tasks/todo.md") -> dict[str, list[str]]:
    text = Path(todo_path).read_text(encoding="utf-8")
    statuses: dict[str, list[str]] = {"TODO": [], "DOING": [], "DONE": [], "BLOCKED": []}
    for status, task_id in re.findall(r"^- `(TODO|DOING|DONE|BLOCKED)` (T-\d+[A-Z]?)\b", text, flags=re.M):
        statuses.setdefault(status, []).append(task_id)
    return statuses


def parse_doing_tasks(todo_path: str | Path = ROOT / "tasks/todo.md") -> list[str]:
    return parse_tasks_by_status(todo_path).get("DOING", [])


def _manifest_has_real_evidence(manifest: Mapping[str, Any]) -> bool:
    if manifest.get("ready_for_launch") is not True:
        return False
    checks = manifest.get("readiness_checks", {})
    if not isinstance(checks, Mapping):
        return False
    for check_id in REQUIRED_CHECK_IDS:
        row = checks.get(check_id, {})
        if not isinstance(row, Mapping) or str(row.get("status", "")) != "passed":
            return False
        if not is_production_artifact_uri(row.get("evidence_uri", "")):
            return False

    package = manifest.get("evidence_package", {})
    if not isinstance(package, Mapping):
        return False
    validations = package.get("external_validations", [])
    if not isinstance(validations, list):
        return False
    scopes = {
        str(item.get("scope", ""))
        for item in validations
        if isinstance(item, Mapping)
        and item.get("ready") is True
        and str(item.get("check_status", "")) == "passed"
        and is_production_artifact_uri(item.get("evidence_uri", ""))
    }
    return REQUIRED_EXTERNAL_VALIDATION_SCOPES.issubset(scopes)


def _external_artifact_count(value: Any) -> int:
    if isinstance(value, str):
        return int(is_production_artifact_uri(value))
    if isinstance(value, Mapping):
        return sum(_external_artifact_count(item) for item in value.values())
    if isinstance(value, list):
        return sum(_external_artifact_count(item) for item in value)
    return 0


def _task_evidence_count(task_id: str, manifest: Mapping[str, Any]) -> int:
    keys = TASK_ARTIFACT_KEYS.get(task_id, [])
    if not keys:
        return 0
    count = 0
    readiness_checks = manifest.get("readiness_checks", {})
    reports = manifest.get("reports", {})
    package = manifest.get("evidence_package", {})
    for key in keys:
        if key in REQUIRED_CHECK_IDS and isinstance(readiness_checks, Mapping):
            count += _external_artifact_count(readiness_checks.get(key, {}))
        elif isinstance(reports, Mapping) and key in reports:
            count += _external_artifact_count(reports.get(key, {}))
        elif key in REQUIRED_EXTERNAL_VALIDATION_SCOPES and isinstance(package, Mapping):
            validations = package.get("external_validations", [])
            if isinstance(validations, list):
                for row in validations:
                    if isinstance(row, Mapping) and row.get("scope") == key:
                        count += _external_artifact_count(row)
        elif key == "astock_connectors":
            count += _external_artifact_count(manifest.get("astock_connectors", {}))
    return count


def _task_code_marker_report(task_id: str) -> dict[str, Any]:
    markers = TASK_CODE_MARKERS.get(task_id, [])
    rows: list[dict[str, Any]] = []
    for relative_path, needle in markers:
        path = ROOT / relative_path
        found = path.exists() and needle in path.read_text(encoding="utf-8")
        rows.append({"path": relative_path, "needle": needle, "found": found})
    return {
        "marker_count": len(rows),
        "found_count": sum(1 for row in rows if row["found"]),
        "missing": [row for row in rows if not row["found"]],
        "rows": rows,
    }


def _load_json_object_if_exists(path: str | Path | None) -> dict[str, Any]:
    if not path:
        return {}
    candidate = Path(path)
    if not candidate.exists():
        return {}
    data = json.loads(candidate.read_text(encoding="utf-8"))
    return data if isinstance(data, dict) else {}


def _local_benchmark_quality_evidence_passed(quality_package: Mapping[str, Any], data_unblock_audit: Mapping[str, Any]) -> bool:
    language_counts = quality_package.get("language_counts", {})
    return (
        bool(quality_package)
        and quality_package.get("run_passed") is True
        and quality_package.get("large_sample_ready") is True
        and int(quality_package.get("sample_count", 0) or 0) >= 300
        and isinstance(language_counts, Mapping)
        and int(language_counts.get("zh", 0) or 0) >= 150
        and int(language_counts.get("en", 0) or 0) >= 150
        and not quality_package.get("readiness_missing_requirements")
        and bool(data_unblock_audit)
        and data_unblock_audit.get("passed") is True
        and data_unblock_audit.get("data_blocked") is False
        and not data_unblock_audit.get("remaining_quality_gaps")
    )


def audit_production_tasks(
    *,
    todo_path: str | Path = ROOT / "tasks/todo.md",
    manifest_path: str | Path | None = ROOT / "artifacts/production-closure-manifest.example.json",
    local_benchmark_quality_package_path: str | Path | None = None,
    local_data_unblock_audit_path: str | Path | None = None,
) -> dict[str, Any]:
    tasks_by_status = parse_tasks_by_status(todo_path)
    open_tasks = list(tasks_by_status.get("DOING", [])) + list(tasks_by_status.get("BLOCKED", []))
    manifest: dict[str, Any] = {}
    manifest_validation: dict[str, Any] | None = None
    if manifest_path:
        path = Path(manifest_path)
        if path.exists():
            manifest = json.loads(path.read_text(encoding="utf-8"))
            manifest_validation = validate_production_closure_manifest(manifest, require_launch_ready=False)

    has_real_closure_evidence = _manifest_has_real_evidence(manifest)
    local_benchmark_quality_package = _load_json_object_if_exists(local_benchmark_quality_package_path)
    local_data_unblock_audit = _load_json_object_if_exists(local_data_unblock_audit_path)
    local_benchmark_quality_passed = _local_benchmark_quality_evidence_passed(local_benchmark_quality_package, local_data_unblock_audit)
    rows: list[dict[str, Any]] = []
    for task_id in open_tasks:
        blockers = TASKS_WITH_EXTERNAL_EVIDENCE.get(task_id, [])
        artifact_count = _task_evidence_count(task_id, manifest)
        code_markers = _task_code_marker_report(task_id)
        code_layer_complete = bool(code_markers["marker_count"]) and not code_markers["missing"]
        local_evidence_passed = task_id == "T-402" and local_benchmark_quality_passed
        status = "done" if local_evidence_passed or (has_real_closure_evidence and not blockers) else (
            "blocked_external_evidence" if blockers and code_layer_complete else "needs_code_work"
        )
        effective_blockers = [] if local_evidence_passed else blockers
        rows.append(
            {
                "task_id": task_id,
                "status": status,
                "code_layer_complete": code_layer_complete,
                "code_markers": code_markers,
                "external_artifact_count_in_manifest": artifact_count,
                "external_evidence_blockers": effective_blockers,
                "local_evidence_passed": local_evidence_passed,
            }
        )

    counts: dict[str, int] = {}
    for row in rows:
        counts[row["status"]] = counts.get(row["status"], 0) + 1
    needs_code_work_ids = [row["task_id"] for row in rows if row["status"] == "needs_code_work"]
    blocked_external_evidence_ids = [row["task_id"] for row in rows if row["status"] == "blocked_external_evidence"]
    done_by_real_evidence_ids = [row["task_id"] for row in rows if row["status"] == "done"]
    return {
        "status": "passed" if not any(row["status"] == "needs_code_work" for row in rows) else "failed",
        "open_task_count": len(open_tasks),
        "doing_task_count": len(tasks_by_status.get("DOING", [])),
        "blocked_task_count": len(tasks_by_status.get("BLOCKED", [])),
        "needs_code_work_count": len(needs_code_work_ids),
        "blocked_external_evidence_count": len(blocked_external_evidence_ids),
        "done_by_real_evidence_count": len(done_by_real_evidence_ids),
        "needs_code_work_task_ids": needs_code_work_ids,
        "blocked_external_evidence_task_ids": blocked_external_evidence_ids,
        "done_by_real_evidence_task_ids": done_by_real_evidence_ids,
        "todo_status_counts": {key.lower(): len(value) for key, value in sorted(tasks_by_status.items())},
        "counts": counts,
        "has_real_closure_evidence": has_real_closure_evidence,
        "local_benchmark_quality_passed": local_benchmark_quality_passed,
        "manifest_validation": manifest_validation,
        "tasks": rows,
        "production_boundary": "blocked_external_evidence means code/test scaffolding exists but real staging/production artifact URIs are still required before marking DONE",
    }


def build_evidence_collection_plan(audit: Mapping[str, Any]) -> dict[str, Any]:
    tasks = []
    for row in audit.get("tasks", []):
        if not isinstance(row, Mapping):
            continue
        if row.get("status") != "blocked_external_evidence":
            continue
        task_id = str(row.get("task_id", ""))
        plan = TASK_EVIDENCE_COLLECTION_PLAN.get(task_id, {})
        artifact_fields = list(plan.get("artifact_fields", [])) if isinstance(plan, Mapping) else []
        tasks.append(
            {
                "task_id": task_id,
                "status": row.get("status", ""),
                "owner_role": plan.get("owner_role", "") if isinstance(plan, Mapping) else "",
                "readiness_endpoint": plan.get("readiness_endpoint", "") if isinstance(plan, Mapping) else "",
                "external_evidence_blockers": list(row.get("external_evidence_blockers", [])),
                "artifact_fields": artifact_fields,
                "artifact_uri_template": {
                    field: f"s3://<production-evidence-bucket>/<release-id>/{task_id}/{field}"
                    for field in artifact_fields
                },
                "acceptance_rule": "artifact_uri must be a real staging/production archive URI and pass readiness/report gate; local/demo/sample URI is not accepted",
            }
        )
    return {
        "plan_id": "production_external_evidence_collection_plan",
        "task_count": len(tasks),
        "tasks": tasks,
        "next_gate": "fill real artifact URIs in this plan, run production_evidence_plan_check.py --require-filled-uris, then use production_release_gate.py or production_evidence_plan_to_manifest.py plus production_closure_manifest_check.py before production_closure.py against the real staging URL",
        "production_boundary": "this plan is a collection checklist only; it is not release evidence",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit remaining open tasks against production closure evidence.")
    parser.add_argument("--todo", default=str(ROOT / "tasks/todo.md"))
    parser.add_argument("--manifest", default=str(ROOT / "artifacts/production-closure-manifest.example.json"))
    parser.add_argument("--local-benchmark-quality-package", default="", help="Optional local benchmark quality package JSON; only applies to T-402 local completion.")
    parser.add_argument("--local-data-unblock-audit", default="", help="Optional local data unblock audit JSON; only applies to T-402 local completion.")
    parser.add_argument("--output", default="", help="Optional path to write the task closure audit JSON.")
    parser.add_argument("--output-plan", default="", help="Optional path to write an external evidence collection plan JSON.")
    args = parser.parse_args()
    result = audit_production_tasks(
        todo_path=args.todo,
        manifest_path=args.manifest,
        local_benchmark_quality_package_path=args.local_benchmark_quality_package or None,
        local_data_unblock_audit_path=args.local_data_unblock_audit or None,
    )
    if args.output_plan:
        plan = build_evidence_collection_plan(result)
        _atomic_write_text(args.output_plan, json.dumps(plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        result["evidence_collection_plan_uri"] = args.output_plan
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        _atomic_write_text(args.output, rendered + "\n")
    print(rendered)
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
