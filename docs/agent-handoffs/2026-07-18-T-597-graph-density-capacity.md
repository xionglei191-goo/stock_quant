# Handoff: T-597 Graph density and renderer capacity

## Metadata

- Status: DONE
- Owner group: Data and Evidence
- Reviewer groups: Product and UI; Platform and Quality; PM / Release Coordination
- Last updated: 2026-07-18
- Last agent: Codex (T-597 delegated agent)
- Branch/worktree: current shared worktree

## Objective

Quantify local governed knowledge-graph layer density and cross-layer links over
multiple subjects, separate seed/fixture evidence from real records, and define
an evidence-based SVG/virtualization/Canvas/WebGL decision without importing or
inventing facts.

## Scope

- In scope: read-only SQLite record audit, nine graph layers, seven cross-link
  ratios, provenance classification, raw model size estimates, existing browser
  artifact measurements, synthetic model-preparation curve, renderer thresholds,
  focused tests, evidence artifact, and capacity decision documentation.
- Out of scope: graph UI/runtime changes, API or storage schema changes, seed or
  import mutation, fact creation, dynamic allocation, and non-local release
  capacity claims.
- Risk level: medium; classification and capacity claims require strict evidence
  boundaries even though the implementation is read-only.

## Background

T-566 proved Obsidian-style graph behavior using seed/acceptance data but left
real document/event/viewpoint/evidence density and renderer migration as open
work. Existing browser artifacts cannot be treated as governed production-like
data because their subjects and relationships were seeded for acceptance.

## Problem Statement

The repository lacked one reusable audit that could answer three questions
without conflation: which graph rows are governed rather than fixture data,
whether multiple subjects have meaningful cross-layer links, and whether the
visible renderer has actually crossed a migration threshold.

## Expected Deliverables

- A reusable default-read-only audit over one or more SQLite stores.
- Multi-subject layer, provenance, link, and size measurements.
- Explicit renderer thresholds and a recommendation tied to governed browser
  evidence rather than seed or synthetic measurements.
- Focused regression and local-only evidence with reproducible commands.

## Current Findings

- Completed: audited three stores and three subjects through SQLite URI
  `mode=ro`; input DB timestamps remained unchanged.
- Completed: classified AAPL as governed with 2,375 governed rows and nine local
  fallback fixture rows; governed layer coverage is only 2/9 (document and
  evidence), with both documents linked to evidence.
- Completed: classified DEMO as seed/fixture (seven graph rows, 0/9 governed
  layers) and the 000001 value-case subject as unclear with no graph-layer rows.
- Completed: measured existing seed/acceptance browser artifacts from 33
  nodes/88 edges at about 60 FPS through 88 nodes/182 edges at 52.74 FPS.
- Completed: defined renderer policy tiers and recorded that the governed AAPL
  raw model estimate is 2,386 nodes/2,387 edges, a Canvas-sized full
  materialization but not a browser measurement.
- In progress: none for the audit deliverable.
- Not started: a second and third governed multi-layer subject and governed
  browser-capacity runs.
- Blocked: real governed browser capacity remains unverified because available
  browser artifacts are seed/acceptance-only and T-597 did not modify T-599 UI.

## Proposed Work Plan

Completed in this turn:

1. Inventory local stores and existing browser evidence.
2. Implement strict provenance-aware multi-subject density and link audit.
3. Run the audit without store initialization or mutation and correct an initial
   over-broad evidence-text classifier before accepting results.
4. Define renderer gates, add focused tests, and publish the evidence boundary.

## Validation Plan

Run the focused graph suite, compile all Python entry points, execute the audit
against three local stores and four existing browser artifacts, verify input DB
timestamps and test-level byte equality, run security/document/link/diff checks,
run full discovery, and validate the handoff.

## Files Touched

- `app/service_modules/graph_density_capacity.py`: 447-line read-only density,
  provenance, link, browser evidence, synthetic curve, and threshold module.
- `scripts/graph_density_capacity_audit.py`: 39-line repeatable CLI using
  existing SQLite files and optional browser artifacts.
- `tests/test_graph_quality.py`: added one focused test proving byte-for-byte
  input DB stability, governed/fixture separation, link ratios, and threshold
  boundaries; the focused module now contains 41 tests.
- `docs/graph-density-capacity-decision.md`: records facts, decisions,
  assumptions, open questions, gates, and reproduction command.
- `artifacts/graph-density-capacity-audit.json`: generated local-only evidence;
  ignored by Git artifact policy but present in the shared workspace.
- `docs/agent-handoffs/2026-07-18-T-597-graph-density-capacity.md`: this handoff.

## Evidence

Commands run:

```bash
python3 scripts/graph_density_capacity_audit.py \
  --state-db data/state.db \
  --state-db data/local/sec_single_name_ui.db \
  --state-db data/local/value-case-t573.sqlite \
  --browser-artifact artifacts/ui-graph-multi-symbol-acceptance-aapl-local.json \
  --browser-artifact artifacts/ui-graph-multi-symbol-acceptance-nvda-local.json \
  --browser-artifact artifacts/ui-graph-multi-symbol-acceptance-600519-local.json \
  --browser-artifact artifacts/ui-graph-multi-symbol-acceptance-aapl-global.json \
  --output artifacts/graph-density-capacity-audit.json
python3 -m unittest tests.test_graph_quality
python3 -m py_compile app/*.py app/service_modules/*.py tests/*.py tests/dynamic_allocation/*.py scripts/*.py
python3 -m unittest discover -s tests
python3 scripts/security_check.py .
python3 scripts/check_doc_metadata.py
python3 scripts/check_markdown_links.py
git diff --check -- app/service_modules/graph_density_capacity.py scripts/graph_density_capacity_audit.py tests/test_graph_quality.py docs/graph-density-capacity-decision.md docs/agent-handoffs/2026-07-18-T-597-graph-density-capacity.md
python3 scripts/check_handoffs.py
```

Result:

- Passed: focused graph suite, 41 tests in 2.176 seconds.
- Passed: compilation, security scan (381 files, zero findings), canonical doc
  metadata, 234-file Markdown link check, and whitespace check.
- Passed count gate: full discovery finds 446 tests, up from 432 before T-597;
  T-597 adds one and concurrent tasks added the remainder.
- Failed, unrelated: full discovery reports 7 failures and 14 errors. Dynamic
  allocation owns 14 errors and 3 failures; PM completion/task audits own 3
  failures; a concurrent production-runbook text assertion owns 1 failure. No
  density/capacity or graph focused test fails.
- Not run: governed-data browser capacity. Available browser artifacts are
  explicitly seed/acceptance-only, so running or relabeling them would not close
  the evidence gap.

Measured facts:

- AAPL: 2,375 governed rows, 9 fixture rows, governed ratio 0.9962, 2/9 governed
  layers, document-evidence link coverage 2/2, raw estimate 2,386/2,387.
- DEMO: 7 fixture rows, no governed layers, link coverage 1/2, raw estimate 9/13.
- 000001: no graph-layer rows, no eligible cross-links, raw estimate 2/1.
- Largest existing browser fixture measurement: 88 nodes, 182 edges, 52.74 FPS,
  3.81 ms average frame.

## Decisions

- Retain SVG for bounded visible graphs and require virtualization/culling when
  raw governed models exceed 250 nodes or 500 edges.
- Do not approve Canvas/WebGL from the 2,386-node raw estimate alone; it does not
  prove those nodes are simultaneously visible or that SVG misses frame budget.
- Canvas becomes a candidate above 750 visible nodes or 1,500 visible edges, or
  below 45 FPS / above 16.7 ms average frame for three governed runs.
- WebGL becomes a candidate above 3,000 visible nodes or 6,000 visible edges, or
  after Canvas fails the same governed browser gate.
- Synthetic preprocessing timings are labeled example/model evidence only and
  never presented as renderer performance.

## Risks

- Evidence depth is concentrated in AAPL SEC slices; it is not multi-subject
  multi-layer density. Events, relationships, reports, and viewpoints remain
  absent from the governed sample.
- Row-level evidence nodes may overstate useful visible density; aggregation by
  document/section/topic should be evaluated before renderer migration.
- Provenance classification is conservative and field-based. Unclear records
  remain excluded rather than promoted based on inferred content.
- Artifact JSON is ignored by Git and is local-only; future agents must rerun the
  recorded command if the local artifact is cleaned.

## Dependencies

- Existing SQLite `records` table contract and governed source metadata.
- T-566 browser artifacts for seed/acceptance capacity context.
- T-599 or a later Product/UI task for a governed browser-capacity run without
  conflicting UI changes.

## Blockers

- No blocker for completing the read-only audit and decision.
- Multi-subject governed density and governed browser capacity require real
  source ingestion/links and a later browser run; T-597 does not fabricate them.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: no; `app/services.py` was not touched.
- Domain module decision: used a standalone read-only domain helper and CLI; an
  API facade was unnecessary for a local evidence audit.
- Focused regression: `tests.test_graph_quality` passes all 41 tests, including
  read-only byte stability and provenance/threshold behavior.
- Contract impact: no API schema, storage schema, UI behavior, audit/permission
  behavior, paper-only boundary, or no-broker boundary changed.

## Artifacts

- `artifacts/graph-density-capacity-audit.json`: produced 2026-07-18 by the
  command above; environment local workspace; owner Data and Evidence;
  classification `local-only`; no sensitive data; not acceptable for non-local
  production release gates.
- Four `artifacts/ui-graph-multi-symbol-acceptance-*.json` inputs: prior local
  seed/acceptance browser evidence; not governed real-data or non-local release
  evidence.

## Handoff Checklist

- [x] Read-only audit, CLI, test, decision doc, and local artifact completed
- [x] Checks run and unrelated aggregate failures recorded
- [x] Evidence classes and browser gap stated without promotion
- [x] `tasks/todo.md` intentionally left to the parent PM agent

## Next Recommended Action

1. PM / Release Coordination records T-597 as the completed audit while keeping
   the measured governed-data and browser gaps as explicit follow-up work.
2. Data and Evidence adds at least two governed subjects with event,
   relationship, report, viewpoint, and evidence links through approved source
   paths, then reruns this audit.
3. Product and UI runs the threshold matrix against governed data; migrate to
   Canvas only if the visible graph crosses the gate or fails frame budget for
   three runs.
