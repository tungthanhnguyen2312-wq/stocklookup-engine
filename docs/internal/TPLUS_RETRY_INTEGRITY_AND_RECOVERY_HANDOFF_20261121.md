# November 21 recovery handoff (T+ retry integrity, financial and corporate-event gates)

Executor: Claude Code, Owner-delegated mission `STOCK_LOOKUP_END_TO_END_RECOVERY_AND_PRODUCT_COMPLETION`.
Base: Producer `main` `2beffc479289be5ea17062ebc883f94da61176a1` (Production checkout
`T:\StockLookup\production-v1\stock-core-private`). Nothing pushed, merged, deployed or published;
no Production evidence or database written.

## Repository state

| Item | Value |
|---|---|
| Branch (local, unpushed) | `fix/tplus-retry-integrity-20261121` (worktree `T:\StockLookup\scratch\claude-tplus-20261121\a-wt`) |
| Commits | Priority A checkpoint, then the Priority B/C commit cherry-picked on top |
| Second branch | `feat/financial-corporate-evidence-20261121` (worktree `…\c-wt`): the same B/C commit alone on `2beffc47` |
| Production checkout | back to `2beffc47` except the protected pre-existing WIP `config/daily_research_session_input_registry.json` (October 26 freeze), untouched |
| Anti-Gravity WIP | `prospective_feedback_streaming.py` edit was syntactically invalid (statements inside a dict literal, `input_digest` deleted) and authorized reuse on one calendar digest alone. Preserved verbatim in `T:\StockLookup\recovery-patches-20261121\`; replaced, not applied. |

## Results

- **A (T+):** see the [contract section](../tplus_incremental_cost_v2_contract.md#retry-integrity-and-incremental-reuse-2026-11-21-local-checkpoint).
  Legitimate same-session retries are terminal (`ALREADY_COMPLETE`, bytes unchanged); the
  re-enacted K15 reproduced the retained attempt-1 artifact exactly; a genuinely changed input
  still conflicts and the prior artifact is named. Re-enactment K15 188 s, K19 224 s, peak
  1.44 GB (attempt 1: 416 / 951 s, 1.40 GB). Not a genuine session.
- **B/C:** see [financial and corporate-event gates](FINANCIAL_AND_CORPORATE_EVIDENCE_GATES_20261121.md).
  One software blocker removed (securities code 52 row identity); remaining gates are Owner
  authority (document type, intake cohort, temporal proof, VSDC pagination policy).

## Validation

Feedback, retry-integrity, retention, containment, transition, intake and host-preflight suites
in the isolated worktree with an isolated test home. Pre-existing failures reproduced on clean
`2beffc47` and not caused here: 6 setup errors in `tests/test_canonical_post_close_pipeline.py`,
2 in `tests/test_feedback_resource_guard.py`, and `test_native_powershell_profile_router`
(requires the Production-writer checkout).

## Owner gates (in order)

1. Review and merge the branch (normal GitHub release); ff-only Production sync keeps the freeze.
2. Before the next Daily: run the Owner seed (`--seed-state-only`, exit 33; receipts and sidecars,
   ≈75 min total because the verifier digest changed), or authorize copying the qualified scratch
   state under `T:\StockLookup\scratch\claude-tplus-20261121\state\operations-review\prospective-decision-outcome-feedback-v1\`.
3. Genuine warm acceptance on the next real session (≤600 s post, ≤900 s combined, ≤2 GiB).
4. B/C authority requests listed in the gates record.

## Exact next command after merge and sync (Owner)

```
python tools/run_prospective_decision_outcome_feedback.py --seed-state-only --root T:\StockLookup\production-v1\retained-evidence --state-root T:\StockLookup\production-v1\retained-evidence
```
