from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.production_evidence_owner_packets import build_owner_packets, owner_group_for_role, validate_owner_packets
from scripts.production_evidence_status_board import build_status_board, validate_status_board
from scripts.production_evidence_plan_check import validate_evidence_collection_plan


EXECUTION_PHASES = [
    {
        "phase_id": "P1",
        "name": "Owner evidence collection",
        "exit_criteria": "Every owner replaces placeholder URIs with concrete external staging/production archive URIs.",
        "command": "python3 scripts/production_evidence_plan_check.py artifacts/production-evidence-collection-plan.json --require-filled-uris",
    },
    {
        "phase_id": "P2",
        "name": "Artifact inventory",
        "exit_criteria": "Every evidence URI has sha256, size, environment, producer, owner, retention, and immutable/object-lock metadata.",
        "command": "python3 scripts/production_artifact_inventory_check.py artifacts/production-artifact-inventory.json --plan artifacts/production-evidence-collection-plan.json --evidence-package artifacts/readiness-evidence-package.json --manifest artifacts/production-closure-manifest.json",
    },
    {
        "phase_id": "P3",
        "name": "Strict release gate",
        "exit_criteria": "The filled plan, readiness evidence package, artifact inventory, generated manifest, and optional closure dry-run all pass.",
        "command": "python3 scripts/production_release_gate.py --plan artifacts/production-evidence-collection-plan.json --evidence-package artifacts/readiness-evidence-package.json --artifact-inventory artifacts/production-artifact-inventory.json --artifact-bundle-root artifacts/production-evidence-bundle --manifest-output artifacts/production-closure-manifest.json",
    },
    {
        "phase_id": "P4",
        "name": "Task status finalization",
        "exit_criteria": "Only tasks covered by a passed strict release gate are moved from BLOCKED to DONE.",
        "command": "python3 scripts/production_task_status_finalize.py --todo tasks/todo.md --plan artifacts/production-evidence-collection-plan.json --evidence-package artifacts/readiness-evidence-package.json --artifact-inventory artifacts/production-artifact-inventory.json --manifest artifacts/production-closure-manifest.json",
    },
]


def _atomic_write_text(path: str | Path, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f".{output_path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(output_path)


def build_execution_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    plan_validation = validate_evidence_collection_plan(plan)
    if not plan_validation["passed"]:
        raise AssertionError(json.dumps(plan_validation, ensure_ascii=False, sort_keys=True))
    owner_packets = build_owner_packets(plan)
    owner_validation = validate_owner_packets(owner_packets)
    if not owner_validation["passed"]:
        raise AssertionError(json.dumps(owner_validation, ensure_ascii=False, sort_keys=True))
    status_board = build_status_board(plan)
    board_validation = validate_status_board(status_board)
    if not board_validation["passed"]:
        raise AssertionError(json.dumps(board_validation, ensure_ascii=False, sort_keys=True))

    owner_runs: list[dict[str, Any]] = []
    for owner in owner_packets.get("owners", []):
        if not isinstance(owner, Mapping):
            continue
        owner_role = str(owner.get("owner_role", "未分配"))
        owner_group = owner_group_for_role(owner_role)
        task_ids = [str(item) for item in owner.get("task_ids", [])]
        artifact_fields = [
            {"task_id": str(task.get("task_id", "")), "fields": [str(field) for field in task.get("artifact_fields", [])]}
            for task in owner.get("tasks", [])
            if isinstance(task, Mapping)
        ]
        owner_runs.append(
            {
                "owner_role": owner_role,
                "owner_group": owner_group,
                "task_count": int(owner.get("task_count", 0)),
                "artifact_field_count": int(owner.get("artifact_field_count", 0)),
                "task_ids": task_ids,
                "artifact_fields": artifact_fields,
                "task_packet_paths": [f"docs/production-evidence-task-packets/{task_id.lower()}-production-evidence.md" for task_id in task_ids],
                "handoff_command": f"python3 scripts/production_evidence_owner_packets.py artifacts/production-evidence-collection-plan.json --output-dir docs/production-evidence-task-packets",
                "exit_criteria": "All task artifact URI placeholders for this owner are replaced by real external staging/production URIs and reviewed by the listed reviewer groups.",
            }
        )

    return {
        "plan_id": "production_external_evidence_execution_plan",
        "source_plan_id": plan.get("plan_id", ""),
        "status": "waiting_for_external_evidence" if status_board.get("waiting_task_count", 0) else "ready_for_release_gate",
        "production_boundary": "execution plan only; it is not release evidence and cannot mark tasks DONE without real external artifacts and a passed release gate",
        "owner_count": owner_packets.get("owner_count", 0),
        "task_count": owner_packets.get("task_count", 0),
        "artifact_field_count": owner_packets.get("artifact_field_count", 0),
        "ready_task_count": status_board.get("ready_task_count", 0),
        "waiting_task_count": status_board.get("waiting_task_count", 0),
        "placeholder_uri_count": status_board.get("placeholder_uri_count", 0),
        "owner_runs": owner_runs,
        "execution_phases": EXECUTION_PHASES,
        "required_inputs": [
            "artifacts/production-evidence-collection-plan.json with real external URIs",
            "artifacts/readiness-evidence-package.json exported from the real staging/production system",
            "artifacts/production-artifact-inventory.json covering every evidence URI",
            "artifacts/production-evidence-bundle/ when local bundle hash verification is required",
        ],
        "blocked_until": "real external staging/production evidence URIs, inventory metadata, and release gate output are available",
    }


def validate_execution_plan(plan: Mapping[str, Any]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []

    def expect(condition: bool, check: str, error: str, **extra: Any) -> None:
        if not condition:
            failures.append({"check": check, "error": error, **extra})

    owner_runs = [dict(item) for item in plan.get("owner_runs", []) if isinstance(item, Mapping)]
    phases = [dict(item) for item in plan.get("execution_phases", []) if isinstance(item, Mapping)]
    expect(plan.get("plan_id") == "production_external_evidence_execution_plan", "plan_id", "unexpected execution plan id")
    expect("not release evidence" in str(plan.get("production_boundary", "")).lower(), "production_boundary", "execution plan must state it is not release evidence")
    expect(int(plan.get("owner_count", -1)) == len(owner_runs), "owner_count", "owner count mismatch")
    expect(int(plan.get("task_count", 0)) == sum(int(owner.get("task_count", 0)) for owner in owner_runs), "task_count", "task count mismatch")
    expect(int(plan.get("artifact_field_count", 0)) == sum(int(owner.get("artifact_field_count", 0)) for owner in owner_runs), "artifact_field_count", "artifact field count mismatch")
    expect(len(phases) == 4, "execution_phase_count", "four execution phases are required")
    for phase in phases:
        expect(bool(phase.get("command")), "phase_command", "phase command is required", phase_id=phase.get("phase_id"))
        expect(bool(phase.get("exit_criteria")), "phase_exit_criteria", "phase exit criteria is required", phase_id=phase.get("phase_id"))
    for owner in owner_runs:
        expect(bool(owner.get("owner_group")), "owner_group", "owner group is required", owner_role=owner.get("owner_role"))
        expect(bool(owner.get("task_packet_paths")), "task_packet_paths", "owner task packet paths are required", owner_role=owner.get("owner_role"))
        expect(bool(owner.get("exit_criteria")), "owner_exit_criteria", "owner exit criteria is required", owner_role=owner.get("owner_role"))
    passed = not failures
    return {
        "status": "passed" if passed else "failed",
        "passed": passed,
        "owner_count": len(owner_runs),
        "task_count": sum(int(owner.get("task_count", 0)) for owner in owner_runs),
        "artifact_field_count": sum(int(owner.get("artifact_field_count", 0)) for owner in owner_runs),
        "execution_phase_count": len(phases),
        "failure_count": len(failures),
        "failures": failures,
    }


def render_execution_plan_markdown(plan: Mapping[str, Any]) -> str:
    lines = [
        "# Production External Evidence Execution Plan",
        "",
        "- Status: active",
        "- Owner group: PM / Release Coordination",
        "- Last updated: 2026-06-27",
        "- Related tasks: T-402, T-404, T-405, T-406, T-406A, T-407, T-408, T-409, T-410, T-411, T-412, T-414, T-416, T-418, T-419, T-420, T-421",
        "- Scope: PM execution plan for collecting real external evidence, validating inventory, running release gate, and finalizing task status",
        "- Non-goals: generating evidence, accepting local-only artifacts, changing task status without strict release gate, broker integration, automatic trading",
        "",
        "## Summary",
        "",
        f"- Execution status: `{plan.get('status', '')}`",
        f"- Owners: {plan.get('owner_count', 0)}",
        f"- Tasks: {plan.get('task_count', 0)}",
        f"- Artifact fields: {plan.get('artifact_field_count', 0)}",
        f"- Ready tasks: {plan.get('ready_task_count', 0)}",
        f"- Waiting tasks: {plan.get('waiting_task_count', 0)}",
        f"- Placeholder URIs: {plan.get('placeholder_uri_count', 0)}",
        f"- Boundary: {plan.get('production_boundary', '')}",
        "",
        "## Owner Runs",
        "",
    ]
    for owner in plan.get("owner_runs", []):
        if not isinstance(owner, Mapping):
            continue
        lines.extend(
            [
                f"### {owner.get('owner_role', '未分配')}",
                "",
                f"- Owner group: {owner.get('owner_group', '')}",
                f"- Tasks: {', '.join(str(item) for item in owner.get('task_ids', []))}",
                f"- Artifact fields: {owner.get('artifact_field_count', 0)}",
                f"- Exit criteria: {owner.get('exit_criteria', '')}",
                "- Task packets:",
                *[f"  - `{path}`" for path in owner.get("task_packet_paths", [])],
                "",
            ]
        )
    lines.extend(["## Execution Phases", ""])
    for phase in plan.get("execution_phases", []):
        if not isinstance(phase, Mapping):
            continue
        lines.extend(
            [
                f"### {phase.get('phase_id', '')} {phase.get('name', '')}",
                "",
                f"- Exit criteria: {phase.get('exit_criteria', '')}",
                "",
                "```bash",
                str(phase.get("command", "")),
                "```",
                "",
            ]
        )
    lines.extend(
        [
            "## Required Inputs",
            "",
            *[f"- `{item}`" for item in plan.get("required_inputs", [])],
            "",
            "## Completion Rule",
            "",
            "The remaining BLOCKED tasks are complete only after the filled evidence plan, readiness evidence package, artifact inventory, generated manifest, and strict release gate all pass with real external staging/production evidence. This plan is a coordination artifact, not release evidence.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a PM execution plan for external production evidence collection.")
    parser.add_argument("plan_json", help="Production evidence collection plan JSON.")
    parser.add_argument("--output-json", default="", help="Optional output JSON path.")
    parser.add_argument("--output-md", default="", help="Optional output Markdown path.")
    args = parser.parse_args()
    plan = json.loads(Path(args.plan_json).read_text(encoding="utf-8"))
    execution_plan = build_execution_plan(plan)
    validation = validate_execution_plan(execution_plan)
    if args.output_json:
        _atomic_write_text(args.output_json, json.dumps(execution_plan, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    if args.output_md:
        _atomic_write_text(args.output_md, render_execution_plan_markdown(execution_plan))
    print(json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True))
    if not validation["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
