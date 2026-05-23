from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import time
from typing import Any
from urllib.request import Request, urlopen


def _compose_command() -> list[str]:
    if shutil.which("docker"):
        return ["docker", "compose"]
    if shutil.which("podman"):
        return ["podman", "compose"]
    raise RuntimeError("Docker or Podman is required for the local backup/restore drill")


def _run(command: list[str], *, timeout: float = 120.0) -> subprocess.CompletedProcess[str]:
    return subprocess.run(command, text=True, capture_output=True, timeout=timeout, check=False)


def _compose_exec(compose: list[str], service: str, command: list[str], *, timeout: float = 120.0) -> subprocess.CompletedProcess[str]:
    return _run([*compose, "exec", "-T", service, *command], timeout=timeout)


def _must(result: subprocess.CompletedProcess[str], step: str) -> None:
    if result.returncode != 0:
        raise RuntimeError(f"{step} failed: {result.stderr.strip() or result.stdout.strip() or result.returncode}")


def _psql_scalar(compose: list[str], database: str, sql: str, *, db_user: str) -> str:
    result = _compose_exec(compose, "postgres", ["psql", "-U", db_user, "-d", database, "-At", "-c", sql])
    _must(result, f"psql {database}")
    return result.stdout.strip()


def _record_readiness(base_url: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        base_url.rstrip("/") + "/api/readiness/checklist/backup_restore_drill",
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "X-Role": "platform",
            "X-Actor": "platform_backup_drill",
        },
    )
    with urlopen(request, timeout=10) as response:
        raw = response.read().decode("utf-8")
    decoded = json.loads(raw)
    if not decoded.get("success"):
        raise RuntimeError(f"readiness record failed: {decoded}")
    return decoded["data"]


def run_backup_restore_drill(
    *,
    db_user: str = "ai_quant",
    source_db: str = "ai_quant",
    restore_db: str = "",
    artifact_prefix: str = "artifact://staging-local",
    record_readiness_url: str = "",
    keep_restore_db: bool = False,
) -> dict[str, Any]:
    compose = _compose_command()
    suffix = str(int(time.time()))
    restore_db = restore_db or f"ai_quant_restore_drill_{suffix}"
    dump_path = f"/tmp/ai_quant_backup_restore_drill_{suffix}.dump"
    cleanup: list[dict[str, Any]] = []

    started = time.perf_counter()
    try:
        before_records = int(_psql_scalar(compose, source_db, "select count(*) from ai_quant.records;", db_user=db_user))
        before_audit = int(_psql_scalar(compose, source_db, "select count(*) from ai_quant.audit_log;", db_user=db_user))

        _must(
            _compose_exec(compose, "postgres", ["pg_dump", "-U", db_user, "-d", source_db, "-Fc", "-f", dump_path], timeout=180),
            "pg_dump",
        )
        _compose_exec(compose, "postgres", ["dropdb", "-U", db_user, "--if-exists", restore_db], timeout=60)
        _must(_compose_exec(compose, "postgres", ["createdb", "-U", db_user, restore_db], timeout=60), "createdb")
        _must(_compose_exec(compose, "postgres", ["pg_restore", "-U", db_user, "-d", restore_db, dump_path], timeout=180), "pg_restore")

        restored_records = int(_psql_scalar(compose, restore_db, "select count(*) from ai_quant.records;", db_user=db_user))
        restored_audit = int(_psql_scalar(compose, restore_db, "select count(*) from ai_quant.audit_log;", db_user=db_user))
        schema_ok = _psql_scalar(
            compose,
            restore_db,
            "select case when exists (select 1 from information_schema.tables where table_schema='ai_quant' and table_name='records') then 'yes' else 'no' end;",
            db_user=db_user,
        ) == "yes"
        counts_match = before_records == restored_records and before_audit == restored_audit
        status = "passed" if schema_ok and counts_match else "failed"
    finally:
        if not keep_restore_db:
            dropped = _compose_exec(compose, "postgres", ["dropdb", "-U", db_user, "--if-exists", restore_db], timeout=60)
            cleanup.append({"step": "drop_restore_db", "returncode": dropped.returncode, "stderr": dropped.stderr.strip()})
        removed = _compose_exec(compose, "postgres", ["rm", "-f", dump_path], timeout=30)
        cleanup.append({"step": "remove_dump", "returncode": removed.returncode, "stderr": removed.stderr.strip()})

    elapsed_ms = round((time.perf_counter() - started) * 1000, 3)
    result: dict[str, Any] = {
        "status": status,
        "source_db": source_db,
        "restore_db": restore_db,
        "dump_path": dump_path,
        "schema_ok": schema_ok,
        "counts_match": counts_match,
        "source_counts": {"records": before_records, "audit_log": before_audit},
        "restored_counts": {"records": restored_records, "audit_log": restored_audit},
        "elapsed_ms": elapsed_ms,
        "cleanup": cleanup,
        "evidence_uri": f"{artifact_prefix.rstrip('/')}/backup-restore-drill.json",
        "production_boundary": "local_staging_postgres_drill_no_main_database_mutation",
    }
    if record_readiness_url:
        result["readiness_record"] = _record_readiness(
            record_readiness_url,
            {
                "status": status,
                "owner": "platform_backup_drill",
                "evidence_uri": result["evidence_uri"],
                "notes": "Local staging PostgreSQL pg_dump/pg_restore drill into a temporary database; main database was not mutated.",
                "metrics": result,
            },
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a local PostgreSQL backup/restore drill against docker compose staging.")
    parser.add_argument("--db-user", default="ai_quant")
    parser.add_argument("--source-db", default="ai_quant")
    parser.add_argument("--restore-db", default="")
    parser.add_argument("--artifact-prefix", default="artifact://staging-local")
    parser.add_argument("--record-readiness-url", default="")
    parser.add_argument("--keep-restore-db", action="store_true")
    args = parser.parse_args()
    result = run_backup_restore_drill(
        db_user=args.db_user,
        source_db=args.source_db,
        restore_db=args.restore_db,
        artifact_prefix=args.artifact_prefix,
        record_readiness_url=args.record_readiness_url,
        keep_restore_db=args.keep_restore_db,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
