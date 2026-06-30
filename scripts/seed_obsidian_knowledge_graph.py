from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT = ROOT / "artifacts" / "obsidian-knowledge-graph-seed.json"


def post_seed(base_url: str, *, timeout: float = 10.0) -> dict[str, Any]:
    request = Request(
        f"{base_url.rstrip('/')}/api/graph/seed/obsidian",
        data=b"{}",
        method="POST",
        headers={"Content-Type": "application/json", "X-Role": "data_engineer", "X-Actor": "obsidian_knowledge_graph_seed"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raw = exc.read().decode("utf-8")
        payload = json.loads(raw) if raw else {"success": False, "error": {"message": str(exc), "status": exc.code}}
        raise RuntimeError(json.dumps(payload, ensure_ascii=False, sort_keys=True)) from exc


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed local Obsidian-style knowledge graph sample network.")
    parser.add_argument("base_url", nargs="?", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    payload = post_seed(args.base_url, timeout=args.timeout)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
