# Production Evidence Task Packet: T-414

- Status: blocked_external_evidence
- Owner role: 风险/合规
- Owner group: Governance, Security, and Compliance
- Last updated: 2026-06-27
- Related task: T-414
- Scope: collect real external staging/production evidence for this task
- Non-goals: local-only release approval, generating or fabricating evidence, broker integration, automatic trading

## Objective

Collect and archive the external evidence required to unblock `T-414` for non-local production closure.

## Readiness Endpoint

- `/api/research/citation-boundary/readiness-report`

## External Blockers

- citation boundary policy review artifact
- source review artifact
- manual reference reviewed-empty artifact where applicable

## Required Artifact Fields

- `citation_policy_uri`
- `source_review_uri`
- `manual_reference_review_uri`
- `research_governance_uri`

## URI Template

- `citation_policy_uri`: `s3://<production-evidence-bucket>/<release-id>/T-414/citation_policy_uri`
- `source_review_uri`: `s3://<production-evidence-bucket>/<release-id>/T-414/source_review_uri`
- `manual_reference_review_uri`: `s3://<production-evidence-bucket>/<release-id>/T-414/manual_reference_review_uri`
- `research_governance_uri`: `s3://<production-evidence-bucket>/<release-id>/T-414/research_governance_uri`

## Collection Procedure

- Review citation length policy, source review coverage, restricted-source handling, and manual-reference metadata-only behavior.
- Use `citation_policy_uri` for the policy artifact accepted by `/api/research/citation-boundary/readiness-report`.
- Record reviewed-empty evidence where no manual-reference bodies are allowed.

## Minimum Artifact Contents

- Citation policy artifact, source review coverage report, and manual-reference review artifact.
- Restricted-source exclusion and metadata-only proof.
- Research governance artifact showing no restricted training or unsupported citation behavior.

## Reviewer Routing

- Research and AI Workflows
- Data and Evidence

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
