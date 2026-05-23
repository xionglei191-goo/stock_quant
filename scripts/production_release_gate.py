from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.production_closure import (
    DEFAULT_BASE_URL,
    load_manifest,
    run_production_closure,
    validate_production_closure_manifest,
)
from scripts.production_artifact_inventory_check import validate_artifact_inventory
from scripts.production_evidence_plan_check import validate_evidence_collection_plan
from scripts.production_evidence_plan_to_manifest import (
    build_manifest_from_evidence_plan,
    load_json_object,
)


def _stage(name: str, status: str, **payload: Any) -> dict[str, Any]:
    return {"stage": name, "status": status, **payload}


def _atomic_write_text(path: str | Path, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f".{output_path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(output_path)


def _finalize_stage_summary(result: dict[str, Any]) -> dict[str, Any]:
    stages = [stage for stage in result.get("stages", []) if isinstance(stage, Mapping)]
    failed_stage_names = [str(stage.get("stage", "")) for stage in stages if stage.get("status") != "passed"]
    result["stage_count"] = len(stages)
    result["passed_stage_count"] = sum(1 for stage in stages if stage.get("status") == "passed")
    result["failed_stage_count"] = len(failed_stage_names)
    result["failed_stage_names"] = failed_stage_names
    return result


def run_production_release_gate(
    *,
    plan: Mapping[str, Any],
    base_manifest: Mapping[str, Any],
    evidence_package: Mapping[str, Any] | None = None,
    artifact_inventory: Mapping[str, Any] | None = None,
    artifact_bundle_root: str | Path | None = None,
    manifest_output: str | Path | None = None,
    base_url: str = DEFAULT_BASE_URL,
    run_closure: bool = False,
    execute: bool = False,
    timeout: float = 10.0,
    require_reports: bool = True,
    require_artifact_inventory: bool = True,
    draft: bool = False,
) -> dict[str, Any]:
    stages: list[dict[str, Any]] = []
    result: dict[str, Any] = {
        "status": "failed",
        "draft": draft,
        "stages": stages,
        "production_boundary": "release gate validates evidence plumbing only; it never enables live broker or automatic order execution",
    }

    plan_validation = validate_evidence_collection_plan(plan, require_filled_uris=not draft)
    stages.append(_stage("evidence_plan_validation", "passed" if plan_validation["passed"] else "failed", validation=plan_validation))
    if not plan_validation["passed"]:
        result["failed_stage"] = "evidence_plan_validation"
        return _finalize_stage_summary(result)

    if not draft and evidence_package is None:
        stages.append(
            _stage(
                "evidence_package_required",
                "failed",
                error="strict release gate requires a readiness evidence package exported from the real staging/production endpoint",
            )
        )
        result["failed_stage"] = "evidence_package_required"
        return _finalize_stage_summary(result)

    if not draft and require_artifact_inventory and artifact_inventory is None:
        stages.append(
            _stage(
                "artifact_inventory_required",
                "failed",
                error="strict release gate requires an artifact inventory covering every release evidence URI",
            )
        )
        result["failed_stage"] = "artifact_inventory_required"
        return _finalize_stage_summary(result)

    try:
        manifest = build_manifest_from_evidence_plan(
            plan,
            base_manifest=base_manifest,
            allow_placeholders=draft,
            evidence_package=evidence_package,
            release_ready=not draft,
        )
    except AssertionError as exc:
        stages.append(_stage("manifest_generation", "failed", error=str(exc)))
        result["failed_stage"] = "manifest_generation"
        return _finalize_stage_summary(result)

    generation = manifest.get("manifest_generation", {})
    stages.append(
        _stage(
            "manifest_generation",
            "passed",
            mapped_field_count=generation.get("mapped_field_count", 0) if isinstance(generation, Mapping) else 0,
            release_field_mapping_enabled=generation.get("release_field_mapping_enabled") if isinstance(generation, Mapping) else None,
        )
    )

    manifest_validation = validate_production_closure_manifest(
        manifest,
        require_reports=require_reports,
        require_launch_ready=not draft,
    )
    stages.append(_stage("manifest_validation", "passed" if manifest_validation["passed"] else "failed", validation=manifest_validation))
    if not manifest_validation["passed"]:
        result["failed_stage"] = "manifest_validation"
        return _finalize_stage_summary(result)

    inventory_validation: dict[str, Any] | None = None
    if artifact_inventory is not None:
        inventory_validation = validate_artifact_inventory(
            artifact_inventory,
            required_contexts=[plan, evidence_package or {}, manifest],
            bundle_root=artifact_bundle_root,
        )
        stages.append(
            _stage(
                "artifact_inventory_validation",
                "passed" if inventory_validation["passed"] else "failed",
                validation=inventory_validation,
            )
        )
        if not inventory_validation["passed"]:
            result["failed_stage"] = "artifact_inventory_validation"
            result["artifact_inventory_validation"] = inventory_validation
            return _finalize_stage_summary(result)

    closure_result: dict[str, Any] | None = None
    if run_closure:
        closure_result = run_production_closure(
            base_url=base_url,
            manifest=manifest,
            timeout=timeout,
            require_reports=require_reports,
            dry_run=not execute,
        )
        stages.append(_stage("production_closure", closure_result.get("status", "failed"), result=closure_result))
        if closure_result.get("status") != "passed":
            result["failed_stage"] = "production_closure"
            result["closure_result"] = closure_result
            return _finalize_stage_summary(result)

    if manifest_output:
        output_path = Path(manifest_output)
        _atomic_write_text(output_path, json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
        result["manifest_output"] = str(output_path)

    result.update(
        {
            "status": "draft" if draft else "passed",
            "manifest_ready_for_launch": bool(manifest.get("ready_for_launch")),
            "manifest_validation": manifest_validation,
            "artifact_inventory_validation": inventory_validation,
            "closure_result": closure_result,
            "next_gate": "run project_completion_audit.py against the real manifest after updating tasks/todo.md evidence status" if not draft else "replace placeholders with real artifact URIs and rerun without --draft",
        }
    )
    return _finalize_stage_summary(result)


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the production release evidence gate from a filled evidence plan.")
    parser.add_argument("--plan", required=True, help="External evidence collection plan JSON.")
    parser.add_argument(
        "--base",
        default=str(ROOT / "artifacts/production-closure-manifest.example.json"),
        help="Base production closure manifest template.",
    )
    parser.add_argument("--evidence-package", default="", help="Real readiness evidence package JSON exported with include_passed=true.")
    parser.add_argument("--artifact-inventory", default="", help="Real artifact inventory JSON covering every release evidence URI.")
    parser.add_argument("--artifact-bundle-root", default="", help="Optional local/exported evidence bundle root used to verify inventory sha256 and size.")
    parser.add_argument("--manifest-output", default="", help="Path to write the generated production closure manifest.")
    parser.add_argument("--output", default="", help="Optional path to write the release gate result JSON.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL, help="Real staging URL used when --run-closure is set.")
    parser.add_argument("--timeout", type=float, default=10.0)
    parser.add_argument("--run-closure", action="store_true", help="Run production_closure.py after manifest validation; dry-run unless --execute is set.")
    parser.add_argument("--execute", action="store_true", help="Write readiness records to the staging URL instead of dry-run validation.")
    parser.add_argument("--skip-report-readiness", action="store_true", help="Do not require storage/security/observability/UI/deployment report payloads.")
    parser.add_argument("--skip-artifact-inventory", action="store_true", help="Do not require a production artifact inventory in strict mode.")
    parser.add_argument("--draft", action="store_true", help="Allow placeholder plan templates and run only draft/template validation.")
    args = parser.parse_args()

    plan = load_json_object(args.plan, label="evidence plan")
    base_manifest = load_manifest(args.base)
    package = load_json_object(args.evidence_package, label="readiness evidence package") if args.evidence_package else None
    inventory = load_json_object(args.artifact_inventory, label="artifact inventory") if args.artifact_inventory else None
    result = run_production_release_gate(
        plan=plan,
        base_manifest=base_manifest,
        evidence_package=package,
        artifact_inventory=inventory,
        artifact_bundle_root=args.artifact_bundle_root or None,
        manifest_output=args.manifest_output or None,
        base_url=args.base_url,
        run_closure=args.run_closure,
        execute=args.execute,
        timeout=args.timeout,
        require_reports=not args.skip_report_readiness,
        require_artifact_inventory=not args.skip_artifact_inventory,
        draft=args.draft,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        _atomic_write_text(args.output, rendered + "\n")
    print(rendered)
    if result["status"] == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
