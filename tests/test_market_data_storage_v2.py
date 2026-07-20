from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from app.market_data_storage import (
    CANONICAL_PAYLOAD_KEYS,
    market_data_bar_params,
    market_data_payload_sql,
    rights_policy_hash,
    split_market_data_payload,
)
from scripts.migrate_market_data_storage_v2 import cleanup


class MarketDataStorageV2Tests(unittest.TestCase):
    def test_payload_split_removes_only_structured_duplicates_and_records_key_presence(self) -> None:
        payload = {
            "data_id": "md_1",
            "security_id": "security_1",
            "source_id": "source_1",
            "market": "A",
            "as_of_date": "2026-07-18",
            "data_type": "eod",
            "close": 12.5,
            "rights_tag": {"license_class": "public"},
            "created_at": "2026-07-18T08:00:00+00:00",
            "provider_note": "kept",
        }

        mask, extra = split_market_data_payload(payload)

        for bit, key in enumerate(CANONICAL_PAYLOAD_KEYS):
            self.assertEqual(bool(mask & (1 << bit)), key in payload)
        self.assertEqual(
            extra,
            {
                "created_at": "2026-07-18T08:00:00+00:00",
                "provider_note": "kept",
            },
        )

    def test_rights_policy_hash_is_stable_across_mapping_order(self) -> None:
        left = {"license_class": "public", "training_allowed": False}
        right = {"training_allowed": False, "license_class": "public"}

        self.assertEqual(rights_policy_hash(left), rights_policy_hash(right))
        self.assertEqual(len(rights_policy_hash(left)), 64)

    def test_bar_params_store_policy_reference_mask_and_only_extra_payload(self) -> None:
        payload = {
            "data_id": "md_1",
            "security_id": "security_1",
            "source_id": "source_1",
            "market": "U",
            "as_of_date": "2026-07-18",
            "data_type": "eod",
            "currency": "USD",
            "open": 10,
            "high": 12,
            "low": 9,
            "close": 11,
            "adjusted_close": 11,
            "volume": 100,
            "rights_tag": {"license_class": "public"},
            "created_at": "2026-07-18T08:00:00+00:00",
        }

        params = market_data_bar_params(payload, amount=500.0)

        self.assertEqual(params[0], rights_policy_hash(payload["rights_tag"]))
        self.assertEqual(json.loads(params[-2]), {"created_at": payload["created_at"]})
        self.assertTrue(params[-3] & (1 << CANONICAL_PAYLOAD_KEYS.index("amount")))

    def test_bar_params_supply_created_at_when_caller_omits_it(self) -> None:
        params = market_data_bar_params(
            {
                "data_id": "md_2",
                "security_id": "security_2",
                "source_id": "source_1",
                "market": "A",
                "as_of_date": "2026-07-19",
                "close": 10,
                "rights_tag": {"license_class": "public"},
            }
        )

        self.assertIsNotNone(params[-1])

    def test_payload_sql_reconstructs_each_canonical_key_and_extra_payload(self) -> None:
        sql = market_data_payload_sql("bar", "policy")

        for key in CANONICAL_PAYLOAD_KEYS:
            self.assertIn(f"'{key}'", sql)
        self.assertIn("policy.rights_tag", sql)
        self.assertTrue(sql.endswith("bar.extra_payload"))

    def test_schema_declares_compact_table_and_no_duplicate_security_index(self) -> None:
        schema = Path("docs/postgresql-schema.sql").read_text(encoding="utf-8")
        table_sql = schema.split("CREATE TABLE IF NOT EXISTS ai_quant.market_data_bars", 1)[1].split(");", 1)[0]

        self.assertIn("rights_policy_id", table_sql)
        self.assertIn("payload_key_mask", table_sql)
        self.assertIn("extra_payload", table_sql)
        self.assertNotIn("rights_tag JSONB", table_sql)
        self.assertNotIn("\n    payload JSONB", table_sql)
        self.assertNotIn("idx_ai_quant_market_data_bars_security_date", schema)

    def test_cleanup_requires_exact_confirmation_and_verified_backup_manifest(self) -> None:
        with self.assertRaisesRegex(RuntimeError, "exactly match"):
            cleanup("postgresql://unused", "run-1", confirmation="wrong", backup_manifest="missing")

        with TemporaryDirectory() as tmpdir:
            manifest = Path(tmpdir) / "backup.json"
            manifest.write_text(json.dumps({"restore_verified": False, "dump_sha256": "abc"}), encoding="utf-8")
            with self.assertRaisesRegex(RuntimeError, "restore_verified"):
                cleanup("postgresql://unused", "run-1", confirmation="run-1", backup_manifest=manifest)

            manifest.write_text(
                json.dumps({"restore_verified": True, "dump_sha256": "abc", "dump_path": str(Path(tmpdir) / "missing.dump")}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "dump.*missing"):
                cleanup("postgresql://unused", "run-1", confirmation="run-1", backup_manifest=manifest)

            dump = Path(tmpdir) / "backup.dump"
            dump.write_bytes(b"backup")
            manifest.write_text(
                json.dumps({"restore_verified": True, "dump_sha256": "abc", "dump_path": str(dump)}),
                encoding="utf-8",
            )
            with self.assertRaisesRegex(RuntimeError, "SHA-256"):
                cleanup("postgresql://unused", "run-1", confirmation="run-1", backup_manifest=manifest)


if __name__ == "__main__":
    unittest.main()
