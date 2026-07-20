from __future__ import annotations

import csv
import hashlib
import json
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from ..contracts import FetchRequest, PointInTimeObservation


class LocalFixtureProvider:
    """Read governed local CSV or JSON observations without network access."""

    def __init__(self, path: str | Path):
        self.path = Path(path)

    def fetch(self, request: FetchRequest) -> list[PointInTimeObservation]:
        records = list(self._records())
        requested = set(request.series_ids)
        rows = [self._normalize(item) for item in records]
        return [
            row
            for row in rows
            if row.series_id in requested
            and (request.start_date is None or row.observation_date >= request.start_date)
            and (request.end_date is None or row.observation_date <= request.end_date)
        ]

    def _records(self) -> Iterable[dict[str, Any]]:
        suffix = self.path.suffix.lower()
        if suffix == ".csv":
            with self.path.open(encoding="utf-8", newline="") as stream:
                yield from csv.DictReader(stream)
            return
        if suffix == ".json":
            payload = json.loads(self.path.read_text(encoding="utf-8"))
            records = payload.get("observations", []) if isinstance(payload, dict) else payload
            if not isinstance(records, list):
                raise ValueError("JSON fixture must be a list or contain observations list")
            yield from records
            return
        raise ValueError("fixture provider supports only .csv and .json")

    @staticmethod
    def _normalize(item: dict[str, Any]) -> PointInTimeObservation:
        material = dict(item)
        material.pop("observation_id", None)
        material.pop("ingested_at", None)
        material.pop("payload_hash", None)
        payload_hash = str(item.get("payload_hash") or hashlib.sha256(
            json.dumps(material, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest())
        observation_id = str(item.get("observation_id") or f"obs-{payload_hash[:24]}")
        return PointInTimeObservation(
            observation_id=observation_id,
            series_id=str(item["series_id"]),
            observation_date=date.fromisoformat(str(item["observation_date"])),
            value=float(item["value"]),
            release_date=date.fromisoformat(str(item["release_date"])),
            available_at=_parse_datetime(item["available_at"]),
            vintage_date=date.fromisoformat(str(item["vintage_date"])),
            revision_seq=int(item.get("revision_seq", 0)),
            source_id=str(item["source_id"]),
            source_uri=str(item.get("source_uri", "")),
            ingested_at=_parse_datetime(item.get("ingested_at") or datetime.now(timezone.utc)),
            rights_tag=_mapping(item.get("rights_tag", {})),
            quality_flags=tuple(_list(item.get("quality_flags", []))),
            payload_hash=payload_hash,
        )


def _parse_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def _mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        parsed = json.loads(value)
        if isinstance(parsed, dict):
            return parsed
    return {}


def _list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value]
    if isinstance(value, str) and value.strip():
        if value.lstrip().startswith("["):
            return [str(item) for item in json.loads(value)]
        return [part.strip() for part in value.split(",") if part.strip()]
    return []
