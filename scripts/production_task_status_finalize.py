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

from scripts.production_evidence_plan_to_manifest import load_json_object
from scripts.production_release_gate import run_production_release_gate
from scripts.production_task_closure_audit import parse_tasks_by_status


TASK_HEADER_RE = re.compile(r"^- `(?P<status>TODO|DOING|DONE|BLOCKED)` (?P<task_id>T-\d+[A-Z]?)\b(?P<rest>.*)$", re.M)


def _task_ids_from_plan(plan: Mapping[str, Any]) -> list[str]:
    task_ids: list[str] = []
    for row in plan.get("tasks", []):
        if isinstance(row, Mapping):
            task_id = str(row.get("task_id", "")).strip()
            if task_id:
                task_ids.append(task_id)
    return task_ids


def _insert_evidence_note(block: str, note: str) -> str:
    lines = block.splitlines()
    insert_at = 1 if lines else 0
    if any(note in line for line in lines):
        return block
    lines.insert(insert_at, f"  - 已收口：{note}")
    return "\n".join(lines)


def _atomic_write_text(path: str | Path, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f".{output_path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(output_path)


def _finalize_task_blocks(todo_text: str, *, task_ids: set[str], note: str) -> tuple[str, list[str]]:
    matches = list(TASK_HEADER_RE.finditer(todo_text))
    if not matches:
        return todo_text, []
    chunks: list[str] = []
    cursor = 0
    finalized: list[str] = []
    for idx, match in enumerate(matches):
        start = match.start()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(todo_text)
        chunks.append(todo_text[cursor:start])
        block = todo_text[start:end].rstrip("\n")
        task_id = match.group("task_id")
        status = match.group("status")
        if task_id in task_ids and status == "BLOCKED":
            block = TASK_HEADER_RE.sub(lambda m: f"- `DONE` {m.group('task_id')}{m.group('rest')}", block, count=1)
            block = _insert_evidence_note(block, note)
            finalized.append(task_id)
        chunks.append(block)
        chunks.append("\n\n" if end < len(todo_text) else "")
        cursor = end
    chunks.append(todo_text[cursor:])
    return "".join(chunks).rstrip() + "\n", finalized


def finalize_production_task_statuses(
    *,
    todo_path: str | Path,
    plan: Mapping[str, Any],
    base_manifest: Mapping[str, Any],
    evidence_package: Mapping[str, Any],
    artifact_inventory: Mapping[str, Any],
    artifact_bundle_root: str | Path | None = None,
    manifest_output: str | Path | None = None,
    task_ids: list[str] | None = None,
    dry_run: bool = False,
) -> dict[str, Any]:
    release_gate = run_production_release_gate(
        plan=plan,
        base_manifest=base_manifest,
        evidence_package=evidence_package,
        artifact_inventory=artifact_inventory,
        artifact_bundle_root=artifact_bundle_root,
        manifest_output=manifest_output,
    )
    if release_gate.get("status") != "passed":
        return {
            "status": "failed",
            "failed_stage": "production_release_gate",
            "release_gate": release_gate,
            "updated_task_ids": [],
            "dry_run": dry_run,
        }

    requested_task_ids = set(task_ids or _task_ids_from_plan(plan))
    current_statuses = parse_tasks_by_status(todo_path)
    blocked_ids = set(current_statuses.get("BLOCKED", []))
    eligible_ids = requested_task_ids & blocked_ids
    ineligible_ids = sorted(requested_task_ids - eligible_ids)
    todo_file = Path(todo_path)
    note = (
        "真实 staging/production evidence plan、readiness evidence package、artifact inventory"
        " 和 release gate 已通过；详见生产闭环 manifest / inventory。"
    )
    updated_text, finalized = _finalize_task_blocks(todo_file.read_text(encoding="utf-8"), task_ids=eligible_ids, note=note)
    if not dry_run:
        _atomic_write_text(todo_file, updated_text)
    return {
        "status": "passed",
        "dry_run": dry_run,
        "updated_task_ids": finalized,
        "updated_task_count": len(finalized),
        "ineligible_task_ids": ineligible_ids,
        "release_gate": release_gate,
        "production_boundary": "task statuses are finalized only after strict release gate passes; this script never enables live broker or automatic order execution",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Finalize BLOCKED production tasks to DONE after strict release evidence gate passes.")
    parser.add_argument("--todo", default=str(ROOT / "tasks/todo.md"))
    parser.add_argument("--plan", required=True, help="Filled production evidence collection plan JSON.")
    parser.add_argument("--base", default=str(ROOT / "artifacts/production-closure-manifest.example.json"))
    parser.add_argument("--evidence-package", required=True)
    parser.add_argument("--artifact-inventory", required=True)
    parser.add_argument("--artifact-bundle-root", default="")
    parser.add_argument("--manifest-output", default="")
    parser.add_argument("--task-id", action="append", default=[], help="Specific task id to finalize; default uses every task in the plan.")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output", default="")
    args = parser.parse_args()

    result = finalize_production_task_statuses(
        todo_path=args.todo,
        plan=load_json_object(args.plan, label="evidence plan"),
        base_manifest=load_json_object(args.base, label="base manifest"),
        evidence_package=load_json_object(args.evidence_package, label="readiness evidence package"),
        artifact_inventory=load_json_object(args.artifact_inventory, label="artifact inventory"),
        artifact_bundle_root=args.artifact_bundle_root or None,
        manifest_output=args.manifest_output or None,
        task_ids=args.task_id or None,
        dry_run=args.dry_run,
    )
    rendered = json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        _atomic_write_text(args.output, rendered + "\n")
    print(rendered)
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
