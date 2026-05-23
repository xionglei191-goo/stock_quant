from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.production_closure import load_manifest, validate_production_closure_manifest


def _atomic_write_text(path: str | Path, text: str) -> None:
    output_path = Path(path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = output_path.with_name(f".{output_path.name}.tmp")
    tmp_path.write_text(text, encoding="utf-8")
    tmp_path.replace(output_path)


def load_and_validate_production_closure_manifest(
    path: str | Path,
    *,
    require_reports: bool = True,
    require_launch_ready: bool = True,
) -> dict[str, Any]:
    manifest = load_manifest(path)
    return validate_production_closure_manifest(
        manifest,
        require_reports=require_reports,
        require_launch_ready=require_launch_ready,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a production closure manifest JSON offline.")
    parser.add_argument("manifest_json")
    parser.add_argument(
        "--skip-report-readiness",
        action="store_true",
        help="Do not require storage/security/observability/UI/deployment reports in the manifest.",
    )
    parser.add_argument(
        "--allow-template",
        action="store_true",
        help="Allow template manifests that are structurally valid but not ready_for_launch=true.",
    )
    parser.add_argument("--output", default="", help="Optional path to write the validation result JSON.")
    args = parser.parse_args()

    validation = load_and_validate_production_closure_manifest(
        args.manifest_json,
        require_reports=not args.skip_report_readiness,
        require_launch_ready=not args.allow_template,
    )
    rendered = json.dumps(validation, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output:
        _atomic_write_text(args.output, rendered + "\n")
    print(rendered)
    if not validation["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
