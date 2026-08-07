"""行情新鲜度同源与滞后标注的单元测试（`app/service_modules/market_data.py` 纯函数）。

覆盖需求 5.6（公司视图与 `market_freshness` 共用同一 `(market, source_id, data_type)` 键）
与 5.7（公司最新行情早于市场 EOD 时标注滞后天数与原因码）。
"""

from __future__ import annotations

from datetime import date
import unittest

from app.service_modules.market_data import (
    ACTIVE_SECURITY_STATUSES,
    DEFAULT_EOD_DATA_TYPE,
    DEFAULT_EOD_SOURCE_ID,
    FRESHNESS_REASON_CODES,
    FRESHNESS_REASON_LABELS,
    MARKET_EOD_SOURCES,
    SOURCE_COVERAGE_THRESHOLD,
    freshness_lag,
    freshness_reason_label,
    market_eod_key,
    market_freshness_annotation,
)


class MarketEodSourcesTests(unittest.TestCase):
    def test_sources_match_existing_market_freshness_defaults(self) -> None:
        # 与 app/services.py:150 的 PUBLIC_EOD_MARKET_DATA_SOURCE_ID 及
        # scripts/daily_market_insight.py:13-14 的 DEFAULT_SOURCE_A / DEFAULT_SOURCE_U 一致。
        self.assertEqual(MARKET_EOD_SOURCES, {"A": "public_eod_market_data", "U": "yahoo_chart_us_eod"})
        self.assertEqual(DEFAULT_EOD_SOURCE_ID, "public_eod_market_data")
        self.assertEqual(DEFAULT_EOD_DATA_TYPE, "eod")


class SourceConstantParityTests(unittest.TestCase):
    def test_sources_stay_in_sync_with_existing_call_sites(self) -> None:
        from app.services import PUBLIC_EOD_MARKET_DATA_SOURCE_ID
        from scripts.daily_market_insight import DEFAULT_SOURCE_A, DEFAULT_SOURCE_U

        self.assertEqual(MARKET_EOD_SOURCES["A"], PUBLIC_EOD_MARKET_DATA_SOURCE_ID)
        self.assertEqual(MARKET_EOD_SOURCES["A"], DEFAULT_SOURCE_A)
        self.assertEqual(MARKET_EOD_SOURCES["U"], DEFAULT_SOURCE_U)


class MarketEodKeyTests(unittest.TestCase):
    def test_key_structure_matches_daily_insight_market_targets(self) -> None:
        targets = [market_eod_key(market) for market in ("A", "U")]

        self.assertEqual(
            targets,
            [
                {"market": "A", "source_id": "public_eod_market_data", "data_type": "eod"},
                {"market": "U", "source_id": "yahoo_chart_us_eod", "data_type": "eod"},
            ],
        )
        for target in targets:
            self.assertEqual(sorted(target), ["data_type", "market", "source_id"])

    def test_company_view_and_market_freshness_resolve_the_same_key(self) -> None:
        for market in ("A", "U"):
            with self.subTest(market=market):
                self.assertEqual(market_eod_key(market), market_eod_key(market, data_type="eod"))

    def test_market_is_normalized_and_unknown_market_falls_back_to_a_share_source(self) -> None:
        self.assertEqual(market_eod_key(" u "), {"market": "U", "source_id": "yahoo_chart_us_eod", "data_type": "eod"})
        self.assertEqual(market_eod_key("H"), {"market": "H", "source_id": DEFAULT_EOD_SOURCE_ID, "data_type": "eod"})
        self.assertEqual(market_eod_key(""), {"market": "", "source_id": DEFAULT_EOD_SOURCE_ID, "data_type": "eod"})

    def test_explicit_source_and_data_type_overrides_are_preserved(self) -> None:
        self.assertEqual(
            market_eod_key("A", data_type="daily", source_id="tdx_vipdoc_eod"),
            {"market": "A", "source_id": "tdx_vipdoc_eod", "data_type": "daily"},
        )
        self.assertEqual(market_eod_key("U", source_id="  ")["source_id"], "yahoo_chart_us_eod")
        self.assertEqual(market_eod_key("U", data_type="")["data_type"], DEFAULT_EOD_DATA_TYPE)


class FreshnessLagTests(unittest.TestCase):
    def test_measured_mismatch_is_reported_as_exact_calendar_lag(self) -> None:
        """实测问题：公司 latest_market.as_of_date=2026-05-25 对市场 EOD 2026-07-24。"""

        result = freshness_lag(company_as_of_date="2026-05-25", market_eod_date="2026-07-24")

        self.assertEqual(result, {"lag_days": 60, "reason_code": "security_not_in_latest_eod_batch", "is_lagging": True})
        self.assertEqual(result["lag_days"], (date(2026, 7, 24) - date(2026, 5, 25)).days)
        self.assertIn(result["reason_code"], FRESHNESS_REASON_CODES)

    def test_lag_days_matches_calendar_difference_across_month_and_year_boundaries(self) -> None:
        pairs = (
            ("2026-07-23", "2026-07-24"),
            ("2026-02-27", "2026-03-02"),
            ("2024-02-28", "2024-03-01"),
            ("2025-12-30", "2026-01-05"),
            ("2026-05-25", "2026-07-27"),
        )
        for company_date, market_date in pairs:
            with self.subTest(company=company_date, market=market_date):
                expected = (date.fromisoformat(market_date) - date.fromisoformat(company_date)).days
                result = freshness_lag(company_as_of_date=company_date, market_eod_date=market_date)
                self.assertEqual(result["lag_days"], expected)
                self.assertTrue(result["is_lagging"])
                self.assertIn(result["reason_code"], FRESHNESS_REASON_CODES)

    def test_same_date_is_not_lagging_and_carries_no_reason_code(self) -> None:
        self.assertEqual(
            freshness_lag(company_as_of_date="2026-07-24", market_eod_date="2026-07-24"),
            {"lag_days": 0, "reason_code": "", "is_lagging": False},
        )

    def test_company_date_ahead_of_market_keeps_signed_difference_without_reason_code(self) -> None:
        result = freshness_lag(company_as_of_date="2026-07-27", market_eod_date="2026-07-24")

        self.assertEqual(result, {"lag_days": -3, "reason_code": "", "is_lagging": False})

    def test_unparsable_or_missing_dates_report_no_lag(self) -> None:
        for company_date, market_date in (("", "2026-07-24"), ("2026-05-25", ""), ("not-a-date", "2026-07-24")):
            with self.subTest(company=company_date, market=market_date):
                self.assertEqual(
                    freshness_lag(company_as_of_date=company_date, market_eod_date=market_date),
                    {"lag_days": 0, "reason_code": "", "is_lagging": False},
                )

    def test_timestamp_inputs_degrade_to_their_date_part(self) -> None:
        self.assertEqual(
            freshness_lag(company_as_of_date="2026-05-25T00:00:00", market_eod_date="2026-07-24 00:00:00"),
            {"lag_days": 60, "reason_code": "security_not_in_latest_eod_batch", "is_lagging": True},
        )


class FreshnessReasonCodeTests(unittest.TestCase):
    def test_inactive_security_status_reports_suspension_or_delisting(self) -> None:
        for status in ("suspended", "delisted", "inactive"):
            with self.subTest(status=status):
                result = freshness_lag(
                    company_as_of_date="2026-05-25",
                    market_eod_date="2026-07-24",
                    security_status=status,
                )
                self.assertEqual(result["reason_code"], "security_suspended_or_delisted")

    def test_active_security_status_does_not_claim_suspension(self) -> None:
        result = freshness_lag(
            company_as_of_date="2026-07-20",
            market_eod_date="2026-07-24",
            security_status=ACTIVE_SECURITY_STATUSES[0].upper(),
        )

        self.assertEqual(result["reason_code"], "security_not_in_latest_eod_batch")

    def test_low_market_coverage_reports_source_partial_coverage(self) -> None:
        result = freshness_lag(
            company_as_of_date="2026-05-25",
            market_eod_date="2026-07-24",
            security_status="active",
            source_coverage_ratio=SOURCE_COVERAGE_THRESHOLD - 0.05,
        )

        self.assertEqual(result["reason_code"], "source_partial_coverage")

    def test_healthy_or_unknown_coverage_falls_back_to_batch_miss(self) -> None:
        for ratio in (None, SOURCE_COVERAGE_THRESHOLD, 1.0, "bad"):
            with self.subTest(ratio=ratio):
                result = freshness_lag(
                    company_as_of_date="2026-05-25",
                    market_eod_date="2026-07-24",
                    source_coverage_ratio=ratio,
                )
                self.assertEqual(result["reason_code"], "security_not_in_latest_eod_batch")

    def test_security_status_wins_over_coverage_signal(self) -> None:
        result = freshness_lag(
            company_as_of_date="2026-05-25",
            market_eod_date="2026-07-24",
            security_status="delisted",
            source_coverage_ratio=0.1,
        )

        self.assertEqual(result["reason_code"], "security_suspended_or_delisted")

    def test_reason_code_is_empty_whenever_not_lagging(self) -> None:
        for company_date in ("2026-07-24", "2026-07-25"):
            with self.subTest(company=company_date):
                result = freshness_lag(
                    company_as_of_date=company_date,
                    market_eod_date="2026-07-24",
                    security_status="delisted",
                    source_coverage_ratio=0.0,
                )
                self.assertEqual(result["reason_code"], "")
                self.assertFalse(result["is_lagging"])


class FreshnessReasonLabelTests(unittest.TestCase):
    def test_every_reason_code_has_a_distinct_chinese_label(self) -> None:
        self.assertEqual(sorted(FRESHNESS_REASON_LABELS), sorted(FRESHNESS_REASON_CODES))
        labels = [FRESHNESS_REASON_LABELS[code] for code in FRESHNESS_REASON_CODES]
        self.assertEqual(len(set(labels)), len(labels))
        for code, label in FRESHNESS_REASON_LABELS.items():
            with self.subTest(code=code):
                self.assertTrue(label.strip())
                self.assertEqual(freshness_reason_label(code), label)

    def test_empty_or_unknown_reason_code_has_no_label(self) -> None:
        for code in ("", "  ", "unknown_reason"):
            with self.subTest(code=code):
                self.assertEqual(freshness_reason_label(code), "")


class MarketFreshnessAnnotationTests(unittest.TestCase):
    def test_annotation_reports_measured_mismatch_with_key_dates_and_reason(self) -> None:
        annotation = market_freshness_annotation(
            market="A",
            company_as_of_date="2026-05-25",
            market_eod_date="2026-07-24",
            security_status="active",
        )

        self.assertEqual(
            annotation,
            {
                "market": "A",
                "source_id": "public_eod_market_data",
                "data_type": "eod",
                "company_as_of_date": "2026-05-25",
                "market_eod_date": "2026-07-24",
                "lag_days": 60,
                "reason_code": "security_not_in_latest_eod_batch",
                "reason_label": FRESHNESS_REASON_LABELS["security_not_in_latest_eod_batch"],
                "is_lagging": True,
            },
        )

    def test_annotation_key_matches_market_eod_key_including_overrides(self) -> None:
        for market, source_id in (("A", ""), ("U", ""), ("H", ""), ("A", "tdx_vipdoc_eod")):
            with self.subTest(market=market, source_id=source_id):
                annotation = market_freshness_annotation(
                    market=market,
                    company_as_of_date="2026-07-24",
                    market_eod_date="2026-07-24",
                    source_id=source_id,
                )
                key = market_eod_key(market, source_id=source_id)
                self.assertEqual({field: annotation[field] for field in key}, key)

    def test_annotation_without_lag_carries_no_reason_code_or_label(self) -> None:
        annotation = market_freshness_annotation(
            market="U",
            company_as_of_date="2026-07-27",
            market_eod_date="2026-07-27",
            security_status="delisted",
        )

        self.assertFalse(annotation["is_lagging"])
        self.assertEqual(annotation["lag_days"], 0)
        self.assertEqual(annotation["reason_code"], "")
        self.assertEqual(annotation["reason_label"], "")

    def test_annotation_forwards_suspension_and_coverage_signals(self) -> None:
        suspended = market_freshness_annotation(
            market="A",
            company_as_of_date="2026-05-25",
            market_eod_date="2026-07-24",
            security_status="suspended",
        )
        partial = market_freshness_annotation(
            market="A",
            company_as_of_date="2026-05-25",
            market_eod_date="2026-07-24",
            security_status="active",
            source_coverage_ratio=0.4,
        )

        self.assertEqual(suspended["reason_code"], "security_suspended_or_delisted")
        self.assertEqual(suspended["reason_label"], FRESHNESS_REASON_LABELS["security_suspended_or_delisted"])
        self.assertEqual(partial["reason_code"], "source_partial_coverage")
        self.assertEqual(partial["reason_label"], FRESHNESS_REASON_LABELS["source_partial_coverage"])

    def test_missing_market_eod_date_is_not_reported_as_lagging(self) -> None:
        annotation = market_freshness_annotation(market="A", company_as_of_date="2026-05-25", market_eod_date="")

        self.assertEqual(annotation["market_eod_date"], "")
        self.assertFalse(annotation["is_lagging"])
        self.assertEqual(annotation["reason_code"], "")


if __name__ == "__main__":  # pragma: no cover - manual run helper
    unittest.main()
