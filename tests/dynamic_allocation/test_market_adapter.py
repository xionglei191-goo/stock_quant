from __future__ import annotations

import unittest
from datetime import datetime, timezone

from app.dynamic_allocation.data.market_adapter import ExistingMarketDataAdapter
from app.models import MarketDataPoint, RightsTag
from app.store import InMemoryStore


class ExistingMarketDataAdapterTest(unittest.TestCase):
    def test_same_day_close_is_not_available_before_configured_delay(self) -> None:
        store = InMemoryStore()
        store.market_data["spy-2024-01-02"] = MarketDataPoint(
            data_id="spy-2024-01-02", security_id="SPY", source_id="fixture", market="U",
            as_of_date="2024-01-02", close=475.0, adjusted_close=475.0,
            rights_tag=RightsTag("public"),
        )
        adapter = ExistingMarketDataAdapter(store, delay_minutes=15)
        before = adapter.history("SPY", datetime(2024, 1, 2, 20, 10, tzinfo=timezone.utc))
        after = adapter.history("SPY", datetime(2024, 1, 2, 21, 20, tzinfo=timezone.utc))
        self.assertEqual(before, [])
        self.assertEqual(len(after), 1)
        self.assertIs(after[0].point, store.market_data["spy-2024-01-02"])


if __name__ == "__main__":
    unittest.main()
