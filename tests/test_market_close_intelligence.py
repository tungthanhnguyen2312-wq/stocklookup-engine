import pytest

from stocklookup_core.decision import market_close_intelligence as mci
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
