# Empirical Setup Outcome Calibration — Current contract

`PROSPECTIVE_LEARNING_AND_CALIBRATION_V1` (R6) extends the existing
`empirical_setup_outcome_calibration.py` to `empirical_setup_outcome_calibration/v2`.
It introduces no parallel backtest, persistence layer, acquisition or automatic policy writer.

## Canonical Current Research path for NEW T0 decisions

```
stocklookup.ps1 daily
 -> canonical_daily_operation: just-built Integrated Decision
 -> canonical_post_close_pipeline.retain_prospective_decision_snapshot
 -> prospective_decision_retention/v1: immutable full T0 decision + exact T0 price copy
 -> same-session canonical handoff binds snapshot/product/operation identities
 -> existing post-handoff prospective_decision_outcome_feedback/v3
 -> integrated_decision_prospective_feedback/v3: completed-session outcomes
 -> empirical_setup_outcome_calibration/v2: comparable cohorts
 -> prospective_calibration_eligibility/v1
 -> prospective_policy_calibration_candidate/v1: human review only
```

Normal Daily already seals and binds the canonical T0 before running the non-blocking
post-handoff feedback observer. That producer sequence is unchanged. The existing empirical
CLI consumes subsequent retained sessions on demand; no background loop is required or added.
One bounded metadata gap is closed: new Integrated products serialize their already-existing
research-action policy `v1`, and new sealed records copy it and the actual source/fundamental
contract versions. Policy thresholds and decision-identity semantics do not change.

The snapshot preserves the full original decision, ticker/session, product and decision identity,
posture/setup, serialized trigger/invalidation, evidence axes, actual source identities, scenario
context and R4/R5 fields where present. `known_at` remains absent when not supplied; content and
Daily-operation retention identities establish the existing temporal proof without inventing a
timestamp. Historical snapshots are neither mutated nor supplemented with current versions.
R4/R5 absence or unavailability is context, never an admission gate.

Legacy handoff-qualified Integrated artifacts remain readable genuine T0 evidence. Immutable
snapshot identity validation precedes a compact read-only projection, limiting corpus memory
without weakening validation. Discovery uses bounded namespace patterns and exact handoff
references; it never recursively scans operations-review. Orphans, mismatched identities and
mutable later views cannot replace the sealed T0.

The older Workspace admission/durable case store and H1/H3/H5 shadow rollforward retain their
existing purposes and vocabulary. They are not converted into late Integrated T0 cases. The
learning ledger continues to require genuine retained claims, registered evidence and explicit
human provenance; market price movement cannot prove or refute a thesis. No store is created or
written by R6 acceptance, and no human-review fixture becomes production evidence.

## Completed sessions, prices and events

T5/T10/T20 count 5/10/20 governed completed sessions, never calendar days. Existing T1/T3/T60
remain available. All canonical horizons and both T0 source families now use one completed-session
chain. Qualified Daily market observations may mature a case even when that future session has
no decision snapshot. Sealed T0 prices retain precedence at their own sessions.

Each horizon retains endpoint sessions/prices and source/basis/transformation lineage. Missing,
non-finite, boolean or nonpositive prices cannot produce returns. Normalized price-basis and
transformation compatibility are required; provider lineage remains explicit. Missing T0 price
is distinguished before the pending-depth gate. The evidence states are:

- `NOT_RETAINED_AT_T0`: required T0 close absent or invalid;
- `RETAINED_BUT_NOT_YET_MATURE`: qualified T0, insufficient completed-session depth;
- `OUTCOME_DATA_UNAVAILABLE`: required future price unavailable;
- `SEMANTICALLY_INCOMPATIBLE`: endpoints have incompatible price semantics;
- `MATURE`: compatible qualified endpoint return available.

Close excursions additionally require every intermediate observation. Labels are
`CLOSE_ONLY_FAVORABLE_EXCURSION` / `CLOSE_ONLY_ADVERSE_EXCURSION`; legacy close-proxy field names
remain readable. They never assert intraday MFE/MAE. A benchmark-relative return requires an
actually retained T0 benchmark and a compatible future benchmark, using the existing benchmark
calculator. Missing benchmark inputs produce an explicit unavailable context.

Only identity-valid serialized fixed T0 conditions are evaluated. Dynamic/narrative boundaries
remain not evaluable. Missing/incompatible observations before a later hit prevent a claim about
first-event order. Events and frequencies are bounded to each cohort's outcome horizon. Ordering
includes confirmation before invalidation, reverse order, either alone, neither, not evaluable,
and `SAME_SESSION_ORDER_UNRESOLVED`; a close does not establish intraday ordering.

The existing shared feedback taxonomy uses T5. Initiation plus qualified invalidation may satisfy
its explicit false-positive breakout rule. Early reversal requires confirmation before invalidation.
A defensive false negative requires its confirmed favorable contract conditions, or an explicitly
qualified signal already retained at T0; a later price rise alone is insufficient. Descriptive
legacy price labels remain separate from policy-failure diagnoses. No label is causal proof.

R units require an identity-valid, fixed downside invalidation boundary actually retained at T0,
a qualified entry reference and positive finite downside. A numeric narrative level alone is
insufficient. Targets must be serialized within the T0 record; later caller-supplied target levels
cannot create target evidence. Target events are also horizon-bounded.

## Comparable cohorts and presentation policy

Keys retain actual T0 Integrated contract, research/fundamental policy versions, actual retained
feature methods, posture, setup/structure, invalidation method and horizon, plus the evaluation
contract. Unknown versions remain unknown: partition by original T0 source identity rather than
pooling different sessions under the currently imported policy. There is no default ticker split.
Optional regime partitions require the existing descriptive sample floor. Identical observation
packets are deduplicated; conflicting identities are rejected.

The unchanged `empirical_setup_outcome_calibration/v1` sample policy is research presentation
policy, not factual authority:

| Mature observations / distinct T0 sessions | Adequacy |
|---|---|
| fewer than 20 observations or fewer than 5 sessions | `INSUFFICIENT_SAMPLE` |
| at least 20 / 5, below either calibrated floor | `DESCRIPTIVE_ONLY` |
| at least 50 / 10 | `CALIBRATED_RESEARCH` |

Counts and horizon-bounded taxonomy are descriptive. Adequate samples expose median,
P10/P25/P75/P90, close-excursion and qualified R distributions. Existing calibrated presentation
policy permits observed frequencies and Wilson intervals. These describe the prospective corpus,
never forecast a future success probability; overlapping windows are not independent samples.

Calibration eligibility additionally requires known compatible policy/feature versions, genuine
T0 provenance, matured outcomes and no price-basis incompatibility. States are
`INSUFFICIENT_PROSPECTIVE_EVIDENCE`, `DESCRIPTIVE_EVIDENCE_ONLY`, and
`CALIBRATION_REVIEW_ELIGIBLE`. Adequacy alone cannot grant review eligibility.
The existing optional Portfolio research hook fails closed when its old lookup is ambiguous across
policy cohorts. It remains optional research context; execution, sizing and margin fields do not change.

## Human-review candidate contract

No registry is assumed. Default disposition is `NO_GOVERNED_POLICY_CANDIDATE_TO_COMPARE`.
An explicit `governed_prospective_policy_review_rule/v1` must identify current policy, exact
comparable cohort key/horizon, declaration, comparison-policy identity, and a valid declaration
session preceding the cohort's first T0. One predeclared taxonomy-count rule may be evaluated;
multiple comparisons, malformed rules and optimizer methods fail closed. The supplied rule is
never chosen from observed returns and never becomes a live threshold.

An actual candidate requires `CALIBRATION_REVIEW_ELIGIBLE` and satisfaction of that explicit
rule. Output binds cohort identity, current policy/version, horizon, observation/session counts,
empirical statistics, existing uncertainty interval, failure taxonomy, reason and limitations.
`required_human_approval=true`, `automatic_policy_change=false`. No optimizer, policy mutation,
new recommendation/score, Kelly/CVaR, sizing or execution authority is introduced.
R4/R5 retained context allows descriptive attribution, never causal explanations or eligibility votes.

## Retained October 1 acceptance and continuity

[Portable R6 acceptance](internal/R6_PROSPECTIVE_LEARNING_ACCEPTANCE.json) inventories all
30,294 genuine decisions / 18 T0 sessions / 1,683 tickers: 26,928 observations from 16 immutable
snapshot sessions and 3,366 from two qualified legacy sessions. Two orphan immutable files and
the identity-mismatched legacy September 4 view remain excluded.

T5: 8,134 mature / 4,288 pending / 17,121 missing price / 751 incompatible.
T10: 4,356 mature / 8,626 pending / 16,560 missing price / 752 incompatible.
T20/T60: 0 mature / 14,716 pending / 15,578 missing T0 price.
The evidence-state table distinguishes missing T0 from unavailable future prices. Qualified
T0 downside denominators: 264; genuine targets: zero; retained R4/R5 attribution: zero.
All 1,952 cohorts are `INSUFFICIENT_SAMPLE`, with zero review-eligible cohorts and zero actual
candidates. Older unversioned sessions cannot be retroactively upgraded to reach the floors.

The gate is NEW immutable T0 with explicit known policy/feature versions, at least 50 mature
observations from 10 distinct comparable T0 sessions per horizon, qualified price basis and a
predeclared governed review rule. Future ordinary Daily capture already supplies the canonical
retention path; R6 does not run Daily or change its acquisition/publication chain.

The existing CLI supports `--acceptance-output`, `--baseline-inventory` and `--baseline-feedback`
in addition to its immutable full artifact/evidence outputs. Acceptance verifies original source
SHA256 hashes before/after, stable genuine case/decision/posture sets, outcome transitions and
reversed-input deterministic identity. Derived artifacts belong in explicit research/scratch paths;
source inputs and production/runtime stores remain untouched.

## Post-release continuity diagnosis — 2026-10-02

`prospective_decision_corpus_health/v2` adds operational session/horizon diagnosis through the existing retention producer. Snapshot identity/absence inventory remains separate from genuine legacy/immutable outcome coverage. Every admitted decision contributes exactly one count per shared feedback horizon, with unavailable horizons labelled UNKNOWN rather than omitted. Missing/invalid T0, pending completed-session depth, future-close absence/invalidity and price-series incompatibility remain distinct. Exact affected future endpoint sessions are retained only when the upstream outcome actually supplied them. Endpoint maturity never proves complete close-path fitness or calibration eligibility.

The feedback artifact embeds this health verdict, and the existing offline maturation runner consumes the same object. Diagnostic content changes health/feedback wrapper hashes; T0/decision identities, source bytes, numerical returns, classifications, cohort thresholds and action policy do not change. No historical T0 backfill, automatic repair/acquisition, policy writer or authority promotion occurs.

## Market-gate decision quality — `market_gate_decision_quality/v1` (2026-11-08)

Offline, read-only, `NON_VOTING`. It asks what happened after the governed rule
`BEARISH_BREADTH_NARROWS_FRESH_ENTRY` held an otherwise valid fired breakout or retest at
`WAIT_FOR_CONFIRMATION`. It lives in `empirical_setup_outcome_calibration.py`; the runner is
`tools/run_market_gate_decision_quality.py --root <retained root> [--output-dir <scratch>]`.

- **T0 facts:** each completed session's retained Daily brief. The brief content identity is
  re-verified, and the brief must bind to the handoff's operation and IID identity. The sealed
  T0 seal index (`prospective_t0_seal_index/v1`, verified with its write receipt) supplies the
  decision identity. Trigger levels come from the same operation's delivery row, and only when
  its decision identity equals the sealed one. The posture, condition class, policy version and
  breadth/regime at the cutoff are copied, never re-derived. A later record never relabels T0.
- **Groups:** `MARKET_GATED`; `ALLOWED_ENTRY_BASELINE` (same policy version,
  `FRESH_ENTRY_TRIGGER` or `CONFIRMED_RETEST_ENTRY` in any session); the same-session decision
  universe median for excess returns. The groups sit in different regimes, so differences are
  not causal.
- **Outcomes:** `_forward_horizon`/`_close_excursion` over the governed session chain (T1, T3,
  T5, T10, T20, T60). A missed capture breaks every horizon that crosses it. Statuses stay
  explicit (`MISSED_CAPTURE`, `PENDING…`, `PRICE_BASIS_INCOMPATIBLE`, `CLOSE_PRICE_NOT_RETAINED`).
  Prices are the exact-session snapshot's own-session close rows, read one snapshot at a time.
- **Release:** the first later retained decision record that is no longer gated. The posture at
  release gives `GATE_RELEASED_AFTER_CONFIRMATION`, `RELEASED_EXTENDED_DO_NOT_CHASE`,
  `SETUP_FAILED_BY_RELEASE` or `RELEASED_SETUP_NOT_ENTRY`. The move to release, and the path
  after release, are close-to-close research counterfactuals: no execution, costs, slippage or
  liquidity. A close below the T0 trigger is a descriptive event, not the governed invalidation.
- **Labels (T5 basis, existing `OUTCOME_POLICY_CONSTANTS`):** `AVOIDED_DOWNSIDE`,
  `MISSED_UPSIDE`, `DELAYED_ENTRY_STILL_AVAILABLE`, `NO_MATERIAL_MOVE` or `INDETERMINATE` with
  its reason. They are descriptive only.
- **Verdict:** `INSUFFICIENT_EVIDENCE_FOR_POLICY_CHANGE` below the existing descriptive floor
  (20 mature T5 observations from 5 sessions). Above it the verdict is descriptive only.
  `policy_change_authorized` is always false; any rule change needs a separate approved
  strategy-policy transition.

First retained acceptance (as of 2026-11-06, policy v2, 16 sessions in scope):
- The gate was active in one session: 2026-11-02, 15 names, `DETERIORATING_BREADTH`, 16% of names
  advancing. All 15 names were released on 2026-11-03: 9 into an entry posture, 5 into a non-entry
  setup and 1 failed breakout.
- The one-session move to release had a median of 0.0%, ranging from −3.1% to +3.0%.
- T3 and longer are `MISSED_CAPTURE` because 2026-11-05 was captured late. The verdict is
  `INSUFFICIENT_EVIDENCE_FOR_POLICY_CHANGE`.
