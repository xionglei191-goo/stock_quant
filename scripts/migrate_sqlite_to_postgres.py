from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Callable

from app.store import COLLECTIONS, PostgreSQLStore, SQLiteStore


def migrate_sqlite_to_postgres(
    sqlite_path: str | Path,
    postgres_dsn: str,
    *,
    replace: bool = False,
    connect: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    if not replace:
        raise ValueError("migration requires replace=True because the target PostgreSQL records and audit_log are rewritten")
    source = SQLiteStore(sqlite_path)
    target = PostgreSQLStore(postgres_dsn, connect=connect)
    for collection, _key_field, _model_type in COLLECTIONS:
        target_records = getattr(target, collection)
        target_records.clear()
        target_records.update(getattr(source, collection))
    target.audit_log = list(source.audit_log)
    target.commit()
    counts = {collection: len(getattr(source, collection)) for collection, _key_field, _model_type in COLLECTIONS}
    counts["audit_log"] = len(source.audit_log)
    return {
        "sqlite_path": str(sqlite_path),
        "postgres_dsn": _redact_dsn(postgres_dsn),
        "counts": counts,
    }


def _redact_dsn(dsn: str) -> str:
    if "@" not in dsn or "://" not in dsn:
        return dsn
    scheme, rest = dsn.split("://", 1)
    credentials, host = rest.split("@", 1)
    if ":" not in credentials:
        return f"{scheme}://***@{host}"
    user, _password = credentials.split(":", 1)
    return f"{scheme}://{user}:***@{host}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate AI Quant SQLite state to PostgreSQLStore.")
    parser.add_argument("sqlite_path", help="Path to the SQLite state.db file")
    parser.add_argument("postgres_dsn", help="PostgreSQL DSN, for example postgresql://user:password@host:5432/ai_quant")
    parser.add_argument("--replace", action="store_true", help="Required. Rewrites target PostgreSQL records and audit_log.")
    args = parser.parse_args()
    summary = migrate_sqlite_to_postgres(args.sqlite_path, args.postgres_dsn, replace=args.replace)
    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
