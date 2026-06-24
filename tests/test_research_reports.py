from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from app.research_reports import infer_report_metadata, infer_structured_report_fields


class ResearchReportMetadataTests(unittest.TestCase):
    def test_infer_report_metadata_classifies_path_and_title_keywords(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            report = root / "Goldman Sachs" / "2026" / "03" / "AI芯片行业深度_买入_目标价_盈利预测.pdf"
            report.parent.mkdir(parents=True)
            report.write_bytes(b"%PDF-1.4\n")

            metadata = infer_report_metadata(report, root)

        self.assertEqual(metadata["broker"], "Goldman Sachs")
        self.assertEqual(metadata["year"], "2026")
        self.assertEqual(metadata["month"], "03")
        self.assertEqual(metadata["industry"], "semiconductor")
        self.assertEqual(metadata["viewpoint"]["sentiment"], "positive")
        self.assertIn("rating_or_target_price", metadata["evidence_topics"])
        self.assertIn("earnings_forecast", metadata["evidence_topics"])
        self.assertIn("target_price", metadata["financial_metric_tags"])

    def test_infer_structured_report_fields_extracts_viewpoint_and_forecasts(self) -> None:
        fields = infer_structured_report_fields(
            title="Demo Corp AI芯片公司深度 买入 目标价",
            broker="CICC",
            year="2026",
            month="06",
            text=(
                "分析师：张三、李四\n"
                "评级：买入，12个月目标价 18.5 元，当前价 10.0 元。"
                "核心假设：AI订单落地；毛利率改善。"
                "盈利预测：2026 EPS 1.20 元。"
                "催化剂：新品放量；政策支持。"
                "风险：需求不及预期；竞争加剧。"
                "估值方法：PE 25x。"
            ),
            industry="semiconductor",
        )

        self.assertEqual(fields["report_type"], "update")
        self.assertEqual(fields["language"], "zh")
        self.assertEqual(fields["rating"], "buy")
        self.assertEqual(fields["target_price"], 18.5)
        self.assertEqual(fields["current_price"], 10.0)
        self.assertEqual(fields["target_price_currency"], "CNY")
        self.assertEqual(fields["target_price_horizon"], "12m")
        self.assertEqual(fields["valuation_method"], "P/E")
        self.assertEqual(fields["analyst_names"], ["张三", "李四"])
        self.assertIn("AI订单落地", fields["core_assumptions"])
        self.assertIn("新品放量", fields["catalysts"])
        self.assertIn("需求不及预期", fields["risks"])
        self.assertIn("target_price", {item["forecast_type"] for item in fields["forecasts"]})
        self.assertIn("eps", {item["forecast_type"] for item in fields["forecasts"]})


if __name__ == "__main__":
    unittest.main()
