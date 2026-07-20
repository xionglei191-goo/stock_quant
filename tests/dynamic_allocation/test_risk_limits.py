from __future__ import annotations

import unittest

from app.dynamic_allocation.risk import FractionalKellySizer, RiskLimitPolicy


class FractionalKellyRiskTests(unittest.TestCase):
    def test_only_quarter_and_half_kelly_are_allowed(self) -> None:
        with self.assertRaisesRegex(ValueError, "full Kelly is prohibited"):
            FractionalKellySizer("full")
        quarter = FractionalKellySizer("quarter").binomial(p_win=0.60, avg_gain=0.10, avg_loss=0.05, sample_size=60)
        half = FractionalKellySizer("half").binomial(p_win=0.60, avg_gain=0.10, avg_loss=0.05, sample_size=60)
        self.assertTrue(quarter.available)
        self.assertAlmostEqual(quarter.raw_kelly or 0, 0.40)
        self.assertAlmostEqual(quarter.recommended_position or 0, 0.10)
        self.assertAlmostEqual(half.recommended_position or 0, 0.20)

    def test_continuous_kelly_shrinks_mu_once_by_confidence(self) -> None:
        result = FractionalKellySizer("half").continuous(
            expected_return=0.08, volatility=0.20, confidence=0.50, sample_size=60
        )
        self.assertTrue(result.available)
        self.assertAlmostEqual(result.raw_kelly or 0, 1.0)
        self.assertAlmostEqual(result.recommended_position or 0, 0.50)

    def test_insufficient_or_unstable_inputs_are_unavailable(self) -> None:
        small = FractionalKellySizer("quarter").binomial(p_win=0.6, avg_gain=0.1, avg_loss=0.1, sample_size=5)
        unstable = FractionalKellySizer("quarter").continuous(expected_return=0.1, volatility=0.0, sample_size=60)
        self.assertFalse(small.available)
        self.assertIsNone(small.recommended_position)
        self.assertFalse(unstable.available)

    def test_final_allocation_is_minimum_with_binding_explanation(self) -> None:
        kelly = FractionalKellySizer("half").binomial(p_win=0.7, avg_gain=0.1, avg_loss=0.05, sample_size=60)
        decision = RiskLimitPolicy(maximum_allocation=0.90).decide(
            0.90, kelly=kelly, permanent_loss_cap=0.60, asset_cap=0.80,
            correlation_cap=0.55, data_quality_cap=0.70,
        )
        self.assertEqual(decision.final_allocation, min(0.90, kelly.recommended_position or 0, 0.55, 0.90))
        self.assertEqual(decision.binding_limit, "kelly_cap")
        self.assertIn("final=", decision.explanation)
        self.assertTrue(decision.paper_only)
        self.assertFalse(decision.broker_connected)
        self.assertEqual(
            RiskLimitPolicy.permanent_loss_cap(loss_budget=0.15, equity_stress_loss=0.30),
            0.50,
        )

    def test_unavailable_kelly_uses_other_caps_and_warns(self) -> None:
        unavailable = FractionalKellySizer("quarter").continuous(expected_return=None, volatility=None)
        decision = RiskLimitPolicy(maximum_allocation=0.90).decide(
            0.70, kelly=unavailable, permanent_loss_cap=0.50, correlation_cap=0.40
        )
        self.assertEqual(decision.final_allocation, 0.40)
        self.assertEqual(decision.binding_limit, "risk_cap:correlation")
        self.assertTrue(any("Kelly unavailable" in warning for warning in decision.warnings))


if __name__ == "__main__":
    unittest.main()
