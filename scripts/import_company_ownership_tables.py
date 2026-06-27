from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import re
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


DEFAULT_OUTPUT = Path("artifacts/company-ownership-table-import.json")


class ApiClient:
    def __init__(self, base_url: str, *, timeout: float = 120.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout

    def request(self, method: str, path: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        data = json.dumps(body or {}, ensure_ascii=False).encode("utf-8") if body is not None else None
        request = Request(
            f"{self.base_url}{path}",
            data=data,
            method=method,
            headers={"Content-Type": "application/json", "X-Role": "data_engineer", "X-Actor": "company_ownership_table_import"},
        )
        try:
            with urlopen(request, timeout=self.timeout) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raw = exc.read().decode("utf-8")
            payload = json.loads(raw) if raw else {"success": False, "error": {"message": str(exc)}}
        if not payload.get("success"):
            raise RuntimeError(f"{method} {path} failed: {payload}")
        return payload["data"]


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in str(value or "").split(",") if item.strip()]


def discover_files(root_path: str, *, patterns: list[str], scan_limit: int) -> list[str]:
    root = Path(root_path).expanduser()
    if scan_limit <= 0:
        return []
    discovered: list[str] = []
    seen: set[str] = set()
    for pattern in patterns:
        for path in sorted(root.rglob(pattern)):
            if not path.is_file():
                continue
            rel_path = str(path.relative_to(root))
            if rel_path in seen:
                continue
            seen.add(rel_path)
            discovered.append(rel_path)
            if len(discovered) >= scan_limit:
                return discovered
    return discovered


def infer_symbols_from_paths(file_paths: list[str]) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()
    for raw_path in file_paths:
        text = str(raw_path)
        candidates = re.findall(r"(?i)(?:^|[^A-Za-z0-9])(?:sh|sz|bj)?(\d{6})(?:\.(?:sh|sz|bj|ss|xshg|xshe))?(?=$|[^A-Za-z0-9])", text)
        candidates.extend(re.findall(r"(?<![A-Za-z0-9])([A-Z]{1,5})(?=[_\-\.\s/]|$)", text))
        for candidate in candidates:
            symbol = candidate.upper()
            if symbol and symbol not in {"CSV", "TSV", "TXT", "MD", "JSON"} and symbol not in seen:
                symbols.append(symbol)
                seen.add(symbol)
    return symbols


def load_manifest(path: str) -> dict[str, Any]:
    if not path:
        return {"files": [], "symbols": [], "issuer_ids": []}
    manifest_path = Path(path).expanduser()
    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    if isinstance(data, list):
        raw_files = data
        defaults: dict[str, Any] = {}
    elif isinstance(data, dict):
        raw_files = data.get("files", data.get("ownership_files", data.get("items", [])))
        defaults = dict(data.get("defaults", {})) if isinstance(data.get("defaults", {}), dict) else {}
    else:
        raise ValueError("ownership manifest must be a JSON object or array")
    if isinstance(raw_files, (str, dict)):
        raw_files = [raw_files]
    files: list[dict[str, Any]] = []
    symbols: list[str] = []
    issuer_ids: list[str] = []
    for raw_item in raw_files if isinstance(raw_files, list) else []:
        if isinstance(raw_item, str):
            item = {**defaults, "file_path": raw_item}
        elif isinstance(raw_item, dict):
            item = {**defaults, **raw_item}
        else:
            continue
        file_path = str(item.get("file_path", item.get("path", ""))).strip()
        if not file_path:
            continue
        item["file_path"] = file_path
        files.append(item)
        symbols.extend(str(symbol).strip() for symbol in item.get("symbols", []) or [] if str(symbol).strip())
        if item.get("symbol"):
            symbols.append(str(item["symbol"]).strip())
        issuer_ids.extend(str(issuer_id).strip() for issuer_id in item.get("issuer_ids", []) or [] if str(issuer_id).strip())
        if item.get("issuer_id"):
            issuer_ids.append(str(item["issuer_id"]).strip())
    return {
        "files": files,
        "symbols": list(dict.fromkeys(symbols)),
        "issuer_ids": list(dict.fromkeys(issuer_ids)),
    }


def build_manifest_template(
    *,
    root_path: str,
    file_paths: list[str],
    scan_patterns: list[str],
    scan_limit: int,
    infer_symbols: bool,
    default_source_id: str,
    default_source_table: str,
    default_kind: str,
) -> dict[str, Any]:
    discovered_files = discover_files(root_path, patterns=scan_patterns, scan_limit=scan_limit) if scan_patterns else []
    merged = list(dict.fromkeys([*file_paths, *discovered_files]))
    files: list[dict[str, Any]] = []
    for file_path in merged:
        inferred = infer_symbols_from_paths([file_path]) if infer_symbols else []
        files.append(
            {
                "file_path": file_path,
                "symbol": inferred[0] if inferred else "",
                "default_kind": default_kind,
                "source_id": default_source_id,
                "source_table": default_source_table or Path(file_path).stem,
            }
        )
    return {
        "schema_id": "company-ownership-table-manifest-v1",
        "generated_at": utc_iso(),
        "root_path": root_path,
        "defaults": {
            "default_kind": default_kind,
            "source_id": default_source_id,
            "source_table": default_source_table,
        },
        "files": files,
        "usage_boundary": "local_ownership_manifest_template_edit_before_execute_no_live_trading",
    }


def run_import(
    *,
    base_url: str,
    symbols: list[str],
    issuer_ids: list[str],
    root_path: str,
    file_paths: list[str],
    manifest_path: str,
    scan_patterns: list[str],
    scan_limit: int,
    infer_symbols: bool,
    relationship_limit: int,
    execute: bool,
    output: Path,
    extensions: list[str],
    file_limit: int,
    file_max_bytes: int,
    timeout: float,
) -> dict[str, Any]:
    manifest = load_manifest(manifest_path)
    discovered_files = discover_files(root_path, patterns=scan_patterns, scan_limit=scan_limit) if scan_patterns else []
    explicit_file_items: list[str | dict[str, Any]] = [*file_paths, *manifest["files"], *discovered_files]
    merged_file_paths: list[str | dict[str, Any]] = []
    seen_file_keys: set[str] = set()
    for item in explicit_file_items:
        key = str(item.get("file_path", item.get("path", "")) if isinstance(item, dict) else item)
        if not key or key in seen_file_keys:
            continue
        seen_file_keys.add(key)
        merged_file_paths.append(item)
    file_path_strings = [str(item.get("file_path", item.get("path", "")) if isinstance(item, dict) else item) for item in merged_file_paths]
    explicit_symbols = list(dict.fromkeys([*symbols, *manifest["symbols"]]))
    explicit_issuer_ids = list(dict.fromkeys([*issuer_ids, *manifest["issuer_ids"]]))
    inferred_symbols = infer_symbols_from_paths(file_path_strings) if infer_symbols and not explicit_symbols else []
    effective_symbols = explicit_symbols or inferred_symbols
    client = ApiClient(base_url, timeout=timeout)
    payload = {
        "symbols": effective_symbols,
        "issuer_ids": explicit_issuer_ids,
        "relationship_limit": relationship_limit,
        "include_listings": False,
        "include_institution_coverage": False,
        "include_disclosure_candidates": False,
        "include_structured_ownership": True,
        "ownership_root_path": root_path,
        "ownership_file_paths": merged_file_paths,
        "ownership_file_extensions": extensions,
        "ownership_file_limit": file_limit,
        "ownership_file_max_bytes": file_max_bytes,
        "execute": execute,
        "dry_run": not execute,
    }
    result = client.request("POST", "/api/company-database/relationships/build", payload)
    summary = {
        "generated_at": utc_iso(),
        "base_url": base_url,
        "execute": execute,
        "status": "passed",
        "symbols": effective_symbols,
        "explicit_symbols": explicit_symbols,
        "inferred_symbols": inferred_symbols,
        "issuer_ids": explicit_issuer_ids,
        "root_path": root_path,
        "file_count": len(merged_file_paths),
        "explicit_files": file_paths,
        "manifest_path": manifest_path,
        "manifest_file_count": len(manifest["files"]),
        "discovered_files": discovered_files,
        "scan_patterns": scan_patterns,
        "relationships_planned": result.get("relationships_planned", 0),
        "relationships_created": result.get("relationships_created", 0),
        "ownership_file_inputs": result.get("ownership_file_inputs", []),
        "companies": result.get("companies", []),
        "usage_boundary": "local_ownership_tables_to_review_required_company_relationship_candidates_no_live_trading",
        "result": result,
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Import explicit local ownership tables into company relationship candidates.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--symbols", default="", help="Comma-separated symbols such as DEMO,600000.")
    parser.add_argument("--issuer-ids", default="", help="Comma-separated issuer IDs.")
    parser.add_argument("--root-path", default=".", help="Root for relative ownership table paths.")
    parser.add_argument("--files", default="", help="Comma-separated local CSV/TSV/TXT/MD files.")
    parser.add_argument("--manifest", default="", help="Optional JSON manifest with files/ownership_files entries and per-file metadata.")
    parser.add_argument("--write-manifest-template", type=Path, default=None, help="Write a JSON manifest template from --files/--glob and exit without calling the API.")
    parser.add_argument("--default-source-id", default="local_structured_ownership", help="Default source_id for manifest template entries.")
    parser.add_argument("--default-source-table", default="", help="Default source_table for manifest template entries; file stem is used when empty.")
    parser.add_argument("--default-kind", default="shareholder", help="Default relationship kind for manifest template entries.")
    parser.add_argument("--scan-root", default="", help="Optional root to scan. Defaults to --root-path when --glob is set.")
    parser.add_argument("--glob", default="", help="Comma-separated glob patterns to discover ownership files, for example '*.csv,**/*ownership*.md'.")
    parser.add_argument("--infer-symbols-from-path", action=argparse.BooleanOptionalAction, default=True, help="Infer target symbols from file names when --symbols is empty.")
    parser.add_argument("--scan-limit", type=int, default=100)
    parser.add_argument("--relationship-limit", type=int, default=100)
    parser.add_argument("--extensions", default=".csv,.tsv,.txt,.md")
    parser.add_argument("--file-limit", type=int, default=20)
    parser.add_argument("--file-max-bytes", type=int, default=1_000_000)
    parser.add_argument("--execute", action="store_true", help="Write candidate relationships. Default is dry-run.")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()
    if args.write_manifest_template is not None:
        root_path = args.scan_root or args.root_path
        template = build_manifest_template(
            root_path=root_path,
            file_paths=_split_csv(args.files),
            scan_patterns=_split_csv(args.glob),
            scan_limit=args.scan_limit,
            infer_symbols=args.infer_symbols_from_path,
            default_source_id=args.default_source_id,
            default_source_table=args.default_source_table,
            default_kind=args.default_kind,
        )
        args.write_manifest_template.parent.mkdir(parents=True, exist_ok=True)
        args.write_manifest_template.write_text(json.dumps(template, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps(template, ensure_ascii=False, indent=2))
        return 0
    summary = run_import(
        base_url=args.base_url,
        symbols=_split_csv(args.symbols),
        issuer_ids=_split_csv(args.issuer_ids),
        root_path=args.scan_root or args.root_path,
        file_paths=_split_csv(args.files),
        manifest_path=args.manifest,
        scan_patterns=_split_csv(args.glob),
        scan_limit=args.scan_limit,
        infer_symbols=args.infer_symbols_from_path,
        relationship_limit=args.relationship_limit,
        execute=args.execute,
        output=args.output,
        extensions=_split_csv(args.extensions),
        file_limit=args.file_limit,
        file_max_bytes=args.file_max_bytes,
        timeout=args.timeout,
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
