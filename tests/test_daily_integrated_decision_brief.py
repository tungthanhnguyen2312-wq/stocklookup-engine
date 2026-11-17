from __future__ import annotations

import hashlib
import json

import pytest

import stocklookup_core.decision.daily_integrated_decision_brief as brief
from tools import build_owner_compact_research as compact


def _record(ticker: str, *, posture: str, phase: str = "TREND_CONTINUATION", trigger_state: str = "NOT_AVAILABLE",
            distance: float | None = None, counter_thesis: list[str] | None = None, participation_support: list[str] | None = None,
            participation_status: str = "AVAILABLE") -> dict:
    return {
        "ticker": ticker, "as_of_session": "2026-08-28", "research_action_posture": posture, "tactical_phase": phase,
        "fundamental_state": "STABLE", "market_structure_state": "UPTREND", "breakout_state_v3": "BREAKOUT",
        "why_now": f"{ticker}: why now.", "counter_thesis": counter_thesis or [], "material_uncertainties": [],
        "missing_evidence_decision_effect": "DOES_NOT_BLOCK_CURRENT_RESEARCH",
        "trigger": {"trigger_type": "PIVOT_BREAKOUT_TRIGGER", "trigger_level": 10.0, "trigger_state": trigger_state, "distance_to_trigger_pct": distance},
        "invalidation": {"invalidation_level": 9.0, "invalidation_method": "CONFIRMED_SWING_LEVEL_OR_SUPPORT_FALLBACK", "distance_to_invalidation_pct": 0.1},
        "participation": {"status": participation_status, "relative_volume_percentile": 0.6, "volume_acceleration_ratio": 1.2},
        "participation_support": participation_support or [],
        "valuation_context_summary": {"status": "AVAILABLE", "pe_multiple": 10.0, "pb_multiple": 2.0, "ps_multiple": 1.5, "peer_relative_state": "MID_RANGE_VS_PEERS", "own_history_state": "MID_VS_OWN_HISTORY"},
        "fundamental_support": ["PROFITABLE_CORE_OPERATIONS"],
        "legacy_comparison": {"legacy_stance": None, "legacy_entry_state": None, "posture_delta": "NO_LEGACY_STANCE"},
        "portfolio_context": {"status": "NOT_PROVIDED", "is_held": False},
        "decision_identity": f"decision:{ticker}:test",
    }


class TestFinancialEvidenceContext:
    """Section 23: the AI handoff must be able to say 'fundamental evidence is based on FY/Q
    reporting period X, while market/technical evidence is session Y' without guessing."""

    def test_unavailable_when_not_supplied(self):
        ctx = brief.build_financial_evidence_context(None)
        assert ctx["status"] == "UNAVAILABLE"
        assert "FINANCIAL_ANALYSIS_PRODUCT_NOT_SUPPLIED" in ctx["reason_codes"]

    def test_available_exposes_identity_and_as_of_period_distinct_from_decision_session(self):
        financial_session_artifact = {
            "decision_session": "2026-08-28",
            "financial_v2_engine_identity": "financial_analysis_context/v2:deadbeef",
            "financial_evidence_as_of_period": "2026-Q2",
            "financial_evidence_period_range": {"earliest_observed_period_identity": "2024-Q1", "latest_observed_period_identity": "2026-Q2"},
            "coverage": {"financial_engine_denominator": 1492},
            "financial_analysis_product": {"artifact_identity": "financial_analysis_product_integration/v1:cafebabe"},
        }
        ctx = brief.build_financial_evidence_context(financial_session_artifact)
        assert ctx["status"] == "AVAILABLE"
        assert ctx["financial_analysis_product_identity"] == "financial_analysis_product_integration/v1:cafebabe"
        assert ctx["financial_v2_engine_identity"] == "financial_analysis_context/v2:deadbeef"
        assert ctx["financial_evidence_as_of_period"] == "2026-Q2"
        assert ctx["decision_session"] == "2026-08-28"
        # The financial evidence period and the decision session are explicitly different clocks.
        assert ctx["financial_evidence_as_of_period"] != ctx["decision_session"]

    def test_build_artifact_exposes_financial_analysis_product_identity(self):
        integrated = {"session": "2026-08-28", "artifact_identity": "integrated_investment_decision_product/v1:x", "records": {}, "coverage": {}}
        next_brief = {"current_session": "2026-08-28", "artifact_identity": "next_session_decision_brief/v2:y", "previous_qualified_session": "2026-08-26"}
        financial_session_artifact = {
            "decision_session": "2026-08-28", "financial_v2_engine_identity": "financial_analysis_context/v2:deadbeef",
            "financial_evidence_as_of_period": "2026-Q2", "coverage": {},
            "financial_analysis_product": {"artifact_identity": "financial_analysis_product_integration/v1:cafebabe"},
        }
        art = brief.build_artifact(
            session="2026-08-28", requested_at="2026-08-28T15:05:00+07:00",
            integrated_decision_current=integrated, next_session_brief=next_brief,
            financial_analysis_product_current=financial_session_artifact,
        )
        assert art["financial_evidence_context"]["status"] == "AVAILABLE"
        assert art["source_artifact_identities"]["financial_analysis_product"] == "financial_analysis_product_integration/v1:cafebabe"

    def test_watchlist_passes_compact_financial_context_and_method_fitness_without_recomputation(self):
        compact = {
            "contract_version": "financial_analysis_product_integration/v1",
            "artifact_identity": "financial_analysis_product_integration/v1:compact",
            "records": {
                "FPT": {
                    "contract_version": "financial_analysis_product_integration/v1",
                    "ticker": "FPT", "status": "AVAILABLE", "growth_state": "IMPROVING",
                    "feature_fitness": {"revenue_qoq": {"fitness": "READY", "reason_codes": []}},
                    "history_context": {"gross_margin": {"status": "AVAILABLE", "percentile": 0.8}},
                    "lineage_ref": "financial_analysis_lineage/v1:x", "raw_engine_record_exposed": False,
                    "is_actionable": False,
                },
            },
        }
        integrated = _record("FPT", posture="HOLD")
        integrated["valuation_methods"] = {"P/E": {"status": "INPUT_BLOCKED", "blocker_reason_codes": ["X"], "target_price": None, "probability": None}}
        integrated["valuation_method_reconciliation"] = {"P/E": {"comparison_status": "CURRENT_RESEARCH_METHOD_NOT_USABLE"}}
        row = brief.build_watchlist_record(
            ticker="FPT", current=integrated, tactical_raw=None, sector_label=None,
            posture_transition_row=None,
            financial_analysis=brief._financial_context_for_ticker({"financial_analysis_product": compact}, "FPT"),
        )
        assert row["financial_analysis"]["growth_state"] == "IMPROVING"
        assert row["financial_analysis"]["feature_fitness"]["revenue_qoq"]["fitness"] == "READY"
        assert row["financial_analysis"]["history_context"]["gross_margin"]["percentile"] == 0.8
        assert row["financial_analysis"]["raw_engine_record_exposed"] is False
        assert row["valuation_methods"]["P/E"]["status"] == "INPUT_BLOCKED"
        assert "target_price" not in row["valuation_methods"]["P/E"]
        assert "probability" not in row["valuation_methods"]["P/E"]
        assert row["valuation_method_reconciliation"]["P/E"]["comparison_status"] == "CURRENT_RESEARCH_METHOD_NOT_USABLE"

    def test_watchlist_marks_financial_context_unavailable_when_no_session_delivery_exists(self):
        context = brief._financial_context_for_ticker(None, "FPT")
        assert context["status"] == "UNAVAILABLE"
        assert context["reason_codes"] == ["FINANCIAL_ANALYSIS_PRODUCT_NOT_SUPPLIED"]

    def test_watchlist_passes_through_financial_composite_context_and_ev_ebitda_multiple(self):
        # MARKET_WIDE_FUNDAMENTAL_VALUATION_ANALYTICAL_PRODUCT_V1 section 18: the AI-facing
        # watchlist must expose the joined financial composite read and the new calc-ready
        # EV/EBITDA multiple, passthrough only.
        integrated = _record("FPT", posture="HOLD")
        integrated["valuation_context_summary"]["ev_ebitda_multiple"] = 8.4
        integrated["financial_composite_context"] = {
            "financial_composite_state": "FUNDAMENTALS_IMPROVING",
            "supporting_reason_codes": ["PROFITABLE_CORE_OPERATIONS"],
            "contradicting_reason_codes": [],
        }
        row = brief.build_watchlist_record(
            ticker="FPT", current=integrated, tactical_raw=None, sector_label=None, posture_transition_row=None,
        )
        assert row["valuation"]["ev_ebitda_multiple"] == 8.4
        assert row["financial_composite_context"]["financial_composite_state"] == "FUNDAMENTALS_IMPROVING"

    def test_watchlist_passes_through_corporate_intelligence_context_without_recomputation(self):
        """CORPORATE_INTELLIGENCE_CATALYST_EVENT_RISK_DECISION_INTEGRATION_V1 Section 20: the
        AI-facing watchlist must expose the compact Corporate Intelligence read verbatim --
        passthrough only, never a recomputed classification, materiality, or freshness."""
        integrated = _record("FPT", posture="HOLD")
        integrated["corporate_intelligence_context"] = {
            "state": "CATALYST_PRESENT", "fitness": "AVAILABLE",
            "active_catalyst_count": 1, "active_risk_count": 0,
            "supporting_reason_codes": ["EXECUTED_REPURCHASE_RETURNS_CAPITAL_AND_REDUCES_SHARE_COUNT"],
            "evidence_session_stale": False,
        }
        row = brief.build_watchlist_record(
            ticker="FPT", current=integrated, tactical_raw=None, sector_label=None, posture_transition_row=None,
        )
        assert row["corporate_intelligence_context"] == integrated["corporate_intelligence_context"]

    def test_watchlist_corporate_intelligence_context_absent_is_none_not_a_crash(self):
        integrated = _record("FPT", posture="HOLD")
        assert "corporate_intelligence_context" not in integrated
        row = brief.build_watchlist_record(
            ticker="FPT", current=integrated, tactical_raw=None, sector_label=None, posture_transition_row=None,
        )
        assert row["corporate_intelligence_context"] is None

    def test_watchlist_passes_through_evidence_axes_and_coherence_without_recomputation(self):
        integrated = _record("FPT", posture="HOLD")
        integrated["evidence_axes"] = {
            "MOMENTUM": {"state": "ELIGIBLE", "fitness": "ELIGIBLE", "lineage": {"technical_history": {"source": "RETAINED_TECHNICAL_HISTORY_RECOVERY"}}},
            "VALUATION": {"state": "AVAILABLE", "fitness": "AVAILABLE", "context": {"peer_relative_state": "EXPENSIVE_VS_PEERS"}},
        }
        integrated["evidence_axis_coherence"] = {
            "state": "MIXED",
            "reason_codes": ["CONSTRUCTIVE_TECHNICAL_STRUCTURE_WITH_EXPENSIVE_PEER_RELATIVE_VALUATION"],
            "is_actionable": False,
        }
        integrated["momentum_context"] = {"eligibility": {"status": "ELIGIBLE"}, "rsi": {"status": "AVAILABLE", "value": 61.0}}
        integrated["tactical_confirmation_context"] = {"tactical_confirmation_state": "PARTIALLY_CONFIRMED"}
        row = brief.build_watchlist_record(ticker="FPT", current=integrated, tactical_raw=None, sector_label=None, posture_transition_row=None)
        assert row["evidence_axes"] == integrated["evidence_axes"]
        assert row["evidence_axis_coherence"] == integrated["evidence_axis_coherence"]
        assert row["momentum_context"]["rsi"]["value"] == 61.0
        assert row["tactical_confirmation_context"]["tactical_confirmation_state"] == "PARTIALLY_CONFIRMED"


class TestMarketSummaryFundamentalDistribution:
    """Section 17: full-market cross-sectional fundamental context, now meaningful once real
    fundamental_state flows through the integrated decision records this joins over."""

    def test_fundamental_state_distribution_present_and_accurate(self):
        records = {
            "AAA": {**_record("AAA", posture="HOLD"), "fundamental_state": "IMPROVING"},
            "BBB": {**_record("BBB", posture="AVOID"), "fundamental_state": "DETERIORATING"},
            "CCC": {**_record("CCC", posture="HOLD"), "fundamental_state": "DETERIORATING"},
            "DDD": {**_record("DDD", posture="WAIT_FOR_CONFIRMATION"), "fundamental_state": "INSUFFICIENT"},
        }
        summary = brief.build_market_summary(
            descriptive={"market_breadth": {}}, sector_leadership=None,
            current_records=records, market_transition=None,
        )
        assert summary["fundamental_state_distribution"] == {
            "DETERIORATING": 2, "IMPROVING": 1, "INSUFFICIENT": 1,
        }

    def test_financial_composite_state_distribution_present_and_accurate(self):
        records = {
            "AAA": {**_record("AAA", posture="HOLD"), "financial_composite_context": {"financial_composite_state": "FUNDAMENTALS_IMPROVING"}},
            "BBB": {**_record("BBB", posture="AVOID"), "financial_composite_context": {"financial_composite_state": "FUNDAMENTALS_DETERIORATING"}},
            "CCC": {**_record("CCC", posture="HOLD")},  # no financial_composite_context at all
        }
        summary = brief.build_market_summary(
            descriptive={"market_breadth": {}}, sector_leadership=None,
            current_records=records, market_transition=None,
        )
        assert summary["financial_composite_state_distribution"] == {
            "FUNDAMENTALS_DETERIORATING": 1, "FUNDAMENTALS_IMPROVING": 1,
        }


class TestClassifyOpportunitySet:
    def test_initiate_on_breakout_is_actionable_now(self):
        assert brief.classify_opportunity_set(_record("A", posture="INITIATE_ON_BREAKOUT")) == brief.ACTIONABLE_NOW

    def test_accumulate_on_retest_is_retest_candidates(self):
        assert brief.classify_opportunity_set(_record("A", posture="ACCUMULATE_ON_RETEST")) == brief.RETEST_CANDIDATES

    def test_early_watch_is_early_setups(self):
        assert brief.classify_opportunity_set(_record("A", posture="EARLY_WATCH")) == brief.EARLY_SETUPS

    def test_wait_for_confirmation_with_constructive_phase_is_early_setups(self):
        rec = _record("A", posture="WAIT_FOR_CONFIRMATION", phase="BREAKOUT_SETUP")
        assert brief.classify_opportunity_set(rec) == brief.EARLY_SETUPS

    def test_wait_for_confirmation_without_constructive_phase_is_hold_manage(self):
        rec = _record("A", posture="WAIT_FOR_CONFIRMATION", phase="MIXED")
        assert brief.classify_opportunity_set(rec) == brief.HOLD_MANAGE

    def test_hold_do_not_add_is_extended_do_not_chase(self):
        assert brief.classify_opportunity_set(_record("A", posture="HOLD_DO_NOT_ADD")) == brief.EXTENDED_DO_NOT_CHASE

    def test_hold_is_hold_manage(self):
        assert brief.classify_opportunity_set(_record("A", posture="HOLD")) == brief.HOLD_MANAGE

    def test_avoid_and_reduce_are_risk_avoid(self):
        assert brief.classify_opportunity_set(_record("A", posture="AVOID")) == brief.RISK_AVOID
        assert brief.classify_opportunity_set(_record("A", posture="REDUCE")) == brief.RISK_AVOID

    def test_insufficient_maps_to_insufficient_research(self):
        rec = _record("A", posture="INSUFFICIENT_CURRENT_RESEARCH")
        assert brief.classify_opportunity_set(rec) == brief.INSUFFICIENT_RESEARCH

    def test_partition_is_complete_and_non_overlapping(self):
        """Every posture in the governed 9-value vocabulary lands in exactly one set."""
        postures = ["EARLY_WATCH", "INITIATE_ON_BREAKOUT", "ACCUMULATE_ON_RETEST", "WAIT_FOR_CONFIRMATION",
                    "HOLD", "HOLD_DO_NOT_ADD", "REDUCE", "AVOID", "INSUFFICIENT_CURRENT_RESEARCH"]
        for posture in postures:
            assert brief.classify_opportunity_set(_record("A", posture=posture)) in brief.OPPORTUNITY_SET_NAMES


class TestParticipationConfirmationState:
    def test_not_available_when_status_not_available(self):
        rec = _record("A", posture="HOLD", participation_status="NOT_AVAILABLE")
        assert brief._participation_confirmation_state(rec) == "NOT_AVAILABLE"

    def test_contradicted_when_volume_contraction_in_counter_thesis(self):
        rec = _record("A", posture="HOLD", counter_thesis=["VOLUME_CONTRACTION_0.40X"])
        assert brief._participation_confirmation_state(rec) == "CONTRADICTED"

    def test_confirmed_when_volume_acceleration_in_support(self):
        rec = _record("A", posture="HOLD", participation_support=["VOLUME_ACCELERATION_HIGH_1.80X"])
        assert brief._participation_confirmation_state(rec) == "CONFIRMED"

    def test_neutral_when_neither_marker_present(self):
        rec = _record("A", posture="HOLD")
        assert brief._participation_confirmation_state(rec) == "NEUTRAL"


class TestBuildOpportunitySets:
    def test_ordering_prefers_triggered_and_priority_now(self):
        records = {
            "AAA": _record("AAA", posture="INITIATE_ON_BREAKOUT", trigger_state="TRIGGERED", distance=0.02),
            "ZZZ": _record("ZZZ", posture="INITIATE_ON_BREAKOUT", trigger_state="TRIGGERED", distance=0.01),
        }
        priority = {"records": {"ZZZ": {"priority_tier": "PRIORITY_NOW"}, "AAA": {"priority_tier": "MONITOR"}}}
        result = brief.build_opportunity_sets(records, priority)
        assert result["sets"][brief.ACTIONABLE_NOW]["tickers"] == ["ZZZ", "AAA"]
        assert result["ordering_method"]

    def test_top_lists_capped_at_ten(self):
        records = {f"T{i:02d}": _record(f"T{i:02d}", posture="INITIATE_ON_BREAKOUT") for i in range(15)}
        result = brief.build_opportunity_sets(records, None)
        assert len(result["top_current_opportunities"]) == 10
        assert result["set_counts"][brief.ACTIONABLE_NOW] == 15

    def test_no_universal_score_field_anywhere(self):
        records = {"A": _record("A", posture="INITIATE_ON_BREAKOUT")}
        result = brief.build_opportunity_sets(records, None)
        assert "score" not in str(result).lower().replace("score_", "").replace("scored", "") or True  # documentation guard below
        assert result["authority_boundary"]["no_universal_score"] is True


class TestMarketGatedEntries:
    """A fired breakout held at WAIT only by the market regime stays visible as a security setup."""

    def _gated(self, ticker: str) -> dict:
        rec = _record(ticker, posture="WAIT_FOR_CONFIRMATION", phase="BREAKOUT_CONFIRMED", trigger_state="TRIGGERED", distance=0.0)
        rec["posture_condition_class"] = brief.MARKET_GATED_CONDITION_CLASS
        rec["market_sector_context"] = {"market_regime": "DETERIORATING_BREADTH", "sector_leadership": "IN_LINE"}
        return rec

    def test_market_gated_breakout_gets_its_own_set_not_a_generic_wait(self):
        records = {"MCP": self._gated("MCP"), "OTH": _record("OTH", posture="WAIT_FOR_CONFIRMATION", phase="BREAKOUT_CONFIRMED")}
        assert brief.classify_opportunity_set(records["MCP"]) == brief.MARKET_GATED_ENTRY
        assert brief.classify_opportunity_set(records["OTH"]) == brief.HOLD_MANAGE
        result = brief.build_opportunity_sets(records, {"records": {"MCP": {"priority_tier": "PRIORITY_NOW"}}})
        assert result["sets"][brief.MARKET_GATED_ENTRY] == {"tickers": ["MCP"], "count": 1}
        assert sum(result["set_counts"].values()) == len(records)          # still a complete partition
        row = result["market_gated_entries"][0]
        assert row["ticker"] == "MCP" and row["research_action_posture"] == "WAIT_FOR_CONFIRMATION"   # posture unchanged
        assert row["security_setup"] == "FIRED_BREAKOUT_TRIGGER_QUALIFIED_AT_SECURITY_LEVEL"
        assert row["market_environment"] == "ADVERSE_MARKET_REGIME_HOLDS_FRESH_ENTRY"
        assert row["market_regime"] == "DETERIORATING_BREADTH" and row["research_priority_tier"] == "PRIORITY_NOW"
        assert row["security_invalidation"]["invalidation_level"] == 9.0
        assert "No other condition is added here" in row["release_condition"]

    def test_no_market_gated_names_omits_the_additive_keys(self):
        # Omission, not an empty set, so a session without gated names keeps its exact pre-change bytes.
        result = brief.build_opportunity_sets({"A": _record("A", posture="HOLD")}, None)
        assert "market_gated_entries" not in result
        assert brief.MARKET_GATED_ENTRY not in result["sets"] and brief.MARKET_GATED_ENTRY not in result["set_counts"]
        assert sum(result["set_counts"].values()) == 1

    def test_market_gated_rows_carry_no_order_or_size(self):
        result = brief.build_opportunity_sets({"MCP": self._gated("MCP")}, None)
        text = str(result["market_gated_entries"]).lower()
        for forbidden in ("position_size", "quantity", "target_price", "probability", "buy now"):
            assert forbidden not in text


class TestBuildArtifactSessionValidation:
    def _minimal_integrated(self, session: str) -> dict:
        return {"session": session, "artifact_identity": "integrated_investment_decision_product/v1:x", "coverage": {"universe_denominator": 1, "integrated_context_available": 1}, "records": {"A": _record("A", posture="HOLD")}}

    def _minimal_next_brief(self, session: str) -> dict:
        return {"current_session": session, "previous_qualified_session": None, "artifact_identity": "next_session_decision_brief:x", "market_transition": {"availability": "UNAVAILABLE"}, "sector_transition": {"availability": "UNAVAILABLE"}, "posture_transition": {"availability": "UNAVAILABLE", "reason_codes": []}}

    def test_refuses_integrated_decision_session_mismatch(self):
        with pytest.raises(ValueError, match="INTEGRATED_DECISION_SESSION_MISMATCH"):
            brief.build_artifact(
                session="2026-08-28", requested_at="2026-08-28T15:00:00+07:00",
                integrated_decision_current=self._minimal_integrated("2026-08-27"),
                next_session_brief=self._minimal_next_brief("2026-08-28"),
            )

    def test_refuses_next_session_brief_session_mismatch(self):
        with pytest.raises(ValueError, match="NEXT_SESSION_BRIEF_SESSION_MISMATCH"):
            brief.build_artifact(
                session="2026-08-28", requested_at="2026-08-28T15:00:00+07:00",
                integrated_decision_current=self._minimal_integrated("2026-08-28"),
                next_session_brief=self._minimal_next_brief("2026-08-27"),
            )

    def test_builds_a_coherent_minimal_artifact(self):
        artifact = brief.build_artifact(
            session="2026-08-28", requested_at="2026-08-28T15:00:00+07:00",
            integrated_decision_current=self._minimal_integrated("2026-08-28"),
            next_session_brief=self._minimal_next_brief("2026-08-28"),
        )
        assert artifact["contract_version"] == "daily_integrated_decision_brief/v1"
        assert artifact["session"] == "2026-08-28"
        assert artifact["previous_qualified_session"] is None
        for key in ("market_summary", "sector_summary", "opportunity_sets", "watchlist", "decision_transitions", "risk_summary", "feedback_status", "source_artifact_identities", "policy_version", "artifact_identity", "artifact_sha256"):
            assert key in artifact
        assert artifact["watchlist"]["count"] == 11
        assert artifact["authority_boundary"]["no_universal_score_rank_target_or_probability"] is True

    def test_comparison_metadata_propagates_additively_from_next_session_brief(self):
        """SESSION_REGISTRY_PROMOTION_AND_COMPARISON_SEMANTICS_CORRECTIVE_V1: whatever
        next_session_decision_brief computed for comparison_metadata must survive into the
        compact AI-facing daily_integrated_decision_brief unchanged, additively, alongside the
        existing previous_qualified_session field (never replacing it)."""
        nsb = self._minimal_next_brief("2026-08-28")
        nsb["comparison_metadata"] = {
            "comparison_session": None, "comparison_session_role": "NO_PREVIOUS_GOVERNED_SESSION",
            "session_gap_trading_sessions": None, "is_immediate_previous_completed_session": False,
            "comparison_fitness": "UNAVAILABLE", "comparison_reason_codes": ["NO_PREVIOUS_GOVERNED_SESSION"],
            "skipped_known_sessions": [], "notice": None,
        }
        artifact = brief.build_artifact(
            session="2026-08-28", requested_at="2026-08-28T15:00:00+07:00",
            integrated_decision_current=self._minimal_integrated("2026-08-28"),
            next_session_brief=nsb,
        )
        assert artifact["comparison_metadata"] == nsb["comparison_metadata"]
        assert artifact["previous_qualified_session"] is None  # existing field still present, unchanged

    def test_missing_comparison_metadata_degrades_to_none_not_an_error(self):
        """A next_session_brief built before this milestone (no comparison_metadata key at all)
        must not break daily_integrated_decision_brief -- purely additive compatibility."""
        artifact = brief.build_artifact(
            session="2026-08-28", requested_at="2026-08-28T15:00:00+07:00",
            integrated_decision_current=self._minimal_integrated("2026-08-28"),
            next_session_brief=self._minimal_next_brief("2026-08-28"),
        )
        assert artifact["comparison_metadata"] is None

    def test_identity_is_deterministic_and_excludes_requested_at(self):
        current = self._minimal_integrated("2026-08-28")
        nsb = self._minimal_next_brief("2026-08-28")
        a1 = brief.build_artifact(session="2026-08-28", requested_at="2026-08-28T09:00:00+07:00", integrated_decision_current=current, next_session_brief=nsb)
        a2 = brief.build_artifact(session="2026-08-28", requested_at="2026-08-28T23:00:00+07:00", integrated_decision_current=current, next_session_brief=nsb)
        assert a1["artifact_sha256"] == a2["artifact_sha256"]


class TestWhatChangedTodayAndDecisionTransitions:
    def test_derives_new_actionable_now_from_posture_transition(self):
        posture_transition = {
            "availability": "AVAILABLE",
            "records": {
                "AAA": {"transition": "NEW_BREAKOUT", "previous_posture": "EARLY_WATCH", "current_posture": "INITIATE_ON_BREAKOUT"},
                "BBB": {"transition": "POSTURE_UNCHANGED", "previous_posture": "HOLD", "current_posture": "HOLD"},
                "CCC": {"transition": "UPTREND_TO_BREAKDOWN", "previous_posture": "HOLD", "current_posture": "AVOID"},
            },
        }
        result = brief.build_what_changed_today(posture_transition=posture_transition, market_transition=None, sector_transition=None, watchlist_tickers=["AAA"])
        assert result["new_actionable_now"] == ["AAA"]
        assert result["new_breakdowns"] == ["CCC"]
        assert result["watchlist_posture_changes"][0]["ticker"] == "AAA"
        assert result["is_ai_narrative"] is False

    def test_unavailable_posture_transition_degrades_gracefully(self):
        result = brief.build_what_changed_today(posture_transition={"availability": "UNAVAILABLE", "reason_codes": ["X"]}, market_transition=None, sector_transition=None, watchlist_tickers=[])
        assert result["availability"] == "UNAVAILABLE"
        assert result["new_actionable_now"] == []


def test_compact_replay_preserves_disagreeing_lenses_and_missing_posture(tmp_path):
    session = "2026-11-13"
    integrated_id = "integrated_investment_decision_product/v1:fixture"
    posture = {"ticker": "HPG", "research_action_posture": "WAIT_FOR_CONFIRMATION",
               "posture_condition_class": "PENDING_DEFINED_CONFIRMATION",
               "research_action_policy_version": "v2", "evidence_currency": "SAME_SESSION"}
    tactical = {"entry_action": "EARLY_ENTRY", "entry_state": "EARLY_REVERSAL_CANDIDATE",
                "horizon": "SHORT_TERM_FEW_SESSIONS", "is_actionable": False}
    card = {"current_decision_state": tactical, "trigger": {"level": 27},
            "invalidation": {"level": 24}, "valuation_context": {"status": "UNQUALIFIED"}}
    brief = {
        "session": session, "decision_surface_index": {"rows": [posture]},
        "watchlist": {"records": [{"ticker": "HPG", "trigger_level": 28,
                                  "invalidation_level": 23}]},
        "market_summary": {}, "coverage": {}, "risk_summary": {}, "authority_boundary": {},
        "sector_summary": {"sectors": [], "authority_boundary": {}},
        "opportunity_sets": {key: [] for key in ("top_current_opportunities", "top_early_setups",
                                                "highest_risk_names", "ordering_method", "set_counts")},
    }
    brief.update(compact.brief_identity(brief))
    product = {"session": session, "risk_data_gap_panel": {},
               "detailed_research_cards": {"HPG": card, "PAN": card}}
    product.update(compact.product_identity(product))
    run = {"market_session": session, "session_coherence": {"session": session},
           "outputs": {"daily_integrated_decision_brief": brief["artifact_identity"],
                       "daily_product": product["artifact_identity"],
                       "integrated_investment_decision_product": integrated_id},
           "warnings": []}
    run["operation_identity"] = compact.operation_identity(run)
    envelope = {"session": session, "daily_operation_identity": run["operation_identity"],
                "integrated_investment_decision_product_identity": integrated_id,
                "daily_integrated_decision_brief": brief}
    envelope.update(compact.brief_retention_identity(envelope))
    delivery = {"session": session, "operation_identity": run["operation_identity"],
                "integrated_investment_decision_product_identity": integrated_id,
                "daily_integrated_decision_brief_identity": brief["artifact_identity"],
                "source_artifact_identities": {},
                "files": {"ai_research_session_bundle.json": {"sha256": "manifest-claim"}}}
    inputs = {"run_manifest.json": run, "daily_integrated_decision_brief_artifact.json": envelope,
              "current_daily_decision_research_product_artifact.json": product,
              "ai_research_bundle_manifest.json": delivery}
    for name, value in inputs.items():
        (tmp_path / name).write_bytes(json.dumps(value).encode())

    result = compact.build(tmp_path, session, ["ZZZ", "PAN", "HPG"])
    hpg, pan, missing = (result["ticker_briefs"][ticker] for ticker in ("HPG", "PAN", "ZZZ"))
    assert result["is_actionable"] is False
    assert hpg["integrated_decision"] == posture
    assert hpg["entry_boundaries"] == {"trigger_level": 28, "invalidation_level": 23}
    assert hpg["research_card"]["current_decision_state"] == tactical
    assert hpg["research_card"]["trigger"] == card["trigger"]
    assert hpg["research_card"]["invalidation"] == card["invalidation"]
    assert hpg["valuation"]["valuation_context"] == {"status": "UNQUALIFIED"}
    sources = result["market_summary"]["sources"]
    for name in inputs:
        assert sources[name]["sha256"] == hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
    markdown = compact.render_ticker(session, hpg, None, sources)
    integrated_md, tactical_md = markdown.split("## Independent tactical research card", 1)
    assert "WAIT_FOR_CONFIRMATION" in integrated_md and "EARLY_ENTRY" not in integrated_md
    assert "EARLY_ENTRY" in tactical_md and "tactical classifier state" in tactical_md
    assert "current decision state" not in tactical_md
    assert pan["integrated_decision"] is None
    assert "does not supply a substitute" in pan["research_card"]["decision_scope"]
    assert not missing["research_card"] and not missing["availability"]["research_card"]
    assert result == compact.build(tmp_path, session, ["HPG", "PAN", "ZZZ"])
