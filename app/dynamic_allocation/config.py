from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


@dataclass(frozen=True, slots=True)
class SeriesConfig:
    series_id: str
    source_id: str
    grain: str
    max_staleness_days: int
    critical: bool
    timezone: str


@dataclass(frozen=True, slots=True)
class DynamicAllocationConfig:
    version: str
    series: dict[str, SeriesConfig]
    config_hash: str
    raw: dict[str, Any]
    paper_only: bool = True
    live_execution_allowed: bool = False
    broker_connected: bool = False


def load_config(path: str | Path) -> DynamicAllocationConfig:
    try:
        import yaml  # type: ignore[import-not-found]
    except ModuleNotFoundError as exc:  # pragma: no cover - dependency error is explicit
        raise RuntimeError("dynamic allocation YAML config requires PyYAML") from exc

    config_path = Path(path)
    payload = yaml.safe_load(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, Mapping):
        raise ValueError("dynamic allocation config must be a mapping")
    raw = dict(payload)
    boundary = raw.get("boundary", {})
    if boundary != {
        "paper_only": True,
        "live_execution_allowed": False,
        "broker_connected": False,
    }:
        raise ValueError("paper-only boundary is mandatory")
    registry = raw.get("series", {})
    if not isinstance(registry, Mapping) or not registry:
        raise ValueError("series registry cannot be empty")
    series: dict[str, SeriesConfig] = {}
    for series_id, item in registry.items():
        if not isinstance(item, Mapping):
            raise ValueError(f"series {series_id} must be a mapping")
        max_staleness = int(item.get("max_staleness_days", 0))
        if max_staleness <= 0:
            raise ValueError(f"series {series_id} max_staleness_days must be positive")
        series[str(series_id)] = SeriesConfig(
            series_id=str(series_id),
            source_id=str(item["source_id"]),
            grain=str(item["grain"]),
            max_staleness_days=max_staleness,
            critical=bool(item.get("critical", False)),
            timezone=str(item.get("timezone", "UTC")),
        )
    canonical = json.dumps(raw, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return DynamicAllocationConfig(
        version=str(raw.get("version", "1")),
        series=series,
        config_hash=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        raw=raw,
    )
