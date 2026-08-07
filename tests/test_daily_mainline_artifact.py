"""Daily mainline run artifact tests: payload contract, redaction, file naming."""

from __future__ import annotations

from datetime import datetime, timezone
import json
import unittest

from app.service_modules.daily_mainline_artifact import (
    ARTIFACT_DIR,
    ARTIFACT_SCHEMA_ID,
    MAX_SUMMARY_LENGTH,
    SENSITIVE_KEY_PATTERNS,
    artifact_filename,
    artifact_path,
    artifact_payload,
    redact,
)


def _run(**overrides):
    run = {
        "run_id": "dmrun_0001",
        "run_date": "2026-07-24",
        "status": "passed",
        "candidate_count": 2,
        "queue_count": 1,
        "unsupported_count": 1,
        "failure_reason_codes": ["llm_call_failed"],
        "next_actions": [{"action": "补充证据", "reason_code": "evidence_missing", "endpoint": "/api/evidence"}],
        "stages": [
            {
                "stage": "scan_market_disturbance",
                "status": "passed",
                "started_at": "2026-07-24T01:00:00+00:00",
                "finished_at": "2026-07-24T01:00:05+00:00",
                "record_count": 24,
            },
            {
                "stage": "build_daily_queue",
                "status": "partial",
                "started_at": "2026-07-24T01:00:05+00:00",
                "finished_at": "2026-07-24T01:00:09+00:00",
                "record_count": 1,
                "reason_code": "completeness_unavailable",
            },
        ],
    }
    run.update(overrides)
    return run


def _items():
    return [
        {
            "item_id": "dmitem_0001",
            "run_id": "dmrun_0001",
            "security_id": "sec_001",
            "ticker": "000670",
            "market": "A",
            "rank": 1,
            "selection_reason": "涨跌幅异常",
            "trigger_metric": "one_day_return",
            "trigger_value": 0.1007,
            "as_of_date": "2026-07-24",
            "completeness_status": "partial",
            "partition": "researchable",
            "evidence_ids": ["ev_001"],
            "review_status": "pending",
            "viewpoint": {
                "summary": "成交额放大且行业催化明确。",
                "source_layer": "viewpoint",
                "fact_field_writes": [],
                "template_id": "tpl_daily_candidate_diligence",
                "prompt_version": "daily-mainline-v1",
                "model": "qwen3.6-plus",
                "llm_task_run_id": "llmrun_0001",
                "raw_response": {"choices": [{"message": {"content": "x" * 5000}}]},
                "gateway_headers": {"Authorization": "Bearer local-test-value", "x-amz-signature": "sig"},
            },
        }
    ]


class DailyMainlineArtifactTests(unittest.TestCase):
    def test_payload_carries_fixed_governance_contract(self) -> None:
        payload = artifact_payload(
            run=_run(),
            items=_items(),
            producer_command="python3 scripts/daily_mainline_run.py --as-of-date 2026-07-24",
            environment="local-compose",
            generated_at=datetime(2026, 7, 24, 1, 0, 10, tzinfo=timezone.utc),
        )
        self.assertEqual(payload["schema_id"], ARTIFACT_SCHEMA_ID)
        self.assertEqual(payload["run_id"], "dmrun_0001")
        self.assertEqual(payload["run_date"], "2026-07-24")
        self.assertEqual(payload["generated_at"], "2026-07-24T01:00:10+00:00")
        self.assertEqual(datetime.fromisoformat(payload["generated_at"]).utcoffset().total_seconds(), 0.0)
        self.assertEqual(payload["producer_command"], "python3 scripts/daily_mainline_run.py --as-of-date 2026-07-24")
        self.assertEqual(payload["environment"], "local-compose")
        self.assertEqual(payload["owner_group"], "product_and_ui")
        self.assertEqual(payload["classification"], "local-only")
        self.assertFalse(payload["contains_sensitive_data"])
        self.assertFalse(payload["production_release_gate_eligible"])
        self.assertFalse(payload["acceptable_for_non_local_release"])
        self.assertTrue(payload["paper_only"])
        self.assertFalse(payload["live_execution_allowed"])
        self.assertEqual([stage["stage"] for stage in payload["stages"]], ["scan_market_disturbance", "build_daily_queue"])
        self.assertEqual(payload["stages"][1]["reason_code"], "completeness_unavailable")
        self.assertEqual(payload["stages"][0]["reason_code"], "")
        self.assertEqual(len(payload["items"]), 1)
        self.assertEqual(payload["items"][0]["rank"], 1)

    def test_generated_at_is_normalized_to_utc(self) -> None:
        payload = artifact_payload(
            run=_run(),
            items=_items(),
            producer_command="python3 scripts/daily_mainline_run.py",
            environment="local-compose",
            generated_at="2026-07-24T10:00:00+08:00",
        )
        self.assertEqual(payload["generated_at"], "2026-07-24T02:00:00+00:00")
        fallback = artifact_payload(
            run=_run(),
            items=_items(),
            producer_command="python3 scripts/daily_mainline_run.py",
            environment="local-compose",
            generated_at="not-a-timestamp",
        )
        self.assertEqual(datetime.fromisoformat(fallback["generated_at"]).utcoffset().total_seconds(), 0.0)

    def test_caller_cannot_override_classification_or_release_gate(self) -> None:
        payload = artifact_payload(
            run=_run(
                classification="production",
                production_release_gate_eligible=True,
                acceptable_for_non_local_release=True,
                contains_sensitive_data=True,
                owner_group="platform_and_quality",
                paper_only=False,
                live_execution_allowed=True,
            ),
            items=_items(),
            producer_command="python3 scripts/daily_mainline_run.py",
            environment="local-compose",
        )
        self.assertEqual(payload["classification"], "local-only")
        self.assertFalse(payload["production_release_gate_eligible"])
        self.assertFalse(payload["acceptable_for_non_local_release"])
        self.assertFalse(payload["contains_sensitive_data"])
        self.assertEqual(payload["owner_group"], "product_and_ui")
        self.assertTrue(payload["paper_only"])
        self.assertFalse(payload["live_execution_allowed"])

    def test_payload_excludes_credentials_and_raw_upstream_response(self) -> None:
        payload = artifact_payload(
            run=_run(),
            items=_items(),
            producer_command="python3 scripts/daily_mainline_run.py",
            environment="local-compose",
        )
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("raw_response", serialized)
        self.assertNotIn("Bearer local-test-value", serialized)
        self.assertNotIn("x-amz-signature", serialized)
        viewpoint = payload["items"][0]["viewpoint"]
        self.assertEqual(viewpoint["summary"], "成交额放大且行业催化明确。")
        self.assertEqual(viewpoint["source_layer"], "viewpoint")
        self.assertEqual(viewpoint["fact_field_writes"], [])
        self.assertEqual(set(viewpoint) & set(SENSITIVE_KEY_PATTERNS), set())

    def test_viewpoint_summary_is_truncated(self) -> None:
        items = _items()
        items[0]["viewpoint"]["summary"] = "长" * (MAX_SUMMARY_LENGTH + 500)
        payload = artifact_payload(
            run=_run(),
            items=items,
            producer_command="python3 scripts/daily_mainline_run.py",
            environment="local-compose",
        )
        summary = payload["items"][0]["viewpoint"]["summary"]
        self.assertEqual(len(summary), MAX_SUMMARY_LENGTH)
        self.assertTrue(summary.endswith("...[truncated]"))

    def test_redact_drops_sensitive_keys_recursively(self) -> None:
        cleaned = redact(
            {
                "api_key": "value",
                "nested": {
                    "AUTHORIZATION": "Bearer x",
                    "llm_api_key": "value",
                    "items": [{"access_token": "t", "secret_note": "s", "keep": "ok"}],
                },
                "keep": "ok",
            }
        )
        self.assertEqual(cleaned, {"nested": {"items": [{"keep": "ok"}]}, "keep": "ok"})

    def test_redact_truncates_long_text_and_normalizes_datetime(self) -> None:
        cleaned = redact({"text": "a" * 3000, "when": datetime(2026, 7, 24, tzinfo=timezone.utc)})
        self.assertEqual(len(cleaned["text"]), 2000)
        self.assertTrue(cleaned["text"].endswith("...[truncated]"))
        self.assertEqual(cleaned["when"], "2026-07-24T00:00:00+00:00")

    def test_same_day_runs_get_distinct_file_names(self) -> None:
        first = artifact_path(run_date="2026-07-24", run_id="dmrun_0001")
        second = artifact_path(run_date="2026-07-24", run_id="dmrun_0002")
        self.assertEqual(first, f"{ARTIFACT_DIR}/daily-mainline-2026-07-24-dmrun_0001.json")
        self.assertNotEqual(first, second)
        self.assertEqual(
            artifact_filename(run_date="2026-07-24", run_id="dmrun_0002"),
            "daily-mainline-2026-07-24-dmrun_0002.json",
        )

    def test_file_name_tokens_are_path_safe(self) -> None:
        path = artifact_path(run_date="2026/07/24", run_id="../../etc/passwd", artifact_dir="artifacts/daily-mainline/")
        self.assertEqual(path, "artifacts/daily-mainline/daily-mainline-2026_07_24-.._.._etc_passwd.json")
        self.assertEqual(artifact_filename(run_date="", run_id=""), "daily-mainline-unknown-date-unknown-run.json")


if __name__ == "__main__":
    unittest.main()
