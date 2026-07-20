# Artifact Governance

- Status: active
- Owner group: PM / Release Coordination
- Last updated: 2026-05-28
- Related tasks: T-429
- Scope: local artifact submission rules, handoff evidence hygiene
- Non-goals: non-local production evidence approval policy

## Classification

Use one of four classes for generated files:

1. `functional_change`: source code and tests required for behavior.
2. `documentation_change`: docs, ADRs, handoffs, checklists.
3. `evidence_artifact`: reproducible readiness/acceptance outputs required by a task gate.
4. `temporary_output`: local debug/log/intermediate files, never required for commit.

## Commit Policy

1. Always commit `functional_change` and `documentation_change` tied to task scope.
2. Commit `evidence_artifact` only when the task explicitly requires archived evidence.
3. Do not commit `temporary_output`; add to `.gitignore` when recurring.
4. Every committed artifact must include owner, generation command, and freshness date in task notes or handoff.

## Local CI Gate

Run:

```bash
make local-ci
```

This chains compile, unit tests, UI static contract, security scan, Markdown link validation, and handoff validation.

For documentation-only changes, at minimum run:

```bash
python3 scripts/check_markdown_links.py
python3 scripts/check_handoffs.py
git diff --check
```

## Local Retention

Generated browser profiles and repeated local staging UI captures are temporary output, not release evidence.

- Browser acceptance scripts must create Chromium user-data directories under the operating system temporary directory and remove them when the browser exits.
- `artifacts/` reports and screenshots may remain local when useful, but Chromium profiles must not be written below an artifact output directory.
- `data/local/tdx`, research-report data, object-store data, Git-tracked files, `*.example.json`, symbolic links, and evidence referenced by current tasks or handoffs are outside automatic cleanup scope.
- Retention review defaults to 14 days while keeping the two newest discovered paths. These values are operator inputs, not production evidence policy.

Audit local candidates without deleting anything:

```bash
make artifact-audit
```

The underlying command is `python3 scripts/local_artifact_retention.py`. It defaults to dry-run and requires explicit `--execute` before deleting eligible paths. Destructive retention is intentionally excluded from `make local-ci` and requires review of the generated candidate list.
`make artifact-audit` writes the full candidate report to `/tmp/ai-quant-artifact-audit.json` and prints only a summary to the terminal.
