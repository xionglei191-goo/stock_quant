# Production Evidence Task Packet: T-421

- Status: blocked_external_evidence
- Owner role: 风险/合规
- Owner group: Governance, Security, and Compliance
- Last updated: 2026-06-27
- Related task: T-421
- Scope: collect real external staging/production evidence for this task
- Non-goals: local-only release approval, generating or fabricating evidence, broker integration, automatic trading

## Objective

Collect and archive the external evidence required to unblock `T-421` for non-local production closure.

## Readiness Endpoint

- `/api/governance/security-readiness-report`

## External Blockers

- external KMS/secret manager evidence
- external API key least privilege review
- object store/search external delete executor evidence

## Required Artifact Fields

- `secret_manager_evidence_uri`
- `least_privilege_policy_uri`
- `external_delete_evidence_uri`
- `permission_review_uri`

## URI Template

- `secret_manager_evidence_uri`: `s3://<production-evidence-bucket>/<release-id>/T-421/secret_manager_evidence_uri`
- `least_privilege_policy_uri`: `s3://<production-evidence-bucket>/<release-id>/T-421/least_privilege_policy_uri`
- `external_delete_evidence_uri`: `s3://<production-evidence-bucket>/<release-id>/T-421/external_delete_evidence_uri`
- `permission_review_uri`: `s3://<production-evidence-bucket>/<release-id>/T-421/permission_review_uri`

## Collection Procedure

- Collect secret/KMS evidence as metadata only; never archive secret values, tokens, private keys, or signed URLs.
- Run external delete evidence from the approved executor identity and capture permission-denied/audit or red-team proof.
- Verify scoped API permissions, key rotation evidence, and object/search delete behavior in the external environment.

## Minimum Artifact Contents

- Secret manager/KMS metadata with no secret values, provider scope, key rotation evidence, and least-privilege policy.
- External delete executor identity, object/search delete result, and audit trail.
- Permission review or red-team proof with no credentials in artifacts.

## Reviewer Routing

- Platform and Quality
- PM / Release Coordination

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
