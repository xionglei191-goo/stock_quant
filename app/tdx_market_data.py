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
            "table": "auto",
        }

    def summary(self) -> dict[str, Any]:
        schema = self._detect_schema()
        rows = self._query(
            f"""
            SELECT
                COUNT(*) AS rows,
                COUNT(DISTINCT {schema['symbol']}) AS symbols,
                MIN({schema['date']}) AS start_date,
                MAX({schema['date']}) AS end_date
            FROM {schema['table']}
            """,
            (),
        )
        result = rows[0] if rows else {"rows": 0, "symbols": 0, "start_date": "", "end_date": ""}
        result["schema"] = schema
        return result

    def symbols(self, *, prefix: str = "", limit: int = 100) -> list[str]:
        schema = self._detect_schema()
        limit = self._limit(limit)
        params: list[Any] = []
        where = ""
        if prefix:
            where = f"WHERE {schema['symbol']} LIKE ?"
            params.append(f"{self._normalize_symbol(prefix)}%")
        rows = self._query(
            f"""
            SELECT {schema['symbol']} AS symbol
            FROM {schema['table']}
            {where}
            GROUP BY {schema['symbol']}
            ORDER BY {schema['symbol']}
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
        schema = self._detect_schema()
        limit = self._limit(limit)
        symbol_variants = self._symbol_variants(clean_symbols)
        placeholders = ",".join("?" for _ in symbol_variants)
        date_expr = schema["date"]
        rows = self._query(
            f"""
            SELECT
                {schema['symbol']} AS symbol,
                {date_expr} AS trade_date,
                {schema['open']} AS open,
                {schema['close']} AS close,
                {schema['high']} AS high,
                {schema['low']} AS low,
                {schema['volume']} AS volume,
                {schema['amount']} AS amount,
                {schema['turnover']} AS turnover
            FROM {schema['table']}
            WHERE {schema['symbol']} IN ({placeholders})
              AND {date_expr} >= ?
              AND {date_expr} <= ?
            ORDER BY {schema['symbol']} ASC, {date_expr} ASC
            LIMIT ?
            """,
            (*symbol_variants, start_date, end_date, limit),
        )
        return [self._normalize_row(row) for row in rows]

    def _detect_schema(self) -> dict[str, str]:
        try:
            tables = self._query(
                """
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema NOT IN ('information_schema', 'pg_catalog')
                ORDER BY CASE WHEN table_name = 'daily_kline' THEN 0 ELSE 1 END, table_name
                """,
                (),
            )
            candidates = [str(row["table_name"]) for row in tables]
        except Exception:
            rows = self._query("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY CASE WHEN name = 'daily_kline' THEN 0 ELSE 1 END, name", ())
            candidates = [str(row["name"]) for row in rows]
        if not candidates:
            raise ValidationError("TDX DuckDB file does not contain user tables")
        for table in candidates:
            columns = self._table_columns(table)
            try:
                return self._schema_for_table(table, columns)
            except ValidationError:
                continue
        raise ValidationError(f"TDX DuckDB schema not recognized in tables: {', '.join(candidates[:10])}")

    def _table_columns(self, table: str) -> list[str]:
        try:
            rows = self._query(
                """
                SELECT column_name
                FROM information_schema.columns
                WHERE table_name = ?
                ORDER BY ordinal_position
                """,
                (table,),
            )
            return [str(row["column_name"]) for row in rows]
        except Exception:
            rows = self._query(f"PRAGMA table_info({self._quote_identifier(table)})", ())
            return [str(row["name"]) for row in rows]

    def _schema_for_table(self, table: str, columns: Sequence[str]) -> dict[str, str]:
        lowered = {column.lower(): column for column in columns}
        symbol = self._column(lowered, "symbol", "code", "ticker", "ts_code", "security_code", "stock_code")
        date = self._column(lowered, "trade_date", "date", "datetime", "time", "交易日期")
        open_col = self._column(lowered, "open", "open_price", "开盘", "开盘价")
        close_col = self._column(lowered, "close", "close_price", "收盘", "收盘价")
        high_col = self._column(lowered, "high", "high_price", "最高", "最高价")
        low_col = self._column(lowered, "low", "low_price", "最低", "最低价")
        volume = self._column(lowered, "volume", "vol", "成交量", required=False) or "0"
        amount = self._column(lowered, "amount", "amt", "成交额", required=False) or "0"
        turnover = self._column(lowered, "turnover", "turnover_rate", "换手率", required=False) or "NULL"
        return {
            "table": self._quote_identifier(table),
            "raw_table": table,
            "symbol": self._normalize_symbol_sql(symbol),
            "raw_symbol": symbol,
            "date": self._normalize_date_sql(date),
            "raw_date": date,
            "open": self._numeric_sql(open_col),
            "close": self._numeric_sql(close_col),
            "high": self._numeric_sql(high_col),
            "low": self._numeric_sql(low_col),
            "volume": self._numeric_sql(volume),
            "amount": self._numeric_sql(amount),
            "turnover": self._numeric_sql(turnover, nullable=True),
        }

    def _column(self, columns: Mapping[str, str], *names: str, required: bool = True) -> str:
        for name in names:
            if name.lower() in columns:
                return self._quote_identifier(columns[name.lower()])
        if required:
            raise ValidationError(f"TDX DuckDB schema missing required column, expected one of: {', '.join(names)}")
        return ""

    def _quote_identifier(self, value: str) -> str:
        return '"' + str(value).replace('"', '""') + '"'

    def _normalize_symbol_sql(self, column: str) -> str:
        raw = f"lower(CAST({column} AS VARCHAR))"
        return (
            "replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace(replace("
            f"{raw}, 'xshg', ''), 'xshe', ''), 'xbei', ''), 'szse', ''), 'sse', ''), "
            "'shg', ''), 'sze', ''), 'ss', ''), 'sh', ''), 'sz', ''), 'bj', ''), '.', '')"
        )

    def _normalize_date_sql(self, column: str) -> str:
        raw = f"CAST({column} AS VARCHAR)"
        digits = f"replace(replace(replace(substr({raw}, 1, 10), '-', ''), '/', ''), '.', '')"
        return f"CASE WHEN length({digits}) = 8 THEN substr({digits}, 1, 4) || '-' || substr({digits}, 5, 2) || '-' || substr({digits}, 7, 2) ELSE substr({raw}, 1, 10) END"

    def _numeric_sql(self, column: str, *, nullable: bool = False) -> str:
        if not column:
            return "NULL" if nullable else "0"
        return f"CAST({column} AS DOUBLE)"

    def _normalize_row(self, row: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "symbol": self._normalize_symbol(str(row.get("symbol", ""))),
            "trade_date": str(row.get("trade_date", ""))[:10],
            "open": float(row.get("open") or 0.0),
            "close": float(row.get("close") or 0.0),
            "high": float(row.get("high") or 0.0),
            "low": float(row.get("low") or 0.0),
            "volume": float(row.get("volume") or 0.0),
            "amount": float(row.get("amount") or 0.0),
            "turnover": None if row.get("turnover") is None else float(row.get("turnover") or 0.0),
        }

    def _symbol_variants(self, symbols: Sequence[str]) -> list[str]:
        variants: list[str] = []
        for symbol in symbols:
            clean = self._normalize_symbol(symbol)
            if not clean:
                continue
            market_prefixes = ["sh"] if clean.startswith(("5", "6", "9")) else ["sz"] if clean.startswith(("0", "2", "3")) else ["bj"] if clean.startswith(("4", "8")) else ["sh", "sz", "bj"]
            values = [clean, clean.upper()]
            for prefix in market_prefixes:
                values.extend(
                    [
                        f"{prefix}{clean}",
                        f"{prefix.upper()}{clean}",
                        f"{clean}.{prefix}",
                        f"{clean}.{prefix.upper()}",
                    ]
                )
            if "sh" in market_prefixes:
                values.extend([f"{clean}.SS", f"{clean}.SHG", f"{clean}.XSHG"])
            if "sz" in market_prefixes:
                values.extend([f"{clean}.SZE", f"{clean}.XSHE"])
            if "bj" in market_prefixes:
                values.extend([f"{clean}.XBEI"])
            variants.extend(values)
        return list(dict.fromkeys(variants))

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
