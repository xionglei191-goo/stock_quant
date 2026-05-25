from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any


DEFAULT_SERVICE_NAME = "ai-quant-daily-update.service"
DEFAULT_TIMER_NAME = "ai-quant-daily-update.timer"


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: str | Path, payload: dict[str, Any]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"status": "unreadable", "error": str(exc), "error_type": type(exc).__name__}
    return payload if isinstance(payload, dict) else {"status": "invalid", "error": "JSON root is not an object"}


def _artifact_json(path: str | Path, *, root: Path) -> dict[str, Any]:
    if not str(path or "").strip():
        return {"exists": False, "path": ""}
    artifact_path = Path(path)
    if not artifact_path.is_absolute():
        artifact_path = root / artifact_path
    if not artifact_path.exists():
        return {"exists": False, "path": str(artifact_path)}
    payload = _load_json(artifact_path)
    return {"exists": True, "path": str(artifact_path), "payload": payload}


def _artifact_summary(artifact: dict[str, Any]) -> dict[str, Any]:
    payload = artifact.get("payload") if isinstance(artifact.get("payload"), dict) else {}
    return {
        "exists": bool(artifact.get("exists")),
        "path": str(artifact.get("path") or ""),
        "status": str(payload.get("status") or ""),
        "has_analysis": isinstance(payload.get("analysis"), dict),
        "has_actionable_research_summary": isinstance(payload.get("actionable_research_summary"), dict),
    }


def _latest_pipeline_artifact(output_dir: Path) -> Path | None:
    pointer = output_dir / "latest-run.json"
    if pointer.exists():
        pointer_payload = _load_json(pointer)
        pointed = pointer_payload.get("pipeline_output")
        if isinstance(pointed, str) and pointed.strip():
            pointed_path = Path(pointed)
            if not pointed_path.is_absolute():
                pointed_path = output_dir.parent.parent / pointed_path if output_dir.name == "daily-update-local" else Path.cwd() / pointed_path
            if pointed_path.exists():
                return pointed_path
    candidates = [
        path
        for path in output_dir.rglob("daily-update-[0-9][0-9][0-9][0-9]-*.json")
        if path.name != "daily-update.json" and path.name != "latest-run.json"
        and "runner-smoke" not in path.parts
        and "date-strategy-smoke" not in path.parts
        and "us-db-pipeline-smoke" not in path.parts
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda path: path.stat().st_mtime)


def _systemctl_user_status(timer_name: str) -> dict[str, Any]:
    if not shutil.which("systemctl"):
        return {"checked": False, "available": False, "error": "systemctl_not_found"}

    def run(*args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(["systemctl", "--user", *args], text=True, capture_output=True, check=False, timeout=15)

    enabled = run("is-enabled", timer_name)
    active = run("is-active", timer_name)
    show = run(
        "show",
        timer_name,
        "--property=LoadState,ActiveState,UnitFileState,NextElapseUSecRealtime,LastTriggerUSecRealtime",
    )
    properties: dict[str, str] = {}
    if show.returncode == 0:
        for line in show.stdout.splitlines():
            if "=" in line:
                key, value = line.split("=", 1)
                properties[key] = value
    return {
        "checked": True,
        "available": enabled.returncode in {0, 1} or active.returncode in {0, 3},
        "is_enabled_returncode": enabled.returncode,
        "is_enabled": enabled.stdout.strip(),
        "is_enabled_stderr": enabled.stderr.strip(),
        "is_active_returncode": active.returncode,
        "is_active": active.stdout.strip(),
        "is_active_stderr": active.stderr.strip(),
        "properties": properties,
    }


def _gate(check: str, passed: bool, detail: str = "") -> dict[str, Any]:
    return {"check": check, "passed": passed, "detail": detail}


def build_daily_update_schedule_audit(
    *,
    repo_root: str | Path = ".",
    unit_dir: str | Path | None = None,
    output_dir: str | Path = "artifacts/daily-update-local",
    service_name: str = DEFAULT_SERVICE_NAME,
    timer_name: str = DEFAULT_TIMER_NAME,
    check_systemd: bool = True,
    require_enabled: bool = True,
    require_latest_run: bool = False,
) -> dict[str, Any]:
    root = Path(repo_root).resolve()
    units = Path(unit_dir).expanduser() if unit_dir else Path.home() / ".config" / "systemd" / "user"
    service_path = units / service_name
    timer_path = units / timer_name
    runner_path = root / "scripts" / "run_daily_data_update.sh"
    output_root = root / output_dir

    service_text = service_path.read_text(encoding="utf-8") if service_path.exists() else ""
    timer_text = timer_path.read_text(encoding="utf-8") if timer_path.exists() else ""
    latest_artifact = _latest_pipeline_artifact(output_root) if output_root.exists() else None
    latest_payload = _load_json(latest_artifact) if latest_artifact else {}
    latest_steps = latest_payload.get("steps") if isinstance(latest_payload.get("steps"), list) else []
    step_names = {str(step.get("name")) for step in latest_steps if isinstance(step, dict)}
    latest_status = latest_payload.get("status") if latest_payload else ""
    latest_artifacts = latest_payload.get("artifacts") if isinstance(latest_payload.get("artifacts"), dict) else {}
    latest_analysis = _artifact_json(latest_artifacts.get("latest_analysis", ""), root=root)
    latest_analysis_payload = latest_analysis.get("payload") if isinstance(latest_analysis.get("payload"), dict) else {}
    daily_insight = _artifact_json(latest_artifacts.get("daily-insight-json", ""), root=root)
    daily_insight_payload = daily_insight.get("payload") if isinstance(daily_insight.get("payload"), dict) else {}

    systemd_status = _systemctl_user_status(timer_name) if check_systemd else {"checked": False, "available": False, "skipped": True}
    enabled_state = str(systemd_status.get("is_enabled") or systemd_status.get("properties", {}).get("UnitFileState") or "")
    active_state = str(systemd_status.get("is_active") or systemd_status.get("properties", {}).get("ActiveState") or "")
    systemd_enabled_passed = not require_enabled or enabled_state in {"enabled", "active", "enabled-runtime"}
    systemd_active_passed = not require_enabled or active_state in {"active", "waiting"}

    gates = [
        _gate("runner_script_exists", runner_path.exists(), str(runner_path)),
        _gate("runner_script_executable", runner_path.exists() and bool(runner_path.stat().st_mode & 0o111), str(runner_path)),
        _gate("service_unit_exists", service_path.exists(), str(service_path)),
        _gate("timer_unit_exists", timer_path.exists(), str(timer_path)),
        _gate("service_uses_daily_runner", "scripts/run_daily_data_update.sh" in service_text, "ExecStart must call the repo daily runner"),
        _gate("service_uses_compose_runner", "AI_QUANT_DAILY_RUNNER=compose" in service_text, "Daily job should run inside the compose app container by default"),
        _gate("service_uses_user_writable_output_base", "AI_QUANT_DAILY_OUTPUT_BASE=artifacts/daily-update-local" in service_text, "Avoid root-owned legacy artifact directories"),
        _gate("service_runs_ashare_scope_refresh", "AI_QUANT_DAILY_RUN_ASHARE_SCOPE_REFRESH=true" in service_text, "A-share active universe scope should refresh before incremental imports"),
        _gate("service_runs_ashare_batches", "AI_QUANT_DAILY_RUN_ASHARE_INCREMENTAL=true" in service_text, "A-share baostock refresh must remain resumable"),
        _gate("service_runs_us_scope_refresh", "AI_QUANT_DAILY_RUN_US_SCOPE_REFRESH=true" in service_text, "US Yahoo refresh scope should classify common-equity active refresh records before imports"),
        _gate("service_runs_us_batches_from_db", "AI_QUANT_DAILY_US_TICKERS_FROM_DB=true" in service_text, "US Yahoo refresh must use the registered securities universe, not only default analysis tickers"),
        _gate("service_keeps_tdx_import_optional", "AI_QUANT_DAILY_TDX_INCREMENTAL=false" in service_text, "TDX is audited daily and imported only when explicitly enabled"),
        _gate("timer_has_calendar", "OnCalendar=" in timer_text, "Timer needs an explicit schedule"),
        _gate("timer_has_morning_and_evening_runs", timer_text.count("OnCalendar=") >= 2, "Timer should refresh after US close and after A-share close"),
        _gate("timer_is_persistent", "Persistent=true" in timer_text, "Persistent timers catch up after local machine downtime"),
    ]
    if check_systemd:
        gates.append(_gate("systemd_timer_enabled", systemd_enabled_passed, enabled_state or "unknown"))
        gates.append(_gate("systemd_timer_active", systemd_active_passed, active_state or "unknown"))
    if require_latest_run:
        gates.extend(
            [
                _gate("latest_pipeline_artifact_exists", latest_artifact is not None, str(latest_artifact or "")),
                _gate("latest_pipeline_passed", latest_status == "passed", str(latest_status or "not_found")),
                _gate("latest_pipeline_storage_audit", "market_data_storage_audit" in step_names, "market_data_storage_audit step required"),
                _gate("latest_pipeline_daily_insight", "daily_market_insight" in step_names, "daily_market_insight step required"),
                _gate("latest_analysis_artifact_shape", latest_analysis.get("exists") and isinstance(latest_analysis_payload.get("analysis"), dict), str(latest_analysis.get("path") or "")),
                _gate("daily_insight_artifact_shape", daily_insight.get("exists") and isinstance(daily_insight_payload.get("actionable_research_summary"), dict), str(daily_insight.get("path") or "")),
            ]
        )

    failed_gates = [gate for gate in gates if not gate["passed"]]
    return {
        "status": "passed" if not failed_gates else "failed",
        "passed": not failed_gates,
        "generated_at": _utc_now(),
        "production_boundary": "local_personal_production_daily_refresh_scheduler_no_live_broker_no_auto_order",
        "repo_root": str(root),
        "unit_dir": str(units),
        "service_name": service_name,
        "timer_name": timer_name,
        "service_path": str(service_path),
        "timer_path": str(timer_path),
        "output_dir": str(output_root),
        "latest_pipeline_artifact": str(latest_artifact) if latest_artifact else "",
        "latest_pipeline_status": latest_status,
        "latest_analysis_artifact": _artifact_summary(latest_analysis),
        "daily_insight_artifact": _artifact_summary(daily_insight),
        "systemd": systemd_status,
        "gates": gates,
        "failure_count": len(failed_gates),
        "failed_gates": failed_gates,
        "notes": [
            "The daily runner uses scripts/daily_data_update_pipeline.py and typed ai_quant.market_data_bars K-line storage.",
            "A-share baostock and US Yahoo refreshes advance through the local security universe with offsets in the state file; A-share scope is refreshed from the current baostock active directory and US Yahoo scope keeps one active common-equity refresh record per ticker; TDX local files are audited before any optional import.",
            "This is local personal production automation only; live broker execution remains outside the pipeline.",
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit the local personal-production daily update systemd timer and latest run artifact.")
    parser.add_argument("--repo-root", default=".")
    parser.add_argument("--unit-dir", default="")
    parser.add_argument("--output-dir", default="artifacts/daily-update-local")
    parser.add_argument("--service-name", default=DEFAULT_SERVICE_NAME)
    parser.add_argument("--timer-name", default=DEFAULT_TIMER_NAME)
    parser.add_argument("--skip-systemd", action="store_true")
    parser.add_argument("--allow-installed-only", action="store_true", help="Do not require the systemd timer to be enabled/active.")
    parser.add_argument("--require-latest-run", action="store_true")
    parser.add_argument("--output", default="artifacts/daily-update/daily-update-schedule-audit.json")
    args = parser.parse_args()

    result = build_daily_update_schedule_audit(
        repo_root=args.repo_root,
        unit_dir=args.unit_dir or None,
        output_dir=args.output_dir,
        service_name=args.service_name,
        timer_name=args.timer_name,
        check_systemd=not args.skip_systemd,
        require_enabled=not args.allow_installed_only,
        require_latest_run=args.require_latest_run,
    )
    _write_json(args.output, result)
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
    if not result["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
