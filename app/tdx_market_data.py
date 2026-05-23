from __future__ import annotations

from pathlib import Path
import os
import re
import struct
from typing import Any, Mapping, Sequence

from .errors import ValidationError


DEFAULT_TDX_VIPDOC_PATH = "data/local/tdx/vipdoc"


class TDXVipdocAdapter:
    """Read TongDaXin vipdoc daily .day files as the local public EOD source."""

    RECORD_SIZE = 32
    TARGET_FIELDS = ("security_id", "as_of_date", "open", "high", "low", "close", "adjusted_close", "volume")

    def __init__(self, *, path: str | Path | None = None):
        self.path = str(path or os.environ.get("AI_QUANT_TDX_VIPDOC_PATH") or DEFAULT_TDX_VIPDOC_PATH)

    def describe(self) -> dict[str, Any]:
        root = Path(self.path)
        return {
            "provider": "tdx_vipdoc",
            "path": self.path,
            "configured": root.exists(),
            "format": "vipdoc_day",
        }

    def summary(self) -> dict[str, Any]:
        root = Path(self.path)
        if not root.exists():
            raise ValidationError(f"TDX vipdoc directory not found: {self.path}")
        files = list(root.glob("**/*.day"))
        return {"files": len(files), "path": self.path, "format": "vipdoc_day"}

    def symbols(self, *, prefix: str = "", limit: int = 100) -> list[str]:
        root = Path(self.path)
        if not root.exists():
            raise ValidationError(f"TDX vipdoc directory not found: {self.path}")
        clean_prefix = self._normalize_symbol(prefix)
        rows: list[str] = []
        for file_path in sorted(root.glob("**/*.day")):
            symbol = self._normalize_symbol(file_path.stem)
            if clean_prefix and not symbol.startswith(clean_prefix):
                continue
            rows.append(symbol)
            if len(rows) >= self._limit(limit):
                break
        return list(dict.fromkeys(rows))

    def schema_coverage_report(self, *, schema_samples: Sequence[dict[str, Any]] | None = None, sample_limit: int = 50) -> dict[str, Any]:
        root = Path(self.path)
        if schema_samples is not None:
            rows = [self._schema_sample_report(sample) for sample in list(schema_samples)[: self._limit(sample_limit)]]
        else:
            files = list(root.glob("**/*.day"))[: self._limit(sample_limit)] if root.exists() else []
            rows = [self._day_file_schema_report(file_path) for file_path in files]
        recognized = [row for row in rows if row["recognized"]]
        return {
            "provider": "tdx_vipdoc",
            "path": self.path,
            "configured": root.exists(),
            "schema_count": len(rows),
            "recognized_schema_count": len(recognized),
            "schema_recognition_coverage": round(len(recognized) / max(1, len(rows)), 4) if rows else 0.0,
            "target_field_coverage": 1.0 if rows else 0.0,
            "required_schema_fields": ["symbol", "date", "open", "high", "low", "close"],
            "optional_schema_fields": ["volume", "amount", "turnover"],
            "target_fields": list(self.TARGET_FIELDS),
            "tables": rows,
            "anomaly_samples": [row for row in rows if row["anomalies"]],
        }

    def _day_file_schema_report(self, file_path: Path) -> dict[str, Any]:
        valid_record_length = file_path.stat().st_size % self.RECORD_SIZE == 0
        return {
            "table": str(file_path),
            "source": "vipdoc_day",
            "columns": ["date", "open", "high", "low", "close", "amount", "volume"],
            "recognized": valid_record_length,
            "raw_field_mapping": {
                "symbol": "file_name",
                "date": "record.date",
                "open": "record.open",
                "high": "record.high",
                "low": "record.low",
                "close": "record.close",
                "volume": "record.volume",
                "amount": "record.amount",
            },
            "target_field_mapping": {
                "security_id": "file_name",
                "as_of_date": "record.date",
                "open": "record.open",
                "high": "record.high",
                "low": "record.low",
                "close": "record.close",
                "adjusted_close": "record.close",
                "volume": "record.volume",
            },
            "target_fields": list(self.TARGET_FIELDS),
            "mapped_target_fields": list(self.TARGET_FIELDS),
            "missing_required_schema_fields": [],
            "missing_optional_schema_fields": ["turnover"],
            "unmapped_columns": [],
            "target_field_coverage": 1.0,
            "anomalies": [] if valid_record_length else [{"severity": "blocking", "issue": "invalid_record_length"}],
        }

    def _schema_sample_report(self, sample: Mapping[str, Any]) -> dict[str, Any]:
        columns = [str(column).strip().lower() for column in sample.get("columns", []) if str(column).strip()]
        required = {"date", "open", "high", "low", "close"}
        missing = sorted(required - set(columns))
        recognized = not missing
        mapped_target_fields = list(self.TARGET_FIELDS) if recognized else []
        return {
            "table": str(sample.get("table", "schema_sample")),
            "source": "schema_sample",
            "columns": columns,
            "recognized": recognized,
            "raw_field_mapping": {},
            "target_field_mapping": {},
            "target_fields": list(self.TARGET_FIELDS),
            "mapped_target_fields": mapped_target_fields,
            "missing_required_schema_fields": missing,
            "missing_optional_schema_fields": ["volume", "amount", "turnover"],
            "unmapped_columns": columns,
            "target_field_coverage": 1.0 if recognized else 0.0,
            "anomalies": [] if recognized else [{"severity": "blocking", "issue": "unrecognized_vipdoc_schema_sample", "missing_fields": missing}],
        }

    def query_daily(
        self,
        *,
        symbols: Sequence[str],
        start_date: str = "1900-01-01",
        end_date: str = "2099-12-31",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        self._validate_date(start_date, "start_date")
        self._validate_date(end_date, "end_date")
        limit = self._limit(limit)
        rows: list[dict[str, Any]] = []
        missing: list[str] = []
        for symbol in symbols:
            file_path = self._resolve_day_file(symbol)
            if file_path is None:
                missing.append(str(symbol))
                continue
            rows.extend(self._read_day_file(file_path, start_date=start_date, end_date=end_date, limit=max(0, limit - len(rows))))
            if len(rows) >= limit:
                break
        if not rows and missing:
            raise ValidationError(f"TDX vipdoc .day file not found for symbols: {', '.join(missing[:5])}")
        rows.sort(key=lambda item: (str(item["symbol"]), str(item["trade_date"])))
        return rows[:limit]

    def _read_day_file(self, file_path: Path, *, start_date: str, end_date: str, limit: int) -> list[dict[str, Any]]:
        if limit <= 0:
            return []
        data = file_path.read_bytes()
        if len(data) % self.RECORD_SIZE != 0:
            raise ValidationError(f"TDX vipdoc file has invalid record length: {file_path}")
        symbol = self._normalize_symbol(file_path.stem)
        rows: list[dict[str, Any]] = []
        for offset in range(0, len(data), self.RECORD_SIZE):
            raw_date, raw_open, raw_high, raw_low, raw_close, amount, volume, _reserved = struct.unpack("<IIIIIfII", data[offset : offset + self.RECORD_SIZE])
            trade_date = self._date_from_int(raw_date)
            if trade_date < start_date or trade_date > end_date:
                continue
            rows.append(
                {
                    "symbol": symbol,
                    "trade_date": trade_date,
                    "open": raw_open / 100.0,
                    "close": raw_close / 100.0,
                    "high": raw_high / 100.0,
                    "low": raw_low / 100.0,
                    "volume": float(volume),
                    "amount": float(amount),
                    "turnover": None,
                    "source_file": str(file_path),
                }
            )
            if len(rows) >= limit:
                break
        return rows

    def _resolve_day_file(self, symbol: str) -> Path | None:
        root = Path(self.path)
        if not root.exists():
            raise ValidationError(f"TDX vipdoc directory not found: {self.path}")
        normalized = self._normalize_symbol(symbol)
        prefixes = self._symbol_prefixes(symbol, normalized)
        candidates: list[Path] = []
        for prefix in prefixes:
            filename = f"{prefix}{normalized}.day"
            candidates.extend(
                [
                    root / prefix / "lday" / filename,
                    root / "vipdoc" / prefix / "lday" / filename,
                    root / filename,
                ]
            )
        for candidate in candidates:
            if candidate.exists():
                return candidate
        for candidate in root.glob(f"**/*{normalized}.day"):
            if candidate.is_file():
                return candidate
        return None

    def _symbol_prefixes(self, original: str, normalized: str) -> list[str]:
        lowered = str(original).strip().lower()
        if lowered.startswith(("sh", "sz", "bj")):
            return [lowered[:2]]
        if normalized.startswith(("5", "6", "9")):
            return ["sh", "sz", "bj"]
        if normalized.startswith(("0", "2", "3")):
            return ["sz", "sh", "bj"]
        if normalized.startswith(("4", "8")):
            return ["bj", "sh", "sz"]
        return ["sh", "sz", "bj"]

    def _normalize_symbol(self, value: str) -> str:
        symbol = str(value).strip().lower()
        symbol = re.sub(r"^(sh|sz|bj)", "", symbol)
        symbol = re.sub(r"\.(sh|sz|bj|ss|szse|sse|xshg|xshe|xbei)$", "", symbol)
        return re.sub(r"\D+", "", symbol)

    def _date_from_int(self, value: int) -> str:
        raw = str(value)
        if not re.fullmatch(r"\d{8}", raw):
            raise ValidationError(f"invalid TDX vipdoc trade date {value}")
        return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"

    def _validate_date(self, value: str, field_name: str) -> None:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value)):
            raise ValidationError(f"{field_name} must use YYYY-MM-DD")

    def _limit(self, value: int) -> int:
        return max(1, min(10000, int(value)))
