# Handoff: T-490 UI Information Denoise

## Metadata

- Status: DONE
- Owner group: Product and UI
- Reviewer groups: PM / Release Coordination, Platform and Quality, Data and Evidence
- Last updated: 2026-06-26
- Last agent: Codex
- Branch/worktree: main / `/home/xionglei/Project/sotck_quant`
- Related task: T-490

## Objective

Make the default UI read like a personal company-intelligence and market-research workspace instead of a database/debug record browser.

## Scope

- In scope: static UI helpers, company intelligence core tables, knowledge graph details, market-data table, dashboard ID/status cleanup, static UI contract, roadmap and handoff.
- Out of scope: backend API schema changes, data migrations, broker/live execution, removing raw traceability.

## Background

The UI had accumulated many backend-oriented tables that surfaced internal IDs, run IDs, trace IDs, status codes and raw JSON. These are useful for debugging but weak as a personal research interface.

## Problem Statement

Personal users need conclusions, key facts, risks and next actions. Raw identifiers such as `issuer_*`, `rr_*`, `run_id` and `manifest_path` should not be the primary UI language.

## Current Findings

- `app/static/index.html` is the main UI surface.
- Company intelligence, knowledge graph and market-data tables were the highest-impact visible areas.
- Existing payloads contain enough title/name/summary/status fields to derive more readable labels without backend changes.

## Expected Deliverables

- Shared user-facing display helpers.
- Default tables with “主题 / 关键发现 / 状态 / 下一步或证据” semantics.
- Advanced trace details are available but collapsed by default.
- K-line functionality remains intact.
- Static UI contract prevents helper removal and key text regressions.

## Proposed Work Plan

1. Add user-facing label/status/summary/trace helpers.
2. Replace company intelligence fact/research/action table rendering with insight rows.
3. Replace knowledge graph fact/decision/edge table rendering with insight rows.
4. Replace market-data table with OHLCV/source-first view.
5. Move company intelligence raw payload into advanced trace details.
6. Validate statically and in browser.

## Validation Plan

- `python3 scripts/ui_static_check.py`
- `python3 -m py_compile app/*.py tests/*.py scripts/*.py`
- Browser validation of `/ui` dashboard, company intelligence, knowledge graph and data center.
- `python3 scripts/check_handoffs.py`
- `git diff --check`

## Current State

- Completed: Shared helper layer added.
- Completed: Company intelligence core tables converted to insight view.
- Completed: Knowledge graph detail tables converted to insight view.
- Completed: Market-data table converted to OHLCV/source view.
- Completed: Static UI contract updated.
- Completed: Validation.
- Blocked: None.

## Dependencies

- Existing static UI.
- Existing API payloads.
- Running local app at `http://127.0.0.1:8000`.

## Blockers

- None.

## Files Touched

- `app/static/index.html`: display helpers, insight rows, advanced trace, core table render changes.
- `scripts/ui_static_check.py`: helper and text-snippet contract.
- `tasks/todo.md`: added T-490.
- `docs/agent-handoffs/2026-06-26-T-490-ui-information-denoise.md`: this handoff.

## Commands Run

```bash
python3 /home/xionglei/.codex/skills/ui-ux-pro-max/scripts/search.py "personal investment research dashboard information hierarchy compact table advanced details" --design-system -p "Personal Research Workbench"
python3 scripts/ui_static_check.py
python3 -m py_compile app/*.py tests/*.py scripts/*.py
docker compose restart ai-quant-org
Browser validation at http://127.0.0.1:8000/ui
python3 scripts/check_handoffs.py
git diff --check
```

Result:

- Passed: design-system query completed.
- Passed: `python3 scripts/ui_static_check.py` (`required_functions=139`, `required_ids=351`, `text_snippets=9`, `node_check=passed`).
- Passed: `python3 -m py_compile app/*.py tests/*.py scripts/*.py`.
- Passed: local service restarted with `docker compose restart ai-quant-org`.
- Passed: browser validation across dashboard, company intelligence, knowledge graph and market-data/K-line.
- Passed: final handoff validation and diff check in the T-491 closeout pass.

## Evidence

- Dashboard: default visible text did not expose naked `issuer_*` IDs.
- Company intelligence: key tables use `主题 / 关键发现 / 状态 / 下一步或证据`; AAPL fact table did not expose naked `issuer_*`; research table did not expose naked `rr ...`; raw payload is collapsed under advanced trace.
- Knowledge graph: selected node title showed `AAPL`, node trace is available in collapsed advanced details, and graph summary tables use the semantic insight headers.
- Market data: table uses `日期 / 开高低收 / 成交量 / 来源`; rights and record IDs are in advanced trace; `sec_000670` K-line rendered 162 SVG rectangles in the smoke check.
- Browser console: 0 errors after escaping advanced trace content.

## Decisions

- Keep raw traceability, but collapse it under advanced details.
- Do not change backend schemas in this phase.
- Focus first on highest-visibility user paths; deeper backend/admin tables can continue in follow-up phases using the same helpers.

## Risks and Open Questions

- Some secondary admin tables still contain compact internal references. They remain traceable but should be progressively converted in later passes.
- Advanced trace content must remain escaped because parsed report bodies may contain HTML-like image tags.

## Artifacts

- None.

## Handoff Checklist

- [x] Implementation completed.
- [x] Static contract updated.
- [x] Browser validation completed.
- [x] Final handoff validation passed.
- [x] Final diff check passed.

## Next Steps

1. Continue from the T-492 long-term completion queue.
2. Keep summary-first rendering and folded trace details as the default UI policy.
3. Preserve browser acceptance for the visible workbench path.

## Next Recommended Action

Continue with T-492 through T-503, linking product completion work to backend modularization and long-term maintainability.
