"""Shared test fixtures for the SystemService suite.

Provides the common base TestCase (env isolation + baseline source/issuer/security
fixture + API-envelope assertion) and the fake Postgres / SEC connector doubles,
so that per-domain test modules can `from tests.support import ...` instead of
re-declaring the 57-line setUp and the DB fakes.
"""

from __future__ import annotations

import json
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from app.api import ApiRouter
from app.connectors import ConnectorDocument
from app.document_parser import PaddleOCRParser
from app.object_store import LocalObjectStore
from app.services import SystemService


class _FakePostgresCursor:
    def __init__(self, database):
        self.database = database
        self._rows = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def execute(self, sql, params=None):
        normalized = " ".join(sql.split()).lower()
        self.database.statements.append(sql)
        if normalized.startswith("select count(*) from ai_quant.records where collection"):
            collection = params[0] if params else "market_data"
            self._rows = [(sum(1 for record_collection, _item_id in self.database.records if record_collection == collection),)]
        elif normalized.startswith("select to_regclass('ai_quant.market_data_bars')"):
            self._rows = [(True,)]
        elif normalized.startswith("select to_regclass('ai_quant.schema_migrations')"):
            self._rows = [(self.database.baseline_schema_recorded,)]
        elif normalized.startswith("select 1 from ai_quant.schema_migrations"):
            self._rows = [(1,)] if self.database.baseline_schema_recorded else []
        elif normalized.startswith("select count(*) from ai_quant.market_data_bars"):
            bars = self._filtered_market_data_bars(normalized, params or [])
            self._rows = [(len(bars),)]
        elif normalized.startswith("select data_id, security_id, source_id, market, as_of_date::text") or normalized.startswith("select b.data_id, b.security_id, b.source_id, b.market, b.as_of_date::text"):
            bars = self._filtered_market_data_bars(normalized, params or [])
            descending = "order by as_of_date desc" in normalized or "order by b.as_of_date desc" in normalized
            bars = sorted(bars, key=lambda item: (item["as_of_date"], item["data_id"]), reverse=descending)
            limit = int((params or [50])[-1] or 50)
            self._rows = [
                (
                    item["data_id"],
                    item["security_id"],
                    item["source_id"],
                    item["market"],
                    item["as_of_date"],
                    item["data_type"],
                    item["currency"],
                    item["open"],
                    item["high"],
                    item["low"],
                    item["close"],
                    item["adjusted_close"],
                    item["volume"],
                    item["amount"],
                    item["rights_tag"],
                    item["created_at"],
                )
                for item in bars[:limit]
            ]
        elif normalized.startswith("select collection"):
            rows = []
            for (collection, item_id), record in self.database.records.items():
                if "where collection <> 'market_data'" in normalized and collection == "market_data":
                    continue
                rows.append((collection, item_id, record["payload"], record["position"]))
            self._rows = sorted(rows, key=lambda item: (item[0], item[3] is None, item[3] or 0, item[1]))
        elif normalized.startswith("select payload from ai_quant.audit_log"):
            audit_rows = sorted(self.database.audit.values(), key=lambda item: (item["timestamp"], item["event_id"]))
            self._rows = [(item["payload"],) for item in audit_rows]
        elif normalized.startswith("delete from ai_quant.records where collection = %s and item_id = %s"):
            self.database.records.pop((params[0], params[1]), None)
            self._rows = []
        elif normalized.startswith("delete from ai_quant.records where collection = %s"):
            collection = params[0]
            self.database.records = {key: value for key, value in self.database.records.items() if key[0] != collection}
            self._rows = []
        elif normalized.startswith("delete from ai_quant.records"):
            self.database.records.clear()
            self._rows = []
        elif normalized.startswith("delete from ai_quant.audit_log where event_id = %s"):
            self.database.audit.pop(params[0], None)
            self._rows = []
        elif normalized.startswith("delete from ai_quant.audit_log"):
            self.database.audit.clear()
            self._rows = []
        elif normalized.startswith("insert into ai_quant.records"):
            collection, item_id, payload, position = params
            self.database.records[(collection, item_id)] = {
                "payload": json.loads(payload),
                "position": position,
            }
            self._rows = []
        elif normalized.startswith("insert into ai_quant.market_data_bars"):
            self._upsert_market_data_bar(params)
            self._rows = []
        elif normalized.startswith("with inserted_policy as") and "insert into ai_quant.market_data_bars" in normalized:
            self._upsert_market_data_bar_v2(params)
            self._rows = []
        elif normalized.startswith("insert into ai_quant.audit_log"):
            self.database.audit[params[0]] = {
                "event_id": params[0],
                "payload": json.loads(params[11]),
                "timestamp": params[12],
            }
            self._rows = []
        elif normalized.startswith("insert into ai_quant.schema_migrations"):
            self.database.baseline_schema_recorded = True
            self._rows = []
        else:
            if "create schema if not exists ai_quant" in normalized:
                self.database.schema_runs += 1
            self._rows = []

    def executemany(self, sql, params_list):
        for params in params_list:
            self.execute(sql, params)

    def _filtered_market_data_bars(self, normalized_sql, params):
        filter_params = list(params)
        if " limit %s" in normalized_sql and filter_params:
            filter_params = filter_params[:-1]
        names = []
        for name in ("security_id", "market", "source_id", "data_type"):
            if f"{name} = %s" in normalized_sql or f"b.{name} = %s" in normalized_sql:
                names.append(name)
        if "as_of_date >= %s::date" in normalized_sql or "b.as_of_date >= %s::date" in normalized_sql:
            names.append("start_date")
        if "as_of_date <= %s::date" in normalized_sql or "b.as_of_date <= %s::date" in normalized_sql:
            names.append("date_lte")
        filters = dict(zip(names, filter_params))
        rows = list(self.database.market_data_bars.values())
        for name in ("security_id", "market", "source_id", "data_type"):
            if name in filters:
                rows = [item for item in rows if item[name] == filters[name]]
        if "start_date" in filters:
            rows = [item for item in rows if item["as_of_date"] >= filters["start_date"]]
        if "date_lte" in filters:
            rows = [item for item in rows if item["as_of_date"] <= filters["date_lte"]]
        return rows

    def _upsert_market_data_bar(self, params):
        (
            security_id,
            source_id,
            data_type,
            as_of_date,
            market,
            currency,
            row_open,
            high,
            low,
            close,
            adjusted_close,
            volume,
            amount,
            data_id,
            rights_tag,
            payload,
            created_at,
        ) = params
        self.database.market_data_bars[(security_id, source_id, data_type, as_of_date)] = {
            "security_id": security_id,
            "source_id": source_id,
            "data_type": data_type,
            "as_of_date": as_of_date,
            "market": market,
            "currency": currency,
            "open": row_open,
            "high": high,
            "low": low,
            "close": close,
            "adjusted_close": adjusted_close,
            "volume": volume,
            "amount": amount,
            "data_id": data_id,
            "rights_tag": json.loads(rights_tag) if isinstance(rights_tag, str) else rights_tag,
            "payload": json.loads(payload) if isinstance(payload, str) else payload,
            "created_at": created_at,
        }

    def _upsert_market_data_bar_v2(self, params):
        (
            _policy_hash,
            rights_json,
            _resolved_policy_hash,
            _resolved_rights_json,
            security_id,
            source_id,
            data_type,
            as_of_date,
            market,
            currency,
            row_open,
            high,
            low,
            close,
            adjusted_close,
            volume,
            amount,
            data_id,
            _payload_key_mask,
            extra_payload,
            created_at,
        ) = params
        rights_tag = json.loads(rights_json) if isinstance(rights_json, str) else rights_json
        self.database.market_data_bars[(security_id, source_id, data_type, as_of_date)] = {
            "security_id": security_id,
            "source_id": source_id,
            "data_type": data_type,
            "as_of_date": as_of_date,
            "market": market,
            "currency": currency,
            "open": row_open,
            "high": high,
            "low": low,
            "close": close,
            "adjusted_close": adjusted_close,
            "volume": volume,
            "amount": amount,
            "data_id": data_id,
            "rights_tag": rights_tag,
            "payload": json.loads(extra_payload) if isinstance(extra_payload, str) else extra_payload,
            "created_at": created_at,
        }

    def fetchall(self):
        return list(self._rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None


class _FakePostgresConnection:
    def __init__(self, database):
        self.database = database
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return None

    def cursor(self):
        return _FakePostgresCursor(self.database)

    def close(self):
        self.closed = True


class _FakePostgresDatabase:
    def __init__(self):
        self.records = {}
        self.market_data_bars = {}
        self.audit = {}
        self.statements = []
        self.schema_runs = 0
        self.dsns = []
        self.baseline_schema_recorded = False

    def connect(self, dsn):
        self.dsns.append(dsn)
        return _FakePostgresConnection(self)


class _FakeSecSingleNameConnectors:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.body = (
            "Apple Inc. reported revenue growth while Services resilience, subscription activity, "
            "and installed-base engagement improved the company mix. Gross margin benefited from "
            "the services contribution and disciplined operating expenses.\n\n"
            "Risk factors include regulatory scrutiny, supply-chain concentration, component "
            "availability, foreign exchange volatility, and macro demand changes."
        )

    def fetch_sec_recent_filings(self, cik, *, user_agent, limit=10, document_types=None):
        if self.fail:
            raise RuntimeError("SEC outage")
        document_type = (document_types or ["10-K"])[0]
        return [
            ConnectorDocument(
                source_id="sec_edgar",
                source_type="regulatory",
                document_type=document_type,
                source_uri="https://www.sec.gov/Archives/edgar/data/320193/000032019324000123/a10-k.htm",
                language="en",
                title=f"Apple Inc. {document_type} filing",
                published_at="2026-05-14",
                metadata={
                    "cik": str(cik).lstrip("0") or "0",
                    "accession_no": "0000320193-24-000123",
                    "primary_doc": "a10-k.htm",
                },
            )
        ]

    def fetch_sec_document_body(self, source_uri, *, user_agent, max_bytes=2_000_000):
        if self.fail:
            raise RuntimeError("SEC body outage")
        return self.body[:max_bytes]


class SystemServiceTestBase(unittest.TestCase):
    def setUp(self) -> None:
        preserved_ai_quant_env = {key: value for key, value in os.environ.items() if key.startswith("AI_QUANT_")}
        for key in list(os.environ):
            if key.startswith("AI_QUANT_"):
                os.environ.pop(key, None)

        def _restore_ai_quant_env() -> None:
            for key in list(os.environ):
                if key.startswith("AI_QUANT_"):
                    os.environ.pop(key, None)
            os.environ.update(preserved_ai_quant_env)

        self.addCleanup(_restore_ai_quant_env)
        self.service = SystemService()
        self.service.document_parser = PaddleOCRParser(token="")
        self.router = ApiRouter(self.service)
        self.service.register_source(
            {
                "source_id": "src_sec",
                "source_type": "regulatory",
                "allowed_document_types": ["annual_report", "10-K", "10-Q", "8-K", "20-F", "6-K"],
                "rights_tag": {
                    "license_class": "public",
                    "training_allowed": False,
                    "redistribution_allowed": False,
                    "display_use": "allowed",
                    "non_display_use": "restricted",
                    "derived_data_use": "restricted",
                },
            },
            actor="risk",
        )
        self.service.register_issuer(
            {
                "issuer_id": "issuer_001",
                "legal_name": "Demo Corp",
                "market": ["A", "U"],
                "lei": "LEI-DEMO-001",
                "cik": "0000001",
                "country": "CN",
            },
            actor="platform",
        )
        self.service.register_security(
            {
                "security_id": "sec_001",
                "issuer_id": "issuer_001",
                "ticker": "DEMO",
                "figi": "FIGI-DEMO-001",
                "isin": "ISIN-DEMO-001",
                "exchange": "SSE",
                "currency": "CNY",
                "market": "A",
            },
            actor="platform",
        )

    def _use_temp_object_store(self) -> None:
        temp_dir = TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        self.service.object_store = LocalObjectStore(Path(temp_dir.name))

    def _assert_api_envelope(self, response, *, success: bool = True, status_code: int = 200) -> None:
        self.assertEqual(response.success, success, response.error)
        self.assertEqual(response.status_code, status_code)
        self.assertTrue(response.trace_id.startswith("trace_"))
        if success:
            self.assertIsNone(response.error)
            self.assertIsNotNone(response.data)
        else:
            self.assertIsNone(response.data)
            self.assertIsInstance(response.error, dict)
            self.assertIn("type", response.error)
