#!/usr/bin/env python3
"""Backfill evidence_ids from document Evidence into graph events, relationships, and viewpoints."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "knowledge-network-evidence-link-backfill.json"


def post_json(base_url: str, path: str, payload: dict[str, Any], *, timeout: float) -> dict[str, Any]:
    request = Request(
        f"{base_url.rstrip('/')}{path}",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        method="POST",
        headers={"Content-Type": "application/json", "X-Role": "analyst", "X-Actor": "knowledge_network_evidence_link_backfill"},
    )
    with urlopen(request, timeout=timeout) as response:
        envelope = json.loads(response.read().decode("utf-8"))
    if not envelope.get("success"):
        raise RuntimeError(json.dumps(envelope.get("error", envelope), ensure_ascii=False))
    return envelope["data"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", nargs="?", default="http://127.0.0.1:8000")
    parser.add_argument("--issuer-id", required=True)
    parser.add_argument("--security-id", default="")
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--execute", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args(argv)
    payload: dict[str, Any] = {
        "issuer_id": args.issuer_id,
        "limit": args.limit,
        "execute": args.execute,
    }
    if args.security_id:
        payload["security_id"] = args.security_id
    try:
        result = post_json(args.base_url, "/api/graph/knowledge-network/evidence-links/backfill", payload, timeout=args.timeout)
    except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
        print(f"knowledge-network evidence-link backfill failed: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
