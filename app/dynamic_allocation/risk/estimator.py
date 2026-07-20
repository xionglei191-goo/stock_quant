"""Transparent historical inputs for conservative continuous Kelly sizing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import math
import statistics
from typing import Sequence

from ..contracts import PointInTimeObservation


@dataclass(frozen=True, slots=True)
class KellyInputEstimate:
    available: bool
    source: str
    method: str
    series_id: str
    expected_return: float | None
    volatility: float | None
    confidence: float
    sample_size: int
    sample_start: date | None
    sample_end: date | None
    source_observation_ids: tuple[str, ...]
    explanation: str
    warnings: tuple[str, ...] = ()


class HistoricalReturnKellyEstimator:
    """Estimate annual return and volatility from non-overlapping 3-month returns.

    The source series contains rolling three-month SPY returns at month end. Only
    March/June/September/December observations are retained, so adjacent samples
    do not overlap. Expected return is geometric; volatility is annualized sample
    volatility. Explicit floors/caps and confidence shrinkage remain visible.
    """

    def __init__(
        self,
        *,
        series_id: str = "return_3m",
        lookback_years: int = 10,
        minimum_samples: int = 24,
        confidence: float = 0.35,
        expected_return_floor: float = -0.10,
        expected_return_cap: float = 0.12,
        volatility_floor: float = 0.08,
    ) -> None:
        if lookback_years <= 0 or minimum_samples < 2:
            raise ValueError("Kelly estimator lookback and minimum_samples must be positive")
        if not 0 <= confidence <= 1:
            raise ValueError("Kelly estimator confidence must be within 0-1")
        if expected_return_floor > expected_return_cap or volatility_floor <= 0:
            raise ValueError("Kelly estimator floors and caps are invalid")
        self.series_id = series_id
        self.lookback_years = lookback_years
        self.minimum_samples = minimum_samples
        self.confidence = confidence
        self.expected_return_floor = expected_return_floor
        self.expected_return_cap = expected_return_cap
        self.volatility_floor = volatility_floor

    def estimate(
        self,
        rows: Sequence[PointInTimeObservation],
        *,
        as_of: datetime,
    ) -> KellyInputEstimate:
        start = self._lookback_start(as_of.date())
        by_quarter: dict[tuple[int, int], PointInTimeObservation] = {}
        for row in rows:
            observed = row.observation_date
            if row.series_id != self.series_id or observed < start or observed > as_of.date():
                continue
            if observed.month not in {3, 6, 9, 12}:
                continue
            key = (observed.year, (observed.month - 1) // 3 + 1)
            current = by_quarter.get(key)
            if current is None or (row.observation_date, row.available_at) > (current.observation_date, current.available_at):
                by_quarter[key] = row
        samples = sorted(by_quarter.values(), key=lambda item: item.observation_date)
        ids = tuple(row.observation_id for row in samples)
        if len(samples) < self.minimum_samples:
            return self._unavailable(
                samples,
                ids,
                f"quarterly sample_size {len(samples)} is below minimum {self.minimum_samples}",
            )
        values = [float(row.value) for row in samples]
        if any(not math.isfinite(value) or value <= -1 for value in values):
            return self._unavailable(samples, ids, "return samples must be finite and greater than -100%")

        annual_return = math.prod(1 + value for value in values) ** (4 / len(values)) - 1
        annual_volatility = statistics.stdev(values) * math.sqrt(4)
        clipped_return = min(max(annual_return, self.expected_return_floor), self.expected_return_cap)
        floored_volatility = max(annual_volatility, self.volatility_floor)
        warnings: list[str] = []
        if clipped_return != annual_return:
            warnings.append(
                f"annual expected return was clipped from {annual_return:.4f} to {clipped_return:.4f}"
            )
        if floored_volatility != annual_volatility:
            warnings.append(
                f"annual volatility was floored from {annual_volatility:.4f} to {floored_volatility:.4f}"
            )
        return KellyInputEstimate(
            available=True,
            source="estimated",
            method="non_overlapping_quarterly_spy_return_3m_geometric_v1",
            series_id=self.series_id,
            expected_return=round(clipped_return, 10),
            volatility=round(floored_volatility, 10),
            confidence=self.confidence,
            sample_size=len(samples),
            sample_start=samples[0].observation_date,
            sample_end=samples[-1].observation_date,
            source_observation_ids=ids,
            explanation=(
                f"estimated from {len(samples)} non-overlapping quarter-end {self.series_id} observations "
                f"from {samples[0].observation_date.isoformat()} to {samples[-1].observation_date.isoformat()}; "
                f"geometric annual return={annual_return:.4f}, annualized volatility={annual_volatility:.4f}, "
                f"confidence shrink={self.confidence:.2f}"
            ),
            warnings=tuple(warnings),
        )

    def _unavailable(
        self,
        samples: Sequence[PointInTimeObservation],
        ids: tuple[str, ...],
        reason: str,
    ) -> KellyInputEstimate:
        return KellyInputEstimate(
            available=False,
            source="estimated",
            method="non_overlapping_quarterly_spy_return_3m_geometric_v1",
            series_id=self.series_id,
            expected_return=None,
            volatility=None,
            confidence=self.confidence,
            sample_size=len(samples),
            sample_start=samples[0].observation_date if samples else None,
            sample_end=samples[-1].observation_date if samples else None,
            source_observation_ids=ids,
            explanation=f"Kelly input estimate unavailable: {reason}",
            warnings=(reason,),
        )

    def _lookback_start(self, as_of: date) -> date:
        try:
            return as_of.replace(year=as_of.year - self.lookback_years)
        except ValueError:
            return as_of.replace(year=as_of.year - self.lookback_years, day=28)
