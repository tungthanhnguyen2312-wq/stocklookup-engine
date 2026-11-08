# Matched-cohort session change — contract v1

Contracts: `market_close_participation_snapshot/v1`, `matched_cohort_session_change/v1`.
Code: [`market_close_intelligence.py`](../stocklookup_core/decision/market_close_intelligence.py)
(pure functions), attached by [`next_session_decision_brief.py`](../next_session_decision_brief.py)
`market_transition.matched_cohort` and surfaced as
`daily_integrated_decision_brief` `what_changed_today.market_participation_change`.
Tests: [`tests/test_market_close_intelligence.py`](../tests/test_market_close_intelligence.py).
Authority effect: **NONE** — descriptive current research, non-voting. No score, forecast,
probability, recommendation, sizing or execution. Owner campaign 2026-11-08.

## Problem

`next_session_decision_brief/v2` compares the aggregate `advance_ratio` of two governed
sessions. Each ratio has its own denominator (the session's technical cohort), and about 15% of
the cohort changes between sessions. The difference therefore mixes participation with
coverage changes. The brief also had no MA20 or momentum change. Market Close Intelligence
publishes next-session conditions but never evaluated them.

## Contract

- **Snapshot.** One row per ticker in exactly the `market_breadth` cohort: same-session
  `SHADOW_ONLY` technical features, in current descriptive scope. Each row is
  `[ticker, sign(return_1d), MA20 side (1/0/null), sign(momentum_20d)]`. The snapshot is
  content-identified and reports whether its count reconciles with `market_breadth`.
- **Previous session.** The governed registry chooses it (`build_comparison_metadata`). This
  contract never chooses one. A Mon–Fri weekday count between the two sessions is a warning
  only (`span.may_span_multiple_trading_sessions`). It is not an exchange calendar. In the real
  pair 2026-10-26 → 2026-11-02, the registry calls the previous session immediate, but four
  weekdays lie between the two.
- **Comparison.** Uses only tickers present in both sessions, so each before/after ratio shares
  one denominator. MA20 shares use tickers whose MA20 side is known in both sessions. It reports:
  - churn: `current_only` and `previous_only`;
  - changes in percentage points for advance, decline, above-MA20 and positive-momentum shares;
  - MA20 crossings above, below and net;
  - `participation_character`: BROADENING, NARROWING, DIVERGENT, UNCHANGED,
    UNCHANGED_ON_ONE_MEASURE or UNKNOWN. These are signs only, with no threshold.
- **Evaluated condition.** Market Close's published "Participation improves" condition is
  evaluated verbatim as CONFIRMED, REFUTED or NEITHER.
- **Refusals**, each with a reason: snapshot unavailable, previous session not earlier, cohort
  rule changed, or no matched tickers.
- **Same-session question.** Market Close also answers "Was the index move broad or
  concentrated?": VN-Index direction against the cohort majority. VN-Index is a cap-weighted
  HOSE index, while the cohort is an equal-count, cross-exchange set, so this answer is context
  and not proof of concentration.

## Real retained check (read-only, five governed pairs, 2026-11-08)

| Pair | Coverage | Aggregate adv Δ | Matched adv Δ | Matched MA20 Δ | MA20 net crossings | Character |
|---|---|---|---|---|---|---|
| 10-26→11-02 | 858→861 | −11.94 | −12.67 (742 matched) | −30.73 | −228 | NARROWING (4-weekday span) |
| 11-02→11-03 | 861→840 | +23.73 | +25.69 (759) | +5.14 | +39 | BROADENING |
| 11-03→11-04 | 840→867 | +18.83 | +21.78 (762) | +11.42 | +87 | BROADENING |
| 11-04→11-05 | 867→892 | −18.79 | −21.14 (790) | −0.76 | −6 | NARROWING |
| 11-05→11-06 | 892→909 | −10.98 | −10.70 (766) | −0.91 | −7 | NARROWING |

In these pairs, matched and aggregate deltas share a sign. The value added is a correct shared
denominator (gaps of up to 2.95 pp), explicit churn, the MA20 and momentum dimensions, and
the span warning. **Predictive value: NOT_YET_VALIDATED.**

## Pre-Market checklist review (Owner idea bank, 2026-11-08)

- **Accepted / modified:**
  - domestic breadth change on a shared denominator (this contract);
  - index-versus-breadth concordance.
- **Already covered (reuse):**
  - US 2Y/10Y, fed funds, USD-EM index, WTI (Macro V1, FRED);
  - sector relative strength (sector leadership context);
  - corporate events (corporate intelligence and event context).
- **Deferred:**
  - VIX spot and the 2s10s curve. FRED is the same route as Macro V1, but it is latest-vintage
    with no release time, and no retained evidence shows incremental value for VN equities.
    Shadow observation only, under a later bounded milestone.
  - US macro event calendar (CPI, FOMC, NFP). It needs a sourced schedule and time precision.
  - MA50/MA200 breadth. The current feature set is MA3/5/20.
- **Rejected:**
  - VIX futures term structure, US equity futures and SOFR/funding stress: no permitted, governed
    source, and US-specific structure.
  - ICE/BofA credit OAS: licence restrictions and truncated history on FRED.
  - DXY: it duplicates the USD-EM index.
  - The 0–100 six-axis risk score, fixed stale penalties, mechanical sizing multipliers,
    loss-limit and no-new-risk rules. These are unvalidated equal weights over correlated
    inputs. They conflict with the no-universal-score doctrine and with blocked sizing authority.
  - Global signals never suppress a security's own research setup.

## Market-gated entries (daily_integrated_decision_brief, same change)

The governed posture rule `BEARISH_BREADTH_NARROWS_FRESH_ENTRY` holds a fired, otherwise
qualified breakout at `WAIT_FOR_CONFIRMATION` while the market regime is adverse. Before this
change those names fell into the generic `EARLY_SETUPS` / `HOLD_MANAGE` buckets with no stated
release condition. They now form the `MARKET_GATED_ENTRY` opportunity set and
`opportunity_sets.market_gated_entries`.

Both brief additions are emitted only when they carry evidence:
- the market-gated keys appear only when at least one name is gated;
- `what_changed_today.market_participation_change` appears only when the next-session brief
  supplied a matched-cohort component, including a refused one with its reason.

A session without either keeps its exact pre-change brief bytes, which the E4 baseline-equality test
checks. The source change is bounded by
`tests/fixtures/decision_context_premarket_source_transition_v1.json`. It archives the base brief,
pins its hash, and extends the E4 v2 chain. `release_authority` is `NOT_GRANTED`. Each row shows the security setup, the market
environment, the regime, the security's own invalidation and the release condition, which is the
existing rule restated with nothing added. Posture, policy and decision identities are unchanged.

Real retained check: on 2026-11-02 (`DETERIORATING_BREADTH`), 15 names were held by this rule
alone. On 2026-11-03 the regime was `MIXED_BREADTH`. Seven of the 15 were then
`INITIATE_ON_BREAKOUT` and two were `ACCUMULATE_ON_RETEST`. This is posture behaviour, not
return evidence. **Effect on outcomes: NOT_YET_VALIDATED.**
