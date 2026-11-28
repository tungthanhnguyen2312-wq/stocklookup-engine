# Bounded EVF / SSI form support — HL-20261128-CODEX-EVF-SSI-FORMS

Development-only extension of [Decision 2](dual_reader_reviewed_transcription_v1_contract.md).
No actual facts were admitted. Common-owner integration and evidence remain blocked;
this note does not change operational state or activate the research config.

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

**Required authorized follow-up:** `official_financial_filing_evidence.py` independently
adds `METRIC_SOURCE_TEMPLATE_PROOF_UNAVAILABLE` for these new metrics. Its template
check needs a bounded delegation to the fully verified form contract, and its admitted
classification needs to propagate the returned basis/provenance. That file is outside
this task's edit allowlist; no reason-removal hook or global template registration is used.
There are therefore no admitted EVF/SSI rows to expose downstream yet.

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

No commits, branch changes, Daily, runtime, production or registry writes were made.
