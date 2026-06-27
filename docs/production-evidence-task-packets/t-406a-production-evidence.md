# Production Evidence Task Packet: T-406A

- Status: blocked_external_evidence
- Owner role: 分析师
- Owner group: Research and AI Workflows
- Last updated: 2026-06-27
- Related task: T-406A
- Scope: collect real external staging/production evidence for this task
- Non-goals: local-only release approval, generating or fabricating evidence, broker integration, automatic trading

## Objective

Collect and archive the external evidence required to unblock `T-406A` for non-local production closure.

## Readiness Endpoint

- `/api/hotspots/readiness-report`

## External Blockers

- real hotspot query/gold reference LLM rerank evaluation

## Required Artifact Fields

- `query_gold_refs_uri`
- `llm_rerank_eval_uri`
- `company_position_review_uri`
- `chain_taxonomy_review_uri`

## URI Template

- `query_gold_refs_uri`: `s3://<production-evidence-bucket>/<release-id>/T-406A/query_gold_refs_uri`
- `llm_rerank_eval_uri`: `s3://<production-evidence-bucket>/<release-id>/T-406A/llm_rerank_eval_uri`
- `company_position_review_uri`: `s3://<production-evidence-bucket>/<release-id>/T-406A/company_position_review_uri`
- `chain_taxonomy_review_uri`: `s3://<production-evidence-bucket>/<release-id>/T-406A/chain_taxonomy_review_uri`

## Collection Procedure

- Collect hotspot query/gold refs and offline rerank evaluation without invoking live trading or broker workflows.
- Attach company positioning and industry-chain taxonomy review artifacts required by `/api/hotspots/readiness-report`.
- Prove persisted or reviewed research tasks through the readiness report gates, not through a standalone queue URI.

## Minimum Artifact Contents

- Hotspot gold refs artifact, rerank evaluation sample count, top-1 accuracy, and model/fallback version.
- Company positioning review and chain taxonomy review artifacts accepted by the readiness endpoint.
- Evidence that research tasks are persisted or explicitly reviewed while automation remains disabled.

## Reviewer Routing

- Data and Evidence
- Governance, Security, and Compliance

## Source And Boundary Rules

- Evidence must come from the declared external staging/production environment.
- Preserve local-first and paper-only boundaries; do not include broker credentials, live order execution, or automatic trading evidence.
- Redact secrets, tokens, signed URLs, private keys, and personal credentials before archiving.
- Restricted or boundary-unclear research content may be metadata/manual-reference evidence only, not training data or automated fact evidence.

## Acceptance

- Every URI is a concrete external staging/production archive URI.
- No URI is local-only, demo, localhost, `file://`, `local://`, or `artifact://staging-local`.
- Artifact inventory records sha256, size, environment, producer, owner, retention, and immutable/object-lock metadata.
- The filled evidence plan passes `scripts/production_evidence_plan_check.py --require-filled-uris`.
- The strict release gate passes before any task status is changed to DONE.

## Commands

```bash
python3 scripts/production_evidence_plan_check.py artifacts/production-evidence-collection-plan.json --require-filled-uris
python3 scripts/production_artifact_inventory_check.py artifacts/production-artifact-inventory.json --plan artifacts/production-evidence-collection-plan.json --evidence-package artifacts/readiness-evidence-package.json --manifest artifacts/production-closure-manifest.json
python3 scripts/production_release_gate.py --plan artifacts/production-evidence-collection-plan.json --evidence-package artifacts/readiness-evidence-package.json --artifact-inventory artifacts/production-artifact-inventory.json --artifact-bundle-root artifacts/production-evidence-bundle --manifest-output artifacts/production-closure-manifest.json
```
