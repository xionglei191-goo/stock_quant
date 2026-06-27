# Multidimensional Relationship Closure

- Status: active
- Owner group: Product and UI, Data and Evidence
- Last updated: 2026-06-27
- Related tasks: T-504 through T-553
- Scope: Company-centered industry chain, peer/upstream/downstream, shareholder, shareholder-related company, and dynamic graph exploration closure.
- Non-goals: Real broker integration, automated trading, restricted data ingestion, and external production release evidence.

## Purpose

This document closes the user-facing multidimensional relationship objective: when viewing a company, the system should show industry-chain context, peer companies, upstream/downstream companies, shareholders or holders, companies connected to the same shareholder/holder, and allow those relationships to expand dynamically in the knowledge graph.

## Decisions

- The database does not need to be rebuilt for this objective.
- The relationship layer is a derived relationship context over existing domain records:
  - `CompanyRelationship`
  - `CompanyPosition`
  - `IndustryChain`
  - `InstitutionalHolding`
  - `/api/graph/query` graph edges
- New relationship data should be backfilled into these existing records through controlled builders, import paths, review queues, or future source connectors.
- Candidate relationships remain candidates until manual review promotes them to fact relationships.
- The system remains research-only, paper-only, and no-broker.

## Capability Matrix

| Requirement | Current capability | Evidence |
| --- | --- | --- |
| Company industry-chain context | `relationship_context.industry.chain_nodes` and UI “产业链位置” rows show chain/node context. | T-504, T-531 |
| Peer companies | `relationship_context.industry.peer_companies`, top peer count, direction trace, graph entry. | T-504, T-529, T-530, T-541, T-542 |
| Upstream companies | `relationship_context.industry.upstream_companies`, top upstream count, direction trace, graph entry. | T-504, T-529, T-530, T-541, T-542 |
| Downstream companies | `relationship_context.industry.downstream_companies`, top downstream count, direction trace, graph entry. | T-504, T-529, T-530, T-541, T-542 |
| Relationship coverage gaps | `coverage_diagnostics` reports missing required and optional layers with actionable targets. | T-505, T-534, T-535, T-536, T-537, T-538 |
| Shareholders and holders | `ownership.shareholders[]` displays 13F/holding holders with graph attributes and readable source labels. | T-532, T-539, T-552 |
| Local ownership import | UI supports ownership manifest preview, import preview, execution, review queue, and approval to active facts. | T-507 through T-512, T-550, T-551 |
| Approved fact ownership | Approved `*_candidate` ownership relationships become active fact relationships and appear separately from candidates. | T-512, T-513 |
| Same fact-shareholder related companies | Approved ownership facts generate `approved_shareholder_related_companies` and holder-key graph expansion. | T-514, T-515, T-519, T-525, T-526, T-527, T-528, T-540 |
| Same 13F holder related companies | Institutional holding holder key expands to same-holder graph and recommended query entries. | T-532, T-533, T-539, T-552 |
| Dynamic graph recommendations | `dynamic_graph.recommended_filters` and `recommended_queries[]` describe graph entry points. | T-521, T-522, T-523, T-524, T-542, T-544 |
| Visible graph filter state | Graph chips show active filters in readable labels and preserve raw trace values. | T-516, T-517, T-518, T-543, T-545 |
| Human-readable relationship labels | Relationship rows, review queue, graph edges, graph inspector, manifest, and import rows avoid raw enum display in primary columns. | T-546, T-547, T-548, T-549, T-550, T-551, T-552 |

## End-to-End User Flow

1. Load a company in the company intelligence workbench.
2. Read the “多维关系” counts for peers, upstream, downstream, shareholders, and shareholder-related companies.
3. Inspect missing relationship layers and click an action to build, import, review, or open the graph.
4. Generate or preview an ownership manifest from local files.
5. Preview and execute ownership relationship import.
6. Review imported candidate relationships.
7. Approve candidate ownership relationships into active fact relationships.
8. Return to the company view and see fact ownership relationships separately from candidates.
9. Click a fact shareholder, same fact-shareholder related company, 13F holder, or graph recommendation.
10. Inspect the dynamic graph with visible filter chips and Chinese relationship labels.

## Verification Evidence

Local-only T-553 closure evidence:

- `python3 -m py_compile app/*.py app/service_modules/*.py tests/*.py scripts/*.py`
  - Result: passed.
- Corrected focused relationship suite:
  - `python3 -m unittest tests.test_system.SystemServiceTests.test_company_intelligence_first_class_models_are_exposed_and_aggregated tests.test_system.SystemServiceTests.test_company_relationship_context_reports_missing_chain_layers tests.test_system.SystemServiceTests.test_approved_ownership_candidate_promotes_to_active_graph_relationship tests.test_system.SystemServiceTests.test_relationship_context_links_approved_same_shareholder_companies tests.test_system.SystemServiceTests.test_company_relationship_builder_reads_local_ownership_files tests.test_system.SystemServiceTests.test_company_ownership_manifest_template_api_previews_and_writes`
  - Result: passed, 6 tests.
- `python3 scripts/ui_static_check.py`
  - Result: passed with `required_ids=379`, `required_functions=162`, `text_snippets=39`, `node_check=passed`.
- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t553 --timeout 60`
  - Result: passed, 48/48 checks.
- `python3 scripts/check_handoffs.py`
  - Result: passed with 127 handoff files.
- `git diff --check`
  - Result: passed.

Prior local-only evidence from the closure sequence:

- `python3 scripts/ui_interaction_acceptance.py http://127.0.0.1:8000 --output-dir artifacts/ui-interaction-acceptance-t552 --timeout 60`
  - Result: passed, 48/48 checks.
  - Scope: browser-level company relationship context, ownership import, review, approval, graph expansion, graph chips, and readable labels.
- `python3 scripts/check_handoffs.py`
  - Result: passed with 126 handoff files after T-552.
- `git diff --check`
  - Result: passed after T-552.

## Remaining Non-Blocking Enhancements

These items do not block the current multidimensional relationship objective:

- Connect more real A-share ownership data sources such as top shareholders, controllers, subsidiaries, associates, exchange disclosures, and annual reports.
- Improve Chinese and English entity extraction, synonym merging, and source-quality scoring.
- Add larger sample acceptance over real local company packages and production-like external evidence URIs.
- Calibrate relationship coverage scoring with broader industry/company samples.

These are data-source and quality-depth extensions. The relationship model, UI workflow, graph exploration, review path, and trace contracts are already in place.

## Open Questions

- Which external data providers will be used for non-local A-share ownership tables.
- Whether future production release will require external graph/vector backend evidence for this relationship module.
- How strict the confidence threshold should be for automatic candidate generation before manual review.
