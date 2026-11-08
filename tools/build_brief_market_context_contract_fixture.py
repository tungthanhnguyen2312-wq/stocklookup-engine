"""Engine-generated contract fixture for brief_market_context/v1 (Engine -> Dashboard).

Every case runs the real production functions in order:
participation_snapshot -> session_change (via next_session_decision_brief._matched_cohort_change)
-> daily_integrated_decision_brief (what_changed_today + opportunity_sets)
-> ai_research_session_delivery.brief_market_context -> cockpit projection field.

Only the per-ticker descriptive inputs are synthetic and small. The committed fixture is checked
byte-for-byte against a fresh run (tests/test_brief_market_context_contract_fixture.py), and the
Dashboard keeps an identical copy that its CI compares with this repository's main. An incompatible
Engine change therefore fails a test on both sides instead of leaving a stale Dashboard fixture.

    python tools/build_brief_market_context_contract_fixture.py --write
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

FIXTURE_PATH = ROOT / "tests" / "fixtures" / "brief_market_context_contract_v1.json"
FIXTURE_CONTRACT = "brief_market_context_contract_fixture/v1"
COCKPIT_SCHEMA = "current_decision_cockpit_projection/v2"
ADJACENT = {"is_immediate_previous_completed_session": True}


def _rec(ret: float, trend: str | None, mom: float | None, *, in_scope: bool = True) -> dict[str, Any]:
    return {"in_current_descriptive_scope": in_scope, "trend_state": trend,
            "technical_features": {"status": "SHADOW_ONLY", "is_current_session": True,
                                   "values": {"return_1d": ret, "momentum_20d": mom}}}


def _descriptive(session: str, rows: Mapping[str, Any], *, breadth_count_delta: int = 0) -> dict[str, Any]:
    scoped = [r for r in rows.values() if r["in_current_descriptive_scope"]]
    return {"artifact_identity": f"market_wide_current_descriptive_research:fixture-{session}", "session": session,
            "market_breadth": {"same_session_technical_feature_available_count": len(scoped) + breadth_count_delta},
            "records": dict(rows)}


# Previous session: 5 in scope (OLD leaves next session), OUT is out of scope.
PREV = {"AAA": _rec(-1.0, "AT_OR_BELOW_MA20", -2.0), "BBB": _rec(-0.5, "AT_OR_BELOW_MA20", -1.0),
        "CCC": _rec(0.4, "ABOVE_MA20", 1.0), "DDD": _rec(-0.2, "ABOVE_MA20", -1.0),
        "OLD": _rec(1.0, "ABOVE_MA20", 1.0)}
# Current session: AAA/BBB cross above MA20 and advance; NEW joins; DDD falls below.
CUR = {"AAA": _rec(2.0, "ABOVE_MA20", -1.0), "BBB": _rec(1.0, "ABOVE_MA20", 1.0),
       "CCC": _rec(0.1, "ABOVE_MA20", 1.0), "DDD": _rec(-0.3, "AT_OR_BELOW_MA20", -1.0),
       "NEW": _rec(-3.0, "AT_OR_BELOW_MA20", -1.0),
       "OUT": _rec(5.0, "ABOVE_MA20", 1.0, in_scope=False)}


def _gated_record(ticker: str) -> dict[str, Any]:
    return {"ticker": ticker, "research_action_posture": "WAIT_FOR_CONFIRMATION",
            "posture_condition_class": "BEARISH_BREADTH_NARROWS_FRESH_ENTRY", "tactical_phase": "BREAKOUT",
            "trigger": {"trigger_state": "TRIGGERED", "distance_to_trigger_pct": 0.0},
            "invalidation": {"invalidation_level": 9.0, "invalidation_method": "PRIOR_SWING_LOW",
                             "distance_to_invalidation_pct": -6.2, "horizon": "SWING"},
            "market_sector_context": {"market_regime": "DETERIORATING_BREADTH"},
            "decision_identity": f"fixture-decision:{ticker}"}


def _cockpit(session: str, *, change: Mapping[str, Any] | None, records: Mapping[str, Any] | None = None) -> dict[str, Any]:
    from ai_research_session_delivery import brief_market_context
    from stocklookup_core.decision import daily_integrated_decision_brief as dib
    market_transition = {"availability": "AVAILABLE", "matched_cohort": change} if change is not None else None
    posture = {"availability": "AVAILABLE", "records": {"AAA": {"transition": "POSTURE_UNCHANGED"}}}
    brief = {"contract_version": dib.CONTRACT_VERSION, "session": session,
             "artifact_identity": "daily_integrated_decision_brief/v1:contract-fixture",
             "what_changed_today": dib.build_what_changed_today(posture_transition=posture, market_transition=market_transition,
                                                                sector_transition=None, watchlist_tickers=[]),
             "opportunity_sets": dib.build_opportunity_sets(dict(records or {"HPG": {"ticker": "HPG", "research_action_posture": "HOLD"}}), None)}
    cockpit: dict[str, Any] = {"schema_version": COCKPIT_SCHEMA, "session": session}
    block = brief_market_context(brief)
    if block is not None:
        cockpit["brief_market_context_v1"] = block
    return cockpit


def _change(cur_s: str, cur: Mapping[str, Any], prev_s: str, prev: Mapping[str, Any] | None,
            metadata: Mapping[str, Any] | None = ADJACENT, *, cur_delta: int = 0) -> dict[str, Any]:
    from next_session_decision_brief import _matched_cohort_change
    from stocklookup_core.decision.market_close_intelligence import participation_snapshot, session_change
    if prev is None:
        current = participation_snapshot(session=cur_s, descriptive=_descriptive(cur_s, cur))
        return session_change(current, None, adjacency="REGISTRY_IMMEDIATE_PREVIOUS_COMPLETED_SESSION")
    return _matched_cohort_change(_descriptive(cur_s, cur, breadth_count_delta=cur_delta), _descriptive(prev_s, prev), metadata)


def build_cases() -> dict[str, Any]:
    flip = {t: _rec(-abs(r["technical_features"]["values"]["return_1d"]) or -1.0,
                    "AT_OR_BELOW_MA20" if r["trend_state"] == "ABOVE_MA20" else "AT_OR_BELOW_MA20",
                    r["technical_features"]["values"]["momentum_20d"], in_scope=r["in_current_descriptive_scope"])
            for t, r in CUR.items()}
    mixed = dict(CUR, AAA=_rec(-2.0, "ABOVE_MA20", -1.0), BBB=_rec(-1.0, "ABOVE_MA20", 1.0))
    asym_mom = dict(CUR, CCC=_rec(0.1, "ABOVE_MA20", None))           # momentum UNKNOWN only now
    ma20_unknown = dict(CUR, BBB=_rec(1.0, None, 1.0))                 # MA20 side UNKNOWN only now
    cases = {
        "adjacent_broadening_confirmed_with_churn": (
            "Registry-adjacent weekday pair; matched cohort of 4 with 1 ticker joining, 1 leaving and 1 out of scope.",
            _cockpit("2026-11-06", change=_change("2026-11-06", CUR, "2026-11-05", PREV))),
        "asymmetric_missing_momentum": (
            "CCC momentum is UNKNOWN in the current session only; momentum shares use the 3 tickers known in both.",
            _cockpit("2026-11-06", change=_change("2026-11-06", asym_mom, "2026-11-05", PREV))),
        "different_ma20_eligibility": (
            "BBB MA20 side is UNKNOWN in the current session only; MA20 shares and crossings use the 3 tickers known in both.",
            _cockpit("2026-11-06", change=_change("2026-11-06", ma20_unknown, "2026-11-05", PREV))),
        "registry_adjacent_calendar_separated": (
            "Real retained shape 2026-10-26 -> 2026-11-02: registry calls it immediate, four weekdays lie between.",
            _cockpit("2026-11-02", change=_change("2026-11-02", CUR, "2026-10-26", PREV))),
        "refuted_condition": (
            "Every matched ticker declines and falls below MA20; the published condition is REFUTED.",
            _cockpit("2026-11-06", change=_change("2026-11-06", flip, "2026-11-05", PREV))),
        "indeterminate_condition": (
            "Majority declines while the MA20 share rises; the condition is NEITHER_CONFIRMED_NOR_REFUTED.",
            _cockpit("2026-11-06", change=_change("2026-11-06", mixed, "2026-11-05", PREV))),
        "missing_previous_snapshot": (
            "No previous governed snapshot; the refusal reason is carried, no change is shown.",
            _cockpit("2026-11-06", change=_change("2026-11-06", CUR, "2026-11-05", None))),
        "cohort_reconciliation_mismatch": (
            "Current snapshot row count differs from its own market_breadth count; the comparison is refused.",
            _cockpit("2026-11-06", change=_change("2026-11-06", CUR, "2026-11-05", PREV, cur_delta=3))),
        "registry_gap_unverified_adjacency": (
            "Registry reports a gap of 2 completed sessions; adjacency is NON_ADJACENT.",
            _cockpit("2026-11-06", change=_change("2026-11-06", CUR, "2026-11-04", PREV,
                                                   {"is_immediate_previous_completed_session": False, "session_gap_trading_sessions": 2}))),
        "market_gated_entries": (
            "A fired, security-qualified breakout held by BEARISH_BREADTH_NARROWS_FRESH_ENTRY, beside an ordinary HOLD.",
            _cockpit("2026-11-02", change=_change("2026-11-02", CUR, "2026-10-26", PREV),
                     records={"MCP": _gated_record("MCP"), "HPG": {"ticker": "HPG", "research_action_posture": "HOLD"}})),
        "older_brief_without_new_fields": (
            "An older Brief carries neither field; the cockpit has no brief_market_context_v1 at all.",
            _cockpit("2026-11-06", change=None)),
    }
    return {name: {"description": desc, "cockpit": cockpit} for name, (desc, cockpit) in cases.items()}


def build_fixture() -> dict[str, Any]:
    cases = build_cases()
    canonical = json.dumps(cases, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return {"contract_version": FIXTURE_CONTRACT, "projection_contract": "brief_market_context/v1",
            "generated_by": "stocklookup-engine:tools/build_brief_market_context_contract_fixture.py",
            "cases_sha256": hashlib.sha256(canonical.encode("utf-8")).hexdigest(), "cases": cases}


def render(fixture: Mapping[str, Any]) -> bytes:
    return (json.dumps(fixture, ensure_ascii=False, sort_keys=True, indent=1) + "\n").encode("utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="rewrite the committed fixture")
    args = parser.parse_args()
    data = render(build_fixture())
    if args.write:
        FIXTURE_PATH.write_bytes(data)
        print(FIXTURE_PATH)
        return 0
    current = FIXTURE_PATH.read_bytes().replace(b"\r\n", b"\n") if FIXTURE_PATH.is_file() else b""
    print("FIXTURE_CURRENT" if current == data else "FIXTURE_STALE")
    return 0 if current == data else 1


if __name__ == "__main__":
    raise SystemExit(main())
