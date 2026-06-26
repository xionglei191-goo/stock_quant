# Handoff: T-467 Company Material Inbox Workbench

## Metadata

- Status: DONE
- Owner group: Data and Evidence / Product and UI
- Reviewer groups: Platform and Quality, PM / Release Coordination
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-467

## Status

- Status: DONE
- Owner group: Data and Evidence / Product and UI
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`

## Objective

Expose the local company official/IR material inbox in the company intelligence workbench so manifest-backed company materials can be previewed and, when explicitly executed, fed into the existing source, document, evidence and profile field assertion pipeline.

## Background

T-461 added `scripts/company_material_inbox_ingest.py` for local manifest-backed company material ingestion. The user-facing company intelligence workbench still had no visible way to preview or execute that inbox flow, leaving company fact database backfill dependent on CLI usage.

## Problem Statement

The platform is being rebuilt around a complete company database. Users need a visible local-only data source workflow for official/IR/company materials, while preserving the rule that research reports, news and manual references are not fact sources.

## Expected Deliverables

- Material inbox API entrypoint for dry-run and explicit execute.
- Company intelligence workbench controls and manifest result table.
- Static and synthetic UI coverage for the new controls and renderer.
- API contract, roadmap and handoff updates.
- Direct smoke proving dry-run and rejection boundaries.

## Scope

- In scope: material inbox API wrapper, company intelligence workbench controls, static and synthetic UI contracts, API documentation, roadmap and handoff.
- Out of scope: external crawling, filename-based company inference, research report fact ingestion, model training, real broker integrations and live trading.

## Current Findings

- T-461 script path already had manifest sidecar semantics and boundary rules.
- `SystemService` had existing source, document, evidence and profile field extraction primitives that could be reused.
- The UI had adjacent patterns for profile field extraction and quality reconciliation that fit the new material inbox controls.

## Proposed Work Plan

1. Add a material inbox ingest service method and API route.
2. Add company intelligence workbench inputs, status counters, result rows and event bindings.
3. Update UI static and synthetic browser acceptance scripts.
4. Update API contracts, roadmap and handoff.
5. Run focused compile, static and smoke checks.

## Validation Plan

- Compile touched Python and acceptance scripts.
- Run `scripts/ui_static_check.py`.
- Run `git diff --check`.
- Run direct API dry-run smoke with one valid official material and one invalid broker research/training record.
- Run handoff validation.

## Current State

- Completed: added `POST /api/company-database/material-inbox/ingest`.
- Completed: added workbench controls for inbox path, manifest glob, scan limit, preview, execute, status counts and manifest result rows.
- Completed: execution refreshes profile field coverage, field assertion conflicts and company intelligence after a successful run.
- Completed: static UI and synthetic browser acceptance contracts know about the material inbox UI.
- Completed: direct API smoke verifies dry-run planned and invalid boundary behavior.
- Not started: end-to-end browser acceptance against a real local inbox fixture.

## Dependencies

- T-461 local material inbox manifest contract.
- Existing source/document/evidence/profile field extraction APIs.
- Existing company intelligence workbench and static UI acceptance scripts.

## Blockers

- None for this task.

## Files Touched

- `app/api.py`: added material inbox ingest route and handler.
- `app/services.py`: added service-side manifest scan, validation, dry-run and execute flow for local company materials.
- `app/static/index.html`: added workbench controls, renderer, payload builder, ingest action and event bindings.
- `scripts/ui_static_check.py`: added required IDs and functions for material inbox.
- `scripts/ui_interaction_acceptance.py`: added synthetic material inbox preview render check and diagnostics fields.
- `docs/api-contracts.md`: documented the new HTTP endpoint and boundaries.
- `tasks/todo.md`: marked T-467 done and recorded acceptance evidence.
- `docs/agent-handoffs/2026-06-26-T-467-company-material-inbox-workbench.md`: this handoff.

## Commands Run

```bash
python3 -m py_compile app/api.py app/services.py scripts/ui_static_check.py scripts/ui_interaction_acceptance.py
python3 scripts/ui_static_check.py
git diff --check
python3 - <<'PY'
import json
import tempfile
from pathlib import Path
from app.api import ApiRouter
from app.models import Issuer
from app.services import SystemService

svc = SystemService()
svc.store.issuers['issuer_demo'] = Issuer(issuer_id='issuer_demo', legal_name='Demo Inc')
router = ApiRouter(svc)
with tempfile.TemporaryDirectory() as tmp:
    root = Path(tmp)
    (root / 'official.txt').write_text('Demo Inc business summary. Products: analytics platform.', encoding='utf-8')
    manifest = {
        'documents': [
            {
                'issuer_id': 'issuer_demo',
                'source_id': 'demo_ir',
                'source_type': 'company_ir',
                'document_type': 'official_business_overview',
                'source_uri': 'https://demo.example.com/ir/profile',
                'file_path': 'official.txt',
            },
            {
                'issuer_id': 'issuer_demo',
                'source_id': 'demo_research',
                'source_type': 'broker_research',
                'document_type': 'research_report',
                'source_uri': 'https://demo.example.com/report',
                'file_path': 'official.txt',
                'rights_tag': {'training_allowed': True},
            },
        ]
    }
    (root / 'demo.manifest.json').write_text(json.dumps(manifest), encoding='utf-8')
    result = router.dispatch('POST', '/api/company-database/material-inbox/ingest', {'root_path': str(root), 'execute': False}, role='data_engineer')
    assert result.success, result.error
    data = result.data
    assert data['status'] == 'dry_run', data
    assert data['totals']['planned_count'] == 1, data['totals']
    assert data['totals']['invalid_count'] == 1, data['totals']
    invalid = [item for item in data['items'] if item['status'] == 'invalid'][0]
    assert 'disallowed_source_type' in invalid['errors'], invalid
    assert 'training_allowed_not_permitted' in invalid['errors'], invalid
    assert not svc.store.documents, 'dry-run mutated documents'
print('company material inbox api dry-run smoke passed')
PY
```

Result:

- Passed: Python compile on touched Python and UI-check scripts.
- Passed: UI static check, `required_ids=261`, `required_functions=90`, `interaction_markers=13`.
- Passed: `git diff --check`.
- Passed: direct API dry-run smoke.
- Not run: full browser acceptance and full unittest suite; this turn only changed a local workbench/API wrapper around the already tested T-461 script path.

## Evidence

- Direct API smoke proves `POST /api/company-database/material-inbox/ingest` returns one planned official material and one invalid broker research record in dry-run mode.
- Static UI check proves new DOM IDs, functions and event bindings are present.
- `git diff --check` reports no whitespace errors.

## Decisions

- The HTTP endpoint reuses the manifest sidecar contract from T-461 instead of guessing company identity from filenames.
- Dry-run is the default; execute must be explicit.
- Research reports remain viewpoint and attention signals only, so broker research and news are rejected from this fact ingestion path.
- Workbench execute refreshes profile field and conflict state because material ingestion can create new field assertions.

## Risks and Open Questions

- The workbench still needs an end-to-end fixture-driven browser acceptance run with a real local inbox directory.
- Service and script logic now overlap; a future cleanup should share manifest validation helpers to avoid drift.
- Execute mode depends on existing issuer IDs; users still need a company profile or batch build seed before material ingestion can write facts.

## Artifacts

- None. This task did not generate persistent runtime artifacts.

## Handoff Checklist

- [x] API route added.
- [x] Workbench controls added.
- [x] Static and synthetic UI contracts updated.
- [x] API contract updated.
- [x] Roadmap updated.
- [x] Focused checks run.

## Next Steps

1. Add an end-to-end UI acceptance fixture that creates a temporary material inbox and calls the actual endpoint through the browser.
2. Consider extracting common material inbox validation from `scripts/company_material_inbox_ingest.py` and `SystemService.company_material_inbox_ingest`.
3. Continue with T-469补库 run retry/resume UI if the roadmap still prioritizes database completion operations.

## Next Recommended Action

Add a fixture-backed browser acceptance case for material inbox preview/execute so the UI test clicks the real endpoint instead of only rendering a synthetic payload.
