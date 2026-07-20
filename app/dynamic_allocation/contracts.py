from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timezone
import math
from typing import Any, Protocol, Sequence


def ensure_aware(value: datetime, field_name: str) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{field_name} must include a timezone")
    return value.astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class PointInTimeObservation:
    observation_id: str
    series_id: str
    observation_date: date
    value: float
    release_date: date
    available_at: datetime
    vintage_date: date
    revision_seq: int
    source_id: str
    source_uri: str = ""
    ingested_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    rights_tag: dict[str, Any] = field(default_factory=dict)
    quality_flags: tuple[str, ...] = ()
    payload_hash: str = ""

    def __post_init__(self) -> None:
        if not self.observation_id.strip() or not self.series_id.strip() or not self.source_id.strip():
            raise ValueError("observation_id, series_id, and source_id are required")
        if self.revision_seq < 0:
            raise ValueError("revision_seq must be non-negative")
        if not math.isfinite(float(self.value)):
            raise ValueError("value must be finite")
        available_at = ensure_aware(self.available_at, "available_at")
        ingested_at = ensure_aware(self.ingested_at, "ingested_at")
        if available_at.date() < self.release_date:
            raise ValueError("available_at cannot precede release_date")
        if self.vintage_date < self.release_date:
            raise ValueError("vintage_date cannot precede release_date")
        object.__setattr__(self, "available_at", available_at)
        object.__setattr__(self, "ingested_at", ingested_at)
        object.__setattr__(self, "value", float(self.value))
        object.__setattr__(self, "quality_flags", tuple(sorted(set(self.quality_flags))))


@dataclass(frozen=True, slots=True)
class FetchRequest:
    series_ids: tuple[str, ...]
    start_date: date | None = None
    end_date: date | None = None


@dataclass(frozen=True, slots=True)
class UpsertSummary:
    received: int
    inserted: int
    duplicates: int
    conflicts: int = 0


class ObservationProvider(Protocol):
    def fetch(self, request: FetchRequest) -> list[PointInTimeObservation]: ...


class ObservationRepository(Protocol):
    def upsert(self, rows: Sequence[PointInTimeObservation]) -> UpsertSummary: ...

    def latest_available(
        self, series_ids: Sequence[str], as_of: datetime
    ) -> list[PointInTimeObservation]: ...

    def history_available(
        self,
        series_ids: Sequence[str],
        as_of: datetime,
        *,
        start_date: date | None = None,
    ) -> list[PointInTimeObservation]: ...

    def vintages(self, series_id: str, observation_date: date) -> list[PointInTimeObservation]: ...
