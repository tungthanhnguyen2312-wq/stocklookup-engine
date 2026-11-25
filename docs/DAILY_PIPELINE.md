# Stock Lookup — Canonical Daily Pipeline

Canonical Daily order (with Macro V1 corrective); code governs. Facts: [ACTIVE_STATE.md](ACTIVE_STATE.md); authority: [AUTHORITY.md](AUTHORITY.md).

Offline opt-ins (no Daily/deploy): [Capacity](capacity_recovery_phase1_contract.md) (adapter offline; reuse off); [Coherence V2](scenario_and_opportunity_cost_decision_coherence_v2_contract.md) (PR101; original order); [Action Center cases](action_center_opportunity_cost_cases_consumer_v1_contract.md) (private; phase-8 supplies none); [Long-term company economics evidence](long_term_company_economics_evidence_contract.md) (no Daily stage/consumer). Oct 8 Macro live acceptance verified (identities in ACTIVE_STATE).

Oct-7 release: K2 projects immutable annual baseline + qualified overlay. [Prior pairing](official_prior_period_pairing_daily_frozen_source_transition_v1_contract.md) loads qualified originals for new projections only; historical cards never vote. USD income stays currency-preserving (excluded from VND citations/valuation). Disposal/audited provisions follow [earnings contract](reported_earnings_component_context_contract.md) (descriptive flags, period, recurrence UNKNOWN, no normalized EPS; future runs only). CI, valuation, research, opportunity & K6 event context receive frozen/attempt binding; completed locks immutable; AI preserves citations/event identity; Dashboard manifests carry bindings. No production Daily/publish ([Offline proof](internal/CURRENT_OFFICIAL_EVIDENCE_PROJECTION_INTEGRATION_20261007.md)).

Phase C (2026-10-06) preserves order/identities: streamed IID, writable binding spine, buffered UTF-8, velocity-only T0 hash projection, bounded record hashing/pretty-write, exact native immutable bytes. Resource measurements/limits: [ACTIVE_STATE](ACTIVE_STATE.md), [closeout](internal/PHASE_C_WHOLE_PIPELINE_RESOURCE_CLOSEOUT_20261006.md). No new child boundary, GC, Daily or threshold change.

**One workflow, two front doors:** `stocklookup.ps1 daily` and Desktop one-click call `tools.run_owner_daily.run_workflow` (no concurrent writers; [OWNER_DAILY_ONE_CLICK.md](OWNER_DAILY_ONE_CLICK.md)). First-real evening target: ~16:00 Asia/Ho_Chi_Minh ([Monday contract](monday_live_readiness_closeout_contract.md)).

Legend — **Block**: stops run. **Soft**: component-local `UNAVAILABLE`/`WARN`; sealed Producer/capture/marker/T0 stay valid. **Process**: Owner parent, Daily child (`daily_analysis_pipeline.py --canonical-post-close`), or tool grandchild.

## A. Owner launcher (parent, 9 phases; FULL = `--full-publish`; default: CORE + AI)

| # | Phase | Purpose | Block/Soft | Process | Retained output | Retry / recovery |
|---|---|---|---|---|---|---|
| 1 | Repository preflight | Safe-sync Producer, Consumer (`ai-core-private`) and Dashboard checkouts: right repo/origin/`main`, clean, `pull --ff-only`, never reset/rebase/stash/clean | Block | parent | durable journal `operations-review/owner-daily-journal-v1/journal.json` | fix checkout, rerun; journal records the stage before work starts |
| 1b | **Host preflight** (`OWNER_DAILY_HOST_PREFLIGHT_V1`), inside phase 1 before Canonical Daily BEGIN; direct `_run_daily` callers remain gated | Read-only commit / physical / pagefile / disk / writer observation; qualified physical band requires strict child Job and runtime reserves ([contract](owner_daily_16gb_host_and_pipeline_memory_recovery_v1_contract.md#final-admission-corrective--october-27)) | Block (AMBER also refuses) | parent | stdout JSON only | satisfy failing dimension; no override; completed-session replay skips acquisition |
| 2 | Canonical Daily | Spawn the Daily child and wait; the child runs section B | Block | child | see B | interrupted but already-complete Daily resumes publication from the journal; otherwise rerun (retained exact-session snapshot is reused, no duplicate acquisition) |
| 3 | Daily completion verification | Verify operation record, registry `COMPLETED_RETAINED_EVIDENCE`, runtime/trusted READY | Block | parent | none | fix and rerun; or `--replay-completed-session SESSION` |
| 4 | Producer state publication | Commit only the governed session registry (`commit_daily_state`), `NO_CHANGE` when identical | Block | parent | git commit of `config/daily_research_session_input_registry.json` | idempotent; resumed step re-verifies |
| 5 | Dashboard publication | `release_orchestrator` publishes to `stocklookup-dashboard` (folder `market-dashboard`); public byte identity check | FULL only; Block | parent→tool | `dashboard-runtime`, Dashboard repo | `REUSED_EXISTING_PUBLICATION` on replay |
| 6 | AI handoff build | Build/publish the compact private AI handoff; refuses without the exact retained Brief and Integrated Decision overlay; verifies the remote | Block | parent | `stocklookup-ai-handoffs` publication | `ALREADY_PUBLISHED_VERIFIED` on replay |
| 7 | Remote verification | Display of phase 6 remote proof (exact session/SHA) | FULL only | parent | none | rerun |
| 8 | Personal Action Center | Owner view over retained artifacts | FULL only; Soft | parent | action-center artifact | rerun |
| 9 | Open owner view | Open local view | FULL only | parent | none | — |

`FINAL STATUS: PASS` means the remote AI handoff is `READY_FOR_AI`. It says nothing about T0 (see
ACTIVE_STATE §3).

## B. Canonical Daily kernel (Daily child; `canonical_daily_operation.run_canonical_daily_operation`)

| # | Stage | Purpose | Block/Soft | Process | Retained output | Authority role | Retry / recovery |
|---|---|---|---|---|---|---|---|
| K1 | **Calendar / Phase A** | One bounded DNSE `working_dates` probe (retained as a calendar receipt); attempt eligibility, session resolution, 15:30 floor | Block | child | calendar receipt (`prospective-calendar-evidence-v1`) | `SCOPED` calendar | rerun when eligible; probe skipped on retained-resume |
| K2 | **Market acquisition** (`acquire_and_materialize`) | DNSE exact-session acquisition + Level-2 current-research chain (universe resolution, liquidity, technical coverage, descriptive, screening, tactical classifier, corporate intelligence, valuation inputs, sector leadership, relative research, risk register) | Block | child + tool grandchildren | exact-session snapshot, raw market evidence (immutable), Level-2 artifacts | `SCOPED` current-session evidence | retained snapshot reused; `DUPLICATE_MARKET_ACQUISITION` guard |
| K3 | **Listing + capture binding** (inside K2) | Same-session positive listing observations; immutable capture companions/bindings/market manifest | Soft for Daily completion; mandatory for capture | child | `prospective-market-evidence-v1`, capture batches | `SCOPED` capture inputs | incomplete capture stays incomplete; never invented |
| K4 | **Phase B gate** | Exact-session completion gate must be `READY` | Block | child | gate record (identity-bound) | `SCOPED` | wait for provider publication / rerun |
| K5 | **Register + freeze** | `register_session_inputs`, `validate_and_freeze_completed_session` | Block | child | registry entry (`COMPLETED_RETAINED_EVIDENCE`) | operational | idempotent |
| K6 | **Technical + enrichment + Integrated Decision** (`build_enrichment_components`) | Financial momentum, corporate event context, historical context (market bars; **Technical V1 before 2026-10-03, V2 from it**), then the Integrated Decision; canonical streaming write, verified working-view copy, classification summary | Block for the Integrated Decision (components are individually soft; absent IID raises before Producer) | child (in-process) | `integrated_investment_decision_product.json` (≈1.3 GB on 2026-10-02) + working view | `SCOPED` research posture | rerun; `*.tmp` unlinked on failure |
| K7 | Macro refresh | Presentation + explicit Macro V1 acquisition; actual research cutoff | Soft | child | presentation + regime context | `SCOPED` | degrades to unavailable/partial |
| K8 | **Daily Producer** (`run_daily_producer`, with pre-seal Daily Integrated Brief) | Seal the immutable run + operation directories and the Brief | Block (only `DailyProducerError`/`CanonicalPostCloseError` map to blocked stages; other exceptions, e.g. `MemoryError`, fail the child) | child (in-process; heaviest memory stage) | `daily-producer-runs-v1`, `daily-research-session-operations-v1`, `run_manifest.json` | `SCOPED` Producer verdicts | sealed identity-addressed; never re-sealed |
| K9 | Runtime + trusted-subset materialization | Release runtime artifacts; verify trusted subset | Block | child | `dashboard-runtime` bundle | `SCOPED` | rerun |
| K10 | **T0 snapshot** (`retain_prospective_decision_snapshot`) | Streamed canonical hash + pretty write of every full decision record | Soft (`UNAVAILABLE` + reason) | child | `prospective-decision-retention-v1/<session>/<digest>/` | `AUTHORITATIVE` for T0 content | **one-shot per session**; same-digest rerun idempotent, conflict fails |
| K11 | **T0 seal index** (writer callback) | Compact verified index + write receipt | Soft | child | `prospective_t0_seal_index.json`, write receipt | `SCOPED` pointer | explicit `tools/recover_t0_seal_index.py` |
| K12 | **Daily boundary / first marker** (`daily_boundary`) | Verify original evidence → immutable complete-session record → write-once first marker → readiness | Soft | child | `prospective-pit-capture-v1/` | `SCOPED` capture completeness | missing marker recovered from original evidence time; records immutable |
| K13 | **Thesis T0 sidecar** | Retained-only compact T0 projection (needs a verified seal index) | Soft; `NOT_APPLICABLE` before 2026-10-03 | tool child (64 KiB result cap) | `thesis-evidence-t0-v1/<session>/<digest>/` (`COMPLETE.json` last) | `NON_VOTING` | `ALREADY_RETAINED`; incomplete dir rebuilds |
| K14 | Decision packet | Retain verified pre-seal canonical packet (new sessions) | Block (no local handler) | child | decision packet | `SCOPED` | rerun |
| K15 | **Pre-handoff prospective collection + feedback #1** | Cohort collection and first outcome-feedback child | Soft | tool children (admission → Job Object, 1,200 s total deadline) | `prospective-research-cohort-collection-v1`, `prospective-decision-outcome-feedback-v1` | `NON_VOTING` | `ALREADY_COMPLETE` reuse on identical inputs |
| K16 | Tactical reversal shadow collection | A/B observer; deferred in CORE + AI ([runbook](OWNER_DAILY_ONE_CLICK.md)) | Soft | tool child | tactical shadow store | `NON_VOTING` | idempotent store |
| K17 | **Handoff bundle** (`build_tiered_bundle`) | Write `session_handoff_bundle.json` (binds T0 status/identity, feedback status) and tier bundles | Block (no local handler) | child | handoff + tier bundles | `SCOPED` | rerun |
| K18 | **Post-handoff observers** | Signal velocity → current foreign flow (live DNSE) → flow/price divergence → **Volume & Flow V2** → **Thesis current** sidecar | Soft each | child + tool child (Thesis) | observer artifacts; `thesis-evidence-current-v1/…` | `NON_VOTING` | immutable writes; replay diagnostics never publish pointers |
| K19 | **Post-handoff outcome feedback #2** | Second feedback child (`INCREMENTAL` over #1) | Soft | tool child | `prospective-decision-outcome-feedback-post-handoff-v1` | `NON_VOTING` | `ALREADY_COMPLETE` reuse; resource/reap statuses are never evidence |
| K20 | Presentation projection + runtime restage | Re-join Workspace/Screener with the now-available axes into a **new** artifact set (never the sealed Producer dir) | Soft | child | `post-handoff-presentation-projection-v1` | `SCOPED` presentation | falls back to sealed bytes |

Heavy children (Thesis, feedback) block until reaped (no overlap) and run **after** capture, marker, T0 and seal (never revise them).

## C. Resume and replay

- Completed-session replay: `tools/run_owner_daily.py --replay-completed-session SESSION` (`tools/run_owner_daily.ps1 -ReplayCompletedSession SESSION`); publishes from retained evidence, zero analytical Daily calls, cannot rebuild T0.
- Read-only post-Daily acceptance: `python tools/run_first_real_session_acceptance.py` (Monday contract; diagnostic report only). Dry run: `--dry-run --session 2026-10-05 --cutoff … --output <scratch>`.
- Original calendar receipt registration (offline, owner-gated): `tools/register_working_dates_receipt.py`.

[Explicit Producer release sync](producer_freeze_release_sync_contract.md) preserves an admitted pending freeze before Daily preflight.
