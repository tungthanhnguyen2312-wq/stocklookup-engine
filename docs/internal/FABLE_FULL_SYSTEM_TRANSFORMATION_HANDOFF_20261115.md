# Fable full-system transformation — continuation handoff (2026-11-15)

Program `STOCKLOOKUP_FABLE_FULL_SYSTEM_TRANSFORMATION`, Owner-delegated. Executor: Claude Code.
Start: Producer `514ee89e`, Consumer `4537e32e`. Working evidence (outside Git):
`C:\Projects\StockLookup\claude-reports\fable-transformation-20261115\`.

## Done and verified

| Block | Result | Proof |
|---|---|---|
| B — D4a activation | PR #263 merged `8052e53d`; post-merge CI 43633581596 6/6; Production fast-forwarded `514ee89e → 8052e53d`, freeze preserved (`FAST_FORWARDED_FREEZE_PRESERVED`) | Deployed config `4e6da55f`, receipt `dae93f0f` (exact plan pins); `capacity_qualification` source_matches on Production; `storage_reuse_switches()` = both true |
| A — first removal | PR #264: 127 unreferenced historical runners (−18,576 LOC); non-test Python 1,057 → 930; `tools/*.py` 448 → 321 | Receipt corrective `unreachable_historical_runner_removal`; transition test re-derives each pin from base bytes |
| A — second removal | 75 unreferenced modules (−7,010 LOC) + 1 dedicated non-CI test (−547); receipt entry `unreferenced_module_removal_batch2`; the transition test now replays every `removed_source_paths` entry generically, so a further removal needs only a receipt entry | Kept: operator tools (`check_/sync_/verify_/...`), relocation targets in `config/repository_layout.json`, and six November tools (candlestick, market close, Q3 freshness/successor, weekend brief, market-gate quality) |
| C/D — Consumer dossier | Consumer PR #18 (`069f3e6d`, Production FAST_FORWARDED) + PR #19: the handoff dossier passes through the same build's EXACT_QUALIFIED official annual metrics and QUALIFIED `EXACT_FIELD_CURRENT_RESEARCH_CONTEXT` income facts, labelled historical/non-voting | HPG/NVL/SSI FY2024 metrics, HPG FY2025 + H1/26, PNJ H1/26, FPT FY2025 facts now reach the Owner dossier |

## Pending on a real session (do not simulate)

- D4a first live session (next Owner Daily, Mon 2026-11-16): verify three same-file pairs (IID canonical/working view; NDJSON and bundle operation/run dir), SHA + identity bindings, five delivery names, separate manifest and brief, NTFS allocation and initial T+ fingerprint anchors; Consumer read compatibility. On any discrepancy: set both switches false and restore receipt pin `9ed88654…` (receipt `8dfabcd8`) through the governed source path. Keep published aliases.
- PR #258 (T+ V2) stays Draft until its warm acceptance after that Daily (one guarded post-handoff call on the scratch state).
- D2 scheduled capture live behaviour after release.

## Measured findings to act on next (no re-audit needed)

1. **Workstream A, remaining 261 unreferenced modules.** Same reachability scan (token refs in all
   non-test sources + launchers + CI + current docs, excluding the three all-module inventories) leaves
   modules only exercised by tests or that look like operator wrappers (`run_current_*`, `run_daily_*`).
   Review each with its test file; remove module + dedicated test together; drop pins under the same
   receipt corrective pattern (append paths, update base commit).
2. **Capacity receipt chain.** `test_offline_financial_capacity_transition_preserves_the_qualified_daily_source`
   replays ~12 bespoke correctives. A generic loop over `{base_commit, prior_source_sha256_lf | removed_source_paths}`
   would replace it; keep the receipt bytes and Production check unchanged.
3. **Delivery duplication (Workstream B) — corrected measurement.** The earlier ≈3 % figure counted only a few
   named fields. Counting every repeated subtree ≥1 KB (copies beyond the first, nested copies not double-counted)
   over a deterministic 1-in-7 sample of the 11-13 `ai_research_full_universe.ndjson` (241 records, 148.6 MB):
   **63.2 % is exact duplication** (≈665 MB of 1.05 GB). Largest sources: `evidence_axes.VALUATION` 25.8 %,
   `valuation_balance_sheet_divergence` 13.0 %, `current_research_decision_input.dimensions` 9.5 %,
   `evidence_axes.FUNDAMENTAL` 6.0 %, `financial_peer_context` 4.8 %. They come from deliberate `copy.deepcopy`
   restatements in `integrated_investment_decision_product.py` (evidence axes ~1791–1795, top-level contexts
   ~1886–1890, `build_ticker_decision_input` ~1901); `decision_identity` and T+ joins hash over them and the same
   copies inflate the 2.39 GB IID that sets `iid_max_bytes`. Not changed here: altering the record representation
   before Monday's D4a same-file/T+ anchor verification, PR #258's warm acceptance and a live capacity measurement
   would invalidate all three. Proposed sequence after those: (a) keep `decision_identity` over the expanded form;
   (b) serialize repeated subtrees once per record (reference by path) in the IID and NDJSON writers only;
   (c) expand in the shared reader (`record_artifact_loading`) so every reader sees identical dicts; (d) prove
   field-level equality on retained sessions and re-measure IID RSS/bytes in one live Daily. Producer readers:
   `ai_research_ticker_extractor`, `ai_research_session_delivery`, `run_market_gate_decision_quality`; no Consumer
   code reads the NDJSON.
4. **Income data gap (Workstream C/D).** Every HPG income-statement feature in the V2 engine is
   `BLOCKED_BY_EVIDENCE` (`MISSING_COMPATIBLE_SERIES`, `MISSING_STANDALONE_NET_INCOME`); market-wide
   income states have been empty since the 10-21 KBS duplicate-period gate. Official income facts exist
   in `fundamental_research_context.official_income` but report `NO_QUALIFIED_COMPATIBLE_INCOME_PAIR`
   and `d1_gate: UNREVIEWED_EXISTING_CONSUMER_USE_REFUSED`; the reviewed 9M packets stay offline.
   Restoring current earnings is an Owner source/authority decision, not a code fix.
5. **Financial chain, traced (11-13).** Semantic facts are the retained 09-05 projection (261,360 rows): KBS
   23,816 standalone income quarters → 18,869 gated by the repeated-head rule (provider payloads are internally
   contradictory; the ISO-head recovery `qualify_kbs_income_from_retained_head` has no head bounds to use because
   KBS capture is `RETIRED_PROVIDER`); VCI 1,595 income rows stay `PERIOD_DURATION_UNRESOLVED` by contract;
   37,502 rows are null placeholders. These are source/authority limits, not code defects. The propagation loss
   (qualified official metrics and facts not reaching the dossier) is fixed in Consumer #18/#19.
6. **Owner source proposal (not acted on).** To restore a current comparable income pair without promoting
   provider data: extract and review the comparative H1/2025 column of the already-retained reviewed H1/2026
   reports — HPG `9a2881a8…` (consolidated, reviewed, known 2026-11-06), PNJ `db877169…` (known 2026-09-29) —
   and the comparative FY2024 column of the audited FY2025 reports (HPG `f38c5f75…`, FPT `bb14baff…`,
   PNJ `309f8683…`), plus the operating-cash-flow lines of the same statement sets (HPG/PNJ blockers
   `NO_SAME_STATEMENT_SET_OPERATING_CASH_FLOW`). Intended use: same-document like-for-like growth and cash
   conversion in `official_income`/`earnings_cash` only; no TTM, valuation, share or target-price use. Missing proof:
   comparative-column extraction + reviewer admission per fact (an evidence write), and the restatement check
   against the prior-year original report.
7. `growth_state` treats disagreeing growth features as `UNAVAILABLE` and mixes seasonal QoQ with YoY. The
   consumption contract documents this as voting policy ("disagreement is no consensus"), so it is not
   changed here; it is moot while income features are blocked.

## Resume

```
git -C C:/Projects/StockLookup/stock-core-private fetch origin
python tools/stocklookup_roadmap.py --check --json
gh pr list -R tungthanhnguyen2312-wq/stocklookup-engine; gh pr list -R tungthanhnguyen2312-wq/stocklookup-ai-research
```
Production sync: `claude-reports/fable-transformation-20261115/sync_producer.ps1 -Target <merged sha> -CiRun <push run id>`
(refuses 15:35–20:30 VN, a moved remote head, or a tree that differs from the candidate).
