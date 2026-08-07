from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import patch

from app.dynamic_allocation.contracts import FetchRequest
from app.dynamic_allocation.data import public_sources
from app.dynamic_allocation.data.providers import LocalFixtureProvider
from app.dynamic_allocation.data.public_sources import PublicSourceClient


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


class PublicSourceDownloadTest(unittest.TestCase):
    def test_fred_download_falls_back_to_urllib_when_curl_is_absent(self) -> None:
        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self) -> bytes:
                return b"observation_date,CPIAUCSL\n2026-06-01,321.0\n"

        with tempfile.TemporaryDirectory() as temp_dir, patch.dict(
            os.environ,
            {"AI_QUANT_DYNAMIC_ALLOCATION_CACHE": temp_dir},
        ), patch.object(
            public_sources.shutil,
            "which",
            return_value=None,
        ), patch.object(
            public_sources,
            "urlopen",
            return_value=Response(),
        ) as urlopen_mock:
            payload = public_sources.download(
                "https://fred.stlouisfed.org/graph/fredgraph.csv?id=CPIAUCSL"
            )

        self.assertIn(b"CPIAUCSL", payload)
        urlopen_mock.assert_called_once()
        self.assertIsInstance(urlopen_mock.call_args.args[0], str)

    def test_fred_uses_cached_full_csv_without_date_query_parameters(self) -> None:
        urls: list[str] = []

        def downloader(url: str) -> bytes:
            urls.append(url)
            return b"observation_date,CPIAUCSL\n2026-06-01,321.0\n"

        rows = PublicSourceClient(downloader).fred("CPIAUCSL")

        self.assertEqual(rows[0].value, 321.0)
        self.assertEqual(len(urls), 1)
        self.assertIn("id=CPIAUCSL", urls[0])
        self.assertNotIn("cosd=", urls[0])
        self.assertNotIn("coed=", urls[0])


if __name__ == "__main__":
    unittest.main()
