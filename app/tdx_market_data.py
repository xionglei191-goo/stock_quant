from __future__ import annotations

from pathlib import Path
import os
import re
from typing import Any, Callable, Mapping, Sequence

from .errors import ValidationError


DEFAULT_TDX_DUCKDB_PATH = "data/local/tdx/market_data.duckdb"


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
