from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.market_data_storage import (
    CANONICAL_PAYLOAD_KEYS,
    MARKET_DATA_STORAGE_MIGRATION,
    canonical_json,
    market_data_payload_sql,
    market_data_view_sql,
    rights_policy_hash,
)


SOURCE_TABLE = "market_data_bars"
SHADOW_TABLE = "market_data_bars_v2"
LEGACY_TABLE = "market_data_bars_legacy"
DEFAULT_DSN = "postgresql://ai_quant:ai_quant_dev_password@127.0.0.1:15432/ai_quant"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _connect(dsn: str) -> Any:
    try:
        import psycopg  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:
        raise RuntimeError("psycopg is required; install the postgres project extra") from exc
    return psycopg.connect(dsn)


def _qualified(name: str) -> str:
    if name not in {SOURCE_TABLE, SHADOW_TABLE, LEGACY_TABLE}:
        raise ValueError(f"unsupported table: {name}")
    return f"ai_quant.{name}"


def _table_exists(cursor: Any, name: str) -> bool:
    cursor.execute("SELECT to_regclass(%s) IS NOT NULL", (f"ai_quant.{name}",))
    row = cursor.fetchone()
    return bool(row and row[0])


def _column_exists(cursor: Any, table: str, column: str) -> bool:
    cursor.execute(
        """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.columns
            WHERE table_schema = 'ai_quant' AND table_name = %s AND column_name = %s
        )
        """,
        (table, column),
    )
    row = cursor.fetchone()
    return bool(row and row[0])


def _state(cursor: Any, run_id: str) -> dict[str, Any]:
    cursor.execute(
        """
        SELECT phase, source_rows, copied_rows, last_security_id, last_source_id,
               last_data_type, last_as_of_date, validation
        FROM ai_quant.market_data_migration_runs
        WHERE run_id = %s
        """,
        (run_id,),
    )
    row = cursor.fetchone()
    if not row:
        raise RuntimeError(f"migration run not found: {run_id}")
    validation = row[7]
    if isinstance(validation, str):
        validation = json.loads(validation)
    return {
        "run_id": run_id,
        "phase": str(row[0]),
        "source_rows": int(row[1] or 0),
        "copied_rows": int(row[2] or 0),
        "last_key": (*row[3:6], str(row[6])) if row[3] is not None else None,
        "validation": dict(validation or {}),
    }


def _ensure_control_tables(cursor: Any) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_quant.market_data_migration_runs (
            run_id TEXT PRIMARY KEY,
            phase TEXT NOT NULL,
            source_rows BIGINT NOT NULL DEFAULT 0,
            copied_rows BIGINT NOT NULL DEFAULT 0,
            last_security_id TEXT,
            last_source_id TEXT,
            last_data_type TEXT,
            last_as_of_date DATE,
            validation JSONB NOT NULL DEFAULT '{}'::jsonb,
            started_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
        )
        """
    )


def _create_shadow_schema(cursor: Any) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS ai_quant.market_data_rights_policies (
            policy_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
            policy_hash CHAR(64) NOT NULL UNIQUE,
            rights_tag JSONB NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            CHECK (length(policy_hash) = 64)
        )
        """
    )
    cursor.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {_qualified(SHADOW_TABLE)} (
            security_id TEXT NOT NULL,
            source_id TEXT NOT NULL,
            data_type TEXT NOT NULL DEFAULT 'eod',
            as_of_date DATE NOT NULL,
            market TEXT NOT NULL,
            currency TEXT NOT NULL DEFAULT '',
            open NUMERIC NOT NULL DEFAULT 0,
            high NUMERIC NOT NULL DEFAULT 0,
            low NUMERIC NOT NULL DEFAULT 0,
            close NUMERIC NOT NULL,
            adjusted_close NUMERIC NOT NULL DEFAULT 0,
            volume NUMERIC NOT NULL DEFAULT 0,
            amount NUMERIC NOT NULL DEFAULT 0,
            data_id TEXT NOT NULL,
            rights_policy_id BIGINT NOT NULL REFERENCES ai_quant.market_data_rights_policies(policy_id) ON DELETE RESTRICT,
            payload_key_mask BIGINT NOT NULL DEFAULT 0,
            extra_payload JSONB NOT NULL DEFAULT '{{}}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
            PRIMARY KEY (security_id, source_id, data_type, as_of_date)
        )
        """
    )


def prepare(dsn: str, run_id: str) -> dict[str, Any]:
    started = time.perf_counter()
    with closing(_connect(dsn)) as connection:
        with connection:
            with connection.cursor() as cursor:
                _ensure_control_tables(cursor)
                if not _table_exists(cursor, SOURCE_TABLE):
                    raise RuntimeError("source market_data_bars table does not exist")
                if not _column_exists(cursor, SOURCE_TABLE, "payload") or not _column_exists(cursor, SOURCE_TABLE, "rights_tag"):
                    raise RuntimeError("source table is not the legacy payload/rights_tag schema")
                if _table_exists(cursor, LEGACY_TABLE):
                    raise RuntimeError("legacy table already exists; finish or roll back the previous cutover")
                _create_shadow_schema(cursor)
                cursor.execute("SELECT phase FROM ai_quant.market_data_migration_runs WHERE run_id = %s", (run_id,))
                existing = cursor.fetchone()
                if existing and str(existing[0]) in {"rolled_back", "validation_failed"}:
                    cursor.execute(f"TRUNCATE TABLE {_qualified(SHADOW_TABLE)}")
                cursor.execute(f"SELECT COUNT(*) FROM {_qualified(SOURCE_TABLE)}")
                source_rows = int(cursor.fetchone()[0] or 0)
                cursor.execute(f"SELECT DISTINCT rights_tag FROM {_qualified(SOURCE_TABLE)}")
                rights_rows = cursor.fetchall()
                for (rights_tag,) in rights_rows:
                    plain = dict(rights_tag or {})
                    cursor.execute(
                        """
                        INSERT INTO ai_quant.market_data_rights_policies (policy_hash, rights_tag)
                        VALUES (%s, %s::jsonb)
                        ON CONFLICT (policy_hash) DO NOTHING
                        """,
                        (rights_policy_hash(plain), canonical_json(plain)),
                    )
                cursor.execute(
                    """
                    INSERT INTO ai_quant.market_data_migration_runs (run_id, phase, source_rows)
                    VALUES (%s, 'prepared', %s)
                    ON CONFLICT (run_id) DO UPDATE SET
                        phase = CASE
                            WHEN ai_quant.market_data_migration_runs.phase IN ('rolled_back', 'validation_failed') THEN 'prepared'
                            ELSE ai_quant.market_data_migration_runs.phase
                        END,
                        source_rows = EXCLUDED.source_rows,
                        copied_rows = CASE
                            WHEN ai_quant.market_data_migration_runs.phase IN ('rolled_back', 'validation_failed') THEN 0
                            ELSE ai_quant.market_data_migration_runs.copied_rows
                        END,
                        last_security_id = CASE WHEN ai_quant.market_data_migration_runs.phase IN ('rolled_back', 'validation_failed') THEN NULL ELSE ai_quant.market_data_migration_runs.last_security_id END,
                        last_source_id = CASE WHEN ai_quant.market_data_migration_runs.phase IN ('rolled_back', 'validation_failed') THEN NULL ELSE ai_quant.market_data_migration_runs.last_source_id END,
                        last_data_type = CASE WHEN ai_quant.market_data_migration_runs.phase IN ('rolled_back', 'validation_failed') THEN NULL ELSE ai_quant.market_data_migration_runs.last_data_type END,
                        last_as_of_date = CASE WHEN ai_quant.market_data_migration_runs.phase IN ('rolled_back', 'validation_failed') THEN NULL ELSE ai_quant.market_data_migration_runs.last_as_of_date END,
                        validation = CASE WHEN ai_quant.market_data_migration_runs.phase IN ('rolled_back', 'validation_failed') THEN '{}'::jsonb ELSE ai_quant.market_data_migration_runs.validation END,
                        updated_at = now()
                    """,
                    (run_id, source_rows),
                )
    return {
        "status": "prepared",
        "run_id": run_id,
        "source_rows": source_rows,
        "rights_policy_count": len(rights_rows),
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


def _mask_expression(alias: str = "b") -> str:
    parts = [f"(CASE WHEN {alias}.payload ? '{key}' THEN {1 << bit} ELSE 0 END)" for bit, key in enumerate(CANONICAL_PAYLOAD_KEYS)]
    return " + ".join(parts)


def _payload_override_expression(source_alias: str, value_alias: str, rights_value_sql: str) -> str:
    column_by_key = {
        "data_id": "data_id",
        "security_id": "security_id",
        "source_id": "source_id",
        "market": "market",
        "as_of_date": "as_of_date",
        "data_type": "data_type",
        "currency": "currency",
        "open": "open",
        "high": "high",
        "low": "low",
        "close": "close",
        "adjusted_close": "adjusted_close",
        "volume": "volume",
        "amount": "amount",
    }
    parts = []
    for key in CANONICAL_PAYLOAD_KEYS:
        value_sql = rights_value_sql if key == "rights_tag" else f"{value_alias}.{column_by_key[key]}"
        parts.append(
            f"CASE WHEN {source_alias}.payload ? '{key}' "
            f"AND {source_alias}.payload->'{key}' IS DISTINCT FROM to_jsonb({value_sql}) "
            f"THEN jsonb_build_object('{key}', {source_alias}.payload->'{key}') ELSE '{{}}'::jsonb END"
        )
    return " || ".join(parts)


def _create_shadow_indexes(cursor: Any) -> None:
    cursor.execute(
        f"CREATE UNIQUE INDEX IF NOT EXISTS idx_ai_quant_market_data_bars_data_id_v2 ON {_qualified(SHADOW_TABLE)} (data_id)"
    )
    cursor.execute(
        f"CREATE INDEX IF NOT EXISTS idx_ai_quant_market_data_bars_market_date_v2 ON {_qualified(SHADOW_TABLE)} (market, as_of_date DESC, security_id)"
    )
    cursor.execute(
        f"CREATE INDEX IF NOT EXISTS idx_ai_quant_market_data_bars_source_date_v2 ON {_qualified(SHADOW_TABLE)} (source_id, data_type, as_of_date DESC)"
    )
    cursor.execute(
        f"CREATE INDEX IF NOT EXISTS idx_ai_quant_market_data_bars_as_of_date_v2 ON {_qualified(SHADOW_TABLE)} (as_of_date DESC, data_id DESC)"
    )
    cursor.execute(f"ANALYZE {_qualified(SHADOW_TABLE)}")


def copy_rows(dsn: str, run_id: str, *, batch_size: int = 100_000) -> dict[str, Any]:
    if batch_size < 1:
        raise ValueError("batch_size must be positive")
    started = time.perf_counter()
    copied_this_run = 0
    canonical_array = ", ".join(f"'{key}'" for key in CANONICAL_PAYLOAD_KEYS)
    with closing(_connect(dsn)) as connection:
        while True:
            with connection.transaction():
                with connection.cursor() as cursor:
                    _ensure_control_tables(cursor)
                    state = _state(cursor, run_id)
                    if state["phase"] in {"validated", "cutover", "cleaned"}:
                        break
                    last_key = state["last_key"]
                    where_sql = ""
                    params: list[Any] = []
                    if last_key:
                        where_sql = "WHERE (security_id, source_id, data_type, as_of_date) > (%s, %s, %s, %s::date)"
                        params.extend(last_key)
                    cursor.execute(
                        f"""
                        SELECT security_id, source_id, data_type, as_of_date
                        FROM {_qualified(SOURCE_TABLE)}
                        {where_sql}
                        ORDER BY security_id, source_id, data_type, as_of_date
                        LIMIT %s
                        """,
                        (*params, batch_size),
                    )
                    keys = cursor.fetchall()
                    if not keys:
                        _create_shadow_indexes(cursor)
                        cursor.execute(
                            "UPDATE ai_quant.market_data_migration_runs SET phase = 'copied', updated_at = now() WHERE run_id = %s",
                            (run_id,),
                        )
                        break
                    end_key = keys[-1]
                    range_sql = "(b.security_id, b.source_id, b.data_type, b.as_of_date) <= (%s, %s, %s, %s::date)"
                    range_params: list[Any] = list(end_key)
                    if last_key:
                        range_sql = "(b.security_id, b.source_id, b.data_type, b.as_of_date) > (%s, %s, %s, %s::date) AND " + range_sql
                        range_params = [*last_key, *end_key]
                    cursor.execute(
                        f"""
                        INSERT INTO {_qualified(SHADOW_TABLE)} (
                            security_id, source_id, data_type, as_of_date, market, currency,
                            open, high, low, close, adjusted_close, volume, amount, data_id,
                            rights_policy_id, payload_key_mask, extra_payload, created_at, updated_at
                        )
                        SELECT
                            b.security_id, b.source_id, b.data_type, b.as_of_date, b.market, b.currency,
                            b.open, b.high, b.low, b.close, b.adjusted_close, b.volume, b.amount, b.data_id,
                            p.policy_id, {_mask_expression('b')},
                            (b.payload - ARRAY[{canonical_array}]::text[])
                            || ({_payload_override_expression('b', 'b', 'b.rights_tag')}),
                            b.created_at, b.updated_at
                        FROM {_qualified(SOURCE_TABLE)} AS b
                        JOIN ai_quant.market_data_rights_policies AS p ON p.rights_tag = b.rights_tag
                        WHERE {range_sql}
                        ON CONFLICT (security_id, source_id, data_type, as_of_date) DO UPDATE SET
                            market = EXCLUDED.market,
                            currency = EXCLUDED.currency,
                            open = EXCLUDED.open,
                            high = EXCLUDED.high,
                            low = EXCLUDED.low,
                            close = EXCLUDED.close,
                            adjusted_close = EXCLUDED.adjusted_close,
                            volume = EXCLUDED.volume,
                            amount = EXCLUDED.amount,
                            data_id = EXCLUDED.data_id,
                            rights_policy_id = EXCLUDED.rights_policy_id,
                            payload_key_mask = EXCLUDED.payload_key_mask,
                            extra_payload = EXCLUDED.extra_payload,
                            created_at = EXCLUDED.created_at,
                            updated_at = EXCLUDED.updated_at
                        """,
                        tuple(range_params),
                    )
                    batch_count = len(keys)
                    copied_this_run += batch_count
                    total_copied = state["copied_rows"] + batch_count
                    cursor.execute(
                        """
                        UPDATE ai_quant.market_data_migration_runs
                        SET phase = 'copying', copied_rows = copied_rows + %s,
                            last_security_id = %s, last_source_id = %s, last_data_type = %s,
                            last_as_of_date = %s, updated_at = now()
                        WHERE run_id = %s
                        """,
                        (batch_count, *end_key, run_id),
                    )
                    if total_copied % 1_000_000 < batch_count:
                        print(f"copied run={run_id} rows={total_copied}", flush=True)
    return {
        "status": "copied",
        "run_id": run_id,
        "copied_this_run": copied_this_run,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


def repair_payload_overrides(dsn: str, run_id: str) -> dict[str, Any]:
    started = time.perf_counter()
    payload_sql = market_data_payload_sql("n", "p")
    override_sql = _payload_override_expression("o", "n", "p.rights_tag")
    with closing(_connect(dsn)) as connection:
        with connection:
            with connection.cursor() as cursor:
                state = _state(cursor, run_id)
                if state["phase"] not in {"copied", "validation_failed"}:
                    raise RuntimeError(f"repair requires copied or validation_failed phase; current={state['phase']}")
                cursor.execute(
                    f"""
                    UPDATE {_qualified(SHADOW_TABLE)} AS n
                    SET extra_payload = n.extra_payload || ({override_sql})
                    FROM {_qualified(SOURCE_TABLE)} AS o,
                         ai_quant.market_data_rights_policies AS p
                    WHERE (o.security_id, o.source_id, o.data_type, o.as_of_date)
                          = (n.security_id, n.source_id, n.data_type, n.as_of_date)
                      AND p.policy_id = n.rights_policy_id
                      AND o.payload IS DISTINCT FROM ({payload_sql})
                    """
                )
                repaired_rows = int(cursor.rowcount or 0)
                cursor.execute(
                    """
                    UPDATE ai_quant.market_data_migration_runs
                    SET phase = 'copied', validation = '{}'::jsonb, updated_at = now()
                    WHERE run_id = %s
                    """,
                    (run_id,),
                )
    return {
        "status": "repaired",
        "run_id": run_id,
        "repaired_rows": repaired_rows,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


def _relation_size(cursor: Any, table: str) -> int:
    cursor.execute("SELECT pg_total_relation_size(%s::regclass)", (f"ai_quant.{table}",))
    return int(cursor.fetchone()[0] or 0)


def validate(dsn: str, run_id: str, *, target_size_gb: float = 22.0) -> dict[str, Any]:
    started = time.perf_counter()
    payload_sql = market_data_payload_sql("n", "p")
    checks: dict[str, Any] = {}
    with closing(_connect(dsn)) as connection:
        with connection:
            with connection.cursor() as cursor:
                state = _state(cursor, run_id)
                if state["phase"] not in {"copied", "validated"}:
                    raise RuntimeError(f"copy must complete before validation; current phase={state['phase']}")
                cursor.execute(f"SELECT COUNT(*) FROM {_qualified(SOURCE_TABLE)}")
                checks["source_rows"] = int(cursor.fetchone()[0] or 0)
                cursor.execute(f"SELECT COUNT(*) FROM {_qualified(SHADOW_TABLE)}")
                checks["shadow_rows"] = int(cursor.fetchone()[0] or 0)
                cursor.execute(
                    f"""
                    SELECT COUNT(*) FROM {_qualified(SOURCE_TABLE)} AS o
                    FULL JOIN {_qualified(SHADOW_TABLE)} AS n
                      USING (security_id, source_id, data_type, as_of_date)
                    WHERE o.security_id IS NULL OR n.security_id IS NULL
                    """
                )
                checks["missing_keys"] = int(cursor.fetchone()[0] or 0)
                cursor.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM {_qualified(SOURCE_TABLE)} AS o
                    JOIN {_qualified(SHADOW_TABLE)} AS n USING (security_id, source_id, data_type, as_of_date)
                    JOIN ai_quant.market_data_rights_policies AS p ON p.policy_id = n.rights_policy_id
                    WHERE (o.market, o.currency, o.open, o.high, o.low, o.close, o.adjusted_close,
                           o.volume, o.amount, o.data_id, o.created_at, o.updated_at, o.rights_tag)
                          IS DISTINCT FROM
                          (n.market, n.currency, n.open, n.high, n.low, n.close, n.adjusted_close,
                           n.volume, n.amount, n.data_id, n.created_at, n.updated_at, p.rights_tag)
                    """
                )
                checks["scalar_or_rights_mismatches"] = int(cursor.fetchone()[0] or 0)
                cursor.execute(
                    f"""
                    SELECT COUNT(*)
                    FROM {_qualified(SOURCE_TABLE)} AS o
                    JOIN {_qualified(SHADOW_TABLE)} AS n USING (security_id, source_id, data_type, as_of_date)
                    JOIN ai_quant.market_data_rights_policies AS p ON p.policy_id = n.rights_policy_id
                    WHERE o.payload IS DISTINCT FROM ({payload_sql})
                    """
                )
                checks["payload_mismatches"] = int(cursor.fetchone()[0] or 0)
                checks["source_size_bytes"] = _relation_size(cursor, SOURCE_TABLE)
                checks["shadow_size_bytes"] = _relation_size(cursor, SHADOW_TABLE)
                cursor.execute("SELECT pg_total_relation_size('ai_quant.market_data_rights_policies'::regclass)")
                checks["policy_size_bytes"] = int(cursor.fetchone()[0] or 0)
                checks["target_size_bytes"] = int(target_size_gb * 1024**3)
                checks["passed"] = (
                    checks["source_rows"] == checks["shadow_rows"] == state["source_rows"]
                    and checks["missing_keys"] == 0
                    and checks["scalar_or_rights_mismatches"] == 0
                    and checks["payload_mismatches"] == 0
                    and checks["shadow_size_bytes"] + checks["policy_size_bytes"] <= checks["target_size_bytes"]
                )
                cursor.execute(
                    """
                    UPDATE ai_quant.market_data_migration_runs
                    SET phase = %s, validation = %s::jsonb, updated_at = now()
                    WHERE run_id = %s
                    """,
                    ("validated" if checks["passed"] else "validation_failed", json.dumps(checks, sort_keys=True), run_id),
                )
    return {
        "status": "passed" if checks["passed"] else "failed",
        "run_id": run_id,
        "checks": checks,
        "elapsed_seconds": round(time.perf_counter() - started, 3),
    }


def cutover(dsn: str, run_id: str) -> dict[str, Any]:
    started = time.perf_counter()
    with closing(_connect(dsn)) as connection:
        with connection:
            with connection.cursor() as cursor:
                state = _state(cursor, run_id)
                if state["phase"] != "validated" or not state["validation"].get("passed"):
                    raise RuntimeError("a passed validation is required before cutover")
                cursor.execute("LOCK TABLE ai_quant.market_data_bars IN ACCESS EXCLUSIVE MODE")
                cursor.execute("DROP VIEW IF EXISTS ai_quant.market_data")
                cursor.execute("DROP TRIGGER IF EXISTS trg_ai_quant_market_data_bars_touch_updated_at ON ai_quant.market_data_bars")
                cursor.execute(f"ALTER TABLE {_qualified(SOURCE_TABLE)} RENAME TO {LEGACY_TABLE}")
                cursor.execute(f"ALTER TABLE {_qualified(SHADOW_TABLE)} RENAME TO {SOURCE_TABLE}")
                cursor.execute(
                    """
                    CREATE TRIGGER trg_ai_quant_market_data_bars_touch_updated_at
                    BEFORE UPDATE ON ai_quant.market_data_bars
                    FOR EACH ROW EXECUTE FUNCTION ai_quant.touch_updated_at()
                    """
                )
                cursor.execute(market_data_view_sql())
                cursor.execute(
                    """
                    INSERT INTO ai_quant.schema_migrations (version, description)
                    VALUES (%s, %s)
                    ON CONFLICT (version) DO UPDATE SET description = EXCLUDED.description, applied_at = now()
                    """,
                    (MARKET_DATA_STORAGE_MIGRATION, "Optimized typed market-data storage with deduplicated rights policies"),
                )
                cursor.execute(
                    "UPDATE ai_quant.market_data_migration_runs SET phase = 'cutover', updated_at = now() WHERE run_id = %s",
                    (run_id,),
                )
    return {"status": "cutover", "run_id": run_id, "elapsed_seconds": round(time.perf_counter() - started, 3)}


def rollback(dsn: str, run_id: str) -> dict[str, Any]:
    with closing(_connect(dsn)) as connection:
        with connection:
            with connection.cursor() as cursor:
                state = _state(cursor, run_id)
                if state["phase"] != "cutover" or not _table_exists(cursor, LEGACY_TABLE):
                    raise RuntimeError("rollback is available only after cutover and before cleanup")
                cursor.execute("DROP VIEW IF EXISTS ai_quant.market_data")
                cursor.execute("DROP TRIGGER IF EXISTS trg_ai_quant_market_data_bars_touch_updated_at ON ai_quant.market_data_bars")
                cursor.execute(f"ALTER TABLE {_qualified(SOURCE_TABLE)} RENAME TO {SHADOW_TABLE}")
                cursor.execute(f"ALTER TABLE {_qualified(LEGACY_TABLE)} RENAME TO {SOURCE_TABLE}")
                cursor.execute(
                    """
                    CREATE TRIGGER trg_ai_quant_market_data_bars_touch_updated_at
                    BEFORE UPDATE ON ai_quant.market_data_bars
                    FOR EACH ROW EXECUTE FUNCTION ai_quant.touch_updated_at()
                    """
                )
                cursor.execute(
                    """
                    CREATE OR REPLACE VIEW ai_quant.market_data AS
                    SELECT data_id, security_id, source_id, market, as_of_date, data_type,
                           open, high, low, close, adjusted_close, volume, amount,
                           rights_tag, payload, updated_at
                    FROM ai_quant.market_data_bars
                    """
                )
                cursor.execute("DELETE FROM ai_quant.schema_migrations WHERE version = %s", (MARKET_DATA_STORAGE_MIGRATION,))
                cursor.execute(
                    "UPDATE ai_quant.market_data_migration_runs SET phase = 'rolled_back', updated_at = now() WHERE run_id = %s",
                    (run_id,),
                )
    return {"status": "rolled_back", "run_id": run_id}


def cleanup(dsn: str, run_id: str, *, confirmation: str, backup_manifest: str | Path) -> dict[str, Any]:
    manifest_path = Path(backup_manifest)
    if confirmation != run_id:
        raise RuntimeError("cleanup confirmation must exactly match the migration run ID")
    if not manifest_path.is_file():
        raise RuntimeError("a readable backup manifest is required before legacy-table deletion")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not manifest.get("restore_verified") or not manifest.get("dump_sha256"):
        raise RuntimeError("backup manifest must contain restore_verified=true and dump_sha256")
    dump_path = Path(str(manifest.get("dump_path") or ""))
    if not dump_path.is_file():
        raise RuntimeError("the restore-verified dump referenced by the backup manifest is missing")
    if _sha256(dump_path) != manifest["dump_sha256"]:
        raise RuntimeError("the backup dump SHA-256 no longer matches the restore-verified manifest")
    with closing(_connect(dsn)) as connection:
        with connection:
            with connection.cursor() as cursor:
                state = _state(cursor, run_id)
                if state["phase"] != "cutover":
                    raise RuntimeError("cleanup is allowed only after cutover acceptance")
                cursor.execute(f"DROP TABLE {_qualified(LEGACY_TABLE)}")
                rename_pairs = (
                    ("market_data_bars_v2_pkey", "market_data_bars_pkey"),
                    ("idx_ai_quant_market_data_bars_data_id_v2", "idx_ai_quant_market_data_bars_data_id"),
                    ("idx_ai_quant_market_data_bars_market_date_v2", "idx_ai_quant_market_data_bars_market_date"),
                    ("idx_ai_quant_market_data_bars_source_date_v2", "idx_ai_quant_market_data_bars_source_date"),
                    ("idx_ai_quant_market_data_bars_as_of_date_v2", "idx_ai_quant_market_data_bars_as_of_date"),
                )
                for old_name, new_name in rename_pairs:
                    cursor.execute(f"ALTER INDEX ai_quant.{old_name} RENAME TO {new_name}")
                cursor.execute(
                    "UPDATE ai_quant.market_data_migration_runs SET phase = 'cleaned', updated_at = now() WHERE run_id = %s",
                    (run_id,),
                )
    return {"status": "cleaned", "run_id": run_id, "backup_manifest": str(manifest_path)}


def status(dsn: str, run_id: str) -> dict[str, Any]:
    with closing(_connect(dsn)) as connection:
        with connection.cursor() as cursor:
            _ensure_control_tables(cursor)
            result = _state(cursor, run_id)
            result["tables"] = {
                name: _table_exists(cursor, name) for name in (SOURCE_TABLE, SHADOW_TABLE, LEGACY_TABLE)
            }
            return result


def _write_artifact(path: str, result: dict[str, Any]) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        **result,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "environment": "local-postgresql",
        "owner_group": "Data and Evidence",
        "classification": "local-only",
        "contains_sensitive_data": False,
        "acceptable_for_non_local_release": False,
    }
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Migrate typed market-data storage to the compact v2 schema.")
    parser.add_argument("phase", choices=("prepare", "copy", "repair", "validate", "cutover", "rollback", "cleanup", "status"))
    parser.add_argument("--dsn", default=os.environ.get("AI_QUANT_POSTGRES_DSN", DEFAULT_DSN))
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--batch-size", type=int, default=100_000)
    parser.add_argument("--target-size-gb", type=float, default=22.0)
    parser.add_argument("--confirm-drop-legacy", default="")
    parser.add_argument("--backup-manifest", default="")
    parser.add_argument("--artifact", default="")
    args = parser.parse_args()
    free_bytes = shutil.disk_usage(ROOT).free
    if args.phase in {"prepare", "copy"} and free_bytes < 100 * 1024**3:
        raise RuntimeError(f"at least 100 GiB free space is required; available={free_bytes / 1024**3:.1f} GiB")
    if args.phase == "prepare":
        result = prepare(args.dsn, args.run_id)
    elif args.phase == "copy":
        result = copy_rows(args.dsn, args.run_id, batch_size=args.batch_size)
    elif args.phase == "repair":
        result = repair_payload_overrides(args.dsn, args.run_id)
    elif args.phase == "validate":
        result = validate(args.dsn, args.run_id, target_size_gb=args.target_size_gb)
    elif args.phase == "cutover":
        result = cutover(args.dsn, args.run_id)
    elif args.phase == "rollback":
        result = rollback(args.dsn, args.run_id)
    elif args.phase == "cleanup":
        result = cleanup(
            args.dsn,
            args.run_id,
            confirmation=args.confirm_drop_legacy,
            backup_manifest=args.backup_manifest,
        )
    else:
        result = status(args.dsn, args.run_id)
    _write_artifact(args.artifact, result)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
