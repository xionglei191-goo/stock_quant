from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = ROOT / "data" / "artifacts" / "ui-browser-acceptance"

VIEWPORTS = [
    {"name": "desktop", "window_size": "1440,1000", "min_width": 1000, "min_height": 700},
    {"name": "mobile", "window_size": "390,844", "min_width": 320, "min_height": 650},
]

REQUIRED_TEXT = [
    "公司情报与市场综合分析平台",
    "总览",
    "最新公司情报分析",
    "本地生产验收",
    "研报观点证据",
    "知识图谱",
    "图谱总览",
    "公司产业定位",
    "研究补全任务",
    "证据、事件与行情",
    "分析结论、模拟反馈与复盘",
    "图谱关系",
    "主体映射双时态",
    "SEC 单标的研究闭环",
    "披露原文问答",
    "热点扩散",
    "需要原文",
    "仅研究",
    "异常审批面板",
    "人工审批",
    "组合模拟审批",
    "仅模拟",
    "不连接券商",
]


def _chrome_binary(explicit: str = "") -> str:
    candidates = [explicit] if explicit else []
    candidates.extend(["google-chrome", "chromium", "chromium-browser"])
    for candidate in candidates:
        if not candidate:
            continue
        found = shutil.which(candidate)
        if found:
            return found
    raise RuntimeError("Chrome/Chromium executable not found")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _image_probe(path: Path, *, min_width: int, min_height: int) -> dict[str, Any]:
    with Image.open(path) as image:
        width, height = image.size
        colors = image.convert("RGB").getcolors(maxcolors=1_000_000)
    color_count = len(colors or [])
    return {
        "width": width,
        "height": height,
        "sha256": _sha256(path),
        "bytes": path.stat().st_size,
        "color_count": color_count,
        "nonblank": width >= min_width and height >= min_height and color_count > 10 and path.stat().st_size > 1000,
    }


def _run_chrome(chrome: str, args: list[str], *, timeout: float) -> subprocess.CompletedProcess[str]:
    command = [chrome, "--headless=new", "--no-sandbox", "--disable-gpu", "--hide-scrollbars", *args]
    return subprocess.run(command, text=True, capture_output=True, timeout=timeout, check=False)


def run_ui_browser_acceptance(
    base_url: str,
    *,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    chrome_bin: str = "",
    timeout: float = 20.0,
) -> dict[str, Any]:
    chrome = _chrome_binary(chrome_bin)
    output = Path(output_dir)
    output.mkdir(parents=True, exist_ok=True)
    ui_url = base_url.rstrip("/") + "/ui"

    dom_result = _run_chrome(chrome, ["--dump-dom", ui_url], timeout=timeout)
    dom = dom_result.stdout
    missing_text = [text for text in REQUIRED_TEXT if text not in dom]
    screenshots: list[dict[str, Any]] = []
    failures: list[dict[str, Any]] = []
    if dom_result.returncode != 0:
        failures.append({"check": "dom_load", "error": dom_result.stderr.strip() or f"exit={dom_result.returncode}"})
    if missing_text:
        failures.append({"check": "required_text", "missing": missing_text})

    for viewport in VIEWPORTS:
        path = output / f"ui-{viewport['name']}.png"
        result = _run_chrome(
            chrome,
            [
                f"--window-size={viewport['window_size']}",
                f"--screenshot={path}",
                ui_url,
            ],
            timeout=timeout,
        )
        row: dict[str, Any] = {
            "name": viewport["name"],
            "path": str(path),
            "chrome_exit_code": result.returncode,
        }
        if result.returncode != 0:
            row["error"] = result.stderr.strip()
            failures.append({"check": f"screenshot_{viewport['name']}", "error": row["error"] or f"exit={result.returncode}"})
        elif not path.exists():
            row["error"] = "screenshot file was not created"
            failures.append({"check": f"screenshot_{viewport['name']}", "error": row["error"]})
        else:
            probe = _image_probe(path, min_width=int(viewport["min_width"]), min_height=int(viewport["min_height"]))
            row.update(probe)
            if not probe["nonblank"]:
                failures.append({"check": f"screenshot_{viewport['name']}", "error": "screenshot is blank or too small", "probe": probe})
        screenshots.append(row)

    passed = not failures
    return {
        "status": "passed" if passed else "failed",
        "base_url": base_url,
        "ui_url": ui_url,
        "browser": chrome,
        "required_text": REQUIRED_TEXT,
        "missing_text": missing_text,
        "screenshots": screenshots,
        "failure_count": len(failures),
        "failures": failures,
        "evidence_uri": f"artifact://ui-browser-acceptance/{output.name}",
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run headless Chrome UI screenshot and browser acceptance.")
    parser.add_argument("base_url", nargs="?", default="http://127.0.0.1:8000")
    parser.add_argument("--output-dir", default=str(DEFAULT_OUTPUT_DIR))
    parser.add_argument("--chrome-bin", default="")
    parser.add_argument("--timeout", type=float, default=20.0)
    args = parser.parse_args()
    result = run_ui_browser_acceptance(args.base_url, output_dir=args.output_dir, chrome_bin=args.chrome_bin, timeout=args.timeout)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if result["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
