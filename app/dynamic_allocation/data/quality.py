from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Sequence

from ..config import DynamicAllocationConfig
from ..contracts import ObservationRepository, ensure_aware


@dataclass(frozen=True, slots=True)
class SeriesHealth:
    series_id: str
    source_id: str
    grain: str
    status: str
    observation_date: str | None
    release_date: str | None
    available_at: str | None
    vintage_date: str | None
    age_days: int | None
    max_staleness_days: int
    critical: bool
    quality_flags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DataHealthReport:
    as_of: str
    coverage_ratio: float
    missing_series: tuple[str, ...]
    stale_series: tuple[str, ...]
    ready_for_factor_calculation: bool
    series: tuple[SeriesHealth, ...]
    config_hash: str
    paper_only: bool = True
    live_execution_allowed: bool = False
    broker_connected: bool = False

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class DataQualityService:
    def __init__(self, repository: ObservationRepository, config: DynamicAllocationConfig):
        self.repository = repository
        self.config = config

    def evaluate(self, as_of: datetime, series_ids: Sequence[str] | None = None) -> DataHealthReport:
        cutoff = ensure_aware(as_of, "as_of")
        selected_ids = list(series_ids or self.config.series)
        latest = {row.series_id: row for row in self.repository.latest_available(selected_ids, cutoff)}
        health: list[SeriesHealth] = []
        missing: list[str] = []
        stale: list[str] = []
        blocking = False
        for series_id in selected_ids:
            definition = self.config.series[series_id]
            row = latest.get(series_id)
            if row is None:
                missing.append(series_id)
                blocking = blocking or definition.critical
                health.append(SeriesHealth(
                    series_id, definition.source_id, definition.grain, "missing", None, None, None, None,
                    None, definition.max_staleness_days, definition.critical, (),
                ))
                continue
            age_days = max(0, (cutoff.date() - row.observation_date).days)
            status = "stale" if age_days > definition.max_staleness_days else "fresh"
            if row.quality_flags:
                status = "quality_blocked"
                blocking = blocking or definition.critical
            if status == "stale":
                stale.append(series_id)
                blocking = blocking or definition.critical
            health.append(SeriesHealth(
                series_id, row.source_id, definition.grain, status, row.observation_date.isoformat(),
                row.release_date.isoformat(), row.available_at.isoformat(), row.vintage_date.isoformat(),
                age_days, definition.max_staleness_days, definition.critical, row.quality_flags,
            ))
        coverage = (len(selected_ids) - len(missing)) / len(selected_ids) if selected_ids else 0.0
        return DataHealthReport(
            as_of=cutoff.isoformat(), coverage_ratio=coverage, missing_series=tuple(missing),
            stale_series=tuple(stale), ready_for_factor_calculation=not blocking and bool(selected_ids),
            series=tuple(health), config_hash=self.config.config_hash,
        )
