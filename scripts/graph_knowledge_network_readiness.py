#!/usr/bin/env python3
"""Fetch the local knowledge-network readiness report and save it as evidence."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "graph-knowledge-network-readiness.json"


def fetch_report(base_url: str, payload: dict[str, object], timeout: float) -> dict[str, object]:
    request = Request(
        f"{base_url.rstrip('/')}/api/graph/knowledge-network/readiness",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Role": "analyst", "X-Actor": "graph_knowledge_network_readiness"},
        method="POST",
    )
    with urlopen(request, timeout=timeout) as response:
        envelope = json.loads(response.read().decode("utf-8"))
    if not envelope.get("success"):
        raise RuntimeError(json.dumps(envelope.get("error", envelope), ensure_ascii=False))
    return envelope


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("base_url", nargs="?", default="http://127.0.0.1:8000")
    parser.add_argument("--issuer-id", default="")
    parser.add_argument("--security-id", default="")
    parser.add_argument("--min-layers", type=int, default=7)
    parser.add_argument("--min-edges", type=int, default=20)
    parser.add_argument("--min-communities", type=int, default=4)
    parser.add_argument("--record-readiness", action="store_true")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)
    payload: dict[str, object] = {
        "min_layers": args.min_layers,
        "min_edges": args.min_edges,
        "min_communities": args.min_communities,
        "record_readiness": args.record_readiness,
    }
    if args.issuer_id:
        payload["issuer_id"] = args.issuer_id
    if args.security_id:
        payload["security_id"] = args.security_id
    try:
        envelope = fetch_report(args.base_url, payload, args.timeout)
    except (HTTPError, URLError, TimeoutError, RuntimeError) as exc:
        print(f"graph knowledge-network readiness failed: {exc}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(envelope, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(envelope["data"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
