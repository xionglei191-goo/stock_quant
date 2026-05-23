from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.readiness_artifacts import is_production_artifact_uri
from scripts.production_task_closure_audit import (
    TASK_EVIDENCE_COLLECTION_PLAN,
    TASKS_WITH_EXTERNAL_EVIDENCE,
)


def _atomic_write_text(path: str | Path, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f".{output_path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(output_path)


def _is_placeholder_uri(value: str) -> bool:
    return "<" in value or ">" in value or "{release-id}" in value or "example" in value.lower()


def validate_evidence_collection_plan(
    plan: Mapping[str, Any],
    *,
    require_filled_uris: bool = False,
) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []

    def expect(condition: bool, check: str, error: str, **extra: Any) -> None:
        if not condition:
            failures.append({"check": check, "error": error, **extra})

    expect(plan.get("plan_id") == "production_external_evidence_collection_plan", "plan_id", "unexpected plan id", value=plan.get("plan_id"))
    tasks = [dict(item) for item in plan.get("tasks", []) if isinstance(item, Mapping)]
    expected_task_ids = set(TASKS_WITH_EXTERNAL_EVIDENCE)
    declared_task_ids = {
        str(item.get("task_id", ""))
        for item in tasks
        if str(item.get("status", "")) == "blocked_external_evidence"
    }
    if declared_task_ids and declared_task_ids.issubset(expected_task_ids):
        expected_task_ids = declared_task_ids
    task_ids = {str(item.get("task_id", "")) for item in tasks}
    expect(task_ids == expected_task_ids, "task_ids", "plan must cover every external-evidence-blocked task exactly", missing=sorted(expected_task_ids - task_ids), extra=sorted(task_ids - expected_task_ids))
    expect(int(plan.get("task_count", -1)) == len(expected_task_ids), "task_count", "task_count must match expected task count", value=plan.get("task_count"))

    duplicate_task_ids = sorted(task_id for task_id in task_ids if sum(1 for row in tasks if str(row.get("task_id", "")) == task_id) > 1)
    expect(not duplicate_task_ids, "duplicate_task_ids", "plan must not duplicate task rows", duplicates=duplicate_task_ids)

    for idx, row in enumerate(tasks):
        task_id = str(row.get("task_id", ""))
        expected = TASK_EVIDENCE_COLLECTION_PLAN.get(task_id, {})
        expect(row.get("status") == "blocked_external_evidence", "task_status", "task row must remain blocked on external evidence", row=idx, task_id=task_id, value=row.get("status"))
        expect(bool(row.get("owner_role")), "owner_role", "owner_role is required", row=idx, task_id=task_id)
        expect(bool(row.get("readiness_endpoint")), "readiness_endpoint", "readiness endpoint is required", row=idx, task_id=task_id)
        if expected:
            expect(row.get("owner_role") == expected.get("owner_role"), "owner_role_expected", "owner_role must match the task collection plan", row=idx, task_id=task_id, value=row.get("owner_role"), expected=expected.get("owner_role"))
            expect(row.get("readiness_endpoint") == expected.get("readiness_endpoint"), "readiness_endpoint_expected", "readiness endpoint must match the task collection plan", row=idx, task_id=task_id, value=row.get("readiness_endpoint"), expected=expected.get("readiness_endpoint"))
        blockers = row.get("external_evidence_blockers", [])
        expect(isinstance(blockers, list) and bool(blockers), "external_evidence_blockers", "external evidence blockers must be a non-empty list", row=idx, task_id=task_id)
        fields = row.get("artifact_fields", [])
        template = row.get("artifact_uri_template", {})
        expect(isinstance(fields, list) and bool(fields), "artifact_fields", "artifact fields must be a non-empty list", row=idx, task_id=task_id)
        expect(isinstance(template, Mapping), "artifact_uri_template", "artifact_uri_template must be an object", row=idx, task_id=task_id)
        if isinstance(fields, list) and isinstance(template, Mapping):
            missing_template_fields = [field for field in fields if field not in template]
            extra_template_fields = sorted(set(str(key) for key in template) - set(str(field) for field in fields))
            expect(not missing_template_fields, "artifact_template_coverage", "every artifact field needs a URI template", row=idx, task_id=task_id, missing=missing_template_fields)
            expect(not extra_template_fields, "artifact_template_extra", "artifact template must not include fields outside artifact_fields", row=idx, task_id=task_id, extra=extra_template_fields)
            for field in fields:
                value = str(template.get(field, ""))
                expect(task_id in value and str(field) in value, "artifact_template_shape", "URI template must include task id and field name", row=idx, task_id=task_id, field=field, value=value)
                if require_filled_uris:
                    expect(not _is_placeholder_uri(value), "artifact_uri_filled", "artifact URI must not contain placeholder tokens when --require-filled-uris is used", row=idx, task_id=task_id, field=field, value=value)
                    expect(is_production_artifact_uri(value), "artifact_uri_production", "artifact URI must be a concrete production/staging archive URI when --require-filled-uris is used", row=idx, task_id=task_id, field=field, value=value)
        expect("not release evidence" in str(plan.get("production_boundary", "")).lower(), "production_boundary", "plan must state it is not release evidence", task_id=task_id)

    passed = not failures
    return {
        "status": "passed" if passed else "failed",
        "passed": passed,
        "task_count": len(tasks),
        "expected_task_count": len(expected_task_ids),
        "filled_uri_required": require_filled_uris,
        "failure_count": len(failures),
        "failures": failures,
    }


def load_and_validate_evidence_collection_plan(path: str | Path, *, require_filled_uris: bool = False) -> dict[str, Any]:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError("evidence collection plan must be a JSON object")
    return validate_evidence_collection_plan(data, require_filled_uris=require_filled_uris)


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a production external evidence collection plan JSON.")
    parser.add_argument("plan_json")
    parser.add_argument(
        "--require-filled-uris",
        action="store_true",
        help="Require every artifact URI template to be replaced with a concrete production/staging archive URI.",
    )
    parser.add_argument("--output", default="", help="Optional path to write the validation result JSON.")
    args = parser.parse_args()
    validation = load_and_validate_evidence_collection_plan(args.plan_json, require_filled_uris=args.require_filled_uris)
    rendered = json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        _atomic_write_text(args.output, rendered + "\n")
    print(rendered)
    if not validation["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
