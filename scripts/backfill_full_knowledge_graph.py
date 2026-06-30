#!/usr/bin/env python3
"""Build or audit full production-universe knowledge graph coverage."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.server import _load_dotenv
from app.services import SystemService
from app.store import PostgreSQLStore, SQLiteStore
from app.utils import utcnow


DEFAULT_OUTPUT_DIR = ROOT / "artifacts" / "full-knowledge-graph"
DEFAULT_STATE = DEFAULT_OUTPUT_DIR / "state.json"


def _create_service() -> SystemService:
    _load_dotenv()
    postgres_dsn = os.getenv("AI_QUANT_POSTGRES_DSN") or os.getenv("AI_QUANT_DATABASE_URL")
    db_path = os.getenv("AI_QUANT_DB", "")
    if postgres_dsn:
        return SystemService(PostgreSQLStore(postgres_dsn))
    if db_path.startswith(("postgresql://", "postgres://")):
        return SystemService(PostgreSQLStore(db_path))
    if db_path:
        return SystemService(SQLiteStore(db_path))
    return SystemService()


def _load_state(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"completed": [], "failed": [], "skipped": [], "runs": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _update_state(path: Path, result: dict[str, Any], *, run_id: str) -> dict[str, Any]:
    state = _load_state(path)
    completed = set(str(item) for item in state.get("completed", []))
    failed = {str(item.get("issuer_id", item)) if isinstance(item, dict) else str(item) for item in state.get("failed", [])}
    skipped = set(str(item) for item in state.get("skipped", []))
    failed_items = []
    marks_production_complete = result.get("status") == "executed"
    for item in result.get("items", []):
        issuer_id = str(item.get("issuer_id", ""))
        if not issuer_id:
            continue
        if item.get("status") == "failed_with_reason":
            failed.add(issuer_id)
            failed_items.append({"issuer_id": issuer_id, "errors": item.get("errors", [])})
        elif marks_production_complete and item.get("status") in {"ready", "needs_data"}:
            completed.add(issuer_id)
            failed.discard(issuer_id)
        elif item.get("status") == "audit_only":
            continue
        else:
            skipped.add(issuer_id)
    previous_last_run_id = state.get("last_run_id", "")
    state.update(
        {
            "updated_at": utcnow().isoformat(),
            "last_run_id": previous_last_run_id if result.get("status") == "audit_only" else run_id,
            "completed": sorted(completed),
            "failed": sorted(failed),
            "skipped": sorted(skipped),
            "failed_items": failed_items,
        }
    )
    runs = list(state.get("runs", []))
    runs.append({"run_id": run_id, "status": result.get("status"), "processed_count": result.get("processed_count"), "failed_count": result.get("failed_count")})
    state["runs"] = runs[-20:]
    _write_json(path, state)
    return state


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", nargs="?", default="", help="Accepted for parity with API scripts; local env selects the store.")
    parser.add_argument("--market", "--markets", dest="markets", default="A,U")
    parser.add_argument("--batch-size", type=int, default=50)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--resume-state", type=Path, default=DEFAULT_STATE)
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--no-latest", action="store_true", help="Write the requested output but do not replace artifacts/full-knowledge-graph/latest.json.")
    parser.add_argument("--audit-only", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--include-evidence-links", action="store_true", help="Also run per-symbol evidence-link backfill; slower and disabled by default.")
    args = parser.parse_args(argv)
    run_id = f"full-knowledge-graph-{utcnow().strftime('%Y%m%dT%H%M%SZ')}"
    output = args.output or DEFAULT_OUTPUT_DIR / f"run-{run_id}.json"
    execute = bool(args.execute)
    if args.dry_run:
        execute = False
    service = _create_service()
    payload: dict[str, Any] = {
        "market": args.markets,
        "batch_size": args.batch_size,
        "limit": args.limit,
        "execute": execute,
        "audit_only": args.audit_only,
        "include_evidence_links": args.include_evidence_links,
    }
    if args.resume:
        state = _load_state(args.resume_state)
        payload["skip_issuer_ids"] = state.get("completed", [])
    result = service.backfill_full_knowledge_graph(payload, actor="full_knowledge_graph_backfill")
    result["run_id"] = run_id
    result["base_url_argument"] = args.base_url
    result["resume_state_path"] = str(args.resume_state)
    state = _update_state(args.resume_state, result, run_id=run_id)
    result["state_summary"] = {
        "completed_count": len(state.get("completed", [])),
        "failed_count": len(state.get("failed", [])),
        "skipped_count": len(state.get("skipped", [])),
    }
    _write_json(output, result)
    if not args.no_latest:
        latest = DEFAULT_OUTPUT_DIR / "latest.json"
        latest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(output, latest)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("failed_count", 0) == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
