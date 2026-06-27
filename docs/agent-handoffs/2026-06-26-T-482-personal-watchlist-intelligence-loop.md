# Handoff: T-482 Personal Watchlist Intelligence Loop

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: PM / Release Coordination, Data and Evidence, Platform and Quality
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-482

## Objective

Turn scattered market, report and evidence data into a personal watchlist company-intelligence loop. Daily refresh should build and summarize company profiles, events, relationships, report viewpoints and paper-only feedback for the user's watchlist.

## Scope

- In scope: daily pipeline orchestration, personal watchlist refresh script, `/api/analysis/latest` artifact surfacing, dashboard UI summary, roadmap and handoff.
- Out of scope: real broker integration, automatic order execution, external paid data feeds, full scheduler service redesign.

## Background

The local stack already has large market-data and research-report collections, but company-level intelligence records are sparse. This makes the UI feel scattered because it reads many low-level collections without a reliable watchlist-driven company intelligence artifact.

## Problem Statement

Personal users need the system to answer which watchlist companies are ready, what changed, and what still needs evidence. The existing daily run updates data but does not consistently form company-level intelligence for the user's watchlist.

## Expected Deliverables

- A script that refreshes a configured personal watchlist through existing company database APIs.
- Daily pipeline integration so the script runs after market/report refresh.
- `/api/analysis/latest` returns the latest personal intelligence artifact.
- Dashboard UI shows watchlist refresh status, ready count, attention count and per-company gaps.
- Validation evidence for script, static UI and handoff checks.

## Current Findings

- `market_data` and `research_reports` are populated, but `company_profiles`, `company_events`, `company_relationships` and workflow records only exist for a sample company.
- `scripts/run_daily_data_update.sh` is the correct daily entry point.
- Existing `/api/company-database/batch/build` already can build profiles, events, relationships and workflow in one call.
- The safest product integration is to add a new artifact and surface it through `/api/analysis/latest`.

## Proposed Work Plan

1. Add `scripts/personal_intelligence_refresh.py`.
2. Wire the script into `scripts/daily_data_update_pipeline.py` and `scripts/run_daily_data_update.sh`.
3. Surface the artifact from `/api/analysis/latest`.
4. Add dashboard UI summary and static contract coverage.
5. Run focused script and UI validation.

## Validation Plan

- `python3 -m py_compile app/*.py tests/*.py scripts/*.py`
- `python3 scripts/ui_static_check.py`
- `python3 scripts/check_handoffs.py`
- `git diff --check`
- Focused script execution against local app on `127.0.0.1:8000`.

## Current State

- Completed: personal watchlist refresh script added.
- Completed: daily pipeline and daily shell entry point wired.
- Completed: `/api/analysis/latest` and dashboard UI updated.
- Completed: validation and final status update.
- Blocked: None.

## Dependencies

- Running local Compose app at `http://127.0.0.1:8000`.
- Existing company database build APIs.
- Existing daily update pipeline.

## Blockers

- None.

## Files Touched

- `scripts/personal_intelligence_refresh.py`: new watchlist refresh script.
- `scripts/daily_data_update_pipeline.py`: runs personal intelligence refresh after latest analysis.
- `scripts/run_daily_data_update.sh`: exposes environment variables for watchlist refresh.
- `app/api.py`: returns personal intelligence artifact from `/api/analysis/latest`.
- `app/static/index.html`: dashboard summary for personal watchlist loop.
- `scripts/ui_static_check.py`: static contract coverage for new dashboard nodes/function.
- `tasks/todo.md`: added T-482.
- `docs/agent-handoffs/2026-06-26-T-482-personal-watchlist-intelligence-loop.md`: this handoff.

## Commands Run

```bash
python3 scripts/personal_intelligence_refresh.py --base-url http://127.0.0.1:8000 --symbols AAPL,NVDA,MSFT,300750,600519 --execute --output artifacts/personal-intelligence/latest.json
docker compose restart ai-quant-org
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 scripts/ui_static_check.py
python3 scripts/check_handoffs.py
git diff --check
python3 - <<'PY'
import json
from urllib.request import urlopen
payload=json.loads(urlopen('http://127.0.0.1:8000/api/analysis/latest',timeout=30).read().decode())
data=payload.get('data') or {}
pi=data.get('personal_intelligence') or {}
print(json.dumps({
  'success': payload.get('success'),
  'personal_intelligence_artifact_path': data.get('personal_intelligence_artifact_path'),
  'status': pi.get('status'),
  'company_count': pi.get('company_count'),
  'ready_count': pi.get('ready_count'),
  'needs_attention_count': pi.get('needs_attention_count'),
  'symbols': pi.get('watchlist_symbols'),
}, ensure_ascii=False, indent=2))
PY
```

Result:

- Passed: personal watchlist refresh produced 5 companies with `status=passed`.
- Passed: Compose app restarted so `app/api.py` and static UI changes are active.
- Passed: `python3 -m py_compile app/*.py tests/*.py scripts/*.py`.
- Passed: `python3 scripts/ui_static_check.py`, with `required_ids=306`, `required_functions=110`, `node_check=passed`.
- Passed: `python3 scripts/check_handoffs.py`, checked 53 handoff files.
- Passed: `git diff --check`.
- Passed: `/api/analysis/latest` returned `personal_intelligence.status=passed`, `company_count=5`, `needs_attention_count=5`.
- Failed: none.
- Not run: full unit suite; scope was orchestration/UI contract plus focused local API validation.

## Evidence

- `artifacts/personal-intelligence/latest.json`: local-only watchlist refresh evidence generated from the local Compose app on 2026-06-26. It contains 5 symbols: `AAPL`, `NVDA`, `MSFT`, `300750`, `600519`.
- API evidence: `/api/analysis/latest` exposes `personal_intelligence_artifact_path=artifacts/personal-intelligence/latest.json` and `personal_intelligence.status=passed`.
- Coverage result: average coverage score `0.7384`; all 5 companies have profiles, market/security coverage, events, relationships, observations, conclusions and paper-only feedback.
- Remaining data gaps: all 5 need financial snapshots and disclosure events; 3 need official/IR documents; 4 need structured viewpoints.

## Decisions

- Use watchlist-driven refresh rather than all-market company-intelligence generation to keep daily runtime and UI output usable.
- Keep the loop paper-only and local-record-only; it does not add broker connectivity or automated trading.
- Surface the artifact through `/api/analysis/latest` to avoid adding another dashboard endpoint for this narrow slice.

## Risks and Open Questions

- Existing company database build APIs may still produce shallow profiles when official/IR material sidecars are missing.
- Future work should add first-class watchlist management in the UI instead of relying only on environment variables.
- The loop now makes missing layers explicit, but it does not solve source acquisition for financial snapshots, disclosures and official/IR documents.

## Artifacts

- `artifacts/personal-intelligence/latest.json`: local-only personal watchlist company-intelligence refresh result; generated by `scripts/personal_intelligence_refresh.py`; not acceptable for non-local production release gates.

## Handoff Checklist

- [x] Implementation drafted.
- [x] Validation passed.
- [x] `tasks/todo.md` marked DONE.
- [x] Handoff marked DONE.

## Next Steps

1. Add a personal watchlist editor instead of relying only on script/env defaults.
2. Add explicit source connectors or import manifests for financial snapshots, disclosures and official/IR documents.
3. Consider a scheduled local runner wrapper after the user confirms the desired refresh cadence.

## Next Recommended Action

Decide whether the next improvement should be source acquisition for missing company layers or first-class watchlist management in the UI.
