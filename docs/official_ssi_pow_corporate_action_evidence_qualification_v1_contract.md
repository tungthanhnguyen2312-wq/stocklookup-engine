# Official SSI/POW corporate-action evidence qualification V1

Owner scope: `OFFICIAL_SSI_POW_CORPORATE_ACTION_EVIDENCE_QUALIFICATION_V1`.
Base: merged PR193 `89eec3e026e32f474abadf1d0ee71b317b3e9f05`.
One feature branch/PR for review; no merge, production/runtime write, Daily,
backfill, Consumer/Dashboard/Hub write, authority promotion or successor.

## Evidence and reproducible acceptance

[Manifest](../operations-review/official-ssi-pow-ca-evidence-qualification-v1-20261026/official_document_retention/official_document_acquisition_manifest.json),
[governed OCR](../operations-review/official-ssi-pow-ca-evidence-qualification-v1-20261026/derived/ssi_pow_scan_ocr_sidecar.json),
[qualification artifact](../operations-review/official-ssi-pow-ca-evidence-qualification-v1-20261026/official_ssi_pow_ca_qualification.json).
Complete original bytes stay in ignored local retention. Eight originals were independently
acquired through the existing source registry, serially, one attempt each. Hub53 at
`848b339592ec0a46bcd0a6f18bd3e8ffb5fba867` supplied locators only. One necessary
POW result-report locator comes from the prior Hub51 manifest; HPG/PVD acquisition
and qualification were not repeated. Prior SSI ex-notice and POW aggregate listing
identities are reused without changing PR192 files.

Completeness is opt-in on the existing acquirer: HTTP 200, no range response,
matching declared length, identity encoding, final EOF and strict all-page PDF
resolution. This proves retained transport/structure, never publication or truth.
The full SSI document has five pages and differs from the Hub partial download.
Cached proof metadata is independently rechecked; incompatible existing receipts
are refused rather than rewritten. A newly acquired changed byte sequence receives
its own immutable identity through the existing mechanism.

Offline commands: `python tools/run_official_ssi_pow_ca_qualification.py`, then
`python -m pytest -q tests/test_official_ssi_pow_ca_qualification.py`.
The default runner verifies all eight originals before writing only its new artifact.
Hermetic tests replay tracked manifest/OCR; the separately marked retained-evidence
check rehashes actual PDFs. Hosted clean clones explicitly account for their absence.
`--acquire` alone permits the finite governed downloads; `--ocr` materializes only
missing finite profiles. Existing profiles are preserved. Reused SSI reads require
an explicit `--prior-retention-root` only when not already cached.

## Substantive before/after

PR192 had no POW ex-date or separable executed components, and SSI lacked a complete
executed-issuance bridge. It qualified only HPG/PVD stock factors offline.

- POW HOSE2280, pages1–3: ex-date 2025-12-10, record 2025-12-11;
  rights 100:12 at VND10,000; stock dividend100:4; bonus100:15.
- POW issuer report2545, pages2–3, and SSC9119 page2: actually issued
  93,672,392 dividend and351,277,104 bonus shares. Reported combined issuance
  444,949,496 adds to2,341,871,600 =2,786,821,096. Combined cancellations6,108
  are not assigned separately to either component. Reported treasury is zero
  before/after in that report. Issuance completed2025-12-11.
- Existing HOSE72 aggregate listing supplies executed lifecycle only after matching
  a directly reported component, companion, total, before and after. The ledger
  retains the aggregate anchor in lineage/knowledge; it never substitutes its total
  for a component quantity. Ambiguous/conflicting anchors fail closed.
- POW HOSE226 page2 and708 page1: rights listing increases2,786,821,096 by
  281,024,592 to3,067,845,688, effective2026-03-11. Unrestricted276,606,691
  trade2026-03-26; restricted4,417,901 trade2027-01-28. Listing is not freely
  tradable quantity. The rights plan and executed listing remain separate ledger
  identities without a document directly stating both planned/executed counts;
  equality alone does not establish that link.
- SSI resolution27/2026 pages3–4: planned500,219,550, distributed500,204,581,
  cancelled14,969; issued total after3,003,293,801 includes1,991,468 treasury.
  Completion2026-08-18 differs from listing2026-09-18 and trading2026-10-01.
  HOSE715 pages1–2 confirms listed before2,503,089,220 and after3,003,293,801.
  Treasury is stated **after issuance only**. Subtraction gives3,001,302,333 in that
  after-issuance context, not a pre-event denominator or current-share authority.
- The supplied SSI trading PDF is **1935/TB-SGDHCM**, not Hub/user lead label457.
  Its original rendered header and bounded sparse OCR corroborate1935. Preserve
  this correction; no document457 is fabricated or claimed acquired.

All reviewed fields retain original URL/full SHA, entity, page, literal token,
unit, OCR identity and method. Ambiguous superscript digits are never repaired:
finite whole-page English/sparse profiles recovered exact numeric tokens, with
visual review of the original pages. No crop, invented zero or arithmetic-derived
printed fact replaces the source. Regulatory versions on documents remain source
identity context, not newly adopted adjustment-method authority.

## Limits and invariants

Knowledge is the latest **Producer receipt among required source inputs**. New
receipts are2026-10-26 UTC; reused identities retain2026-10-25 receipts. HTTP
Last-Modified and portal postedDate cannot establish historical availability.
No event date, filing reference, or Hub header upper bound backdates knowledge.
The governed session calendar does not reach these receipts, so session resolution
remains unavailable. No original T0 changes.

SSI cash/bonus and POW's three legs stay separate. The existing factor-chain gate
refuses every new complete mixed-event factor. Rights retain
`FACTOR_NOT_APPLICABLE` plus `UNSUPPORTED_FACTOR_TYPE`; stock-only operands cannot
stand in for the entire POW event. SSI has no cash-factor policy. Common-share
continuity uses the existing bridge and refuses listed-share openings; no listed
count is relabelled common outstanding. New facts improve Investor Research event
and dilution context only. RAW_AS_TRADED, historical PIT/backtest, liquidity,
execution, market-wide CA coverage and strict valuation authority remain unchanged.

HPG/PVD and the complete prior observation/ledger/cohort replay exactly. Historical
state/docs, prior retained evidence, frozen source identities, Daily callers and
`AUTHORITY.md` stay unchanged. Existing Producer CI selection includes the new tests;
only its exact launcher digest is refreshed. There is no automatic next milestone.

## Independently retained complete original identities

| HOSE news ID | Entity / pages / bytes | Complete SHA-256 |
|---|---|---|
| 2422161 | POW / 3 / 851251 | `22c9abea2fdfdfb34ffc595ebf628a2d2ab48ad0f45b6734ef592b646193a5d4` |
| 2425221 | POW / 3 / 348338 | `8609d428fa5bcebf55d5ab70be558835f985c1416355de748cfe3944d0dd575a` |
| 2425695 | POW / 2 / 231390 | `cb47737e190fd1017dc91af25fb94e6d7951a10787d8377ad01a508973167761` |
| 2443111 | POW / 2 / 502826 | `4e292966d2e9f791c13ecfd6e7e37a166656b84a4763d0b741c58b5a4bcbe31c` |
| 2444347 | POW / 1 / 255143 | `d397e8e440711fecf1e48b0f02adf8e6d46b6d3ee5688eaa679868bf04d0dae1` |
| 2492611 | SSI / 5 / 1951939 | `221c1507f533bdb7b8565ed905d9b9482355eb4bb2bf80ba71397ade5a3259be` |
| 2497826 | SSI / 2 / 522424 | `6e156b76ec7e513a43a23e7d586c11bbe5798ca9c5e5bdcbbedfaf21dd9a0ea9` |
| 2499239 | SSI / 1 / 257221 | `4b12bb8d3c549661d0bd1fb9c861ba956f48d6846ddafb492a617a995d9fcb00` |

## Local acceptance checkpoint

Focused CA/acquisition/continuity, offline production call-shape, architecture,
repository layout and frozen source-transition checks: 256 passed, 2 predecessor
raw-body skips, 7 subtests. The final directly affected rerun passed90 tests,
2 predecessor raw-body skips and5 subtests; final SSI/POW module passes39 tests.
All eight new originals passed the retained-evidence check locally. Syntax passed.
Hosted CI and the final exact PR head are delivery evidence, not historical knowledge
or a main release. Stop at the open review PR; no Owner decision is needed to accept
these bounded source facts. Any factor-policy or stronger authority change needs
its own separate authorization and evidence.

Native local implementation checkpoint: `0a3073b62675cdabff1b6e21b3522f7cf0aeaca1`.
Current milestone COMPLETE / LOCAL_IMPLEMENTATION_COMPLETE_NOT_PROMOTED; queue empty.
