# Handoff: T-618 HTTP Client Disconnect Resilience

## Metadata

- Status: DONE
- Owner group: Platform and Quality
- Reviewer groups: Product and UI; PM / Release Coordination
- Last updated: 2026-07-22
- Last agent: Codex `/root`
- Branch/worktree: `main`, shared working tree
- Artifact classification: local-only
- Related tasks: T-618

## Objective

Prevent client timeouts or browser tab closure from producing misleading server traceback logs while a response is being written.

## Scope

- In scope: response-body writes in the local HTTP handler and a focused regression.
- Out of scope: API semantics, data mutations, timeout policy, database behavior, and live-trading boundaries.

## Background

The live UI interaction acceptance timed out while waiting for a slow company database preview. The application then logged repeated `BrokenPipeError` tracebacks when writing responses to clients that had already disconnected.

## Problem Statement

Expected client disconnects were treated as unhandled server errors, polluting operational logs and obscuring real failures.

## Expected Deliverables

- A shared response write helper that ignores `BrokenPipeError` and `ConnectionResetError`.
- Regression coverage and live container verification.

## Current State

- Completed: JSON, HTML, and UI module responses use `_write_body`.
- Completed: focused regression and full local CI.
- Completed: Compose app restarted and health verified.
- Not started: none.
- Blocked: click-through UI acceptance remains unconfirmed because the prior run was manually interrupted after a long wait; screenshot/browser acceptance passed separately.

## Current Findings

- Before the fix, `docker compose logs` showed repeated `BrokenPipeError` from `Handler._send_json` after client timeout.
- After the fix, an intentionally disconnected batch-preview request produced no `BrokenPipeError` or `ConnectionResetError` in recent app logs.

## Proposed Work Plan

1. Centralize response writes behind a disconnect-tolerant helper.
2. Add regression coverage and run repository checks.
3. Restart the app container and verify health/log behavior.

## Validation Plan

- Focused HTTP handler regression.
- `PATH=.venv/bin:$PATH make local-ci`.
- Live `/api/health` check and intentional client disconnect probe.
- `scripts/ui_browser_acceptance.py` for desktop/mobile screenshots.

## Dependencies

- Existing Compose app container and local PostgreSQL/S3/OpenSearch services.

## Blockers

- None for T-618. The separate click-through acceptance remains an unverified follow-up, not a T-618 release blocker.

## Files Touched

- `app/server.py`: route all response bodies through `_write_body` and ignore expected disconnect errors.
- `tests/test_system.py`: add regression for a closed response writer.
- `tasks/todo.md`: record T-618 as complete.

## Commands Run

```bash
.venv/bin/python -m unittest tests.test_system.SystemServiceTests.test_http_handler_ignores_client_disconnect_while_writing_response
PATH=".venv/bin:$PATH" make local-ci
docker compose restart ai-quant-org
curl -fsS http://127.0.0.1:8000/api/health
```

Result:

- Passed: focused regression; full CI 546 tests; UI static; security; Markdown links; handoff and canonical metadata checks; live health check.
- Passed: desktop/mobile browser screenshot acceptance with zero failures and nonblank screenshots.
- Not passed: click-through interaction acceptance was interrupted after an extended wait at the company database batch preview check; no pass claim is made.

## Evidence

- `artifacts/local-production-audit-current.json`: local-only live audit, generated 2026-07-22 after app restart, passed, not eligible for non-local release.
- `artifacts/local-ai-capability-acceptance-current.json`: local-only live LLM/OCR smoke, generated 2026-07-22, passed, not eligible for non-local release.
- `artifacts/ui-browser-acceptance-live/`: local-only desktop/mobile screenshots, generated 2026-07-22, passed, not eligible for non-local release.

## Decisions

- Catch only expected socket disconnect exceptions; do not swallow unrelated write errors.
- Keep response status and business behavior unchanged.

## Risks and Open Questions

- Slow company database preview still takes about 15 seconds over HTTP and deserves a separate UI latency/async workflow task if it remains a repeated operator bottleneck.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated if applicable
- [x] `tasks/todo.md` status updated

## Next Steps

1. Consider a separate async/progress UX for long company database preview operations.
2. Re-run click-through acceptance after that latency behavior is addressed.

## Next Recommended Action

Profile the company database batch preview path and decide whether it should expose progress instead of requiring a long synchronous browser wait.
