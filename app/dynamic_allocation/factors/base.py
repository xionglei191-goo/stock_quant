from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from math import isfinite
from typing import Any, Mapping, Protocol, Sequence


@dataclass(frozen=True)
class HistoricalValue:
    value: float
    available_at: datetime
    observation_id: str = ""


@dataclass(frozen=True)
class SeriesSnapshot:
    value: float | None
    available_at: datetime | None
    observation_id: str = ""
    history: tuple[HistoricalValue, ...] = ()
    quality_flags: tuple[str, ...] = ()


@dataclass(frozen=True)
class FactorContext:
    as_of: datetime
    series: Mapping[str, SeriesSnapshot | Mapping[str, Any]]
    config_hash: str
    data_cutoff_at: datetime | None = None

    def snapshot(self, series_id: str) -> SeriesSnapshot | None:
        raw = self.series.get(series_id)
        if raw is None:
            return None
        if isinstance(raw, SeriesSnapshot):
            return raw
        return _snapshot_from_mapping(raw)


@dataclass(frozen=True)
class ComponentSpec:
    series_id: str
    weight: float
    direction: str = "high"
    critical: bool = False
    min_history: int = 3
    max_age_days: float | None = None
    target: float | None = None

    def __post_init__(self) -> None:
        if self.weight <= 0:
            raise ValueError("component weight must be positive")
        if self.direction not in {"high", "low", "target"}:
            raise ValueError("component direction must be high, low, or target")
        if self.direction == "target" and self.target is None:
            raise ValueError("target direction requires a target")
        if self.min_history < 1:
            raise ValueError("min_history must be positive")


@dataclass(frozen=True)
class ComponentContribution:
    component: str
    raw_value: float | None
    component_score: float | None
    weight: float
    weighted_contribution: float | None
    status: str
    direction: str
    observation_id: str = ""
    available_at: str | None = None
    history_count: int = 0
    explanation: str = ""


@dataclass(frozen=True)
class FactorResult:
    name: str
    version: str
    as_of: str
    score: float | None
    raw_values: Mapping[str, float | None]
    contributions: tuple[ComponentContribution, ...]
    coverage_ratio: float
    freshness_status: str
    data_cutoff_at: str | None
    source_observation_ids: tuple[str, ...]
    config_hash: str
    warnings: tuple[str, ...]
    ready: bool

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["contributions"] = [asdict(item) for item in self.contributions]
        payload["source_observation_ids"] = list(self.source_observation_ids)
        payload["warnings"] = list(self.warnings)
        return payload


class FactorCalculator(Protocol):
    name: str
    version: str

    def required_series(self) -> set[str]: ...

    def calculate(self, context: FactorContext) -> FactorResult: ...

    def explain(self, result: FactorResult) -> list[ComponentContribution]: ...


class PercentileFactorCalculator:
    name = "factor"
    version = "1.0"
    components: tuple[ComponentSpec, ...] = ()
    minimum_coverage = 0.65

    def required_series(self) -> set[str]:
        return {component.series_id for component in self.components}

    def explain(self, result: FactorResult) -> list[ComponentContribution]:
        return list(result.contributions)

    def calculate(self, context: FactorContext) -> FactorResult:
        as_of = _aware(context.as_of)
        total_weight = sum(item.weight for item in self.components)
        available_weight = 0.0
        weighted_score = 0.0
        critical_failure = False
        stale_seen = False
        warnings: list[str] = []
        contributions: list[ComponentContribution] = []
        observation_ids: list[str] = []
        raw_values: dict[str, float | None] = {}

        for spec in self.components:
            snapshot = context.snapshot(spec.series_id)
            raw_value = snapshot.value if snapshot else None
            raw_values[spec.series_id] = raw_value
            status, reason = self._availability(spec, snapshot, as_of)
            score: float | None = None
            history_count = 0

            if status == "available" and snapshot is not None:
                history_points = [
                    point
                    for point in snapshot.history
                    if _aware(point.available_at) <= as_of and _finite(point.value)
                ]
                history = [point.value for point in history_points]
                history_count = len(history)
                if history_count < spec.min_history:
                    status = "insufficient_history"
                    reason = f"needs {spec.min_history} as-of observations; found {history_count}"
                else:
                    score = _component_score(float(snapshot.value), history, spec)
                    available_weight += spec.weight
                    weighted_score += spec.weight * score
                    if snapshot.observation_id:
                        observation_ids.append(snapshot.observation_id)
                    observation_ids.extend(
                        point.observation_id for point in history_points if point.observation_id
                    )

            if status != "available":
                warnings.append(f"{spec.series_id}:{status}:{reason}")
                if status == "stale":
                    stale_seen = True
                if spec.critical:
                    critical_failure = True

            contribution = None if score is None else spec.weight * (score - 50.0) / total_weight
            contributions.append(
                ComponentContribution(
                    component=spec.series_id,
                    raw_value=raw_value,
                    component_score=score,
                    weight=spec.weight,
                    weighted_contribution=contribution,
                    status=status,
                    direction=spec.direction,
                    observation_id=snapshot.observation_id if snapshot else "",
                    available_at=_iso(snapshot.available_at) if snapshot else None,
                    history_count=history_count,
                    explanation=_explanation(spec, score, reason),
                )
            )

        coverage = available_weight / total_weight if total_weight else 0.0
        ready = not critical_failure and coverage >= self.minimum_coverage
        score = round(weighted_score / available_weight, 6) if ready and available_weight else None
        if coverage < self.minimum_coverage:
            warnings.append(
                f"coverage_below_minimum:{coverage:.3f}<{self.minimum_coverage:.3f}"
            )
        if critical_failure:
            warnings.append("critical_component_unavailable")

        cutoff = context.data_cutoff_at
        if cutoff is None:
            available_times = [
                snapshot.available_at
                for series_id in self.required_series()
                if (snapshot := context.snapshot(series_id)) is not None
                and snapshot.available_at is not None
                and _aware(snapshot.available_at) <= as_of
            ]
            cutoff = max(available_times, default=None)

        freshness = "stale" if stale_seen else ("incomplete" if not ready else "fresh")
        return FactorResult(
            name=self.name,
            version=self.version,
            as_of=_iso(as_of) or "",
            score=score,
            raw_values=raw_values,
            contributions=tuple(contributions),
            coverage_ratio=round(coverage, 6),
            freshness_status=freshness,
            data_cutoff_at=_iso(cutoff),
            source_observation_ids=tuple(dict.fromkeys(observation_ids)),
            config_hash=context.config_hash,
            warnings=tuple(warnings),
            ready=ready,
        )

    @staticmethod
    def _availability(
        spec: ComponentSpec,
        snapshot: SeriesSnapshot | None,
        as_of: datetime,
    ) -> tuple[str, str]:
        if snapshot is None:
            return "missing", "series is absent"
        if snapshot.value is None or not _finite(snapshot.value):
            return "missing", "current value is absent or non-finite"
        if snapshot.available_at is None:
            return "missing", "available_at is required"
        available_at = _aware(snapshot.available_at)
        if available_at > as_of:
            return "future", "current observation was not available as of evaluation"
        if spec.max_age_days is not None:
            age_days = (as_of - available_at).total_seconds() / 86400
            if age_days > spec.max_age_days:
                return "stale", f"age {age_days:.1f}d exceeds {spec.max_age_days:.1f}d"
        if snapshot.quality_flags:
            return "quality_blocked", ",".join(snapshot.quality_flags)
        return "available", ""


class ConfiguredPercentileFactorCalculator(PercentileFactorCalculator):
    """Percentile factor whose components are loaded from versioned config."""

    def __init__(
        self,
        name: str,
        components: Sequence[ComponentSpec],
        *,
        version: str = "1.0",
        minimum_coverage: float = 0.65,
    ) -> None:
        if not name.strip() or not components:
            raise ValueError("configured factor requires a name and components")
        if not 0 < minimum_coverage <= 1:
            raise ValueError("minimum_coverage must be within (0,1]")
        self.name = name.strip()
        self.version = version
        self.components = tuple(components)
        self.minimum_coverage = float(minimum_coverage)

def factor_rows(results: Sequence[FactorResult]) -> list[dict[str, Any]]:
    """Return a dataframe-like, JSON-serializable list with one row per factor."""
    return [result.to_dict() for result in results]


def _snapshot_from_mapping(raw: Mapping[str, Any]) -> SeriesSnapshot:
    history: list[HistoricalValue] = []
    for item in raw.get("history", ()):
        if isinstance(item, HistoricalValue):
            history.append(item)
            continue
        if not isinstance(item, Mapping) or item.get("available_at") is None:
            raise ValueError("history entries require value and available_at")
        history.append(
            HistoricalValue(
                value=float(item["value"]),
                available_at=_parse_datetime(item["available_at"]),
                observation_id=str(item.get("observation_id", "")),
            )
        )
    value = raw.get("value")
    return SeriesSnapshot(
        value=float(value) if value is not None else None,
        available_at=(
            _parse_datetime(raw["available_at"])
            if raw.get("available_at") is not None
            else None
        ),
        observation_id=str(raw.get("observation_id", "")),
        history=tuple(history),
        quality_flags=tuple(str(flag) for flag in raw.get("quality_flags", ())),
    )


def _component_score(current: float, history: Sequence[float], spec: ComponentSpec) -> float:
    if spec.direction == "target":
        current = abs(current - float(spec.target))
        history = [abs(value - float(spec.target)) for value in history]
        favorable_high = False
    else:
        favorable_high = spec.direction == "high"
    below = sum(value < current for value in history)
    equal = sum(value == current for value in history)
    percentile = 100.0 * (below + 0.5 * equal) / len(history)
    score = percentile if favorable_high else 100.0 - percentile
    return round(min(100.0, max(0.0, score)), 6)


def _explanation(spec: ComponentSpec, score: float | None, reason: str) -> str:
    if score is None:
        return reason
    if spec.direction == "target":
        rule = f"closer to target {spec.target:g} is more supportive"
    elif spec.direction == "high":
        rule = "higher historical percentile is more supportive"
    else:
        rule = "lower historical percentile is more supportive"
    return f"{rule}; component score={score:.2f}"


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return _aware(value)
    parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    return _aware(parsed)


def _aware(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime | None) -> str | None:
    return _aware(value).isoformat() if value is not None else None


def _finite(value: Any) -> bool:
    try:
        return isfinite(float(value))
    except (TypeError, ValueError):
        return False
