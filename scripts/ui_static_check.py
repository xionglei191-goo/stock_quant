from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HTML_PATH = ROOT / "app" / "static" / "index.html"

REQUIRED_NAV_LABELS = [
    "总览",
    "数据中台",
    "研究工作台",
    "Agent 协作",
    "策略实验室",
    "投委会",
    "风控合规",
    "CEO 看板",
    "知识图谱",
    "系统治理",
]

REQUIRED_STATUS_LABELS = [
    "A股",
    "港股",
    "美股",
    "研究中",
    "风险正常",
    "3 条冲突证据",
    "2 条高优先级事件",
]

REQUIRED_IDS = [
    "metrics",
    "marketRows",
    "crowding",
    "eventWall",
    "riskRows",
    "graphIssuer",
    "sysHealth",
    "issuerBox",
    "securityRows",
    "researchRows",
    "documentRows",
    "searchRows",
    "promptChangeRows",
    "llmRuns",
    "llmErrorRate",
    "llmCost",
    "llmBudgetUsed",
    "permissionAllowed",
    "permissionDenied",
    "permissionRedAllowed",
    "permissionRuleCount",
    "permissionDomainCount",
    "permissionRows",
    "decisionBox",
    "intentBox",
    "replayCompareRows",
    "replayCompareCount",
    "replayVarianceCount",
    "replayLatestId",
    "replayReviewCount",
    "replayContinueCount",
    "marketDataRows",
    "manualReferenceRows",
    "holdingRows",
    "extractionBox",
    "scheduleBox",
    "playbooksBox",
    "reportsBox",
    "schedulesBox",
    "sourceReviewRows",
    "sourceReviewOwnerRows",
    "sourceReviewNotificationRows",
]

REQUIRED_JS_FUNCTIONS = [
    "loadDashboard",
    "seedDemo",
    "loadEntity",
    "createPromptChange",
    "approvePromptChange",
    "loadPromptChanges",
    "loadPermissionMatrix",
    "runSearch",
    "loadDecision",
    "loadIntent",
    "compareReplays",
    "addMarketData",
    "loadMarketData",
    "createManualReference",
    "loadManualReferences",
    "add13fHolding",
    "update13fCrowding",
    "load13fHoldings",
    "runExtraction",
    "createSchedule",
    "runSchedules",
    "loadIncidents",
    "loadSourceReviews",
    "notifySourceReviews",
]


def validate_ui_html(path: str | Path = HTML_PATH, *, run_node: bool = True) -> dict[str, object]:
    html_path = Path(path)
    html = html_path.read_text(encoding="utf-8")
    missing_nav = [label for label in REQUIRED_NAV_LABELS if label not in html]
    missing_status = [label for label in REQUIRED_STATUS_LABELS if label not in html]
    missing_ids = [item_id for item_id in REQUIRED_IDS if f'id="{item_id}"' not in html]
    missing_functions = [name for name in REQUIRED_JS_FUNCTIONS if f"function {name}(" not in html and f"async function {name}(" not in html]
    failures = {
        "nav": missing_nav,
        "status": missing_status,
        "ids": missing_ids,
        "functions": missing_functions,
    }
    script_check = "skipped"
    if run_node and shutil.which("node"):
        script = _extract_script(html)
        script_path = html_path.with_suffix(".ui-check.js")
        try:
            script_path.write_text(script, encoding="utf-8")
            subprocess.run(["node", "--check", str(script_path)], check=True, capture_output=True, text=True)
            script_check = "passed"
        finally:
            script_path.unlink(missing_ok=True)
    if any(failures.values()):
        raise AssertionError(json.dumps(failures, ensure_ascii=False, sort_keys=True))
    return {
        "path": str(html_path),
        "nav_labels": len(REQUIRED_NAV_LABELS),
        "status_labels": len(REQUIRED_STATUS_LABELS),
        "required_ids": len(REQUIRED_IDS),
        "required_functions": len(REQUIRED_JS_FUNCTIONS),
        "node_check": script_check,
    }


def _extract_script(html: str) -> str:
    start = html.index("<script>") + len("<script>")
    end = html.index("</script>", start)
    return html[start:end]


def main() -> None:
    print(json.dumps(validate_ui_html(), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
