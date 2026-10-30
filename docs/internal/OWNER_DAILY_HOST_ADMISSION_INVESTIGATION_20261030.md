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
