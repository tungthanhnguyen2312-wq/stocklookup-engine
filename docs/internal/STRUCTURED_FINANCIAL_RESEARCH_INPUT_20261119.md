# Structured financial research input — 2026-11-19

Offline path for a permitted structured export. The command is:

`python tools/build_conditional_research_cases.py --structured-input FILE --out-json OUT.json --out-md OUT.md`

`FILE` is a CSV or a JSON object with an `observations` list. The CSV columns are the normalized-long provider export: ticker, period label, consolidation, unit, item, value, statement, source, source file, source SHA-256, period year, period kind and period basis. Optional assurance and vendor dates are kept when present. A missing required header rejects the file. A bad row is rejected and the other rows remain. A trailing `.0` is accepted as an integer and the original text is kept. Any other fraction is rejected.

Accepted period tokens are Q1–Q4 with `quarterly_discrete`, and 6M, 9M and FY with `cumulative_ytd`. Scope tokens are `Hợp nhất`, `Riêng` and `Công ty mẹ`. Units are 1 VND, thousand VND, million VND and USD. The statement family comes from labels in the file, not from an issuer list. Industrial, bank and securities labels are not crossed. A finance-company export that uses the credit-institution labels stays on those labels.

The same file bytes produce the same research identity. Two different values for one reported cell stay in conflict. A new file writes a new result and does not replace an existing output. `--knowledge-cutoff` without `--observed-at` blocks current use. A vendor date and the file clock are not publication and are not a point-in-time clock.

No trailing twelve months, annualization, share count, price or research multiple is invented. Four reported discrete quarters may be summed and are labeled as that sum. Interest-bearing debt stays blocked while the borrowings label still includes finance leases. Official admission and Financial V2 authority stay unchanged. The hardcoded statement cohort remains the regression control. The default command does not feed an AI preview and does not activate Daily. An opt-in question can build a local validator input; see `STRUCTURED_FINANCIAL_AI_RESEARCH_20261119.md`.
