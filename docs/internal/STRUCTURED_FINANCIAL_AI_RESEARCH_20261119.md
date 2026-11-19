# Structured financial AI research — 2026-11-19

Opt-in companion to `structured_financial_research_input/v1`. The command is:

`python tools/build_conditional_research_cases.py --structured-input FILE --ai-question QUESTION --tickers TICKERS --out-json OUT.json --out-md OUT.md`

Questions are `industrial_profitability`, `earnings_quality`, `balance_sheet_risk`, `template_earnings_trends`, `valuation_readiness` and `company_thesis`. The default command is unchanged when `--ai-question` is absent.

The selected records pass through `validate_ai_draft` and `build_human_review_packet`. Python remains the numerical authority. The deterministic draft is a validator fixture, not a model response. No remote model is called. Licensed remote disclosure of the provider extract is not established.

A caller `--observed-at` string is rejected on this path. A time-bound request needs `structured_financial_observation_receipt/v1` bound to the same input SHA-256, with `observation_basis` `RETAINED_ACQUISITION_RECORD`. A vendor date, an export timestamp or a file clock is not that receipt. Without it, reported figures are withheld. With a receipt at or before the cutoff, figures may be shown and are still publication-unproven, not historical PIT and not a sealed session.

Provider attribution, period, scope, unit and blocked measures stay on the evidence. Industrial, bank and securities templates are not crossed. Valuation, shares, price and trailing twelve months stay blocked. Official admission, Financial V2 and ordinary Daily stay unchanged.
