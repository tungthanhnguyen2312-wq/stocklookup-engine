# Conditional research cases — HPG, KBC, FPT

Strict decision, execution and official-fact admission stay closed. No target price is stated.

## HPG — research date 2026-10-13

Research price 20450.00 VND per share. Source unit verified: False.
Research shares 8442964520. Conditional market capitalization 172658624434000.00 VND.
Price over reported H1 parent profit: 11.23712166759485639921773228. This is the six-month column, not annual P/E and not TTM P/E.
Price over total equity including non-controlling interests: 1.220064104042173803878334598. This is not parent-shareholder P/B.
Parent P/B, TTM P/E and EV/EBITDA are unusable.
Consolidated operating cash flow over parent-attributable profit carries that scope warning. The ratio is a visual review, not an admitted fact.

## KBC — Q3 and nine-month 2026

Consolidated and separate profits stay apart. The quarter is not added to the nine-month column.
OCR candidates are not native lexemes. No price was supplied, so there is no market capitalization.

## FPT — audited FY2025 context

Qualified consolidated revenue 70112825100710 VND and line-400 equity 43748040747539 VND are historical context.
Parent profit stays blocked on ambiguous digits. Cash, debt, current shares and a current price are absent, so no multiple is calculated.
A later company highlight is not used as a statement fact.

Failed checks: none.

## Run locally

From a clean checkout, use the offline CLI and two new output filenames in a
scratch directory. The example mode takes the retained HPG/KBC intake, the
retained HPG price/share example and the audited FPT context. Use `--intake`,
`--valuation-examples` and `--fpt-annual` to select copies at other paths.

```powershell
python -B tools/build_conditional_research_cases.py --out-json <scratch>/cases.json --out-md <scratch>/cases.md
python -B tools/build_conditional_research_cases.py --inputs <issuer-inputs.json> --out-json <scratch>/issuer.json --out-md <scratch>/issuer.md
```

Supply a JSON list (or an object with a `records` list) of
`{"ticker":"ABC","entity":"corporate","inputs":{"price":{},"share_components":{},"facts":{}}}`
records. Populate those inputs with the retained evidence and its provenance.
An empty evidence object produces unavailable values. Annual context records
can instead carry `canonical_facts`, `blocked`, `document_sha256` and
`knowledge_available_at`. Supplied labels describe the input evidence and this
command grants no new source authority. The offline CLI owns the conditional valuation route.
