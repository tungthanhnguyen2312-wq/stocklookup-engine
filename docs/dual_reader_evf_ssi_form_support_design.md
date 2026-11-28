# Bounded EVF / SSI form support — HL-20261128-CODEX-EVF-SSI-FORMS

Development-only extension of [Decision 2](dual_reader_reviewed_transcription_v1_contract.md).
No actual facts were admitted. Common-owner integration is implemented in DEV;
native lane admission, capacity corrective and conforming evidence remain pending.
This note does not activate the research config or promote operational authority.

## Contract

The new immutable [form contract](../stocklookup_core/evidence/dual_reader_form_contract.py)
is called only for non-corporate forms. Corporate B02/B02a-DN/HN codes 10/60/61
retain their existing gate and serialized results. Nine corporate FY2025/H1-2025/
H1-2026 metric combinations match golden bytes generated from baseline a7e399fa.

SSI's exact retained forms are `B02-CTCK/HN` and `B02a-CTCK/HN`. Code/label pairs
90, 200, 201 and 202 map respectively to `securities_profit_before_tax`,
`securities_profit_after_tax`, `securities_profit_allocated_to_owners`, and
`securities_profit_appropriated_to_funds`. Roman section prefixes remain significant;
only the existing numeric outline split applies. Annual and interim labels differ.
There is no corporate revenue or parent-profit alias. P/S and EV/EBITDA carry
`NOT_APPLICABLE` in the verifier result; no downstream engine is changed.

EVF's five coded candidate identities (I, IX, X, XI, XIII) retain credit-native
net interest income, operating profit before provisions, provision expense, PBT
and PAT meanings. **EVF has no enabled form literal.** Both cold readers retained
null form/scope on all three income pages; visual inspection of FY2025 PDF11
confirms no printed form code. The total operating income row is unnumbered.
No code, form, scope, revenue mapping or parent PAT is invented. Consequently an
EVF positive admission fixture would fabricate a prerequisite and is not supplied.

All existing Decision 2 conditions persist: independent model families and reader
IDs, precomparison recording/retention chronology, exact shared/selected literals,
document/image/source-rights bindings, metadata/issuer/assurance qualification,
scope/period/current-column and unit/value/sign checks, completion-time knowledge
floor/cutoff, and research-only use with original conflict/restatement safeguards.
Balance sheets, admitted note facts, comparative columns, nine-month facts, EPS,
weighted/diluted/outstanding share bases and Production/PIT are not extended.

## Code 201 basis and TTM hand-off

No default basis exists. The row must declare `appropriation_basis`, and its
sealed agreement proof must reference `appropriation_note = {page_image, readings}`.
The loader reads those same-PDF note bytes only for the securities owner-profit
metric, under the existing proof-root path rules. Each note reading must replay
its hash, image/source binding, actual timestamp chronology, independent family,
issuer, note form, period caption, current column, literal disclosure and identical
numerator. Both income-reader families must agree. Notes classify basis only;
they do not admit EPS or note financial facts.

Only the exact FY2025 note85 and H1-2026 note82 printed disclosures that fund
appropriation was not estimated are registered. A successful verifier result
returns source-bound `appropriation_basis` with basis
`PRE_FUND_APPROPRIATION_UNESTIMATED`, original-current-column vintage, document,
period/column, note image/literal and both note hashes. A conflicting row claim
is `DUAL_READER_APPROPRIATION_BASIS_MISMATCH`; absent/unsupported proof is
`DUAL_READER_APPROPRIATION_BASIS_UNPROVEN`. No AGM fund percentage is applied to
another earnings period. Restated H1-2025 and approved fund amounts remain distinct.

**DEV continuation — HL-20261128-CODEX-SSI-COMMON-ADMISSION:**
`official_financial_filing_evidence.py` now delegates its template check only for SSI
rows whose full Decision 2 verifier returned the registered form contract and family.
There is no generic metric registration or reason-removal hook. All other source,
metadata, issuer, assurance, conflict, numeric, cutoff and use checks still run.
Only `CURRENT_RESEARCH_FACTUAL_AUTHORITY` is eligible for this extension.
The admission result retains form identity and valuation applicability in its
classification, and code201's verified `appropriation_basis` object (including note
provenance) both at the result's top level and in `evidence_classification`. Input
rows remain immutable; a caller's scalar basis claim is never returned as proof.

The form contract additionally recognizes only the exact retained CTCK H1/2025 and
H1/2026 full Vietnamese current-column heading and caption spellings. It never
repairs or changes the literals; contrary years, restated headings, corporate forms
and other forms remain refused. Current code202 dashes stay nonnumeric and cannot
be treated as zero. EVF has no enabled printed form and remains closed.

The later H1 engine lane must consume the native metric explicitly, require identical
proven basis classifications across FY / H1-current / H1-prior, and retain each
operand's source/vintage and common-owner admission. Document-specific provenance
is preserved rather than compared as if different documents should have equal hashes.
`SECURITIES_BONUS_WELFARE_BASIS_UNPROVEN` is unchanged. Original H1-2025 has no
registered basis proof in this change, so a three-operand TTM is still withheld.

## Retained replay and missing inputs

[Read-only replay tool](../tools/replay_dual_reader_form_support.py):
`--sealed-root <clean-readers> --neutral-root <neutral_inputs>`; optional
`--rows-file <existing candidates.jsonl> --evidence-root <existing landing root>`
replays common admission only when its raw hashes bind to the exact cold pair.
It never constructs agreement proofs, invents timestamps, converts sealed schemas,
copies artifacts into a landing, or calls a model/network. Exit 1 means refusals;
exit 2 means malformed/unreadable inputs. JSON includes every observed cell,
source/hash references, reason codes and missing proof inputs.

Six income pages replayed: **ADMIT 0 / REFUSE 282** (EVF198; SSI84), including
comparative and note-reference cells. Index SHA256:
`96fc7a618f3c1cd64c25c301c0f0e6a0c3219bdb0c75ae9fd6fb8b9585c0215a`.
The comparison report is research evidence, not an agreement proof; its HPG
qualification review does not qualify EVF/SSI. The referenced remote reader-2
report was inaccessible in this sandbox.

Missing supplied proof inputs: Decision 2 agreement with PDF/document ID, image,
raw hashes and actual comparison/completion times; eligible actual raw recording/
retention provenance (Gemini `recorded_at` is null); supported raw family strings
and current-column schema (cold records use `current_period`, not `current`);
manifest-selected explicit rights/issuer/image bindings; qualified metadata and
assurance/legal scope; source-bound code201 note proofs; EVF printed form/scope
and document ID. Original records remain immutable. Seal time is not substituted
for recording time, and no unrelated rights/assurance proof is borrowed.

## Validation and integration impact

Continuation validation: **72 direct assertion cases**, **90 complete common-admission
and 90 verifier byte comparisons with starting HEAD 0373a161** (PNJ corporate / VCB bank, three periods,
three metrics and five proof/cutoff variants), and **4 standard-library replay tests**
passed using a temporary harness, deleted after validation. The 72 include 11 positive
SSI cases through pure and retained common admission; nine corporate golden cases;
missing/mismatched basis, single family, corporate code on CTCK, unsupported original
H1/2025 basis, rights/assurance/conflict/cutoff failures, research-only use, exact interim
headings and nonnumeric fund dashes. Positive values/row literals come from the sealed
literal fixture; code202 positives explicitly use owned synthetic `123`, since the real
current cells are dashes. No actual cold reading was converted. PDF text loading is the
only stub in retained positive tests; raw/proof bytes, hashes and all admission gates
are replayed. Full pytest remains unavailable (`No module named pytest`); this
interpreter also lacks pypdf. Syntax and diff checks pass.

Cold replay remains **ADMIT 0 / REFUSE 282**, SSI84 / EVF198 across six income pages,
with the same sealed-index SHA above. The [answer-free reading spec](ssi_decision2_reading_package_spec.json)
was built only from the neutral input manifest, independently hash-checking all five
image/PDF bindings: three income pages and same-PDF FY2025/H1-2026 basis notes. It
requests ten new raw records from two blind families. It contains no answers, expected
values, labels, note disclosures or existing reader output. Original H1/2025 basis
and a compatible three-operand TTM remain unproven.

The earlier implementation validation at 0373a161 is preserved below:

54 direct checks passed through a temporary standard-library harness, including
nine original-verifier byte comparisons, five original rejection comparisons,
and nine committed golden checks; four
standard-library replay tests passed. Row/form literals are extracted from the
sealed files with original hashes; other positive-test metadata/readings are owned
synthetic fixtures, not issuer admissions. Full pytest was attempted but cannot
run: this interpreter lacks pytest and PDF dependencies. No environment/guard
configuration was changed. Syntax and diff checks pass.

No E-tier frozen source fixture names `dual_reader_transcription.py`; capacity
does pin it. HL must chain the capacity corrective (including the new module's
source closure); protected capacity config/tests are untouched. Changed pinned file:

| File | Prior LF SHA256 | New LF SHA256 |
|---|---|---|
| `stocklookup_core/evidence/dual_reader_transcription.py` | `226b4b89001fc473e6dd4283a189a34fd7e2d109b17d29b00f50995dd8dd856d` | `464355d0a815b04387b7576a69f3e80458b091fdf66d3d26c8a18375403fb85a` |

Continuation LF identities (prior = task starting HEAD 0373a161; not a capacity
receipt amendment):

| File | Prior LF SHA256 | New LF SHA256 |
|---|---|---|
| `official_financial_filing_evidence.py` (capacity-pinned) | `88bc2c0ebbffcb21488dd871742eb7ec160badc6f420a8fc2aa63befea2842a3` | `6754a7e486f80836f18a813e592784834bf84e7382d51f87bd0c7bbd880d49a7` |
| `stocklookup_core/evidence/dual_reader_transcription.py` (capacity-pinned) | `464355d0a815b04387b7576a69f3e80458b091fdf66d3d26c8a18375403fb85a` | `5ff824e02d1053b8c223b9579cabd31b7cf9416da12d1a0723c76192a9af62f9` |
| `stocklookup_core/evidence/dual_reader_form_contract.py` (source closure; not yet pinned) | `51a668ea3ee8bf13b36b8484d71e1ac5feaf1e299c45f7a2a83e86b8a49247f3` | `a415cb4de5e8f8ae35db80c0e7b0b0165a626a06076cff0e2abcca3e0fe3d01d` |

No E-tier frozen source is touched. Capacity receipt and protected capacity tests
remain untouched. HL must retain the prior 226b… → 4643… transition as well as
this continuation, include the form module's closure, and run the normal corrective;
these development checks do not grant capacity/release authority.

HL next: admit the native lane for this exact development scope; review/commit the
candidate and chain the capacity corrective; obtain fresh blind D2 income/note
readings from the spec; retain proper source/metadata/assurance proofs and replay
common admission. Missing original H1/2025 basis still blocks compatible TTM.
Daily/config activation and any authority promotion remain separate gates.

No commits, branch changes, Daily, runtime, production or registry writes were made.
