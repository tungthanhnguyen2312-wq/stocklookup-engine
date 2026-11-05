# Vault incremental snapshot and retention contract V1

Owner-authorized `STOCKLOOKUP_VAULT_INCREMENTAL_SNAPSHOT_CONTRACT_AND_OFFLINE_ACCEPTANCE_V1`.
Offline opt-in tools and synthetic acceptance only. Authority effect NONE. No Daily hook,
scheduler, source deletion/relocation, provider acquisition, deployment or automatic successor.
Existing Core/Tactical/Portfolio, original completion/cutoff, source knowledge and T0 authority
remain unchanged. Backup is preservation, not permission to remove a referenced source path.

## Implemented interfaces

- `python -m tools.vault_snapshot --opt-in --source SOURCE --vault VAULT --volumes volumes.json
  --max-bytes BYTES snapshot --boundary boundary.json --boundary-sha SHA
  [--previous MANIFEST --previous-sha SHA]`
- Same opt-in prefix with `sqlite --relative db/VERSION.db --source-sha SHA` for a **closed** DB.
- `python -m tools.vault_retention --proposal PROPOSAL --proofs PROOFS [--vault-available]`
  emits preflight JSON to stdout. It has no delete, migrate, download or scheduler command.
- `restore_verify` is a read-only library function for an explicitly restored fixture/directory;
  `archive_resolution` is an offline specification, not a production fallback.

The production CLI requires explicit W: destination; Windows native observation reads actual
mount GUID, label, Healthy/OK state and rejects unknown/missing/wrong identity. Both expected
volume records are `{id, label, healthy: true}`. Distinct source/destination mounts and existing
roots are required. Paths reject traversal, ADS, reserved aliases, symlinks, junctions and reparse
points. Native SQLite exclusivity currently requires Windows; other hosts refuse that operation.
Fake volume observers are dependency injection for small offline tests, not CLI attestations.
Default eligible payload ceiling is 64 MiB. Larger explicit budgets require separately authorized
operator use; the ceiling bounds payload size, not cumulative bytes across verification passes.

## Completion boundary and identity

`vault_completed_boundary/v1` contains `status=COMPLETE`, exact `session_identity`,
`source_identity`, original `cutoff`, `receipt_refs`, `seal_refs`, and `files`.
Each file has `relative_path`, native `size`, `sha256`, `family`, `state=COMPLETE`,
`immutable=true`, `lock_dependent=false`. Allowed families are `IMMUTABLE_SESSION`,
`RAW_EVIDENCE`, `T0`; unknown/mutable/incomplete/temporary/database families are excluded.
Each seal/receipt reference is `{relative_path, sha256}` and must itself belong to the included
closure and pass native-byte hashing. Caller pins the exact boundary SHA. Old mtime alone is
never a completion criterion. Boundary bytes are rechecked before manifest completion.

This is a consumer input contract: an upstream adapter/operator must establish real Producer
completion, original receipt/seal authority and closed dependency closure before emitting it.
The tool verifies native hashes and reference closure; it does not invent a Producer completion
adapter, reinterpret any legacy schema, or promote a caller's declaration to Daily authority.
The October 8 vault's timestamp selection does not qualify future immutable boundaries.

The canonical plan hash names an immutable version under `snapshots/PLAN_SHA`. Source-relative
paths, source and session identities, cutoff, seal/receipt references, volume identities and
native hashes are retained in the COMPLETE manifest. Receipts have no wall-clock nonce, name
the exact canonical manifest SHA, and return identical bytes on repeat. Their identities bind
the captured filesystem fingerprints as well as content; they are not portable T0 identities.
Earlier manifests and files are never overwritten. A new changed file requires a new explicit
completed boundary; its old vault version survives. The tool never edits the source version.

## Explicit per-session emitter

Owner backlog directive `CODEX_PROMPT_E2E_20261105_BACKLOG_FULL_AUTHORITY` authorizes
the D3 emitter and copy-only session backups. `python -B -m tools.vault_boundary_emit
--source COMMON_ROOT --repo PRODUCER --retained RETAINED --session YYYY-MM-DD
--out OUTPUT [--max-bytes BYTES]` writes only within OUTPUT, disjoint from COMMON_ROOT.
It never invokes Daily, acquisition, a seal writer, publication, or source cleanup.
The default byte ceiling remains 64 MiB; real retained sessions need an explicit budget.

`vault_session_closure/v1` is an explicit session-artifact preservation boundary:

1. Read the registry from the exact Git HEAD blob, retaining commit and blob SHA256.
   The selected completed row and selection must also match the working registry.
   Require validated trading day, all required inputs and exact frozen identities.
   A row present only in the working registry is refused, including October 26.
2. The exact tier-1 `canonical-post-close-v1/<session>/session_handoff_bundle.json`
   selects one operation identity and Producer run identity. Recompute both with the
   existing owner functions. Include the entire identity-addressed
   `daily-research-session-operations-v1/<session>/<hash>/` and
   `daily-producer-runs-v1/<session>/<hash>/` trees, including manifests and delivery.
   Verify original delivery-manifest native SHA/size claims.
3. Include the one `canonical-daily-operation-v1/<session>/op-*/` tree whose
   `daily_operation_record.json` binds those identities and is LOCAL_COMPLETE.
   The existing adapter additionally requires COMPLETED Producer, runtime/trusted READY,
   and the exact resolved acquisition session. Ambiguous matching records refuse.
   Boundary `cutoff` is the original canonical record's `requested_at`, with
   `cutoff_basis=ORIGINAL_CANONICAL_REQUESTED_AT`; it is not backup time or a new
   source-knowledge/PIT claim. Original finer-grained cutoffs stay in their native files.
4. Include every frozen registry input, any attached macro input, every Producer
   source-plan artifact, the same-session shadow recommendation if bound, and the
   tier-1 handoff's direct deeper-bundle/recommended-input paths. Frozen input content
   SHA identities are recomputed with the existing bounded canonical JSON stream;
   both identity and exact registry path must match. Include adjacent tier indexes.
   A missing downstream feedback locator is omitted only when the original tier-1
   identity is explicitly null and the included same-session tier-2 bundle binds the
   exact path with null identity, UNAVAILABLE status and a reason. Retain that negative
   proof in `unavailable_optional_refs`, pinned to the native tier-2 SHA. A missing
   claimed/READY observation or any other missing dependency still refuses.
5. Require retained original T0. Include its whole identity directory, snapshot,
   seal index and write receipt. Its operation binding and native snapshot SHA must
   match. The existing native seal-index verifier must admit the original inode and
   receipt. A diagnostic, unverified or missing T0 is refused; never reseal a copy.

These are the complete dependencies of this session-artifact boundary. Nested raw-source
URLs, provider provenance and historical analytical references remain native metadata;
this is not a claim that the entire raw lake, runtime databases or all historical
cross-session analysis can be reconstructed. Source retirement/portable T0 admission
remain separately governed. Backup never authorizes source removal.

No caller file list or immutable boolean can select payloads. Mutable/cache/stream,
config/data/runtime, accumulator, temporary, lock and database members refuse the
whole boundary. Native absolute references from split workspaces may be mapped only
to their exact location inside COMMON_ROOT, after traversal and reparse checks.
There is no path search, rebasing, transparent archive fallback or retained JSON edit.
The adapter uses that same exact mapping for T0, retaining original proof bytes.

Discovery fingerprints are checked under deny-write/delete source handles. Native
hashes, original completion/seal references, committed HEAD stability and the existing
`qualified_boundary` checks precede publication of `boundary.json`; the emitted
boundary is consumed unchanged by the adapter. Candidate JSON may remain under OUTPUT
after refusal, but is never published as `boundary.json`. The boundary's pinned SHA
must be passed to the adapter. The Git commit/blob pin supplements the original
registry proof; it does not commit or relabel any pending session.

## Incremental verification and interruption

A prior COMPLETE manifest must have a separately trusted expected SHA, the same source root
and volume identities, and verified object fingerprints. Unchanged large files can reuse prior
vault-relative object paths without another copy/hash when native SHA **and** full source and
destination fingerprints match. Fingerprints include file ID/device, size, mtime, link count,
physical allocation, and **NTFS ChangeTime**, not Python's Windows creation-time `ctime`.
POSIX fixtures use ctime; arbitrary hostile administrator changes to metadata are outside this
offline cache trust model. A mismatching destination refuses; a changed source needs its newly
qualified native SHA. Receipt/seal files remain directly verified each run.

Legacy verified ledgers remain retained proof, but lack the new strong change fingerprint.
They cannot be silently treated as cache leases. A separately approved bounded import/qualification
adapter must pin their recorded SHA and obtain fresh strong fingerprints before initial adoption.
No 100-GB rehash or legacy-ledger import was performed in this milestone.

One exclusive destination writer handle protects publication. Each Windows source handle denies
write/delete sharing during copy; existing incompatible writers refuse. Chunks go to a separate
tool-owned staging area. Resume requires the same immutable plan and source fingerprint and
compares every retained prefix byte against source before continuing. Native SHA, size and
post-copy fingerprints are verified; all source/vault fingerprints and volumes are rechecked
before completion. Partial files are never COMPLETE. A prepared deterministic receipt precedes
exclusive manifest publication; a crash between manifest and final receipt can resume publication.
Only owned destination staging files may be removed as part of atomic publication. There is no
source unlink, cleanup synchronization, MIR/PURGE, automatic old-version pruning, or relocation.

## SQLite boundary

Raw snapshot excludes database files. Separate SQLite `Connection.backup` uses read-only
`mode=ro&immutable=1` source **only after** Windows deny-write/delete exclusivity and absence of
WAL/SHM/journal sidecars. Identity is a caller-pinned native source SHA and exact volume.
Unclear/open writers, sidecars, unknown identity or budgets refuse. No source SQL writes,
PRAGMA journal changes, runtime configuration changes, lock replacement or production DB run.
Bounded Backup API pages, no busy retries/sleep, source/target integrity_check, source post-hash
and fingerprint, destination SHA and an immutable version receipt establish a consistent backup.
Backup native bytes may differ from source; logical backup is not evidence of an exact duplicate.
An interrupted DB stage refuses and requires a separately selected recovery/version operation.

## Retention preflight and proposed restore contract

Categories: ACTIVE_REQUIRED; VERIFIED_RECOVERABLE_COLD_CANDIDATE; HISTORICAL_DISTINCT;
EXACT_DUPLICATE_BUT_REFERENCED; UNVERIFIED_OR_UNKNOWN; REGENERABLE_WITH_PROOF.
Input proofs are audited operator records, not inferred from a boolean backup flag. Proposal
identity is the canonical complete candidate hash; rank is presentation and need not be unique.
Every row reports exact paths and proof slots for source volume, measured allocation, evidence
identity, complete verified W coverage, runtime/code/manifest references, cross-session dependencies,
hardlink consequences, restore destination/procedure, and invalidation when the vault is absent.
Missing proofs stay UNKNOWN. Nonempty runtime refs protect a candidate even with valid backup.
Historical distinctions and referenced duplicates remain protected; verified cold preflight
requires complete coverage with manifest/restore receipt identity, all exact source paths,
known-empty dependency/reference closures, allocation and recovery proof, and available W.
Regeneration needs an explicit recipe/input/golden-output proof, never a guessed cache label.
No category authorizes deletion. All output rows carry `execute=false`, `deletion_authorized=false`.

Proposed recovery sequence, requiring separate operational approval:
1. Resolve an explicitly registered archived original identity before any missing-file acquisition.
2. Observe the exact W GUID/health; absence yields ARCHIVE_UNAVAILABLE, not download/regeneration.
3. Select a pinned complete manifest and dependency closure. Restore into an explicit staged
   recovery destination; verify native SHA, receipt/seal links, original knowledge time and cutoff.
4. A storage receipt binds original path to restored bytes without rewriting sealed source receipts.
5. Run the relevant existing semantic verifier. Restored bytes alone do **not** satisfy inode-based
   T0 fingerprint checks. A separately approved portable verifier must preserve the original
   authority and distinguish original native proof from the new storage-location proof.
6. Admit the recovered path only via an approved consumer contract. No transparent W fallback.

## Daily dependency analysis and minimum future change

| Existing dependency | Consequence / required future contract |
|---|---|
| `runtime_paths.py`; host runtime root; absolute paths in retained operation/AI manifests | Explicit original-path mapping, no runtime relocation by inference. Runtime root alone does not relocate retained operations. |
| `prospective_decision_retention.py`, `prospective_pit_capture_retention.py` whole-history globs | Versioned identity catalog must expose archived/unavailable versus never-retained entries before a bounded consumer selects its exact closure. Missing directories cannot silently shorten a cohort. |
| `prospective_t0_seal_index.py` file fingerprint and native/per-record hashes | Portable verifier/storage receipt as above; no seal/index rewrite or fabricated T0. |
| `atomic_io.py`, existing worktree hardlinks | Per-volume file-ID/link closure; path-size totals are not physical reclaim. Cross-volume copies do not preserve hardlinks. |
| `canonical_daily_operation.py` retained exact-session resume; immutable snapshot writers | Archive state checked before acquisition, explicit restore required; missing archived evidence must never trigger silent live redownload. |
| Feedback pre/post accumulators and streaming caches | Keep mutable files hot and out of snapshot boundaries; archive only independently completed immutable inputs. Cache absence is not loss of original evidence authority. |
| Session markers, calendar/cutoff, source knowledge and receipt identities | Resolve exact original session closure, not latest glob/date or copied file timestamps; preserve original authority and knowledge time. |
| Archived runtime-backup DB referenced by `dnse_ohlc_price_basis_capability.py` and `tools/run_vci_basis_pilot.py` | Those exact historical paths remain required until consumers gain explicitly approved mappings. |

No listed production module changed. Minimum future work is a fail-closed registered archive
catalog/resolver plus portable verification and bounded consumers, followed by explicit exact-path
source-retention decisions. There is no transparent fallback, silent reacquisition or live integration.

## Evidence, capacity and gates

[Host-local machine acceptance](internal/VAULT_INCREMENTAL_OFFLINE_ACCEPTANCE_20261009.json)
and [77-candidate preflight](internal/VAULT_RETENTION_PREFLIGHT_20261009.json) reuse the prior
bounded audit and receipt identities. No storage inventory/large hash/duplicate scan repeated.
They distinguish historical verified W backups and the 508-file data backup/restore drill from
complete production recovery eligibility. Proof gaps are explicit; verified immediately reclaimable
bytes are zero. Conditional allocation samples are not authorized reclaim.

Observed dated core outputs are logical bytes, include retries, omit independently named fixtures
and mutable accumulators, and do not measure physical C growth. October 5–8 mean is approximately
5.82 GiB per completed session; October 2 has unavailable T0 and is disclosed but excluded from that
mean. Planning 8 GiB and stress 12 GiB are assumptions, not policy thresholds. READY's 25-GiB guard
is unchanged. At approximately 125 GiB free, around 17 observed-assumption, 12 planning or 8 stressed
whole sessions remain above that guard. The 30/90/180-day scenarios use 22/64/128 successful weekdays,
no holidays/unrelated growth; W adds retained growth plus one 275,177,472-byte SQLite backup per Daily.
The acceptance JSON contains exact free-space observation, per-family logical bytes and all scenarios.

Backup alone does not lower C growth. Even conditional approximately 5.16 GiB reclaim buys less than
one planning session. Production integration, physical growth measurement, complete reference/hardlink
and recovery closure, and owner-approved exact source retention remain independent gates. Offline
acceptance does not mean the C capacity problem is solved or ordinary Daily can ignore preflight.

Focused tests cover first/repeat/new/changed snapshots, strong-fingerprint cache, mutation/writer denial,
interruption/resume, volume refusal, incomplete/temp exclusion, native receipt/seal proof, T0 preservation,
tampering, explicit restore, SQLite consistency/exclusivity, hardlink allocation, all retention categories,
referenced backup protection and archive absence without acquisition. No full repository pytest.

## Roadmap checkpoint

Starting main is `9db35f157af38baf3807be1a6a6827e77fd461dc`. The prior Economics HEAD sentinel is
frozen to `d4d9a0f969baf7ab559aa9d337aa1fd238d74635`: Git proves it introduced the unchanged prior
roadmap record, is an ancestor of the PR96 merge, and the native checker explicitly names that stale
sentinel target. The new milestone alone uses the documented HEAD self-checkpoint convention;
no fabricated future SHA. Native roadmap --check runs before and after the normal local checkpoint.
Queue stays empty. No push, PR, merge, Daily, deployment, production cleanup or authority promotion.
