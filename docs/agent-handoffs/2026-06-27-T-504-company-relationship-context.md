# Handoff: T-504 Company Relationship Context

## Metadata

- Status: DONE
- Owner group: Product and UI, Data and Evidence
- Reviewer groups: Research and AI Workflows, Platform and Quality
- Last updated: 2026-06-27
- Last agent: Codex
- Branch/worktree: local worktree `/home/xionglei/Project/sotck_quant`
- Related tasks: T-504

## Objective

Expose a company-centered multi-dimensional relationship context without rebuilding the database. The company intelligence view now shows industry position, peer companies, upstream/downstream companies, shareholders or holders, ownership candidates, and companies held by the same holder.

## Scope

- In scope: `/api/company-intelligence/{symbol}` aggregation, local graph expansion, company intelligence UI summary, API docs, roadmap status, focused regression.
- Out of scope: database migration, external data collection, real broker integration, automatic trading, upgrading candidate relationships to facts without review.

## Background

The user pointed out that the system had company profile, relationship, industry-chain, shareholder, and graph pieces, but did not present them as a complete company-centered exploration flow. The agreed direction was not to rebuild the database; instead, add relationship-layer backfill/read-model behavior and make it visible in the company intelligence UI.

## Problem Statement

Before this slice, company intelligence exposed raw `company_relationships`, `company_positions`, holdings, and `/api/graph/query`, but a user could not quickly answer: what chain segment is this company in, who are peers, who is upstream/downstream, who are holders, and what other companies those holders connect to.

## Expected Deliverables

- Additive `relationships.relationship_context` response under `/api/company-intelligence/{symbol}`.
- Multi-dimensional relationship summary in the company intelligence UI.
- Graph expansion for same-holder related companies.
- Disclosure extraction for shareholder/controller/investee candidates.
- Click-through from relationship context rows into `/api/graph/query` with `relationship_type`, `chain_id`, and `chain_node_id` filters.
- Structured local ownership input for top shareholders, controllers, subsidiaries, and investee companies through the existing relationship builder.
- CSV/TSV/Markdown local ownership table parsing into the same structured ownership input path.
- Explicit local ownership file import into the same table parsing path.
- CLI script for submitting explicit or glob-discovered local ownership files to the relationship builder.
- Path-based symbol inference for ownership file imports when explicit symbols are absent.
- JSON manifest mode for ownership file batches with per-file source metadata.
- Manifest template generation from ownership directories before API import.
- Focused regression proving peers, upstream/downstream, shareholders, ownership candidates, related holder companies, and graph edges.
- Docs and roadmap status updates.

## Current Findings

- Completed: Added `relationships.relationship_context` as a derived read model.
- Completed: Added company intelligence UI "多维关系" panel.
- Completed: Added focused regression for peers, upstream/downstream, shareholders, holder-related companies, and graph edges.
- Completed: Extended public disclosure relationship extraction to `shareholder_candidate`, `controller_candidate`, and `investee_candidate`; these now appear under `relationship_context.ownership.relationship_candidates`.
- Completed: Added relationship-context click-through into the dynamic graph view; industry rows carry chain filters and company relationship rows carry relationship-type filters.
- Completed: Added `structured_ownership_relationships` / `ownership_relationships` input to `POST /api/company-database/relationships/build`; local A-share top shareholders, controllers, subsidiaries, and investee rows can now be normalized into review-required company relationship candidates.
- Completed: Added `ownership_csv`, `ownership_tsv`, `ownership_table_text`, and `structured_ownership_tables` parsing for local CSV/TSV/Markdown ownership tables with Chinese/English header normalization.
- Completed: Added `ownership_file_paths` / `ownership_files` for explicitly supplied local ownership files, with extension, file-count, and file-size guards plus `ownership_file_inputs` parse summaries.
- Completed: Added `scripts/import_company_ownership_tables.py` as the dry-run-first CLI entrypoint for local ownership file import, including explicit `--files` and bounded `--glob` discovery.
- Completed: Added path-based symbol inference in the ownership import script for common A-share and US ticker filename patterns when `--symbols` is omitted.
- Completed: Added `--manifest` support to the ownership import script so file batches can carry per-file symbol, source, source table, and default relationship kind metadata.
- Completed: Added `--write-manifest-template` support so local ownership directories can produce editable manifest drafts without calling the API.
- Not started: automated external ingestion of A-share top ten shareholders, fully governed controllers, subsidiaries, and investee-company source tables.
- Finding: richer shareholder data depends on governed public filings or user-provided local data.

## Proposed Work Plan

1. Keep `CompanyRelationship`, `CompanyPosition`, `IndustryChain`, and `InstitutionalHolding` as source records.
2. Derive company-centered relationship context in `app/service_modules/company_intelligence.py`.
3. Assemble the context in `SystemService.company_intelligence` without storage migration.
4. Render the summarized context in the company intelligence UI.
5. Let relationship context rows open a scoped graph exploration path.
6. Convert explicit local structured ownership rows into review-required `CompanyRelationship` candidates.
7. Parse local ownership CSV/TSV/Markdown tables into the same structured ownership rows.
8. Read explicit local ownership files into the same table parsing path with bounded file guards.
9. Provide a script-level local workflow for submitting ownership files.
10. Infer target symbols from ownership file paths when explicit symbols are absent.
11. Support JSON ownership manifests with per-file metadata.
12. Generate editable JSON ownership manifest templates from local directories.
13. Lock behavior with focused regression and static UI checks.

## Validation Plan

Run:

```bash
python3 -m py_compile app/*.py app/service_modules/*.py tests/*.py scripts/*.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_relationship_builder_creates_listing_and_coverage_links tests.test_system.SystemServiceTests.test_company_relationship_builder_accepts_structured_ownership_rows tests.test_system.SystemServiceTests.test_company_relationship_builder_parses_local_ownership_tables tests.test_system.SystemServiceTests.test_company_relationship_builder_reads_local_ownership_files tests.test_system.SystemServiceTests.test_company_ownership_table_import_script_uses_relationship_builder tests.test_system.SystemServiceTests.test_company_ownership_table_import_script_infers_symbol_from_path tests.test_system.SystemServiceTests.test_company_ownership_table_import_script_uses_manifest_metadata tests.test_system.SystemServiceTests.test_company_ownership_table_import_script_builds_manifest_template tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated
python3 scripts/ui_static_check.py
python3 scripts/check_handoffs.py
git diff --check
```

Full unit suite and browser acceptance are optional for this slice because the behavior is an additive read model plus summary UI; focused regression and static UI contract cover the new path.

## Risks

- Existing 13F holdings are only a holder proxy and do not fully represent statutory shareholders.
- Public disclosure ownership candidates are not facts until reviewed.
- Upstream/downstream and peer derivation depends on existing `CompanyPosition` and `IndustryChain` quality.
- Candidate company relationships still need review before being treated as facts.

## Dependencies

- Local persisted company records: `CompanyRelationship`, `CompanyPosition`, `IndustryChain`, `InstitutionalHolding`, `Issuer`, `Security`.
- Existing `/api/company-intelligence/{symbol}` and `/api/graph/query` behavior.
- UI static contract in `scripts/ui_static_check.py`.

## Blockers

- No blocker for the delivered slice.
- Future richer shareholder/controller coverage is blocked on governed public filing ingestion or user-provided local data.

## SystemService Growth Freeze Review

- New `SystemService` business logic added: No. The relationship classification and derived context live in `app/service_modules/company_intelligence.py`.
- Domain module used: Yes, `company_intelligence.relationship_context` owns the deterministic aggregation; `company_intelligence.ownership_rows_from_payload` parses table inputs; `company_intelligence.structured_ownership_relationship_specs` owns structured ownership row normalization.
- `SystemService` changes: API aggregation assembly, graph edge expansion, additive `/api/graph/query` relationship-type filtering, bounded local ownership file reading, and relationship-builder orchestration for structured ownership rows only, preserving facade behavior.
- Focused regression: `tests.test_system.SystemServiceTests.test_company_relationship_builder_creates_listing_and_coverage_links`, `tests.test_system.SystemServiceTests.test_company_relationship_builder_accepts_structured_ownership_rows`, `tests.test_system.SystemServiceTests.test_company_relationship_builder_parses_local_ownership_tables`, `tests.test_system.SystemServiceTests.test_company_relationship_builder_reads_local_ownership_files`, `tests.test_system.SystemServiceTests.test_company_ownership_table_import_script_uses_relationship_builder`, `tests.test_system.SystemServiceTests.test_company_ownership_table_import_script_infers_symbol_from_path`, `tests.test_system.SystemServiceTests.test_company_ownership_table_import_script_uses_manifest_metadata`, `tests.test_system.SystemServiceTests.test_company_ownership_table_import_script_builds_manifest_template`, and `tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated`.
- API schema changed: additive only, `relationships.relationship_context` and optional `/api/graph/query relationship_type`.
- Storage schema changed: No.
- UI behavior changed: additive "多维关系" panel in company intelligence and row click-through into the dynamic graph view.
- Paper-only/no-broker boundary changed: No.

## Handoff Checklist

- [x] Code changes completed
- [x] Tests/checks run or explicitly skipped with reason
- [x] Docs/contracts updated
- [x] `tasks/todo.md` status updated
- [x] No known unrelated user changes reverted

## Evidence

Commands run:

```bash
python3 -m py_compile app/service_modules/company_intelligence.py app/services.py
python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated
python3 -m unittest tests.test_system.SystemServiceTests.test_company_relationship_builder_creates_listing_and_coverage_links tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated
python3 -m unittest tests.test_system.SystemServiceTests.test_company_relationship_builder_creates_listing_and_coverage_links tests.test_system.SystemServiceTests.test_company_relationship_builder_accepts_structured_ownership_rows tests.test_system.SystemServiceTests.test_company_relationship_builder_parses_local_ownership_tables tests.test_system.SystemServiceTests.test_company_relationship_builder_reads_local_ownership_files tests.test_system.SystemServiceTests.test_company_ownership_table_import_script_uses_relationship_builder tests.test_system.SystemServiceTests.test_company_ownership_table_import_script_infers_symbol_from_path tests.test_system.SystemServiceTests.test_company_ownership_table_import_script_uses_manifest_metadata tests.test_system.SystemServiceTests.test_company_ownership_table_import_script_builds_manifest_template tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated
python3 -m py_compile app/*.py app/service_modules/*.py tests/*.py scripts/*.py
python3 scripts/ui_static_check.py
python3 scripts/check_handoffs.py
git diff --check
```

Results:

- Passed: all commands above.
- Initial focused test failed because the sample chain id contained the ticker token and text matching pulled all sample positions; fixed by renaming the sample chain id.
- Continue pass found ownership bucketing did not include controller/investee; fixed `_relationship_bucket` and re-ran the two focused tests successfully.
- Continue pass added graph query filtering by `relationship_type` and static UI-covered click-through attributes for relationship context rows.
- Continue pass added structured local ownership input through the relationship builder, keeping all resulting shareholder/controller/subsidiary/investee rows as review-required candidates.
- Continue pass added local ownership table parsing for CSV, TSV, and Markdown pipe tables, including Chinese headers and percentage normalization.
- Continue pass added explicit local ownership file input with bounded extension/count/size handling and dry-run parse summaries.
- Continue pass added a dry-run-first local ownership import script that submits explicit or glob-discovered files to the same relationship builder and writes a local artifact.
- Continue pass added path-based symbol inference for ownership imports, while preserving explicit `--symbols` precedence.
- Continue pass added ownership JSON manifest support for batch source metadata.
- Continue pass added ownership manifest template generation without API calls.
- Artifact boundary: no new local artifact files; evidence is test output and tracked code/docs.

Files touched:

- `app/service_modules/company_intelligence.py`: relationship context domain aggregation, ownership table parsing, and structured ownership row normalization.
- `app/services.py`: context assembly, disclosure ownership candidate extraction, same-holder graph expansion, graph relationship-type filtering, local ownership file reading, and builder orchestration for structured ownership rows.
- `app/static/index.html`: multi-dimensional relationship panel, renderer, and graph click-through.
- `scripts/import_company_ownership_tables.py`: dry-run-first local ownership file import CLI with explicit file, glob discovery, manifest, template generation, and optional path-based symbol inference modes.
- `tests/test_system.py`: focused regression.
- `docs/api-contracts.md`: API contract update.
- `tasks/todo.md`: T-504 roadmap record.

## Next Recommended Action

Add automated governed shareholder/controller and subsidiary/investee source fetchers that write local ownership files or `structured_ownership_relationships`, then add browser interaction acceptance for clicking relationship-context rows into the dynamic graph view.
