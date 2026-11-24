# Current-state relative valuation contract

## Headline earnings attribution — Owner Decision 1, 2026-11-24

`HL-20261124-HOL-06` implements the approved Owner Decision 1 in the current
market-wide P/E path. `p3f_current_market_valuation.select_pe_profit` is the
annual denominator selector: consolidated corporate filers use the qualified
parent-profit identity (`attributable_net_income` / taxonomy `net_income_parent`,
code 61 under TT200/202 and FY2026 TT99/2025 + TT43/2026). Code 60 never supplies
a consolidated headline. Latest qualified FY is selected; interim figures are
not annualized. Explicit standalone/separate total profit equals parent profit
and the label states that equality. Unknown scope, conflicting parent facts or
unmapped forms cannot qualify a parent denominator. Bank `net_profit_parent` and
securities `profit_after_tax_parent` retain their own mapped form identities;
insurance/finance-company applicability remains unchanged and unimplemented
parent forms remain unavailable.

`current_research_valuation_context` prefers a qualified, monetary-compatible
parent TTM over FY. Total-profit TTM cannot substitute, except for an explicitly
standalone input. Nonpositive qualified parent TTM yields `PE_NOT_MEANINGFUL`
without a positive-FY headline fallback. Missing qualified parent profit withholds
the headline with `PARENT_PROFIT_NOT_QUALIFIED`, preserving other input blockers.
Annual labels include the actual fiscal period, for example
`P/E (LN cổ đông công ty mẹ, FY2025)`.

The distinct `P/E_TOTAL_INCLUDING_NCI` supplementary method retains code-60
earnings with `earnings_attribution = TOTAL_INCLUDING_NCI` and label
`P/E toàn tập đoàn`. It never supplies a headline or a peer percentile. Headline
peer cohorts partition by earnings attribution as well as existing method,
entity, period and share/monetary compatibility. The integrated product and
Daily brief pass through the selected method, label, supplementary method and
withholding reason; legacy record-level values cannot override the new producer
policy. Frozen historical artifacts and period-end valuation history remain
preserved. This changes numerical research eligibility, not source admission,
PIT/execution authority or any runtime launch condition.

Local implementation and retained-input coverage evidence:
[2026-11-24 acceptance](internal/PARENT_ATTRIBUTABLE_HEADLINE_PE_20261124.md).

## Original current-state lane

Schema/method version: `1.0.0` / `current_state_relative_valuation_v1_current_price_x_official_current_shares`.
`market_cap`, `pe`, `pb`, `ps`, `enterprise_value`, `ev_sales`, `ev_ebitda` from the qualified
DNSE current-state price (`dnse_current_state_price_analytics.py`, reused verbatim) times official
current common shares outstanding (`share_transition_bridge.resolve_share_transition`, fed only
by `data/official-evidence/share_basis_citations.jsonl`), against already-qualified historical
canonical financial denominators (`relative_valuation._qualified`, reused verbatim). Evidence-
bounded to the same ticker gate as DNSE current-state price analytics (currently HPG, VCB).

Every available method carries `as_of_semantics = "current_market_price_on_qualified_historical_fundamentals"`
— never "TTM", "forward", or "current earnings" — because it deliberately relates a *current*
price to an *older* qualified financial period. One current share count feeds every metric (not
relative_valuation.py's period-end/weighted-average split, which values a *completed* reporting
period against its own contemporaneous price; there is no "weighted-average during the still-open
current period" to compute). `is_actionable` is always `false`, at both the lane and method level.

Current shares are qualified for a session only when `resolve_share_transition`'s own
`coverage_through` reaches that exact session — never inferred forward from a stale corroboration
(deliberately not `market_wide_current_shares_resolver.py`'s more permissive lane). A blocked
current-shares leg blocks every method; a metric is never partially computed from a mix of
qualified and unqualified inputs.

`historical_comparison` reads the ticker's own `relative_valuation` bundle section read-only and
never recomputes it. A method is `comparable` only when both sides are `state="available"`, share
`denominator_identity` and `statement_scope`, and the historical side is `historical_only=true`;
otherwise `incomparable` with reasons. A comparable result exposes `multiple_change_pct` as a
plain descriptive delta only — never a cheap/expensive, buy/sell, or target-price conclusion.

Producer flag: `export_ai_bundle.py --include-current-state-relative-valuation` (opt-in, disabled
by default). Bundle key: `tickers[ticker].current_state_relative_valuation` — distinct from the
pre-existing `relative_valuation` (historical, untouched) and from
`ticker_capability_matrix.market_actionable.current_valuation` (an unrelated, market-wide generic
capability-status slot from `market_basis_capability_registry.py`, also untouched). Consumer:
`apply_bundle_current_state_relative_valuation_contract` in
`ai-core-private/builders/build_ticker_context.py`, byte-identical pass-through.

See `current_state_relative_valuation.py`'s module docstring for the full rationale, including the
three independent evidence-loader gaps (a `manifest.json` registration gap for HPG's period-end/
EBITDA-component evidence document, and a separate flat-path bug in
`official_evidence.load_cited_financial_records`) this milestone discovered while wiring this
contract but did not fix (shared, pre-existing infrastructure, out of scope).
