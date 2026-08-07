"""Daily mainline scan unit tests (candidate pool contract, pure domain module)."""

from __future__ import annotations

import unittest

from app.service_modules.daily_mainline_scan import TRIGGER_RULES, build_candidate_pool


def _row(
    security_id: str,
    *,
    market: str = "A",
    one_day_return: float = 0.0,
    amount_ratio: float = 1.0,
    volume_ratio: float = 1.0,
    intraday_range: float = 0.0,
    as_of_date: str = "2026-07-24",
) -> dict[str, object]:
    return {
        "security_id": security_id,
        "market": market,
        "ticker": f"{security_id}.T",
        "issuer_id": f"iss_{security_id}",
        "as_of_date": as_of_date,
        "one_day_return": one_day_return,
        "amount_ratio": amount_ratio,
        "volume_ratio": volume_ratio,
        "intraday_range": intraday_range,
    }


class DailyMainlineTriggerRulesTests(unittest.TestCase):
    def test_trigger_rules_match_existing_scan_thresholds(self) -> None:
        self.assertEqual(
            TRIGGER_RULES,
            (
                ("one_day_return", 0.07, "涨跌幅异常"),
                ("amount_ratio", 3.0, "成交额显著放大"),
                ("volume_ratio", 3.0, "成交量显著放大"),
                ("intraday_range", 0.08, "日内振幅较高"),
            ),
        )


class DailyMainlineCandidatePoolTests(unittest.TestCase):
    def test_only_triggered_rows_enter_pool_with_reason_and_metric(self) -> None:
        pool = build_candidate_pool(
            [
                _row("sec_quiet", one_day_return=0.02, amount_ratio=1.2, volume_ratio=1.1, intraday_range=0.01),
                _row("sec_drop", one_day_return=-0.09),
                _row("sec_volume", volume_ratio=4.0),
            ],
            candidate_limit=20,
            market_quota=10,
        )

        self.assertEqual([item["security_id"] for item in pool], ["sec_drop", "sec_volume"])
        drop = pool[0]
        self.assertEqual(drop["rank"], 1)
        self.assertEqual(drop["trigger_metric"], "one_day_return")
        self.assertEqual(drop["trigger_value"], -0.09)
        self.assertEqual(drop["trigger_threshold"], 0.07)
        self.assertEqual(drop["selection_reason"], "涨跌幅异常")
        self.assertEqual(drop["as_of_date"], "2026-07-24")
        self.assertEqual(drop["issuer_id"], "iss_sec_drop")
        self.assertEqual(drop["ticker"], "sec_drop.T")
        self.assertEqual(drop["market"], "A")
        self.assertEqual(pool[1]["selection_reason"], "成交量显著放大")

    def test_multiple_triggers_join_reasons_in_rule_order(self) -> None:
        pool = build_candidate_pool(
            [_row("sec_multi", one_day_return=0.11, amount_ratio=5.0, volume_ratio=6.0, intraday_range=0.2)],
            candidate_limit=20,
            market_quota=10,
        )

        self.assertEqual(len(pool), 1)
        self.assertEqual(
            pool[0]["selection_reason"],
            "涨跌幅异常、成交额显著放大、成交量显著放大、日内振幅较高",
        )
        self.assertEqual(
            [rule["metric"] for rule in pool[0]["trigger_rules"]],
            [metric for metric, _threshold, _reason in TRIGGER_RULES],
        )

    def test_rank_is_contiguous_and_strength_non_increasing(self) -> None:
        pool = build_candidate_pool(
            [
                _row("sec_b", one_day_return=0.08, amount_ratio=9.0),
                _row("sec_a", one_day_return=0.08, amount_ratio=9.0, volume_ratio=5.0),
                _row("sec_c", one_day_return=0.30),
                _row("sec_d", volume_ratio=3.0),
            ],
            candidate_limit=20,
            market_quota=10,
        )

        self.assertEqual([item["rank"] for item in pool], [1, 2, 3, 4])
        self.assertEqual([item["security_id"] for item in pool], ["sec_c", "sec_a", "sec_b", "sec_d"])
        strengths = [item["trigger_strength"] for item in pool]
        self.assertEqual(strengths, sorted(strengths, reverse=True))

    def test_market_quota_and_candidate_limit_are_applied(self) -> None:
        rows = [_row(f"sec_a{index}", market="A", one_day_return=0.5 - index * 0.01) for index in range(6)]
        rows += [_row(f"sec_u{index}", market="U", one_day_return=0.2 - index * 0.01) for index in range(6)]

        quota_pool = build_candidate_pool(rows, candidate_limit=20, market_quota=2)
        self.assertEqual(
            [item["security_id"] for item in quota_pool],
            ["sec_a0", "sec_a1", "sec_u0", "sec_u1"],
        )
        self.assertEqual([item["rank"] for item in quota_pool], [1, 2, 3, 4])

        limited_pool = build_candidate_pool(rows, candidate_limit=3, market_quota=10)
        self.assertEqual([item["security_id"] for item in limited_pool], ["sec_a0", "sec_a1", "sec_a2"])
        self.assertEqual([item["rank"] for item in limited_pool], [1, 2, 3])

    def test_pool_is_deterministic_and_ignores_unusable_rows(self) -> None:
        rows = [
            _row("sec_dup", one_day_return=0.10),
            _row("sec_dup", one_day_return=0.20),
            _row("", one_day_return=0.30),
            {"security_id": "sec_none", "market": "A", "one_day_return": None, "amount_ratio": "bad"},
        ]

        first = build_candidate_pool(rows, candidate_limit=20, market_quota=10)
        second = build_candidate_pool(list(reversed(rows)), candidate_limit=20, market_quota=10)

        self.assertEqual([item["security_id"] for item in first], ["sec_dup"])
        self.assertEqual(first[0]["trigger_value"], 0.2)
        self.assertEqual(first, second)
        self.assertEqual(build_candidate_pool([], candidate_limit=20, market_quota=10), [])
        self.assertEqual(build_candidate_pool(rows, candidate_limit=0, market_quota=10), [])


if __name__ == "__main__":  # pragma: no cover - manual runs
    unittest.main()
