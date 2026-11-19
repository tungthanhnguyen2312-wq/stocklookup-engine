# Current statement research cohort — 2026-11-19

Offline consumer for readings that already lived in `q3_2026_successor_research`.
No new store, no PDF fetch, no official admission, no Financial V2 authority change.
The command is `python tools/build_conditional_research_cases.py --statement-cohort`.

Issuers in this slice: HPG, PAN, POW, SSI, EVF. Banks are absent.
Industrial ratios use only columns that pass the existing income cross-foot.
A one-dong parent or tax-bridge residual withholds the whole column and is not repaired.
POW 2026-Q3 is withheld at group minus parent and non-controlling interest = -1 VND.
POW 2026-9M is withheld at the pretax bridge = +1 VND. Its operating cash flow still foots.
PAN 2026-9M is withheld at group minus parent and non-controlling interest = +1 VND.
SSI stays on the securities template. EVF stays in million VND on the separate statement.
No trailing twelve months and no research multiple is emitted.

PR #271 stays open. Its official HPG admission did not qualify, and this cohort does not merge that claim.
