from __future__ import annotations

import argparse
from datetime import datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import time
from typing import Any, Mapping


RESEARCH_STATE_SAMPLE_LIMIT = 25
RESEARCH_STATE_COUNT_KEYS = (
    "research_reports",
    "research_documents",
    "research_report_citation_evidence",
    "structured_research_reports",
    "report_viewpoints",
    "report_forecasts",
)
SAFE_POSTGRES_IDENTIFIER = re.compile(r"^[a-z_][a-z0-9_]*$")
SAFE_REPORT_ID = re.compile(r"^[A-Za-z0-9_.:-]+$")

RESEARCH_STATE_SQL = f"""
WITH report_assets AS (
    SELECT
        item_id AS report_id,
        NULLIF(payload->>'document_id', '') AS document_id
    FROM ai_quant.records
    WHERE collection = 'research_reports'
),
research_documents AS (
    SELECT
        document.item_id AS document_id,
        COALESCE(
            NULLIF(
                substring(
                    COALESCE(document.payload->>'source_uri', '')
                    FROM '^research-report://([A-Za-z0-9_.:-]+)$'
                ),
                ''
            ),
            (
                SELECT MIN(asset.report_id)
                FROM report_assets AS asset
                WHERE asset.document_id = document.item_id
            )
        ) AS report_id
    FROM ai_quant.records AS document
    WHERE document.collection = 'documents'
      AND (
        document.payload->>'document_type' = 'research'
        OR document.payload->>'source_uri' LIKE 'research-report://%'
        OR document.payload->>'source_id' LIKE 'local_research_%'
        OR document.payload->'rights_tag'->>'license_class' = 'local_research_reference'
      )
),
research_citation_evidence AS (
    SELECT
        evidence.item_id AS evidence_id,
        document.report_id
    FROM ai_quant.records AS evidence
    LEFT JOIN research_documents AS document
      ON document.document_id = evidence.payload->>'document_id'
    WHERE evidence.collection = 'evidence'
      AND (
        evidence.payload->>'section' = 'research_report_citation'
        OR evidence.payload->>'bbox' LIKE 'research_report://%'
      )
),
structured_reports AS (
    SELECT COALESCE(NULLIF(payload->>'research_report_id', ''), item_id) AS report_id
    FROM ai_quant.records
    WHERE collection = 'structured_research_reports'
),
viewpoints AS (
    SELECT NULLIF(payload->>'research_report_id', '') AS report_id
    FROM ai_quant.records
    WHERE collection = 'report_viewpoints'
),
forecasts AS (
    SELECT NULLIF(payload->>'research_report_id', '') AS report_id
    FROM ai_quant.records
    WHERE collection = 'report_forecasts'
)
SELECT jsonb_build_object(
    'counts', jsonb_build_object(
        'research_reports', (SELECT COUNT(*) FROM report_assets),
        'research_documents', (SELECT COUNT(*) FROM research_documents),
        'research_report_citation_evidence', (SELECT COUNT(*) FROM research_citation_evidence),
        'structured_research_reports', (SELECT COUNT(*) FROM structured_reports),
        'report_viewpoints', (SELECT COUNT(*) FROM viewpoints),
        'report_forecasts', (SELECT COUNT(*) FROM forecasts)
    ),
    'report_id_samples', jsonb_build_object(
        'research_reports', (
            SELECT COALESCE(jsonb_agg(report_id ORDER BY report_id), '[]'::jsonb)
            FROM (
                SELECT DISTINCT report_id
                FROM report_assets
                WHERE report_id ~ '^[A-Za-z0-9_.:-]+$'
                ORDER BY report_id
                LIMIT {RESEARCH_STATE_SAMPLE_LIMIT}
            ) AS sample
        ),
        'research_documents', (
            SELECT COALESCE(jsonb_agg(report_id ORDER BY report_id), '[]'::jsonb)
            FROM (
                SELECT DISTINCT report_id
                FROM research_documents
                WHERE report_id ~ '^[A-Za-z0-9_.:-]+$'
                ORDER BY report_id
                LIMIT {RESEARCH_STATE_SAMPLE_LIMIT}
            ) AS sample
        ),
        'research_report_citation_evidence', (
            SELECT COALESCE(jsonb_agg(report_id ORDER BY report_id), '[]'::jsonb)
            FROM (
                SELECT DISTINCT report_id
                FROM research_citation_evidence
                WHERE report_id ~ '^[A-Za-z0-9_.:-]+$'
                ORDER BY report_id
                LIMIT {RESEARCH_STATE_SAMPLE_LIMIT}
            ) AS sample
        ),
        'structured_research_reports', (
            SELECT COALESCE(jsonb_agg(report_id ORDER BY report_id), '[]'::jsonb)
            FROM (
                SELECT DISTINCT report_id
                FROM structured_reports
                WHERE report_id ~ '^[A-Za-z0-9_.:-]+$'
                ORDER BY report_id
                LIMIT {RESEARCH_STATE_SAMPLE_LIMIT}
            ) AS sample
        ),
        'report_viewpoints', (
            SELECT COALESCE(jsonb_agg(report_id ORDER BY report_id), '[]'::jsonb)
            FROM (
                SELECT DISTINCT report_id
                FROM viewpoints
                WHERE report_id ~ '^[A-Za-z0-9_.:-]+$'
                ORDER BY report_id
                LIMIT {RESEARCH_STATE_SAMPLE_LIMIT}
            ) AS sample
        ),
        'report_forecasts', (
            SELECT COALESCE(jsonb_agg(report_id ORDER BY report_id), '[]'::jsonb)
            FROM (
                SELECT DISTINCT report_id
                FROM forecasts
                WHERE report_id ~ '^[A-Za-z0-9_.:-]+$'
                ORDER BY report_id
                LIMIT {RESEARCH_STATE_SAMPLE_LIMIT}
            ) AS sample
        )
    )
)::text
"""


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


def _validate_postgres_identifier(value: str, *, field_name: str) -> str:
    if not SAFE_POSTGRES_IDENTIFIER.fullmatch(value):
        raise ValueError(f"{field_name} must match {SAFE_POSTGRES_IDENTIFIER.pattern}")
    return value


def _normalize_research_state(payload: Mapping[str, Any]) -> dict[str, object]:
    raw_counts = payload.get("counts")
    raw_samples = payload.get("report_id_samples")
    if not isinstance(raw_counts, Mapping) or not isinstance(raw_samples, Mapping):
        raise RuntimeError("research-state query returned an incomplete manifest")

    counts: dict[str, int] = {}
    samples: dict[str, list[str]] = {}
    for key in RESEARCH_STATE_COUNT_KEYS:
        if key not in raw_counts or key not in raw_samples:
            raise RuntimeError(f"research-state query omitted {key}")
        count = int(raw_counts[key])
        if count < 0:
            raise RuntimeError(f"research-state count cannot be negative: {key}")
        if not isinstance(raw_samples[key], list):
            raise RuntimeError(f"research-state report-ID sample must be a list: {key}")
        counts[key] = count
        samples[key] = sorted(
            {
                str(item)
                for item in raw_samples[key]
                if SAFE_REPORT_ID.fullmatch(str(item))
            }
        )[:RESEARCH_STATE_SAMPLE_LIMIT]

    return {
        "schema_id": "postgres-research-state-manifest-v1",
        "counts": counts,
        "report_id_samples": samples,
        "sample_limit": RESEARCH_STATE_SAMPLE_LIMIT,
        "sample_policy": "sorted_unique_safe_report_ids_only_no_paths_or_content",
        "count_definitions": {
            "research_reports": "collection=research_reports",
            "research_documents": "research-linked subset of collection=documents",
            "research_report_citation_evidence": "research-citation subset of collection=evidence",
            "structured_research_reports": "collection=structured_research_reports",
            "report_viewpoints": "collection=report_viewpoints",
            "report_forecasts": "collection=report_forecasts",
        },
        "coverage_limitation": (
            "This point-in-time count/sample manifest protects the current database state; "
            "it does not prove historical research-state coverage or every unsampled identity."
        ),
    }


def _research_state_manifest(database: str, *, db_user: str, timeout: float) -> dict[str, object]:
    raw = _scalar(database, RESEARCH_STATE_SQL, db_user=db_user, timeout=timeout)
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("research-state query did not return valid JSON") from exc
    if not isinstance(payload, Mapping):
        raise RuntimeError("research-state query did not return a JSON object")
    return _normalize_research_state(payload)


def _database_manifest(database: str, *, db_user: str, timeout: float) -> dict[str, object]:
    table_counts = {
        "records": int(_scalar(database, "SELECT COUNT(*) FROM ai_quant.records", db_user=db_user, timeout=timeout)),
        "audit_log": int(_scalar(database, "SELECT COUNT(*) FROM ai_quant.audit_log", db_user=db_user, timeout=timeout)),
        "market_data_bars": int(
            _scalar(database, "SELECT COUNT(*) FROM ai_quant.market_data_bars", db_user=db_user, timeout=timeout)
        ),
    }
    return {
        "table_counts": table_counts,
        "research_state": _research_state_manifest(database, db_user=db_user, timeout=timeout),
    }


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
    source_db = _validate_postgres_identifier(source_db, field_name="source_db")
    db_user = _validate_postgres_identifier(db_user, field_name="db_user")
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

    before = _database_manifest(source_db, db_user=db_user, timeout=timeout_seconds)
    restore_verified = False
    restored: dict[str, object] = {}
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
        restored = _database_manifest(restore_db, db_user=db_user, timeout=timeout_seconds)
        restore_verified = restored == before
        if not restore_verified:
            mismatches = sorted(key for key in before if before.get(key) != restored.get(key))
            raise RuntimeError(f"restored database manifest differs in: {', '.join(mismatches)}")
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
        "source_counts": before["table_counts"],
        "restored_counts": restored["table_counts"],
        "collection_counts": before["research_state"]["counts"],
        "restored_collection_counts": restored["research_state"]["counts"],
        "source_database_manifest": before,
        "restored_database_manifest": restored,
        "research_state_coverage": "current_point_in_time_only_not_historical_coverage_proof",
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
