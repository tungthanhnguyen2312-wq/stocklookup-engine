"""CURRENT_RESEARCH_VALUATION_OUTPUT_TRUTHFULNESS_CORRECTIVE regression tests.

Fixtures mirror the retained 2026-11-20 HPG / POW / PAN valuation records (method status,
period basis, financial-input lineage, peer cohorts). They pin presentation truthfulness only:
which method a headline multiple is, its denominator period and limits, and which cohorts drove
a peer verdict. They never assert a replacement TTM value.
"""
from __future__ import annotations

import copy

import pytest

from stocklookup_core.decision import daily_integrated_decision_brief as brief
from stocklookup_core.decision import integrated_investment_decision_product as iidp
from stocklookup_core.financial import fundamental_signal_consumption_contract as signals
from stocklookup_core.valuation import current_research_valuation_context as valuation

SESSION = "2026-11-20"
TOTAL_EQUITY = "TOTAL_OWNERS_EQUITY_AS_REPORTED_INCLUDES_NCI_WHERE_PRESENT"


def _annual_input(metric: str, evidence_id: str) -> dict:
    return {"canonical_metric": metric, "currency": "VND", "period_end": "2024-12-31", "period_type": "annual",
            "reporting_period": "2024", "statement_scope": "consolidated", "temporal_nature": "duration",
            "unit_scale": 1, "value": 1.0,
            "source_lineage": {"provider": "official_issuer_filing", "evidence_id": evidence_id}}


def _legacy(method_id: str, value: float, metric: str) -> dict:
    return {"method_id": method_id, "applicability": "APPLICABLE", "status": "RESEARCH_USABLE", "value": value,
            "period_basis": "2024", "formula": f"market_cap / {metric}", "price_session": SESSION,
            "share_basis": "CURRENT_SHARE_RESEARCH_PROXY", "share_identity": "ISSUED_SHARES",
            "financial_inputs": [_annual_input(metric, f"ev-{metric}")], "blocker_reason_codes": []}


def _blocked_ttm(method_id: str) -> dict:
    return {"method_id": method_id, "applicability": "APPLICABLE", "status": "INPUT_BLOCKED", "value": None,
            "period_basis": "TTM_SUM", "blocker_reason_codes": ["TTM_INPUT_UNAVAILABLE"]}


def _usable_ttm(method_id: str, value: float) -> dict:
    return {"method_id": method_id, "applicability": "APPLICABLE", "status": "RESEARCH_USABLE", "value": value,
            "period_basis": "TTM_SUM", "ttm_periods": ["2025-Q4", "2026-Q1", "2026-Q2", "2026-Q3"],
            "ttm_feature_id": "net_income_ttm", "ttm_provider": "VCI", "ttm_input_source": "NEW_QUALIFIED_TTM_SELECTED",
            "denominator_feature": "net_income_ttm_sum", "share_basis": "CURRENT_SHARE_RESEARCH_PROXY",
            "limitations": ["CURRENT_RESEARCH_ONLY"], "blocker_reason_codes": []}


def _research_pb(value: float) -> dict:
    return {"method_id": "P/B_CURRENT_RESEARCH", "applicability": "APPLICABLE", "status": "RESEARCH_USABLE",
            "value": value, "period_basis": "POINT_IN_TIME_BALANCE_SHEET", "input_periods": ["2026-Q1"],
            "equity_definition": TOTAL_EQUITY, "statement_scope": "consolidated",
            "ttm_compatibility_class": "VCI_TOTAL_OWNERS_EQUITY_CURRENT_RESEARCH:consolidated",
            "share_basis": "CURRENT_SHARE_RESEARCH_PROXY",
            "limitations": ["CURRENT_RESEARCH_ONLY", "NCI_NOT_DEDUCTED"]}


def _peer(percentile: float, count: int, period: str, *, compatibility=None) -> dict:
    return {"status": "READY_RESEARCH_ONLY", "percentile": percentile, "peer_count": count,
            "basis": {"period_basis": period, "compatibility_class": compatibility}}


def _record(*, pe: float, ps: float, pb_research: float, relative_state: str, peers: dict) -> dict:
    return {
        "entity_class": "corporate", "share_basis": "CURRENT_SHARE_RESEARCH_PROXY",
        "relative_research_state": relative_state,
        "methods": {
            "P/E_TTM": _blocked_ttm("P/E_TTM"), "P/S_TTM": _blocked_ttm("P/S_TTM"),
            "P/E": _legacy("P/E", pe, "net_income"), "P/S": _legacy("P/S", ps, "revenue"),
            "P/B": _legacy("P/B", 1.0, "shareholders_equity"),
            "P/B_CURRENT_RESEARCH": _research_pb(pb_research),
            "market_cap": {"method_id": "market_cap", "status": "RESEARCH_USABLE", "value": 1e14},
        },
        "peer_relative": {**peers, "market_cap": _peer(0.9, 792, "EXISTING_CURRENT_VALUATION_METHOD")},
        "denominator_integrity": {"multiples": [
            {"method_id": "P/E", "status": "UNKNOWN", "strict_valuation_use": "STRICT_VALUATION_QUARANTINED",
             "reason_codes": ["ARITHMETIC_INPUT_INSUFFICIENT"]}]},
    }


def hpg():
    return _record(pe=14.364250010994823, ps=1.2434444924910475, pb_research=1.2352011067290192,
                   relative_state="IN_LINE_RELATIVE_RESEARCH",
                   peers={"P/B": _peer(0.7, 5, "2024"), "P/S": _peer(0.3, 5, "2024"),
                          "P/B_CURRENT_RESEARCH": _peer(0.73, 348, "POINT_IN_TIME_BALANCE_SHEET",
                                                        compatibility="VCI_TOTAL_OWNERS_EQUITY_CURRENT_RESEARCH:consolidated")})


def pow_():
    return _record(pe=33.68359155430105, ps=1.3463617784304152, pb_research=0.988060654565531,
                   relative_state="IN_LINE_RELATIVE_RESEARCH",
                   peers={"P/B": _peer(0.5, 5, "2024"), "P/S": _peer(0.5, 5, "2024")})


def pan():
    return _record(pe=3.447360346069988, ps=0.24863401983490957, pb_research=0.41762279074491815,
                   relative_state="ATTRACTIVE_RELATIVE_RESEARCH",
                   peers={"P/B": _peer(0.1, 5, "2024"), "P/S": _peer(0.1, 5, "2024"), "EV/Sales": _peer(0.1, 5, "2024"),
                          "P/B_CURRENT_RESEARCH": _peer(0.237, 348, "POINT_IN_TIME_BALANCE_SHEET",
                                                        compatibility="VCI_TOTAL_OWNERS_EQUITY_CURRENT_RESEARCH:consolidated")})


def _summary(record, session=SESSION):
    return iidp.evaluate_valuation_context(record, {}, decision_session=session)


@pytest.mark.parametrize("make, pe, ps", [(hpg, 14.364250010994823, 1.2434444924910475),
                                          (pow_, 33.68359155430105, 1.3463617784304152)])
def test_annual_denominator_with_current_price_is_labelled_historical_not_ttm(make, pe, ps):
    summary, *_ = _summary(make())
    # The reported value stays visible and unchanged; only its basis becomes explicit.
    assert summary["pe_multiple"] == pe and summary["ps_multiple"] == ps
    for key, metric in (("pe_basis", "net_income"), ("ps_basis", "revenue")):
        basis = summary[key]
        assert basis["claim"] == "HISTORICAL_DENOMINATOR_RESEARCH_CONTEXT_NOT_CURRENT_TTM"
        assert basis["denominator_class"] == "ANNUAL_REPORTED_PERIOD"
        assert basis["denominator_periods"] == ["2024"] and basis["denominator_period_end"] == "2024-12-31"
        assert basis["denominator_metrics"] == [metric] and basis["statement_scopes"] == ["consolidated"]
        assert basis["price_session"] == SESSION
        assert basis["denominator_freshness"]["freshness_status"] == "STALE_BUT_RESEARCH_USABLE"
        assert basis["denominator_freshness"]["price_session_does_not_set_financial_freshness"] is True
        assert {"DENOMINATOR_NOT_TTM", "CURRENT_PRICE_OVER_HISTORICAL_PERIOD_DENOMINATOR",
                "DENOMINATOR_PERIOD_STALE_BUT_RESEARCH_USABLE"} <= set(basis["limitations"])
        assert basis["source_lineage"][0]["provider"] == "official_issuer_filing"
    assert summary["pe_basis"]["method"] == "P/E" and summary["ps_basis"]["method"] == "P/S"
    assert summary["pe_basis"]["alternative_methods"]["P/E_TTM"] == {
        "status": "INPUT_BLOCKED", "period_basis": "TTM_SUM", "blocker_reason_codes": ["TTM_INPUT_UNAVAILABLE"]}
    assert summary["pe_basis"]["integrity"]["strict_valuation_use"] == "STRICT_VALUATION_QUARANTINED"


def test_usable_ttm_method_is_the_headline_and_is_never_hidden_by_a_blocked_existing_method():
    record = hpg()
    record["methods"]["P/E_TTM"] = _usable_ttm("P/E_TTM", 9.5)
    summary, *_ = _summary(record)
    assert summary["pe_multiple"] == 9.5
    assert summary["pe_basis"]["method"] == "P/E_TTM"
    assert summary["pe_basis"]["claim"] == "CURRENT_RESEARCH_TTM_MULTIPLE"
    assert summary["pe_basis"]["denominator_class"] == "TTM_SUM"
    assert summary["pe_basis"]["alternative_methods"]["P/E"]["period_basis"] == "2024"
    # Before the corrective a blocked existing P/E dict masked a usable TTM method entirely.
    record["methods"]["P/E"] = {"method_id": "P/E", "status": "INPUT_BLOCKED", "value": None,
                                "blocker_reason_codes": ["VALUATION_INPUT_BLOCKED"]}
    masked, *_ = _summary(record)
    assert masked["pe_multiple"] == 9.5 and masked["pe_basis"]["method"] == "P/E_TTM"


def test_both_methods_blocked_keep_no_value_and_no_basis_claim():
    record = hpg()
    record["methods"]["P/E"] = {"method_id": "P/E", "status": "INPUT_BLOCKED", "value": None}
    summary, *_ = _summary(record)
    assert summary["pe_multiple"] is None
    assert summary["pe_basis"] == {"method": None, "claim": None}


def test_missing_period_metadata_is_explicitly_unspecified():
    record = hpg()
    record["methods"]["P/E"] = {"method_id": "P/E", "status": "RESEARCH_USABLE", "value": 12.0,
                                "period_basis": "EXISTING_CURRENT_VALUATION_METHOD", "price_session": SESSION}
    summary, *_ = _summary(record)
    basis = summary["pe_basis"]
    assert summary["pe_multiple"] == 12.0
    assert basis["claim"] == "DENOMINATOR_PERIOD_UNSPECIFIED_NOT_TTM"
    assert basis["denominator_class"] == "PERIOD_UNSPECIFIED" and basis["denominator_periods"] == []
    assert {"DENOMINATOR_NOT_TTM", "DENOMINATOR_PERIOD_UNSPECIFIED"} <= set(basis["limitations"])
    assert basis["denominator_freshness"]["freshness_status"] == "UNAVAILABLE"


def test_compact_record_without_methods_names_the_unretained_basis():
    summary, *_ = _summary({"pe": 10.0, "research_usable": True})
    assert summary["pe_multiple"] == 10.0
    assert summary["pe_basis"]["claim"] == "METHOD_AND_DENOMINATOR_PERIOD_NOT_RETAINED"


def test_pan_total_equity_peer_verdict_is_qualified_not_changed():
    summary, supports, counters, uncertainties = _summary(pan())
    # The producer's verdict and the dependent policy codes are passed through unchanged.
    assert summary["peer_relative_state"] == "CHEAP_VS_PEERS"
    assert supports == ["ATTRACTIVE_RELATIVE_RESEARCH_PEER_VALUATION"] and counters == []
    assert "P_B_IS_RESEARCH_TOTAL_EQUITY_NCI_NOT_DEDUCTED_NOT_COMMON_SHAREHOLDER" in uncertainties
    assert summary["pb_basis"]["equity_definition"] == TOTAL_EQUITY
    drivers = {row["method"]: row for row in summary["peer_relative_drivers"]}
    assert set(drivers) == {"P/B", "P/S", "EV/Sales", "P/B_CURRENT_RESEARCH"}
    assert drivers["P/B_CURRENT_RESEARCH"]["equity_definition"] == TOTAL_EQUITY
    assert drivers["P/B_CURRENT_RESEARCH"]["peer_count"] == 348
    assert drivers["P/B"]["period_basis"] == "2024" and drivers["P/B"]["peer_count"] == 5
    assert set(summary["peer_relative_qualifications"]) == {
        "TOTAL_EQUITY_PB_NCI_NOT_DEDUCTED_NOT_COMMON_SHAREHOLDER_RELATIVE",
        "ANNUAL_REPORTED_PERIOD_DENOMINATOR_COHORT", "PEER_COHORT_NOT_INDUSTRY_MATCHED"}


def test_verdict_resting_only_on_annual_cohorts_says_so_and_market_cap_never_drives():
    record = pan()
    del record["peer_relative"]["P/B_CURRENT_RESEARCH"]
    summary, *_ = _summary(record)
    assert summary["peer_relative_state"] == "CHEAP_VS_PEERS"
    assert "market_cap" not in {row["method"] for row in summary["peer_relative_drivers"]}
    assert "VERDICT_RESTS_ONLY_ON_ANNUAL_REPORTED_PERIOD_DENOMINATORS" in summary["peer_relative_qualifications"]
    assert "TOTAL_EQUITY_PB_NCI_NOT_DEDUCTED_NOT_COMMON_SHAREHOLDER_RELATIVE" not in summary["peer_relative_qualifications"]


def test_attach_peer_relative_records_an_industry_cohort_only_when_one_keyed_the_comparison():
    def rows():
        return {f"T{i}": {"entity_class": "corporate", "methods": {"P/B_CURRENT_RESEARCH": {
            **_research_pb(0.5 + i / 10), "method_id": "P/B_CURRENT_RESEARCH"}}} for i in range(6)}
    pooled = valuation.attach_peer_relative(rows())
    assert "cohort" not in pooled["T0"]["peer_relative"]["P/B_CURRENT_RESEARCH"]["basis"]
    keyed = valuation.attach_peer_relative(rows(), cohort_by_ticker={f"T{i}": "FOOD" for i in range(6)})
    detail = keyed["T0"]["peer_relative"]["P/B_CURRENT_RESEARCH"]
    assert detail["basis"]["cohort"] == "FOOD"
    record = {"methods": keyed["T0"]["methods"], "peer_relative": keyed["T0"]["peer_relative"],
              "relative_research_state": keyed["T0"]["relative_research_state"]}
    summary, *_ = _summary(record)
    assert summary["peer_relative_drivers"][0]["cohort_scope"] == "SAME_METHOD_SAME_BASIS_COHORT_FOOD"
    assert "PEER_COHORT_NOT_INDUSTRY_MATCHED" not in summary["peer_relative_qualifications"]


def test_balance_sheet_only_scope_names_the_statement_families_that_did_not_vote():
    basis = signals.research_evidence_basis({"favorable_votes": ["CAPITAL_STRUCTURE.DIRECTION"], "adverse_votes": []})
    scope = signals.headline_evidence_scope(basis)
    assert scope["scope"] == "BALANCE_SHEET_ONLY"
    assert scope["represented_statement_families"] == ["BALANCE_SHEET"]
    assert scope["unrepresented_statement_families"] == ["INCOME_STATEMENT", "CASH_FLOW"]
    assert "BALANCE_SHEET_DIRECTION_IS_NOT_REVENUE_OR_EARNINGS_CONFIRMATION" in scope["limitations"]
    assert scope["vote_effect"] == "NONE"
    multi = signals.headline_evidence_scope(signals.research_evidence_basis(
        {"favorable_votes": ["GROWTH.DIRECTION", "CAPITAL_STRUCTURE.DIRECTION"], "adverse_votes": []}))
    assert multi["scope"] == "MULTI_FAMILY" and multi["unrepresented_statement_families"] == ["CASH_FLOW"]
    bank = signals.headline_evidence_scope(signals.research_evidence_basis(
        {"favorable_votes": ["BANK_FUNDING.DIRECTION"], "adverse_votes": []}))
    assert bank["unrepresented_statement_families"] == []


def _decision(valuation_record, monkeypatch=None):
    from test_integrated_investment_decision_product import (
        _current_disposition, _sample_financial_record, _sample_tactical_record)
    return iidp.build_ticker_integrated_decision(
        ticker="HPG", as_of_session=SESSION, tactical_record=_sample_tactical_record(),
        financial_record=_sample_financial_record(), valuation_record=valuation_record,
        relative_volume_record=None, market_sector_record=None,
        technical_coverage_disposition_record=_current_disposition(SESSION))


def test_method_provenance_reaches_integrated_decision_and_daily_brief():
    record = _decision(hpg())
    summary = record["valuation_context_summary"]
    assert summary["pe_basis"]["claim"] == "HISTORICAL_DENOMINATOR_RESEARCH_CONTEXT_NOT_CURRENT_TTM"
    assert summary["pe_basis"]["denominator_freshness"]["freshness_status"] == "STALE_BUT_RESEARCH_USABLE"
    scope = record["financial_composite_context"]["evidence_scope"]
    assert scope == signals.headline_evidence_scope(record["financial_composite_context"]["evidence_basis"])
    watch = brief.build_watchlist_record(ticker="HPG", current=record, tactical_raw=None,
                                         sector_label=None, posture_transition_row=None)
    assert watch["valuation"]["pe_basis"] == summary["pe_basis"]
    assert watch["valuation"]["ps_basis"] == summary["ps_basis"]
    assert watch["valuation"]["pe_multiple"] == summary["pe_multiple"]
    assert watch["valuation"]["peer_relative_drivers"] == summary["peer_relative_drivers"]
    assert watch["valuation"]["peer_relative_qualifications"] == summary["peer_relative_qualifications"]
    assert watch["fundamental_evidence_scope"] == scope


def test_corrective_is_additive_posture_identity_and_policy_codes_unchanged(monkeypatch):
    baseline = _decision(pan())
    monkeypatch.setattr(iidp, "_headline_multiple_basis", lambda *a, **k: {})
    monkeypatch.setattr(iidp, "_peer_relative_verdict_basis", lambda *a, **k: ([], []))
    monkeypatch.setattr(signals, "headline_evidence_scope", lambda basis: {})
    without = _decision(pan())
    for key in ("research_action_posture", "posture_condition_class", "decision_identity", "fundamental_state",
                "tactical_phase", "fundamental_support", "counter_thesis", "uncertainty_reasons"):
        assert baseline.get(key) == without.get(key), key
    for key in ("peer_relative_state", "pe_multiple", "ps_multiple", "pb_multiple", "pb_basis", "limitations", "status"):
        assert baseline["valuation_context_summary"][key] == without["valuation_context_summary"][key], key
    assert (baseline["financial_composite_context"]["financial_composite_state"]
            == without["financial_composite_context"]["financial_composite_state"])
    assert baseline["evidence_axes"] == without["evidence_axes"]


def test_inputs_are_not_mutated():
    record = pan()
    snapshot = copy.deepcopy(record)
    _summary(record)
    assert record == snapshot
