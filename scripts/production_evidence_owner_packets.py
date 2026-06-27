from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
import sys
from typing import Any, Mapping


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.production_evidence_plan_check import validate_evidence_collection_plan


def _atomic_write_text(path: str | Path, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f".{output_path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(output_path)


def build_owner_packets(plan: Mapping[str, Any]) -> dict[str, Any]:
    validation = validate_evidence_collection_plan(plan)
    if not validation["passed"]:
        raise AssertionError(json.dumps(validation, ensure_ascii=False, sort_keys=True))
    tasks = [dict(item) for item in plan.get("tasks", []) if isinstance(item, Mapping)]
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for task in tasks:
        grouped[str(task.get("owner_role", "未分配"))].append(task)
    owner_packets: list[dict[str, Any]] = []
    for owner_role, rows in sorted(grouped.items()):
        artifact_field_count = sum(len(row.get("artifact_fields", [])) for row in rows)
        owner_packets.append(
            {
                "owner_role": owner_role,
                "task_count": len(rows),
                "artifact_field_count": artifact_field_count,
                "task_ids": [str(row.get("task_id", "")) for row in rows],
                "tasks": rows,
            }
        )
    return {
        "packet_id": "production_external_evidence_owner_packets",
        "source_plan_id": plan.get("plan_id", ""),
        "production_boundary": "owner packets are collection instructions only; they are not release evidence",
        "owner_count": len(owner_packets),
        "task_count": len(tasks),
        "artifact_field_count": sum(packet["artifact_field_count"] for packet in owner_packets),
        "owners": owner_packets,
    }


def render_owner_packets_markdown(packet: Mapping[str, Any]) -> str:
    lines = [
        "# Production External Evidence Owner Packets",
        "",
        "- Status: active",
        "- Owner group: PM / Release Coordination",
        "- Last updated: 2026-06-27",
        "- Related tasks: T-402, T-404, T-405, T-406, T-406A, T-407, T-408, T-409, T-410, T-411, T-412, T-414, T-416, T-418, T-419, T-420, T-421",
        "- Scope: owner-by-owner external evidence collection instructions for non-local production closure",
        "- Non-goals: local-only release approval, generating or fabricating evidence, broker integration, automatic trading",
        "",
        "## Purpose",
        "",
        "These packets convert the production evidence collection plan into owner-specific work. They are collection instructions only and are not release evidence. Every artifact URI must later be replaced with a concrete external staging/production archive URI, validated by `scripts/production_evidence_plan_check.py --require-filled-uris`, covered by artifact inventory, and passed through the strict release gate.",
        "",
        "## Summary",
        "",
        f"- Owner packets: {packet.get('owner_count', 0)}",
        f"- External evidence tasks: {packet.get('task_count', 0)}",
        f"- Required artifact fields: {packet.get('artifact_field_count', 0)}",
        f"- Boundary: {packet.get('production_boundary', '')}",
        "",
    ]
    for owner in packet.get("owners", []):
        if not isinstance(owner, Mapping):
            continue
        lines.extend(
            [
                f"## {owner.get('owner_role', '未分配')}",
                "",
                f"- Task count: {owner.get('task_count', 0)}",
                f"- Artifact field count: {owner.get('artifact_field_count', 0)}",
                f"- Task IDs: {', '.join(str(item) for item in owner.get('task_ids', []))}",
                "",
            ]
        )
        for task in owner.get("tasks", []):
            if not isinstance(task, Mapping):
                continue
            fields = [str(item) for item in task.get("artifact_fields", [])]
            blockers = [str(item) for item in task.get("external_evidence_blockers", [])]
            lines.extend(
                [
                    f"### {task.get('task_id', '')}",
                    "",
                    f"- Readiness endpoint: `{task.get('readiness_endpoint', '')}`",
                    f"- Acceptance rule: {task.get('acceptance_rule', '')}",
                    "- External blockers:",
                    *[f"  - {item}" for item in blockers],
                    "- Required artifact fields:",
                    *[f"  - `{field}`" for field in fields],
                    "- URI template:",
                ]
            )
            template = task.get("artifact_uri_template", {})
            if isinstance(template, Mapping):
                for field in fields:
                    lines.append(f"  - `{field}`: `{template.get(field, '')}`")
            lines.append("")
    lines.extend(
        [
            "## Release Gate Handoff",
            "",
            "After owners upload the real evidence objects, run:",
            "",
            "```bash",
            "python3 scripts/production_evidence_plan_check.py artifacts/production-evidence-collection-plan.json --require-filled-uris",
            "python3 scripts/production_artifact_inventory_check.py artifacts/production-artifact-inventory.json --plan artifacts/production-evidence-collection-plan.json --evidence-package artifacts/readiness-evidence-package.json --manifest artifacts/production-closure-manifest.json",
            "python3 scripts/production_release_gate.py --plan artifacts/production-evidence-collection-plan.json --evidence-package artifacts/readiness-evidence-package.json --artifact-inventory artifacts/production-artifact-inventory.json --artifact-bundle-root artifacts/production-evidence-bundle --manifest-output artifacts/production-closure-manifest.json",
            "```",
            "",
            "Do not use local-only artifacts, demo artifacts, localhost URLs, `file://`, `local://`, or `artifact://staging-local` as production evidence.",
        ]
    )
    return "\n".join(lines) + "\n"


def validate_owner_packets(packet: Mapping[str, Any]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []

    def expect(condition: bool, check: str, error: str, **extra: Any) -> None:
        if not condition:
            failures.append({"check": check, "error": error, **extra})

    owners = [dict(item) for item in packet.get("owners", []) if isinstance(item, Mapping)]
    expect(packet.get("packet_id") == "production_external_evidence_owner_packets", "packet_id", "unexpected packet id")
    expect("not release evidence" in str(packet.get("production_boundary", "")).lower(), "production_boundary", "packets must state they are not release evidence")
    expect(int(packet.get("owner_count", -1)) == len(owners), "owner_count", "owner_count must match owner rows")
    task_ids: list[str] = []
    artifact_field_count = 0
    for owner in owners:
        tasks = [dict(item) for item in owner.get("tasks", []) if isinstance(item, Mapping)]
        expect(int(owner.get("task_count", -1)) == len(tasks), "owner_task_count", "owner task_count mismatch", owner_role=owner.get("owner_role"))
        owner_fields = sum(len(task.get("artifact_fields", [])) for task in tasks)
        artifact_field_count += owner_fields
        expect(int(owner.get("artifact_field_count", -1)) == owner_fields, "owner_artifact_field_count", "owner artifact_field_count mismatch", owner_role=owner.get("owner_role"))
        for task in tasks:
            task_id = str(task.get("task_id", ""))
            task_ids.append(task_id)
            expect(str(task.get("status", "")) == "blocked_external_evidence", "task_status", "task must remain blocked_external_evidence", task_id=task_id)
            expect(bool(task.get("readiness_endpoint")), "readiness_endpoint", "readiness endpoint is required", task_id=task_id)
            expect(bool(task.get("artifact_fields")), "artifact_fields", "artifact fields are required", task_id=task_id)
            expect(bool(task.get("external_evidence_blockers")), "external_evidence_blockers", "external blockers are required", task_id=task_id)
    duplicates = sorted(task_id for task_id in set(task_ids) if task_ids.count(task_id) > 1)
    expect(not duplicates, "duplicate_task_ids", "task ids must not be duplicated across owners", duplicates=duplicates)
    expect(int(packet.get("task_count", -1)) == len(task_ids), "task_count", "task_count must match all owner task rows")
    expect(int(packet.get("artifact_field_count", -1)) == artifact_field_count, "artifact_field_count", "artifact_field_count must match all fields")
    passed = not failures
    return {
        "status": "passed" if passed else "failed",
        "passed": passed,
        "owner_count": len(owners),
        "task_count": len(task_ids),
        "artifact_field_count": artifact_field_count,
        "failure_count": len(failures),
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build owner-specific production evidence collection packets.")
    parser.add_argument("plan_json", help="Production evidence collection plan JSON.")
    parser.add_argument("--output-json", default="", help="Optional output JSON path for the owner packets.")
    parser.add_argument("--output-md", default="", help="Optional output Markdown path for owner-readable packets.")
    args = parser.parse_args()
    plan = json.loads(Path(args.plan_json).read_text(encoding="utf-8"))
    packet = build_owner_packets(plan)
    validation = validate_owner_packets(packet)
    rendered_json = json.dumps(packet, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output_json:
        _atomic_write_text(args.output_json, rendered_json + "\n")
    if args.output_md:
        _atomic_write_text(args.output_md, render_owner_packets_markdown(packet))
    print(json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True))
    if not validation["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
