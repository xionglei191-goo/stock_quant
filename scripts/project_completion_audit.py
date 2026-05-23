from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.production_evidence_plan_check import validate_evidence_collection_plan
from scripts.production_release_gate import run_production_release_gate
from scripts.production_task_closure_audit import audit_production_tasks, build_evidence_collection_plan


OBJECTIVE = "完成剩下的所有的内容，改变半成品状态。验收标准：实现项目目标。"


def _atomic_write_text(path: str | Path, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f".{output_path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(output_path)


def _requirement(
    requirement_id: str,
    description: str,
    *,
    status: str,
    evidence: list[str],
    gap: str = "",
) -> dict[str, Any]:
    return {
        "requirement_id": requirement_id,
        "description": description,
        "status": status,
        "evidence": evidence,
        "gap": gap,
    }


def _load_optional_json_object(path: str | Path | None, *, label: str) -> dict[str, Any] | None:
    if not path:
        return None
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError(f"{label} must be a JSON object")
    return data


def _local_production_evidence_status(
    local_production_audit: Mapping[str, Any] | None,
    local_ai_acceptance: Mapping[str, Any] | None,
) -> dict[str, Any]:
    audit = dict(local_production_audit or {})
    ai = dict(local_ai_acceptance or {})
    audit_passed = (
        bool(audit)
        and audit.get("status") == "passed"
        and audit.get("passed") is True
        and audit.get("deployment_target") == "local_only_personal_production"
        and audit.get("ready_for_launch") is True
        and int(audit.get("failure_count", 0) or 0) == 0
        and audit.get("strict_production_gate_unchanged") is True
    )
    ai_required = bool(local_ai_acceptance)
    ai_passed = (
        bool(ai)
        and ai.get("status") == "passed"
        and ai.get("passed") is True
        and ai.get("deployment_target") == "local_only_personal_production"
        and int(ai.get("failure_count", 0) or 0) == 0
    )
    return {
        "target_mode": "local_only_personal_production" if audit else "non_local_organizational_release",
        "enabled": bool(audit),
        "audit_passed": audit_passed,
        "ai_acceptance_required": ai_required,
        "ai_acceptance_passed": (not ai_required) or ai_passed,
        "ai_acceptance_present": bool(ai),
        "warning_count": int(audit.get("warning_count", 0) or 0) if audit else 0,
        "strict_production_gate_unchanged": bool(audit.get("strict_production_gate_unchanged")) if audit else False,
        "ready_for_launch": bool(audit.get("ready_for_launch")) if audit else False,
    }


def build_completion_audit(
    *,
    todo_path: str | Path = ROOT / "tasks/todo.md",
    manifest_path: str | Path | None = ROOT / "artifacts/production-closure-manifest.example.json",
    evidence_plan_path: str | Path | None = None,
    evidence_package_path: str | Path | None = None,
    artifact_inventory_path: str | Path | None = None,
    artifact_bundle_root: str | Path | None = None,
    local_production_audit_path: str | Path | None = None,
    local_ai_acceptance_path: str | Path | None = None,
    local_benchmark_quality_package_path: str | Path | None = None,
    local_data_unblock_audit_path: str | Path | None = None,
) -> dict[str, Any]:
    production_audit = audit_production_tasks(
        todo_path=todo_path,
        manifest_path=manifest_path,
        local_benchmark_quality_package_path=local_benchmark_quality_package_path,
        local_data_unblock_audit_path=local_data_unblock_audit_path,
    )
    evidence_plan = build_evidence_collection_plan(production_audit)
    plan_validation = validate_evidence_collection_plan(evidence_plan)
    local_production_audit = _load_optional_json_object(local_production_audit_path, label="local production audit")
    local_ai_acceptance = _load_optional_json_object(local_ai_acceptance_path, label="local AI capability acceptance")
    local_evidence = _local_production_evidence_status(local_production_audit, local_ai_acceptance)
    local_mode = bool(local_evidence["enabled"])
    local_goal_passed = bool(local_evidence["audit_passed"] and local_evidence["ai_acceptance_passed"])
    release_gate: dict[str, Any] | None = None
    release_gate_passed = False
    if evidence_plan_path and evidence_package_path and artifact_inventory_path and manifest_path:
        evidence_plan_data = json.loads(Path(evidence_plan_path).read_text(encoding="utf-8"))
        evidence_package = json.loads(Path(evidence_package_path).read_text(encoding="utf-8"))
        artifact_inventory = json.loads(Path(artifact_inventory_path).read_text(encoding="utf-8"))
        base_manifest = json.loads(Path(manifest_path).read_text(encoding="utf-8"))
        if isinstance(evidence_plan_data, Mapping) and isinstance(evidence_package, Mapping) and isinstance(artifact_inventory, Mapping) and isinstance(base_manifest, Mapping):
            release_gate = run_production_release_gate(
                plan=evidence_plan_data,
                base_manifest=base_manifest,
                evidence_package=evidence_package,
                artifact_inventory=artifact_inventory,
                artifact_bundle_root=artifact_bundle_root,
                require_artifact_inventory=True,
            )
            release_gate_passed = release_gate.get("status") == "passed"

    doing_count = int(production_audit.get("doing_task_count", 0) or 0)
    blocked_count = int(production_audit.get("blocked_task_count", 0) or 0)
    open_count = int(production_audit.get("open_task_count", 0) or 0)
    has_real_closure_evidence = bool(production_audit.get("has_real_closure_evidence"))
    needs_code_work = int(production_audit.get("counts", {}).get("needs_code_work", 0) or 0)
    blocked_external_evidence = int(production_audit.get("counts", {}).get("blocked_external_evidence", 0) or 0)
    done_by_evidence = int(production_audit.get("done_by_real_evidence_count", 0) or 0)

    manifest_validation = production_audit.get("manifest_validation") or {}
    manifest_structurally_valid = bool(isinstance(manifest_validation, Mapping) and manifest_validation.get("passed"))

    requirements = [
        _requirement(
            "R1",
            "tasks/todo.md 中不能再有 DOING 半成品任务。",
            status="passed" if doing_count == 0 else "failed",
            evidence=[f"production_task_closure_audit.doing_task_count={doing_count}"],
            gap="" if doing_count == 0 else "仍存在 DOING 任务。",
        ),
        _requirement(
            "R2",
            "剩余任务必须区分代码缺口和外部证据缺口。",
            status="passed" if needs_code_work == 0 and blocked_external_evidence + done_by_evidence == blocked_count else "failed",
            evidence=[
                f"production_task_closure_audit.counts.needs_code_work={needs_code_work}",
                f"production_task_closure_audit.counts.blocked_external_evidence={blocked_external_evidence}",
                f"production_task_closure_audit.done_by_real_evidence_count={done_by_evidence}",
                f"production_task_closure_audit.blocked_task_count={blocked_count}",
            ],
            gap="" if needs_code_work == 0 else "仍存在代码层缺口。",
        ),
        _requirement(
            "R3",
            "生产闭环证据必须匹配部署目标；本机长期运行可用本机生产审计，非本机组织级发布必须有真实 staging/production 证据。",
            status="passed" if (local_goal_passed or (has_real_closure_evidence and release_gate_passed)) else "blocked",
            evidence=[
                f"target_mode={local_evidence['target_mode']}",
                f"local_production_audit.passed={local_evidence['audit_passed']}",
                f"local_ai_acceptance.passed={local_evidence['ai_acceptance_passed']}",
                f"production_task_closure_audit.has_real_closure_evidence={has_real_closure_evidence}",
            ],
            gap=""
            if (local_goal_passed or (has_real_closure_evidence and release_gate_passed))
            else "缺本机生产审计通过结果，或缺真实 staging/production artifact URI、artifact inventory、release gate 通过结果。",
        ),
        _requirement(
            "R4",
            "生产 manifest 模板只能作为结构样例，不能被默认发布校验误判为可发布。",
            status="passed" if manifest_structurally_valid else "failed",
            evidence=[
                f"template_manifest_structural_validation={manifest_structurally_valid}",
                f"production_task_closure_audit.has_real_closure_evidence={has_real_closure_evidence}",
            ],
            gap="" if manifest_structurally_valid else "manifest 模板或真实证据状态不清晰。",
        ),
        _requirement(
            "R5",
            "每个真实外部证据阻塞项必须能分派 owner、readiness endpoint 和 artifact 字段。",
            status="passed" if plan_validation.get("passed") else "failed",
            evidence=[
                f"production_evidence_plan_check.status={plan_validation.get('status')}",
                f"production_evidence_plan_check.task_count={plan_validation.get('task_count')}",
            ],
            gap="" if plan_validation.get("passed") else "证据采集计划不完整。",
        ),
        _requirement(
            "R6",
            "项目目标实现标准：部署目标对应的生产证据齐备；本机长期运行不要求非本机组织级发布证据。",
            status="passed" if local_goal_passed or (open_count == 0 and has_real_closure_evidence and release_gate_passed) else "blocked",
            evidence=[
                f"production_task_closure_audit.open_task_count={open_count}",
                f"production_task_closure_audit.has_real_closure_evidence={has_real_closure_evidence}",
                f"production_release_gate.status={release_gate.get('status') if release_gate else 'not_run'}",
                f"local_production_audit.status={local_production_audit.get('status') if local_production_audit else 'not_run'}",
                f"local_ai_acceptance.status={local_ai_acceptance.get('status') if local_ai_acceptance else 'not_run'}",
            ],
            gap=""
            if local_goal_passed or (open_count == 0 and has_real_closure_evidence and release_gate_passed)
            else "仍有开放任务、缺目标部署口径对应的生产证据，或 release gate 未通过。",
        ),
    ]

    failed = [row for row in requirements if row["status"] == "failed"]
    blocked = [row for row in requirements if row["status"] == "blocked"]
    achieved = not failed and not blocked
    summary = {
        "target_mode": local_evidence["target_mode"],
        "doing_task_count": doing_count,
        "blocked_task_count": blocked_count,
        "open_task_count": open_count,
        "needs_code_work_count": needs_code_work,
        "blocked_external_evidence_count": blocked_external_evidence,
        "has_real_closure_evidence": has_real_closure_evidence,
        "local_production_ready": local_goal_passed,
    }
    return {
        "objective": OBJECTIVE,
        "status": "achieved" if achieved else "not_achieved",
        "achieved": achieved,
        **summary,
        "failed_requirement_ids": [row["requirement_id"] for row in failed],
        "blocked_requirement_ids": [row["requirement_id"] for row in blocked],
        "open_requirement_ids": [row["requirement_id"] for row in requirements if row["status"] != "passed"],
        "failed_requirements": failed,
        "blocked_requirements": blocked,
        "summary": summary,
        "prompt_to_artifact_checklist": requirements,
        "production_task_closure_audit": production_audit,
        "evidence_collection_plan_validation": plan_validation,
        "production_release_gate": release_gate,
        "local_production_evidence": local_evidence,
        "next_gate": "local personal-production target is complete when local-production-audit and optional local AI acceptance pass; non-local organizational release still requires real staging/production artifact URIs, filled plan, artifact inventory, and release gate",
        "production_boundary": "local_only_personal_production is valid for this machine and does not enable live broker execution; non-local organizational release gate remains strict",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit whether the user objective is actually complete.")
    parser.add_argument("--todo", default=str(ROOT / "tasks/todo.md"))
    parser.add_argument("--manifest", default=str(ROOT / "artifacts/production-closure-manifest.example.json"))
    parser.add_argument("--evidence-plan", default="", help="Optional filled evidence collection plan for strict release gate audit.")
    parser.add_argument("--evidence-package", default="", help="Optional readiness evidence package for strict release gate audit.")
    parser.add_argument("--artifact-inventory", default="", help="Optional artifact inventory for strict release gate audit.")
    parser.add_argument("--artifact-bundle-root", default="", help="Optional local/exported evidence bundle root for release artifact hash/size verification.")
    parser.add_argument("--local-production-audit", default="", help="Optional local-only production audit JSON for personal on-machine completion.")
    parser.add_argument("--local-ai-acceptance", default="", help="Optional local AI capability acceptance JSON for personal on-machine completion.")
    parser.add_argument("--local-benchmark-quality-package", default="", help="Optional local benchmark quality package JSON for T-402 local completion.")
    parser.add_argument("--local-data-unblock-audit", default="", help="Optional local data unblock audit JSON for T-402 local completion.")
    parser.add_argument("--output", default="", help="Optional path to write the completion audit JSON.")
    args = parser.parse_args()

    result = build_completion_audit(
        todo_path=args.todo,
        manifest_path=args.manifest,
        evidence_plan_path=args.evidence_plan or None,
        evidence_package_path=args.evidence_package or None,
        artifact_inventory_path=args.artifact_inventory or None,
        artifact_bundle_root=args.artifact_bundle_root or None,
        local_production_audit_path=args.local_production_audit or None,
        local_ai_acceptance_path=args.local_ai_acceptance or None,
        local_benchmark_quality_package_path=args.local_benchmark_quality_package or None,
        local_data_unblock_audit_path=args.local_data_unblock_audit or None,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        _atomic_write_text(args.output, rendered + "\n")
    print(rendered)
    if not result["achieved"]:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
