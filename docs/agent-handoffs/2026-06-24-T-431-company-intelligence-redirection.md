# Handoff: T-431 Company Intelligence Redirection

## Metadata

- Status: DONE
- Owner group: PM / Release Coordination
- Last updated: 2026-06-24
- Last agent: Codex
- Branch/worktree: local workspace, branch not assumed
- Related task: T-431
- Follow-up completion: `2026-06-24-T-432-company-intelligence-core-completion.md`

## Objective

Reposition the project from an organization/execution centered investment workflow into a company intelligence and market analysis platform. This T-431 handoff covers documentation and roadmap state only; business code changes, if present in the local worktree, belong outside this document-level handoff and should be reviewed under their own task before commit.

## Scope

- Rewrite the product entry narrative in `README.md`.
- Rewrite `docs/product-requirements-document.md`.
- Rewrite `docs/system-architecture.md`.
- Rewrite `docs/data-structure-design.md`.
- Update `docs/README.md`.
- Add T-431 through T-436 to `tasks/todo.md` as roadmap items, without marking downstream implementation tasks as completed by this documentation pass.
- Record this handoff and validate handoff formatting.

## Background

The user clarified that the desired system is not a fund-company workflow and not a real-time quantitative trading system. The target is a Palantir-like company intelligence platform that builds detailed stock/company databases, incorporates structured and unstructured evidence, tracks research report viewpoints, records analysis conclusions, and uses simulation only as feedback.

## Problem Statement

The previous primary documents framed the product around decision governance, committee packs, signatures, execution intent, and production readiness. That framing overemphasized organizational workflow and live-operation gates relative to the desired company-level data and analysis platform.

## Expected Deliverables

- Main product narrative states "公司情报与市场综合分析平台".
- Core workflow is `数据入湖 -> 公司画像 -> 事件时间线 -> 关系图谱 -> 多源观点 -> 观察任务 -> 分析结论 -> 模拟反馈`.
- Research reports are defined as attention signals, viewpoint samples, and analyst reliability review sources.
- Simulation is defined as paper-only feedback, not trading execution.
- Data structure docs define company profile, event, relationship, report viewpoint, observation, conclusion, and feedback models.
- Roadmap includes T-431 to T-436.

## Current Findings

- Existing code already has useful foundations: issuer/security records, evidence, reports, graph query, market data, simulated ledger, local storage, object store, search, LLM gateway, OCR fallback, and audit logs.
- Existing naming still contains legacy objects such as thesis, decision, execution intent, operating report, and organization dashboards.
- The new route should preserve those capabilities while migrating product language, schemas, and UI structure toward company intelligence.
- Current local worktree inspection showed non-document files already modified. This handoff does not validate or claim those code changes; they should be handled separately from T-431 if they are kept.

## Proposed Work Plan

1. Treat T-431 as document-level completion only.
2. Use `2026-06-24-T-432-company-intelligence-core-completion.md` for the completed implementation baseline covering T-432 through T-436.
3. Create new task IDs for deeper scoring, richer company pages, larger data quality automation, or external graph/vector adapter work.

## Validation Plan

- Run `python3 scripts/check_handoffs.py`.
- Do not run unit tests or `make local-ci` in this round because only Markdown and roadmap files changed.

## Risks

- Existing API and UI names still expose legacy decision/committee concepts, so later code work should use compatibility aliases instead of breaking clients abruptly.
- Research report extraction can create false confidence if report fields are treated as facts; follow the data boundary in `docs/data-structure-design.md`.
- Simulation feedback must remain visibly paper-only in UI and API contracts.

## Dependencies

- `AGENTS.md` documentation and handoff rules.
- Existing source governance and evidence back-link behavior.
- Existing research report asset registry and simulated ledger capabilities.

## Blockers

- None for T-431 documentation completion.
- Implementation tasks T-432 through T-436 were intentionally out of scope for this handoff and are now covered by `2026-06-24-T-432-company-intelligence-core-completion.md`.

## Handoff Checklist

- [x] Product positioning updated.
- [x] Architecture updated.
- [x] Data structure design updated.
- [x] Roadmap updated.
- [x] Docs index updated.
- [x] T-431 scope limited to Markdown documentation and roadmap updates.
- [x] Handoff validator run after file creation.

## Evidence

- `README.md`: product entry now describes a company intelligence and market analysis platform.
- `docs/product-requirements-document.md`: PRD rewritten around personal research users and company intelligence success metrics.
- `docs/system-architecture.md`: architecture rewritten around data, entity, event, relationship, viewpoint, and feedback layers.
- `docs/data-structure-design.md`: core keys and objects rewritten around company intelligence objects.
- `tasks/todo.md`: T-431 through T-436 roadmap added.
- `docs/README.md`: document index updated to highlight the new main docs.
- Command: `python3 scripts/check_handoffs.py`
- Result: passed, checked 6 markdown files in `docs/agent-handoffs`.

## Next Recommended Action

Refer to `2026-06-24-T-432-company-intelligence-core-completion.md` for the completed implementation baseline, then open new enhancement tasks instead of extending T-431.
