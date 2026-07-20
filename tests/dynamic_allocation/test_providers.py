from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path

from app.dynamic_allocation.contracts import FetchRequest
from app.dynamic_allocation.data.providers import LocalFixtureProvider


class LocalFixtureProviderTest(unittest.TestCase):
    def test_json_fixture_is_filtered_and_hashes_are_deterministic(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "observations.json"
            path.write_text(json.dumps({"observations": [
                {
                    "series_id": "fred:CPI", "observation_date": "2024-01-01", "value": 3.1,
                    "release_date": "2024-02-10", "available_at": "2024-02-10T13:30:00Z",
                    "vintage_date": "2024-02-10", "revision_seq": 0, "source_id": "fred-public",
                    "rights_tag": {"license_class": "public"},
                },
                {
                    "series_id": "fred:UNRATE", "observation_date": "2024-01-01", "value": 4.0,
                    "release_date": "2024-02-02", "available_at": "2024-02-02T13:30:00Z",
                    "vintage_date": "2024-02-02", "revision_seq": 0, "source_id": "fred-public",
                },
            ]}), encoding="utf-8")
            provider = LocalFixtureProvider(path)
            request = FetchRequest(("fred:CPI",), date(2024, 1, 1), date(2024, 1, 31))
            first = provider.fetch(request)
            second = provider.fetch(request)
        self.assertEqual(len(first), 1)
        self.assertEqual(first[0].observation_id, second[0].observation_id)
        self.assertEqual(first[0].payload_hash, second[0].payload_hash)


if __name__ == "__main__":
    unittest.main()
