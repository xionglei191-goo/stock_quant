from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from ...models import MarketDataPoint
from ..contracts import ensure_aware


@dataclass(frozen=True, slots=True)
class AvailableMarketBar:
    point: MarketDataPoint
    available_at: datetime


class ExistingMarketDataAdapter:
    """Read existing bars in place; dynamic allocation never copies them."""

    def __init__(
        self,
        store: Any,
        *,
        exchange_timezone: str = "America/New_York",
        close_time: time = time(16, 0),
        delay_minutes: int = 15,
    ):
        self.store = store
        self.timezone = ZoneInfo(exchange_timezone)
        self.close_time = close_time
        self.delay_minutes = delay_minutes

    def history(self, security_id: str, as_of: datetime, *, limit: int = 10000) -> list[AvailableMarketBar]:
        cutoff = ensure_aware(as_of, "as_of")
        query = getattr(self.store, "query_market_data_points", None)
        if callable(query):
            points = query(
                security_id=security_id,
                market="U",
                data_type="eod",
                as_of_date_lte=cutoff.date().isoformat(),
                limit=limit,
                descending=False,
            )
        else:
            points = sorted(
                (point for point in self.store.market_data.values() if point.security_id == security_id),
                key=lambda point: point.as_of_date,
            )[-limit:]
        result: list[AvailableMarketBar] = []
        for point in points:
            local_date = datetime.fromisoformat(point.as_of_date).date()
            available = datetime.combine(local_date, self.close_time, self.timezone)
            from datetime import timedelta

            available += timedelta(minutes=self.delay_minutes)
            available = available.astimezone(cutoff.tzinfo)
            if available <= cutoff:
                result.append(AvailableMarketBar(point, available))
        return result
