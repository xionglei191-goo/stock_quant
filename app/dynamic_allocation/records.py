from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any, Mapping


SCHEMA = """
CREATE TABLE IF NOT EXISTS dynamic_allocation_records (
    record_type TEXT NOT NULL,
    record_id TEXT NOT NULL,
    as_of TEXT NOT NULL,
    payload TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (record_type, record_id)
);
CREATE INDEX IF NOT EXISTS idx_dynamic_allocation_records_history
ON dynamic_allocation_records(record_type, as_of DESC, record_id DESC);
"""


class SQLiteAllocationRecordRepository:
    """Append-only JSON records for decisions and backtest summaries."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.executescript(SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def append(self, record_type: str, record_id: str, as_of: str, payload: Mapping[str, Any]) -> bool:
        encoded = json.dumps(dict(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        created_at = str(payload.get("created_at", as_of))
        with closing(self._connect()) as connection, connection:
            existing = connection.execute(
                "SELECT payload FROM dynamic_allocation_records WHERE record_type=? AND record_id=?",
                (record_type, record_id),
            ).fetchone()
            if existing is not None:
                if str(existing["payload"]) != encoded:
                    raise ValueError("immutable dynamic allocation record conflict")
                return False
            connection.execute(
                "INSERT INTO dynamic_allocation_records VALUES (?, ?, ?, ?, ?)",
                (record_type, record_id, as_of, encoded, created_at),
            )
        return True

    def list(self, record_type: str, *, limit: int = 100) -> list[dict[str, Any]]:
        bounded = max(1, min(int(limit), 1000))
        with closing(self._connect()) as connection:
            rows = connection.execute(
                "SELECT payload FROM dynamic_allocation_records WHERE record_type=? ORDER BY as_of DESC, record_id DESC LIMIT ?",
                (record_type, bounded),
            ).fetchall()
        return [json.loads(row["payload"]) for row in rows]

    def get(self, record_type: str, record_id: str) -> dict[str, Any] | None:
        with closing(self._connect()) as connection:
            row = connection.execute(
                "SELECT payload FROM dynamic_allocation_records WHERE record_type=? AND record_id=?",
                (record_type, record_id),
            ).fetchone()
        return json.loads(row["payload"]) if row else None
