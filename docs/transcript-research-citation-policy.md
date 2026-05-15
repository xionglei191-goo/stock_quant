# Transcript And Research Citation Policy

## Decision

Conference calls, transcripts, seller research, expert notes, and third-party summaries are not default training assets. Use company-published public materials and the local research library first; unclear or private materials remain manual-reference only.

## Source Classes

| Source | Default Source ID | Use | Boundary |
|---|---|---|---|
| Company public webcast or IR transcript | `company_public_webcast` | Evidence, summary, citation | Public source URI required; no redistribution beyond citation snippets |
| Manual transcript reference | `manual_reference_transcripts` | Manual analyst reference | No automated ingestion, training, redistribution, derived data, or broad display |
| Local research library | `local_research_reports` | Citation tracking and analyst reference | No model training or re-publication by default |
| Unverified notes or private meetings | none | Manual reference only | Block automated ingestion and route to compliance review |

## Required Metadata

Every transcript or research item must keep:

| Field | Requirement |
|---|---|
| `source_id` | Must map to an approved source definition |
| `source_uri` | Original public URL or local object reference |
| `document_type` | `transcript`, `webcast`, `presentation`, or `research` |
| `rights_tag` | Must not exceed source rights |
| `published_at` | Public release or file timestamp when available |
| `language` | `zh`, `en`, or `mixed` |
| `content_sha256` | Set by object storage when body is retained |

## Citation Rules

1. Prefer company-published public webcasts and official IR transcripts.
2. For manual transcript references, keep metadata only through `/api/research/manual-references` and route to human review.
3. For sell-side research in the local library, store title, source, analyst-facing note, and citation pointer; do not train models or redistribute text by default.
4. Any private meeting note, roadshow note, or unverified summary remains outside automated ingestion until compliance approves a source definition.
5. Research answers should preserve the original English evidence first and generate Chinese summaries second.

## Red Lines

- No transcript or research text enters training unless `training_allowed=true`.
- No local or third-party text is redistributed unless `redistribution_allowed=true`.
- No automated scoring from real-time or non-display market data unless `non_display_use=allowed`.
- No Reg FD-sensitive private disclosure enters a decision pack without compliance review.
- No private meeting, roadshow, expert note, or unclear transcript text is accepted by the manual reference endpoint; only metadata and source pointer are retained.

## Review Cadence

Review public source provenance, TOS/robots, cache retention, redistribution, and model-training use cases quarterly.
