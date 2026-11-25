# Stock Lookup — Current Roadmap

History: [ROADMAP.md](ROADMAP.md); execution: ROADMAP_STATE.json.
Verified analytical baseline 2026-10-14 `a9c799397a74641a0e16c8ea84454d2dc4d0745b`.
Nothing below auto-starts; native standing admission required (AI_RULES 11).
Facts: [ACTIVE_STATE.md](ACTIVE_STATE.md).

## NOW — TPLUS_INCREMENTAL_COST_V2 (ACTIVE)

[Scope](tplus_incremental_cost_v2_contract.md). PR267/258 released; 11-18 bootstrap
completed in 1,561.522 s. 11-21 local retry fix: re-enactment 188/224 s; ACTIVE.
[Health/Q3 evidence](internal/Q3_FINANCIAL_EVIDENCE_RECOVERY_20261118.md).

## PRIOR — [16-GiB recovery](owner_daily_16gb_host_and_pipeline_memory_recovery_v1_contract.md) COMPLETE `f4347143`

## PRIOR — STOCKLOOKUP_PRODUCER_DEEP_SIMPLIFICATION (RELEASED PR146)

[Scope](parallel_domain_development_control_plane_v1_contract.md): disjoint native lanes
and Owner merge gate. E0–E5, V2/V3 and the source waves are released. See
[History](HISTORICAL_INDEX.md) for exact source-wave checkpoints and CI receipts.
Fiscal mapping lacks issuer calendar/covered-period/provider-label/publication proof;
existing semantics knowledge time is insufficient. No automatic conversion/promotion.
Capacity Phase 1 COMPLETE: PR99 `168e0f7`, CI 37893984528 success;
zero production reclaim/activation. [Contract](capacity_recovery_phase1_contract.md).

Vault V1 COMPLETE (PR97): offline snapshot/SQLite, 77 candidates, zero deletion authority;
C capacity and production/retention approvals gated. [Contract](vault_incremental_snapshot_contract.md).

Economics V1 COMPLETE: PR96; [offline limits](long_term_company_economics_evidence_contract.md).

## PRIOR — `MACRO_REGIME_CANONICAL_DAILY_CONSUMER_AND_TEMPORAL_CORRECTIVE_V1` (COMPLETE)

Macro Daily/AI/cockpit and October 8 live acceptance are recorded in ACTIVE_STATE.
No successor; SBV UNKNOWN. [Contract](macro_market_regime_decision_context_contract.md).

## PRIOR — retained financial evidence checkpoints (COMPLETE)

Qualification/blockers: ACTIVE_STATE and [campaign record](internal/STOCK_LOOKUP_AUTONOMOUS_CAMPAIGN_20261008.md) ([prior checkpoint](long_term_company_economics_evidence_contract.md#retained-prior-checkpoint-detail)). Strict shares/valuation zero; completed sessions immutable; campaign authorizes no Daily (Oct 8 Owner completion separate).

`FIRST_REAL_POST_RELEASE_CAPTURE_ACCEPTANCE` stays RECORDED for Oct 5 (not reopened). Non-voting research foundations (decision-intelligence closure, portfolio workbench, evidence packet V2, outcome review, historical panel, freshness) are in ACTIVE_STATE; none starts a successor or supplies capital decisions. Forex idea bank is not a roadmap entry.

**2026-10-06 Phase C:** `3231616022213aac7f8c75e164c1f403566ee12c`, `RESIDUAL_PEAK_CORRECTIVE_READY`. Heavy path 4.03 GiB private; Owner completion/handoff 5.51 GiB (< 7-GiB guard), exact parity, no authority effect. Disk READY required; Depth2 `DEPTH_PENDING`. [Whole model](internal/PHASE_C_WHOLE_PIPELINE_RESOURCE_CLOSEOUT_20261006.md); [V1 proof](internal/POST_FIRST_REAL_DAILY_PHASE_C_RESOURCE_SIMPLIFICATION_20261006.md). Oct 5 identities & 10.23-GiB peak in ACTIVE_STATE; `official_verification` conditional, RAW/CA closed, journal COMPLETE.

Next ordinary Daily = next completed session after fresh READY preflight (not a milestone; `queued_next` empty).

## NEXT EVIDENCE GATE — time-driven, not milestones

Advance via real sessions only:
- First live DNSE VN-Index capture + Market Close publication after 2026-11-09 close (fresh READY preflight; [Active State](ACTIVE_STATE.md)).
- Contiguous capture depth at 20 / 21 / 50 / 60 / 120 / 250 sessions (`READY_FOR_BOUNDED_EVALUATION` invites governed review, never authorizes).
- Outcome maturity: T+20 / T+60; foreign-flow 10 / 20-session cohorts.
- Calendar: `CALENDAR_REFRESH_NEEDED` when forward coverage < 60-session max outcome horizon (no invented schedule).
- Later official verification of prospective RAW from exact retained ledgers.

## AFTER FIRST-REAL ACCEPTANCE — candidates, bounded admission required

1. **Record first-real result** — done in control plane (docs only; Phase C released above).
2. **Control-plane simplification Phase B** (admitted in Codex source closeout): cut obsolete bootstrap context/duplicate audits; explicit coordinator/lane handoffs. Preserve historical files, markers, parser output/error shape and native roadmap contracts; measure reading footprint.
3. **Simplification Phase C** (released): allocation causes and immutable session sizes remain in acceptance, [host preflight](owner_daily_host_preflight_contract.md) and [feedback containment](owner_daily_feedback_resource_containment_contract.md) contracts. Further runtime work needs measured justification; historical instruction attribution unavailable.

## LATER — blocked on evidence or an owner decision

- Corporate-action factor qualification → PIT-adjusted history, PIT backtest, execution replay.
- R7 / RAW / PIT / execution authority promotion (`AUTHORITY_PROMOTION_PENDING_EVIDENCE_OR_OWNER_APPROVAL`).
- Intrinsic / reverse valuation (needs governed FCFF/WACC/terminal inputs); official financial statement currency refresh.
- Execution-grade liquidity and canonical participation/horizon policy; capital/risk-budget bindings.
- Any new market-data provider (requires a new owner decision; EODHD rejected; Vnstock retired).
- Calibration use of prospective learning outputs (sample-limited; human review only).
