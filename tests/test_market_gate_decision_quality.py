"""MARKET_GATE_DECISION_QUALITY_V1: synthetic fixtures for logic and failure paths only.

No real-market performance is claimed from these tests.
"""
import copy
from pathlib import Path

import pytest

import completed_market_session_gate as gate
import empirical_setup_outcome_calibration as calibration
import governed_session_chain as chains
import integrated_decision_prospective_feedback as feedback_bridge
import prospective_market_snapshot_contract as market
import prospective_pit_capture as capture
from stocklookup_core.decision import daily_integrated_decision_brief as brief_module

ROOT = Path(__file__).resolve().parents[1]
DAYS = ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-11-06", "2026-11-09", "2026-11-10"]
D0, D1 = DAYS[0], DAYS[1]
GATE = calibration.MARKET_GATE_CONDITION_CLASS
BASIS = "CURRENT_DESCRIPTIVE_DNSE_REST_ADJUSTED_RETROSPECTIVE_RAW_AS_TRADED_NOT_PROMOTED"
TRANSFORM = "identity_provider_numeric_ohlc/v1"
# Closes on DAYS. AAA: released into entry, the move continued. DDD: released into entry after the
# move. BBB: large decline while held. CCC: released extended, no material move.
CLOSES = {
    "AAA": [10.0, 10.5, 10.8, 11.0, 11.2, 11.5, 11.6],
    "BBB": [10.0, 9.8, 9.5, 9.2, 9.0, 9.1, 9.0],
    "CCC": [10.0, 10.1, 10.0, 10.05, 10.1, 10.1, 10.0],
    "DDD": [10.0, 12.0, 11.8, 11.5, 11.2, 11.0, 11.0],
    "EEE": [20.0, 20.4, 20.8, 21.0, 21.4, 21.8, 22.0],
    "FFF": [5.0, 5.0, 5.0, 5.0, 5.0, 5.0, 5.0],
}
SEALED = {ticker: f"decision:{ticker}:{index:016x}" for index, ticker in enumerate(sorted(CLOSES))}


def calendar(days):
    return gate.build_working_dates_calendar_receipt(market.canonical({"workingDates": days}),
        retrieved_at=days[0] + "T01:00:00Z", documentation_sha256="a" * 64,
        documentation_retrieved_at="2026-10-02T03:40:00Z")


def completed(day):
    return capture.identified({"contract_version": "prospective_capture_complete_session/v1", "session": day,
        "completion_known_at": day + "T12:05:00Z", "completion_gate_status": "READY", "completion_gate_identity": "gate:" + day,
        "capture_binding_identity": "binding:" + day, "listing_presence_identity": "listing:" + day,
        "market_manifest_identity": "manifest:" + day}, "prospective_capture_complete_session")


def chain(realized=DAYS, *, as_of="2026-12-31T12:00:00Z"):
    return chains.GovernedSessionChain([completed(d) for d in realized], calendar=chains.CalendarCoverage([calendar(DAYS)], cutoff=as_of),
                                       as_of=as_of, first_complete_capture_session=DAYS[0])


def row(ticker, posture, condition):
    return {"ticker": ticker, "research_action_posture": posture, "posture_condition_class": condition,
            "research_action_policy_version": "v2", "evidence_currency": "CURRENT_SESSION", "opportunity_priority_tier": "MONITOR"}


def brief(session, rows, *, regime, descriptor, ratio, policy="v2"):
    inner = {"contract_version": brief_module.CONTRACT_VERSION, "policy_version": policy,
             "decision_surface_index": {"contract_version": "decision_surface_index/v1", "rows": rows},
             "market_summary": {"market_regime": regime, "breadth": {"breadth_descriptor": descriptor, "advance_ratio": ratio,
                                                                      "advancing": 10, "declining": 20}}}
    inner.update(brief_module.content_identity(inner))
    return {"contract_version": "daily_session_integrated_decision_brief_artifact/v1", "session": session,
            "artifact_identity": "daily_session_integrated_decision_brief_artifact:" + session,
            "integrated_investment_decision_product_identity": "integrated_investment_decision_product/v1:" + session,
            "daily_integrated_decision_brief": inner}


def seal_index(session, tickers, *, source=None):
    body = {"contract_version": "prospective_t0_seal_index/v1", "session": session, "records": {
        t: {"ticker": t, "session": session, "integrated_decision_identity": SEALED[t] + session[-2:],
            "source_decision_artifact_identity": source or "integrated_investment_decision_product/v1:" + session}
        for t in tickers}}
    body.update(market.content_identity(body, kind="prospective_t0_seal_index"))
    return body


def t0_record(ticker, session=D0, *, identity=None, invalidation_operator=">"):
    level = {"AAA": 9.8, "BBB": 9.9, "CCC": 9.7, "DDD": 9.6}.get(ticker, 9.5)

    def boundary(role, operator):
        return {"condition": {"status": "MACHINE_EVALUABLE", "operator": operator, "reference_field": "close",
                              "reference_level": level, "role": role}, "distance_to_trigger_pct": 0.02}
    return {"ticker": ticker, "as_of_session": session, "decision_identity": identity or SEALED[ticker] + session[-2:],
            "posture_condition_class": GATE, "tactical_phase": "BREAKOUT_CONFIRMED",
            "trigger": boundary("trigger", ">"), "invalidation": boundary("invalidation", invalidation_operator)}


def day0_rows():
    return [row(t, "WAIT_FOR_CONFIRMATION", GATE) for t in ("AAA", "BBB", "CCC", "DDD")] + [
        row("FFF", "AVOID", "BEARISH_STRUCTURE_ADVERSE")]


def day1_rows():
    return [row("AAA", "INITIATE_ON_BREAKOUT", "FRESH_ENTRY_TRIGGER"), row("BBB", "WAIT_FOR_CONFIRMATION", GATE),
            row("CCC", "HOLD_DO_NOT_ADD", "EXTENDED_NO_CHASE"), row("DDD", "INITIATE_ON_BREAKOUT", "FRESH_ENTRY_TRIGGER"),
            row("EEE", "INITIATE_ON_BREAKOUT", "FRESH_ENTRY_TRIGGER"), row("FFF", "AVOID", "BEARISH_STRUCTURE_ADVERSE")]


def session_inputs():
    gated = ("AAA", "BBB", "CCC", "DDD")
    return [
        calibration.market_gate_session_input(brief(D0, day0_rows(), regime="DETERIORATING_BREADTH", descriptor="MARKET_BREADTH_NEGATIVE", ratio=0.16),
            seal_index=seal_index(D0, gated + ("FFF",)), t0_records={t: t0_record(t) for t in gated}),
        calibration.market_gate_session_input(brief(D1, day1_rows(), regime="MIXED_BREADTH", descriptor="MARKET_BREADTH_MIXED", ratio=0.4),
            seal_index=seal_index(D1, sorted(CLOSES))),
    ]


def raw_snapshot(day, closes=CLOSES, *, basis=BASIS, history=True):
    records = {}
    for ticker, series in closes.items():
        index = DAYS.index(day)
        own = {"session": day, "close": series[index], "price_basis": basis, "transformation_identity": TRANSFORM,
               "provider": "DNSE", "dataset": "DNSE_OHLC_1D", "qualification": "CURRENT_MARKET_DESCRIPTIVE_QUALIFIED_ONLY", "volume": 1}
        rows = [own]
        if history and index:
            rows.insert(0, {**own, "session": DAYS[index - 1], "close": 999.0})
        records[ticker] = {"observations": rows, "status": "OBSERVED"}
    return {"resolved_completed_session": day, "snapshot_identity": "p3f9_exact_session_snapshot:" + day, "records": records}


def prices(overrides=None):
    result = {day: calibration.project_exact_session_price_rows(raw_snapshot(day)) for day in DAYS}
    for (ticker, day), change in (overrides or {}).items():
        observation = result[day]["records"][ticker]["observations"][0]
        if change is None:
            del result[day]["records"][ticker]
        else:
            observation.update(change)
    return result


def evaluate(inputs=None, *, governed=None, snapshots=None):
    return calibration.build_market_gate_evaluation(inputs if inputs is not None else session_inputs(), chain=governed or chain(),
        price_snapshots=snapshots if snapshots is not None else prices(), evaluated_as_of="2026-11-10")


def cases(evaluation, group=calibration.GATED_GROUP, session=D0):
    return {case["ticker"]: case for case in evaluation["cases"] if case["group"] == group and case["t0_session"] == session}


def test_labels_release_and_decision_time_facts_preserved():
    evaluation = evaluate()
    gated = cases(evaluation)
    assert {t: c["descriptive_label"]["label"] for t, c in gated.items()} == {
        "AAA": "DELAYED_ENTRY_STILL_AVAILABLE", "BBB": "AVOIDED_DOWNSIDE", "CCC": "NO_MATERIAL_MOVE", "DDD": "MISSED_UPSIDE"}
    assert gated["AAA"]["release"]["state"] == "GATE_RELEASED_AFTER_CONFIRMATION"
    assert gated["AAA"]["release"]["governed_sessions_to_release"] == 1
    assert gated["AAA"]["move_before_release"]["return"] == pytest.approx(0.05)
    assert gated["AAA"]["delayed_entry"]["return_from_release_to_label_horizon_end"] == pytest.approx(11.5 / 10.5 - 1)
    assert gated["BBB"]["release"]["state"] == "GATE_STILL_ACTIVE_AT_LAST_RECORD"
    assert gated["CCC"]["release"]["state"] == "RELEASED_EXTENDED_DO_NOT_CHASE"
    # Original identity, policy and decision-time regime survive; the later MIXED regime never relabels T0.
    assert gated["AAA"]["t0_decision_identity"] == SEALED["AAA"] + "02"
    assert gated["AAA"]["t0_policy_version"] == "v2" and gated["AAA"]["t0_posture"] == "WAIT_FOR_CONFIRMATION"
    assert gated["AAA"]["t0_market_context"]["market_regime"] == "DETERIORATING_BREADTH"
    assert gated["AAA"]["t0_setup"]["downside_invalidation_status"] == "NOT_A_DOWNSIDE_BOUNDARY_AT_T0"
    # Both favourable and unfavourable outcomes stay visible.
    # BBB is held again on 2026-11-03: a second, separately identified observation.
    assert evaluation["case_counts"][calibration.GATED_GROUP] == 5
    assert evaluation["gated_descriptive_labels"]["AVOIDED_DOWNSIDE"] == 2
    assert evaluation["gated_descriptive_labels"]["MISSED_UPSIDE"] == 1


def test_session_horizons_and_comparable_baseline():
    evaluation = evaluate()
    aaa = cases(evaluation)["AAA"]["horizons"]
    assert aaa["T5"]["future_session"] == "2026-11-09"  # five completed sessions, across the weekend
    assert aaa["T5"]["return"] == pytest.approx(0.15)
    assert aaa["T60"]["status"] == "UNSUPPORTED_CALENDAR_GAP" and aaa["T60"]["return"] is None
    baseline = cases(evaluation, calibration.BASELINE_GROUP, D1)
    assert sorted(baseline) == ["AAA", "DDD", "EEE"] and evaluation["case_counts"][calibration.BASELINE_GROUP] == 3
    summary = evaluation["groups"][calibration.GATED_GROUP]["T5"]
    assert summary["eligible_count"] == 5 and summary["mature_count"] == 5 and summary["distinct_mature_t0_sessions"] == 2
    assert summary["excess_vs_same_session_universe_median"]["n"] == 5
    assert evaluation["same_session_universe_median"][D0 + "|T5"]["mature_count"] == 5


def test_missed_capture_never_matures_and_insufficient_verdict():
    evaluation = evaluate(governed=chain([d for d in DAYS if d != "2026-11-05"]))
    aaa = cases(evaluation)["AAA"]
    assert aaa["horizons"]["T1"]["status"] == "MATURE"
    assert aaa["horizons"]["T3"]["status"] == "MISSED_CAPTURE" and aaa["horizons"]["T5"]["status"] == "MISSED_CAPTURE"
    assert aaa["descriptive_label"] == {"label": "INDETERMINATE", "reason": "T5_MISSED_CAPTURE", "basis_horizon": "T5", "semantics": "DESCRIPTIVE_NOT_CAUSAL"}
    verdict = evaluation["evidence_verdict"]
    assert verdict["state"] == calibration.INSUFFICIENT_EVIDENCE_FOR_POLICY_CHANGE and verdict["policy_change_authorized"] is False
    assert any(gap["state"] == "MISSED_CAPTURE" for gap in evaluation["session_accounting"]["governed_chain_gaps"])


def test_immature_horizons_stay_pending():
    governed = chain(DAYS[:3], as_of="2026-11-04T13:00:00Z")
    aaa = cases(evaluate(governed=governed))["AAA"]["horizons"]
    assert aaa["T1"]["status"] == "MATURE"
    assert {aaa[h]["status"] for h in ("T3", "T5", "T10", "T20")} <= {feedback_bridge.PENDING, "UNSUPPORTED_CALENDAR_GAP"}
    assert all(aaa[h]["return"] is None for h in ("T3", "T5", "T10", "T20", "T60"))


def test_incompatible_basis_and_missing_close_are_explicit():
    snapshots = prices({("AAA", "2026-11-09"): {"price_basis": "OTHER_BASIS"}, ("BBB", D0): None})
    gated = cases(evaluate(snapshots=snapshots))
    assert gated["AAA"]["horizons"]["T5"]["status"] == "PRICE_BASIS_INCOMPATIBLE"
    assert gated["AAA"]["horizons"]["T5"]["return"] is None
    assert gated["AAA"]["descriptive_label"]["label"] == "INDETERMINATE"
    assert gated["BBB"]["horizons"]["T1"]["status"] == feedback_bridge.PRICE_NOT_RETAINED
    assert gated["BBB"]["move_before_release"] == {"status": "NOT_RELEASED"}


def test_no_double_counting_and_deterministic_identity():
    once = evaluate()
    twice = evaluate(session_inputs() + session_inputs())
    reversed_inputs = evaluate(list(reversed(session_inputs())))
    assert once["artifact_identity"] == twice["artifact_identity"] == reversed_inputs["artifact_identity"]
    assert once["cohort_identity"] == twice["cohort_identity"] and once["case_counts"][calibration.GATED_GROUP] == 5
    conflicting = session_inputs()
    conflicting.append({**conflicting[0], "brief_identity": "other"})
    with pytest.raises(calibration.MarketGateEvidenceError, match="CONFLICTING_DECISION_RECORDS_FOR_SESSION"):
        evaluate(conflicting)


def test_inputs_are_not_rewritten_and_later_records_do_not_leak():
    inputs = session_inputs()
    snapshots = prices()
    before = copy.deepcopy((inputs, snapshots))
    first = evaluate(inputs, snapshots=snapshots)
    assert (inputs, snapshots) == before
    later = calibration.market_gate_session_input(brief("2026-11-04", [row("AAA", "AVOID", "BEARISH_STRUCTURE_ADVERSE")],
                                                        regime="NARROW_LEADERSHIP", descriptor="MARKET_BREADTH_MIXED", ratio=0.6))
    second = evaluate(inputs + [later], snapshots=snapshots)
    for key in ("t0_decision_identity", "t0_posture", "t0_condition_class", "t0_market_context", "t0_setup", "horizons"):
        assert cases(first)["AAA"][key] == cases(second)["AAA"][key]


def test_refuses_tampered_or_mismatched_records():
    tampered = brief(D0, day0_rows(), regime="X", descriptor="Y", ratio=0.1)
    tampered["daily_integrated_decision_brief"]["decision_surface_index"]["rows"][0]["research_action_posture"] = "INITIATE_ON_BREAKOUT"
    with pytest.raises(calibration.MarketGateEvidenceError, match="BRIEF_CONTENT_IDENTITY_INVALID"):
        calibration.market_gate_session_input(tampered)
    duplicated = brief(D0, day0_rows() + [row("AAA", "AVOID", "X")], regime="X", descriptor="Y", ratio=0.1)
    with pytest.raises(calibration.MarketGateEvidenceError, match="CONFLICTING_DECISION_ROW"):
        calibration.market_gate_session_input(duplicated)
    good = brief(D0, day0_rows(), regime="X", descriptor="Y", ratio=0.1)
    with pytest.raises(calibration.MarketGateEvidenceError, match="SEAL_INDEX_SOURCE_MISMATCH"):
        calibration.market_gate_session_input(good, seal_index=seal_index(D0, ["AAA"], source="integrated_investment_decision_product/v1:other"))
    with pytest.raises(calibration.MarketGateEvidenceError, match="T0_RECORD_DECISION_IDENTITY_MISMATCH"):
        calibration.market_gate_session_input(good, seal_index=seal_index(D0, ["AAA"]), t0_records={"AAA": t0_record("AAA", identity="decision:AAA:other")})
    forged = seal_index(D0, ["AAA"])
    forged["records"]["AAA"]["integrated_decision_identity"] = "decision:AAA:forged"
    with pytest.raises(ValueError, match="T0_SEAL_INDEX_IDENTITY_INVALID"):
        calibration.market_gate_session_input(good, seal_index=forged)


def test_unknown_stays_unknown_and_policy_scope_is_separate():
    bare = calibration.market_gate_session_input(brief(D0, day0_rows(), regime="DETERIORATING_BREADTH", descriptor="NEG", ratio=0.1))
    v1 = calibration.market_gate_session_input(brief(D1, day1_rows(), regime="MIXED_BREADTH", descriptor="MIX", ratio=0.4, policy="v1"))
    evaluation = evaluate([bare, v1])
    aaa = cases(evaluation)["AAA"]
    assert aaa["t0_decision_identity"] == calibration.FIELD_NOT_RETAINED and aaa["t0_setup"] == {}
    assert aaa["close_below_t0_trigger"]["status"] == "NO_T0_TRIGGER_LEVEL_RETAINED"
    assert evaluation["session_accounting"]["excluded_sessions"] == [{"session": D1, "reason": "POLICY_VERSION_OUT_OF_SCOPE", "policy_version": "v1"}]
    assert evaluation["case_counts"][calibration.BASELINE_GROUP] == 0
    # The release scan still reads the later decision record; it is a decision fact, not a price.
    assert aaa["release"]["release_session"] == D1


def test_trigger_close_event_is_descriptive():
    gated = cases(evaluate())
    assert gated["BBB"]["close_below_t0_trigger"]["status"] == "CLOSE_BELOW_T0_TRIGGER"
    assert gated["BBB"]["close_below_t0_trigger"]["first_session"] == D1
    assert gated["AAA"]["close_below_t0_trigger"]["status"] == "NOT_OBSERVED_IN_REALIZED_PATH"
    assert gated["AAA"]["close_below_t0_trigger"]["semantics"] == "DESCRIPTIVE_CLOSE_EVENT_NOT_GOVERNED_INVALIDATION"


def test_projection_keeps_only_own_session_rows():
    projected = calibration.project_exact_session_price_rows(raw_snapshot(D1))
    assert projected["records"]["AAA"]["observations"] == [{
        "session": D1, "close": 10.5, "price_basis": BASIS, "transformation_identity": TRANSFORM, "provider": "DNSE",
        "dataset": "DNSE_OHLC_1D", "qualification": "CURRENT_MARKET_DESCRIPTIVE_QUALIFIED_ONLY"}]
    with pytest.raises(calibration.MarketGateEvidenceError, match="PRICE_SNAPSHOT_IDENTITY_MISSING"):
        calibration.project_exact_session_price_rows({"records": {}})


def test_research_only_boundary_and_no_posture_vote():
    evaluation = evaluate()
    boundary = evaluation["authority_boundary"]
    assert boundary["does_not_vote_into_research_action_posture"] and boundary["no_automatic_policy_change"]
    assert boundary["counterfactual_close_to_close_not_an_executed_trade"] and boundary["no_transaction_costs_slippage_or_liquidity_modeled"]
    assert all(case["delayed_entry"]["counterfactual"] == "CLOSE_AT_RELEASE_SESSION_NOT_EXECUTED" for case in cases(evaluation).values())
    for producer in ("stocklookup_core/decision/integrated_investment_decision_product.py",
                     "stocklookup_core/decision/daily_integrated_decision_brief.py", "canonical_daily_operation.py"):
        assert "empirical_setup_outcome_calibration" not in (ROOT / producer).read_text(encoding="utf-8")
    assert evaluation["methodology"]["outcome_thresholds"]["material_upside_return_greater_than_or_equal_to"] == 0.03


def test_vietnamese_summary_reports_counts_and_limits():
    text = calibration.render_market_gate_summary_vi(evaluate(governed=chain([d for d in DAYS if d != "2026-11-05"])))
    assert "Chưa đủ dữ liệu để kết luận quy tắc WAIT nên thay đổi" in text
    assert "giữ 5 thiết lập" in text and "2026-11-05" in text
    assert "không phải tín hiệu mua/bán" in text and "chưa tính phí" in text
