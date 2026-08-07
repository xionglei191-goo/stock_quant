"""行情新鲜度取数接线测试（任务 8.2）：脚本侧市场键与公司条目、服务侧公司情报视图。

覆盖需求 5.6（公司最新行情与 `market_freshness` 共用同一 `(market, source_id, data_type)` 键）
与 5.7（公司最新行情早于市场 EOD 时输出滞后天数与原因码）。
"""

from __future__ import annotations

import unittest
from typing import Any

from app.service_modules.market_data import FRESHNESS_REASON_LABELS, MARKET_EOD_SOURCES, market_eod_key
from scripts.latest_analysis_run import (
    _asset_from_ashare_symbol,
    _asset_from_us_ticker,
    _company_intelligence_overview,
)
from scripts.daily_market_insight import (
    DEFAULT_SOURCE_A,
    DEFAULT_SOURCE_U,
    _fetch_latest_market_context,
    _market_eod_target,
    _market_eod_targets,
    build_markdown,
)
from tests.support import SystemServiceTestBase


class _FakeCursor:
    """最小 psycopg cursor 替身：只回答本脚本的两条 SQL，并记录实际使用的取数键。"""

    def __init__(self, *, market_eod_dates: dict, bars: dict) -> None:
        self.market_eod_dates = dict(market_eod_dates)
        self.bars = dict(bars)
        self.latest_date_keys: list[tuple[str, str, str]] = []
        self.bar_keys: list[tuple[tuple[str, ...], str, str, str]] = []
        self._rows: list[tuple] = []

    def execute(self, sql: str, params: tuple = ()) -> None:
        normalized = " ".join(str(sql).split()).lower()
        values = tuple(params or ())
        if normalized.startswith("select as_of_date::text from ai_quant.market_data_bars"):
            market, source_id, data_type = values
            self.latest_date_keys.append((market, source_id, data_type))
            found = self.market_eod_dates.get((market, source_id, data_type), "")
            self._rows = [(found,)] if found else []
            return
        if normalized.startswith("with latest as"):
            security_ids, source_id, data_type, market = values[0], values[1], values[2], values[3]
            self.bar_keys.append((tuple(security_ids), market, source_id, data_type))
            self._rows = [
                self._bar_row(security_id, self.bars[(security_id, source_id, data_type)])
                for security_id in security_ids
                if (security_id, source_id, data_type) in self.bars
                and (not market or self.bars[(security_id, source_id, data_type)]["market"] == market)
            ]
            return
        self._rows = []

    @staticmethod
    def _bar_row(security_id: str, bar: dict) -> tuple:
        return (
            security_id,
            bar["market"],
            bar["source_id"],
            bar["as_of_date"],
            1.0,
            1.0,
            1.0,
            bar.get("close", 1.0),
            100.0,
            1000.0,
            bar.get("previous_date", ""),
            bar.get("previous_close", 0.0),
            0.0,
            0.0,
            0.0,
            0.0,
            0,
        )

    def fetchone(self) -> tuple | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[tuple]:
        return list(self._rows)


def _cursor() -> _FakeCursor:
    """实测场景：A 市场 EOD 2026-07-24、U 市场 EOD 2026-07-27，公司条目落在 2026-05-25。"""

    return _FakeCursor(
        market_eod_dates={
            ("A", DEFAULT_SOURCE_A, "eod"): "2026-07-24",
            ("U", DEFAULT_SOURCE_U, "eod"): "2026-07-27",
        },
        bars={
            ("sec_a", DEFAULT_SOURCE_A, "eod"): {"market": "A", "source_id": DEFAULT_SOURCE_A, "as_of_date": "2026-05-25", "close": 10.0, "previous_date": "2026-05-22", "previous_close": 10.0},
            ("sec_u", DEFAULT_SOURCE_U, "eod"): {"market": "U", "source_id": DEFAULT_SOURCE_U, "as_of_date": "2026-07-27", "close": 20.0, "previous_date": "2026-07-24", "previous_close": 20.0},
            # 同一 A 股标的在美股源下的陈旧记录：旧实现按 source_id = ANY([A, U]) 混取会命中。
            ("sec_a", DEFAULT_SOURCE_U, "eod"): {"market": "U", "source_id": DEFAULT_SOURCE_U, "as_of_date": "2026-07-27", "close": 99.0},
        },
    )


class DailyInsightMarketTargetTests(unittest.TestCase):
    def test_market_targets_come_from_market_eod_key(self) -> None:
        targets = _market_eod_targets(data_type="eod", source_a=DEFAULT_SOURCE_A, source_u=DEFAULT_SOURCE_U)

        self.assertEqual(targets, [market_eod_key("A"), market_eod_key("U")])

    def test_cli_source_overrides_are_preserved(self) -> None:
        targets = _market_eod_targets(data_type="delayed", source_a="tdx_vipdoc_eod", source_u="stooq_us_eod")

        self.assertEqual(
            targets,
            [
                {"market": "A", "source_id": "tdx_vipdoc_eod", "data_type": "delayed"},
                {"market": "U", "source_id": "stooq_us_eod", "data_type": "delayed"},
            ],
        )

    def test_unregistered_market_falls_back_to_a_share_source(self) -> None:
        target = _market_eod_target("H", data_type="eod", source_a=DEFAULT_SOURCE_A, source_u=DEFAULT_SOURCE_U)

        self.assertEqual(target, {"market": "H", "source_id": DEFAULT_SOURCE_A, "data_type": "eod"})


class DailyInsightCompanyContextTests(unittest.TestCase):
    def _context(self, cursor: _FakeCursor, *, statuses: dict | None = None) -> dict:
        return _fetch_latest_market_context(
            cursor,
            security_ids=["sec_a", "sec_u"],
            data_type="eod",
            source_a=DEFAULT_SOURCE_A,
            source_u=DEFAULT_SOURCE_U,
            history_rows=20,
            security_markets={"sec_a": "A", "sec_u": "U"},
            security_statuses=statuses or {"sec_a": "active", "sec_u": "active"},
        )

    def test_company_context_uses_the_same_keys_as_market_freshness(self) -> None:
        cursor = _cursor()

        self._context(cursor)

        self.assertEqual(sorted(cursor.latest_date_keys), [("A", DEFAULT_SOURCE_A, "eod"), ("U", DEFAULT_SOURCE_U, "eod")])
        self.assertEqual(
            sorted((market, source_id, data_type) for _ids, market, source_id, data_type in cursor.bar_keys),
            sorted(cursor.latest_date_keys),
        )
        for _ids, market, source_id, data_type in cursor.bar_keys:
            with self.subTest(market=market):
                self.assertEqual({"market": market, "source_id": source_id, "data_type": data_type}, market_eod_key(market))

    def test_lagging_company_entry_carries_lag_days_and_reason(self) -> None:
        context = self._context(_cursor())

        self.assertEqual(context["sec_a"]["as_of_date"], "2026-05-25")
        self.assertEqual(context["sec_a"]["market_eod_date"], "2026-07-24")
        self.assertEqual(context["sec_a"]["lag_days"], 60)
        self.assertEqual(context["sec_a"]["reason_code"], "security_not_in_latest_eod_batch")
        self.assertEqual(context["sec_a"]["reason_label"], FRESHNESS_REASON_LABELS["security_not_in_latest_eod_batch"])
        self.assertTrue(context["sec_a"]["is_lagging"])

    def test_fresh_company_entry_is_not_marked_as_lagging(self) -> None:
        context = self._context(_cursor())

        self.assertEqual(context["sec_u"]["as_of_date"], "2026-07-27")
        self.assertEqual(context["sec_u"]["lag_days"], 0)
        self.assertEqual(context["sec_u"]["reason_code"], "")
        self.assertEqual(context["sec_u"]["reason_label"], "")
        self.assertFalse(context["sec_u"]["is_lagging"])

    def test_cross_market_source_rows_no_longer_win(self) -> None:
        """旧实现 source_id = ANY([A, U]) 会把 A 股标的的美股源行当成最新行情。"""

        context = self._context(_cursor())

        self.assertEqual(context["sec_a"]["source_id"], DEFAULT_SOURCE_A)
        self.assertEqual(context["sec_a"]["eod_source_id"], DEFAULT_SOURCE_A)
        self.assertNotEqual(context["sec_a"]["close"], 99.0)

    def test_suspended_security_reports_suspension_reason(self) -> None:
        context = self._context(_cursor(), statuses={"sec_a": "suspended"})

        self.assertEqual(context["sec_a"]["reason_code"], "security_suspended_or_delisted")
        self.assertEqual(context["sec_a"]["reason_label"], FRESHNESS_REASON_LABELS["security_suspended_or_delisted"])

    def test_markdown_company_section_explains_the_lag(self) -> None:
        context = self._context(_cursor())
        markdown = build_markdown(
            {
                "research_and_events": {
                    "company_recent_activity": [
                        {
                            "ticker": "DEMO",
                            "issuer_name": "Demo Corp",
                            "market": "A",
                            "latest_market": context["sec_a"],
                            "activity_summary": "1 条公司绑定研报",
                        }
                    ]
                }
            }
        )

        self.assertIn("滞后市场 EOD 2026-07-24 共 60 天", markdown)
        self.assertIn(FRESHNESS_REASON_LABELS["security_not_in_latest_eod_batch"], markdown)


class ServiceMarketEodKeyTests(SystemServiceTestBase):
    def test_key_defaults_match_market_freshness(self) -> None:
        for market in ("A", "U", "H"):
            with self.subTest(market=market):
                self.assertEqual(self.service._market_eod_key(market), market_eod_key(market))
                self.assertEqual(self.service._market_data_source_for_market(market, {}), market_eod_key(market)["source_id"])

    def test_request_field_overrides_stay_available(self) -> None:
        self.assertEqual(self.service._market_data_source_for_market("A", {"ashare_source_id": "tdx_vipdoc_eod"}), "tdx_vipdoc_eod")
        self.assertEqual(self.service._market_data_source_for_market("U", {"us_source_id": "stooq_us_eod"}), "stooq_us_eod")
        self.assertEqual(self.service._market_data_source_for_market("A", {"source_id": "tdx_vipdoc_eod"}), "tdx_vipdoc_eod")

    def test_override_aliases_are_normalized(self) -> None:
        self.assertEqual(
            self.service._market_data_source_for_market("A", {"ashare_source_id": "authorized_eod_market_data"}),
            "public_eod_market_data",
        )


class _RouterApiClient:
    """把 `_company_intelligence_overview` 的 HTTP 调用转接到本地 router，不伪造响应数据。"""

    def __init__(self, router: Any) -> None:
        self.router = router

    def request(self, method: str, path: str, body: dict | None = None, *, role: str = "platform", allow_error: bool = False, timeout: float | None = None) -> dict:
        response = self.router.dispatch(method, path, dict(body or {}), role=role)
        return response.data if response.success else {"_error": response.error}


class CompanyLatestMarketFreshnessTests(SystemServiceTestBase):
    def setUp(self) -> None:
        super().setUp()
        self.service.register_issuer({"issuer_id": "issuer_peer", "legal_name": "Peer Corp", "market": ["A"], "country": "CN"}, actor="platform")
        self.service.register_security(
            {"security_id": "sec_peer", "issuer_id": "issuer_peer", "ticker": "PEER", "exchange": "SSE", "currency": "CNY", "market": "A"},
            actor="platform",
        )
        # 公司自己的最新本地行情停在 2026-05-25，市场（同键）已到 2026-07-24。
        for data_id, security_id, as_of_date, close in (
            ("md_demo_may", "sec_001", "2026-05-25", 10.0),
            ("md_peer_jul", "sec_peer", "2026-07-24", 20.0),
        ):
            self.service.register_market_data_point(
                {
                    "data_id": data_id,
                    "security_id": security_id,
                    "source_id": "public_eod_market_data",
                    "as_of_date": as_of_date,
                    "data_type": "eod",
                    "market": "A",
                    "close": close,
                },
                actor="data",
            )

    def test_company_intelligence_reports_lag_days_and_reason_code(self) -> None:
        freshness = self.service.company_intelligence({"symbol": "DEMO", "limit": 10})["facts_and_events"]["latest_market_freshness"]

        self.assertEqual(freshness["market"], "A")
        self.assertEqual(freshness["source_id"], "public_eod_market_data")
        self.assertEqual(freshness["data_type"], "eod")
        self.assertEqual(freshness["company_as_of_date"], "2026-05-25")
        self.assertEqual(freshness["market_eod_date"], "2026-07-24")
        self.assertEqual(freshness["lag_days"], 60)
        self.assertEqual(freshness["reason_code"], "security_not_in_latest_eod_batch")
        self.assertEqual(freshness["reason_label"], FRESHNESS_REASON_LABELS["security_not_in_latest_eod_batch"])
        self.assertTrue(freshness["is_lagging"])

    def test_annotation_ignores_rows_outside_the_eod_key(self) -> None:
        """需求 5.6：公司侧日期只取 `market_eod_key` 键（`source_id` + `data_type`）下的最新一根。"""

        self.service.register_market_data_point(
            {
                "data_id": "md_demo_delayed_jul",
                "security_id": "sec_001",
                "source_id": "public_eod_market_data",
                "as_of_date": "2026-07-24",
                "data_type": "delayed",
                "market": "A",
                "close": 11.0,
            },
            actor="data",
        )

        facts = self.service.company_intelligence({"symbol": "DEMO", "limit": 10})["facts_and_events"]

        # 既有 latest_market_snapshot 仍按"全部行里最新一条"的原语义取值，本任务不改它。
        self.assertEqual(facts["latest_market_snapshot"]["data_type"], "delayed")
        self.assertEqual(facts["latest_market_snapshot"]["as_of_date"], "2026-07-24")
        self.assertEqual(facts["latest_market_freshness"]["data_type"], "eod")
        self.assertEqual(facts["latest_market_freshness"]["company_as_of_date"], "2026-05-25")
        self.assertEqual(facts["latest_market_freshness"]["lag_days"], 60)

    def test_company_on_the_latest_batch_is_not_marked_as_lagging(self) -> None:
        freshness = self.service.company_intelligence({"symbol": "PEER", "limit": 10})["facts_and_events"]["latest_market_freshness"]

        self.assertEqual(freshness["company_as_of_date"], "2026-07-24")
        self.assertEqual(freshness["lag_days"], 0)
        self.assertEqual(freshness["reason_code"], "")
        self.assertFalse(freshness["is_lagging"])

    def test_coverage_report_lists_lagging_securities_with_the_shared_key(self) -> None:
        report = self.service.market_data_backfill_coverage_report({"market": "A", "as_of_date": "2026-07-24"})["markets"]["A"]

        self.assertEqual(report["source_id"], market_eod_key("A")["source_id"])
        self.assertEqual(report["data_type"], market_eod_key("A")["data_type"])
        self.assertEqual(report["latest_market_date"], "2026-07-24")
        self.assertEqual(report["lagging_count"], 1)
        sample = report["lagging_samples"][0]
        self.assertEqual(sample["security_id"], "sec_001")
        self.assertEqual(sample["latest_as_of_date"], "2026-05-25")
        self.assertEqual(sample["market_eod_date"], "2026-07-24")
        self.assertEqual(sample["lag_days"], 60)
        self.assertEqual(sample["reason_code"], "security_not_in_latest_eod_batch")
        self.assertEqual(sample["reason_label"], FRESHNESS_REASON_LABELS["security_not_in_latest_eod_batch"])

    def test_materialized_latest_analysis_snapshot_carries_the_annotation(self) -> None:
        """物化快照是 `/api/analysis/latest` 的主路径（兜底路径只服务旧产物）。"""

        expected = self.service.company_intelligence({"symbol": "DEMO", "limit": 10})["facts_and_events"]["latest_market_freshness"]

        overview = _company_intelligence_overview(_RouterApiClient(self.router), [{"label": "DEMO", "symbol": "DEMO"}], limit=10)

        self.assertEqual(overview["schema_id"], "latest-analysis-company-intelligence-v1")
        row = overview["companies"][0]
        self.assertEqual(row["market_freshness"], expected)
        self.assertEqual(row["market_freshness"]["lag_days"], 60)
        self.assertEqual(row["market_freshness"]["reason_code"], "security_not_in_latest_eod_batch")

    def test_latest_analysis_company_rows_expose_the_freshness_annotation(self) -> None:
        row_freshness = self.service.company_intelligence({"symbol": "DEMO", "limit": 10})["facts_and_events"]["latest_market_freshness"]

        response = self.router.dispatch("GET", "/api/company-intelligence/DEMO", {"limit": 10}, role="analyst")
        self._assert_api_envelope(response)
        self.assertEqual(response.data["facts_and_events"]["latest_market_freshness"], row_freshness)


class LatestAnalysisAssetSourceParityTests(unittest.TestCase):
    """`latest-analysis` 产物顶层 `latest_market_date` 的取数源必须与 `market_eod_key` 同值。"""

    def test_snapshot_asset_sources_match_market_eod_sources(self) -> None:
        self.assertEqual(_asset_from_ashare_symbol("600000")["source_id"], MARKET_EOD_SOURCES["A"])
        self.assertEqual(_asset_from_us_ticker("AAPL")["source_id"], MARKET_EOD_SOURCES["U"])


if __name__ == "__main__":  # pragma: no cover - manual run helper
    unittest.main()
