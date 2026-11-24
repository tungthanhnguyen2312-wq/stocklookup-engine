"""Owner Decision 1 (2026-11-24), HL-20261124-HOL-06. Synthetic numbers only."""
import copy

import pytest

from stocklookup_core.valuation import p3f_current_market_valuation as p3f
from stocklookup_core.valuation import current_research_valuation_context as context
from stocklookup_core.valuation.market_wide_current_valuation_input_scaleout import _build_metrics
from stocklookup_core.decision import integrated_investment_decision_product as iid
from test_p3f_current_market_valuation import _fact, _issuer, _price, _shares
from test_current_research_valuation_context import qualified_feature, valuation_record, market_cap_metric


def annual(facts, entity="corporate"):
    return p3f._evaluate_issuer(_issuer(entity=entity, facts=facts), price=_price(), shares=_shares())


def evaluated(facts, *, entity="corporate", features=None):
    formula = annual(facts, entity)
    record = valuation_record(market_cap_metric(1000))
    record["entity_class"] = entity
    for name in ("P/E", "P/E_TOTAL_INCLUDING_NCI"):
        if name not in formula["methods"]:
            continue
        m = formula["methods"][name]
        record["metrics"][name] = {**m, "status": "RESEARCH_USABLE" if m["status"] == "VALUATION_READY" else "BLOCKED",
            "p3f_method_status": m["status"], "blocked_reasons": m["blockers"]}
    return context.evaluate_ticker_valuation(ticker="AAA", feature_record=None, valuation_record=record,
        financial_analysis_record={"features": features or {}}, decision_session="2026-11-23")


@pytest.mark.parametrize("metric", ["attributable_net_income", "net_income_parent"])
def test_consolidated_parent_profit_is_headline_and_total_is_supplementary(metric):
    row = evaluated([_fact("net_income", 100), _fact(metric, 40)])
    summary, *_ = iid.evaluate_valuation_context(row, {})
    assert summary["pe_multiple"] == 25
    assert summary["pe_basis"]["earnings_attribution"] == "PARENT_ATTRIBUTABLE"
    assert summary["pe_basis"]["display_label"] == "P/E (LN cổ đông công ty mẹ, FY2024)"
    assert summary["pe_supplementary"]["value"] == 10
    assert summary["pe_supplementary"]["earnings_attribution"] == "TOTAL_INCLUDING_NCI"
    assert summary["pe_supplementary"]["display_label"] == "P/E toàn tập đoàn (FY2024)"


@pytest.mark.parametrize("parent", [None, "UNQUALIFIED", "WRONG_LINE"])
def test_total_never_satisfies_missing_or_unqualified_parent(parent):
    facts = [_fact("net_income", 100)]
    if parent:
        fact = _fact("attributable_net_income", 40)
        if parent == "UNQUALIFIED":
            fact["qualification_state"] = "CANDIDATE"
        else:
            fact["line_code"] = "60"
        facts.append(fact)
    row = evaluated(facts)
    row["pe"] = 10  # stale record-level total must not resurrect the headline
    summary, *_ = iid.evaluate_valuation_context(row, {})
    assert summary["pe_multiple"] is None
    assert summary["pe_basis"]["claim"] == "WITHHELD"
    assert "PARENT_PROFIT_NOT_QUALIFIED" in summary["pe_basis"]["blocker_reason_codes"]
    assert summary["pe_supplementary"]["value"] == 10


@pytest.mark.parametrize("scope", ["standalone", "separate"])
def test_standalone_total_equals_parent_is_explicit(scope):
    row = evaluated([{**_fact("net_income", 50), "statement_scope": scope}])
    summary, *_ = iid.evaluate_valuation_context(row, {})
    assert summary["pe_multiple"] == 20
    assert summary["pe_basis"]["earnings_attribution"] == "STANDALONE_TOTAL_EQUALS_PARENT"
    assert "riêng lẻ" in summary["pe_basis"]["display_label"]


@pytest.mark.parametrize("entity,metric", [("bank", "net_profit_parent"), ("securities", "profit_after_tax_parent")])
def test_sector_form_keeps_its_own_parent_line(entity, metric):
    assert annual([_fact(metric, 50)], entity)["methods"]["P/E"]["value"] == 20
    assert "PARENT_PROFIT_NOT_QUALIFIED" in annual([_fact("net_income", 50)], entity)["methods"]["P/E"]["blockers"]


def test_unmapped_insurance_form_stays_not_applicable():
    assert annual([_fact("net_income", 50)], "insurance")["methods"]["P/E"]["status"] == "NOT_APPLICABLE"


@pytest.mark.parametrize("value", [-40, 0])
def test_nonpositive_parent_is_not_meaningful_and_never_uses_positive_total(value):
    row = evaluated([_fact("net_income", 100), _fact("attributable_net_income", value)])
    assert row["methods"]["P/E"]["status"] == "PE_NOT_MEANINGFUL"
    assert iid.evaluate_valuation_context(row, {})[0]["pe_multiple"] is None


def test_latest_qualified_fy_parent_excludes_interim_and_unqualified_newer_fy():
    facts = [_fact("attributable_net_income", 10, "2024"), _fact("attributable_net_income", 20, "2025"),
             {**_fact("attributable_net_income", 30, "2026"), "qualification_state": "CANDIDATE"},
             {**_fact("attributable_net_income", 40, "2026-Q3"), "period_type": "quarterly"}]
    pe = annual(facts)["methods"]["P/E"]
    assert pe["value"] == 50 and pe["financial_period"] == "2025"


def test_parent_ttm_preferred_to_fy_and_total_ttm_never_used():
    facts = [_fact("attributable_net_income", 40)]
    row = evaluated(facts, features={"attributable_net_income_ttm": qualified_feature(100),
                                     "net_income_ttm": qualified_feature(500)})
    summary = iid.evaluate_valuation_context(row, {})[0]
    assert summary["pe_multiple"] == 10 and summary["pe_basis"]["method"] == "P/E_TTM"
    total_only = evaluated(facts, features={"net_income_ttm": qualified_feature(500)})
    assert iid.evaluate_valuation_context(total_only, {})[0]["pe_multiple"] == 25


def test_standalone_total_ttm_requires_its_own_explicit_scope():
    f = qualified_feature(100)
    row = evaluated([_fact("attributable_net_income", 40)], features={"net_income_ttm": {**f, "statement_scope": "standalone"}})
    assert row["methods"]["P/E_TTM"]["value"] == 10
    assert row["methods"]["P/E_TTM"]["earnings_attribution"] == "STANDALONE_TOTAL_EQUALS_PARENT"


def test_parent_ttm_currency_gate_is_preserved_and_fy_survives():
    row = evaluated([_fact("attributable_net_income", 40)],
                    features={"attributable_net_income_ttm": qualified_feature(100, currency="USD")})
    assert row["methods"]["P/E_TTM"]["status"] == "INPUT_BLOCKED"
    assert iid.evaluate_valuation_context(row, {})[0]["pe_multiple"] == 25


@pytest.mark.parametrize("value", [-100, 0])
def test_nonpositive_qualified_parent_ttm_does_not_revert_to_positive_fy(value):
    row = evaluated([_fact("attributable_net_income", 40)],
                    features={"attributable_net_income_ttm": qualified_feature(value)})
    summary = iid.evaluate_valuation_context(row, {})[0]
    assert summary["pe_multiple"] is None
    assert summary["pe_basis"]["status"] == "PE_NOT_MEANINGFUL"
    assert summary["pe_basis"]["method"] == "P/E_TTM"


def test_peer_percentile_excludes_withheld_total_and_standalone():
    rows = {f"P{i}": evaluated([_fact("attributable_net_income", 10 + i)]) for i in range(5)}
    rows["TOTAL"] = evaluated([_fact("net_income", 100)])
    rows["SOLO"] = evaluated([{**_fact("net_income", 100), "statement_scope": "standalone"}])
    result = context.attach_peer_relative(rows)
    assert result["P0"]["peer_relative"]["P/E"]["peer_count"] == 5
    assert result["TOTAL"]["peer_relative"]["P/E"]["percentile"] is None
    assert result["TOTAL"]["peer_relative"]["P/E_TOTAL_INCLUDING_NCI"]["percentile"] is None


def test_new_labels_survive_integrated_decision_and_daily_brief():
    from test_valuation_output_truthfulness import _decision
    from stocklookup_core.decision import daily_integrated_decision_brief as brief
    row = evaluated([_fact("net_income", 100)])
    decision = _decision(row)
    watch = brief.build_watchlist_record(ticker="HPG", current=decision, tactical_raw=None,
        sector_label=None, posture_transition_row=None)
    for key in ("pe_multiple", "pe_basis", "pe_supplementary"):
        assert watch["valuation"][key] == decision["valuation_context_summary"][key]


def test_source_mapping_carries_supplementary_without_fabricating_identity():
    price = {"status": "PRICE_READY", "value": 100, "currency": "VND", "session": "2026-11-23"}
    share = {"value": 10, "research_proxy_eligible": True, "share_concept": "ISSUED_SHARES"}
    facts = [_fact("net_income", 100), _fact("attributable_net_income", 40)]
    issuer = _issuer(facts=facts)
    snapshot = copy.deepcopy(issuer)
    metrics = _build_metrics(entity="corporate", price=price, share=share, financial={"calculation_grade": True}, issuer=issuer)
    assert metrics["P/E"]["value"] == 25
    assert metrics["P/E_TOTAL_INCLUDING_NCI"]["value"] == 10
    assert issuer == snapshot
