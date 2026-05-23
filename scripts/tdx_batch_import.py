from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import sys
from typing import Any, Iterable, Mapping
import urllib.error
import urllib.request


DEFAULT_BASE_URL = "http://127.0.0.1:8000"


def normalize_symbol(value: str) -> str:
    raw = str(value).strip()
    if not raw:
        return ""
    upper = raw.upper()
    if upper.startswith(("SH", "SZ", "BJ")) and len(upper) >= 8:
        upper = upper[2:]
    if "." in upper:
        upper = upper.split(".", 1)[0]
    digits = re.sub(r"\D", "", upper)
    return digits[-6:] if len(digits) >= 6 else digits


def infer_exchange(symbol: str) -> str:
    clean = normalize_symbol(symbol)
    if clean.startswith(("60", "68", "90")):
        return "SSE"
    if clean.startswith(("00", "20", "30")):
        return "SZSE"
    if clean.startswith(("43", "83", "87", "92")):
        return "BSE"
    return "A"


def load_symbols(args: argparse.Namespace) -> list[str]:
    symbols: list[str] = []
    if args.symbols:
        symbols.extend(args.symbols.split(","))
    if args.symbol_file:
        path = Path(args.symbol_file)
        text = path.read_text(encoding="utf-8")
        if path.suffix.lower() == ".json":
            payload = json.loads(text)
            if isinstance(payload, dict):
                payload = payload.get("symbols", [])
            if not isinstance(payload, list):
                raise ValueError("JSON symbol file must be a list or an object with symbols")
            symbols.extend(str(item) for item in payload)
        else:
            symbols.extend(line.split(",", 1)[0] for line in text.splitlines() if line.strip() and not line.startswith("#"))
    if args.discover_from_tdx:
        symbols.extend(discover_tdx_symbols(args.discover_from_tdx, prefix=args.symbol_prefix, limit=args.discover_limit))
    clean = [normalize_symbol(item) for item in symbols]
    clean = [item for item in clean if item]
    if args.symbol_prefix:
        clean = [item for item in clean if item.startswith(args.symbol_prefix)]
    unique = list(dict.fromkeys(clean))
    if args.max_symbols:
        unique = unique[: args.max_symbols]
    return unique


def discover_tdx_symbols(path: str, *, prefix: str = "", limit: int = 100) -> list[str]:
    root = Path(path)
    if not root.exists():
        raise RuntimeError(f"TDX vipdoc path not found: {path}")
    symbols: list[str] = []
    for file_path in sorted(root.glob("**/*.day")):
        symbol = normalize_symbol(file_path.stem)
        if prefix and not symbol.startswith(prefix):
            continue
        symbols.append(symbol)
        if len(symbols) >= int(limit):
            break
    return list(dict.fromkeys(symbols))


def api_request(base_url: str, method: str, path: str, payload: Mapping[str, Any] | None = None, *, role: str = "data_engineer", timeout: int = 180) -> dict[str, Any]:
    body = json.dumps(payload or {}, ensure_ascii=False).encode("utf-8") if method != "GET" else None
    request = urllib.request.Request(
        base_url.rstrip("/") + path,
        data=body,
        headers={"Content-Type": "application/json", "X-Role": role},
        method=method,
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        text = exc.read().decode("utf-8", errors="replace")
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            payload = {"success": False, "error": {"type": "http_error", "message": text}}
        payload.setdefault("success", False)
        payload.setdefault("status_code", exc.code)
        return payload


def register_symbol(base_url: str, symbol: str, *, timeout: int) -> dict[str, Any]:
    issuer_id = f"issuer_{symbol}"
    security_id = f"sec_{symbol}"
    issuer_payload = {
        "issuer_id": issuer_id,
        "legal_name": symbol,
        "aliases": [symbol],
        "market": ["A"],
        "country": "CN",
    }
    security_payload = {
        "security_id": security_id,
        "issuer_id": issuer_id,
        "ticker": symbol,
        "exchange": infer_exchange(symbol),
        "currency": "CNY",
        "market": "A",
    }
    issuer = api_request(base_url, "POST", "/api/issuers", issuer_payload, timeout=timeout)
    security = api_request(base_url, "POST", "/api/securities", security_payload, timeout=timeout)
    return {
        "issuer_id": issuer_id,
        "security_id": security_id,
        "issuer_status": classify_write_status(issuer),
        "security_status": classify_write_status(security),
    }


def classify_write_status(response: Mapping[str, Any]) -> str:
    if response.get("success"):
        return "created"
    message = str((response.get("error") or {}).get("message", ""))
    if "already exists" in message:
        return "exists"
    return f"error:{message}"


def import_symbol(base_url: str, symbol: str, args: argparse.Namespace) -> dict[str, Any]:
    endpoint = "/api/market-data/tdx/preview" if args.dry_run else "/api/market-data/tdx/import"
    payload = {
        "symbols": [symbol],
        "security_map": {symbol: f"sec_{symbol}"},
        "start_date": args.start_date,
        "end_date": args.end_date,
        "limit": args.limit_per_symbol,
        "skip_existing": not args.no_skip_existing,
        "batch_id": f"tdx_batch_{symbol}_{args.start_date}_{args.end_date}",
    }
    response = api_request(args.base_url, "POST", endpoint, payload, timeout=args.timeout)
    data = response.get("data") or {}
    if args.dry_run:
        return {
            "symbol": symbol,
            "status": "previewed" if response.get("success") else "failed",
            "source_rows": data.get("count", 0),
            "created_count": 0,
            "skipped_count": 0,
            "failed_count": 0 if response.get("success") else 1,
            "error": "" if response.get("success") else str((response.get("error") or {}).get("message", "")),
        }
    return {
        "symbol": symbol,
        "status": "completed" if response.get("success") and int(data.get("failed_count", 0) or 0) == 0 else "partial_or_failed",
        "source_rows": int(data.get("source_rows", 0) or 0),
        "created_count": int(data.get("created_count", 0) or 0),
        "skipped_count": int(data.get("skipped_count", 0) or 0),
        "failed_count": int(data.get("failed_count", 0) or (0 if response.get("success") else 1)),
        "error": "" if response.get("success") else str((response.get("error") or {}).get("message", "")),
    }


def run_batch(args: argparse.Namespace) -> dict[str, Any]:
    symbols = load_symbols(args)
    if not symbols:
        raise ValueError("no symbols selected")
    started_at = datetime.now(timezone.utc).isoformat()
    registrations: list[dict[str, Any]] = []
    results: list[dict[str, Any]] = []
    for index, symbol in enumerate(symbols, start=1):
        if args.register_missing:
            registrations.append(register_symbol(args.base_url, symbol, timeout=args.timeout))
        row = import_symbol(args.base_url, symbol, args)
        results.append(row)
        print(
            f"[{index}/{len(symbols)}] {symbol} {row['status']} "
            f"source={row['source_rows']} created={row['created_count']} skipped={row['skipped_count']} failed={row['failed_count']}",
            flush=True,
        )
    totals = {
        "source_rows": sum(int(row["source_rows"]) for row in results),
        "created_count": sum(int(row["created_count"]) for row in results),
        "skipped_count": sum(int(row["skipped_count"]) for row in results),
        "failed_count": sum(int(row["failed_count"]) for row in results),
    }
    return {
        "started_at": started_at,
        "completed_at": datetime.now(timezone.utc).isoformat(),
        "base_url": args.base_url,
        "dry_run": args.dry_run,
        "symbol_count": len(symbols),
        "start_date": args.start_date,
        "end_date": args.end_date,
        "limit_per_symbol": args.limit_per_symbol,
        **totals,
        "registrations": registrations,
        "results": results,
    }


def write_json(path: str, payload: Mapping[str, Any]) -> None:
    if not path:
        return
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Batch TDX market-data import through the running AI Quant API.")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--symbols", default="", help="Comma-separated symbols.")
    parser.add_argument("--symbol-file", default="", help="Text/CSV/JSON file with symbols.")
    parser.add_argument("--discover-from-tdx", default="", help="Optional local TDX vipdoc path to discover symbols from .day files.")
    parser.add_argument("--symbol-prefix", default="", help="Optional symbol prefix filter.")
    parser.add_argument("--discover-limit", type=int, default=100)
    parser.add_argument("--max-symbols", type=int, default=0)
    parser.add_argument("--start-date", default="2026-03-25")
    parser.add_argument("--end-date", default="2099-12-31")
    parser.add_argument("--limit-per-symbol", type=int, default=5)
    parser.add_argument("--register-missing", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--no-skip-existing", action="store_true")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--output", default="artifacts/tdx-batch-import.json")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        summary = run_batch(args)
    except Exception as exc:
        print(f"tdx batch import failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    write_json(args.output, summary)
    print(json.dumps({key: summary[key] for key in ["symbol_count", "source_rows", "created_count", "skipped_count", "failed_count", "dry_run"]}, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    main()
