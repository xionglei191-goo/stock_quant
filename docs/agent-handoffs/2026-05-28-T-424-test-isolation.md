# Handoff: T-424 Test Isolation

## Metadata
- Task ID: T-424
- Title: Test health and isolation from local production configuration
- Status: DONE
- Priority: high
- Owner Group: Platform and Quality
- Current Agent: codex-gpt5
- Reviewer:
- Created At: 2026-05-28
- Updated At: 2026-05-28T19:53:03+08:00

## Objective
Stabilize the test environment so the full local test suite can run without being polluted by `.env` values or external PostgreSQL/S3/OpenSearch configuration.

## Scope
In scope:
- Prevent `.env` import-time side effects from contaminating unit tests
- Make configuration parsing resilient to empty-string environment values
- Restore deterministic local test execution
- Align UI static contract assertions with current `required_ids`

Out of scope:
- New product features
- Non-local production deployment redesign
- Real broker integration
- Full security/auth redesign for external service exposure

## Background
Current evidence from earlier repository analysis:
- `app/server.py` loads `.env` during import and mutates process environment
- direct `python3 -m unittest discover -s tests` was polluted by local production-like config
- after forcing a clean environment, almost all tests passed
- remaining failure was a static UI contract assertion expecting `145` while current checker output was `151`

This makes test health look worse than actual code health and blocks reliable multi-agent parallel work.

## Problem Statement
Tests are not isolated from machine-local runtime configuration. Importing the server can load `.env` and leak storage/database/search settings into later tests. Some config parsing paths also break on empty strings such as `int("")`. This causes false failures and hides real regressions.

## Expected Deliverables
- Import-safe configuration loading path
- Test-safe environment handling strategy
- Updated UI static contract expectation or de-hardcoded assertion
- Evidence of a clean local test run
- Handoff note with exact validation commands and results

## Current Findings
1. Import-time `.env` loading was removed from module import path and moved to explicit startup flow, preventing unit-test environment pollution.
2. Empty-string environment parsing is now handled by shared helpers, preventing `int("")`/`float("")` failures during service initialization.
3. UI static contract assertion now derives required counts from `scripts/ui_static_check.py` source constants.
4. Full `make local-ci` passes in current worktree: `204/204` unit tests passed, UI static check passed, security check passed, handoff check passed.

## Proposed Work Plan
1. Audit config-loading entry points in `app/server.py` and shared config helpers. (completed)
2. Move `.env` loading to runtime entrypoint only, not module import. (completed)
3. Normalize env parsing for integer-like values to handle unset and empty-string safely. (completed)
4. Re-run targeted and full checks via `make local-ci`. (completed)
5. Keep UI static contract assertion bound to source-of-truth constant lengths. (completed)
6. Record commands, outputs, and residual risk in this handoff. (completed)

## Implementation Notes
- Preserve current local-production behavior when running the actual service.
- Do not silently weaken test coverage.
- Prefer a single configuration helper instead of ad hoc `os.environ.get()` parsing.
- Any test-only workaround must be justified and documented.

## Validation Plan
```bash
python3 -m py_compile app/*.py tests/*.py scripts/*.py
python3 scripts/security_check.py .
env -u AI_QUANT_POSTGRES_DSN -u AI_QUANT_S3_ENDPOINT -u AI_QUANT_S3_BUCKET -u AI_QUANT_OPENSEARCH_URL python3 -m unittest discover -s tests
python3 scripts/ui_static_check.py
```

## Risks
- Remaining `ResourceWarning` observed during tests (`Implicitly cleaning up <HTTPError 422...>`) should be tracked separately if it becomes noisy, but it is non-failing and not blocking this task.
- UI required ID/function counts can still evolve with feature growth; tests now assert against source constants to avoid hardcoded drift.

## Dependencies
- `app/server.py`
- config parsing helpers across `app/`
- `tests/test_system.py`
- `scripts/ui_static_check.py`

## Blockers
- None.

## Handoff Checklist
- [x] Code changes implemented
- [x] Validation commands executed
- [x] Test results captured
- [x] Artifact or log references added
- [x] `tasks/todo.md` status updated
- [ ] Reviewer assigned

## Evidence
- Validation command:
  ```bash
  make local-ci
  ```
- Result summary:
  - `python3 -m py_compile app/*.py tests/*.py scripts/*.py`: passed
  - `python3 -m unittest discover -s tests`: passed (`Ran 204 tests in 15.520s`)
  - `python3 scripts/ui_static_check.py`: passed (`required_ids=151`, `required_functions=50`, `node_check=passed`)
  - `python3 scripts/security_check.py .`: passed (`ok=true`, `findings=[]`)
  - `python3 scripts/check_handoffs.py`: passed
- Environment:
  - local workspace on `main` branch, commit base `6791acc`, with uncommitted working-tree changes.

## Next Recommended Action
Task is complete for local quality gates. Next owner can continue from T-425/T-426/T-427 integration and commit grouping without reopening isolation fixes.
