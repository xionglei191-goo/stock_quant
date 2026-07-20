from __future__ import annotations

from contextlib import redirect_stdout
from copy import deepcopy
from io import StringIO
import json
from pathlib import Path
import tempfile
import unittest

from app.dynamic_allocation.paper import JsonlPaperSnapshotRepository, build_paper_snapshot
from scripts.dynamic_allocation_paper_run import main


def valid_payload() -> dict[str, object]:
    observations = [
        {
            "observation_id": f"obs-{name}",
            "series_id": f"series:{name}",
            "available_at": "2026-07-16T20:00:00Z",
            "vintage_date": "2026-07-16",
        }
        for name in ("valuation", "trend", "volatility", "credit", "leverage", "macro", "liquidity", "breadth")
    ]
    factors = {
        name: {
            "version": "1.0",
            "as_of": "2026-07-16T20:00:00Z",
            "score": 60.0,
            "coverage_ratio": 1.0,
            "source_observation_ids": [f"obs-{name}"],
            "config_hash": "cfg-sha256",
            "contributions": [{"component": name, "weighted_contribution": 1.25}],
        }
        for name in ("valuation", "trend", "volatility", "credit", "leverage", "macro", "liquidity", "breadth")
    }
    return {
        "as_of": "2026-07-17T00:00:00Z",
        "data_observations": observations,
        "factors": factors,
        "model": {
            "name": "rule_regime",
            "version": "rules-v1",
            "regime": "risk_on",
            "raw_equity_score": 64.0,
            "bucket_equity_weight": 0.70,
            "requested_allocation": 0.70,
            "regime_probabilities": {"risk_on": 1.0},
            "explanation": "supportive factors map to the 70% bucket",
        },
        "risk": {
            "kelly_cap": 0.50,
            "risk_cap": 0.60,
            "maximum_allocation": 0.90,
            "final_allocation": 0.50,
            "binding_limit": "kelly_cap",
            "component_caps": {
                "permanent_loss": 0.60,
                "asset": 0.90,
                "correlation": 0.80,
                "data_quality": 1.0,
            },
            "kelly": {
                "available": True,
                "fraction": "half",
                "mode": "continuous",
                "expected_return": 0.08,
                "volatility": 0.20,
                "sample_size": 120,
                "explanation": "half Kelly after confidence shrinkage",
            },
            "explanation": "50% is the minimum of requested, Kelly, risk, and maximum caps",
        },
        "allocation": {"SPY": 0.35, "QQQ": 0.15, "SGOV": 0.50},
        "config": {"version": "dynamic-allocation-v1", "hash": "cfg-sha256"},
        "explanation": ["risk_on rule matched", "half Kelly binds final equity exposure"],
        "warnings": [],
        "paper_only": True,
        "live_execution_allowed": False,
        "broker_connected": False,
        "order_execution_allowed": False,
    }


class PaperSnapshotTests(unittest.TestCase):
    def test_snapshot_is_deterministic_and_complete(self) -> None:
        first = build_paper_snapshot(valid_payload())
        second = build_paper_snapshot(deepcopy(valid_payload()))
        self.assertEqual(first.run_id, second.run_id)
        self.assertEqual(first.to_dict(), second.to_dict())
        self.assertEqual(first.evaluated_at, first.as_of)
        self.assertEqual(len(first.data_observations), 8)
        self.assertEqual(set(first.factors), {"valuation", "trend", "volatility", "credit", "leverage", "macro", "liquidity", "breadth"})
        self.assertTrue(first.paper_only)
        self.assertFalse(first.live_execution_allowed)
        self.assertFalse(first.broker_connected)
        self.assertFalse(first.order_execution_allowed)

    def test_future_observation_and_unknown_factor_lineage_are_rejected(self) -> None:
        future = valid_payload()
        future["data_observations"][0]["available_at"] = "2026-07-18T00:00:00Z"  # type: ignore[index]
        with self.assertRaisesRegex(ValueError, "future observation"):
            build_paper_snapshot(future)
        unknown = valid_payload()
        unknown["factors"]["valuation"]["source_observation_ids"] = ["missing"]  # type: ignore[index]
        with self.assertRaisesRegex(ValueError, "unknown observations"):
            build_paper_snapshot(unknown)

    def test_boundary_risk_math_and_asset_universe_are_enforced(self) -> None:
        live = valid_payload()
        live["broker_connected"] = True
        with self.assertRaisesRegex(ValueError, "broker_connected"):
            build_paper_snapshot(live)
        bad_risk = valid_payload()
        bad_risk["risk"]["final_allocation"] = 0.60  # type: ignore[index]
        with self.assertRaisesRegex(ValueError, "must equal min"):
            build_paper_snapshot(bad_risk)
        hedge = valid_payload()
        hedge["allocation"] = {"SPY": 0.30, "QQQ": 0.15, "SGOV": 0.50, "SQQQ": 0.05}
        with self.assertRaisesRegex(ValueError, "unsupported phase-one"):
            build_paper_snapshot(hedge)

        full_kelly = valid_payload()
        full_kelly["risk"]["kelly"]["fraction"] = "full"  # type: ignore[index]
        with self.assertRaisesRegex(ValueError, "full Kelly is prohibited"):
            build_paper_snapshot(full_kelly)


class PaperRepositoryTests(unittest.TestCase):
    def test_append_is_idempotent_and_replayable(self) -> None:
        snapshot = build_paper_snapshot(valid_payload())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "paper.jsonl"
            repository = JsonlPaperSnapshotRepository(path)
            first = repository.append(snapshot)
            second = repository.append(snapshot)
            self.assertTrue(first.appended)
            self.assertFalse(second.appended)
            self.assertEqual(first.record_hash, second.record_hash)
            self.assertEqual(path.read_text(encoding="utf-8").count("\n"), 1)
            replay = repository.replay()
            self.assertEqual([snapshot.run_id], [item.run_id for item in replay])

    def test_hash_chain_detects_tampering(self) -> None:
        snapshot = build_paper_snapshot(valid_payload())
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "paper.jsonl"
            repository = JsonlPaperSnapshotRepository(path)
            repository.append(snapshot)
            envelope = json.loads(path.read_text(encoding="utf-8"))
            envelope["snapshot"]["allocation"]["SGOV"] = 0.49
            path.write_text(json.dumps(envelope) + "\n", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "content hash mismatch"):
                repository.replay()


class PaperCliTests(unittest.TestCase):
    def test_cli_defaults_to_dry_run_and_execute_requires_explicit_output(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            input_path = Path(directory) / "input.json"
            output_path = Path(directory) / "ledger.jsonl"
            input_path.write_text(json.dumps(valid_payload()), encoding="utf-8")
            stdout = StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(main(["--input", str(input_path)]), 0)
            dry_run = json.loads(stdout.getvalue())
            self.assertEqual(dry_run["mode"], "dry-run")
            self.assertFalse(output_path.exists())

            stdout = StringIO()
            with redirect_stdout(stdout):
                self.assertEqual(
                    main(["--input", str(input_path), "--execute", "--output", str(output_path)]),
                    0,
                )
            execution = json.loads(stdout.getvalue())
            self.assertTrue(execution["append"]["appended"])
            self.assertEqual(execution["classification"], "local-only")
            self.assertFalse(execution["acceptable_for_non_local_release_gate"])
            self.assertTrue(output_path.is_file())


if __name__ == "__main__":
    unittest.main()
