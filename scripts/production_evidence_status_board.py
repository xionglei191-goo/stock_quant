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

from app.readiness_artifacts import is_production_artifact_uri
from scripts.production_evidence_plan_check import validate_evidence_collection_plan


def _atomic_write_text(path: str | Path, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f".{output_path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(output_path)


def _has_placeholder(value: str) -> bool:
    lowered = value.lower()
    return "<" in value or ">" in value or "{release-id}" in value or "example" in lowered


def build_status_board(plan: Mapping[str, Any]) -> dict[str, Any]:
    validation = validate_evidence_collection_plan(plan)
    if not validation["passed"]:
        raise AssertionError(json.dumps(validation, ensure_ascii=False, sort_keys=True))
    owner_rows: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "owner_role": "",
            "task_count": 0,
            "artifact_field_count": 0,
            "filled_uri_count": 0,
            "placeholder_uri_count": 0,
            "invalid_uri_count": 0,
            "tasks": [],
        }
    )
    board_tasks: list[dict[str, Any]] = []
    for raw_task in plan.get("tasks", []):
        if not isinstance(raw_task, Mapping):
            continue
        task_id = str(raw_task.get("task_id", ""))
        owner_role = str(raw_task.get("owner_role", "未分配"))
        fields = [str(item) for item in raw_task.get("artifact_fields", [])]
        template = raw_task.get("artifact_uri_template", {})
        field_rows: list[dict[str, Any]] = []
        filled_count = 0
        placeholder_count = 0
        invalid_count = 0
        for field in fields:
            uri = str(template.get(field, "")) if isinstance(template, Mapping) else ""
            has_placeholder = _has_placeholder(uri)
            production_uri = is_production_artifact_uri(uri)
            status = "filled" if production_uri and not has_placeholder else "placeholder" if has_placeholder else "invalid"
            if status == "filled":
                filled_count += 1
            elif status == "placeholder":
                placeholder_count += 1
            else:
                invalid_count += 1
            field_rows.append(
                {
                    "field": field,
                    "uri": uri,
                    "status": status,
                    "production_artifact_uri": production_uri,
                    "has_placeholder": has_placeholder,
                }
            )
        task_status = "ready_for_inventory" if filled_count == len(fields) and invalid_count == 0 else "waiting_for_external_uri"
        next_action = (
            "Build artifact inventory and run strict release gate."
            if task_status == "ready_for_inventory"
            else "Replace every placeholder with a concrete external staging/production archive URI."
        )
        task_row = {
            "task_id": task_id,
            "owner_role": owner_role,
            "readiness_endpoint": raw_task.get("readiness_endpoint", ""),
            "status": task_status,
            "artifact_field_count": len(fields),
            "filled_uri_count": filled_count,
            "placeholder_uri_count": placeholder_count,
            "invalid_uri_count": invalid_count,
            "next_action": next_action,
            "fields": field_rows,
        }
        board_tasks.append(task_row)
        owner = owner_rows[owner_role]
        owner["owner_role"] = owner_role
        owner["task_count"] += 1
        owner["artifact_field_count"] += len(fields)
        owner["filled_uri_count"] += filled_count
        owner["placeholder_uri_count"] += placeholder_count
        owner["invalid_uri_count"] += invalid_count
        owner["tasks"].append(task_row)
    owner_summaries = sorted(owner_rows.values(), key=lambda item: str(item["owner_role"]))
    artifact_field_count = sum(int(owner["artifact_field_count"]) for owner in owner_summaries)
    filled_uri_count = sum(int(owner["filled_uri_count"]) for owner in owner_summaries)
    placeholder_uri_count = sum(int(owner["placeholder_uri_count"]) for owner in owner_summaries)
    invalid_uri_count = sum(int(owner["invalid_uri_count"]) for owner in owner_summaries)
    ready_task_count = sum(1 for item in board_tasks if item["status"] == "ready_for_inventory")
    return {
        "board_id": "production_external_evidence_status_board",
        "source_plan_id": plan.get("plan_id", ""),
        "status": "ready_for_release_gate" if ready_task_count == len(board_tasks) and invalid_uri_count == 0 else "waiting_for_external_evidence",
        "production_boundary": "status board only; not release evidence and not a substitute for artifact inventory or release gate",
        "owner_count": len(owner_summaries),
        "task_count": len(board_tasks),
        "ready_task_count": ready_task_count,
        "waiting_task_count": len(board_tasks) - ready_task_count,
        "artifact_field_count": artifact_field_count,
        "filled_uri_count": filled_uri_count,
        "placeholder_uri_count": placeholder_uri_count,
        "invalid_uri_count": invalid_uri_count,
        "owners": owner_summaries,
    }


def validate_status_board(board: Mapping[str, Any]) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []

    def expect(condition: bool, check: str, error: str, **extra: Any) -> None:
        if not condition:
            failures.append({"check": check, "error": error, **extra})

    owners = [dict(item) for item in board.get("owners", []) if isinstance(item, Mapping)]
    tasks = [task for owner in owners for task in owner.get("tasks", []) if isinstance(task, Mapping)]
    expect(board.get("board_id") == "production_external_evidence_status_board", "board_id", "unexpected board id")
    expect("not release evidence" in str(board.get("production_boundary", "")).lower(), "production_boundary", "board must state it is not release evidence")
    expect(int(board.get("owner_count", -1)) == len(owners), "owner_count", "owner count mismatch")
    expect(int(board.get("task_count", -1)) == len(tasks), "task_count", "task count mismatch")
    expect(int(board.get("ready_task_count", 0)) + int(board.get("waiting_task_count", 0)) == len(tasks), "task_status_counts", "ready plus waiting must match task count")
    field_count = sum(int(task.get("artifact_field_count", 0)) for task in tasks)
    filled_count = sum(int(task.get("filled_uri_count", 0)) for task in tasks)
    placeholder_count = sum(int(task.get("placeholder_uri_count", 0)) for task in tasks)
    invalid_count = sum(int(task.get("invalid_uri_count", 0)) for task in tasks)
    expect(int(board.get("artifact_field_count", -1)) == field_count, "artifact_field_count", "field count mismatch")
    expect(int(board.get("filled_uri_count", -1)) == filled_count, "filled_uri_count", "filled count mismatch")
    expect(int(board.get("placeholder_uri_count", -1)) == placeholder_count, "placeholder_uri_count", "placeholder count mismatch")
    expect(int(board.get("invalid_uri_count", -1)) == invalid_count, "invalid_uri_count", "invalid count mismatch")
    passed = not failures
    return {
        "status": "passed" if passed else "failed",
        "passed": passed,
        "owner_count": len(owners),
        "task_count": len(tasks),
        "artifact_field_count": field_count,
        "failure_count": len(failures),
        "failures": failures,
    }


def render_status_board_markdown(board: Mapping[str, Any]) -> str:
    lines = [
        "# Production External Evidence Status Board",
        "",
        "- Status: active",
        "- Owner group: PM / Release Coordination",
        "- Last updated: 2026-06-27",
        "- Related tasks: T-402, T-404, T-405, T-406, T-406A, T-407, T-408, T-409, T-410, T-411, T-412, T-414, T-416, T-418, T-419, T-420, T-421",
        "- Scope: PM tracking board for external evidence URI readiness",
        "- Non-goals: release approval, local-only evidence approval, fabricating evidence, changing task status to DONE",
        "",
        "## Summary",
        "",
        f"- Board status: `{board.get('status', '')}`",
        f"- Owners: {board.get('owner_count', 0)}",
        f"- Tasks: {board.get('task_count', 0)}",
        f"- Ready for inventory: {board.get('ready_task_count', 0)}",
        f"- Waiting for external URI: {board.get('waiting_task_count', 0)}",
        f"- Artifact fields: {board.get('artifact_field_count', 0)}",
        f"- Filled URIs: {board.get('filled_uri_count', 0)}",
        f"- Placeholder URIs: {board.get('placeholder_uri_count', 0)}",
        f"- Invalid URIs: {board.get('invalid_uri_count', 0)}",
        f"- Boundary: {board.get('production_boundary', '')}",
        "",
    ]
    for owner in board.get("owners", []):
        if not isinstance(owner, Mapping):
            continue
        lines.extend(
            [
                f"## {owner.get('owner_role', '未分配')}",
                "",
                f"- Tasks: {owner.get('task_count', 0)}",
                f"- Artifact fields: {owner.get('artifact_field_count', 0)}",
                f"- Filled / placeholder / invalid: {owner.get('filled_uri_count', 0)} / {owner.get('placeholder_uri_count', 0)} / {owner.get('invalid_uri_count', 0)}",
                "",
                "| Task | Status | Endpoint | Filled | Placeholder | Invalid | Next action |",
                "| --- | --- | --- | ---: | ---: | ---: | --- |",
            ]
        )
        for task in owner.get("tasks", []):
            if not isinstance(task, Mapping):
                continue
            lines.append(
                f"| `{task.get('task_id', '')}` | `{task.get('status', '')}` | `{task.get('readiness_endpoint', '')}` | {task.get('filled_uri_count', 0)} | {task.get('placeholder_uri_count', 0)} | {task.get('invalid_uri_count', 0)} | {task.get('next_action', '')} |"
            )
        lines.append("")
    lines.extend(
        [
            "## Release Gate Rule",
            "",
            "This board is complete only when every task is `ready_for_inventory`, artifact inventory covers every URI, and `scripts/production_release_gate.py` passes. Until then, the matching `tasks/todo.md` entries must remain `BLOCKED`.",
        ]
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a PM status board for external production evidence URI readiness.")
    parser.add_argument("plan_json", help="Production evidence collection plan JSON.")
    parser.add_argument("--output-json", default="", help="Optional output JSON path.")
    parser.add_argument("--output-md", default="", help="Optional output Markdown path.")
    args = parser.parse_args()
    plan = json.loads(Path(args.plan_json).read_text(encoding="utf-8"))
    board = build_status_board(plan)
    validation = validate_status_board(board)
    if args.output_json:
        _atomic_write_text(args.output_json, json.dumps(board, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    if args.output_md:
        _atomic_write_text(args.output_md, render_status_board_markdown(board))
    print(json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True))
    if not validation["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
