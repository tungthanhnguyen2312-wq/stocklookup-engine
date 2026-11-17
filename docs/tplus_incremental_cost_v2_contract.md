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


## Verified T0 projections and Producer progress

PR #267 reuses matching T0 projection receipts and adds Producer seal progress.
A November 17 scratch replay of the retained September 16 T0 (91,489,054 bytes)
verified cold in 2.115 seconds. Warm reuse took 0.064 seconds, read zero snapshot
payload bytes and produced an identical projection
(`8f0a1555c31eff4cbeb813cac5d13221da3d1cd3a411cedabd89c9f765780b6b`).
No Production state was written. Merge and source sync require live D4a
acceptance from the November 17 Owner Daily.

Full retained corpus, same host and conditions (November 17, candidate
`b7e048c9`, Production retained root read-only, scratch receipts; 48 registry
sessions, 41 T0 files, 54,614,905,595 bytes, 40 qualified, 67,320 records):

| Pass | Wall s | Peak commit B |
|---|---:|---:|
| Unchanged verifier, no receipts | 1,344.223 | 2,065,248,256 |
| Candidate cold, writes receipts | 1,413.302 | 2,065,330,176 |
| Candidate warm, 41 receipt hits | 17.160 | 2,145,533,952 |

All three artifacts are identical
(`53eb1ea77c000ffb1a0abcf24b4c6c3771e3b419853d167e3eb0bdeabc29973e`), and their
records and validation equal the retained November 16 Production artifact. The
one-time cold cost is 69.079 seconds (5.1 %) over the unchanged verifier; the
earlier 1,983.592-second replay reflected host load, not the receipt path. One
new 2.5 GB T0 verifies cold in about 69 seconds, so a warm Daily stage is about
86 seconds against 1,260.047 seconds measured in the November 16 Daily. The 41
receipts hold 138,563,362 bytes. A receipt binds the T0 file fingerprint and
the verifier source digest, not its own location, so receipts built offline by
the released source are valid in Production's receipt root. Placing them there
is an optional Owner-authorized step; without it the first Daily pays the cold
pass once.

## November 16 retained acceptance (local verification)

Released main `337590cdebc8f2a62939e3844d43ee8588e48f73` retains a genuine
November 16 Daily from source `799243cc8ffb3e5e3189a93bcfb1252e0fbc52b1`.
Guarded pre/post intervals were 327.124 / 560.542 seconds (887.666 combined);
child builder intervals 319.394 / 547.553 seconds. Peaks were 1,272,004,608 /
1,303,752,704 bytes. The post pass adds exactly the November 16 T0, reports
INCREMENTAL, 44 fingerprint hits and zero streamed source SHA bytes. Both
feedback raw hashes were independently verified. This session passes M1b's
600/900-second and 2-GiB limits; repeatability and PR258 candidate acceptance
remain separate, unclaimed gates. No new Daily or replay was run.

D4a is PARTIAL: IID shares one file; the two delivery pairs are independent but
byte-identical. The canonical Owner route omitted `reuse_immutable_delivery`
when invoking the Producer. The release corrective passes the existing switch;
new outputs use the existing immutable writer, legacy aliases remain untouched.

## Full-universe NDJSON subtree codec (M3 candidate, default off)

`stocklookup_core/evidence/record_subtree_codec.py` (`record_subtree_refs/v1`) stores later exact
repeats (>= 1 KB canonical) of a container subtree inside one NDJSON record as an RFC 6901
pointer to the first occurrence. `decode_record` restores the exact logical record; legacy rows
pass through; records using a reserved key are never encoded; malformed pointers, unsupported
versions and truncated rows refuse. Every Producer reader decodes: the Owner Daily M1 verifier
(refusal `M1_AI_FULL_UNIVERSE_COMPANION_UNREADABLE`), the ticker extractor, the extract tool and
market-gate decision quality. When encoded, the bundle manifest entry names `record_encoding`.
The published AI handoff carries no NDJSON. `build_delivery(full_universe_subtree_codec=False)`
is the only switch and no production caller enables it.

Offline on the retained 11-16 file (1,683 records): 1,048,622,846 -> 392,036,587 bytes
(allocated 1,048,625,152 -> 392,040,448); decoded stream sha256 equals the original
`11976dda…`; encoded sha256 `7711d49a…` is reproduced across runs. Delivery write 72.9 -> 176.9 s,
peak working set 66 -> 76 MB; full sequential decode 36.2 -> 56.3 s (65 -> 86 MB); extractor
five-ticker lookup 13.6 -> 3.9 s. The codec is not on the T+ feedback path.

Activation is a separate M3 admission: it needs an explicit Owner decision recorded in native
state, a production caller passing the switch, and acceptance on a real Owner Daily (byte and
identity parity, M1 verifier PASS, delivery runtime). Rollback is removing that caller; encoded
retained sessions stay readable through `decode_record`. IID is out of scope: 22 modules read IID
artifacts (7 through the shared loader) and T0 seals bind IID identities.
