# US Compliance Open Questions

## Scope

This note tracks US-market compliance questions that must be answered before the system moves from research assistance to external asset management, broker connectivity, derivatives trading, or automated execution.

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
| Is data used by a machine without human display? | Treat as non-display until vendor confirms otherwise | Data + Compliance |
| Does derived data require separate declaration? | Treat as restricted unless contract says allowed | Compliance |
| Can real-time data feed scoring, routing, or alerts? | Not in MVP; use EOD/delayed/authorized research data only | CIO |
| Are professional/non-professional entitlements relevant? | Must be checked before user-specific market data display | Platform |

## Investment Adviser And External Management

| Question | Current Stance | Owner |
|---|---|---|
| Is the system used only for internal research? | Current assumption: yes | CEO |
| Does output become individualized advice for clients? | Requires separate legal review | Legal |
| Are performance reports marketed externally? | Not allowed without review of adviser, advertising, and recordkeeping rules | CEO + Legal |
| Are model changes and prompts books-and-records material? | Treat as audit-retained governance records | Compliance |

## Broker Interfaces And Execution

| Question | Current Stance | Owner |
|---|---|---|
| Can `ExecutionIntent` connect directly to a broker? | No; it is a paper/manual intent in MVP | CIO |
| What approvals are required before order routing? | DecisionPack approval, execution policy, kill switch, broker review | CEO + CIO |
| Are duplicate or stale intents blocked? | Required before broker integration | Platform |
| Is best execution policy documented? | Open item before any live routing | Compliance |

## Derivatives And Cross-Border

| Question | Current Stance | Owner |
|---|---|---|
| Are options, futures, swaps, or leveraged ETFs in scope? | Out of MVP scope | CIO |
| Are US, Hong Kong, and Mainland China cross-border restrictions mapped? | Open legal review item | Legal |
| Are currency controls, tax withholding, and short-sale rules covered? | Not yet; require separate workstream | Legal + Operations |
| Can ADR/A/H linked securities be traded as one exposure? | Research mapping only until legal and broker rules are reviewed | CIO |

## Required Before Live US Execution

1. Written data-license matrix for SEC, market data, transcript, and research sources.
2. Reg FD source checklist attached to event and decision workflows.
3. Nasdaq/NYSE non-display declaration review for every real-time or derived-data use case.
4. Adviser, broker, best-execution, derivatives, and cross-border legal review.
5. Kill switch, duplicate-order guard, stale-intent guard, and incident playbook drill.

Until these are complete, US-market functionality remains research, evidence, paper portfolio, and human committee workflow only.
