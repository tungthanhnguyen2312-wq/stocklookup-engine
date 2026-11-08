"""brief_market_context/v1 Engine -> Dashboard contract: the committed fixture is real Engine output."""
import json
from pathlib import Path

import pytest

from stocklookup_core.decision import market_close_intelligence as mci
import build_brief_market_context_contract_fixture as gen

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = json.loads(gen.FIXTURE_PATH.read_bytes())


def _pc(name):
    return FIXTURE["cases"][name]["cockpit"]["brief_market_context_v1"]["market_participation_change"]


def test_committed_fixture_is_byte_identical_to_a_fresh_engine_run():
    # Fails on any Engine change that alters the delivered shape or values; regenerate with
    # `python tests/build_brief_market_context_contract_fixture.py --write` and copy the file to
    # stocklookup-dashboard tests/fixtures/ (its CI compares the copy with this repository's main).
    assert gen.FIXTURE_PATH.read_bytes().replace(b"\r\n", b"\n") == gen.render(gen.build_fixture())


def test_condition_is_one_structured_object_with_a_verbatim_state():
    states = set()
    for case in FIXTURE["cases"].values():
        pc = (case["cockpit"].get("brief_market_context_v1") or {}).get("market_participation_change") or {}
        if pc.get("status") != "AVAILABLE":
            continue
        cond = pc["market_close_condition_evaluation"]
        assert set(cond) == {"hypothesis", "state", "condition_source"}
        assert cond["hypothesis"] == "Participation improves"
        states.add(cond["state"])
    assert states == {"CONFIRMED", "REFUTED", "NEITHER_CONFIRMED_NOR_REFUTED"}


def test_asymmetric_momentum_uses_the_both_sessions_denominator():
    pc = _pc("asymmetric_missing_momentum")
    assert pc["cohort"]["matched"] == 4 and pc["cohort"]["matched_with_momentum_both_sessions"] == 3
    # Both sessions on {AAA, BBB, DDD}: 0/3 -> 1/3. The per-session denominators (4 then 3) gave +8.33.
    assert pc["changes"]["positive_momentum_share_pp"] == 33.33
    assert pc["changes"]["advance_ratio_pp"] == _pc("adjacent_broadening_confirmed_with_churn")["changes"]["advance_ratio_pp"]


def test_ma20_eligibility_churn_and_crossings():
    base = _pc("adjacent_broadening_confirmed_with_churn")
    assert base["cohort"] == {"matched": 4, "matched_with_ma20_side_both_sessions": 4, "matched_with_momentum_both_sessions": 4,
                              "current_only": 1, "previous_only": 1, "rule": base["cohort"]["rule"]}
    assert base["ma20_crossings"] == {"crossed_above": 2, "crossed_below": 1, "net": 1}
    ma = _pc("different_ma20_eligibility")
    assert ma["cohort"]["matched_with_ma20_side_both_sessions"] == 3 and ma["ma20_crossings"]["crossed_above"] == 1


def test_span_and_limitations_survive_the_projection():
    sep = _pc("registry_adjacent_calendar_separated")
    assert sep["adjacency"] == "REGISTRY_IMMEDIATE_PREVIOUS_COMPLETED_SESSION"
    assert sep["span"] == {"calendar_weekdays_between": 4, "basis": "MON_FRI_CALENDAR_WARNING_ONLY_NOT_EXCHANGE_CALENDAR",
                           "may_span_multiple_trading_sessions": True}
    assert any("4 weekday(s)" in item for item in sep["limitations"])
    adj = _pc("adjacent_broadening_confirmed_with_churn")
    assert adj["span"]["may_span_multiple_trading_sessions"] is False
    gap = _pc("registry_gap_unverified_adjacency")
    assert gap["adjacency"] == "NON_ADJACENT_SESSION_GAP_2"
    assert any("not verified as the immediately preceding" in item for item in gap["limitations"])


@pytest.mark.parametrize("name,reason", [
    ("missing_previous_snapshot", "NO_PREVIOUS_PARTICIPATION_SNAPSHOT"),
    ("cohort_reconciliation_mismatch", "CURRENT_PARTICIPATION_COHORT_DIFFERS_FROM_MARKET_BREADTH"),
])
def test_refusals_carry_only_status_and_reason(name, reason):
    assert _pc(name) == {"status": "UNAVAILABLE", "reason_codes": [reason]}


def test_market_gated_rows_keep_security_and_market_context_and_policy_fields():
    block = FIXTURE["cases"]["market_gated_entries"]["cockpit"]["brief_market_context_v1"]
    assert block["market_gated_count"] == 1
    row = block["market_gated_entries"][0]
    assert row["ticker"] == "MCP" and row["research_action_posture"] == "WAIT_FOR_CONFIRMATION"
    assert row["posture_condition_class"] == "BEARISH_BREADTH_NARROWS_FRESH_ENTRY"
    assert row["security_setup"] == "FIRED_BREAKOUT_TRIGGER_QUALIFIED_AT_SECURITY_LEVEL"
    assert row["market_environment"] == "ADVERSE_MARKET_REGIME_HOLDS_FRESH_ENTRY"
    assert row["market_regime"] == "DETERIORATING_BREADTH"
    assert row["security_invalidation"]["invalidation_level"] == 9.0
    assert row["decision_identity"] == "fixture-decision:MCP"
    assert block["authority_boundary"]["is_actionable"] is False


def test_older_brief_yields_no_block():
    assert "brief_market_context_v1" not in FIXTURE["cases"]["older_brief_without_new_fields"]["cockpit"]


def _snap(session, rows, delta=0):
    return mci.participation_snapshot(session=session, descriptive=gen._descriptive(session, rows, breadth_count_delta=delta))


def test_reconciliation_refusal_is_scoped_to_a_count_disagreement():
    cur, prev = _snap("2026-11-06", gen.CUR), _snap("2026-11-05", gen.PREV)
    assert mci.session_change(cur, prev)["status"] == "AVAILABLE"
    absent = dict(_snap("2026-11-06", gen.CUR), cohort_reconciliation="MARKET_BREADTH_COUNT_ABSENT")
    assert mci.session_change(absent, prev)["status"] == "AVAILABLE"            # older artifacts stay comparable
    assert mci.session_change(cur, _snap("2026-11-05", gen.PREV, delta=-1))["reason_codes"] == [
        "PREVIOUS_PARTICIPATION_COHORT_DIFFERS_FROM_MARKET_BREADTH"]


def test_no_momentum_known_in_both_sessions_gives_no_momentum_change():
    rows = {t: gen._rec(r["technical_features"]["values"]["return_1d"], r["trend_state"], None,
                        in_scope=r["in_current_descriptive_scope"]) for t, r in gen.CUR.items()}
    change = mci.session_change(_snap("2026-11-06", rows), _snap("2026-11-05", gen.PREV))
    assert change["cohort"]["matched_with_momentum_both_sessions"] == 0
    assert change["changes"]["positive_momentum_share_pp"] is None
    assert change["changes"]["advance_ratio_pp"] is not None
