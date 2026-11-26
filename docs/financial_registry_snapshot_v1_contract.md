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

In this executor environment all 16 specs remain `REAL_REPLAY_NOT_CERTIFIED`:
11 have equal base/current blocked outputs but lack `pypdf` and `fitz`; five lack
original completion/evidence inputs. Missing parser dependencies caused retained
text proof to remain unavailable. These comparisons certify neither real
admission outcomes nor historical availability. HL must replay with the approved
dependencies before claiming real parity certification. Pytest was not run.

## A2 checkpoint and lease blocker

A2 has not started. The initial durable journal writer
`stocklookup_core/acquisition/owner_daily_journal.py` has no registry-binding
parameter and is outside this task's write lease. It must accept the binding in
its initial atomic write; a second write would leave an unbound initial durable
record. An exact `run_owner_daily` source-transition fixture/archive also requires
additional leased paths before the protected owner can be edited.

The planned A2 gate still must require capacity-receipt selectors and matching LF
hashes, reject unapproved or conflicting registries, bind consumers and children
to identical snapshots, and propagate bindings into initial, terminal and failure
records. The current A1 loader is not that hard Daily gate. The capacity receipt
and preflight test corrective are owned by HL. Production activation remains an
Owner decision; no Daily or Production operation was performed here.
