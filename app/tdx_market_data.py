from __future__ import annotations

from pathlib import Path
import os
import re
import struct
from typing import Any, Callable, Mapping, Sequence

from .errors import ValidationError


DEFAULT_TDX_DUCKDB_PATH = "data/local/tdx/market_data.duckdb"
DEFAULT_TDX_VIPDOC_PATH = "data/local/tdx/vipdoc"


class TDXMarketDataAdapter:
    """Read-only adapter for the migrated TongDaXin DuckDB daily kline store."""

    def __init__(
        self,
        *,
        path: str | Path | None = None,
        connect: Callable[[str, bool], Any] | None = None,
    ):
        self.path = str(path or os.environ.get("AI_QUANT_TDX_DUCKDB_PATH") or DEFAULT_TDX_DUCKDB_PATH)
        self._connect_func = connect or self._default_connect

    def describe(self) -> dict[str, Any]:
        return {
            "provider": "tdx",
            "path": self.path,
            "configured": Path(self.path).exists(),
            "table": "daily_kline",
        }

    def summary(self) -> dict[str, Any]:
        rows = self._query(
            """
            SELECT
                COUNT(*) AS rows,
                COUNT(DISTINCT symbol) AS symbols,
                MIN(trade_date) AS start_date,
                MAX(trade_date) AS end_date
            FROM daily_kline
            """,
            (),
        )
        return rows[0] if rows else {"rows": 0, "symbols": 0, "start_date": "", "end_date": ""}

    def symbols(self, *, prefix: str = "", limit: int = 100) -> list[str]:
        limit = self._limit(limit)
        params: list[Any] = []
        where = ""
        if prefix:
            where = "WHERE symbol LIKE ?"
            params.append(f"{self._normalize_symbol(prefix)}%")
        rows = self._query(
            f"""
            SELECT symbol
            FROM daily_kline
            {where}
            GROUP BY symbol
            ORDER BY symbol
            LIMIT ?
            """,
            (*params, limit),
        )
        return [str(row["symbol"]) for row in rows]

    def query_daily(
        self,
        *,
        symbols: Sequence[str],
        start_date: str = "1900-01-01",
        end_date: str = "2099-12-31",
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        clean_symbols = [self._normalize_symbol(symbol) for symbol in symbols if self._normalize_symbol(symbol)]
        if not clean_symbols:
            raise ValidationError("TDX query requires at least one symbol")
        self._validate_date(start_date, "start_date")
        self._validate_date(end_date, "end_date")
        limit = self._limit(limit)
        placeholders = ",".join("?" for _ in clean_symbols)
        rows = self._query(
            f"""
            SELECT symbol, trade_date, open, close, high, low, volume, amount, turnover
            FROM daily_kline
            WHERE symbol IN ({placeholders})
              AND trade_date >= ?
              AND trade_date <= ?
            ORDER BY symbol ASC, trade_date ASC
            LIMIT ?
            """,
            (*clean_symbols, start_date, end_date, limit),
        )
        return rows

    def _query(self, sql: str, params: Sequence[Any]) -> list[dict[str, Any]]:
        path = Path(self.path)
        if not path.exists():
            raise ValidationError(f"TDX DuckDB file not found: {self.path}")
        connection = self._connect_func(self.path, True)
        try:
            cursor = connection.execute(sql, tuple(params))
            columns = [item[0] for item in cursor.description]
            return [dict(zip(columns, row)) for row in cursor.fetchall()]
        finally:
            connection.close()

    def _default_connect(self, path: str, read_only: bool) -> Any:
        try:
            import duckdb  # type: ignore[import-not-found]
        except ModuleNotFoundError as exc:  # pragma: no cover - optional runtime package
            raise ValidationError("TDX DuckDB adapter requires the optional duckdb package") from exc
        return duckdb.connect(path, read_only=read_only)

    def _normalize_symbol(self, value: str) -> str:
        symbol = str(value).strip().lower()
        symbol = re.sub(r"^(sh|sz|bj)", "", symbol)
        symbol = re.sub(r"\.(sh|sz|bj|ss|szse|sse)$", "", symbol)
        return re.sub(r"\D+", "", symbol)

    def _validate_date(self, value: str, field_name: str) -> None:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(value)):
            raise ValidationError(f"{field_name} must use YYYY-MM-DD")

    def _limit(self, value: int) -> int:
        return max(1, min(10000, int(value)))


class TDXVipdocAdapter:
    """Read TongDaXin vipdoc daily .day files as a local public/reference fallback."""

    RECORD_SIZE = 32

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
        symbol = re.sub(r"\.(sh|sz|bj|ss|szse|sse)$", "", symbol)
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
