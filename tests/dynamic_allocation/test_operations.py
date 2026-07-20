from __future__ import annotations

from contextlib import redirect_stdout
from dataclasses import replace
from datetime import datetime, timezone
from io import StringIO
import json
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from app.dynamic_allocation.operations import build_longitudinal_report, load_daily_reports
from app.dynamic_allocation.paper import JsonlPaperSnapshotRepository, build_paper_snapshot
from scripts.dynamic_allocation_operations_report import main as report_main
from scripts.dynamic_allocation_scheduler_template import main as scheduler_main, render
from tests.dynamic_allocation.test_paper_run import valid_payload


def daily_report(as_of: str, status: str = "completed") -> dict[str, object]:
    return {
        "status": status,
        "mode": "execute",
        "generated_at": as_of,
        "as_of": as_of,
        "classification": "local-only",
        "acceptable_for_non_local_release_gate": False,
        "paper_only": True,
        "live_execution_allowed": False,
        "broker_connected": False,
        "order_execution_allowed": False,
        "decision": {"ready": status == "completed"},
        "refresh": {
            "pipeline": {"missing_series": [], "source_errors": {}},
            "upsert": {"conflicts": 0},
        },
        "auditability": {"configured_series_count": 38, "fresh_series_count": 38},
    }


class LongitudinalOperationsTests(unittest.TestCase):
    def test_monthly_health_and_explicit_gates_do_not_claim_efficacy(self) -> None:
        base = build_paper_snapshot(valid_payload())
        snapshots = [
            base,
            replace(base, run_id="dap_later", as_of="2026-10-17T00:00:00Z", evaluated_at="2026-10-17T00:00:00Z"),
        ]
        reports = [
            daily_report("2026-07-17T00:00:00Z"),
            daily_report("2026-08-17T00:00:00Z"),
            daily_report("2026-09-17T00:00:00Z", "failed"),
            daily_report("2026-10-17T00:00:00Z"),
        ]
        reports[2]["refresh"]["pipeline"]["missing_series"] = ["vix"]  # type: ignore[index]
        result = build_longitudinal_report(
            snapshots,
            reports,
            as_of=datetime(2026, 10, 18, tzinfo=timezone.utc),
        )
        self.assertTrue(result["ledger"]["integrity_validated"])
        self.assertEqual(result["daily_operations"]["failed_runs"], 1)
        self.assertEqual(result["daily_operations"]["data_health_failure_runs"], 1)
        self.assertEqual(result["review_gates"][0]["status"], "insufficient_performance_evidence")
        self.assertEqual(result["review_gates"][1]["status"], "awaiting_elapsed_time")
        self.assertFalse(result["review_gates"][0]["efficacy_proven"])
        self.assertFalse(result["efficacy_evidence"]["performance_series_present"])

    def test_loader_rejects_live_or_non_local_reports(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "daily.json"
            payload = daily_report("2026-07-17T00:00:00Z")
            payload["broker_connected"] = True
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "broker_connected"):
                load_daily_reports([path])

    def test_report_cli_is_read_only_by_default(self) -> None:
        with TemporaryDirectory() as directory:
            ledger_path = Path(directory) / "paper.jsonl"
            output = Path(directory) / "report.json"
            JsonlPaperSnapshotRepository(ledger_path).append(build_paper_snapshot(valid_payload()))
            stdout = StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(
                    report_main(["--ledger", str(ledger_path), "--as-of", "2026-07-18T00:00:00Z"]),
                    0,
                )
            self.assertEqual(json.loads(stdout.getvalue())["ledger"]["record_count"], 1)
            self.assertFalse(output.exists())
            with self.assertRaises(SystemExit):
                report_main(["--ledger", str(ledger_path), "--output", str(output)])


class SchedulerTemplateTests(unittest.TestCase):
    def test_template_uses_explicit_paths_and_preserves_paper_boundary(self) -> None:
        root = Path(__file__).resolve().parents[2]
        python = Path(sys.executable).resolve()
        service, timer = render(
            project_root=root,
            python=python,
            state_dir=root / "data" / "local",
            artifact_dir=root / "artifacts" / "dynamic-allocation",
            calendar="Mon..Fri *-*-* 07:30:00 Asia/Shanghai",
        )
        self.assertIn(str(root / "scripts" / "dynamic_allocation_daily_run.py"), service)
        self.assertIn("--history-dir", service)
        self.assertIn("NoNewPrivileges=true", service)
        self.assertIn("OnCalendar=Mon..Fri", timer)

    def test_cli_defaults_to_print_only(self) -> None:
        root = Path(__file__).resolve().parents[2]
        stdout = StringIO()
        with redirect_stdout(stdout):
            self.assertEqual(
                scheduler_main(
                    [
                        "--project-root", str(root),
                        "--python", str(Path(sys.executable).resolve()),
                        "--state-dir", str(root / "data" / "local"),
                        "--artifact-dir", str(root / "artifacts" / "dynamic-allocation"),
                    ]
                ),
                0,
            )
        self.assertIn("# ai-quant-dynamic-allocation-paper.service", stdout.getvalue())

    def test_template_rejects_systemd_directive_injection(self) -> None:
        root = Path(__file__).resolve().parents[2]
        with self.assertRaisesRegex(ValueError, "unsupported systemd"):
            render(
                project_root=root,
                python=Path(sys.executable).resolve(),
                state_dir=root / "data" / "local",
                artifact_dir=root / "artifacts" / "dynamic-allocation",
                calendar="daily\nOnFailure=unexpected.service",
            )


if __name__ == "__main__":
    unittest.main()
