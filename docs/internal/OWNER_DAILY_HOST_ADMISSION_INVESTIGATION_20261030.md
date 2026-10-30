# October 30 host-admission investigation — same memory recovery

Milestone: `OWNER_DAILY_16GB_HOST_AND_PIPELINE_MEMORY_RECOVERY_V1` remains ACTIVE.
No successor, new release authority, capacity receipt, IID cap, historical evidence
or ordinary Daily admission change follows from these diagnostics.

The Owner's `run-20261030T004537Z-749720e0` measured 16,859,357,184 total physical
bytes, 9,479,192,576 available physical and 20,016,119,808 available commit.
Measurement required 9,932,111,872 physical and 11,005,853,696 commit bytes.
Only `MEASUREMENT_PHYSICAL_BUDGET_LOW` refused admission, before any child.
The physical deficit was 452,919,296 bytes. Ordinary preflight separately remained
AMBER at its legacy scaled physical/commit bands. The measurement's 9.25-GiB
physical requirement models 8-GiB aggregate private commit, 0.25-GiB supervisor
and 1-GiB reserve; it is not a measured resident minimum.

The earlier positive process allocation-limit event remains valid: 7,227,588,608
process / 7,228,379,136 Job peak committed bytes, 173.2407257 seconds, last trace
`PRESEAL_BRIEF_BEGIN`. Denied allocations need not appear in committed peaks.
It is separate from both admission refusals and runtime physical-reserve failures.

Experimental direct invocation of the same CPython image with its original
virtual-environment launcher context reproduced executable, prefix and import
paths, avoiding the redirector process. A 384-MiB touched allocation completed
under a 128-MiB hard working-set request, with one additional boundary page.
Descendant refusal, timeout/reap and 21 existing procedure checks passed. The
required native-volume PowerShell helper was separately bounded before resume;
its exact command passed and arbitrary helpers refused. Windows Job working-set
configuration itself refused with privilege error 1314; no elevation was attempted.

These tests did **not** establish a safe physical admission envelope. A 2-GiB
resident-capped consumer attempt reached 5,544,972,288 private bytes, then stopped
at 1,025,769,472 available physical bytes. A targeted 1-GiB resident-capped held-graph
diagnostic reached 4,705,415,168 private bytes, then stopped at 969,801,728 physical
bytes. Both retained 7/8-GiB ceilings, reported no process/Job allocation-limit
event and confirmed complete tree reaping. Host physical consumption exceeded
the worker working set; limiting working set alone cannot justify ordinary
admission or a capacity receipt. A smaller diagnostic also refused an observed
two-page boundary overshoot; a later experiment reserved a 1-MiB margin beneath
its actual resident budget instead of treating the requested maximum as exact.

Code inspection found a genuine harness/production difference: the production
Canonical Daily call still decoded the original 521,967,045-byte evaluated-valuation
input via whole-file Unicode, while the retained harness used bounded decoding.
The production call now uses `load_record_artifact` before the unchanged
`accept_evaluated_valuation`. Full graph, metadata, identity acceptance and optional
failure semantics remain unchanged. An exact one-file successor preserves the
prior source and all older manifests/archives. This orchestration file is outside
the feedback/E4 executable digest; that digest stays unchanged.

Validation: 99 focused operation/source-boundary checks passed, including a
production-call regression that forbids whole-file Unicode loading for an
18-MiB full graph. Two retained-evidence setup cases lack their original August-26
and September-21 inputs; neither is claimed passing. No full stage qualification,
integration, deployment, genuine Daily or publication acceptance is yet claimed.

Next bounded option: serialized stages may enforce a **lower** 7-GiB aggregate
Job ceiling and derive an 8.25-GiB physical measurement budget from that actual
ceiling plus unchanged allowances. This does not change ordinary 7/8-GiB limits
or grant an ordinary launch permit. A one-time working-set trim may reclaim
idle user-application pages without killing processes or changing application
state; actual admission and runtime reserve checks remain mandatory. No retry
loop or repeated Owner reboot/command is authorized or requested.

## Further actual allocation defects and targeted proof

The evaluated-valuation product copy also used the full-Unicode atomic JSON writer
and full-graph validation. It now reuses the existing streamed native-byte writer;
validation parses every record but discards its record universes instead of
retaining a duplicate graph. Original metadata, all output fields, atomic
promotion and failed-validation preservation remain unchanged.

Separately, Financial V2 `_identity` built a whole-universe Unicode string and
UTF-8 buffer. It now feeds the same strict standard-library sorted JSON encoder's
chunks into SHA-256. Identity exclusions, nonfinite refusal, float/Unicode bytes
and all analytical calculations remain unchanged. This file is outside the
feedback/E4 domain; its original code remains in the preceding Git checkpoint.

The original 521,967,045-byte input reproduced its exact retained identity
`canonical_daily_financial_v2_materialization/v1:b3e29e70bbd2ba07eb713ca7f1c926bc4f54ec04a7fb2c09b13777734c216fb3`.
The original identity buffer hit a positive **diagnostic 4-GiB Job** allocation
limit before serialization. This lower diagnostic ceiling is not the historical
7-GiB process event. After the streaming identity correction, the old copy writer
separately reached its `COPY_BEGIN` and hit that same diagnostic Job limit:
4,297,633,792 process / 4,298,539,008 Job peak committed bytes, 45.2202 seconds.
These refused results never qualify capacity.

The candidate copy completed at 1,684,942,848 process / 1,685,843,968 Job private
bytes in 67.1945 seconds including load, independent identity/native-byte audits
and raw-input checks. Serialization itself took 29.1990 seconds. Output SHA-256
`4375df0c451c50892ccdb1c4130e304a49675357c98139caaf0d8e6a564add90`
matches an independent standard-library incremental encoder; the original input
hash is unchanged. This comparison holds no IID or caller graphs and is not
whole-stage qualification. Failed diagnostic setups and their original scripts
are retained separately, including the initial incorrect identity-prefix check.

131 affected memory, IID, current-product and Workspace checks passed, with three
retained-evidence cases deselected. These are additional to the prior 99 focused
operation/source-boundary passes. The one-time user-application working-set trim
terminated no process, changed no limits and recovered approximately 2.1 GB after
Windows paging; the observed baseline still did not satisfy an 8.25-GiB physical
budget. Working-set trimming is not a durable capacity guarantee.

The staged v10 run admitted the original retained graphs with a 1-GiB worker
working-set bound and unchanged 7-GiB process ceiling. It completed the native
preseal Brief, then encountered a positive PROCESS allocation-limit event while
building the full-universe NDJSON companion (1,073 of 1,683 rows completed).
Recorded peak process/Job private bytes were 7,472,635,904; minimum available
physical memory was 2,258,690,048 and minimum available commit 6,854,242,304.
The run was reaped after 863.1302368 seconds. This is a genuine allocation
inefficiency with host reserves still available, distinct from admission refusal.

The internal materializer now spools companion rows and incrementally attests
size/hash. Its public bytes-returning interface remains available and unchanged.
Independent immutable publication and Owner retention use bounded copies with
source/stage proofs, conflict refusal, private staging and fsync; no hard-link
reuse is enabled. 126 focused delivery, ownership, capacity and writer-lifecycle
checks passed (two platform skips). Read-only retained integration checks passed
21 cases; six failures reproduce on the previous f6b34dd6 source with identical
missing historical fixture or stale event-binding errors. The baseline comparison
and original logs are retained in streamed-companion-v11-tests. Full-stage
qualification remains pending; no IID cap, receipt, Production or release state
has been changed by these corrections.


The v11 companion completed at 1,048,919,265 bytes and its operation manifest was
written. The later post-seal path stopped at the physical reserve, not an allocation
limit: minimum physical 1,003,896,832; minimum commit 7,116,144,640; process/Job
peak private 7,090,937,856; resident peak 1,072,705,536; runtime 971.1285796 seconds.
Both 7-GiB ceilings remained enforced, no limit event was reported, and the whole
tree was reaped. The run is unqualified. A post-stop host snapshot recorded
6,848,229,376 available physical bytes; it is not substituted for the failure-time
observation or treated as a launch permit.

Post-seal original-artifact comparisons now retain the native output and source
hashes before/after. The original self-verifier decoded the complete 59,809,861-byte
primary bundle although only metadata was consumed. The projected reader still
parses every ticker/owner-focus row and all metadata, preserving all existing
session, identity, lineage and file-hash checks. Standalone native verification
results match: process peaks 591,491,072 baseline / 334,974,976 candidate; aggregate
Job peaks 592,412,672 / 470,863,872, runtimes 9.3173 / 6.5751 seconds. The 1-GiB
diagnostic Job is lower than Production. These hold no IID/caller graph and do not
qualify a combined stage.

The old atomic copy also retained the complete evaluated-product UTF-8 buffer.
An opt-in bounded copy now uses the same private sibling, fsync, pre-promotion
validator, atomic replacement and observability events. Existing atomic-copy and
bytes-writer functions are unchanged. Exact original identity/output checks pass
under a 2.5-GiB diagnostic Job: process peaks 1,685,078,016 / 1,163,051,008; Job
peaks 1,685,975,040 / 1,163,952,128; runtimes 57.1909 / 62.2582 seconds. Both outputs
match the independently qualified SHA-256
`4375df0c451c50892ccdb1c4130e304a49675357c98139caaf0d8e6a564add90`.
Original evaluated input and all v11 operation outputs are unchanged. Exact scripts,
old source-function archives and receipts are retained in post-seal-allocation-v12.

The canonical caller now drops only its finished Producer argument container after
return, releasing an otherwise unnecessary evaluated-valuation reference before
retention/feedback. Returned operations and borrowed caller evidence remain owned
by their existing consumers. Weak-reference checks prove both release and explicit
Producer-retained ownership. An exact one-file successor archives the bcca504e
source without editing older manifests/archives; an AST check permits only this
single deletion. Feedback/E4 domains remain unchanged. 146 focused memory,
delivery, atomic-write and lifecycle checks passed (two platform skips); 38 current
product checks passed (two retained cases excluded); 107 orchestration/historical
source-boundary checks passed (two retained cases excluded). The complete larger-IID
five-stage qualification is still pending; no receipt, IID cap or admission band
has been refreshed and Production remains unchanged.


The v12 attempt on the corrected post-seal source stopped earlier, while loading
original caller graphs, with no process/Job limit event: 5,546,819,584 peak private,
940,933,120 minimum available physical, 4,656,828,416 minimum available commit,
341.9791 seconds; whole tree reaped. Post-stop Chrome RSS was 4,687,581,184 and
Zalo RSS 1,073,434,624; the earlier v11 snapshot had Chrome RSS 1,556,688,896.
The working-set cap alone therefore cannot be presented as a total physical-memory
reservation: system compression/paging and competing load remain material.

The record loader also retained independent copies of repeated schema keys and
scalar lineage/status strings. Its native decoder now shares only immutable
strings within one reader. Keys are bounded to 4,096 entries/256 characters;
scalar strings use an 8,192-entry LRU with an 8-MiB accounted size budget and a
2,048-character token bound. Dict/list ownership, values/types, member limits and
all parsing/identity checks remain unchanged. Memos are not global intern tables
or artifact/result caches and are released with the decoder. Periodic semantic
JSONL uses the identical per-reader decoder before its unchanged KBS flow gate.

Original 2,394,768,092-byte IID comparison under identical 5-GiB diagnostic Job,
7-GiB process and 1-GiB resident bounds:

| Metric | Prior loader | Shared-string loader |
| --- | ---: | ---: |
| Peak process/Job private bytes | 3,688,693,760 | 1,807,831,040 |
| Private bytes after full graph load | 3,677,696,000 | 1,795,776,512 |
| Private bytes after full identity | 3,678,396,416 | 1,797,742,592 |
| Minimum available physical bytes | 1,999,466,496 | 2,055,274,496 |
| Minimum available commit bytes | 7,986,667,520 | 8,833,843,200 |
| Full guarded lifetime seconds | 182.8276 | 139.8402 |

Both retain all 1,683 records, reproduce canonical digest
`783d3391cf277745282c20a55d262b8e552c4e97f483e9df6eee43ad71d60d45`,
preserve the original raw SHA and finish/reap without a limit event. The private
peak reduction is 1,880,862,720 bytes (about 1.75 GiB); differing host conditions
mean the physical/commit minima and timing are not controlled host-recovery
comparisons. These are IID-loader components, not complete stage qualifications.
Exact measured candidate/prior source bytes and source fingerprints are retained
in shared-string-loader-v13. The shared decoder was subsequently extracted without
changing its memo body for reuse by semantic JSONL. 106 loader, memory, IID and
Financial V2 regression checks passed, including the real 1,492-ticker Financial
engine regression and unchanged period-alignment gate.

A single finite preparation pass trimmed working sets of 57 SID-verified same-user
GUI processes, terminating none and changing no ceilings/configuration. Available
physical bytes changed from 4,393,545,728 to 6,769,668,096 five seconds later;
commit remained independently measured. This is reversible paging preparation for
qualification, not a persistent capacity guarantee, evidence authority or READY
permit. No retry loop or Owner reboot was requested. Its exact before/after receipt
is separate from all workload measurements. The next complete experiment enforces
a stricter 5-GiB Job ceiling while preserving the 7-GiB process maximum, original
1/2-GiB reserves and all stage deadlines. Ordinary admission/receipts remain unchanged
until that workload envelope is validated.
