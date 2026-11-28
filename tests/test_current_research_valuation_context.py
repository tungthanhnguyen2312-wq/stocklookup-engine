"""Focused tests for `current_research_valuation_context`: the TTM monetary-basis
comparison, and the sector/industry (entity-class fallback) engine-feature peer context.
"""
from __future__ import annotations

import pytest

from stocklookup_core.valuation.current_research_valuation_context import (
    AVAILABLE_QUALIFIED, AVAILABLE_REFERENCE_ONLY, ENGINE_PEER_FEATURES, ENTITY_CLASS_COHORT_LEVEL,
    EV_EBITDA, EV_EBITDA_CALC_READY, INPUT_BLOCKED, NOT_AVAILABLE,
    NOT_APPLICABLE, PE_NOT_MEANINGFUL, PE_TTM, PS_TTM, RELATIVE_METHODS, SECTOR_COHORT_LEVEL,
    _calculation_readiness_method, _calculation_readiness_reconciliation, _monetary_basis_compatible,
    _select_ttm, attach_engine_fundamental_peers, attach_peer_relative, evaluate_ticker_valuation,
    method_availability_state, valuation_axis,
)
from stocklookup_core.decision.opportunity_axis_freshness import CURRENT
from stocklookup_core.financial import monetary_basis_contract as basis_contract

BLOCKED_METHOD = {"status": "BLOCKED", "value": None, "blocked_reasons": []}


def test_readiness_reconciliation_compares_only_same_period_methods():
    methods = {
        "P/E": {"status": "RESEARCH_USABLE", "value": 12.0, "period_basis": "2025"},
        "P/S": {"status": "RESEARCH_USABLE", "value": 2.0, "period_basis": "2025"},
    }
    context = {"status": "AVAILABLE", "calculation_readiness": [{
        "reporting_period": "2025",
        "pe": {"readiness": "ready", "status": "provider_reported", "value": 12.0, "blocked_by": []},
    }]}
    result = _calculation_readiness_reconciliation(methods, context)
    assert result["P/E"]["comparison_status"] == "AGREES_WITHIN_REPRESENTATION_TOLERANCE"
    assert result["P/S"]["comparison_status"] == "NOT_SEMANTICALLY_EQUIVALENT"
    context["calculation_readiness"][0]["reporting_period"] = "2026-Q1"
    result = _calculation_readiness_reconciliation(methods, context)
    assert result["P/E"]["comparison_status"] == "NOT_COMPARABLE_DIFFERENT_REPORTING_PERIOD"


def qualified_feature(value, *, currency="VND", scale="units", provider="KBS",
                      periods=("2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4")):
    return {"fitness": "READY", "value": value, "method": "four_consecutive_compatible_standalone_quarters/v2",
            "period_identity": list(periods), "provider_source_provenance": [{"provider": provider}],
            "currency": currency, "scale": scale, "reason_codes": []}


def financial_analysis_record(*, net_income=None, revenue=None):
    features = {}
    if net_income is not None:
        features["attributable_net_income_ttm"] = net_income
    if revenue is not None:
        features["revenue_ttm"] = revenue
    return {"features": features}


def market_cap_metric(value, *, status="RESEARCH_USABLE", currency="VND", scale="units", monetary_basis=None):
    row = {"status": status, "value": value, "blocked_reasons": []}
    if monetary_basis is not None:
        row["monetary_basis"] = monetary_basis
        row["currency"] = monetary_basis.get("currency")
        row["scale"] = monetary_basis.get("native_scale")
        row["monetary_basis_status"] = monetary_basis.get("basis_status")
    else:
        row["currency"] = currency
        row["scale"] = scale
    return row


def valuation_record(market_cap):
    share = {"authority": "provider_reported_lagged", "status": "PROVIDER_REPORTED_LAGGED",
             "research_proxy_eligible": True, "authoritative_current_market_cap_eligible": False,
             "share_concept": "ISSUED_SHARES"}
    return {
        "entity_class": "corporate", "share_basis_input": share,
        "metrics": {
            "market_cap": market_cap, "P/E": BLOCKED_METHOD, "P/B": BLOCKED_METHOD,
            "P/S": BLOCKED_METHOD, "EV/Sales": BLOCKED_METHOD, "EV/EBITDA": BLOCKED_METHOD,
        },
    }


def feature_record():
    return {"features": {
        "net_income_ttm_sum": {"status": "BLOCKED"},
        "revenue_ttm_sum": {"status": "BLOCKED"},
        "profit_state": {"status": "BLOCKED"},
    }}


def _b_config():
    import json
    from pathlib import Path
    return json.loads((Path(__file__).resolve().parents[1] / "config/dual_reader_ttm_research_config.json").read_bytes())


def _b_research_case(ticker="NVL"):
    from stocklookup_core.evidence import dual_reader_transcription as dual
    config = _b_config()
    config["enabled"] = True  # in-memory synthetic shadow only
    bound = [dict(c, source_verification_status=c["verification_status"])
             for c in config["research_caveats"] if c["ticker"] == ticker and c["document_sha256"]]
    features = {}
    for fid, value in (("attributable_net_income_ttm", 400), ("revenue_ttm", 800)):
        feature = qualified_feature(value, provider="official_issuer_ir")
        feature.update(evidence_tier=dual.EVIDENCE_TIER, authority_effect="OFFLINE_RESEARCH_ONLY",
            pit_backtest_eligible=False, knowledge_available_at=config["approved_at"], research_caveats=bound,
            ttm_operand_provenance=[{"reporting_period": c["reporting_period"], "document_sha256": c["document_sha256"],
                "proof_sha256": "1" * 64, "knowledge_available_at": config["approved_at"]} for c in bound])
        features[fid] = feature
    state = {"state": "ON", "config": config, "tickers": [ticker], "cutoff": "2026-11-28T15:00:00+07:00",
        "caveats_by_ticker": {ticker: bound}, "features_by_ticker": {ticker: features}, "integrity_blocked": False}
    return {"features": features}, state


def test_b_off_exact_pre_b_valuation_materializer_and_ai_bytes(monkeypatch):
    import copy, json, subprocess, types
    from pathlib import Path
    import canonical_daily_financial_v2_materialization as materializer
    import stocklookup_core.valuation.current_research_valuation_context as valuation
    import ai_research_session_delivery as delivery
    root = Path(__file__).resolve().parents[1]
    def module(name, content, file):
        result = types.ModuleType(name)
        result.__file__ = str(root / file)
        exec(compile(content, file, "exec"), result.__dict__)
        return result
    archives = root / "tests/fixtures/dual_reader_ttm_valuation_b_v1_sources"
    prior_valuation = module("b_prior_valuation", (archives / "stocklookup_core__valuation__current_research_valuation_context.py.txt").read_bytes(), "stocklookup_core/valuation/current_research_valuation_context.py")
    prior_delivery = module("b_prior_delivery", (archives / "ai_research_session_delivery.py.txt").read_bytes(), "ai_research_session_delivery.py")
    prior_materializer = module("b_prior_materializer", subprocess.check_output([
        "git", "show", "1c3b1d1fd1c05186f6660f89085dcf2580f415fb:canonical_daily_financial_v2_materialization.py"], cwd=root), "canonical_daily_financial_v2_materialization.py")
    prior_materializer.valuation_context = prior_valuation
    for target in (materializer, prior_materializer):
        monkeypatch.setattr(target, "_official_equity_overlay", lambda root: [])
    import stocklookup_core.evidence.official_document_qualification as qualification
    def forbidden(*args, **kwargs):
        raise AssertionError("OFF read the landing root")
    monkeypatch.setattr(qualification, "official_landing_root", forbidden)
    engine = {"artifact_identity": "engine:fixture", "records": {"AAA": financial_analysis_record(
        net_income=qualified_feature(400), revenue=qualified_feature(800))}}
    before = copy.deepcopy(engine)
    kwargs = dict(engine_artifact=engine, raw_valuation_artifact={"records": {"AAA": valuation_record(market_cap_metric(4000))}},
        product_tickers=["AAA"], requested_at="2026-11-28T15:00:00+07:00", official_financial_facts=[])
    current, prior = materializer.build_evaluated_valuation_artifact(**kwargs), prior_materializer.build_evaluated_valuation_artifact(**kwargs)
    encode = lambda value: json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    assert encode(current) == encode(prior)
    assert engine == before
    record = {"valuation_methods": current["records"]["AAA"]["methods"]}
    assert encode(delivery.project_integrated_decision_for_ai_delivery(record, source_session="2026-11-28")) == encode(
        prior_delivery.project_integrated_decision_for_ai_delivery(record, source_session="2026-11-28"))


def test_b_nvl_ttm_numeric_lead_immutable_pb_closed_and_peer_isolated():
    import copy
    from stocklookup_core.evidence import dual_reader_transcription as dual
    from stocklookup_core.research.ai_handoff_publication import _unsafe_pointer
    from ai_research_session_delivery import _valuation_methods_for_delivery
    financial, research = _b_research_case()
    before = copy.deepcopy(financial)
    raw = valuation_record(market_cap_metric(4000))
    row = evaluate_ticker_valuation(ticker="NVL", feature_record=None, valuation_record=raw,
        financial_analysis_record=financial, dual_reader_research_state=research,
        official_financial_facts=[], decision_session="2026-11-28")
    assert row["methods"][PE_TTM]["value"] == 10
    assert row["methods"][PS_TTM]["value"] == 5
    pb = row["methods"]["P/B_CURRENT_RESEARCH"]
    assert pb["status"] == INPUT_BLOCKED
    assert "SHARE_COUNT_EQUITY_CONSISTENCY_RISK_UNREGISTERED_CONVERSION" in pb["blocker_reason_codes"]
    cohort = attach_peer_relative({str(i): copy.deepcopy(row) for i in range(6)})
    for result in cohort.values():
        for method_id in (PE_TTM, PS_TTM):
            peer = result["peer_relative"][method_id]
            assert peer["reason"] == "OFFLINE_RESEARCH_ONLY_PEER_ISOLATED"
            assert peer["peer_count"] == 0 and peer["percentile"] is None
        assert result["relative_research_state"] not in {"ATTRACTIVE_RELATIVE_RESEARCH", "EXPENSIVE_RELATIVE_RESEARCH"}
    methods = _valuation_methods_for_delivery({"valuation_methods": row["methods"]}, source_session="2026-11-28")
    assert PE_TTM in methods and PS_TTM in methods and _unsafe_pointer(methods) is None
    assert any(c["verification_status"] == "LEAD" for c in methods[PE_TTM]["research_caveats"])
    assert set(dual.RESEARCH_LIMITATIONS) <= set(methods[PE_TTM]["limitations"])
    assert financial == before


@pytest.mark.parametrize("missing", ["authority_effect", "evidence_tier", "pit_backtest_eligible", "knowledge_available_at",
    "limitations", "share_basis_caveats", "research_caveats", "old_session", "absolute_path", "promoted_lead"])
def test_b_ai_omits_incomplete_research_method(missing):
    from ai_research_session_delivery import _valuation_methods_for_delivery
    from stocklookup_core.evidence import dual_reader_transcription as dual
    method = {"value": 5, "status": "RESEARCH_USABLE", "authority_effect": "OFFLINE_RESEARCH_ONLY",
        "evidence_tier": dual.EVIDENCE_TIER, "pit_backtest_eligible": False,
        "knowledge_available_at": "2026-11-27T01:00:00+07:00",
        "limitations": [*dual.RESEARCH_LIMITATIONS, "SYNTHETIC_LEAD", "SHARE_BASIS_LAGGED_PROVIDER_ISSUED"],
        "required_research_caveat_codes": ["SYNTHETIC_LEAD"],
        "share_authority": "provider_reported_lagged", "share_basis_caveats": [{"code": "SHARE_BASIS_LAGGED_PROVIDER_ISSUED", "verification_status": "VERIFIED", "source_verification_status": "VERIFIED", "never_adjust_multiples": True}],
        "research_caveats": [{"code": "SYNTHETIC_LEAD", "verification_status": "LEAD", "source_verification_status": "LEAD", "never_adjust_multiples": True}]}
    session = "2026-11-28"
    assert PE_TTM in _valuation_methods_for_delivery({"valuation_methods": {PE_TTM: method}}, source_session=session)
    if missing == "old_session": session = "2026-10-13"
    elif missing == "absolute_path": method["ttm_operand_provenance"] = [{"path": "C:/private/file"}]
    elif missing == "promoted_lead": method["research_caveats"][0]["verification_status"] = "VERIFIED"
    else: del method[missing]
    assert PE_TTM not in _valuation_methods_for_delivery({"valuation_methods": {PE_TTM: method}}, source_session=session)


def test_b_overlay_off_corrupt_on_unset_root_and_preapproval(monkeypatch, tmp_path):
    from canonical_daily_financial_v2_materialization import _load_dual_reader_ttm_research_overlay as load
    config = _b_config()
    kwargs = dict(repo_root=tmp_path, decision_session="2026-11-28", product_tickers=["NVL", "POW"], official_financial_facts=[])
    assert load(**kwargs, config=config)["state"] == "OFF"
    assert load(**kwargs)["state"] == "CORRUPT_BLOCKED"
    config["enabled"] = True
    monkeypatch.delenv("STOCK_LOOKUP_RUNTIME_ROOT", raising=False)
    blocked = load(**kwargs, config=config)
    assert blocked["state"] == "INTEGRITY_BLOCKED" and "RUNTIME_ROOT_UNSET" in blocked["reason"]
    kwargs["decision_session"] = "2026-11-25"
    assert load(**kwargs, config=config)["state"] == "PRE_APPROVAL_CUTOFF"


def test_b_overlay_on_real_engine_empty_frozen_rows(monkeypatch, tmp_path):
    from canonical_daily_financial_v2_materialization import _load_dual_reader_ttm_research_overlay as load
    from stocklookup_core.evidence import dual_reader_transcription as dual
    config = _b_config()
    config["enabled"] = True
    dual._config_schema(config)
    # Empty frozen-row boundary, real overlay and keyword-only engine. No runtime lookup.
    monkeypatch.setattr(dual, "load_admitted_rows", lambda root, entries: [])
    result = load(repo_root=tmp_path, decision_session="2026-11-28", product_tickers=["NVL"],
        official_financial_facts=[], evidence_root=tmp_path, config=config)
    assert result["state"] == "ON" and result["integrity_blocked"] is False, result
    assert "reason" not in result
    features = result["features_by_ticker"]["NVL"]
    assert set(features) == {"revenue_ttm", "net_income_ttm", "attributable_net_income_ttm"}
    for feature in features.values():
        assert feature["fitness"] == "BLOCKED_BY_EVIDENCE" and feature["value"] is None
        assert feature["reason_codes"] == [
            "OFFICIAL_H1_OPERAND_MISSING_OR_NOT_ADMITTED:" + period
            for period in ("2025", "2025-H1", "2026-H1")]
        assert feature["method"] == "official_fy_plus_h1_minus_prior_h1/v2"
        assert feature["ttm_operand_provenance"] == []
        assert feature["evidence_tier"] == dual.EVIDENCE_TIER


def test_b_overlay_on_real_engine_three_periods_nvl_pb_closed_and_peer_isolated(monkeypatch, tmp_path):
    import copy
    from canonical_daily_financial_v2_materialization import _load_dual_reader_ttm_research_overlay as load
    from stocklookup_core.evidence import dual_reader_transcription as dual
    import stocklookup_core.evidence.official_document_qualification as admission
    from test_financial_flow_semantics_ttm_bridge import _official_operands
    config = _b_config()
    config["enabled"] = True
    dual._config_schema(config)
    entries = [e for e in config["evidence_subdirs"] if e["ticker"] == "NVL"]
    rows = _official_operands()
    for row in rows:
        entry = next(e for e in entries if e["reporting_period"] == row["reporting_period"])
        row.update(ticker="NVL", document_sha256=entry["document_sha256"],
            dual_reader_transcription={"proof_sha256": entry["proof_sha256"]})
    before = copy.deepcopy(rows)
    # Qualified synthetic operands isolate orchestration/calculation from retained PDF replay,
    # as in the bridge tests. Neither the materializer seam nor the engine is replaced.
    monkeypatch.setattr(dual, "load_admitted_rows", lambda root, selected: rows)
    monkeypatch.setattr(admission, "admit_retained_financial_fact",
        lambda *args, **kwargs: {"state": "ADMITTED", "reason_codes": []})
    research = load(repo_root=tmp_path, decision_session="2026-11-28", product_tickers=["NVL"],
        official_financial_facts=[], evidence_root=tmp_path, config=config)
    assert research["state"] == "ON" and research["integrity_blocked"] is False, research
    features = research["features_by_ticker"]["NVL"]
    for fid, expected in (("revenue_ttm", 120), ("net_income_ttm", 120), ("attributable_net_income_ttm", 115)):
        feature = features[fid]
        assert feature["fitness"] == "READY" and feature["value"] == expected
        assert feature["operand_periods"] == ["2025", "2026-H1", "2025-H1"]
        assert len(feature["ttm_operand_provenance"]) == 3
        assert feature["authority_effect"] == "OFFLINE_RESEARCH_ONLY"
        assert feature["pit_backtest_eligible"] is False
    row = evaluate_ticker_valuation(ticker="NVL", feature_record=None,
        valuation_record=valuation_record(market_cap_metric(1200)),
        financial_analysis_record={"features": features}, dual_reader_research_state=research,
        official_financial_facts=[], decision_session="2026-11-28")
    assert row["methods"][PE_TTM]["value"] == pytest.approx(1200 / 115)
    assert row["methods"][PS_TTM]["value"] == 10
    pb = row["methods"]["P/B_CURRENT_RESEARCH"]
    assert pb["status"] == INPUT_BLOCKED
    assert "SHARE_COUNT_EQUITY_CONSISTENCY_RISK_UNREGISTERED_CONVERSION" in pb["blocker_reason_codes"]
    for result in attach_peer_relative({str(i): copy.deepcopy(row) for i in range(6)}).values():
        for method in (PE_TTM, PS_TTM):
            peer = result["peer_relative"][method]
            assert peer["reason"] == "OFFLINE_RESEARCH_ONLY_PEER_ISOLATED"
            assert peer["peer_count"] == 0 and peer["percentile"] is None
    assert rows == before


def evaluate(*, net_income=None, revenue=None, market_cap_value=8_000_000, cap_currency="VND",
            cap_scale="units", cap_monetary_basis=None):
    market_cap = market_cap_metric(market_cap_value, currency=cap_currency, scale=cap_scale,
                                   monetary_basis=cap_monetary_basis)
    return evaluate_ticker_valuation(
        ticker="AAA", feature_record=feature_record(), valuation_record=valuation_record(market_cap),
        financial_analysis_record=financial_analysis_record(net_income=net_income, revenue=revenue),
        financial_analysis_context_identity="fa:1",
    )


def test_compatible_normalized_bases_allow_pe_ttm():
    row = evaluate(net_income=qualified_feature(400_000), market_cap_value=8_000_000)
    method = row["methods"][PE_TTM]
    assert method["status"] == "RESEARCH_USABLE"
    assert method["value"] == pytest.approx(20.0)


def test_compatible_normalized_bases_allow_ps_ttm():
    row = evaluate(revenue=qualified_feature(4_000_000), market_cap_value=8_000_000)
    method = row["methods"][PS_TTM]
    assert method["status"] == "RESEARCH_USABLE"
    assert method["value"] == pytest.approx(2.0)


def test_currency_mismatch_blocks_pe_ttm():
    row = evaluate(net_income=qualified_feature(400_000, currency="USD"), market_cap_value=8_000_000)
    method = row["methods"][PE_TTM]
    assert method["status"] == INPUT_BLOCKED
    assert "TTM_MARKET_CAP_MONETARY_BASIS_INCOMPATIBLE" in method["blocker_reason_codes"]


def test_unknown_ttm_basis_blocks_even_though_market_cap_basis_is_known():
    # `feature.get("currency")` missing entirely (as `resolve_currency_and_scale` leaves
    # it absent an official-citation match) must never be treated as "matches VND".
    row = evaluate(net_income=qualified_feature(400_000, currency=None, scale=None), market_cap_value=8_000_000)
    method = row["methods"][PE_TTM]
    assert method["status"] == INPUT_BLOCKED
    assert "TTM_MARKET_CAP_MONETARY_BASIS_INCOMPATIBLE" in method["blocker_reason_codes"]


def test_unknown_market_cap_basis_blocks_even_though_ttm_basis_is_known():
    # The real production default today: market_wide_current_valuation_input_scaleout's
    # market_cap carries monetary_basis_status == UNKNOWN (see that module's own tests).
    unknown_cap_basis = basis_contract.build_basis(currency="VND", scale=None, basis_source="price scale undocumented")
    row = evaluate(net_income=qualified_feature(400_000), market_cap_value=8_000_000, cap_monetary_basis=unknown_cap_basis)
    method = row["methods"][PE_TTM]
    assert method["status"] == INPUT_BLOCKED
    assert "TTM_MARKET_CAP_MONETARY_BASIS_INCOMPATIBLE" in method["blocker_reason_codes"]


def test_different_native_scales_but_same_normalized_vnd_may_compare():
    # TTM retained in native thousand-VND with a proven multiplier; market cap retained
    # in native base VND. Native scales differ, but both reach the same normalized VND.
    ttm_thousand = qualified_feature(4_000)  # will be overridden below with a richer basis
    ttm_thousand["currency"], ttm_thousand["scale"] = "VND", "THOUSAND"
    financial_record = {"features": {"net_income_ttm": ttm_thousand}}
    cap_basis = basis_contract.build_basis(currency="VND", scale="units", multiplier_to_vnd=1,
                                           normalized_unit="VND", basis_status=basis_contract.QUALIFIED,
                                           basis_source="test: base-vnd market cap")
    market_cap = market_cap_metric(8_000_000, monetary_basis=cap_basis)
    row = evaluate_ticker_valuation(
        ticker="AAA", feature_record=feature_record(), valuation_record=valuation_record(market_cap),
        financial_analysis_record=financial_record, financial_analysis_context_identity="fa:1",
    )
    method = row["methods"][PE_TTM]
    # THOUSAND vs units, with no proven multiplier on the THOUSAND side -> still blocked:
    # a labelled scale alone (without a multiplier_to_vnd) is not by itself comparable.
    assert method["status"] == INPUT_BLOCKED


def test_monetary_basis_compatible_directly_with_a_proven_multiplier_on_both_sides():
    thousand = basis_contract.build_basis(currency="VND", scale="THOUSAND", multiplier_to_vnd=1000,
                                          normalized_unit="VND", basis_status=basis_contract.QUALIFIED, basis_source="a")
    base = basis_contract.build_basis(currency="VND", scale="units", multiplier_to_vnd=1,
                                      normalized_unit="VND", basis_status=basis_contract.QUALIFIED, basis_source="b")
    ttm = {"ttm_currency": thousand["currency"], "ttm_scale": thousand["native_scale"], "ttm_monetary_basis": thousand}
    market_cap = market_cap_metric(1, monetary_basis=base)
    ok, reason = _monetary_basis_compatible(ttm, market_cap)
    assert ok is True
    assert reason is None


def test_negative_ni_ttm_is_pe_not_meaningful_not_blocked():
    row = evaluate(net_income=qualified_feature(-400_000), market_cap_value=8_000_000)
    method = row["methods"][PE_TTM]
    assert method["status"] == PE_NOT_MEANINGFUL
    assert method["value"] is None


def test_zero_ni_ttm_is_pe_not_meaningful_not_blocked():
    row = evaluate(net_income=qualified_feature(0), market_cap_value=8_000_000)
    method = row["methods"][PE_TTM]
    assert method["status"] == PE_NOT_MEANINGFUL


def test_no_value_magnitude_heuristic_a_plausible_looking_ratio_still_blocks():
    # A market cap and TTM net income whose *ratio* looks like an entirely ordinary P/E
    # must still block when the basis itself is unproven -- plausibility is never used
    # as a substitute for a real currency/scale citation.
    unknown_cap_basis = basis_contract.build_basis(currency="VND", scale=None, basis_source="undocumented")
    row = evaluate(net_income=qualified_feature(1_000), market_cap_value=15_000, cap_monetary_basis=unknown_cap_basis)
    method = row["methods"][PE_TTM]
    assert method["status"] == INPUT_BLOCKED


def test_old_ttm_fallback_precedence_unchanged_when_no_qualified_ttm_present():
    old = {"status": "READY_RESEARCH_PROXY", "value": 500, "feature_id": "net_income_ttm_sum",
           "provider_source_lineage": [{"provider": "LEGACY"}], "currency": "VND", "scale": "units"}
    selected = _select_ttm(old=old, qualified=None)
    assert selected["ttm_input_source"] == "OLD_TTM_FALLBACK_SELECTED"
    assert selected["ttm_currency"] == "VND"
    assert selected["ttm_scale"] == "units"


def test_no_ttm_precedence_unchanged_when_neither_source_present():
    old = {"status": "BLOCKED", "value": None, "feature_id": "net_income_ttm_sum"}
    selected = _select_ttm(old=old, qualified=None)
    assert selected["ttm_input_source"] == "NO_TTM"
    assert selected["ttm_currency"] is None
    assert selected["ttm_scale"] is None


def test_both_present_new_qualified_ttm_still_preferred():
    old = {"status": "READY_RESEARCH_PROXY", "value": 999, "feature_id": "net_income_ttm_sum",
           "provider_source_lineage": [{"provider": "LEGACY"}], "currency": "VND", "scale": "units"}
    qualified = {"status": "READY", "value": 400, "ttm_currency": "VND", "ttm_scale": "units"}
    selected = _select_ttm(old=old, qualified=qualified)
    assert selected["ttm_input_source"] == "BOTH_PRESENT_CONFLICT"
    assert selected["value"] == 400
    assert selected["old_ttm_value"] == 999


def test_deterministic_identity_same_inputs_same_output():
    first = evaluate(net_income=qualified_feature(400_000), market_cap_value=8_000_000)
    second = evaluate(net_income=qualified_feature(400_000), market_cap_value=8_000_000)
    assert first["methods"][PE_TTM] == second["methods"][PE_TTM]


# --- attach_engine_fundamental_peers: sector/industry peer context over engine_v2 -----

def _engine_feature(value, *, fitness="READY", method="same_provider_same_period_gross_margin/v2",
                    period="2026-Q2", scope=("consolidated",), currency="unknown", scale="unknown"):
    return {"fitness": fitness, "value": value, "method": method, "period_identity": [period, period],
           "scope": list(scope), "currency": currency, "scale": scale, "reason_codes": [] if fitness == "READY" else ["X"],
           "provider_source_provenance": [{"provider": "KBS"}], "period_semantics": ["STANDALONE_QUARTER"]}


def _engine_record(gross_margin=None, *, issuer_type="corporate", **overrides):
    features = {}
    if gross_margin is not None:
        features["gross_margin"] = gross_margin if isinstance(gross_margin, dict) else _engine_feature(gross_margin)
    features.update(overrides)
    return {"issuer_type": issuer_type, "features": features}


def test_engine_peer_median_and_tie_aware_percentile():
    values = [0.10, 0.20, 0.30, 0.40, 0.50, 0.60]
    records = {f"T{i}": _engine_record(value) for i, value in enumerate(values)}
    peers = attach_engine_fundamental_peers(records)
    entry = peers["T2"]["gross_margin"]  # subject value 0.30
    assert entry["status"] == "READY_RESEARCH_ONLY"
    assert entry["peer_count"] == 6
    assert entry["peer_median"] == pytest.approx(0.35)
    assert entry["percentile"] == pytest.approx((2 + 0.5) / 6)
    assert entry["cohort_level"] == ENTITY_CLASS_COHORT_LEVEL
    assert entry["cohort_id"] == "ENTITY_CLASS:corporate"


def test_engine_peer_percentile_is_tie_aware():
    values = [0.20, 0.20, 0.20, 0.30, 0.40]
    records = {f"T{i}": _engine_record(value) for i, value in enumerate(values)}
    peers = attach_engine_fundamental_peers(records)
    entry = peers["T0"]["gross_margin"]
    assert entry["percentile"] == pytest.approx((0 + 0.5 * 3) / 5)


def test_engine_peer_insufficient_below_minimum_cohort():
    records = {f"T{i}": _engine_record(value) for i, value in enumerate([0.1, 0.2, 0.3, 0.4])}
    peers = attach_engine_fundamental_peers(records)
    entry = peers["T0"]["gross_margin"]
    assert entry["status"] == "INSUFFICIENT_PEER_COUNT"
    assert entry["peer_count"] == 4
    assert entry.get("percentile") is None


def test_engine_peer_not_comparable_when_feature_not_ready():
    records = {f"T{i}": _engine_record(0.2 + i / 100) for i in range(5)}
    records["T0"] = _engine_record(_engine_feature(None, fitness="BLOCKED_BY_EVIDENCE"))
    peers = attach_engine_fundamental_peers(records)
    assert peers["T0"]["gross_margin"]["status"] == "NOT_COMPARABLE"
    assert peers["T0"]["gross_margin"]["peer_count"] == 0


def test_engine_peer_missing_metric_degrades_only_that_metric():
    records = {f"T{i}": _engine_record(0.2 + i / 100) for i in range(5)}
    for ticker, record in records.items():
        record["features"]["net_margin"] = _engine_feature(None, fitness="BLOCKED_BY_EVIDENCE")
    peers = attach_engine_fundamental_peers(records)
    assert peers["T0"]["gross_margin"]["status"] == "READY_RESEARCH_ONLY"
    assert peers["T0"]["net_margin"]["status"] == "NOT_COMPARABLE"
    assert set(peers["T0"]) == set(ENGINE_PEER_FEATURES)


def test_engine_peer_incompatible_method_never_pooled_together():
    records = {f"T{i}": _engine_record(0.2 + i / 100) for i in range(5)}
    records["T5"] = _engine_record(_engine_feature(0.99, method="a_different_method/v9"))
    peers = attach_engine_fundamental_peers(records)
    assert peers["T0"]["gross_margin"]["peer_count"] == 5
    assert peers["T5"]["gross_margin"]["status"] == "INSUFFICIENT_PEER_COUNT"
    assert peers["T5"]["gross_margin"]["peer_count"] == 1


def test_engine_peer_incompatible_monetary_basis_never_pooled_together():
    # Same feature, same cohort, same method, same period -- but a different native
    # currency/scale is a genuinely different monetary basis and must not be blended
    # into one percentile, exactly as the pre-existing valuation route's monetary-basis
    # compatibility gate already enforces for P/E, P/B, and P/S.
    records = {f"T{i}": _engine_record(0.2 + i / 100) for i in range(5)}
    records["T5"] = _engine_record(_engine_feature(0.99, currency="USD"))
    records["T6"] = _engine_record(_engine_feature(0.98, scale="thousand"))
    peers = attach_engine_fundamental_peers(records)
    assert peers["T0"]["gross_margin"]["peer_count"] == 5
    assert peers["T5"]["gross_margin"]["status"] == "INSUFFICIENT_PEER_COUNT"
    assert peers["T5"]["gross_margin"]["peer_count"] == 1
    assert peers["T6"]["gross_margin"]["status"] == "INSUFFICIENT_PEER_COUNT"
    assert peers["T6"]["gross_margin"]["peer_count"] == 1


def test_engine_peer_prefers_retained_sector_over_entity_class():
    records = {f"T{i}": _engine_record(0.2 + i / 100) for i in range(5)}
    industry = {ticker: "Bất động sản" for ticker in records}
    peers = attach_engine_fundamental_peers(records, industry_by_ticker=industry)
    entry = peers["T0"]["gross_margin"]
    assert entry["cohort_level"] == SECTOR_COHORT_LEVEL
    assert entry["cohort_id"] == f"SECTOR:{'bất động sản'}"
    assert entry["status"] == "READY_RESEARCH_ONLY" and entry["peer_count"] == 5


def test_engine_peer_falls_back_to_entity_class_without_retained_industry():
    records = {f"T{i}": _engine_record(0.2 + i / 100) for i in range(5)}
    peers = attach_engine_fundamental_peers(records, industry_by_ticker={"T0": "   "})
    assert peers["T0"]["gross_margin"]["cohort_level"] == ENTITY_CLASS_COHORT_LEVEL


# --- MARKET_WIDE_FUNDAMENTAL_VALUATION_ANALYTICAL_PRODUCT_V1: EV/EBITDA_CALC_READY ---------
# Wires market_wide_calculation_readiness.py's own EV/EBITDA verdict into a genuinely usable,
# separately-named method. The pre-existing EV_EBITDA method_id must remain untouched.

def _readiness_context(*, period="2026-Q1", readiness="ready", value=8.5, status="provider_reported",
                       blocked_by=()):
    return {
        "status": "AVAILABLE",
        "calculation_readiness": [{
            "reporting_period": period,
            "ev_ebitda": {"readiness": readiness, "status": status, "value": value,
                         "formula": "enterprise_value / ebitda", "blocked_by": list(blocked_by)},
        }],
    }


def test_calculation_readiness_method_ready_is_research_usable():
    method = _calculation_readiness_method(
        capability="ev_ebitda", method_id=EV_EBITDA_CALC_READY, applicability_method_id=EV_EBITDA,
        entity="corporate", calculation_readiness_record=_readiness_context(value=7.25))
    assert method["status"] == "RESEARCH_USABLE"
    assert method["value"] == pytest.approx(7.25)
    assert method["applicability"] == "APPLICABLE"
    assert method["own_history_status"] == "UNAVAILABLE_LATEST_PERIOD_ONLY_PIPELINE"


def test_calculation_readiness_method_not_applicable_for_bank():
    method = _calculation_readiness_method(
        capability="ev_ebitda", method_id=EV_EBITDA_CALC_READY, applicability_method_id=EV_EBITDA,
        entity="bank", calculation_readiness_record=_readiness_context())
    assert method["status"] == NOT_APPLICABLE
    assert method["applicability"] == NOT_APPLICABLE


def test_calculation_readiness_method_blocked_when_not_ready():
    method = _calculation_readiness_method(
        capability="ev_ebitda", method_id=EV_EBITDA_CALC_READY, applicability_method_id=EV_EBITDA,
        entity="corporate", calculation_readiness_record=_readiness_context(
            readiness="blocked", value=None, blocked_by=["negative_or_zero_ebitda_denominator"]))
    assert method["status"] == INPUT_BLOCKED
    assert "negative_or_zero_ebitda_denominator" in method["blocker_reason_codes"]


def test_calculation_readiness_method_blocked_when_context_absent():
    method = _calculation_readiness_method(
        capability="ev_ebitda", method_id=EV_EBITDA_CALC_READY, applicability_method_id=EV_EBITDA,
        entity="corporate", calculation_readiness_record=None)
    assert method["status"] == INPUT_BLOCKED
    assert "CALCULATION_READINESS_CONTEXT_UNAVAILABLE" in method["blocker_reason_codes"]


def test_evaluate_ticker_valuation_wires_calculation_readiness_method_end_to_end():
    row = evaluate_ticker_valuation(
        ticker="AAA", feature_record=feature_record(), valuation_record=valuation_record(market_cap_metric(8_000_000)),
        financial_analysis_record=financial_analysis_record(), financial_analysis_context_identity="fa:1",
        calculation_readiness_record=_readiness_context(value=9.1),
    )
    method = row["methods"][EV_EBITDA_CALC_READY]
    assert method["status"] == "RESEARCH_USABLE"
    assert method["value"] == pytest.approx(9.1)
    # The always-blocked, structurally-distinct legacy method is untouched by this wiring.
    assert row["methods"][EV_EBITDA]["status"] == INPUT_BLOCKED
    assert row["usable_relative_method_count"] >= 1


def test_evaluate_ticker_valuation_ev_ebitda_calc_ready_absent_stays_blocked_not_crashing():
    row = evaluate(net_income=qualified_feature(400_000), market_cap_value=8_000_000)
    assert row["methods"][EV_EBITDA_CALC_READY]["status"] == INPUT_BLOCKED


def test_ev_ebitda_calc_ready_participates_in_peer_relative_cohort():
    rows = {
        f"T{i}": evaluate_ticker_valuation(
            ticker=f"T{i}", feature_record=feature_record(), valuation_record=valuation_record(market_cap_metric(8_000_000)),
            financial_analysis_record=financial_analysis_record(), financial_analysis_context_identity="fa:1",
            calculation_readiness_record=_readiness_context(value=value),
        )
        for i, value in enumerate([5.0, 6.0, 7.0, 8.0, 9.0, 10.0])
    }
    rows = attach_peer_relative(rows)
    entry = rows["T2"]["peer_relative"][EV_EBITDA_CALC_READY]  # subject value 7.0
    assert entry["status"] == "READY_RESEARCH_ONLY"
    assert entry["peer_count"] == 6
    assert entry["percentile"] == pytest.approx((2 + 0.5) / 6)


def test_earnings_yield_ttm_is_reciprocal_of_usable_pe_ttm():
    row = evaluate(net_income=qualified_feature(400_000), market_cap_value=8_000_000)
    assert row["methods"][PE_TTM]["value"] == pytest.approx(20.0)
    assert row["earnings_yield_ttm"]["status"] == "RESEARCH_USABLE"
    assert row["earnings_yield_ttm"]["value"] == pytest.approx(0.05)


def test_earnings_yield_ttm_blocked_when_pe_ttm_not_meaningful():
    row = evaluate(net_income=qualified_feature(-400_000), market_cap_value=8_000_000)
    assert row["methods"][PE_TTM]["status"] == PE_NOT_MEANINGFUL
    assert row["earnings_yield_ttm"]["status"] == "BLOCKED"
    assert row["earnings_yield_ttm"]["value"] is None


def test_fcf_yield_ttm_is_explicitly_blocked_no_ttm_fcf_retained():
    row = evaluate(net_income=qualified_feature(400_000), market_cap_value=8_000_000)
    assert row["fcf_yield_ttm"]["status"] == "BLOCKED"
    assert row["fcf_yield_ttm"]["blocker_reason_codes"] == ["FCF_TTM_NOT_RETAINED_STANDALONE_QUARTER_PROXY_ONLY"]


# --- WORKSPACE_DIAGNOSTIC_TRANSPARENCY_AND_DAILY_DASHBOARD_BINDING_V1: availability/authority ---

def _freshness(session="2026-09-16"):
    return {"freshness_status": CURRENT, "source_session": session}


def test_method_availability_qualified_only_with_peer_relative_ready():
    method = {"status": "RESEARCH_USABLE", "value": 12.0}
    assert method_availability_state(method, {"status": "READY_RESEARCH_ONLY"}) == AVAILABLE_QUALIFIED
    assert method_availability_state(method, {"status": "INSUFFICIENT_PEER_COUNT"}) == AVAILABLE_REFERENCE_ONLY
    assert method_availability_state(method, None) == AVAILABLE_REFERENCE_ONLY


def test_method_availability_reference_only_for_pe_not_meaningful():
    method = {"status": PE_NOT_MEANINGFUL, "value": None}
    assert method_availability_state(method, None) == AVAILABLE_REFERENCE_ONLY


def test_method_availability_not_available_when_input_blocked_or_not_applicable():
    assert method_availability_state({"status": INPUT_BLOCKED, "value": None}, None) == NOT_AVAILABLE
    assert method_availability_state({"status": NOT_APPLICABLE, "value": None}, None) == NOT_AVAILABLE


def test_peer_blocker_does_not_erase_the_underlying_usable_multiple():
    """A method usable but below the minimum peer cohort stays visible as reference-only,
    never silently erased/collapsed to NOT_AVAILABLE just because peer-relative is blocked."""
    rows = attach_peer_relative({"AAA": evaluate(net_income=qualified_feature(400_000), market_cap_value=8_000_000)})
    axis = valuation_axis(ticker="AAA", decision_session="2026-09-16", valuation_artifact={"as_of_session": "2026-09-16"},
                          feature_store=None, row=rows["AAA"], freshness=_freshness())
    pe_ttm = axis["applicable_methods"][PE_TTM]
    assert pe_ttm["value"] == pytest.approx(20.0)
    assert pe_ttm["peer_relative"]["status"] == "INSUFFICIENT_PEER_COUNT"
    assert pe_ttm["availability_state"] == AVAILABLE_REFERENCE_ONLY
    assert axis["valuation_summary"]["valuation_display_state"] == "RESEARCH_METHODS_AVAILABLE_NOT_PEER_QUALIFIED"
    assert axis["valuation_summary"]["qualified_relative_method_count"] == 0
    assert axis["valuation_summary"]["available_method_count"] >= 1


def test_method_level_value_survives_projection_once_peer_cohort_qualifies():
    cohort = {
        f"T{i}": evaluate(net_income=qualified_feature(400_000 * (i + 1)), market_cap_value=8_000_000)
        for i in range(5)
    }
    rows = attach_peer_relative(cohort)
    axis = valuation_axis(ticker="T0", decision_session="2026-09-16", valuation_artifact={"as_of_session": "2026-09-16"},
                          feature_store=None, row=rows["T0"], freshness=_freshness())
    pe_ttm = axis["applicable_methods"][PE_TTM]
    assert pe_ttm["status"] == "RESEARCH_USABLE"
    assert pe_ttm["value"] is not None
    assert pe_ttm["peer_relative"]["status"] == "READY_RESEARCH_ONLY"
    assert pe_ttm["availability_state"] == AVAILABLE_QUALIFIED
    assert axis["valuation_summary"]["qualified_relative_method_count"] >= 1
    assert axis["valuation_summary"]["valuation_display_state"] == "PEER_RELATIVE_QUALIFIED"


def test_truly_missing_method_stays_not_available_never_a_fabricated_number():
    row = evaluate(net_income=None, revenue=None)
    rows = attach_peer_relative({"AAA": row})
    axis = valuation_axis(ticker="AAA", decision_session="2026-09-16", valuation_artifact={"as_of_session": "2026-09-16"},
                          feature_store=None, row=rows["AAA"], freshness=_freshness())
    for method_id in RELATIVE_METHODS:
        method = axis["applicable_methods"][method_id]
        assert method["availability_state"] == NOT_AVAILABLE
        assert method["value"] is None
    summary = axis["valuation_summary"]
    assert summary["valuation_display_state"] == "NO_VALUATION_METHOD_AVAILABLE"
    assert summary["available_method_count"] == 0
    assert summary["missing_method_count"] == len(RELATIVE_METHODS)


def test_valuation_summary_never_implies_intrinsic_fair_value_or_target_price():
    row = evaluate(net_income=qualified_feature(400_000), market_cap_value=8_000_000)
    rows = attach_peer_relative({"AAA": row})
    axis = valuation_axis(ticker="AAA", decision_session="2026-09-16", valuation_artifact={"as_of_session": "2026-09-16"},
                          feature_store=None, row=rows["AAA"], freshness=_freshness())
    summary = axis["valuation_summary"]
    assert summary["not_intrinsic_fair_value"] is True
    assert summary["not_dcf_or_target_price"] is True
    assert "target_price" not in summary and "fair_value" not in summary and "dcf" not in summary
    assert "absolute valuation model" not in summary["display_note"].lower()
    assert "fair value" not in summary["display_note"].lower()


def test_raw_upstream_relative_state_preserved_separately_from_availability_state():
    """`status`/`applicability` (the raw upstream fields) are untouched by the new
    `availability_state` diagnostic lens -- additive, not a silent rename/replacement."""
    row = evaluate(net_income=qualified_feature(400_000), market_cap_value=8_000_000)
    rows = attach_peer_relative({"AAA": row})
    axis = valuation_axis(ticker="AAA", decision_session="2026-09-16", valuation_artifact={"as_of_session": "2026-09-16"},
                          feature_store=None, row=rows["AAA"], freshness=_freshness())
    pe_ttm = axis["applicable_methods"][PE_TTM]
    assert pe_ttm["status"] == "RESEARCH_USABLE"
    assert pe_ttm["applicability"] == "APPLICABLE"
    assert "availability_state" in pe_ttm
