from __future__ import annotations

import unittest

from app.dynamic_allocation.models import AllocationScorer, MarketRegime, RuleRegimeClassifier
from app.dynamic_allocation.portfolio import AllocationPolicy, RebalancePolicy


def scores(**overrides: float) -> dict[str, float]:
    values = {key: 60.0 for key in RuleRegimeClassifier.REQUIRED}
    values.update(overrides)
    return values


class RuleRegimeTests(unittest.TestCase):
    def test_all_five_regimes_are_deterministic_and_explained(self) -> None:
        classifier = RuleRegimeClassifier(minimum_residence_periods=0, transition_margin=0)
        cases = [
            (scores(**{key: 80 for key in RuleRegimeClassifier.REQUIRED}), None, MarketRegime.RISK_ON),
            (scores(valuation=20, trend=70, leverage=30, macro=40), None, MarketRegime.LATE_CYCLE),
            (scores(trend=20, breadth=20, macro=30), None, MarketRegime.RISK_OFF),
            (scores(volatility=10, credit=10), None, MarketRegime.CRISIS),
            (scores(valuation=70, trend=70, breadth=70), MarketRegime.RISK_OFF, MarketRegime.RECOVERY),
        ]
        for factors, previous, expected in cases:
            with self.subTest(expected=expected):
                result = classifier.classify(factors, previous_regime=previous, periods_in_regime=10)
                self.assertEqual(result.regime, expected)
                self.assertIn(expected.value, result.explanation)
                self.assertTrue(result.paper_only)
                self.assertFalse(result.live_execution_allowed)

    def test_residence_hysteresis_retains_state_but_crisis_overrides(self) -> None:
        classifier = RuleRegimeClassifier(minimum_residence_periods=3, transition_margin=0)
        held = classifier.classify(scores(**{key: 80 for key in RuleRegimeClassifier.REQUIRED}), previous_regime="late_cycle", periods_in_regime=1)
        self.assertEqual(held.raw_regime, MarketRegime.RISK_ON)
        self.assertEqual(held.regime, MarketRegime.LATE_CYCLE)
        self.assertTrue(held.retained_by_hysteresis)
        crisis = classifier.classify(scores(volatility=5, credit=5), previous_regime="risk_on", periods_in_regime=0)
        self.assertEqual(crisis.regime, MarketRegime.CRISIS)

    def test_five_bucket_score_and_regime_cap_are_visible(self) -> None:
        scorer = AllocationScorer()
        expected = [(10, 0.10), (30, 0.30), (50, 0.50), (70, 0.70), (90, 0.90)]
        for value, bucket in expected:
            result = scorer.score(scores(**{key: value for key in RuleRegimeClassifier.REQUIRED}), MarketRegime.RISK_ON)
            self.assertEqual(result.score_bucket, bucket)
            self.assertEqual(result.target_equity_weight, bucket)
            self.assertAlmostEqual(sum(result.contributions.values()), result.raw_score, places=3)
        capped = scorer.score(scores(**{key: 90 for key in RuleRegimeClassifier.REQUIRED}), MarketRegime.RISK_OFF)
        self.assertEqual(capped.score_bucket, 0.90)
        self.assertEqual(capped.target_equity_weight, 0.30)
        self.assertIn("min=30%", capped.explanation)

    def test_allocation_and_rebalance_controls(self) -> None:
        allocation = AllocationPolicy().allocate(0.70)
        self.assertEqual(allocation.weights, {"SPY": 0.49, "QQQ": 0.21, "SGOV": 0.30})
        with self.assertRaises(ValueError):
            AllocationPolicy().allocate(0.60)
        policy = RebalancePolicy(no_trade_buffer=0.10, maximum_step=0.15)
        self.assertEqual(policy.apply(0.50, 0.60).action, "hold")
        staged = policy.apply(0.30, 0.90)
        self.assertEqual(staged.applied_weight, 0.45)
        self.assertEqual(staged.action, "increase")
        unscheduled = policy.apply(0.30, 0.90, scheduled=False)
        self.assertEqual(unscheduled.applied_weight, 0.30)


if __name__ == "__main__":
    unittest.main()
