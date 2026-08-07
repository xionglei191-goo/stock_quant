from __future__ import annotations

from pathlib import Path
import re
import unittest

from app.service_modules import company_intelligence, completeness_policy


def _full_coverage() -> dict[str, float]:
    return {key: 1.0 for key in completeness_policy.LAYER_COVERAGE_THRESHOLDS}


class ResolveStatusTests(unittest.TestCase):
    def test_complete_requires_no_gaps_no_missing_fields_and_all_thresholds(self) -> None:
        verdict = completeness_policy.resolve_status(
            profile_available=True,
            blocking_gaps=[],
            warning_gaps=[],
            missing_fact_fields=[],
            coverage_scores=_full_coverage(),
        )

        self.assertEqual(verdict["status"], "complete")
        self.assertEqual(verdict["label"], "完整")
        self.assertTrue(verdict["is_complete"])
        self.assertEqual(verdict["missing_layers"], [])

    def test_missing_fact_fields_downgrade_high_score_company_to_partial(self) -> None:
        """Reproduces the /api/company-intelligence/600519 mismatch: 27 missing fields but complete."""

        verdict = completeness_policy.resolve_status(
            profile_available=True,
            blocking_gaps=[],
            warning_gaps=[],
            missing_fact_fields=["management", "revenue", "ir_url"],
            coverage_scores=_full_coverage(),
        )

        self.assertEqual(verdict["status"], "partial")
        self.assertEqual(verdict["label"], "部分完整")
        self.assertFalse(verdict["is_complete"])
        self.assertIn(completeness_policy.MISSING_FACT_FIELDS_LAYER, verdict["missing_layers"])

    def test_gaps_and_unmet_coverage_are_listed_as_missing_layers(self) -> None:
        verdict = completeness_policy.resolve_status(
            profile_available=True,
            blocking_gaps=["events", "events"],
            warning_gaps=["research_results"],
            missing_fact_fields=[],
            coverage_scores={"profile_field_coverage_score": 0.4167, "database_coverage_score": 0.8462, "relationship_coverage_score": 1.0},
        )

        self.assertEqual(verdict["status"], "partial")
        self.assertEqual(
            verdict["missing_layers"],
            ["events", "research_results", "profile_field_coverage", "database_coverage"],
        )

    def test_absent_coverage_key_counts_as_unmet(self) -> None:
        verdict = completeness_policy.resolve_status(
            profile_available=True,
            blocking_gaps=[],
            warning_gaps=[],
            missing_fact_fields=[],
            coverage_scores={"profile_field_coverage_score": 1.0, "database_coverage_score": 1.0},
        )

        self.assertEqual(verdict["status"], "partial")
        self.assertEqual(verdict["missing_layers"], ["relationship_coverage"])

    def test_unavailable_profile_reports_not_found(self) -> None:
        verdict = completeness_policy.resolve_status(
            profile_available=False,
            blocking_gaps=["company_profile"],
            warning_gaps=[],
            missing_fact_fields=[],
            coverage_scores={},
        )

        self.assertEqual(verdict["status"], "not_found")
        self.assertEqual(verdict["label"], "未建档")
        self.assertFalse(verdict["is_complete"])
        self.assertIn("company_profile", verdict["missing_layers"])


class CoverageDenominatorTests(unittest.TestCase):
    def test_score_declares_denominator_and_matches_ratio(self) -> None:
        self.assertEqual(
            completeness_policy.coverage_denominator(total_fields=48, filled_fields=20),
            {"total_fields": 48, "filled_fields": 20, "score": round(20 / 48, 4)},
        )

    def test_zero_total_scores_zero(self) -> None:
        self.assertEqual(
            completeness_policy.coverage_denominator(total_fields=0, filled_fields=5),
            {"total_fields": 0, "filled_fields": 0, "score": 0.0},
        )

    def test_filled_is_clamped_into_denominator_range(self) -> None:
        self.assertEqual(
            completeness_policy.coverage_denominator(total_fields=10, filled_fields=99),
            {"total_fields": 10, "filled_fields": 10, "score": 1.0},
        )
        self.assertEqual(
            completeness_policy.coverage_denominator(total_fields=10, filled_fields=-4),
            {"total_fields": 10, "filled_fields": 0, "score": 0.0},
        )


class NextActionsTests(unittest.TestCase):
    def test_complete_status_needs_no_actions(self) -> None:
        self.assertEqual(
            completeness_policy.next_actions(status="complete", missing_layers=[], missing_fact_fields=[]),
            [],
        )

    def test_partial_status_returns_executable_actions_for_layers_and_fields(self) -> None:
        actions = completeness_policy.next_actions(
            status="partial",
            missing_layers=["market_data", completeness_policy.MISSING_FACT_FIELDS_LAYER],
            missing_fact_fields=["revenue", "ir_url"],
        )

        self.assertGreaterEqual(len(actions), 1)
        for action in actions:
            self.assertTrue(action["target_field"])
            self.assertTrue(action["source_type"])
            self.assertTrue(action["command"] or action["endpoint"])
        self.assertEqual(
            [action["target_field"] for action in actions],
            ["market_data", "revenue", "ir_url"],
        )

    def test_partial_status_without_detail_still_returns_one_action(self) -> None:
        actions = completeness_policy.next_actions(status="partial", missing_layers=[], missing_fact_fields=[])

        self.assertEqual(len(actions), 1)
        self.assertTrue(actions[0]["target_field"])
        self.assertTrue(actions[0]["source_type"])
        self.assertTrue(actions[0]["command"] or actions[0]["endpoint"])

    def test_not_found_status_points_at_company_bootstrap(self) -> None:
        actions = completeness_policy.next_actions(status="not_found", missing_layers=[], missing_fact_fields=[])

        self.assertEqual(actions[0]["target_field"], "company_profile")
        self.assertEqual(actions[0]["endpoint"], "/api/company-database/bootstrap")


def _all_layers_available() -> dict[str, object]:
    return {
        "profile_available": True,
        "market_data_available": True,
        "event_timeline_available": True,
        "relationship_graph_available": True,
        "research_results_available": True,
        "simulation_feedback_available": True,
        "profile_coverage": 1.0,
        "event_backlink_rate": 1.0,
        "relationship_backlink_rate": 1.0,
    }


def _verdict(**overrides: object) -> dict[str, object]:
    kwargs: dict[str, object] = {
        "symbol": "600519",
        "data_quality": _all_layers_available(),
        "section_counts": {"company_profiles": 1, "securities": 1},
        "database_coverage": {"coverage_score": 1.0},
        "profile_field_coverage": {"field_coverage_score": 1.0, "required_fields": ["legal_name"], "missing_fields": []},
        "relationship_coverage": {"coverage_score": 1.0},
    }
    kwargs.update(overrides)
    return company_intelligence.completeness_verdict(
        str(kwargs["symbol"]),
        kwargs["data_quality"],
        kwargs["section_counts"],
        database_coverage=kwargs["database_coverage"],
        profile_field_coverage=kwargs["profile_field_coverage"],
        deep_coverage_fields=lambda include_optional=False: ["legal_name"],
        relationship_coverage=kwargs["relationship_coverage"],
    )


class CompanyIntelligenceVerdictDelegationTests(unittest.TestCase):
    """`company_intelligence.completeness_verdict` 必须与 `completeness_policy` 同口径（需求 5.1、5.2、5.3）。"""

    def test_complete_requires_all_layers_thresholds_and_no_missing_fact_fields(self) -> None:
        verdict = _verdict()

        self.assertEqual(verdict["status"], "complete")
        self.assertEqual(verdict["label"], "完整")
        self.assertTrue(verdict["is_complete"])
        self.assertEqual(verdict["missing_layers"], [])
        self.assertEqual(verdict["next_actions"], [])

    def test_missing_fact_fields_downgrade_full_score_company_to_partial(self) -> None:
        """实测口径矛盾：score≈0.99 且 27 项缺失字段同时报 complete。"""

        verdict = _verdict(
            profile_field_coverage={
                "field_coverage_score": 0.4167,
                "required_fields": ["legal_name", "management", "revenue"],
                "missing_fields": ["management", "revenue"],
            }
        )

        self.assertEqual(verdict["status"], "partial")
        self.assertEqual(verdict["label"], "部分完整")
        self.assertFalse(verdict["is_complete"])
        self.assertIn(completeness_policy.MISSING_FACT_FIELDS_LAYER, verdict["missing_layers"])
        self.assertIn("profile_field_coverage", verdict["missing_layers"])
        self.assertTrue(verdict["next_actions"])
        for action in verdict["next_actions"]:
            self.assertTrue(action["target_field"])
            self.assertTrue(action["source_type"])
            self.assertTrue(action["command"] or action["endpoint"])

    def test_absent_relationship_coverage_keeps_company_out_of_complete(self) -> None:
        verdict = _verdict(relationship_coverage=None)

        self.assertEqual(verdict["relationship_coverage_score"], 0.0)
        self.assertEqual(verdict["status"], "partial")
        self.assertIn("relationship_coverage", verdict["missing_layers"])

    def test_blocking_gap_reports_partial_and_keeps_section_gap_semantics(self) -> None:
        data_quality = _all_layers_available()
        data_quality["event_timeline_available"] = False

        verdict = _verdict(data_quality=data_quality)

        self.assertEqual(verdict["status"], "partial")
        self.assertIn("events", verdict["blocking_gaps"])
        self.assertIn("events", verdict["missing_layers"])
        self.assertEqual(verdict["section_gap_layers"], ["events"])
        self.assertFalse(verdict["ready_for_fact_review"])

    def test_unavailable_profile_reports_not_found_with_actions(self) -> None:
        verdict = _verdict(data_quality={"profile_available": False})

        self.assertEqual(verdict["status"], "not_found")
        self.assertEqual(verdict["label"], "未建档")
        self.assertFalse(verdict["is_complete"])
        self.assertIn("company_profile", verdict["blocking_gaps"])
        self.assertTrue(verdict["next_actions"])

    def test_level_score_and_sections_keep_existing_semantics(self) -> None:
        verdict = _verdict(
            profile_field_coverage={"field_coverage_score": 0.4167, "required_fields": ["legal_name"], "missing_fields": ["management"]},
        )

        # 所有分节可用且加权分达标时 `level` 仍为 complete，不受新增覆盖度/事实字段分层影响。
        self.assertEqual(verdict["level"], "complete")
        self.assertGreaterEqual(float(verdict["score"]), 0.9)
        self.assertEqual(verdict["schema_id"], "company-intelligence-completeness-verdict-v1")
        self.assertEqual([item["section"] for item in verdict["sections"]], [spec[0] for spec in company_intelligence.SECTION_SPECS])
        self.assertEqual(verdict["required_fact_fields"], ["legal_name"])
        self.assertTrue(verdict["ready_for_feedback_review"])
        self.assertTrue(verdict["recommended_next_action"]["action"])

    def test_status_domain_is_limited_to_policy_values(self) -> None:
        cases = [
            _verdict(),
            _verdict(profile_field_coverage={"field_coverage_score": 0.1, "required_fields": ["legal_name"], "missing_fields": ["revenue"]}),
            _verdict(data_quality={"profile_available": False}),
        ]

        for verdict in cases:
            self.assertIn(verdict["status"], completeness_policy.STATUS_VALUES)
            self.assertEqual(verdict["label"], completeness_policy.STATUS_LABELS[str(verdict["status"])])


class UiCompletenessValueDomainTests(unittest.TestCase):
    """UI 侧完整度取值域必须与 `completeness_policy` 对齐（需求 5.3、7.10；设计 §9 风险 1）。"""

    @classmethod
    def setUpClass(cls) -> None:
        cls.ui = Path("app/static/index.html").read_text(encoding="utf-8")

    def _ui_completeness_labels(self) -> dict[str, str]:
        block = re.search(r"const COMPLETENESS_STATUS_LABELS = \{(.*?)\};", self.ui, re.DOTALL)
        self.assertIsNotNone(block, "index.html 缺少 COMPLETENESS_STATUS_LABELS 取值域映射")
        return dict(re.findall(r"(\w+):\s*\"([^\"]+)\"", block.group(1)))

    def test_ui_labels_match_policy_status_labels(self) -> None:
        labels = self._ui_completeness_labels()

        for status, label in completeness_policy.STATUS_LABELS.items():
            self.assertEqual(labels.get(status), label)

    def test_legacy_status_values_are_merged_into_partial_label(self) -> None:
        labels = self._ui_completeness_labels()
        partial_label = completeness_policy.STATUS_LABELS["partial"]

        for legacy in ["usable_with_gaps", "incomplete"]:
            self.assertEqual(labels.get(legacy), partial_label)

    def test_verdict_tone_uses_blocking_gaps_instead_of_removed_status(self) -> None:
        self.assertIn("function companyIntelVerdictTone(status, verdict = {})", self.ui)
        self.assertIn('if ((verdict.blocking_gaps || []).length) return "block";', self.ui)
        self.assertNotIn('status === "incomplete"', self.ui)

    def test_complete_label_cannot_be_shown_with_missing_fact_fields(self) -> None:
        self.assertIn("function companyIntelVerdictView(verdict = {}, fallbackStatus = \"unknown\")", self.ui)
        self.assertIn('const downgraded = declaredStatus === "complete" && missingFields.length > 0;', self.ui)
        for consumer in [
            "const view = companyIntelVerdictView(verdict);",
            "const verdictLabel = companyIntelVerdictView(verdict, data.status).label;",
        ]:
            self.assertIn(consumer, self.ui)


if __name__ == "__main__":  # pragma: no cover - manual run helper
    unittest.main()
