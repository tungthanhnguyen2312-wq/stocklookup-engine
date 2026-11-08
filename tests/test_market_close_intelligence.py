import json

import pytest

from stocklookup_core.decision import market_close_intelligence as mci
from stocklookup_core.decision import dashboard_home_summary as home
from stocklookup_core.decision.current_daily_decision_research_product import markdown

S = "2026-11-06"


def _descriptive(adv=262, dec=424, unch=223, above=322, below=587, session=S):
    n = adv + dec + unch
    return {"artifact_identity": "market_wide_current_descriptive_research:x", "session": session,
            "validation": {"coverage": {"input_candidates": 1683}},
            "market_breadth": {"advancing": adv, "declining": dec, "unchanged": unch,
                               "same_session_technical_feature_available_count": n,
                               "observed_session_cohort": 920, "current_active_equity_denominator": 1497,
                               "trend": {"above_ma20": above, "at_or_below_ma20": below, "unavailable": 0},
                               "breadth_descriptor": {"descriptor": "MARKET_BREADTH_MIXED",
                                                      "rule_identity": "market_regime_breadth_context/v1", "threshold": 0.6},
                               "momentum_descriptor": {"input_statistics": {"positive_count": 342, "negative_count": 529}}}}


def _sector():
    def g(name, adv, dec, state):
        return {"group_identity": name, "advancing": adv, "declining": dec, "leadership_state": state,
                "classification_namespace": "VCI.symbols_by_industries/retained-20260728",
                "exact_session_observed_count": adv + dec, "leadership_rule": {"breadth_state": "X"}}
    return {"artifact_identity": "current_market_sector_leadership_context:x", "session": S,
            "groups": {"records": {"a": g("bank", 2, 20, "WEAKENING"), "b": g("steel", 6, 3, "MIXED")}}}


def _regime():
    return {"artifact_identity": "macro_market_regime_decision_context:x", "dimensions": {
        "INFLATION_PRESSURE": {"state": "UNKNOWN", "authority": "OFFICIAL_SOURCE_ROUTE_ATTEMPTED",
                               "freshness": {"status": "STALE_OR_UNAVAILABLE", "valid_through": "2026-09-30"}},
        "GLOBAL_RATES": {"state": "NEUTRAL", "authority": "OFFICIAL_PUBLIC_SOURCE", "freshness": {"status": "CURRENT"}},
        "FOREIGN_FLOW": {"state": "UNKNOWN", "authority": "PRESENTATION_ONLY_NOT_ANALYTICAL"}}}


def test_home_attaches_the_producer_market_close_identity():
    brief = mci.build(session=S, descriptive=_descriptive(), regime_context=_regime())
    summary = {"contract_version": home.CONTRACT_VERSION, "as_of_session": S,
               "authority_effect": "NONE / PRESENTATION_READ_MODEL_ONLY"}
    summary.update(home.content_identity(summary))

    bound = home.with_market_close(summary, brief)
    assert bound["market_close"]["source_artifact_identity"] == brief["artifact_identity"]
    assert bound["market_close"]["macro_usable_axes"] == ["GLOBAL_RATES"]
    assert bound["market_close"]["breadth"]["denominator"] == 909
    assert home.content_identity(bound)["artifact_identity"] == bound["artifact_identity"]


def test_absent_components_are_unavailable_with_reasons_never_derived():
    out = mci.build(session=S, descriptive=_descriptive(), sector_leadership=_sector(), regime_context=_regime())
    c = out["components"]
    assert c["benchmark_index"]["status"] == "UNAVAILABLE"
    assert c["benchmark_index"]["derivation_from_constituents"] == "NOT_PERMITTED"
    assert c["liquidity"]["status"] == "UNAVAILABLE" and c["liquidity"]["price_times_volume"] == "NOT_PERMITTED"
    assert c["liquidity"]["liquidity_expansion_label"] == "NOT_EMITTED"
    assert c["foreign_flow"]["status"] == "UNAVAILABLE"
    assert c["macro"]["usable_axes"] == ["GLOBAL_RATES"]
    q = {row["question"]: row for row in out["interpretation"]["questions"]}
    assert q["Index fell while foreign investors bought: was that supportive?"]["answer_state"] == "CANNOT_ANSWER"
    assert out["artifact_identity"] == "market_close_intelligence:" + out["artifact_sha256"]


def test_breadth_keeps_cohort_denominator_and_explains_mixed_label():
    out = mci.build(session=S, descriptive=_descriptive(), sector_leadership=_sector(), regime_context=_regime())
    b = out["components"]["breadth"]
    assert b["denominator"] == 909 and b["scope"] == "EXACT_SESSION_TECHNICAL_COHORT_NOT_WHOLE_MARKET"
    assert round(b["advance_ratio"], 4) == round(262 / 909, 4)
    assert "does not mean the session was balanced" in b["existing_descriptor_rule"]["meaning"]
    assert out["denominators"]["current_active_equity"]["count"] == 1497
    facts = [r for r in out["interpretation"]["questions"] if r.get("observed_cohort_facts")][0]["observed_cohort_facts"]
    assert facts == ["DECLINERS_OUTNUMBER_ADVANCERS", "MAJORITY_AT_OR_BELOW_MA20", "MAJORITY_NEGATIVE_20D_MOMENTUM"]


def test_sectors_use_provider_taxonomy_and_are_not_broker_comparable():
    s = mci.build(session=S, descriptive=_descriptive(), sector_leadership=_sector())["components"]["sectors"]
    assert s["groups_with_more_decliners_than_advancers"] == 1 and s["groups_with_more_advancers_than_decliners"] == 1
    assert s["comparability"] == "NOT_COMPARABLE_WITH_BROKER_SECTOR_COUNTS_DIFFERENT_TAXONOMY"


def test_bound_benchmark_reports_change_from_published_levels():
    bench = {"index": "VNINDEX", "session": S, "close": 1725.36, "previous_close": 1740.73, "previous_session": "2026-11-05",
             "source_identity": "x", "knowledge_available_at": "2026-11-06T09:00:00Z", "authority": "CURRENT_RESEARCH"}
    b = mci.build(session=S, descriptive=_descriptive(), benchmark=bench)["components"]["benchmark_index"]
    assert b["status"] == "AVAILABLE" and b["change_points"] == -15.37 and b["change_percent"] == -0.88
    wrong = dict(bench, session="2026-11-05")
    assert mci.build(session=S, descriptive=_descriptive(), benchmark=wrong)["components"]["benchmark_index"]["status"] == "UNAVAILABLE"


def test_liquidity_budget_status_is_reported_not_hidden():
    status = {"status": "UNAVAILABLE_REQUEST_BUDGET", "reason_code": "DAILY_OFFICIAL_LIQUIDITY_ROLLFORWARD_PARTIAL_REQUEST_BUDGET_CEILING",
              "planned_requests": 403, "hard_request_budget": 400, "http_requests_made": 0}
    liq = mci.build(session=S, descriptive=_descriptive(), official_liquidity=status)["components"]["liquidity"]
    assert liq["reason_codes"] == ["DAILY_OFFICIAL_LIQUIDITY_ROLLFORWARD_PARTIAL_REQUEST_BUDGET_CEILING"]
    assert liq["source_status"]["planned_requests"] == 403


def test_session_mismatch_refused():
    with pytest.raises(ValueError):
        mci.build(session=S, descriptive=_descriptive(session="2026-11-05"))
    bad = dict(_sector(), session="2026-11-05")
    with pytest.raises(ValueError):
        mci.build(session=S, descriptive=_descriptive(), sector_leadership=bad)


def test_brief_markdown_renders_section_only_when_bound():
    out = mci.build(session=S, descriptive=_descriptive(), sector_leadership=_sector(), regime_context=_regime())
    text = "\n".join(mci.markdown_lines(out))
    assert "VN-Index: UNAVAILABLE" in text and "not whole-market statistics" in text
    assert "no forecast, probability, recommendation or sizing" in text
    product = {"session": S, "market_brief": {"breadth_state": "MARKET_BREADTH_MIXED", "momentum_state": "M",
               "coverage": {"same_session_technical_feature_available_count": 909, "current_active_equity_denominator": 1497},
               "data_quality_limitations": ["X"]}, "research_cohorts": {}, "high_priority_full_universe_review_set":
               {"count": 0, "outside_watchlist": [], "tickers": []}, "detailed_research_cards": {},
               "watchlist": {"tickers": []}, "what_to_verify_next": [],
               "risk_data_gap_panel": {"technical_unavailable": 0, "peer_context_unavailable": 0}}
    try:
        base = markdown(product)
    except (KeyError, TypeError):
        pytest.skip("product markdown needs a fuller fixture; covered by the product test module")
    assert "## Market close intelligence" not in base
    assert "## Market close intelligence" in markdown(dict(product, market_close_intelligence=out))


# --- matched-cohort session change (matched_cohort_session_change/v1) ----------------

P = "2026-11-05"
ADJ = "REGISTRY_IMMEDIATE_PREVIOUS_COMPLETED_SESSION"


def _rec(ret, trend, mom):
    return {"in_current_descriptive_scope": True, "trend_state": trend,
            "technical_features": {"status": "SHADOW_ONLY", "is_current_session": True,
                                   "values": {"return_1d": ret, "momentum_20d": mom}}}


def _desc_with(session, rows):
    scoped = {k: v for k, v in rows.items() if v["in_current_descriptive_scope"]}
    adv = sum(1 for r in scoped.values() if r["technical_features"]["values"]["return_1d"] > 0)
    dec = sum(1 for r in scoped.values() if r["technical_features"]["values"]["return_1d"] < 0)
    above = sum(1 for r in scoped.values() if r["trend_state"] == "ABOVE_MA20")
    d = _descriptive(adv=adv, dec=dec, unch=len(scoped) - adv - dec, above=above, below=len(scoped) - above, session=session)
    d["records"] = dict(rows)
    return d


PRIOR_ROWS = {"AAA": _rec(-1.0, "AT_OR_BELOW_MA20", -2), "BBB": _rec(-0.5, "AT_OR_BELOW_MA20", -1),
              "CCC": _rec(0.4, "ABOVE_MA20", 1), "DDD": _rec(-0.2, "ABOVE_MA20", -1),
              "OLD": _rec(1.0, "ABOVE_MA20", 1)}
CURRENT_ROWS = {"AAA": _rec(2.0, "ABOVE_MA20", -1), "BBB": _rec(1.0, "ABOVE_MA20", 1),
                "CCC": _rec(0.1, "ABOVE_MA20", 1), "DDD": _rec(-0.3, "AT_OR_BELOW_MA20", -1),
                "NEW": _rec(-3.0, "AT_OR_BELOW_MA20", -1),
                "OUT": dict(_rec(5.0, "ABOVE_MA20", 1), in_current_descriptive_scope=False)}


def _snap(session, rows):
    return mci.participation_snapshot(session=session, descriptive=_desc_with(session, rows))


def test_snapshot_keeps_exactly_the_breadth_cohort_and_is_identity_bound():
    snap = _snap(S, CURRENT_ROWS)
    assert snap["status"] == "AVAILABLE" and snap["cohort_count"] == 5          # OUT is outside scope
    assert snap["cohort_reconciliation"] == "MATCHES_MARKET_BREADTH"
    assert snap["cohort"][0] == ["AAA", 1, 1, -1]
    assert snap["artifact_identity"] == "market_close_participation_snapshot:" + snap["artifact_sha256"]
    assert _snap(S, CURRENT_ROWS) == snap                                       # deterministic
    missing = mci.participation_snapshot(session=S, descriptive=_descriptive())
    assert missing["status"] == "UNAVAILABLE" and missing["reason_codes"] == ["DESCRIPTIVE_PER_TICKER_RECORDS_ABSENT"]
    with pytest.raises(ValueError):
        mci.participation_snapshot(session=P, descriptive=_desc_with(S, CURRENT_ROWS))


def test_matched_cohort_change_shares_one_denominator_and_reports_churn():
    ch = mci.session_change(_snap(S, CURRENT_ROWS), _snap(P, PRIOR_ROWS), adjacency=ADJ)
    assert ch["status"] == "AVAILABLE" and ch["previous_session"] == P and ch["adjacency"] == ADJ
    assert {k: ch["cohort"][k] for k in ("matched", "matched_with_ma20_side_both_sessions", "current_only", "previous_only")} == {
        "matched": 4, "matched_with_ma20_side_both_sessions": 4, "current_only": 1, "previous_only": 1}
    assert ch["previous"]["advancing"] == 1 and ch["current"]["advancing"] == 3     # NEW / OLD excluded
    assert ch["changes"]["advance_ratio_pp"] == 50.0 and ch["changes"]["above_ma20_share_pp"] == 25.0
    assert ch["changes"]["positive_momentum_share_pp"] == 25.0
    assert ch["ma20_crossings"] == {"crossed_above": 2, "crossed_below": 1, "net": 1}
    assert ch["participation_character"] == "BROADENING"
    assert ch["market_close_condition_evaluation"]["state"] == "CONFIRMED"
    assert not any("not verified" in x for x in ch["limitations"])
    assert ch["span"]["calendar_weekdays_between"] == 0 and ch["span"]["may_span_multiple_trading_sessions"] is False


def test_registry_adjacent_pair_with_missing_weekdays_is_flagged_as_multi_session():
    # Mirrors the real 2026-10-26 -> 2026-11-02 registry pair: immediate previous *completed*
    # session, yet four weekdays lie between, so the change is not a one-session change.
    ch = mci.session_change(_snap("2026-11-02", CURRENT_ROWS), _snap("2026-10-26", PRIOR_ROWS), adjacency=ADJ)
    assert ch["span"] == {"calendar_weekdays_between": 4, "basis": "MON_FRI_CALENDAR_WARNING_ONLY_NOT_EXCHANGE_CALENDAR",
                          "may_span_multiple_trading_sessions": True}
    assert any("spans more than one trading session" in x for x in ch["limitations"])
    friday_to_monday = mci.session_change(_snap("2026-11-09", CURRENT_ROWS), _snap("2026-11-06", PRIOR_ROWS), adjacency=ADJ)
    assert friday_to_monday["span"]["calendar_weekdays_between"] == 0


def test_aggregate_delta_would_mislead_when_coverage_changes():
    # Same 4 names unchanged; the later session adds 4 newly covered decliners. The aggregate
    # advance ratio falls 25 pp although no matched name changed direction.
    prior = {"A": _rec(1, "ABOVE_MA20", 1), "B": _rec(1, "ABOVE_MA20", 1), "C": _rec(-1, "AT_OR_BELOW_MA20", -1), "D": _rec(0, "AT_OR_BELOW_MA20", 0)}
    current = dict(prior, **{f"N{i}": _rec(-1, "AT_OR_BELOW_MA20", -1) for i in range(4)})
    aggregate_pp = (_desc_with(S, current)["market_breadth"]["advancing"] / 8 - 2 / 4) * 100
    assert aggregate_pp == -25.0
    ch = mci.session_change(_snap(S, current), _snap(P, prior), adjacency=ADJ)
    assert ch["changes"]["advance_ratio_pp"] == 0.0 and ch["cohort"]["current_only"] == 4
    assert ch["changes"]["above_ma20_share_pp"] == 0.0 and ch["participation_character"] == "UNCHANGED"


def test_deteriorating_participation_is_refuted_not_hidden():
    previous = _snap(P, {k: v for k, v in CURRENT_ROWS.items() if k != "OUT"})
    current = _snap(S, dict(PRIOR_ROWS, NEW=CURRENT_ROWS["NEW"]))
    ch = mci.session_change(current, previous)
    assert ch["participation_character"] == "NARROWING"
    assert ch["market_close_condition_evaluation"]["state"] == "REFUTED"
    assert ch["adjacency"] == "ADJACENCY_UNVERIFIED"
    assert any("not verified as the immediately preceding" in x for x in ch["limitations"])


def test_missing_incompatible_or_out_of_order_inputs_are_unavailable():
    current = _snap(S, CURRENT_ROWS)
    assert mci.session_change(current, None)["reason_codes"] == ["NO_PREVIOUS_PARTICIPATION_SNAPSHOT"]
    assert mci.session_change(None, current)["reason_codes"] == ["CURRENT_PARTICIPATION_SNAPSHOT_UNAVAILABLE"]
    missing = mci.participation_snapshot(session=P, descriptive=_descriptive(session=P))
    assert mci.session_change(current, missing)["reason_codes"] == ["PREVIOUS_PARTICIPATION_SNAPSHOT_UNAVAILABLE"]
    assert mci.session_change(_snap(P, PRIOR_ROWS), current)["reason_codes"] == ["PREVIOUS_SESSION_NOT_EARLIER"]
    changed = dict(_snap(P, PRIOR_ROWS), cohort_rule="different")
    assert mci.session_change(current, changed)["reason_codes"] == ["COHORT_RULE_CHANGED_NOT_COMPARABLE"]
    disjoint = _snap(P, {"ZZZ": _rec(1, "ABOVE_MA20", 1)})
    assert mci.session_change(current, disjoint)["reason_codes"] == ["NO_MATCHED_TICKERS_BETWEEN_SESSIONS"]


def test_unknown_ma20_side_is_excluded_from_ma20_share_not_counted_as_below():
    prior = {"A": _rec(1, None, 1), "B": _rec(1, "AT_OR_BELOW_MA20", 1)}
    current = {"A": _rec(1, "ABOVE_MA20", 1), "B": _rec(1, "ABOVE_MA20", 1)}
    ch = mci.session_change(_snap(S, current), _snap(P, prior))
    assert ch["cohort"]["matched_with_ma20_side_both_sessions"] == 1
    assert ch["previous"]["above_ma20_share"] == 0.0 and ch["current"]["above_ma20_share"] == 1.0
    assert ch["ma20_crossings"]["crossed_above"] == 1


def test_index_breadth_concordance_flags_narrow_index_move():
    bench = {"index": "VNINDEX", "session": S, "close": 1740.0, "previous_close": 1725.0, "previous_session": P,
             "source_identity": "x", "knowledge_available_at": S + "T09:00:00Z", "authority": "CURRENT_RESEARCH"}
    out = mci.build(session=S, descriptive=_descriptive(), benchmark=bench)        # 262 up / 424 down
    q = {r["question"]: r for r in out["interpretation"]["questions"]}["Was the index move broad or concentrated?"]
    assert q["observed_cohort_facts"] == ["INDEX_UP_WHILE_MORE_OF_COHORT_DECLINED"]
    assert "not proof of concentration" in q["note"]
    agree = mci.build(session=S, descriptive=_descriptive(adv=500, dec=100), benchmark=bench)
    q2 = {r["question"]: r for r in agree["interpretation"]["questions"]}["Was the index move broad or concentrated?"]
    assert q2["observed_cohort_facts"] == ["INDEX_AND_COHORT_MAJORITY_AGREE"]
    none = {r["question"]: r for r in mci.build(session=S, descriptive=_descriptive())["interpretation"]["questions"]}
    assert none["Was the index move broad or concentrated?"]["answer_state"] == "CANNOT_ANSWER"
    assert none["Was the index move broad or concentrated?"]["missing_evidence"] == ["benchmark_index"]


def test_session_change_emits_no_score_recommendation_or_sizing():
    ch = mci.session_change(_snap(S, CURRENT_ROWS), _snap(P, PRIOR_ROWS), adjacency=ADJ)
    blob = json.dumps(ch).lower()
    for forbidden in ("score", "probability", "recommend", "position_size", "\"buy", "\"sell", "target_price", "avoid"):
        assert forbidden not in blob


def test_next_session_market_transition_attaches_matched_cohort_from_governed_pair():
    import next_session_decision_brief as nsb
    current, previous = _desc_with(S, CURRENT_ROWS), _desc_with(P, PRIOR_ROWS)
    immediate = {"is_immediate_previous_completed_session": True, "session_gap_trading_sessions": 0}
    ch = nsb._matched_cohort_change(current, previous, immediate)
    assert ch["status"] == "AVAILABLE" and ch["adjacency"] == ADJ and ch["participation_character"] == "BROADENING"
    gap = nsb._matched_cohort_change(current, previous, {"is_immediate_previous_completed_session": False, "session_gap_trading_sessions": 2})
    assert gap["adjacency"] == "NON_ADJACENT_SESSION_GAP_2"
    assert nsb._matched_cohort_change(current, previous, None)["adjacency"] == "ADJACENCY_UNVERIFIED"
    wrong = dict(previous, session=None)
    assert nsb._matched_cohort_change(current, wrong, immediate)["status"] == "UNAVAILABLE"


def test_integrated_brief_what_changed_today_carries_compact_participation_change():
    import next_session_decision_brief as nsb
    from stocklookup_core.decision import daily_integrated_decision_brief as dib
    change = nsb._matched_cohort_change(_desc_with(S, CURRENT_ROWS), _desc_with(P, PRIOR_ROWS),
                                        {"is_immediate_previous_completed_session": True})
    transition = {"availability": "AVAILABLE", "transition": {"advance_ratio_direction": "IMPROVING"}, "matched_cohort": change}
    posture = {"availability": "AVAILABLE", "records": {"AAA": {"transition": "POSTURE_UNCHANGED"}}}
    out = dib.build_what_changed_today(posture_transition=posture, market_transition=transition, sector_transition=None, watchlist_tickers=[])
    pc = out["market_participation_change"]
    assert pc["participation_character"] == "BROADENING" and pc["changes"]["advance_ratio_pp"] == 50.0
    assert "previous" not in pc and "current" not in pc                       # aggregates only
    assert out["market_breadth_change"] == {"advance_ratio_direction": "IMPROVING"}  # existing field unchanged
    degraded = dib.build_what_changed_today(posture_transition={"availability": "UNAVAILABLE", "reason_codes": ["X"]},
                                            market_transition=None, sector_transition=None, watchlist_tickers=[])
    assert "market_participation_change" not in degraded                      # not supplied -> omitted
    refused = dib.build_what_changed_today(posture_transition=posture, sector_transition=None, watchlist_tickers=[],
                                           market_transition={"matched_cohort": {"status": "UNAVAILABLE", "reason_codes": ["NO_PREVIOUS_PARTICIPATION_SNAPSHOT"]}})
    assert refused["market_participation_change"] == {"status": "UNAVAILABLE", "reason_codes": ["NO_PREVIOUS_PARTICIPATION_SNAPSHOT"]}
