# Fable full-system transformation — continuation handoff (2026-11-15)

Program `STOCKLOOKUP_FABLE_FULL_SYSTEM_TRANSFORMATION`, Owner-delegated. Executor: Claude Code.
Start: Producer `514ee89e`, Consumer `4537e32e`. Working evidence (outside Git):
`C:\Projects\StockLookup\claude-reports\fable-transformation-20261115\`.

## Done and verified

| Block | Result | Proof |
|---|---|---|
| B — D4a activation | PR #263 merged `8052e53d`; post-merge CI 43633581596 6/6; Production fast-forwarded `514ee89e → 8052e53d`, freeze preserved (`FAST_FORWARDED_FREEZE_PRESERVED`) | Deployed config `4e6da55f`, receipt `dae93f0f` (exact plan pins); `capacity_qualification` source_matches on Production; `storage_reuse_switches()` = both true |
| A — first removal | PR #264: 130 unreferenced historical runners (−19,923 LOC); non-test Python 1,057 → 927; `tools/*.py` 448 → 318 | Receipt corrective `unreachable_historical_runner_removal`; transition test re-derives each pin from base bytes |

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
3. **Delivery duplication (Workstream B).** In the 11-13 NDJSON, per ticker (~1 MB/record): `integrated_decision_v1.financial_composite_context`
   == `fundamental_research_context.composite` (9.3 KB), `valuation_method_reconciliation` twice (5.0 KB),
   `trigger.price_basis` == `invalidation.price_basis` (5.9 KB): ≈20 KB/ticker, ≈3 % of the 1.05 GB file.
   Larger sections: `current_research_decision_input.dimensions` 296 KB, `evidence_axes.VALUATION` 230 KB,
   `valuation_balance_sheet_divergence` 136 KB. Deduplication needs Consumer reader changes in dependency order.
4. **Income data gap (Workstream C/D).** Every HPG income-statement feature in the V2 engine is
   `BLOCKED_BY_EVIDENCE` (`MISSING_COMPATIBLE_SERIES`, `MISSING_STANDALONE_NET_INCOME`); market-wide
   income states have been empty since the 10-21 KBS duplicate-period gate. Official income facts exist
   in `fundamental_research_context.official_income` but report `NO_QUALIFIED_COMPATIBLE_INCOME_PAIR`
   and `d1_gate: UNREVIEWED_EXISTING_CONSUMER_USE_REFUSED`; the reviewed 9M packets stay offline.
   Restoring current earnings is an Owner source/authority decision, not a code fix.
5. `growth_state` treats disagreeing growth features as `UNAVAILABLE` and mixes seasonal QoQ with YoY. The
   consumption contract documents this as voting policy ("disagreement is no consensus"), so it is not
   changed here; it is moot while income features are blocked.

## Resume

```
git -C C:/Projects/StockLookup/stock-core-private fetch origin
python tools/stocklookup_roadmap.py --check --json
gh pr view 264 -R tungthanhnguyen2312-wq/stocklookup-engine
```
Production sync: `claude-reports/fable-transformation-20261115/sync_producer.ps1 -Target <merged sha> -CiRun <push run id>`
(refuses 15:35–20:30 VN, a moved remote head, or a tree that differs from the candidate).
