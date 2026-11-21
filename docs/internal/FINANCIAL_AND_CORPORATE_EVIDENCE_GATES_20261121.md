# November 21 financial and corporate-event evidence gates

Owner job `STOCK_LOOKUP_END_TO_END_RECOVERY_AND_PRODUCT_COMPLETION` (Priorities B and C).
Source baseline `2beffc479289be5ea17062ebc883f94da61176a1`. One writer; no Daily, no Production
write, no source or authority promotion. Builds on the
[November 18 reconciliation](Q3_FINANCIAL_EVIDENCE_RECOVERY_20261118.md); that record's
per-issuer findings were re-checked against code, not re-audited.

## B. Financial evidence: what changed and what remains gated

**Delivered (software blocker removed).** The intake row-identity owner
(`stocklookup_core/evidence/financial_row_identity.py`) had no entry for income-statement code 52,
so SSI's securities-template borrowing-cost row returned `ROW_IDENTITY_NOT_MAPPED` although the
sector taxonomy already defines Circular 334 code 52 as `borrowing_costs`. Code 52 now resolves to
the existing `REPORTED_BORROWING_COSTS` concept only when the printed label literally says
borrowing cost / interest expense. No canonical metric or alias is added. The industrial form uses
code 52 for deferred income tax; that label fails the literal check (`LITERAL_ROW_LABEL_MISMATCH`).
A combined "borrowing cost and loan/receivable loss" line is blocked as
`COMPOSITE_FINANCE_COST_ROW_NOT_PURE_BORROWING_COST`. Offline only; the capacity receipt records
the one changed hash without a new measurement.

**Verified unchanged (no code defect).**
- POW code 321 is loans **and finance leases** (`SHORT_TERM_LOANS_AND_FINANCE_LEASES`); a plain
  "loans" label with code 321/339 stays `*_LOANS_LEASE_CONTENT_UNKNOWN`. No pure-borrowing alias.
- PAN consolidated/separate research commits named on November 18 (`00de30c2`, `792bf9ec`,
  `1b3b6484`) are not objects in this Producer repository; nothing to integrate here.
- HPG Q3/9M shadow rows and POW's live issuer-source observation remain research candidates.

**Remaining gates are Owner authority, not engineering.** The registry
(`config/official_source_registry.json`) declares for `issuer_ir` and `hose` only
`audited_annual_financial_statements` and `reviewed_interim_financial_statements`. A Q3
statement is neither audited nor reviewed, so every Q3 row returns
`document_type_not_declared_for_source`. Independently, `APPROVED_ROUTES` in
`approved_issuer_ir_financial_evidence.py` (the intake cohort) does not contain HPG, SSI, PAN or
POW, so rows also return `TICKER_NOT_IN_APPROVED_COHORT`. Unknown original first-publication time
remains for all four (CMS labels, signature dates, PDF metadata and HTTP Last-Modified are not
substitutes).

### Approval request (not applied)

1. Declare a distinct document type `unreviewed_quarterly_financial_statements` for `issuer_ir`
   (hosts already allowed: `hoaphat.com.vn`) and `hose` (`staticfile.hsx.vn`, POW `c423af37…`).
   It must not alias `reviewed_interim_financial_statements`; consumers must keep the
   assurance state `UNREVIEWED`.
2. Add HPG (`https://www.hoaphat.com.vn/quan-he-co-dong/bao-cao-tai-chinh`), POW and SSI issuer
   routes to the intake cohort, with their existing retained original hashes (HPG primary
   `22a4061c…` / alternate `5e06426f…`, POW `ec37fd3a…`, SSI `caa48d6f…`).
3. Temporal proof stays a separate requirement: a retained disclosure receipt bound to the exact
   original hash and cutoff (for POW, the HTTP 200 issuer detail page `2e93e438…` proves
   *current* linkage only).

Expected effect after 1–2: the four issuers' Q3 rows can pass source/document gates as
`UNREVIEWED` research facts; strict valuation remains closed until temporal proof (3) and the
common-share continuity gates (below) clear. Nothing is promoted by this document.

## C. Corporate actions and publication time: measured ceilings

Retained 2026-11-20 enrichment (`corporate_event_context.json`): 154 events for 142 of 1,507
current-universe tickers; 152 from `hnx_official_rights_event_index/v1`, 2 from
`hose_public_event_hpg/v1`. All 154 have an official ex-date and **no** `published_at`
(`KNOWLEDGE_TIME_MISSING`, `historical_known_at_eligible=false`). Missing publication time is not
a missing ex-date.

| Source | What it can legitimately add | Ceiling found (2026-11-21) |
|---|---|---|
| HNX rights index (`NextPageTinCPNY_LTHQ`/`NextPageTHQUpCoM`) | ex/record/execution dates | Rows carry no publication column. |
| HNX disclosure index (`NextPageTinCPNY`/`NextPageTinUpCoM`) | minute-precision publication time | `pMaChungKhoan` is ignored (UPCoM returned all 11,058 rows); titles are HNX's own notices with no shared key to a rights row. No safe join. |
| HOSE per-security `securities/dividend/{id}` | issuer rights history | HPG returns only 2013/2015 rows: a stale history, not current events. |
| HOSE disclosure index (`news/securitiesType/1`) | exchange notices with exact `postedDate` | 43 "ngày đăng ký cuối cùng" notices in the retained window (e.g. FPT interim dividend, posted 2026-11-19 13:35 UTC), but the public JSON (`news/{id}`) has no body or dates; the structured HOSE event product is licensed (already recorded by `hose_source_surface_authority_qualification`). The 1,000-row page also truncates the window to ~3 weeks. |
| VSDC (`vsdc.vn`, approved `last_registration_date_notice`) | ticker + exact record date + official "Cập nhật" timestamp | Verified on `vsdc.vn/vi/ad/203002` (VCR, record date 03/12/2026, updated 20/11/2026 16:42:38). `vsd.vn`/`www.vsd.vn` fail TLS principal validation from this host (not bypassed). Registry policy allows one index page (15 latest notices) plus operator-supplied notice URLs, so the 152-event window cannot be reached within policy. |

Binding rule ready for use once inputs are admissible: an HNX/HOSE rights event receives
`published_at` only from a VSDC record-date notice with the **same ticker and the same record
date**, exactly one match, using the notice's own official timestamp (an update timestamp is a
conservative upper bound of first availability). Zero or several matches stay
`KNOWLEDGE_TIME_MISSING`. Ex-dates are never derived from record dates.

### Approval request (not applied)

Allow a bounded VSDC announcement-index walk for the active rights window (pages until the
oldest notice predates the window start minus 45 days; at the registry's 4 requests/minute), or
supply the finite notice URL list. Either unblocks publication time for the 152 HNX events and
the HOSE cohort without a new provider.

Coverage change delivered by this job for C: **none** (ceilings established; no fact inferred).
Common-share continuity for valuation remains blocked by the same official-source gates.
