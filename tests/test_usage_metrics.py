"""Usage telemetry tests (local feature-access counters via dispatch)."""

from __future__ import annotations

import unittest

from tests.support import SystemServiceTestBase


class UsageMetricsTests(SystemServiceTestBase):
    def test_dispatch_records_feature_usage(self) -> None:
        self.router.dispatch("GET", "/api/company-intelligence/DEMO", {"limit": 5}, role="analyst")
        self.router.dispatch("GET", "/api/observation-items", {}, role="analyst")
        self.router.dispatch("GET", "/api/observation-items", {}, role="analyst")
        resp = self.router.dispatch("GET", "/api/usage-metrics", {}, role="analyst")
        self._assert_api_envelope(resp)
        features = {row["feature"]: row for row in resp.data["features"]}
        self.assertIn("company_intelligence", features)
        self.assertIn("observation_items", features)
        self.assertEqual(features["observation_items"]["hit_count"], 2)
        self.assertEqual(features["observation_items"]["read_count"], 2)
        self.assertGreaterEqual(resp.data["total_hits"], 3)

    def test_health_metrics_and_self_excluded(self) -> None:
        self.router.dispatch("GET", "/api/health", {}, role="analyst")
        self.router.dispatch("GET", "/api/metrics", {}, role="analyst")
        self.router.dispatch("GET", "/api/usage-metrics", {}, role="analyst")
        resp = self.router.dispatch("GET", "/api/usage-metrics", {}, role="analyst")
        features = {row["feature"] for row in resp.data["features"]}
        self.assertNotIn("health", features)
        self.assertNotIn("metrics", features)
        self.assertNotIn("usage_metrics", features)

    def test_failed_requests_not_counted(self) -> None:
        # unknown route -> 404, must not create a usage row
        self.router.dispatch("GET", "/api/company-events", {}, role="analyst")
        before = self.service.usage_metrics_summary()["total_hits"]
        self.router.dispatch("GET", "/api/does-not-exist", {}, role="analyst")
        after = self.service.usage_metrics_summary()["total_hits"]
        self.assertEqual(before, after)

    def test_summary_surfaced_in_metrics(self) -> None:
        self.router.dispatch("GET", "/api/company-intelligence/DEMO", {"limit": 5}, role="analyst")
        summary = self.service.usage_metrics_summary()
        self.assertGreaterEqual(summary["total_hits"], 1)
        self.assertGreaterEqual(summary["feature_count"], 1)
        self.assertTrue(any(item["feature"] == "company_intelligence" for item in summary["top_features"]))


if __name__ == "__main__":
    unittest.main()
