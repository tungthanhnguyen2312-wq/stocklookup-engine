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

## November 13 host observation

M1/M1b are deployed (PR210/212). The guarded calls took 322.877 s pre-handoff and
470.727 s post-handoff (793.604 s combined), with peaks of 1,253,130,240 and
1,284,591,616 bytes. The respective child receipts report 42 and 43 T0 fingerprint hits,
24 and 26 evaluator-sidecar hits, 2,551,467,498 and zero streamed SHA-256 bytes, and zero full
IID parses. The post pass records `INCREMENTAL` with the newly bound November 13 T0;
the pre pass keeps the earlier observation boundary. Their durable outputs were
1,761,400,190 and 1,817,859,487 bytes. These are retained host measurements, with no new
production replay. The November 11 and 12 child receipts total 1,030 and 1,034 s
respectively, above the 900 s target even before launcher overhead. The post pass
recorded zero streamed SHA-256 bytes on all three days. Repeatable combined
cost remains the native closeout gate.

M2 source is delivered in PR213/242. The partial-scan tests cover withholding runway.
Use the existing bounded ledger when a fresh inventory is needed.

## Retained I/O corrective

The November 11 and 12 child-builder receipts attribute the combined overrun to
post-handoff evaluation (592.864 and 589.528 seconds, versus 323.176 seconds on
November 13). Both earlier runs rebuilt 8,415 more rows. Required partition
invalidation remains in force. The settled store avoids rereading a contribution
already validated by the evaluator. Assembly verifies the canonical body and
emitted identity header and computes the raw hash in one disk readback.

A guarded component replay of 2,000 settled hits and 26,928 retained output rows
through November 12 took 60.561 seconds at baseline and 34.014 seconds after the
change. Peak child commit was 592,506,880 and 594,432,000 bytes. The rows,
assembled artifact identity and raw bytes matched. The replay did not exercise
a full pre/post pair or the cold rebuild caused by the new evaluator digest.
Repeatable warm and combined acceptance remains open.
## Resume and warm acceptance

The feedback builder commits a session partition only after the row and
trigger segments are flushed, hashed and moved into place. The manifest is
published last. To resume an interrupted offline rebuild, invoke the same
bounded feedback runner again with the same retained input root and isolated
state root. Keep the evaluator and verifier source unchanged between attempts.
The runner rechecks source and context keys, manifest identity and both segment
hashes. An unfinished partition is rebuilt. A strict prospective partition
must match the current capture, calendar and as-of context. A resumed artifact
is published only after complete assembly and verification. Record each
attempt separately and keep earlier timeout receipts. Use a distinct scratch
output when preserving a failed attempt's status.

The November 11 and 12 status files identify the T0 admitted by each post
handoff stage. They cannot restore the complete input view seen by either
historical child. In particular, the reduced clone does not preserve the
storage catalog, capture chain and calendar, seal and write receipts, and all
inventoried paths. The original handoffs reference absolute Production paths.
The post-handoff capture context also depends on the invocation's as-of
boundary. Record HISTORICAL_BOUNDARY_UNAVAILABLE for these historical warm
pairs unless that complete input view is recovered and verified.

For the next genuine session on an authorized candidate, use the ordinary
pre-handoff and post-handoff feedback calls with the same qualified state,
source revision and retained root. Collect the evidence from an Owner-run
session or from an authorized read-only capture of both input boundaries for
the existing offline rehearsal. Retain the two status and completion
manifests, the sealed T0 and its canonical handoff, and the matching bounded
child BEGIN/END events and Job peak receipts. Bind the events to the same
session and Daily run. Confirm the post-handoff input set adds exactly the
handoff's T0, and check both complete artifacts against a qualified baseline
on identical inputs by identity, raw SHA-256 and row count. Keep cold resume
attempts out of the warm totals. The new-T0 stage must take at most 600 seconds,
the two guarded child intervals together at most 900 seconds, and each Job
peak at most 2 GiB with the 1,200-second deadline in force. Preserve the
source and input identities used for parity. Prior component measurements or
two calls after the handoff do not satisfy this gate.

## Measured cold bootstrap (2026-11-14, offline)

Candidate ce34c945, retained root read-only, isolated scratch state, unchanged
1,200-second deadline and 2 GiB Job limit. Verifier receipts were valid. The
evaluator, partition and settled stores started empty, as they would after this
change is deployed. Three guarded post-handoff invocations for November 13 used
the same state root:

| Invocation | Outcome | Wall s | Peak commit B | Partitions after |
|---|---|---:|---:|---:|
| 1 | FEEDBACK_RESOURCE_TIMEOUT | 1,200.021 | 741,539,840 | 30 |
| 2 | FEEDBACK_RESOURCE_TIMEOUT | 1,200.054 | 715,239,424 | 40 |
| 3 | COLLECTED | 696.189 | 1,272,778,752 | 44 |

Each timed-out child was reaped, its tree termination was confirmed, and it
published no output or completion manifest. Invocation 3 reused 40 partitions
exactly and built 4. Its artifact matched the retained November 13 artifact on
identity, raw SHA-256, 1,817,859,487 bytes and 74,052 rows. The chain, T0, legacy
and inventory input sets matched too. Its `input_digest` differed. The full
input manifest was captured on the live root, before evaluation. It reproduced the
candidate digest. Replacing only `future_chain.as_of_date` (`io_known_at()`,
2026-11-14 UTC) with the retained run's date (2026-11-13) reproduced the retained
digest exactly. Every other input was therefore byte-identical: T0 and legacy
hashes, inventories, price sources, the handoff inventory, the marker, capture
sessions and calendar revisions. The difference is only the as-of date of the
call. The same date also feeds `context_key` for strict prospective sessions, so
those partitions are rebuilt on each new calendar day by design. Cumulative cold
cost was 3,096.264 seconds.

The partition source key and the evaluator-input projection both include this
module's digest. Any deployed change to it therefore rebuilds the whole T+
derived state. On this host that needs more than two guarded calls. The first
Daily stages after such a deployment are expected to time out while still
persisting progress. Plan that bootstrap before release. These cold calls are not
warm acceptance.

## Rollout: seed before the first Daily

Use the existing one-time seed (see the
[containment contract](owner_daily_feedback_resource_containment_contract.md)).
Do not deploy without it. This change keeps the verifier digest, so Production
receipts stay valid. The seed only rebuilds evaluator-input sidecars under the
new projection digest. It reads the retained root, writes only Production
feedback state, and publishes nothing. Daily passes no state root, so that state
is the retained-evidence root itself. The seed is Owner-run, outside Daily, after
the fast-forward Production sync and before the next Daily:

```
python tools/run_prospective_decision_outcome_feedback.py --seed-state-only --root <retained-evidence> --state-root <retained-evidence>
```

Exit 33 means seeded. Partitions and the settled store are keyed by the code
digest and start empty. That is the expected first-call cost measured below.

Offline qualification (2026-11-14, isolated state): a copy of the Production
verifier receipts, plus sidecars that the seed CLI then revalidated. Every
sidecar hit checks source SHA-256, projection digest, content SHA-256 and row
count. The seed took 130.296 s (exit 33, 420,515,840 B, all sidecars hit). The
next guarded November 13 post-handoff call, with no partitions and no settled
entries, collected in one call. It took 717.946 s with a 1,305,255,936 B peak.
It built 44 partitions, had 41 sidecar hits and 31,977 settled misses, and
re-evaluated 74,052 rows. The artifact was byte-identical to the retained
November 13 artifact. Without the seed, the same state needed three calls.

A seed from empty sidecars must parse every T0. Expect about 2,200 s (sidecar
work in the three cold calls). It has no Daily deadline. On the first Daily
after deployment, expect the pre-handoff stage at about 720 s. The post-handoff
stage reuses that run's settled entries. That Daily may exceed the 900-second
combined target once. Neither stage is expected to reach the 1,200-second
deadline. The seeded first Daily is a bootstrap, not warm acceptance. Measure
warm acceptance on the following session.
