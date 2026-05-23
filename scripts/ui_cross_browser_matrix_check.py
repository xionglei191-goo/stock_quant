from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


REQUIRED_VIEWPORTS = {"desktop", "mobile"}
DEFAULT_REQUIRED_BROWSER_FAMILY_COUNT = 2


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() not in {"", "0", "false", "no", "off", "failed", "fail"}
    return bool(value)


def _as_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str):
        return [item.strip() for item in re.split(r"[\n,]+", value) if item.strip()]
    return []


def _browser_family(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return ""
    if "firefox" in text:
        return "firefox"
    if "webkit" in text:
        return "webkit"
    if "safari" in text:
        return "safari"
    if "edge" in text:
        return "edge"
    if "chrome" in text or "chromium" in text:
        return "chromium"
    return re.sub(r"[^a-z0-9]+", "_", text).strip("_")[:48]


def _matrix_rows(matrix: dict[str, Any]) -> list[dict[str, Any]]:
    raw_matrix = matrix.get("browser_matrix", matrix.get("cross_browser_matrix", []))
    if isinstance(raw_matrix, dict):
        raw_rows = raw_matrix.get("rows", raw_matrix.get("browsers", raw_matrix.get("matrix", [])))
    else:
        raw_rows = raw_matrix
    return [dict(item) for item in raw_rows if isinstance(item, dict)] if isinstance(raw_rows, list) else []


def validate_cross_browser_matrix(
    matrix: dict[str, Any],
    *,
    required_browser_family_count: int = DEFAULT_REQUIRED_BROWSER_FAMILY_COUNT,
    required_viewports: set[str] | None = None,
) -> dict[str, Any]:
    required_viewports = required_viewports or REQUIRED_VIEWPORTS
    rows = _matrix_rows(matrix)
    families = {_browser_family(item) for item in _as_list(matrix.get("browsers_checked", matrix.get("browser_families", [])))}
    viewports = {str(item).strip().lower() for item in _as_list(matrix.get("viewports_checked", matrix.get("viewport_names", [])))}
    failures: list[dict[str, Any]] = []
    for idx, row in enumerate(rows):
        family = _browser_family(row.get("browser", row.get("browser_family", row.get("engine", ""))))
        viewport = str(row.get("viewport", row.get("viewport_name", row.get("name", "")))).strip().lower()
        status = str(row.get("status", "passed")).strip().lower()
        if family:
            families.add(family)
        if viewport:
            viewports.add(viewport)
        if not family:
            failures.append({"row": idx, "check": "browser_family", "error": "missing browser/browser_family/engine"})
        if not viewport:
            failures.append({"row": idx, "check": "viewport", "error": "missing viewport"})
        if status not in {"", "pass", "passed", "ok", "success"} or _truthy(row.get("passed", True)) is False:
            failures.append({"row": idx, "check": "row_status", "error": f"status={status or row.get('passed')}"})

    missing_text = [str(item) for item in _as_list(matrix.get("missing_text", []))]
    required_text = [str(item) for item in _as_list(matrix.get("required_text", []))]
    failure_count = int(matrix.get("failure_count", len(_as_list(matrix.get("failures", [])))) or 0)
    missing_viewports = sorted(required_viewports - viewports)
    missing_browser_family_count = max(0, required_browser_family_count - len({item for item in families if item}))

    if not rows and not families:
        failures.append({"check": "matrix_rows", "error": "no browser matrix rows or browsers_checked values"})
    if missing_browser_family_count:
        failures.append({"check": "browser_family_count", "error": f"need {required_browser_family_count}, got {len(families)}"})
    if missing_viewports:
        failures.append({"check": "required_viewports", "missing": missing_viewports})
    if missing_text:
        failures.append({"check": "required_text", "missing": missing_text})
    if not required_text:
        failures.append({"check": "required_text", "error": "required_text field missing or empty"})
    if failure_count:
        failures.append({"check": "failure_count", "error": f"failure_count={failure_count}"})

    passed = not failures
    return {
        "status": "passed" if passed else "failed",
        "passed": passed,
        "browser_matrix_count": len(rows),
        "browser_families": sorted(item for item in families if item),
        "required_browser_family_count": required_browser_family_count,
        "missing_browser_family_count": missing_browser_family_count,
        "viewports": sorted(item for item in viewports if item),
        "required_viewports": sorted(required_viewports),
        "missing_viewports": missing_viewports,
        "required_text_count": len(required_text),
        "missing_text": missing_text,
        "failure_count": failure_count,
        "failures": failures,
    }


def load_and_validate_cross_browser_matrix(
    path: str | Path,
    *,
    required_browser_family_count: int = DEFAULT_REQUIRED_BROWSER_FAMILY_COUNT,
) -> dict[str, Any]:
    matrix_path = Path(path)
    data = json.loads(matrix_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise AssertionError("cross-browser matrix must be a JSON object")
    validation = validate_cross_browser_matrix(data, required_browser_family_count=required_browser_family_count)
    return {**data, "validation": validation}


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate a real cross-browser UI acceptance matrix JSON.")
    parser.add_argument("matrix_json")
    parser.add_argument("--required-browser-family-count", type=int, default=DEFAULT_REQUIRED_BROWSER_FAMILY_COUNT)
    args = parser.parse_args()
    result = load_and_validate_cross_browser_matrix(
        args.matrix_json,
        required_browser_family_count=args.required_browser_family_count,
    )
    print(json.dumps(result["validation"], ensure_ascii=False, indent=2, sort_keys=True))
    if not result["validation"]["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
