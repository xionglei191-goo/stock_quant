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
from scripts.production_evidence_plan_check import validate_evidence_collection_plan
from scripts.production_evidence_plan_to_manifest import load_json_object


def _normalize_prefix(prefix: str) -> str:
    normalized = prefix.strip().rstrip("/")
    if not normalized:
        raise AssertionError("artifact prefix is required")
    if not is_production_artifact_uri(f"{normalized}/prefix-check.json"):
        raise AssertionError("artifact prefix must be a concrete production/staging archive URI")
    return normalized


def fill_evidence_collection_plan(
    plan: Mapping[str, Any],
    *,
    artifact_prefix: str,
) -> dict[str, Any]:
    prefix = _normalize_prefix(artifact_prefix)
    filled = json.loads(json.dumps(plan, ensure_ascii=False))
    for row in filled.get("tasks", []):
        if not isinstance(row, dict):
            continue
        task_id = str(row.get("task_id", "")).strip()
        fields = row.get("artifact_fields", [])
        if not isinstance(fields, list):
            continue
        row["status"] = "blocked_external_evidence"
        row["artifact_uri_template"] = {
            str(field): f"{prefix}/{task_id}/{field}.json"
            for field in fields
        }
    filled["filled_artifact_prefix"] = prefix
    filled["production_boundary"] = "this plan is a collection checklist only; it is not release evidence"
    validation = validate_evidence_collection_plan(filled, require_filled_uris=True)
    if not validation["passed"]:
        raise AssertionError(json.dumps(validation, ensure_ascii=False, sort_keys=True))
    return filled


def _atomic_write_text(path: str | Path, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f".{output_path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(output_path)


def main() -> None:
    parser = argparse.ArgumentParser(description="Fill a production evidence collection plan with a concrete artifact prefix.")
    parser.add_argument("plan_json", help="Evidence collection plan template JSON.")
    parser.add_argument("--artifact-prefix", required=True, help="Concrete production/staging artifact prefix, e.g. s3://bucket/release-id.")
    parser.add_argument("--output", required=True, help="Output path for the filled evidence collection plan.")
    args = parser.parse_args()

    plan = load_json_object(args.plan_json, label="evidence collection plan")
    filled = fill_evidence_collection_plan(plan, artifact_prefix=args.artifact_prefix)
    rendered = json.dumps(filled, ensure_ascii=False, indent=2, sort_keys=True)
    _atomic_write_text(args.output, rendered + "\n")
    print(rendered)


if __name__ == "__main__":
    main()
