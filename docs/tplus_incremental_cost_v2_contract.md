# TPLUS_INCREMENTAL_COST_V2 — scope contract

First milestone of the Owner-approved `STOCKLOOKUP_SUSTAINABILITY_PROGRAM_V1`. The Owner approved
D1 (the program and the native reconcile) and D2 (the T0 integrity policy below) on 2026-11-03.
This document defines the scope. Results are recorded in the
[feedback containment contract](owner_daily_feedback_resource_containment_contract.md) and its
rehearsal receipt.

## Program order

Each step needs its own admission:
1. M1 — this milestone.
2. M2 — storage ledger and 30/90-day runway alert.
3. M3 — verified duplicate consolidation (needs D4).
4. M4 — hot/warm/cold lifecycle with byte-identical restore (needs D5).
5. M5 — observer scheduling.
6. M6 — operations resilience: vault after Daily, restore rehearsal, runbook.

## Runway (host-local, 2026-11-03)

- T: free: 379.7 GiB.
- Floor: 160 GiB (reserve plus writer).
- Retained-evidence write: about 14.6 GiB per session.
- Runway: about 13 sessions.

## M2 — storage ledger and 30/90-day runway alert

`tools/storage_ledger.py` is read-only. It reports physical bytes for retained-evidence
(by artifact family and session), the T+ store and sidecars, IID, scratch,
recovery-checkpoints, worktree-archives, and content duplicates identified by SHA-256,
link count, and file id. Hashing is bounded by a byte budget and resumes from its state
file. It takes no locks and stops when a Daily is running. Runway is the free space above
the 160 GiB floor, in sessions and at 30 and 90 days, using the measured session size.
A session is a real calendar day that stands alone in a path component, either
`YYYYMMDD` or `YYYY-MM-DD`. An 8-digit slice of a hash is not a session.
A stopped metadata scan keeps the inventory it measured and withholds runway projections.
Runway uses session days on or before the scan date. Later dates are horizon
labels inside files, and they stay in the session list without setting the median.

`owner_daily_progress.py` probes the volume that holds the Daily output path. It does not
probe `C:\` unless that volume is the output volume. Under 10 sessions is a warning. Under
5 sessions is a critical warning. `AUTHORITY_EFFECT` stays
`NONE_OPERATIONAL_OBSERVABILITY_ONLY`. Admission and preflight do not change.

## Measured cause (Daily 2026-11-03)

**Pre-handoff T+ completed**
- Elapsed: 967 s.
- Phases: discovery 327 s, evaluate 606 s.
- `stream_sha256_bytes`: 34.4 GB.
- `partitions_invalidated`: 16.

**Post-handoff T+ failed**
- Status: `FEEDBACK_RESOURCE_TIMEOUT` at 1,200 s.

**Cost centres in `prospective_feedback_streaming.py`.** Both scale with the size of the corpus:
1. Every T0 is fully hashed before its receipt is looked up.
2. Each invalidated partition re-parses its whole T0 snapshot.

Partition invalidation itself (`context_key`) is semantically required and is unchanged.

## Scope

- **Fingerprint receipts.**
  - A T0 source receipt is trusted inside Daily only on an exact file fingerprint match: volume id, file id, size, mtime_ns and NTFS ChangeTime.
  - Any mismatch forces a full SHA-256.
  - A full re-hash scrub runs outside Daily (D2).
- **Evaluator-input sidecar.**
  - A rebuildable, SHA-verified sidecar holds exactly the evaluator inputs for each T0.
  - Re-evaluation reads the sidecar instead of the T0.
  - The T0 stays the only authority.

## Invariants

- Feedback contract, classification, horizon, maturity, ordering and `artifact_identity` are unchanged.
- Output bytes are identical for identical inputs.
- Deadline stays 1,200 s and the memory ceiling stays 2 GiB.
- Post-handoff stage wiring is unchanged.
- No authority effect, no change to the storage form, no hardlink or compression.

## Acceptance targets

- Parity with the unchanged builder.
- Warm stage with one new T0 ≤ 600 s.
- Pre + post stages ≤ 900 s.
- Child peak ≤ 2 GiB.

The real Daily observation follows the Owner-gated merge and deploy.
