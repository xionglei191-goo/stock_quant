from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from dataclasses import replace
from datetime import date, datetime
from pathlib import Path
from typing import Any, Callable, Sequence

from ..contracts import PointInTimeObservation, UpsertSummary, ensure_aware


SQLITE_SCHEMA = """
CREATE TABLE IF NOT EXISTS economic_observations (
    observation_id TEXT NOT NULL UNIQUE,
    series_id TEXT NOT NULL,
    observation_date TEXT NOT NULL,
    value REAL NOT NULL,
    release_date TEXT NOT NULL,
    available_at TEXT NOT NULL,
    vintage_date TEXT NOT NULL,
    revision_seq INTEGER NOT NULL CHECK (revision_seq >= 0),
    source_id TEXT NOT NULL,
    source_uri TEXT NOT NULL DEFAULT '',
    ingested_at TEXT NOT NULL,
    rights_tag TEXT NOT NULL DEFAULT '{}',
    quality_flags TEXT NOT NULL DEFAULT '[]',
    payload_hash TEXT NOT NULL,
    PRIMARY KEY (series_id, observation_date, vintage_date, revision_seq)
);
CREATE INDEX IF NOT EXISTS idx_dynamic_observations_pit
    ON economic_observations (series_id, available_at, observation_date, vintage_date, revision_seq);
CREATE INDEX IF NOT EXISTS idx_dynamic_observations_vintage
    ON economic_observations (series_id, observation_date, vintage_date, revision_seq);
"""


class ImmutableObservationConflict(ValueError):
    pass


class SQLiteObservationRepository:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with closing(self._connect()) as connection:
            connection.executescript(SQLITE_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    def upsert(self, rows: Sequence[PointInTimeObservation]) -> UpsertSummary:
        inserted = duplicates = conflicts = 0
        with closing(self._connect()) as connection, connection:
            for row in rows:
                existing = connection.execute(
                    """SELECT * FROM economic_observations
                       WHERE series_id = ? AND observation_date = ? AND vintage_date = ? AND revision_seq = ?""",
                    (row.series_id, row.observation_date.isoformat(), row.vintage_date.isoformat(), row.revision_seq),
                ).fetchone()
                if existing is not None:
                    if _material_signature(_from_sql_row(existing)) != _material_signature(row):
                        conflicts += 1
                    else:
                        duplicates += 1
                    continue
                connection.execute(
                    """INSERT INTO economic_observations (
                        observation_id, series_id, observation_date, value, release_date,
                        available_at, vintage_date, revision_seq, source_id, source_uri,
                        ingested_at, rights_tag, quality_flags, payload_hash
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    _sql_params(row),
                )
                inserted += 1
        return UpsertSummary(len(rows), inserted, duplicates, conflicts)

    def upsert_with_revisions(
        self,
        rows: Sequence[PointInTimeObservation],
    ) -> UpsertSummary:
        """Append same-vintage source changes as immutable revisions.

        The ordinary ``upsert`` remains strict and reports a changed primary
        key as a conflict. Governed public refreshes use this method because a
        source can revise current-vintage values between same-day retries.
        """

        inserted = duplicates = conflicts = 0
        with closing(self._connect()) as connection, connection:
            for row in rows:
                existing_rows = connection.execute(
                    """SELECT * FROM economic_observations
                       WHERE series_id = ? AND observation_date = ? AND vintage_date = ?
                       ORDER BY revision_seq""",
                    (
                        row.series_id,
                        row.observation_date.isoformat(),
                        row.vintage_date.isoformat(),
                    ),
                ).fetchall()
                existing = [_from_sql_row(item) for item in existing_rows]
                if any(
                    _material_signature(item) == _material_signature(row)
                    for item in existing
                ):
                    duplicates += 1
                    continue
                candidate = row
                if existing:
                    candidate = replace(
                        row,
                        revision_seq=max(item.revision_seq for item in existing) + 1,
                    )
                try:
                    connection.execute(
                        """INSERT INTO economic_observations (
                            observation_id, series_id, observation_date, value, release_date,
                            available_at, vintage_date, revision_seq, source_id, source_uri,
                            ingested_at, rights_tag, quality_flags, payload_hash
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        _sql_params(candidate),
                    )
                    inserted += 1
                except sqlite3.IntegrityError:
                    conflicts += 1
        return UpsertSummary(len(rows), inserted, duplicates, conflicts)

    def latest_available(self, series_ids: Sequence[str], as_of: datetime) -> list[PointInTimeObservation]:
        history = self.history_available(series_ids, as_of)
        latest: dict[str, PointInTimeObservation] = {}
        for row in history:
            current = latest.get(row.series_id)
            if current is None or row.observation_date > current.observation_date:
                latest[row.series_id] = row
        return [latest[key] for key in sorted(latest)]

    def history_available(
        self,
        series_ids: Sequence[str],
        as_of: datetime,
        *,
        start_date: date | None = None,
    ) -> list[PointInTimeObservation]:
        if not series_ids:
            return []
        cutoff = ensure_aware(as_of, "as_of").isoformat()
        placeholders = ",".join("?" for _ in series_ids)
        clauses = [f"series_id IN ({placeholders})", "available_at <= ?"]
        params: list[Any] = [*series_ids, cutoff]
        if start_date:
            clauses.append("observation_date >= ?")
            params.append(start_date.isoformat())
        sql = f"""
            SELECT * FROM (
                SELECT o.*, ROW_NUMBER() OVER (
                    PARTITION BY series_id, observation_date
                    ORDER BY available_at DESC, vintage_date DESC, revision_seq DESC, ingested_at DESC
                ) AS version_rank
                FROM economic_observations o
                WHERE {' AND '.join(clauses)}
            ) ranked
            WHERE version_rank = 1
            ORDER BY series_id, observation_date
        """
        with closing(self._connect()) as connection:
            return [_from_sql_row(row) for row in connection.execute(sql, params).fetchall()]

    def vintages(self, series_id: str, observation_date: date) -> list[PointInTimeObservation]:
        with closing(self._connect()) as connection:
            rows = connection.execute(
                """SELECT * FROM economic_observations
                   WHERE series_id = ? AND observation_date = ?
                   ORDER BY available_at, vintage_date, revision_seq""",
                (series_id, observation_date.isoformat()),
            ).fetchall()
        return [_from_sql_row(row) for row in rows]

    def count(self) -> int:
        with closing(self._connect()) as connection:
            return int(connection.execute("SELECT COUNT(*) FROM economic_observations").fetchone()[0])


class PostgresObservationRepository:
    """Psycopg-compatible implementation of the observation repository contract."""

    def __init__(self, dsn: str, *, connect: Callable[[str], Any] | None = None):
        self.dsn = dsn
        self._connect_func = connect or self._default_connect

    @staticmethod
    def _default_connect(dsn: str) -> Any:
        try:
            import psycopg  # type: ignore[import-not-found]
        except ModuleNotFoundError as exc:  # pragma: no cover
            raise RuntimeError("PostgreSQL repository requires psycopg") from exc
        return psycopg.connect(dsn)

    def _connect(self) -> Any:
        return self._connect_func(self.dsn)

    def upsert(self, rows: Sequence[PointInTimeObservation]) -> UpsertSummary:
        inserted = duplicates = conflicts = 0
        with closing(self._connect()) as connection, connection, connection.cursor() as cursor:
            for row in rows:
                cursor.execute(
                    """SELECT value, release_date, available_at, source_id, payload_hash
                       FROM ai_quant.economic_observations
                       WHERE series_id = %s AND observation_date = %s AND vintage_date = %s AND revision_seq = %s""",
                    (row.series_id, row.observation_date, row.vintage_date, row.revision_seq),
                )
                existing = cursor.fetchone()
                if existing:
                    expected = (row.value, row.release_date, row.available_at, row.source_id, row.payload_hash)
                    if tuple(existing) == expected:
                        duplicates += 1
                    else:
                        conflicts += 1
                    continue
                cursor.execute(
                    """INSERT INTO ai_quant.economic_observations (
                        observation_id, series_id, observation_date, value, release_date,
                        available_at, vintage_date, revision_seq, source_id, source_uri,
                        ingested_at, rights_tag, quality_flags, payload_hash
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s)""",
                    _postgres_params(row),
                )
                inserted += 1
        return UpsertSummary(len(rows), inserted, duplicates, conflicts)

    def latest_available(self, series_ids: Sequence[str], as_of: datetime) -> list[PointInTimeObservation]:
        history = self.history_available(series_ids, as_of)
        latest: dict[str, PointInTimeObservation] = {}
        for row in history:
            if row.series_id not in latest or row.observation_date > latest[row.series_id].observation_date:
                latest[row.series_id] = row
        return [latest[key] for key in sorted(latest)]

    def history_available(
        self,
        series_ids: Sequence[str],
        as_of: datetime,
        *,
        start_date: date | None = None,
    ) -> list[PointInTimeObservation]:
        if not series_ids:
            return []
        cutoff = ensure_aware(as_of, "as_of")
        start_clause = "AND observation_date >= %s" if start_date else ""
        params: list[Any] = [list(series_ids), cutoff]
        if start_date:
            params.append(start_date)
        with closing(self._connect()) as connection, connection.cursor() as cursor:
            cursor.execute(
                f"""SELECT DISTINCT ON (series_id, observation_date)
                    observation_id, series_id, observation_date, value, release_date, available_at,
                    vintage_date, revision_seq, source_id, source_uri, ingested_at,
                    rights_tag, quality_flags, payload_hash
                    FROM ai_quant.economic_observations
                    WHERE series_id = ANY(%s) AND available_at <= %s {start_clause}
                    ORDER BY series_id, observation_date, available_at DESC,
                             vintage_date DESC, revision_seq DESC, ingested_at DESC""",
                tuple(params),
            )
            return [_from_postgres_row(row) for row in cursor.fetchall()]

    def vintages(self, series_id: str, observation_date: date) -> list[PointInTimeObservation]:
        with closing(self._connect()) as connection, connection.cursor() as cursor:
            cursor.execute(
                """SELECT observation_id, series_id, observation_date, value, release_date, available_at,
                          vintage_date, revision_seq, source_id, source_uri, ingested_at,
                          rights_tag, quality_flags, payload_hash
                   FROM ai_quant.economic_observations
                   WHERE series_id = %s AND observation_date = %s
                   ORDER BY available_at, vintage_date, revision_seq""",
                (series_id, observation_date),
            )
            return [_from_postgres_row(row) for row in cursor.fetchall()]


def _material_signature(row: PointInTimeObservation) -> tuple[Any, ...]:
    return (
        row.observation_id,
        row.value,
        row.release_date,
        row.available_at,
        row.source_id,
        row.source_uri,
        json.dumps(row.rights_tag, sort_keys=True),
        row.quality_flags,
        row.payload_hash,
    )


def _sql_params(row: PointInTimeObservation) -> tuple[Any, ...]:
    return (
        row.observation_id, row.series_id, row.observation_date.isoformat(), row.value,
        row.release_date.isoformat(), row.available_at.isoformat(), row.vintage_date.isoformat(),
        row.revision_seq, row.source_id, row.source_uri, row.ingested_at.isoformat(),
        json.dumps(row.rights_tag, sort_keys=True), json.dumps(list(row.quality_flags)), row.payload_hash,
    )


def _postgres_params(row: PointInTimeObservation) -> tuple[Any, ...]:
    values = list(_sql_params(row))
    values[2] = row.observation_date
    values[4] = row.release_date
    values[5] = row.available_at
    values[6] = row.vintage_date
    values[10] = row.ingested_at
    return tuple(values)


def _from_sql_row(row: Any) -> PointInTimeObservation:
    return PointInTimeObservation(
        observation_id=str(row["observation_id"]), series_id=str(row["series_id"]),
        observation_date=date.fromisoformat(str(row["observation_date"])), value=float(row["value"]),
        release_date=date.fromisoformat(str(row["release_date"])),
        available_at=datetime.fromisoformat(str(row["available_at"])),
        vintage_date=date.fromisoformat(str(row["vintage_date"])), revision_seq=int(row["revision_seq"]),
        source_id=str(row["source_id"]), source_uri=str(row["source_uri"]),
        ingested_at=datetime.fromisoformat(str(row["ingested_at"])),
        rights_tag=json.loads(row["rights_tag"]), quality_flags=tuple(json.loads(row["quality_flags"])),
        payload_hash=str(row["payload_hash"]),
    )


def _from_postgres_row(row: Any) -> PointInTimeObservation:
    return PointInTimeObservation(
        observation_id=str(row[0]), series_id=str(row[1]), observation_date=row[2], value=float(row[3]),
        release_date=row[4], available_at=row[5], vintage_date=row[6], revision_seq=int(row[7]),
        source_id=str(row[8]), source_uri=str(row[9]), ingested_at=row[10], rights_tag=dict(row[11] or {}),
        quality_flags=tuple(row[12] or ()), payload_hash=str(row[13]),
    )
