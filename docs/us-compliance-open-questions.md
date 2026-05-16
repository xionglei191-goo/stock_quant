# US Compliance Open Questions

## Scope

This note tracks US-market compliance questions for a research and simulated-portfolio system. Broker connectivity, derivatives trading, automated execution, and external asset management are explicit non-goals for the current project; the questions below are retained as boundary reminders, not as near-term implementation requirements.

## Reg FD

| Question | Current Stance | Owner |
|---|---|---|
| Can a source be traced to broad public disclosure? | Required before filing evidence enters a decision pack | Compliance |
| Are private meeting notes, roadshow notes, or expert calls allowed? | Manual reference only until source review approves ingestion | Compliance + CIO |
| Does the system keep public release timestamp and citation? | Required via `source_uri`, `published_at`, evidence locator, and audit log | Data Engineering |
| Can an agent summarize private or selectively disclosed material? | No, not into automated research answers or decision packs | Compliance |

## Nasdaq / NYSE Non-Display

| Question | Current Stance | Owner |
|---|---|---|
| Is data used by a machine without human display? | Treat as non-display and block automation unless the public source terms clearly allow it | Data + Compliance |
| Does derived data require separate declaration? | Treat as restricted unless public source terms clearly allow it | Compliance |
| Can real-time data feed scoring, routing, or alerts? | Not in MVP; use public/locally provided EOD or delayed data only | CIO |
| Are professional/non-professional entitlements relevant? | Must be checked before user-specific market data display | Platform |

## Investment Adviser And External Management

| Question | Current Stance | Owner |
|---|---|---|
| Is the system used only for internal research? | Current assumption: yes | CEO |
| Does output become individualized advice for clients? | Requires separate legal review | Legal |
| Are performance reports marketed externally? | Not allowed without review of adviser, advertising, and recordkeeping rules | CEO + Legal |
| Are model changes and prompts books-and-records material? | Treat as audit-retained governance records | Compliance |

## Broker Interfaces And Execution Boundary

| Question | Current Stance | Owner |
|---|---|---|
| Can `ExecutionIntent` connect directly to a broker? | No; it is a paper/simulation object only | CIO |
| Is order routing in scope? | No; do not implement live routing in this system | CEO + CIO |
| Are duplicate or stale intents blocked? | Useful for simulation hygiene; not a broker requirement | Platform |
| Is best execution policy documented? | Not required for current simulated-only scope; revisit only if the project scope changes | Compliance |

## Derivatives And Cross-Border

| Question | Current Stance | Owner |
|---|---|---|
| Are options, futures, swaps, or leveraged ETFs in scope? | Out of MVP scope | CIO |
| Are US, Hong Kong, and Mainland China cross-border restrictions mapped? | Open legal review item | Legal |
| Are currency controls, tax withholding, and short-sale rules covered? | Not yet; require separate workstream | Legal + Operations |
| Can ADR/A/H linked securities be traded as one exposure? | Research mapping only until legal and broker rules are reviewed | CIO |

## If Scope Ever Changes Toward Live US Execution

1. Written data-license matrix for SEC, market data, transcript, and research sources.
2. Reg FD source checklist attached to event and decision workflows.
3. Nasdaq/NYSE non-display declaration review for every real-time or derived-data use case.
4. Adviser, broker, best-execution, derivatives, and cross-border legal review.
5. Kill switch, duplicate-order guard, stale-intent guard, and incident playbook drill.

Until the project is explicitly re-scoped and these are complete, US-market functionality remains research, evidence, simulated portfolio, and human review workflow only.
