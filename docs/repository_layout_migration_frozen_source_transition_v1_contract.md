# Repository layout migration: frozen-source transition and root-dependency consolidation V1

Owner milestone: `REPOSITORY_LAYOUT_MIGRATION — FROZEN-SOURCE AND ROOT-DEPENDENCY CONSOLIDATION`.
Base: `92fe761287f08d97ab88602dbe9349ab656a1fe6` (main after PR188). Authority effect: NONE.
Source ownership, imports and source-identity records only. Local commits are authorized;
push, PR, merge, Daily and production writes are not.

## Classification at the base

Every root module was classified with the unchanged E0 analyzer, the E2/E3 pins, the source
transition manifests, the E4 V1/V2 inputs, the provider worker bundle, the path-launcher
manifest, the historically executed sources and the Consumer/Dashboard imports (Consumer
`ffd68af`, Dashboard `2f67650`). A module may carry several labels.

| Class | Meaning | Base (258) | Now (218) |
|---|---|---:|---:|
| A | reachable from a reviewed Daily launcher | 211 | 185 |
| B | frozen hash-bound active source | 25 | 25 |
| C | used only by tools/tests (historical replay) | 36 | 29 |
| D | required filename/path launcher or compatibility entrypoint | 21 | 21 |
| E | name or file imported by the Consumer or mirrored by the Dashboard | 16 | 16 |
| F | held at root only by another root dependency | 224 | 184 |
| G | historical identity (executed-source import, E4 digest, provider bundle, E5) | 55 | 55 |

Highest-leverage blockers left: `vn_time`, `runtime_paths`, `provider_execution_guard`
(E2/E3 pins and provider bundle), `field_temporal_contract` (E5 keeps its temporal classes
and the TemporalField stable-ID patch slot), `bounded_artifact_stream`, `session_bar_integrity`,
`governed_session_chain`, `prospective_pit_capture_retention`, `daily_session_level2_package`
(E4 V1 code-digest inputs) and `semantic_evidence_bridge` (E6 admission).

## Versioned source transition

`canonical_daily_operation.py`, `canonical_post_close_pipeline.py`, `stocklookup.py` and
`tools/run_owner_daily.py` are already governed by existing source transitions. They change
import lines only. [The transition record](../tests/fixtures/repository_layout_source_transition_v1.json)
archives their exact base bytes, records the base digest (the digest each governing manifest
declared before), the live digest and the unchanged E2/E3 pin. Each governing manifest now
declares the live digest; historical pins and archives are untouched and remain the only
historical bytes. `tools/verify_retention_reader_transition.layout_transition_identity` hashes
every file on every call; a receipt for the base or original digest never proves the live source.
Bounded-caller AST digests were refreshed only after asserting identical invocation paths and
argv references. A test proves the non-import AST and every bound import name are unchanged.

## Families and owners

[The relocation fixture](../tests/fixtures/repository_layout_migration_20261025_relocations.json)
lists 40 modules that left the root with no copy, in six cohorts, and 16 root re-export
interfaces. Owners follow the dependency policy: provider access beside the existing EODHD
access in acquisition; universe, PIT, route and classification evidence in evidence; financial
classification, coverage and sidecars in financial; AI-handoff and research contexts in
research; presentation, queue and workspace read models in decision; VNM backtest in portfolio.

Each interface is one explicit import of the owner's objects, kept only because frozen or
historically executed importers use the root name. Owner classes and functions keep the
historical `__module__` (V5/V6 precedent), so pickles and identity checks resolve. Frozen
importers keep the root name; package importers bind the owner. Repository-root path anchors
in moved files resolve the same directories.

Not moved: `current_official_event_context` (moving it changes the E5 restored-cut coupling
assertion); the E6 financial OCR/statement family (E6 uses honest module names and its own
patch seams); `release_session_contract`/`trusted_subset_contract` (Dashboard mirrored files);
`financial_mapping`/`news_ticker_mapping` (Consumer file-path loads).

## Measurements (same analyzer and settings)

| Measure | Base | Now |
|---|---:|---:|
| Root Python files | 258 | 218 |
| Root implementation modules | 254 | 198 |
| Root re-export interfaces | 4 | 20 |
| Core-to-root edge rows / module pairs | 102 / 101 | 84 / 83 |
| Backward edge rows / pairs | 138 / 135 | 120 / 117 |
| Eager / runtime SCCs (participants) | 1 / 11 (41) | 1 / 11 (41) |
| Runtime cycle edges / unresolved dynamic | 61 / 9 | 61 / 9 |
| Path-launch targets moved | — | 0 |

No new package, registry, framework, cycle or carried-debt row. The sealed E0 baseline, policy,
E2/E3 pins, E4 V1/V2 inputs and digests, provider bundle and launcher targets are unchanged.

## Validation and release

Full hermetic suite against the base: 12,818 pass / 578 environment failures (absent retained
evidence) / 214 skip at the base; the same 578 IDs fail at each checkpoint and no new ID fails.
A static parity check shows all 56 moved or owner modules are identical to their base files
modulo import lines, path anchors and the identity trailer, and 92 other changed files are
import-only. No Daily, provider or production operation was run. No maintenance window is
needed: the change is source layout only, and Daily picks it up through the normal release
and fast-forward path.
