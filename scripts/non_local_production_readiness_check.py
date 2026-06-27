#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DOC_PATH = ROOT / "docs" / "non-local-production-readiness-package.md"

REQUIRED_PHRASES = [
    "Status: active",
    "Owner group: Governance, Security, and Compliance",
    "Related tasks: T-499",
    "local-first",
    "paper-only",
    "does not connect to real brokers",
    "does not place orders",
    "not production release evidence",
    "Deployment Mode Matrix",
    "Required Evidence Template",
    "API And Backend Boundary Checklist",
    "Release Gate Sequence",
    "AI_QUANT_DEPLOYMENT_MODE",
    "AI_QUANT_AUTH_MODE",
]

REQUIRED_EVIDENCE_FIELDS = [
    "auth_mode_review",
    "permission_red_team",
    "secret_governance",
    "backup_restore_drill",
    "source_authorization_audit",
    "artifact_inventory",
    "monitoring_alert_drill",
    "release_gate_result",
    "paper_only_boundary_review",
]

REQUIRED_MODES = ["Local personal", "Non-local staging", "Production"]
REJECTED_EVIDENCE_MARKERS = [
    "artifact://local-",
    "artifact://staging-local",
    "file://",
    "local://",
    "127.0.0.1",
]


def validate_document(path: Path = DOC_PATH) -> dict[str, Any]:
    failures: list[dict[str, Any]] = []
    if not path.exists():
        return {
            "ok": False,
            "status": "failed",
            "path": str(path.relative_to(ROOT)),
            "failure_count": 1,
            "failures": [{"check": "exists", "error": "document is missing"}],
        }
    text = path.read_text(encoding="utf-8")

    def expect(condition: bool, check: str, error: str, **extra: Any) -> None:
        if not condition:
            failures.append({"check": check, "error": error, **extra})

    for phrase in REQUIRED_PHRASES:
        expect(phrase in text, "required_phrase", "missing required phrase", phrase=phrase)
    for field in REQUIRED_EVIDENCE_FIELDS:
        expect(f"`{field}`" in text, "evidence_field", "missing required evidence field", field=field)
    for mode in REQUIRED_MODES:
        expect(mode in text, "deployment_mode", "missing deployment mode", mode=mode)
    for marker in REJECTED_EVIDENCE_MARKERS:
        pattern = re.escape(marker)
        occurrences = len(re.findall(pattern, text))
        expect(occurrences > 0, "rejected_marker_documented", "rejected evidence marker must be documented", marker=marker)
    expect(
        "x-role-header" in text.lower() and "token/JWT/OIDC".lower() in text.lower(),
        "auth_boundary",
        "document must contrast local header auth with non-local token/JWT/OIDC auth",
    )
    expect(
        "python3 scripts/production_release_gate.py" in text,
        "release_gate_command",
        "release gate command must be documented",
    )

    passed = not failures
    return {
        "ok": passed,
        "status": "passed" if passed else "failed",
        "path": str(path.relative_to(ROOT)),
        "evidence_field_count": len(REQUIRED_EVIDENCE_FIELDS),
        "failure_count": len(failures),
        "failures": failures,
    }


def main(argv: list[str] | None = None) -> int:
    argv = argv or sys.argv[1:]
    path = Path(argv[0]).resolve() if argv else DOC_PATH
    result = validate_document(path)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    return 0 if result["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
