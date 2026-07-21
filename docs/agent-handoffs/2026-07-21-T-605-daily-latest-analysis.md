# Handoff: T-605 Daily Status and Latest Analysis Hot Read

## Metadata

- Status: DONE
- Owner group: Research and AI Workflows
- Reviewer groups: Platform and Quality; Product and UI; PM / Release Coordination
- Last updated: 2026-07-21
- Last agent: Codex `/root/t605_daily_latest_analysis`
- Branch/worktree: `main`, shared T-603 integration worktree
- Artifact classification: local-only
- Risk level: high

## Objective

Make `GET /api/analysis/latest` read the company-intelligence snapshot already materialized by the latest-analysis run, and separate daily execution health from research-content readiness without hiding evidence gaps.

## Scope

- In scope: latest-analysis artifact selection, materialized company-intelligence reads, daily execution/content status fields, scheduler audit semantics, focused regressions, API and runbook contracts, and local latency evidence.
- Out of scope: report-state recovery, data-health counting, usage-origin design, database/index/object-store mutation, UI redesign, real broker connectivity, and automatic order execution.

## Background

The 2026-07-20 daily run failed both the direct-report evidence gate and the latency audit. `GET /api/analysis/latest` took about 12.3 seconds because the handler looked for company intelligence at the artifact root even though `scripts/latest_analysis_run.py` already materialized it at `analysis.company_intelligence`; the miss triggered one live `SystemService.company_intelligence` call per asset.

## Problem Statement

The API read the correct artifact but the wrong JSON level, turning a hot read into repeated business computation. The daily pipeline also treated a successfully generated insight whose evidence gate failed as an execution failure, so systemd could not distinguish infrastructure failure from honest `needs_evidence` research content.

## Expected Deliverables

- Current latest-analysis artifacts serve materialized company intelligence without service recomputation.
- Old artifacts keep their compatibility fallback.
- Daily output exposes `execution_status` and `content_status`; legacy `status` and `passed` remain present and represent execution health.
- Evidence gaps remain visible as `needs_evidence` and retain the original failed quality gates.
- Real HTTP p95 is below two seconds.

## Current State

- Completed: the API reads `analysis.company_intelligence`, then the legacy top-level field, before using the old per-company fallback.
- Completed: daily top-level and summary output expose `execution_status=passed|failed` and `content_status=ready|needs_evidence|unavailable`.
- Completed: a generated daily insight is an execution success even when its research gate is `needs_evidence`; exceptions and missing generation remain blocking execution failures.
- Completed: `content_issues` retains quality-gate failures, and operator actions still direct the user to the insight artifact.
- Completed: schedule audit validates execution independently and accepts both classified content states `ready` and `needs_evidence` without hiding the latter.
- Completed: real local HTTP p95 is 0.042 seconds over 20 warm samples; the application container is healthy.
- Blocked: none.

## Current Findings

- The current artifact `artifacts/daily-update-local/runs/2026-07-20-184827/latest-analysis-2026-07-20/latest-analysis.json` contains `analysis.company_intelligence` with schema `latest-analysis-company-intelligence-v1` and nine companies.
- Direct handler reads of that artifact took a median 19.9 ms and maximum 23.4 ms across seven samples.
- The first HTTP probe after removing company recomputation was still about 2.1 seconds because usage telemetry called `PostgreSQLStore.commit()` without a dirty collection and scanned all loaded records. T-607 added `mark_dirty_for_resource("usage_metric")`; after restart, 20 HTTP samples had median 0.038 seconds, p95 0.042 seconds, and maximum 0.051 seconds.
- The current on-disk daily pipeline artifact predates the new status contract, so its historical `status=failed` remains unchanged. The next daily run will populate distinct execution/content fields.

## Proposed Work Plan

1. Read the already materialized company-intelligence snapshot before invoking any legacy fallback.
2. Split pipeline execution health from content readiness while preserving legacy output fields.
3. Update the scheduler audit, focused regressions, and operator contracts.
4. Reload the local app and verify real HTTP latency against the current artifact.

## Validation Plan

- Run changed-file compilation, whitespace checks, latest-analysis regressions, all daily-pipeline matches, and the scheduler audit regression.
- Confirm the current artifact contains the expected materialized schema and company count.
- Restart only `ai-quant-org`, confirm container health, and measure 20 read-only HTTP samples.
- Leave the repository-wide `make local-ci` to the parent after all T-603 parallel changes are integrated.

## Dependencies

- T-607 usage telemetry dirty-scope fix removes the remaining generic PostgreSQL commit scan from the HTTP request path.
- T-604 report-state recovery is required before content readiness can advance from `needs_evidence` based on direct report evidence.

## Blockers

- None for T-605 implementation and local acceptance.

## Files Touched

- `app/api.py`: prefer materialized company intelligence and expose daily pipeline execution/content status alongside the legacy status field.
- `scripts/daily_data_update_pipeline.py`: define execution/content status mapping, keep evidence failures in `content_issues`, and make generated-but-under-evidenced insight nonblocking.
- `scripts/audit_daily_update_schedule.py`: audit execution and classified content independently.
- `tests/test_system.py`: cover materialized zero-recompute reads, legacy fallback behavior, status separation, and schedule-audit semantics.
- `docs/api-contracts.md`: document artifact priority, materialized snapshot location, and legacy fallback.
- `docs/production-runbook.md`: document daily status meanings and operator handling.
- `docs/agent-handoffs/2026-07-21-T-605-daily-latest-analysis.md`: record implementation, evidence, and residual risks.

## Commands Run

```bash
.venv/bin/python -m py_compile app/api.py scripts/daily_data_update_pipeline.py scripts/audit_daily_update_schedule.py tests/test_system.py
.venv/bin/python -m unittest -v \
  tests.test_system.SystemServiceTests.test_latest_analysis_api_summarizes_local_artifact_for_ui \
  tests.test_system.SystemServiceTests.test_latest_analysis_api_prefers_daily_update_artifacts_and_exposes_daily_insight \
  tests.test_system.SystemServiceTests.test_daily_pipeline_runs_research_binding_before_insight_gate \
  tests.test_system.SystemServiceTests.test_daily_pipeline_emits_operator_summary_and_artifact_manifest \
  tests.test_system.SystemServiceTests.test_daily_pipeline_separates_execution_health_from_content_readiness \
  tests.test_system.SystemServiceTests.test_daily_pipeline_command_timeout_writes_failure_artifact \
  tests.test_system.SystemServiceTests.test_daily_market_insight_fails_when_direct_research_evidence_gate_is_not_met \
  tests.test_system.SystemServiceTests.test_daily_update_systemd_audit_requires_scheduler_and_latest_pipeline
.venv/bin/python -m unittest -v tests.test_system -k daily_pipeline
.venv/bin/python -m unittest -v tests.test_system -k latest_analysis
.venv/bin/python -m unittest -v tests.test_system -k daily_update_systemd_audit
docker compose restart ai-quant-org
curl -H 'X-Role: ceo' -H 'X-Client-Origin: acceptance' http://127.0.0.1:8000/api/analysis/latest
git diff --check -- app/api.py scripts/daily_data_update_pipeline.py scripts/audit_daily_update_schedule.py tests/test_system.py docs/api-contracts.md docs/production-runbook.md
```

Result:

- Passed: changed-file compilation and diff whitespace check.
- Passed: focused acceptance set, 8/8.
- Passed: all `daily_pipeline` matches, 8/8; all `latest_analysis` matches, 5/5; schedule audit, 1/1.
- Passed: real HTTP response `200`, materialized company count 9, median 0.038 seconds, p95 0.042 seconds, maximum 0.051 seconds across 20 samples after T-607 dirty-scope integration.
- Failed then resolved: the first focused run had two latest-analysis failures because the shared worktree temporarily contained `origin=` router propagation before the matching T-607 facade signature. After T-607 integration, both tests and the full focused set passed; this was not a T-605 behavior failure.
- Not run: full `make local-ci`; the parent T-603 integration owner will run the repository-wide gate after all parallel work is merged.

## Evidence

- `artifacts/daily-update-local/runs/2026-07-20-184827/latest-analysis-2026-07-20/latest-analysis.json`: produced by the 2026-07-20 local daily pipeline; consumed to verify the materialized nine-company snapshot; local-only, may contain restricted local research references, and is not eligible for non-local release.
- Live HTTP probe output from 2026-07-21 against `http://127.0.0.1:8000/api/analysis/latest`: produced by 20 read-only acceptance-origin requests; no response body was persisted, contains no credentials, local-only, and is not eligible for non-local release.

## Decisions

- Treat `status` and `passed` as legacy-compatible execution fields; do not overload them with research readiness again.
- Keep the raw daily-insight artifact's failed evidence gate intact. The pipeline maps it to `content_status=needs_evidence` only after successful artifact generation.
- Keep the old per-company fallback for artifacts that predate materialization. Removing it would break compatibility; current and future artifacts do not use it.
- Keep latency failure operationally blocking. T-605 fixes the endpoint rather than weakening the latency gate.
- Preserve the local-research, simulated-portfolio, no-broker, no-automatic-order boundary.

## Risks and Open Questions

- An old artifact without either materialized company-intelligence location can still use the slow compatibility fallback. Regenerate latest analysis instead of relying on that path for normal operation.
- Existing daily artifacts are immutable historical evidence and will not gain `execution_status`/`content_status`; verify the next scheduled run rather than rewriting them.
- Direct report evidence is still missing in the current data state. The next run should complete execution successfully but remain `content_status=needs_evidence` until T-604 recovery and five-company evidence work improve coverage.
- The latency result is local-only and includes one application instance; it is not an external staging capacity report.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated
- [x] `tasks/todo.md` contains T-605 and is ready for PM to mark DONE after integration

## SystemService Growth Freeze Review

- New `SystemService` business logic added: no; `app/services.py` was not changed by T-605.
- Domain placement: status mapping stays in the daily pipeline script, and artifact projection stays in `app/api.py`; neither requires a new service domain method.
- Focused regression: latest-analysis tests prove materialized reads make zero `company_intelligence` service calls while the older fixture still exercises compatibility fallback; daily and schedule tests protect status semantics.
- Contract/boundary changes: additive API and artifact fields only; no storage schema or UI workflow changed, and paper-only/no-broker boundaries remain unchanged.

## Next Steps

1. Let the next scheduled daily run produce the first artifact with the split status contract.
2. Confirm that a direct-report evidence gap yields `execution_status=passed`, `content_status=needs_evidence`, and a successful systemd unit result.
3. After T-604 recovery, rerun the daily insight and verify whether the content state advances to `ready` without changing execution semantics.

## Next Recommended Action

Observe and audit the next scheduled daily run; do not rewrite the failed 2026-07-20 artifact.
