from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib import request


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "graph-enrichment-runner" / "latest.json"
DEFAULT_STATE = ROOT / "artifacts" / "graph-enrichment-runner" / "state.json"


def _post_json(base_url: str, path: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    req = request.Request(
        base_url.rstrip("/") + path,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Role": "data_engineer", "X-Actor": "graph_enrichment_runner"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as response:  # noqa: S310 - local CLI talks to configured app URL
        envelope = json.loads(response.read().decode("utf-8"))
    if not envelope.get("success", False):
        raise RuntimeError(json.dumps(envelope.get("error", envelope), ensure_ascii=False))
    return dict(envelope.get("data", {}))


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"completed_issuer_ids": [], "failed_issuer_ids": []}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"completed_issuer_ids": [], "failed_issuer_ids": [], "state_error": "invalid_json"}


def _write_state(path: Path, report: dict[str, Any], previous: dict[str, Any]) -> None:
    completed = set(str(item) for item in previous.get("completed_issuer_ids", []) if str(item))
    failed = set(str(item) for item in previous.get("failed_issuer_ids", []) if str(item))
    report_status = str(report.get("status", "") or "")
    executed_run = bool(report.get("execute")) and report_status == "executed"
    for row in report.get("items", []) or []:
        issuer_id = str(row.get("issuer_id", "") or "")
        if not issuer_id:
            continue
        if row.get("status") == "failed_with_reason":
            failed.add(issuer_id)
        elif executed_run and row.get("status") == "executed":
            completed.add(issuer_id)
            failed.discard(issuer_id)
    state = {
        "schema_id": "graph-enrichment-runner-state-v1",
        "last_status": report.get("status"),
        "last_completed_at": report.get("completed_at"),
        "last_execute": bool(report.get("execute")),
        "dry_run_items_not_completed": len(
            [
                row
                for row in report.get("items", []) or []
                if not executed_run or row.get("status") != "executed"
            ]
        ),
        "completed_issuer_ids": sorted(completed),
        "failed_issuer_ids": sorted(failed),
        "completed_count": len(completed),
        "failed_count": len(failed),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def run_graph_enrichment_runner(
    base_url: str,
    *,
    output: str | Path = DEFAULT_OUTPUT,
    markets: str = "A,U",
    limit: int = 50,
    batch_size: int = 20,
    execute: bool = False,
    audit_only: bool = False,
    priority_layers: str = "company_event,company_relationship",
    include_events: bool = True,
    include_relationships: bool = True,
    resume_state: str | Path = DEFAULT_STATE,
    resume: bool = False,
    timeout: float = 60.0,
) -> dict[str, Any]:
    output_path = Path(output)
    state_path = Path(resume_state)
    state = _load_state(state_path) if resume else {"completed_issuer_ids": [], "failed_issuer_ids": []}
    payload = {
        "market": markets,
        "limit": limit,
        "batch_size": batch_size,
        "execute": execute,
        "audit_only": audit_only,
        "priority_layers": priority_layers,
        "include_events": include_events,
        "include_relationships": include_relationships,
        "skip_issuer_ids": state.get("completed_issuer_ids", []) if resume else [],
    }
    report = _post_json(base_url, "/api/graph/enrichment-runner", payload, timeout=timeout)
    report["resume_state_path"] = str(state_path)
    report["resume_skipped_count"] = len(payload["skip_issuer_ids"])
    _write_state(state_path, report, state)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Run batch graph enrichment planning/execution for event and relationship candidates.")
    parser.add_argument("base_url", nargs="?", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--market", "--markets", dest="markets", default="A,U")
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--batch-size", type=int, default=20)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--priority-layers", default="company_event,company_relationship")
    parser.add_argument("--no-events", action="store_true")
    parser.add_argument("--no-relationships", action="store_true")
    parser.add_argument("--resume-state", default=str(DEFAULT_STATE))
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()
    report = run_graph_enrichment_runner(
        args.base_url,
        output=args.output,
        markets=args.markets,
        limit=args.limit,
        batch_size=args.batch_size,
        execute=args.execute,
        audit_only=args.audit_only,
        priority_layers=args.priority_layers,
        include_events=not args.no_events,
        include_relationships=not args.no_relationships,
        resume_state=args.resume_state,
        resume=args.resume,
        timeout=args.timeout,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    if report.get("failed_count", 0) or report.get("status") == "no_targets":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
