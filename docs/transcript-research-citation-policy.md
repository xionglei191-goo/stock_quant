# Transcript And Research Citation Policy

## Decision

Conference calls, transcripts, seller research, expert notes, and third-party summaries are not default training assets. They are citation and analyst-reference assets unless a contract explicitly grants broader use.

## Source Classes

| Source | Default Source ID | Use | Boundary |
|---|---|---|---|
| Company public webcast or IR transcript | `company_public_webcast` | Evidence, summary, citation | Public source URI required; no redistribution beyond citation snippets |
| Contracted transcript vendor | `authorized_transcript_vendor` | Internal analyst reference | No training, redistribution, derived data, or broad display unless contract allows |
| Contracted research vendor | `authorized_research_vendor` | Citation tracking and analyst reference | No model training or re-publication by default |
| Unverified notes or private meetings | none | Manual reference only | Block automated ingestion and route to compliance review |

## Required Metadata

Every transcript or research item must keep:

| Field | Requirement |
|---|---|
| `source_id` | Must map to an approved source definition |
| `source_uri` | Original public URL or vendor object reference |
| `document_type` | `transcript`, `webcast`, `presentation`, or `research` |
| `rights_tag` | Must not exceed source rights |
| `published_at` | Public release or vendor timestamp when available |
| `language` | `zh`, `en`, or `mixed` |
| `content_sha256` | Set by object storage when body is retained |

## Citation Rules

1. Prefer company-published public webcasts and official IR transcripts.
2. For vendor transcripts, cite metadata and minimal snippets only when the contract permits display.
3. For sell-side research, store title, source, analyst-facing note, and citation pointer; do not train models or redistribute text by default.
4. Any private meeting note, roadshow note, or unverified summary remains outside automated ingestion until compliance approves a source definition.
5. Research answers should preserve the original English evidence first and generate Chinese summaries second.

## Red Lines

- No transcript or research text enters training unless `training_allowed=true`.
- No vendor text is redistributed unless `redistribution_allowed=true`.
- No automated scoring from real-time or non-display market data unless `non_display_use=allowed`.
- No Reg FD-sensitive private disclosure enters a decision pack without compliance review.

## Review Cadence

Review transcript and research source contracts quarterly, and whenever a new vendor, new redistribution channel, or new model-training use case is proposed.
