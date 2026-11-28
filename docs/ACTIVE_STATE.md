# Stock Lookup — Active State

11-20 Daily PASS; local/unpushed [T+ retry](tplus_incremental_cost_v2_contract.md); seed before deploy; warm gate open.
[Sync](producer_freeze_release_sync_contract.md) preserves the 10-26 freeze. Fresh preflight required.

Release `a9c799397a74641a0e16c8ea84454d2dc4d0745b`: PR146; post-merge CI38512024681 5/5 PASS; Codex native96.
`git fetch origin main` / `git ls-remote origin refs/heads/main`; **local** remote-tracking refs may be stale.
## 0. Navigation
| Question | Answer lives in |
|---|---|
| What is active? | this file + [CAPABILITIES.md](CAPABILITIES.md) |
| Authority? | [AUTHORITY.md](AUTHORITY.md) + the controlling contract it cites |
| What runs Daily? | [DAILY_PIPELINE.md](DAILY_PIPELINE.md) |
| What happens next? | [ROADMAP_CURRENT.md](ROADMAP_CURRENT.md) |
| History? | [HISTORICAL_INDEX.md](HISTORICAL_INDEX.md) → legacy STATE / ROADMAP / DECISIONS / `internal/` |

**Authority by domain** (one rule, no ladder and no new authority layer; identical in `AGENTS.md`):
- *Milestone execution state* (current / queued / blocked / startable, checkpoint verification):
  `docs/ROADMAP_STATE.json`, queried with `python tools/stocklookup_roadmap.py` (AI_RULES rule 11).
- *Capability semantics and authority limits*: the controlling contract (`docs/*_contract.md`, cited in
  `AUTHORITY.md`) and the code and tests that implement it.
- *Compact current-state docs* (`ACTIVE_STATE`, `CAPABILITIES`, `AUTHORITY`, `DAILY_PIPELINE`,
  `ROADMAP_CURRENT`): maintained navigation views of the two items above. They add **no** authority; if one
  disagrees with the first two, the first two govern and the view is corrected in the same change.
- *Preserved `STATE.md` / `ROADMAP.md` / `DECISIONS.md`*: history, rationale and recorded invariants; not the
  default current-state source. A compact view never overrides a recorded invariant: surface the conflict
  and obtain an explicit owner decision.

Kinds: **CURRENT FACT** verified; **HOST-LOCAL** untracked/re-verify; **BLOCKED**, **DEFERRED**, **HISTORICAL**.

## 1. The operational gate (CURRENT FACT unless marked otherwise)
- **LOCAL / unreleased - PR #296 HAH config integration (2026-11-28):** HAH R3 FY2025, H1/2025 and H1/2026 research entries added to the [dual-reader config](../config/dual_reader_ttm_research_config.json); B remains OFF / `OWNER_PENDING_ACTIVATION`. The [capacity receipt](../config/owner_daily_capacity_qualification.json) appends HAH after the handoff gzip corrective at base `72d558ea771342e020a9afda5dd328da37fb2cb8`, preserving A selectors and all prior corrective bytes. Commit/release and hosted CI pending; no Daily launch or production change.
- **LOCAL, unreleased — Owner Decision 1 (2026-11-24), `HL-20261124-HOL-06`:** [parent-attributable headline P/E](current_state_relative_valuation_contract.md) implementation with total-profit supplementary context. Supplied November 23 retained-input replay: 5 headlines → 0 of 1,683 evaluated names; upstream annual parent panel absent locally. [Evidence and gaps](internal/PARENT_ATTRIBUTABLE_HEADLINE_PE_20261124.md).
- **LOCAL PR #284 (`HL-20261124-HOL-01`, `HL-20261124-HOL-04`, `HL-20261124-HOL-05`, `HL-20261124-HOL-09`):** retained share events require aware `known_by` (live recorded run clock/replay historical cutoff); exclude only proven-late rows. Untimed rows retain `KNOWN_AT_UNPROVEN_ADMITTED_FOR_WITHHOLDING_ONLY`; exclusion is fail-open; 2026-11-23 matches main. Owner 2026-11-24 admits supported VSDC registered counts/share-changing events market-wide; `official_source_registry.json` prototype OFF. Record-date upper bounds (BMI `tests/fixtures/vsdc_notices/bmi_202076_retained_20261124.html`) withhold only. Registration-change `corporate_action_notice` (4 fixture hashes verified, absent venue UNKNOWN) parses `ISSUED_SHARES`, literal reason, second-precision `Asia/Ho_Chi_Minh` publication; enabled `official_registered_shares` needs exact ticker/ISIN link to retained VSDC HOSE notice, known by cutoff after provider observation. [Finite retention](official_document_acquisition_pilot.md#vsdc-finite-operator-notice-scope-hl-20261124-hol-05): exact VSDC URLs beyond financial cohort, fixed registry gates/manifest; offline OFF/ON replay may BLOCK without registered-share valuation tier; downloads/full-market replay pending. [Body repair](official_document_acquisition_pilot.md#body-completeness-and-append-only-repair-hl-20261124-hol-09): reject body-less HTTP200 shells, append superseding receipts, select latest complete linked version, diagnose preserved shells; re-fetch/replay3 shells pending. No outstanding-ex-treasury/continuity/effective-date/valuation-use/PIT/price-factor/Daily/source-admission/production promotion or production evidence change.
- **LOCAL / OFFLINE - PR #287: HL-20261124-HOL-02C, HOL-02F, HOL-08, HOL-10, HOL-11** ([HOL-08](official_financial_source_qualification_integrity_corrective_v1_contract.md#hol-08-retained-baseline-digit-proof-and-offline-h1-bridge), [HOL-10](official_financial_source_qualification_integrity_corrective_v1_contract.md#hol-10-retained-metadata-and-form-aware-identity), [HOL-11](official_financial_source_qualification_integrity_corrective_v1_contract.md#hol-11-exact-year-and-dotted-date-header-provenance)).
  HOL-02C shares joined-word parent-label admission, recognizes TT43 parent labels/JV 27 and industrial interest 23/JV 24; crossed 60/61 and NCI guards persist. Annual qualification-time knowledge floor is never backdated. Retained HPG H1/2026 layout replay admits parent profit; no overlay published. HOL-02F completed offline PNJ/VRE FY2025 OCR replay with supplied dependencies: PNJ income page 10, code-row overlap resolves off-row gutter competition; VRE registered for explicit annual subset replay. Owner approval 2026-11-24 adds only 2025-H1/2025-Q3/2026-Q3 acquisition periods; no downloads.
  HOL-08 permits U+00B2 as 2 only when same-render character-box top/bottom/height match ASCII digit medians within 10% of median digit height; raw tokens/full proof retained. No other numeric or damaged-parent-label repair. Offline V2 H1 bridge replays all three operands through common cutoff admission; document metadata/issuer/period/assurance failure still withholds table-qualified values. Of 17 requested operands, table-qualified rose 5 to 8; zero HOL-08 admissions. November23/25 P/E TTM blocked for all 13 names; P/S blocked (SSI/VCB not applicable), superseded only by HOL-10's metadata/HPG P/S results below.
  HOL-10 common-owner replay admits seven income rows: HPG FY2025 10/60/61, HPG H1/2025 10, VRE H1/2025 10/60/61. Exact manifest roots, literal mixed-accent period headings, registered legal issuer names and existing assurance owner apply; unusable nonempty native text needs retained zero-candidate artifact/page-hash replay. Printed TT200/202 versus TT99/43 governs income/expense, borrowing costs and JV rows; absent form references use fiscal start. November25 HPG revenue TTM 190,643,650,555,249 VND and research P/S TTM 0.9034472205413704 use retained market cap; November23 remains blocked. Both P/E codes remain blocked: prior-H1 code60 comparative glyph boxes overlap, code61 label damaged. PNJ annual layout proof, VRE annual assurance/code60 geometry/code61 label and VRE H1/2026 parent-label letter remain blocked.
  HOL-11 retains exact positioned year identities and literal complete dotted dates (PNJ `30.6.2025`/`30.6.2024`), without repair: PNJ FY2025 header blockers clear, prior-H1 revenue/total profit become table-qualified only. Unchanged unit-above-header/physical same-row code gates reject below-year `VND` and wrapped second-baseline amounts. PNJ FY2025 revenue still has a competing comparative token, total profit superscript digits (HOL-08 supersedes numeric diagnosis), parent profit split/damaged; H1 parent label/period damaged or unavailable. No absent code 62 inferred. HPG page 10 native total profit includes `s2L`, parent ends `.752`; direct owner yields zero candidates, ending HOL-11 investigation. HOL-02F/08/11 admit/publish zero new income facts; November23/25 TTM statuses remain HOL-10's (only HPG P/S November25 research usable). No gate waiver, unit/physical-row/comparative-numeric/damaged-label change, overlay, headline selection, Daily input/launch or production change.
- [Shareholder/dilution](corporate_shareholder_economics_research_v1_contract.md): share-note scaleout LOCAL COMPLETE; OFFLINE/NON_VOTING; strict gates unchanged.
- **Non-voting prior-period research:** [pairing contract](official_prior_period_pairing_daily_frozen_source_transition_v1_contract.md) and [reviewed HPG, PNJ and FPT comparisons](internal/FABLE_FULL_SYSTEM_TRANSFORMATION_HANDOFF_20261115.md).
- **[Native releases](parallel_domain_development_control_plane_v1_contract.md):** declaration correction; explicit coupled source review.
- **RELEASED:** PR145/146 source wave; exact historical acceptance remains in [SYSTEM_MAP](SYSTEM_MAP.md). No new source authority or production admission follows.
- **RELEASED — [financial intake](official_financial_quarterly_intake_contract.md):** PR137; candidates; source admission gated.
- **RELEASED — [Wave 1 replay](SYSTEM_MAP.md#wave-1-historical-replay-relocation--2026-10-13):** PR139; `tools/replay/`: 34 modules; root 325 → 291; replay unchanged.
- **RELEASED — [unlock/transport](current_financial_valuation_input_unlock_v1_contract.md):** PR133: six H1 ratios/proxy shares; PR140: present labels (bound AI session ≥2026-10-14), no new facts/ratios.
- **COMPLETE — [root hub V3](root_hub_dependency_reduction_v3_contract.md):** PR131 merged `d11b101`.
- **COMPLETE — [E6 financial seams](e6_financial_extraction_admission_boundary_contract.md):** row/envelope/status owners.
- **COMPLETE — [E4](e4_versioned_identity_safe_infrastructure_extraction_contract.md):** frozen V1; V2 offline.
- **COMPLETE — [E2/E3](e2_e3_foundation_seams_and_dependency_untangling_contract.md):** registry/temporal seams.
- **COMPLETE — [E1 evidence move](e1_official_exchange_evidence_package_migration_contract.md):** 13 modules to `stocklookup_core/evidence/`; no shim, Daily or authority change.
- **COMPLETE — [E0](stocklookup_architecture_dependency_ratchet_and_daily_launch_guard_v1_contract.md):** PR123 `56cdc36`. [CI extension](CI_AND_DEPENDENCY_TIERS.md): G2/business/quarterly mandatory; 367 files nonblocking; release via native lanes.
- **COMPLETE — [Action Center cases](action_center_opportunity_cost_cases_consumer_v1_contract.md):** PR119, four post-merge jobs PASS (38105025004); offline/non-voting.
- **COMPLETE — [capacity Phase 1](capacity_recovery_phase1_contract.md):** PR99 merged `168e0f7`, post-merge CI 37893984528 success; zero production reclaim/activation.
- **COMPLETE — Vault V1:** PR97 merged `3f3d4fe`; offline/opt-in, 77 candidates, zero deletion authority; C retention/runtime recovery still gated. Queue empty. [Contract](vault_incremental_snapshot_contract.md); session emitter offline/opt-in.
- **Economics research:** PR96 matrix / PR117 [packet](company_economics_research_packet_consumer_v1_contract.md). Quality bridge LOCAL COMPLETE: offline/opt-in/non-voting; profit vs cash/components, denominator limits and thesis tests. No normalized EPS, strict valuation or Daily change.
- **HOST-LOCAL — October 8 Owner Daily completed; Macro live acceptance independently verified:**
  `MACRO_REGIME_20261008_LIVE_ACCEPTED`. Operation
  `daily_research_session_operation:537cda6b2e7085d1461d925c7f342cf5e870feca41abb6d5ecaccd71f7262a98`,
  Macro `current_macro_regime:e2a1a64e1a41dd50b5aa66016fa72bfff9fd7da049528d77003cba117447b541`,
  context `macro_market_regime_decision_context:f02a0ee3f7fbcfcf79c7119a9d151437cb7302c84f4a4c4a95fc0e1d4d4b70b0`,
  packet `current_research_decision_packet:c4fc0700eddfa04d281722ddb15ba0e6f10a8e15b0eaf460a48c9be1952908f0`.
  Macro authority and completed records unchanged; no further corrective or Daily here.
- **COMPLETE — opportunity cost:** `PORTFOLIO_OPPORTUNITY_COST_COMPARATIVE_RESEARCH_V1`; offline hold/add/trim/alternative/cash cases; no winner, score, size, return or successor. **Closed VNM/QNS/POW triad and QNS detail resolver:** reviewed consolidated H1/2026, fixed OCR; known October 8, excluded October 7. VNM cash 4,535,672,366,831 VND (retained, zero network, page 7/110); QNS equity 10,647,823,148,609 VND (page 7/400), its only qualified H1 fact. One authorized detail request rebound the same `www.qns.com.vn` PDF (`5a06a40f…`); no download/OCR. Other fields: damaged headers (`²0²6`, dash artefact, 2026 rows); no earnings component. POW `APPROVED_ROUTE_BLOCKED` (index 404); 5/12 HTTP requests. Loans require literal labels; strict share/valuation 0. SBV UNKNOWN. [Campaign](internal/STOCK_LOOKUP_AUTONOMOUS_CAMPAIGN_20261008.md).
- **COMPLETE — FPT FY2025 earnings-quality context:** audited cash-flow 03 Provisions 651,406,282,654 VND, known October 8; no H1/normalized-EPS/valuation use. Superscripts: `SOURCE_FAITHFUL_NORMALIZATION_NOT_YET_PROVABLE`. Qualified H1 provisions: PNJ 2,667,248,523,366 VND; VRE −7,066 million VND; VRE cash/equity/OCF retained. Total assets need literal labels. PR87 `2b6208a`, PR88 `559ff7a`; NVL assurance PR86. PNJ FY2025 OCF, PVD assets/equity and auditor-backed English FPT revenue/equity qualified; annual overlay10. FPT Q2 assurance absent; PNJ H1/PVD cash-flow numeric ambiguity blocked. Annual baseline94, current official fields9, strict share/valuation0. [Campaign](internal/STOCK_LOOKUP_AUTONOMOUS_CAMPAIGN_20261008.md).

- **HPG common-share observation:** audited FY2025 page 41 states 7,675,465,855 at December 31, 2025; later-known historical context only. July-2 quantity is listed shares. January 1–October 7 common-share continuity remains unproven; strict shares/valuation stay zero. [Campaign](internal/STOCK_LOOKUP_AUTONOMOUS_CAMPAIGN_20261008.md).
- **retained projection:** Owner-selected `CURRENT_OFFICIAL_EVIDENCE_PROJECTION_INTEGRATION_V1`, PR76: eight reviewed H1 income fields PNJ/VRE/PVD, one VRE disposal component; three PVD USD fields excluded from VND canonical citations/valuation. PNJ parent profit source-qualified; VRE possible non-recurring component, recurrence UNKNOWN, no normalized EPS. Two HPG FY2025 fields are after-close historical context; completed cutoff/annual metrics/shares/valuation eligibility fixed. Bounded evidence campaign delegated, `queued_next=[]`. [Results/blockers](internal/STOCK_LOOKUP_AUTONOMOUS_CAMPAIGN_20261007.md).
- **HOST-LOCAL - October7 Daily:** read-only journal: session2026-10-07, run `30e060d6e0f74ccb826e6f4bf5adba1e`, `COMPLETE`, no failure; before Phase2. Campaign ran no Daily, accessed no T0 body, changed no genuine session/seal/Dashboard output.
- **October7 operational override:** `OWNER_DAILY_PHASE2_TRUTHFUL_PROGRESS_AND_TERMINAL_CLEANUP_V2`, not native milestone; thirteen checkpoints/Vietnamese progress, no analytical authority/Daily/rebuild/successor. [Acceptance](internal/owner_daily_progress_post_merge_acceptance.md#phase-2-v2-corrective--2026-10-07).
- **`DECISION_INTELLIGENCE_COVERAGE_AND_CALIBRATION_CLOSURE_V1`:** joins 1,683-name index, historical panel, outcome review, v2 packet/workbench. Effect `NONE / DECISION_INTELLIGENCE_RESEARCH_COVERAGE_AND_CALIBRATION_ONLY`; deferred optional CLI, admitted offline inspection. No October7 Daily/new T0 in closure job; later completion above. [Closure](internal/DECISION_INTELLIGENCE_COVERAGE_AND_CALIBRATION_CLOSURE_20261007.md).
- **`PORTFOLIO_RESEARCH_DECISION_WORKBENCH_FOUNDATION_V1`:** opportunity counts (not owner exposure), overlap/shared-date correlations; [opportunity-cost cases](portfolio_opportunity_cost_research_contract.md), four independent lenses, no allocation/size/leverage/order. [Workbench](internal/PORTFOLIO_RESEARCH_DECISION_WORKBENCH_FOUNDATION_20261006.md).
- **`HUMAN_AI_DECISION_EVIDENCE_PACKET_CONVERGENCE_V2`:** sectioned pointer to existing packet identity, named measurements, no buy score/numerical AI authority/CLI; human capital decision. [Contract](internal/HUMAN_AI_DECISION_EVIDENCE_PACKET_CONVERGENCE_V2_20261006.md).
- **`DECISION_OUTCOME_CALIBRATION_AND_FALSE_NEGATIVE_REVIEW_V1`:** retained forward feedback, separate populations/unchanged thresholds, no authority effect. October6 streamed recount T5/T10/T20 mature rows9,590/5,823/16 versus prior10,338/6,544/16 (different status filters/session membership); October5/6 are not decision sessions in artifact. [Recount](internal/DECISION_OUTCOME_CALIBRATION_AND_FALSE_NEGATIVE_REVIEW_20261006.md).
- **`HISTORICAL_TEMPORAL_RESEARCH_PANEL_FOUNDATION_V1`:** retained post-close handoff/opportunity bundles to research memory; read-only host index28 session dirs, 2,445 reconstructed rows/26 sessions/PIT0; no NVL/PNJ cohort evidence in slice. Unpersisted, no PIT backtest authority. [Slice/contract](internal/HISTORICAL_TEMPORAL_RESEARCH_PANEL_FOUNDATION_20261006.md).
- **`CURRENT_RESEARCH_FUNDAMENTAL_CI_VALUATION_FRESHNESS_CONVERGENCE_V1`:** denominator diagnostics, earnings-quality flag/event binding on existing valuation/packet path; provider multiples unchanged, no authority effect. October6 artifact:13 official-qualified financial inputs,5 research-usable P/E rows,0 price-and-qualified-shares-ready records; denominator1,507. [Counts/contract](internal/CURRENT_RESEARCH_FUNDAMENTAL_CI_VALUATION_FRESHNESS_20261006.md).
- **October6 Phase C release:** Owner-authorized `POST_FIRST_REAL_DAILY_PHASE_C_RESOURCE_ARCHITECTURE_RELEASE_V1`, candidate `3231616022213aac7f8c75e164c1f403566ee12c`, `POST_FIRST_REAL_DAILY_PHASE_C_WHOLE_PIPELINE_RESOURCE_ARCHITECTURE_CLOSEOUT_V2`, `RESIDUAL_PEAK_CORRECTIVE_READY`. Record-streamed T0 observer removes residual overread; held-live Canonical4.03 GiB private, separate Owner completion/handoff5.51 GiB, both below unchanged7-GiB Job ceiling. Retained-only qualification, no production Daily/launch authorization/authority effect; marker/T0/seals/captures unchanged, depth2 `DEPTH_PENDING`, `queued_next=[]`. Diagnostic scratch left disk AMBER; fresh READY preflight mandatory. [Parity/model/limits](internal/PHASE_C_WHOLE_PIPELINE_RESOURCE_CLOSEOUT_20261006.md).
- **`FIRST_REAL_POST_RELEASE_CAPTURE_ACCEPTANCE=RECORDED`, October5:** read-only harness cutoff `2026-10-05T16:00:00Z`, untracked `operations-review/first-real-session-acceptance-v1/2026-10-05/`: `capture_session` OPEN (`prospective_capture_complete_session:661a12b7fd0bbbde2a747e660b88f7b1eb33b57ad6d96fc3db4ddef844327d5d`,658 complete tickers), `first_marker` OPEN, `t0_snapshot_availability` OPEN (`prospective_decision_snapshot:1c496e3f7a2df9770e269ef20821805ef0cb8c76d34ebb2869d72fbb61e319f9`). `complete_session_count`0 to1, `DEPTH_PENDING`; `representation_tier` OPEN (853 `SOURCE_NATIVE_SCALE_CONSISTENT`); `positive_listing` STILL_BLOCKED (HOSE364/UPCOM294/UNKNOWN195); `official_verification`/`raw_as_traded`/`ca` STILL_BLOCKED, not gate failures. [Monday](monday_live_readiness_closeout_contract.md), [capture contract](prospective_pit_capture_completeness_contract.md).
- **October5 Daily complete:** journal `COMPLETE`, run `e244385f2a7441d697679d08826c88f9`, failure null, Producer `317118c788bdd46bd6de55dbff3888b92de1172d`. October2 T0 failed `MemoryError`, permanently `UNAVAILABLE`, retained0-byte file never rebuilt. Recorded `ROADMAP_STATE.json`: `current=POST_FIRST_REAL_DAILY_PHASE_C_RESOURCE_ARCHITECTURE_RELEASE_V1 / COMPLETE`, `queued_next=[]`, `successor_disposition=PHASE_C_RELEASED_NO_AUTOMATIC_SUCCESSOR`.
- **October13 source-only program:** native receipts/exact-head CI for admitted lanes/merges; specific Owner approval for source/runtime activation, sealed-session edits or authority promotion.

### Launch conditions (all must hold immediately before the live Daily)

1. Fresh `OWNER_DAILY_HOST_PREFLIGHT_V1` READY (0) required; AMBER (2)/BLOCKED (3) refuse, no override. Owner phase1 rechecks before Canonical BEGIN. Canonical main: `python -B tools/check_owner_daily_host_preflight.py`. Bands: [owner_daily_host_preflight_contract.md](owner_daily_host_preflight_contract.md).
2. Producer, Consumer (`ai-core-private`) and Dashboard (`market-dashboard`) folders (GitHub `stocklookup-engine`/`-ai-research`/`-dashboard` since 2026-10-24, [identity](../release_checkout_identity.py)) pass the Owner
   repository preflight (`tools/run_owner_daily.py`): right repo/origin, on `main`, clean, fast-forwardable.
   Untracked-path allowances are **per checkout** and defined by `acquisition/checkout_cleanliness_contract.py` as applied
   there: the Consumer allows only `.worktrees/` (`CONSUMER_APPROVED_UNTRACKED_PREFIXES`); Producer and
   Dashboard checks use the default `APPROVED_RUNTIME_EVIDENCE_PREFIXES` (specific `data/<store>/` evidence
   subdirectories, not all of `data/`). Tracked changes block, except additive pre-Producer registry freezes (`PENDING_INPUT_FREEZE_AT_ORIGIN_MAIN`,
   not completion; several may pend; only a sealed row is committed). Any other tracked or untracked file blocks.
3. No other Daily/Producer writer is running; launch the Daily alone, with ordinary browsers/IDEs/
   unrelated Python workloads closed.
4. Evidence/runtime/session/window gates pass independently of host READY.
5. Existing local DNSE credential injection required (`DNSE_CREDENTIAL_INJECTION_REQUIRED` otherwise); never print/commit credentials.

## 2. Monday-critical releases

| Item | State | Contract / evidence |
|---|---|---|
| Feedback resource containment | **COMPLETE** (PR #58). Streaming proof/projection, 1,200 s total deadline, Windows Job Object, whole-tree reap accounting, single-winner COMPLETE-last publication, `FEEDBACK_CALL_RELATION = INCREMENTAL`. Fail-soft; never gates capture/marker/T0. | [owner_daily_feedback_resource_containment_contract.md](owner_daily_feedback_resource_containment_contract.md) |
| Host preflight | **COMPLETE** PR59; Owner launcher; read-only observation, not a lease. | [owner_daily_host_preflight_contract.md](owner_daily_host_preflight_contract.md) |
| First-real capture final guardrails | **COMPLETE** (PR #60). Commit bands tightened to READY ≥12.0 / AMBER 9.2–12.0 / BLOCKED <9.2 GiB; acceptance now exposes `t0_snapshot_availability` and never reports T0 leakage as vacuously OPEN. | `first_real_session_acceptance.py`, Monday contract |
| Thesis Stage 2 | **COMPLETE**; Monday hook `thesis_production_runtime.AUTOMATIC_HOOK_ENABLED = True`; fail-soft/non-voting. | [thesis_evidence_stage_2_production_contract.md](thesis_evidence_stage_2_production_contract.md) |
| Technical V2 + Volume & Flow V2 | **COMPLETE**; V2 from **2026-10-03**, first production session **2026-10-05**; October2 `REPLAY_DIAGNOSTIC / NON_AUTHORITATIVE`; V1 frozen. | [contextual_technical_features_v2_contract.md](contextual_technical_features_v2_contract.md), [volume_and_flow_context_v2_contract.md](volume_and_flow_context_v2_contract.md) |
| Prospective capture completeness | **COMPLETE (code)**; first real session pending. | capture contract above |
| Provider runtime | Vnstock/VNAI/KBS/VCI runtime **retired**; DNSE/Livespeed is the provider direction; EODHD rejected. | `ROADMAP_STATE.json` blocked_capabilities, AI_RULES rule 8 |

## 3. First-session capture, marker and T0

- **the write-once first marker is published for 2026-10-05.** Identity
  `first_complete_capture_session:48a52e9458f361aa50bbaf5297ab98d5ccb9d5d6f76a1522cb8290bc7c7028c3`,
  bound capture `prospective_capture_complete_session:661a12b7fd0bbbde2a747e660b88f7b1eb33b57ad6d96fc3db4ddef844327d5d`,
  `written_at` `2026-10-05T11:31:02.861384+00:00`. Exactly one original T0 directory:
  `operations-review/prospective-decision-retention-v1/2026-10-05/1c496e3f7a2df9770e269ef20821805ef0cb8c76d34ebb2869d72fbb61e319f9/`.
  Do not replace the marker, the capture record, the seal index, the write receipt, or that T0.
- **marker: `CAPTURE_COMPLETENESS_ONLY`.** `first_complete_capture_session`
  is write-once; T0 optional. Preconditions: Phase-B `READY`,
  supported calendar, exact market/listing/binding batches, ≥1 capture-complete ticker. `t0_snapshot_identity=None` is accepted; a later non-`None` T0 that
  differs from the recorded value raises `RECOVERY_T0_BINDING_MISMATCH` (expected immutability).
- **T0 availability is independent.** The T0 snapshot (`prospective_decision_retention`)
  is streamed, content-addressed and fail-soft: a failure becomes `UNAVAILABLE` and the Daily
  continues. T0 is **one-shot per session** — no later rebuild. The seal index
  (`prospective_t0_seal_index/v1`) is derived from the snapshot and also fail-soft.
- **Reporting rule for Monday:** report capture, marker and T0 as three separate lines. "Capture yes,
  marker yes, T0 unavailable" is a legal outcome; it must never be labelled T0/PIT-ready. Rows that
  stay blocked/unknown without T0: `t0_snapshot_availability`, `exact_t0_v2_seal_index`,
  `t0_native_volume`, `post_to_t0_leakage` (NOT_EVALUABLE), all `thesis_t0_*` rows. Separately, first capture
  alone does not open `pit_continuous_price`, `raw_as_traded` or `ca` (evidence-blocked today; their opening
  predicates are conjunctions over qualified evidence). `official_verification` is conditional and
  use-dependent: it opens only when exact retained official ledgers/bodies have been verified later and every
  current name is `VERIFIED_MATCH`; the contract keeps that verification a separate later step, so it is not
  expected from the first-real run. Read T0 in acceptance/journal `t0_snapshot` attestation; terminal screen omits it.
- **Streaming T0 write at real scale** (scratch benchmark, `PERFORMANCE_ONLY_NON_AUTHORITATIVE`,
  2026-10-04): 1,683 records, 1.30 GiB output, +~6 MB working set over a 1.93 GiB resident decision
  graph, ≈326 s for build + write + seal index.

## 4. HOST-LOCAL (verified 2026-10-04; untracked, re-verify)

- **Calendar registered locally:** October-2 DNSE `working_dates`, 257 dates (2026-10-02 to 2027-10-01), raw SHA-256 `fce46fe3...33d6d`; one offline `tools/register_working_dates_receipt.py` registration, `network_requests=0`, `historical_extension=false`, `authority_effect=NONE`. Registration `governed_calendar_registration:5cceff48f1f72934b856cc2cede8f959a276ce9f39f431057f0d27a2baf54941`; receipt `dnse_working_dates_calendar_receipt:c324eb2a9825b965db63eabf5dd4fd213290351fb9f7b91442cf56ab10143ca3`, git-ignored `operations-review/prospective-calendar-evidence-v1/`. Receipt alone proves 2026-10-02 to 2026-10-05 continuity `TRUE`; before knowledge time `2026-10-02T03:40:02Z`, `UNKNOWN`. September5-October1 remains `UNSUPPORTED_CALENDAR_GAP`; no capture/T0/foreign maturity/backfill. Re-verify read-only from production checkout: `python -c "import prospective_pit_capture_retention as s,governed_session_chain as g;from pathlib import Path;c=s.calendar_evidence_at_cutoff(Path('.'),cutoff='2026-10-05T12:10:00Z');print(g.are_consecutive_governed_sessions('2026-10-02','2026-10-05','2026-10-05T12:10:00Z',c)['state'])"`. Monday Daily retains its own probe; registration affects continuity, not first capture/marker.
- Rehearsal scratch 15.24 GiB deleted; C: free 35.61 GiB. Other `Temp\claude\*`/`Temp\codex-*` UNCERTAIN, untouched. October4 preflight: `BLOCKED`, commit9.11 GiB (<9.2), physical3.22 GiB AMBER, disk35.61 GiB READY, no writers. Observation only: fresh READY required; close browsers/IDEs, never alter thresholds or kill processes from tool.
- October5 16:08/16:35 launches refused: commit1.74/physical1.02/disk17.29 GiB. Agent's orphan Git-Bash `find / -name ...` (05:46) held ~12.6M handles/~8 GB kernel paged pool and delete-pending files; after stop: commit6.51 BLOCKED/physical2.27 BLOCKED/disk27.1 READY. Remaining load ordinary apps; thresholds unchanged. Agents must never run root-wide `find /` or unbounded scans.
- October5 18:00, run `ad670e74...`, main `f2721f4`: READY, Canonical exit1, `build_tiered_bundle` raised `AttributeError: 'str' object has no attribute 'resolve'`. First session at/after `PRODUCTION_V2_START_SESSION`: serialized seal `{"path": str}` reached Path-only `_rel`. Read-only verified original T0 `prospective_decision_snapshot:1c496e3f...` (seal/receipt/hash), capture/first marker/Thesis T0 already sealed. No tier bundle/operation/journal completion/state commit/publication; local `dashboard-runtime` promoted18:26. `fix/owner-daily-20261005-recovery-v1`: `_rel` accepts `Path | str`, reuses verified original V2 T0 (HEAD-bound operation identity otherwise conflicts after merge). Telemetry-silent enrichment/Producer/T0 child peak ~10 GB; attribution separate milestone.
- October5 19:56, main `c7362dd`: `LOCAL_COMPLETE`, operation `daily_research_session_operation:140adc8a...`, original T0 reused; Producer/Dashboard published, then `AI_HANDOFF_REQUIRED_FILE_MISSING`. First attempt's post-cutoff `...-20261005` context hid eligible `29f3a1bc...` (`...-20261002`); completed lock has no `event_context`/queue, handoff required queue unconditionally. `fix/owner-daily-final-recovery-20261005`: newest context known by unchanged15:00 cutoff; require identity-checked queue only if sealed operation declares it, otherwise `NOT_DECLARED_BY_SEALED_OPERATION`. Lock preserved.
- October5 completion resumed on `317118c`: **PASS**, no Canonical rerun. Dashboard `origin/main` `5a050b46b2092e2d5bac2c0af216624447800c83`, session2026-10-05; `governed_publication_attestation:6daf0b708354b0384286a5c331c1765011602e446ffcd1ecd2322b3570955808`; CI37335772813/Deploy Pages37335959559 success, public-byte identity PASS. AI `origin/main` `9f379cc2b6f1655806ed42d63161c17479e79951`, `READY_FOR_AI`, queue `NOT_DECLARED_BY_SEALED_OPERATION`; `personal_investment_decision_action_center/v1:37ec23f5d430ce11b89520f171d8c4d8d0011c26b2b0feb59752e0efa435514a`. First real child peak_rss_bytes10985897984 (~10.23 GiB), above6.5-8.0 band; publication-only resumes6840815616/2057273344 skipped Canonical. Merged PR64 `c316458` companion run binding, PR65 `cc8f548` hermetic fixture/dashboard failure reason, PR66 `317118c` `gh run watch` conclusion; Producer CI37335518993 success. Volume/flow and Thesis T0 sidecar `UNAVAILABLE`: frozen lock lacks event context, reused T0 IID differs from later IID; fail-soft. Lock/T0 unchanged.

## 5. BLOCKED (evidence-blocked; do not work around)

- [CA](official_ssi_pow_corporate_action_evidence_qualification_v1_contract.md): SSI/POW facts qualified offline; mixed factors/PIT blocked.
  HPG/PVD unchanged, known from Oct25 receipts only. Historical raw PARTIAL; prospective raw needs HOSE parity.
- `ACTIVE_UNIVERSE` authority: `UNKNOWN` for all instruments (no official listing-status proof from DNSE).
- Reverse / intrinsic valuation outputs: no governed intrinsic evaluator output or FCFF inputs.
- Execution-grade liquidity, canonical participation/horizon policy, position sizing authority.
- Continuous-price and standing-signal PIT readiness. Official verification of prospective RAW is conditional
  on later exact retained official ledgers (a separate step), not blocked by design.
- Foreign-flow 10/20-session maturity and Friday-governed continuity beyond the registered receipt.

## 6. HISTORICAL (not current)

- Historical STATE calendar-registration gate is superseded by §4 (host-local 2026-10-04).
- The 9,853,145,088-byte (~9.18 GiB) peak is STALE: whole-string T0 write removed.
  Band stays **6.5–8.0 GiB; 8.0 is a floor**, first real child `10985897984` bytes (§4).
  Do not lower host thresholds.
- October 4's first marker is null / 0 captures were superseded October 5 (§3); October 2 T0 stays UNAVAILABLE.
  October 4's no-live-Daily-since-October-2 statement is superseded by §1.
- OWNER_DAILY_ONE_CLICK's ~16:30 is historical: Monday contract targets ~16:00,
  attempt floor15:30; use that contract for October 5.

- M1 live acceptance (2026-09-28, `DNSE_PRIMARY_UNCORROBORATED`), Thesis Stage 1 (offline, frozen),
  the R1–R7 program closeouts, Vnstock operation and every dated section of the giant narrative files.

## 7. DEFERRED

- Further control-plane/runtime work is **not authorized, not started**. Phase B's bounded source improvements
  are admitted in the current closeout; historical files stay preserved and Phase C's release scope is unchanged.
- R7 authority promotion (`AUTHORITY_PROMOTION_PENDING_EVIDENCE_OR_OWNER_APPROVAL`).
- Any later analytical milestone, new provider, new authority, or calibration use of learning outputs.
- Worktree/scratch cleanup beyond the Owner-approved 2026-10-24 retirement.

## 8. Blockers

1. Daily 20/11 complete; retry T+ conflict fixed locally. Needs Owner merge, seed, genuine warm session.
   HPG/PAN Q3 stays non-voting; [official intake gaps](internal/Q3_FINANCIAL_EVIDENCE_RECOVERY_20261118.md) remain.
2. Launch only with fresh `OWNER_DAILY_HOST_PREFLIGHT_V1` = **READY**. **AMBER or BLOCKED must not launch.**

## 9. Next action

Future Daily handoffs may attach retained structured financial context as post-session research; missing files are fail-soft. Official admission/PIT/valuation stay closed.

## 10. Open Owner approvals

- Work outside the source-only program; admitted in-scope merges are delegated with native receipts/exact-head CI. Source/runtime approvals stay separate.
- Further host scratch / `Temp\*` / worktree cleanup beyond the 2026-10-24 approval.
- R7 / RAW / PIT / execution authority promotion; any new provider; any threshold change to the host preflight.

Historical entries removed during the 2026-11-25 compaction are kept verbatim in [`docs/internal/ACTIVE_STATE_HISTORY_20261125.md`](internal/ACTIVE_STATE_HISTORY_20261125.md).
