# Financial registry snapshots v1

Task HL-20261126-CDX-34 implements the A1 data migration from merged baseline
`74017553c7a17c33a5464ec735f3700df669bbd5`. This contract preserves the existing
qualification contracts and adds no source, publication, PIT or execution authority.
The approved migration design remains the scope; this slice is not a redesign.

## Data ownership and immutable revisions

- `config/dual_reader_admissions/r0001.json` is offline only. Its `entries` are keyed
  by the unchanged CLI spec IDs. The offline runner retains all original exported
  spec names, CLI choices, tuple/list shapes, default spec, payloads and seal bytes.
- `config/official_financial_layouts/r0001.json` contains the shared document-SHA
  layout registrations. Their payloads are unchanged, including approvals and
  text-layer verification limits.
- `config/official_financial_issuers/r0001.json` contains exact names with their
  original provenance, the existing folded names and entity families. No folded
  names are inferred from exact names. Unknown-family refusal, exact legal-name
  matching and native fallback gates retain their existing semantics.
- `COHORT` stays an independent literal in `financial_evidence_currency_contract`.
  Registry membership never expands acquisition scope.

The schema version and revision are integers. Each entry has a distinct revision,
supersedes reference, review, input provenance and evidence-observation,
registration and knowledge-availability timestamps outside the legacy payload.
Historical timestamps not proven by retained evidence are explicitly `null`.
The top-level review records this migration; it does not establish historical
knowledge availability. Provenance cites the exact baseline source. Existing
reader/render bytes are hashed when available; missing hashes remain `null`.

Corrections require successor revisions and distinct target directories, never
in-place editing of released snapshots or existing seals. Original admission
completion instants and knowledge floors must not be changed. No review or
migration metadata is injected into legacy sealed payloads.

## Strict loading and Daily boundary

Small stdlib loaders live beside the existing layout owner and offline runner.
They reject duplicate keys, unknown schemas or fields (including nested fields),
invalid types, non-finite numbers, files larger than 1 MiB and escaping or
redirected paths. The bounded bytes are normalized CRLF to LF once, hashed and
parsed from that same immutable byte string. Parsed snapshots are cached using
those bytes, digest and role; callers receive detached copies. Layout sequences
and exact-name tuples are restored without modifying their values.

Daily source enumeration excludes the exact offline manifest directory with a
Git pathspec before listing paths, and also filters it before hashing. Shared
loaders have no default path into that directory. The Daily-readable snapshots
remain in the tracked capacity surface. Offline edits cannot change those shared
snapshots or advance any approval anchor.

## Conservation and replay

`tests/fixtures/registry_migration_v1/baseline_registries.json` freezes complete
entry equality, rather than entry counts. The layout predecessor archive and its
exact source transition conserve its baseline bytes. The currency fixture appends
a successor to the existing HAH transition and preserves that older transition;
its inline predecessor is hash-bound. The verifier checks exact active and prior
hashes independently of fixture claims. Historical receipt adoption is forbidden.
Unchanged filing, OCR-table, dual-reader and native-fallback owners are not edited.

`parity_report.json` records every registered spec. Retained-input runs use isolated
temporary landing directories and original completion instants. Base source is
loaded read-only with `git show`; no branch is switched. Complete reports compare
fact, citation and admission IDs, normalized values, rejections and every output
file SHA256. Synthetic equality is never admission evidence.

At the original A1 executor checkpoint all 16 specs were `REAL_REPLAY_NOT_CERTIFIED`:
11 have equal base/current blocked outputs but lack `pypdf` and `fitz`; five lack
original completion/evidence inputs. Missing parser dependencies caused retained
text proof to remain unavailable. These comparisons certify neither real
admission outcomes nor historical availability. The original handoff therefore required HL replay with the approved
dependencies before real parity certification. A2 leaves the per-spec replay
artifacts unchanged and does not rerun admission replay. Pytest was not run by
this executor.

## A2 Daily integrity gate (implementation pending HL validation/release)

Tasks HL-20261126-CDX-35/36/37/38 add the gate, the optional child-load correction,
the HL-authorized capacity selectors and chained compatibility corrective, and
the malformed-attestation and import-cycle fixes.
No Daily, host preflight or Production operation was performed. The corrective
follows `decision2_hah_bwe_admission_corrective`, pins every changed capacity
source and both shared snapshots, and preserves all historical corrective entries
and measured values. No new capacity measurement was performed; this grants no
release authority.

The existing capacity receipt must contain exactly two `financial_registry_inputs`
selectors, keyed `layouts` and `issuers`. Each selector has exactly `role`, `path`,
`revision`, `approval_reference`, and `approved_at`. Roles must match the keys;
revision is a positive integer, and the path must be the corresponding shared
registry's immutable `rNNNN.json` revision path. Approval references must be
nonblank and not unknown/pending/unapproved sentinels; approval times must be
non-null timezone-aware instants. These fields record governed approval of the
capacity receipt; registry-internal migration metadata is never that approval.

The gate validates the capacity schema and CRLF-to-LF convention, rejects duplicate
JSON keys, and requires each selected snapshot's LF SHA256 to equal its entry in
`source_sha256`. It fully validates each selected snapshot's schema and revision,
including existing provenance, type, conflict, path-redirection and 1 MiB limits.
The selectors reject unknown fields. Unrelated capacity history and limits retain
their existing contract. No digest sidecar, feature flag, memory-band fallback or
offline admission manifest can satisfy this gate.

`run_workflow` gates before its first durable journal write or analytical work;
direct `_run_daily` callers are gated too. The journal's initial atomic write
already includes `financial_registry_inputs`. The record contains
`layouts:{path,revision,sha256_lf}`, `issuers:{path,revision,sha256_lf}`, and
`capacity_receipt_sha256_lf`. Every existing journal/receipt value is preserved;
the binding is additive operational metadata, outside historical analytical seals.

The selected immutable bytes are parsed once and cached in the shared loader.
Parent binding refreshes existing registry references; child consumers verify the
same receipt and snapshot digests on import, then use detached cached snapshots
without reopening source files. Bindings flow through the child environment.
Run-token/PID attestations are retained beside the journal. Registry loading is
lazy: neither the direct Daily child nor a descendant is required to import it.
The parent rejects differing bindings, malformed or duplicate attestations, and
PIDs outside this run's owner-descendant lineage. Tokens cannot reuse a prior
invocation's attestations. The additive `financial_registry_child_attestations`
records sorted `pids` and status `BOUND` when any valid attestation exists, or
`REGISTRY_NOT_LOADED_BY_CHILD` when none exists. Terminal and failure receipts
and journal details carry this result. The child command, launcher lifecycle,
and import-time `bind_active_workspace` remain unchanged.

The layout owner writes import-time child attestations directly; the journal's
compatibility wrappers delegate to that owner without a reverse import. Directory
validation, OS ancestry proof, atomic serialization and record format are unchanged.
Attestation parse and shape failures raise
`ValueError("REGISTRY_CHILD_ATTESTATION_INVALID")`; lineage and binding mismatches
retain their fail-closed refusals.

Terminal, BLOCKED/PARTIAL and failure receipts carry the identical additive binding.
Failure before a binding can be verified records `null`, never a stale or invented
approval. Integrity refusal never falls through to analytical resume checks.
The journal also retains the binding on later failure. This is not a PIT assertion:
original completion instants, seals, knowledge floors and `pit_backtest_eligible`
remain unchanged.

The exact Daily successor archives the A1 source bytes and peels into the existing
E6 chain. The layout fixture appends an exact successor with inline, hash-bound
A1 bytes before its unchanged original transition. Both boundaries independently
pin prior and active LF hashes in the verifier and grant no release authority.
See the A2 checkpoint for validation limits and capacity deltas.
