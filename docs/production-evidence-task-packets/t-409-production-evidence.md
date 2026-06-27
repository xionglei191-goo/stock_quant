# Production Evidence Task Packet: T-409

- Status: blocked_external_evidence
- Owner role: CIO
- Owner group: Research and AI Workflows / Portfolio
- Last updated: 2026-06-27
- Related task: T-409
- Scope: collect real external staging/production evidence for this task
- Non-goals: local-only release approval, generating or fabricating evidence, broker integration, automatic trading

## Objective

Collect and archive the external evidence required to unblock `T-409` for non-local production closure.

## Readiness Endpoint

- `/api/portfolio/optimizer/readiness-report`

## External Blockers

- production PyPortfolioOpt/CVXPY solver comparison
- solver version/parameter artifact

## Required Artifact Fields

- `solver_artifact_uri`
- `comparison_report_uri`
- `constraint_report_uri`

## URI Template

- `solver_artifact_uri`: `s3://<production-evidence-bucket>/<release-id>/T-409/solver_artifact_uri`
- `comparison_report_uri`: `s3://<production-evidence-bucket>/<release-id>/T-409/comparison_report_uri`
- `constraint_report_uri`: `s3://<production-evidence-bucket>/<release-id>/T-409/constraint_report_uri`

## Collection Procedure

- Run the production PyPortfolioOpt/CVXPY solver comparison with declared versions and parameters.
- Capture constraint reports and comparison output using paper-only portfolio inputs.
- Record infeasible-solver handling and reviewer sign-off.

## Minimum Artifact Contents

- Solver version, parameter artifact, and reproducible input snapshot.
- Comparison report and constraint report.
- Paper-only/no-order-execution boundary statement.

## Reviewer Routing

- Platform and Quality
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
