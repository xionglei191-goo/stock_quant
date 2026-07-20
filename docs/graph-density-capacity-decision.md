# Knowledge Graph Density and Renderer Capacity Decision

- Status: active; local-only evidence
- Owner group: Data and Evidence
- Last updated: 2026-07-18
- Related tasks: T-566, T-597
- Scope: governed local graph-layer density, cross-layer links, and renderer migration thresholds
- Non-goals: importing facts, changing graph UI/runtime, proving non-local production capacity, or approving Canvas/WebGL without governed browser evidence

## Purpose

This document records the T-597 evidence boundary and the decision for retaining
SVG, adding visible-graph virtualization, or migrating to Canvas/WebGL. It keeps
governed records, seed/fixture records, model estimates, synthetic benchmarks,
and real browser measurements separate.

## Facts

The read-only audit scanned three local SQLite stores through SQLite URI
`mode=ro` and found three subjects:

| Subject | Classification | Governed rows | Seed/fixture rows | Governed layers | Cross-layer links | Raw model estimate |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| AAPL / Apple Inc. | governed, with local fallback contamination separated | 2,375 | 9 | 2/9 (document, evidence) | 2/2 eligible document-evidence links | 2,386 nodes / 2,387 edges |
| DEMO / Demo Holdings | seed/fixture | 0 | 7 | 0/9 | 1/2 eligible links | 9 nodes / 13 edges |
| 000001 value-case subject | unclear; no graph-layer records | 0 | 0 | 0/9 | no eligible links | 2 nodes / 1 edge |

The AAPL governed rows consist of one real SEC document and 2,374 evidence
slices. One `local://samples/...fallback` document and its eight evidence slices
are classified as fixture and excluded from governed density. AAPL has no
governed company profile, industry position, relationship, holding, event,
research report, or viewpoint layer in the audited store.

Therefore, the repository does not yet contain multiple subjects with governed
multi-layer knowledge graphs. It has one deep document/evidence subject, one
explicit demo graph, and one subject without graph-layer records. T-597 measures
this gap; it does not close it by inventing data.

Existing browser artifacts are all seed/acceptance evidence. The measured curve
used by this decision is:

| Subject/scope | Nodes | Edges | FPS | Average frame | Evidence class |
| --- | ---: | ---: | ---: | ---: | --- |
| AAPL local | 36 | 60 | 60.01 | 1.91 ms | seed/acceptance |
| NVDA local | 36 | 73 | 60.03 | 1.85 ms | seed/acceptance |
| 600519 local | 33 | 88 | 60.02 | 1.84 ms | seed/acceptance |
| AAPL global | 88 | 182 | 52.74 | 3.81 ms | seed/acceptance |

These measurements prove SVG is adequate for the tested bounded fixture views.
They do not prove performance for the 2,386-node governed AAPL raw model or for
multiple governed subjects.

## Decisions

1. Retain SVG for the currently bounded visible graph.
2. Treat the governed AAPL raw model as a trigger for visible-graph
   virtualization/culling, because full materialization exceeds the base SVG
   tier. This is a model-size decision, not a browser performance claim.
3. Do not approve Canvas or WebGL migration yet. No governed real-data browser
   run has crossed a visible threshold or failed the frame budget.
4. Use these explicit gates:

| Tier | Trigger |
| --- | --- |
| SVG | <=250 visible nodes, <=500 visible edges, >=45 FPS, <=16.7 ms average frame |
| SVG with virtualization | <=750 visible nodes and <=1,500 visible edges, or raw model exceeds the base SVG tier while visible graph stays bounded |
| Canvas candidate | >750 visible nodes, >1,500 visible edges, or <45 FPS / >16.7 ms average frame for three governed-data runs |
| WebGL candidate | >3,000 visible nodes, >6,000 visible edges, or Canvas fails the same governed browser gate |

5. Synthetic Python adjacency preparation is retained only as an example/model
   complexity curve. It is not DOM, Canvas, WebGL, layout, or browser evidence.

## Assumptions

- The audited SQLite files are representative of the current local evidence
  available in this worktree, not every possible external or unmounted store.
- A visible graph can remain materially smaller than the raw graph through
  subject scoping, evidence aggregation, culling, and expansion on demand.
- Renderer migration cost is justified by governed visible-graph measurements,
  not by seed datasets or raw database row counts alone.

## Open Questions

- Which second and third governed subjects will receive document, event,
  relationship, research report, viewpoint, and evidence cross-links?
- Should thousands of evidence slices render individually, or aggregate first
  by document, section, topic, or semantic cluster?
- Can T-599 expose a browser acceptance input that uses the existing governed
  AAPL store without modifying UI source or importing fixture data?
- Does a governed AAPL run remain above 45 FPS after the visible graph is capped
  at 250/500 and expanded incrementally?

## Reproduction

```bash
python3 scripts/graph_density_capacity_audit.py \
  --state-db data/state.db \
  --state-db data/local/sec_single_name_ui.db \
  --state-db data/local/value-case-t573.sqlite \
  --browser-artifact artifacts/ui-graph-multi-symbol-acceptance-aapl-local.json \
  --browser-artifact artifacts/ui-graph-multi-symbol-acceptance-nvda-local.json \
  --browser-artifact artifacts/ui-graph-multi-symbol-acceptance-600519-local.json \
  --browser-artifact artifacts/ui-graph-multi-symbol-acceptance-aapl-global.json \
  --output artifacts/graph-density-capacity-audit.json
```

Artifact:

- `artifacts/graph-density-capacity-audit.json`: local-only, generated
  2026-07-18 by the command above; owner Data and Evidence; no secrets; not
  acceptable for non-local production gates.
