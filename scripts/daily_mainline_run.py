#!/usr/bin/env python3
"""Run the local, paper-only daily research mainline."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys
from typing import Callable, Sequence


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.server import _load_dotenv
from app.services import SystemService
from app.store import PostgreSQLStore, SQLiteStore


def _create_service() -> SystemService:
    _load_dotenv()
    postgres_dsn = os.environ.get("AI_QUANT_POSTGRES_DSN") or os.environ.get(
        "AI_QUANT_DATABASE_URL"
    )
    db_path = os.environ.get("AI_QUANT_DB", "")
    if postgres_dsn:
        return SystemService(PostgreSQLStore(postgres_dsn))
    if db_path.startswith(("postgresql://", "postgres://")):
        return SystemService(PostgreSQLStore(db_path))
    if db_path:
        return SystemService(SQLiteStore(db_path))
    return SystemService()


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run scan, candidate, diligence, and daily queue stages."
    )
    parser.add_argument("--as-of-date", default="")
    parser.add_argument("--timeout-seconds", type=int)
    parser.add_argument("--diligence-limit", type=int)
    parser.add_argument("--artifact-dir", default="")
    parser.add_argument("--actor", default="daily_mainline_cli")
    return parser.parse_args(argv)


def main(
    argv: Sequence[str] | None = None,
    *,
    service_factory: Callable[[], SystemService] = _create_service,
) -> int:
    args = _parse_args(argv)
    request = {
        key: value
        for key, value in {
            "as_of_date": args.as_of_date,
            "timeout_seconds": args.timeout_seconds,
            "diligence_limit": args.diligence_limit,
            "artifact_dir": args.artifact_dir,
            "producer_command": (
                "python3 scripts/daily_mainline_run.py"
                + (f" --as-of-date {args.as_of_date}" if args.as_of_date else "")
            ),
        }.items()
        if value not in {None, ""}
    }
    service = service_factory()
    result = service.run_daily_mainline(request, actor=args.actor)
    service.store.commit_all()
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result.get("status") in {"passed", "empty"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
