from __future__ import annotations

import argparse
from contextlib import closing
from pathlib import Path
from typing import Any, Callable


BASELINE_VERSION = "0001_baseline_jsonb_records"


def _default_connect(dsn: str) -> Any:
    try:
        import psycopg  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:  # pragma: no cover - optional dependency
        raise RuntimeError("Install psycopg[binary] or the project postgres extra to run PostgreSQL migrations.") from exc
    return psycopg.connect(dsn)


def apply_postgres_schema(
    dsn: str,
    *,
    schema_path: str | Path = "docs/postgresql-schema.sql",
    version: str = BASELINE_VERSION,
    dry_run: bool = False,
    connect: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    path = Path(schema_path)
    schema_sql = path.read_text(encoding="utf-8")
    if dry_run:
        return {"version": version, "schema_path": str(path), "dry_run": True, "bytes": len(schema_sql.encode("utf-8"))}
    connect_func = connect or _default_connect
    with closing(connect_func(dsn)) as connection:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute(schema_sql)
                cursor.execute(
                    """
                    INSERT INTO ai_quant.schema_migrations (version, description)
                    VALUES (%s, %s)
                    ON CONFLICT (version)
                    DO UPDATE SET description = EXCLUDED.description, applied_at = now()
                    """,
                    (version, f"Applied {path}"),
                )
    return {"version": version, "schema_path": str(path), "dry_run": False, "applied": True}


def mark_last_migration_rolled_back(
    dsn: str,
    *,
    version: str = BASELINE_VERSION,
    connect: Callable[[str], Any] | None = None,
) -> dict[str, Any]:
    connect_func = connect or _default_connect
    with closing(connect_func(dsn)) as connection:
        with connection:
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM ai_quant.schema_migrations WHERE version = %s", (version,))
    return {"version": version, "rolled_back_record": True, "destructive_schema_changes": False}


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply or mark rollback for the AI Quant PostgreSQL schema baseline.")
    parser.add_argument("dsn", help="PostgreSQL DSN")
    parser.add_argument("--schema-path", default="docs/postgresql-schema.sql")
    parser.add_argument("--version", default=BASELINE_VERSION)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--rollback-last", action="store_true", help="Remove the migration record only; does not drop data or schema objects.")
    args = parser.parse_args()
    if args.rollback_last:
        summary = mark_last_migration_rolled_back(args.dsn, version=args.version)
    else:
        summary = apply_postgres_schema(args.dsn, schema_path=args.schema_path, version=args.version, dry_run=args.dry_run)
    print(summary)


if __name__ == "__main__":
    main()
