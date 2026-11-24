# Official corporate document acquisition pilot

## VSDC finite operator notice scope (HL-20261124-HOL-05)

Owner decision 2026-11-24 admits VSDC as the official source for registered-securities
counts and share-changing events, market-wide where supported. Registered shares remain
distinct from listed shares and outstanding shares excluding treasury; publication time,
record date and effective/listing date remain separate.

`acquire(..., vsdc_operator_notice_list=True)` accepts any well-formed ticker only
when **every** request in the finite operator list names source `vsdc`, class
`corporate_action_notice` or `last_registration_date_notice`, and an exact URL
`https://vsdc.vn/vi/ad/<digits>` (no query, fragment, port or trailing slash).
The entire list is validated before storage or HTTP. Registry admission, host/redirect
checks, declared 15-second interval, periods, timeout/retry/size bounds, hash-addressed
storage and manifest format are unchanged. This scope cannot combine with the bounded
three-ticker extension. Financial statements retain the existing cohort.

`tools/retain_vsdc_share_notices.py --urls <csv> --destination <scratch-dir> --dry-run`
validates all CSV rows and prints rejection reasons, planned requests and minimum spacing
time without HTTP or destination writes. Required columns are `ticker,notice_kind,url,published,title,venue_from_crawl`;
notice kinds are `registration_change` and `record_date_notice`, dates `DD/MM/YYYY`.
Remove `--dry-run` only for an operator-authorized download. Any rejected row prevents
the whole download. Crawl title/date/venue stay discovery provenance, never publication
time or venue authority. Retained notice bodies and same-ISIN witnesses govern extraction.

`tools/replay_vsdc_valuation_impact.py` is offline and takes repeatable `--evidence-root`,
read-only `--runtime-root`, aware `--known-by`, `--price`, `--fundamental`, `--shares`,
`--p3e`, optional `--official-universe`, and a new `--output` JSON path. These are the
same input artifacts used by `derive_market_wide_current_valuation_input_scaleout.py`,
with self-identities verified. `--expected-session` defaults to `2026-11-23`.
Bind the retained exact-session source inputs, rather than using the financial-analysis
or integrated-decision product as substitute inputs. Pass all applicable retained event
roots for the baseline as well as the new VSDC retention root. Both passes use the same
roots, provider inventory, prices and financial inputs, changing only the prototype flag.
The registry flag remains OFF. Run on a stable retained inventory; this tool does not
create a historical snapshot of a mutable runtime. It never opens integrated-decision artifacts.

The output covers every changed resolver basis, with raw provider count, registered count,
notice URL/publication time, authority before/after and existing-builder metric values,
statuses, blockers and percentage changes. Missing/blocked values and zero baselines
produce null percentage changes. A ticker outside the valuation universe remains in the
report with `NOT_IN_VALUATION_UNIVERSE` metrics. **Current gap:** the valuation builder
does not admit `official_registered_shares` as a research share tier. Enabling the resolver
can therefore block metrics; this replay does not relabel registered shares as outstanding
or expand valuation eligibility. Numeric registered-share sensitivities require a separately
reviewed valuation-use boundary. No production, Daily, PIT or factor authority changes.

The bounded FY2024 annual-evidence cohort extends the explicit ticker vocabulary to PNJ and FPT.
Their requests remain finite operator-supplied URLs; the registry admits only issuer-attributed
hosts (`www.pnj.com.vn` -> `cdn.pnj.io`, and `fpt.com` -> the specifically linked FPT storage
host), never a wildcard CDN or generic cloud-storage domain.

`official_document_acquisition.py` is a Producer-only, bounded intake contract for HPG, VNM, VCB, SSI, PAN, PNJ, and FPT. It accepts an explicit caller-supplied finite URL list for FY2023–FY2026 only; it does not crawl, poll, infer URLs, or write a runtime root.

Each retained version records canonical URL, issuer authority, document class, period, publication/observation dates, HTTP metadata, SHA-256, and immutable hash-addressed relative path. Repeated URL/hash pairs are skipped. Changed bytes append a new record and can name a previous `supersedes_document_id`; no prior byte or manifest record is replaced.
For governed, non-production retention, the canonical caller destination is `operations-review/governed-official-evidence-v1/` relative to the Producer repository. It is deliberately untracked, outside every runtime/database root, and is the only location where this pilot may retain downloaded PDF binaries. Its deterministic manifest and citation handoff are operational evidence, not Git-binary inputs.

The supported classes are audited annual financial statements, reviewed interim financial statements, annual reports, corporate-governance reports, AGM documents/resolutions, corporate-action notices, and amendment/supersession notices. Failure states are `unsupported_request`, `inaccessible`, `malformed`, `unsupported_document`, `needs_ocr`, and `malformed_document`; the coverage matrix marks no retained class as `missing`.

The bounded period allowlist includes 2026 so current-year HPG/VNM corporate-action
completion notices can be retained without weakening the ticker or document-class
allowlists. Retention alone never qualifies a share transition; citation, lifecycle,
effective-date, share-identity, and hash validation remain separate promotion gates.

Retained PDFs are passed only to the cited-retrieval intake handoff. Direct page citation metadata remains mandatory before deterministic retrieval can expose any passage, and acquisition never creates canonical financial observations. OCR is deliberately not implemented; textless PDFs report `needs_ocr`.

Existing source patterns: issuer IR PDFs for HPG and VNM, issuer IR / disclosure documents for VCB, and VSDC notice pages for corporate actions. A VCB historic third-party mirror is retained as weaker prior evidence and is not elevated by this acquisition contract. SSI and PAN require caller-supplied explicit official URLs before any bytes can be acquired.
