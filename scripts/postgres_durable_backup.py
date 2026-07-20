from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time


def _run(command: list[str], *, timeout: float, capture: bool = True) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, text=True, capture_output=capture, timeout=timeout, check=False)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "command failed").strip()
        raise RuntimeError(f"{command[0]} command failed: {detail[:500]}")
    return result


def _compose(*args: str, timeout: float = 3600.0) -> subprocess.CompletedProcess[str]:
    return _run(["docker", "compose", *args], timeout=timeout)


def _scalar(database: str, sql: str, *, db_user: str, timeout: float) -> str:
    result = _compose(
        "exec",
        "-T",
        "postgres",
        "psql",
        "-U",
        db_user,
        "-d",
        database,
        "-Atqc",
        sql,
        timeout=timeout,
    )
    return result.stdout.strip()


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def create_durable_backup(
    *,
    output_dir: str | Path,
    source_db: str = "ai_quant",
    db_user: str = "ai_quant",
    retention_days: int = 7,
    timeout_seconds: float = 3600.0,
) -> dict[str, object]:
    started = time.perf_counter()
    timestamp = datetime.now(timezone.utc)
    suffix = timestamp.strftime("%Y%m%dT%H%M%SZ")
    restore_db = f"ai_quant_t602_restore_{suffix.lower()}"
    if not re.fullmatch(r"[a-z0-9_]+", restore_db):
        raise RuntimeError("generated restore database name is unsafe")
    destination = Path(output_dir).resolve()
    destination.mkdir(parents=True, exist_ok=True)
    dump_path = destination / f"{source_db}-{suffix}.dump"
    manifest_path = destination / f"{source_db}-{suffix}.manifest.json"
    container_dump = f"/tmp/{source_db}-{suffix}.dump"
    container_id = _compose("ps", "-q", "postgres", timeout=30).stdout.strip()
    if not container_id:
        raise RuntimeError("docker compose postgres service is not running")

    before = {
        "records": int(_scalar(source_db, "SELECT COUNT(*) FROM ai_quant.records", db_user=db_user, timeout=timeout_seconds)),
        "audit_log": int(_scalar(source_db, "SELECT COUNT(*) FROM ai_quant.audit_log", db_user=db_user, timeout=timeout_seconds)),
        "market_data_bars": int(_scalar(source_db, "SELECT COUNT(*) FROM ai_quant.market_data_bars", db_user=db_user, timeout=timeout_seconds)),
    }
    restore_verified = False
    restored: dict[str, int] = {}
    try:
        _compose(
            "exec",
            "-T",
            "postgres",
            "pg_dump",
            "-U",
            db_user,
            "-d",
            source_db,
            "-Fc",
            "-f",
            container_dump,
            timeout=timeout_seconds,
        )
        _run(["docker", "cp", f"{container_id}:{container_dump}", str(dump_path)], timeout=timeout_seconds)
        _compose("exec", "-T", "postgres", "dropdb", "-U", db_user, "--if-exists", restore_db, timeout=60)
        _compose("exec", "-T", "postgres", "createdb", "-U", db_user, restore_db, timeout=60)
        _compose(
            "exec",
            "-T",
            "postgres",
            "pg_restore",
            "-U",
            db_user,
            "-d",
            restore_db,
            container_dump,
            timeout=timeout_seconds,
        )
        restored = {
            "records": int(_scalar(restore_db, "SELECT COUNT(*) FROM ai_quant.records", db_user=db_user, timeout=timeout_seconds)),
            "audit_log": int(_scalar(restore_db, "SELECT COUNT(*) FROM ai_quant.audit_log", db_user=db_user, timeout=timeout_seconds)),
            "market_data_bars": int(_scalar(restore_db, "SELECT COUNT(*) FROM ai_quant.market_data_bars", db_user=db_user, timeout=timeout_seconds)),
        }
        restore_verified = restored == before
        if not restore_verified:
            raise RuntimeError(f"restored counts differ: source={before} restored={restored}")
    finally:
        _compose("exec", "-T", "postgres", "dropdb", "-U", db_user, "--if-exists", restore_db, timeout=60)
        _compose("exec", "-T", "postgres", "rm", "-f", container_dump, timeout=60)

    manifest: dict[str, object] = {
        "status": "passed",
        "generated_at": timestamp.isoformat(),
        "retained_until": (timestamp + timedelta(days=retention_days)).isoformat(),
        "source_db": source_db,
        "dump_path": str(dump_path),
        "dump_size_bytes": dump_path.stat().st_size,
        "dump_sha256": _sha256(dump_path),
        "restore_verified": restore_verified,
        "source_counts": before,
        "restored_counts": restored,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
        "environment": "local-docker-compose-postgresql",
        "owner_group": "Platform and Quality",
        "classification": "local-only",
        "contains_sensitive_data": True,
        "acceptable_for_non_local_release": False,
    }
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    manifest["manifest_path"] = str(manifest_path)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Create and restore-verify a durable local PostgreSQL custom-format backup.")
    parser.add_argument("--output-dir", default="data/local/backups/postgres")
    parser.add_argument("--source-db", default="ai_quant")
    parser.add_argument("--db-user", default="ai_quant")
    parser.add_argument("--retention-days", type=int, default=7)
    parser.add_argument("--timeout-seconds", type=float, default=3600.0)
    args = parser.parse_args()
    result = create_durable_backup(
        output_dir=args.output_dir,
        source_db=args.source_db,
        db_user=args.db_user,
        retention_days=args.retention_days,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
