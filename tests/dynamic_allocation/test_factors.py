from __future__ import annotations

import unittest
from datetime import datetime, timedelta, timezone

from app.dynamic_allocation.factors import (
    BreadthFactor,
    CreditFactor,
    FactorContext,
    LeverageFactor,
    LiquidityFactor,
    MacroFactor,
    TrendFactor,
    ValuationFactor,
    VolatilityFactor,
    factor_rows,
)
from app.dynamic_allocation.factors.base import ComponentSpec, PercentileFactorCalculator


AS_OF = datetime(2026, 7, 17, 12, tzinfo=timezone.utc)


def supportive_series(calculator):
    series = {}
    for index, spec in enumerate(calculator.components):
        if spec.direction == "high":
            current, historical = 10.0, [1.0, 2.0, 3.0, 4.0]
        elif spec.direction == "low":
            current, historical = 1.0, [2.0, 3.0, 4.0, 5.0]
        else:
            current, historical = float(spec.target), [4.0, 5.0, 6.0, 7.0]
        series[spec.series_id] = {
            "value": current,
            "available_at": (AS_OF - timedelta(days=1)).isoformat(),
            "observation_id": f"obs-{index}",
            "history": [
                {
                    "value": value,
                    "available_at": (AS_OF - timedelta(days=20 - offset)).isoformat(),
                    "observation_id": f"hist-{index}-{offset}",
                }
                for offset, value in enumerate(historical)
            ],
        }
    return series


class SingleComponentFactor(PercentileFactorCalculator):
    name = "single"
    components = (ComponentSpec("signal", 1.0, "high", critical=True),)


class FactorCalculatorTest(unittest.TestCase):
    def test_all_eight_factor_families_are_explainable_and_directionally_consistent(self):
        calculators = [
            ValuationFactor(),
            TrendFactor(),
            VolatilityFactor(),
            CreditFactor(),
            LeverageFactor(),
            MacroFactor(),
            LiquidityFactor(),
            BreadthFactor(),
        ]
        results = []
        for calculator in calculators:
            result = calculator.calculate(
                FactorContext(AS_OF, supportive_series(calculator), "cfg-123")
            )
            self.assertTrue(result.ready, calculator.name)
            self.assertEqual(result.score, 100.0, calculator.name)
            self.assertEqual(result.coverage_ratio, 1.0)
            self.assertEqual(result.config_hash, "cfg-123")
            self.assertEqual(result.version, "1.0")
            self.assertTrue(result.source_observation_ids)
            self.assertTrue(any(item.startswith("hist-") for item in result.source_observation_ids))
            self.assertTrue(all(item.explanation for item in result.contributions))
            results.append(result)

        rows = factor_rows(results)
        self.assertEqual(len(rows), 8)
        self.assertEqual({row["name"] for row in rows}, {item.name for item in calculators})
        self.assertIsInstance(rows[0]["contributions"], list)

    def test_future_history_is_excluded_from_historical_percentile(self):
        context = FactorContext(
            AS_OF,
            {
                "signal": {
                    "value": 5,
                    "available_at": AS_OF.isoformat(),
                    "observation_id": "current",
                    "history": [
                        {"value": 1, "available_at": (AS_OF - timedelta(days=3)).isoformat()},
                        {"value": 2, "available_at": (AS_OF - timedelta(days=2)).isoformat()},
                        {"value": 3, "available_at": (AS_OF - timedelta(days=1)).isoformat()},
                        {"value": 100, "available_at": (AS_OF + timedelta(days=1)).isoformat()},
                    ],
                }
            },
            "cfg-pit",
        )
        result = SingleComponentFactor().calculate(context)
        self.assertEqual(result.score, 100.0)
        self.assertEqual(result.contributions[0].history_count, 3)

    def test_critical_missing_value_blocks_factor_instead_of_using_neutral_score(self):
        calculator = ValuationFactor()
        series = supportive_series(calculator)
        del series["forward_pe"]
        result = calculator.calculate(FactorContext(AS_OF, series, "cfg-missing"))
        self.assertFalse(result.ready)
        self.assertIsNone(result.score)
        self.assertLess(result.coverage_ratio, 1.0)
        self.assertIn("critical_component_unavailable", result.warnings)
        self.assertEqual(result.contributions[0].status, "missing")

    def test_insufficient_history_is_visible_and_blocks_critical_component(self):
        calculator = SingleComponentFactor()
        series = supportive_series(calculator)
        series["signal"]["history"] = series["signal"]["history"][:2]
        result = calculator.calculate(FactorContext(AS_OF, series, "cfg-short"))
        self.assertFalse(result.ready)
        self.assertIsNone(result.score)
        self.assertEqual(result.coverage_ratio, 0.0)
        self.assertEqual(result.contributions[0].status, "insufficient_history")

    def test_stale_data_has_freshness_warning_and_cannot_masquerade_as_complete(self):
        calculator = VolatilityFactor()
        series = supportive_series(calculator)
        series["vix_level"]["available_at"] = (AS_OF - timedelta(days=30)).isoformat()
        result = calculator.calculate(FactorContext(AS_OF, series, "cfg-stale"))
        self.assertFalse(result.ready)
        self.assertIsNone(result.score)
        self.assertEqual(result.freshness_status, "stale")
        self.assertEqual(result.contributions[0].status, "stale")

    def test_future_current_observation_is_rejected(self):
        calculator = SingleComponentFactor()
        series = supportive_series(calculator)
        series["signal"]["available_at"] = (AS_OF + timedelta(minutes=1)).isoformat()
        result = calculator.calculate(FactorContext(AS_OF, series, "cfg-future"))
        self.assertFalse(result.ready)
        self.assertEqual(result.contributions[0].status, "future")

    def test_quality_flags_block_automatic_scoring(self):
        calculator = SingleComponentFactor()
        series = supportive_series(calculator)
        series["signal"]["quality_flags"] = ["rights_unclear"]
        result = calculator.calculate(FactorContext(AS_OF, series, "cfg-quality"))
        self.assertFalse(result.ready)
        self.assertEqual(result.contributions[0].status, "quality_blocked")


if __name__ == "__main__":
    unittest.main()
