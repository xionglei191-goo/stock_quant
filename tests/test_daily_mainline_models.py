"""Daily mainline dataclass unit tests (field contract + enum validation, design §3.1)."""

from __future__ import annotations

import unittest
from dataclasses import fields

from app.errors import ValidationError
from app.models import DailyMainlineQueueItem, DailyMainlineRun, DailyWatchlistEntry


class DailyMainlineRunTests(unittest.TestCase):
    def test_defaults_match_design_contract(self) -> None:
        run = DailyMainlineRun(run_id="run_1", run_date="2026-07-28")
        self.assertEqual(run.status, "passed")
        self.assertEqual(run.stages, [])
        self.assertEqual(run.candidate_count, 0)
        self.assertEqual(run.queue_count, 0)
        self.assertEqual(run.unsupported_count, 0)
        self.assertEqual(run.llm_run_ids, [])
        self.assertEqual(run.failure_reason_codes, [])
        self.assertEqual(run.next_actions, [])
        self.assertEqual(run.timeout_seconds, 600)
        self.assertEqual(run.elapsed_seconds, 0.0)
        self.assertEqual(run.artifact_path, "")
        self.assertFalse(run.live_execution_allowed)
        self.assertTrue(run.paper_only)
        self.assertIsNotNone(run.created_at)

    def test_accepts_every_declared_status(self) -> None:
        for status in ("passed", "partial", "failed", "empty"):
            with self.subTest(status=status):
                run = DailyMainlineRun(run_id="run_1", run_date="2026-07-28", status=status)
                self.assertEqual(run.status, status)

    def test_rejects_unknown_status(self) -> None:
        for status in ("", "skipped", "PASSED", "succeeded", "unknown"):
            with self.subTest(status=status):
                with self.assertRaises(ValidationError):
                    DailyMainlineRun(run_id="run_1", run_date="2026-07-28", status=status)

    def test_mutable_defaults_are_not_shared_between_instances(self) -> None:
        first = DailyMainlineRun(run_id="run_1", run_date="2026-07-28")
        second = DailyMainlineRun(run_id="run_2", run_date="2026-07-28")
        first.stages.append({"stage": "scan_market_disturbance"})
        first.llm_run_ids.append("llm_1")
        first.failure_reason_codes.append("llm_call_failed")
        first.next_actions.append({"action": "retry"})
        self.assertEqual(second.stages, [])
        self.assertEqual(second.llm_run_ids, [])
        self.assertEqual(second.failure_reason_codes, [])
        self.assertEqual(second.next_actions, [])

    def test_uses_slots(self) -> None:
        run = DailyMainlineRun(run_id="run_1", run_date="2026-07-28")
        self.assertFalse(hasattr(run, "__dict__"))


class DailyMainlineQueueItemTests(unittest.TestCase):
    def test_defaults_match_design_contract(self) -> None:
        item = DailyMainlineQueueItem(item_id="item_1", run_id="run_1", security_id="sec_1")
        self.assertEqual(item.issuer_id, "")
        self.assertEqual(item.ticker, "")
        self.assertEqual(item.market, "")
        self.assertEqual(item.rank, 0)
        self.assertEqual(item.selection_reason, "")
        self.assertEqual(item.trigger_metric, "")
        self.assertEqual(item.trigger_value, 0.0)
        self.assertEqual(item.as_of_date, "")
        self.assertEqual(item.completeness_status, "unknown")
        self.assertEqual(item.missing_layers, [])
        self.assertEqual(item.partition, "researchable")
        self.assertEqual(item.viewpoint, {})
        self.assertEqual(item.evidence_ids, [])
        self.assertEqual(item.research_answer_id, "")
        self.assertEqual(item.llm_task_run_id, "")
        self.assertEqual(item.template_id, "")
        self.assertEqual(item.review_status, "pending")
        self.assertEqual(item.diligence_status, "generated")
        self.assertEqual(item.diligence_reason_code, "")
        self.assertIsNotNone(item.created_at)

    def test_accepts_every_declared_enum_value(self) -> None:
        cases = {
            "partition": ("researchable", "pending_evidence"),
            "review_status": ("pending", "accepted", "rejected"),
            "diligence_status": ("generated", "unsupported", "skipped", "failed"),
        }
        for field_name, values in cases.items():
            for value in values:
                with self.subTest(field=field_name, value=value):
                    item = DailyMainlineQueueItem(
                        item_id="item_1",
                        run_id="run_1",
                        security_id="sec_1",
                        **{field_name: value},
                    )
                    self.assertEqual(getattr(item, field_name), value)

    def test_rejects_unknown_enum_values(self) -> None:
        cases = {
            "partition": ("", "pending", "RESEARCHABLE", "unsupported"),
            "review_status": ("", "approved", "PENDING", "skipped"),
            "diligence_status": ("", "passed", "GENERATED", "pending_evidence"),
        }
        for field_name, values in cases.items():
            for value in values:
                with self.subTest(field=field_name, value=value):
                    with self.assertRaises(ValidationError):
                        DailyMainlineQueueItem(
                            item_id="item_1",
                            run_id="run_1",
                            security_id="sec_1",
                            **{field_name: value},
                        )

    def test_mutable_defaults_are_not_shared_between_instances(self) -> None:
        first = DailyMainlineQueueItem(item_id="item_1", run_id="run_1", security_id="sec_1")
        second = DailyMainlineQueueItem(item_id="item_2", run_id="run_1", security_id="sec_2")
        first.missing_layers.append("financial_snapshot")
        first.evidence_ids.append("ev_1")
        first.viewpoint["summary"] = "x"
        self.assertEqual(second.missing_layers, [])
        self.assertEqual(second.evidence_ids, [])
        self.assertEqual(second.viewpoint, {})


class DailyWatchlistEntryTests(unittest.TestCase):
    def test_defaults_match_design_contract(self) -> None:
        entry = DailyWatchlistEntry(entry_id="entry_1", security_id="sec_1")
        self.assertEqual(entry.run_id, "")
        self.assertEqual(entry.item_id, "")
        self.assertEqual(entry.selection_reason, "")
        self.assertEqual(entry.actor, "system")
        self.assertIsNotNone(entry.joined_at)

    def test_records_run_lineage_for_watchlist_join(self) -> None:
        entry = DailyWatchlistEntry(
            entry_id="entry_1",
            security_id="sec_1",
            run_id="run_1",
            item_id="item_1",
            selection_reason="涨跌幅异常",
            actor="analyst_1",
        )
        self.assertEqual(entry.run_id, "run_1")
        self.assertEqual(entry.item_id, "item_1")
        self.assertEqual(entry.selection_reason, "涨跌幅异常")
        self.assertEqual(entry.actor, "analyst_1")


class DailyMainlinePrimaryKeyTests(unittest.TestCase):
    def test_primary_key_fields_are_declared_first(self) -> None:
        expectations = (
            (DailyMainlineRun, "run_id"),
            (DailyMainlineQueueItem, "item_id"),
            (DailyWatchlistEntry, "entry_id"),
        )
        for model, key_field in expectations:
            with self.subTest(model=model.__name__):
                declared = [item.name for item in fields(model)]
                self.assertEqual(declared[0], key_field)


if __name__ == "__main__":
    unittest.main()
