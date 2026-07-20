from __future__ import annotations

from datetime import datetime
from typing import Iterable

from ..contracts import PointInTimeObservation, ensure_aware


def visible_vintages(
    rows: Iterable[PointInTimeObservation], as_of: datetime
) -> list[PointInTimeObservation]:
    """Select the latest version known at as_of for every observation date."""
    cutoff = ensure_aware(as_of, "as_of")
    selected: dict[tuple[str, object], PointInTimeObservation] = {}
    for row in rows:
        if row.available_at > cutoff:
            continue
        key = (row.series_id, row.observation_date)
        current = selected.get(key)
        rank = (row.available_at, row.vintage_date, row.revision_seq, row.ingested_at)
        if current is None or rank > (
            current.available_at,
            current.vintage_date,
            current.revision_seq,
            current.ingested_at,
        ):
            selected[key] = row
    return sorted(selected.values(), key=lambda item: (item.series_id, item.observation_date))
