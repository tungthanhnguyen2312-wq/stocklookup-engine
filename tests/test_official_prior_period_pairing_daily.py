"""Daily frozen-caller integration and non-voting historical card acceptance."""
import copy
import hashlib
import json
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest
import daily_session_level2_package as level2
import market_wide_current_fundamental_research as fundamental
import ai_research_session_delivery as delivery
from stocklookup_core.financial import official_income_prior_period_pairing as pairing
from tests.test_official_income_prior_period_pairing import current, governed, prior, record, CUTOFF
from tests.test_current_official_evidence_projection import baseline
from tests.financial_source_fixture import bind_fixture_source, synthetic_retained_source_io
from tests.test_daily_session_level2_package import (
    _independent_component_session_paths, _write_json, _write_valid_p3f9b_snapshot,
    _valid_technical_recovery_payload, _fake_ensure_exact_session_snapshot,
)

ROOT = Path(__file__).resolve().parents[1]
PUBLIC = ROOT / "derived/financial-evidence-currency-refresh-v1"
SESSION = "2026-10-26"
NEW_CUTOFF = SESSION + "T15:00:00+07:00"


def bundle(rows):
    return {"rows": rows, "load_blockers": [], "comparative_observations": []}


def test_reviewed_comparatives_flow_only_after_review_and_leave_official_facts_unchanged():
    receipts = pairing.load_reviewed_comparatives(PUBLIC)
    assert len(receipts) == 5 and sum(len(row["rows"]) for row in receipts) == 86
    inputs = bundle([]) | {"reviewed_comparatives": receipts}
    assert pairing.qualified_prior_inputs_at_cutoff(inputs, cutoff="2026-11-13T15:00:00+07:00") is None
    cutoff = "2026-11-16T15:00:00+07:00"
    assert pairing.qualified_prior_inputs_at_cutoff(inputs, cutoff=cutoff)["reviewed_comparatives"] == receipts
    source = baseline()
    source["records"]["HPG"]["entity_class"] = "corporate"
    source.update(fundamental.content_identity(source))
    options = dict(baseline=source, official_rows=[], session="2026-11-16", cutoff=cutoff)
    plain = fundamental.project_session(**options)["records"]["HPG"]
    candidate = fundamental.project_session(**options, prior_period_inputs=inputs)["records"]["HPG"]
    first = delivery.financial_research_card({"ticker": "HPG"}, plain, {}, cutoff=cutoff)
    second = delivery.financial_research_card({"ticker": "HPG"}, candidate, {}, cutoff=cutoff)
    income = second["fundamental_research_context"]["official_income"]
    reviewed = income.pop("reviewed_comparative")
    assert reviewed["use"] == "CONDITIONAL_NON_VOTING_RESEARCH_ONLY"
    assert reviewed["is_actionable"] is False and reviewed["strict_valuation_effect"] == "NONE"
    h1 = next(report for report in reviewed["reports"] if report["document"]["reporting_period"] == "2026-H1")
    assert {row["metric"] for row in h1["comparisons"]} == {"revenue", "net_income", "attributable_net_income", "operating_cash_flow"}
    assert h1["cash_conversion"][0]["operating_cash_flow"] == 12_641_697_117_285
    assert h1["cash_conversion"][0]["profit_metric"] == "net_income"
    income.pop("prior_period_pairing")
    assert second == first


def test_reviewed_comparatives_reject_numeric_tamper_even_with_new_receipt_hash(tmp_path):
    receipts = pairing.load_reviewed_comparatives(PUBLIC)
    receipt = receipts[0]
    receipt["rows"][0]["normalized_value"] += 1
    row = receipt["rows"][0]
    row["citation_id"] = pairing._hash({k: v for k, v in row.items() if k != "citation_id"})
    receipt["review_receipt"] = pairing._hash({k: v for k, v in receipt.items() if k != "review_receipt"})
    _write_json(tmp_path / pairing.REVIEWED_COMPARATIVE_FILE, receipts)
    with pytest.raises(ValueError, match="REVIEWED_COMPARATIVE_ROW_BINDING_INVALID"):
        pairing.load_reviewed_comparatives(tmp_path)


def daily_fixture(tmp_path, monkeypatch):
    paths = _independent_component_session_paths(tmp_path, SESSION)
    snapshot = _write_valid_p3f9b_snapshot(paths["exact_session_snapshot"], SESSION)
    _write_json(paths["technical_recovery"], _valid_technical_recovery_payload(SESSION, snapshot))
    source = baseline()
    for r in source["records"].values(): r["entity_class"] = "corporate"
    source.update(fundamental.content_identity(source))
    _write_json(paths["fundamental"], source)
    monkeypatch.setattr(level2, "ensure_exact_session_snapshot", _fake_ensure_exact_session_snapshot(paths))
    monkeypatch.setattr(level2, "_prior_completed_descriptive", lambda *a, **k: tmp_path / "prior.json")
    monkeypatch.setattr(level2, "materialize_official_liquidity_component", lambda *a, **k: None)
    monkeypatch.setattr(level2, "run_cmd", lambda *a, **k: pytest.fail("unexpected subprocess"))
    return source


def test_daily_calls_existing_loader_and_projection_then_existing_card(tmp_path, monkeypatch):
    source = daily_fixture(tmp_path, monkeypatch)
    template = next(json.loads(line) for line in (PUBLIC / "qualified_official_facts.jsonl").read_bytes().splitlines()
                    if json.loads(line)["ticker"] == "HPG" and json.loads(line)["canonical_metric"] == "net_income")
    template.update(normalized_value=120, value=120)
    fact, _ = bind_fixture_source(template)
    import financial_evidence_currency_refresh as refresh
    monkeypatch.setattr(refresh, "load_public_official_fact_rows", lambda root: [fact])
    rows = prior(governed(100, ticker="HPG"))
    with patch.object(pairing, "load_prior_period_inputs", return_value=bundle(rows)) as loader:
        level2.materialize_independent_components(tmp_path, SESSION, tmp_path / "runtime")
    loader.assert_called_once_with(runtime_root=tmp_path / "runtime", repo_root=tmp_path,
                                  public_root=tmp_path / refresh.PUBLIC_ARTIFACT_DIR)
    actual = json.loads(level2.session_fundamental_path(tmp_path, SESSION).read_bytes())
    assert fundamental.content_identity(actual)["artifact_identity"] == actual["artifact_identity"]
    row = actual["records"]["HPG"]
    context = row["official_income_research_context"]["prior_period_pairing"]
    assert context["comparisons"][0]["growth_ratio"] == .2
    card = delivery.financial_research_card({"ticker": "HPG"}, row, {}, cutoff=NEW_CUTOFF)
    assert card["fundamental_research_context"]["official_income"]["prior_period_pairing"] == context
    plain = fundamental.project_session(baseline=source, official_rows=[fact], session=SESSION, cutoff=NEW_CUTOFF)
    changed = copy.deepcopy(actual)
    for rec in changed["records"].values(): rec["official_income_research_context"].pop("prior_period_pairing")
    changed["source_artifacts"].pop("official_income_prior_period_inputs")
    for key in ("artifact_identity", "artifact_sha256"):
        changed.pop(key); plain.pop(key)
    assert changed == plain  # Includes trajectory, votes, valuation inputs and summaries.


@pytest.mark.parametrize("rows", [[], prior(governed(100, verified="2026-10-27T00:00:00Z")),
                                   prior(governed(100, currency=None))])
def test_daily_no_qualified_known_input_preserves_projection_identity(tmp_path, monkeypatch, rows):
    source = daily_fixture(tmp_path, monkeypatch)
    import financial_evidence_currency_refresh as refresh
    monkeypatch.setattr(refresh, "load_public_official_fact_rows", lambda root: [])
    monkeypatch.setattr(pairing, "load_prior_period_inputs", lambda **kwargs: bundle(rows))
    expected = fundamental.project_session(baseline=source, official_rows=[], session=SESSION, cutoff=NEW_CUTOFF)
    level2.materialize_independent_components(tmp_path, SESSION, tmp_path / "runtime")
    assert json.loads(level2.session_fundamental_path(tmp_path, SESSION).read_bytes()) == expected


@pytest.mark.parametrize("completed", [True, False])
def test_completed_or_occupied_projection_never_loads_new_inputs(tmp_path, monkeypatch, completed):
    source = daily_fixture(tmp_path, monkeypatch)
    path = level2.session_fundamental_path(tmp_path, SESSION)
    if completed:
        _write_json(tmp_path / "config/daily_research_session_input_registry.json",
                    {"contract_version": "daily_research_session_input_registry/v1",
                     "completed_sessions": {SESSION: {"status": "COMPLETED_RETAINED_EVIDENCE"}}})
    else:
        existing = fundamental.project_session(baseline=source, official_rows=[], session=SESSION, cutoff=NEW_CUTOFF)
        _write_json(path, existing)
    before = path.read_bytes() if path.exists() else None
    monkeypatch.setattr(pairing, "load_prior_period_inputs", lambda **k: pytest.fail("must not load"))
    level2.materialize_independent_components(tmp_path, SESSION, tmp_path / "runtime")
    assert (path.read_bytes() if path.exists() else None) == before


def test_card_never_adopts_later_or_different_facts_or_preview():
    source = record(current())
    pairing.attach_prior_period_pairing({"SYN": source}, prior_rows=prior(governed()), cutoff=CUTOFF)
    assert "prior_period_pairing" in delivery.financial_research_card(
        {"ticker": "SYN"}, source, {}, cutoff=CUTOFF)["fundamental_research_context"]["official_income"]
    for cutoff in [None, "2026-10-22T15:00:00+07:00", "2026-10-26T15:00:00+07:00"]:
        assert "prior_period_pairing" not in delivery.financial_research_card(
            {"ticker": "SYN"}, source, {}, cutoff=cutoff)["fundamental_research_context"]["official_income"]
    source["official_income_research_context"]["prior_period_pairing"]["owner_gated_preview"]["enabled_gates"] = [pairing.COMPARATIVE_GATE]
    assert "prior_period_pairing" not in delivery.financial_research_card(
        {"ticker": "SYN"}, source, {}, cutoff=CUTOFF)["fundamental_research_context"]["official_income"]


def test_stale_cached_current_context_cannot_leak_future_facts():
    source = record(current())
    ctx = pairing.official_income_prior_period_context(source, prior_rows=prior(governed()),
        ticker="SYN", cutoff="2026-10-01T15:00:00+07:00")
    assert not ctx["comparisons"]
    assert "NO_ADMITTED_CURRENT_OFFICIAL_INCOME_FACT" in ctx["blocker_reason_codes"]


def test_malformed_semantic_corrections_fail_closed_before_loading_owners(tmp_path):
    path = tmp_path / "derived/financial-evidence-currency-refresh-v1/semantic_metric_relabel_corrections.jsonl"
    path.parent.mkdir(parents=True); path.write_text("broken", encoding="utf-8")
    assert pairing.load_prior_official_income_rows(runtime_root=tmp_path, repo_root=tmp_path) == {
        "rows": [], "load_blockers": ["SEMANTIC_CORRECTIONS_UNREADABLE"]}


def test_exact_daily_source_transition_conserves_pins_and_rejects_tampering(tmp_path):
    from tools.verify_retention_reader_transition import historical_bytes, legacy_source_identity, FINANCIAL_RESEARCH_MANIFEST
    from tools.qualify_e4_infrastructure import source_identity
    relative = "daily_session_level2_package.py"
    pins = json.loads((ROOT / "tests/fixtures/e2e3_frozen_sources.json").read_bytes())["source_sha256_lf"]
    original = subprocess.check_output(["git", "show", "829500e7:" + relative], cwd=ROOT).replace(b"\r\n", b"\n")
    assert historical_bytes(ROOT, relative) == original
    assert hashlib.sha256(original).hexdigest() == pins[relative]
    for version, expected in [("v1", "fa79baadcca197493b9ca70067fbd153f5e8bb7f50dfb6dbc6da53f253483d46"),
                              ("v2", "07c2a363df0e91a1dee230f0316a081249b247f7aa74bd67e04e45b1d1886567")]:
        assert legacy_source_identity(ROOT, version=version)["code_digest"] == expected
        assert source_identity(ROOT, version=version)["code_digest"] != expected
    for rel in [relative, FINANCIAL_RESEARCH_MANIFEST, "tests/fixtures/e2e3_frozen_sources.json",
                "tests/fixtures/financial_research_v1_sources/" + relative + ".txt"]:
        dest = tmp_path / rel; dest.parent.mkdir(parents=True, exist_ok=True); dest.write_bytes((ROOT / rel).read_bytes())
    (tmp_path / relative).write_bytes((tmp_path / relative).read_bytes() + b"\n# unreviewed mutation\n")
    with pytest.raises(ValueError, match="TRANSITION_BINDING_INVALID"):
        historical_bytes(tmp_path, relative)


def test_active_coupled_digest_refuses_both_prior_declared_and_main_receipts():
    from tools import qualify_e4_infrastructure as e4
    row = json.loads((ROOT / "tests/fixtures/financial_research_source_transition_v1.json").read_bytes())["sources"]["daily_session_level2_package.py"]
    digest = hashlib.sha256(b"e4_infrastructure_source/v2\0")
    for label, path in [*e4.V1_SOURCES, *((p, p) for p in e4.V2_SOURCES)]:
        content = subprocess.check_output(["git", "show", "829500e7:" + path], cwd=ROOT).replace(b"\r\n", b"\n")
        digest.update(label.encode() + b"\0" + hashlib.sha256(content).digest())
    assert digest.hexdigest() == row["base_live_e4_v2_digest"]
    live = e4.source_identity(ROOT, version="v2")
    successor = json.loads((ROOT / "tests/fixtures/owner_daily_iid_runtime_memory_source_transition_v1.json").read_bytes())
    assert row["active_e4_v2_digest"] == successor["previous_e4_v2_digest"]
    tplus = json.loads((ROOT / "tests/fixtures/tplus_resumable_feedback_source_transition_v1.json").read_bytes())
    assert successor["active_e4_v2_digest"] == tplus["previous_e4_v2_digest"]
    daily = json.loads((ROOT / "tests/fixtures/tplus_daily_incremental_source_transition_v1.json").read_bytes())
    assert tplus["active_e4_v2_digest"] == daily["previous_e4_v2_digest"]
    resident = json.loads((ROOT / "tests/fixtures/owner_daily_resident_iid_source_transition_v1.json").read_bytes())
    assert resident["previous_e4_v2_digest"] == daily["active_e4_v2_digest"]
    brief_inputs = json.loads((ROOT / "tests/fixtures/owner_daily_brief_inputs_source_transition_v1.json").read_bytes())
    assert brief_inputs["previous_e4_v2_digest"] == resident["active_e4_v2_digest"]
    real_corpus = json.loads((ROOT / "tests/fixtures/tplus_real_t0_corpus_source_transition_v1.json").read_bytes())
    assert real_corpus["previous_e4_v2_digest"] == brief_inputs["active_e4_v2_digest"]
    incremental = json.loads((ROOT / "tests/fixtures/tplus_incremental_cost_v2_source_transition_v1.json").read_bytes())
    assert incremental["previous_e4_v2_digest"] == real_corpus["active_e4_v2_digest"]
    m1b = json.loads((ROOT / "tests/fixtures/tplus_incremental_cost_v2_m1b_source_transition_v1.json").read_bytes())
    assert m1b["previous_e4_v2_digest"] == incremental["active_e4_v2_digest"]
    root_fix = json.loads((ROOT / "tests/fixtures/thesis_current_technical_root_source_transition_v1.json").read_bytes())
    assert root_fix["previous_e4_v2_digest"] == m1b["active_e4_v2_digest"]
    summary_fp = json.loads((ROOT / "tests/fixtures/tplus_legacy_summary_fingerprint_source_transition_v1.json").read_bytes())
    assert summary_fp["previous_e4_v2_digest"] == root_fix["active_e4_v2_digest"]
    context_fp = json.loads((ROOT / "tests/fixtures/decision_context_premarket_source_transition_v1.json").read_bytes())
    assert context_fp["previous_e4_v2_digest"] == summary_fp["active_e4_v2_digest"]
    feedback_io = json.loads((ROOT / "tests/fixtures/tplus_feedback_io_source_transition_v1.json").read_bytes())
    assert feedback_io["previous_e4_v2_digest"] == context_fp["active_e4_v2_digest"]
    retry = json.loads((ROOT / "tests/fixtures/tplus_retry_integrity_source_transition_v1.json").read_bytes())
    assert retry["previous_e4_v2_digest"] == feedback_io["active_e4_v2_digest"]
    truthfulness = json.loads((ROOT / "tests/fixtures/valuation_output_truthfulness_source_transition_v1.json").read_bytes())
    assert truthfulness["previous_e4_v2_digest"] == retry["active_e4_v2_digest"]
    assert live["code_digest"] == truthfulness["active_e4_v2_digest"]
    for old in (row["prior_declared_e4_v2_digest"], row["base_live_e4_v2_digest"], row["active_e4_v2_digest"],
                feedback_io["active_e4_v2_digest"], retry["active_e4_v2_digest"]):
        assert old != live["code_digest"]
        assert not e4.candidate_reuse_eligible({"source_version": "v2",
            "contract_version": "e4_infrastructure_source/v2", "code_digest": old,
            "input_digest": "old-input"}, live, input_digest="old-input")


def test_all_daily_delivery_surfaces_keep_the_exact_historical_context():
    from tests.test_ai_research_session_delivery import _operation, _integrated_delivery_fixture
    operation, integrated = _operation(), _integrated_delivery_fixture(session="2026-10-23")
    operation["manifest"]["market_session"] = "2026-10-23"
    source = record(current(ticker="AAA"))
    # The source-owned context in this synthetic case uses the same ticker.
    from stocklookup_core.financial.fundamental_signal_consumption_contract import official_income_research_context
    source["official_income_research_context"] = official_income_research_context(source, cutoff=CUTOFF, ticker="AAA")
    pairing.attach_prior_period_pairing({"AAA": source}, prior_rows=prior(governed(ticker="AAA")), cutoff=CUTOFF)
    inputs = {"descriptive": {"records": {"AAA": {}}}, "fundamental": {"session_cutoff": CUTOFF,
              "records": {"AAA": source}}, "integrated_investment_decision_product": integrated}
    saved = copy.deepcopy((operation, inputs))
    output = delivery.build_delivery(operation, inputs)
    primary = json.loads(output["primary"])["ticker_research_contexts"]["AAA"]["fundamental_research_context"]["official_income"]
    assert primary["prior_period_pairing"]["comparisons"]
    cockpit = json.loads(output["projection"])
    assert cockpit["ticker_cards"]["AAA"]["fundamental_research_context"]["official_income"] == primary
    assert cockpit["decision_card_v1"]["AAA"]["fundamental"]["official_income_research_context"] == primary
    assert json.loads(output["full_universe"])["fundamental_research_context"]["official_income"] == primary
    assert (operation, inputs) == saved


def test_reviewed_reported_margins_keep_source_periods_and_non_voting_boundary():
    from stocklookup_core.financial.interim_earnings_cash_research import reviewed_comparative_research
    receipts = pairing.load_reviewed_comparatives(PUBLIC)
    saved = copy.deepcopy(receipts)
    results = {ticker: reviewed_comparative_research(ticker, "2026-11-16T15:00:00+07:00", receipts)
               for ticker in ("HPG", "PNJ", "FPT")}
    reports = [r for result in results.values() for r in result["reports"]]
    assert sum(len(r["profitability"]["measurements"]) for r in reports) == 20
    assert sum(len(r["profitability"]["changes"]) for r in reports) == 10
    for result in results.values():
        assert all(result[k] == "NONE" for k in ("vote_effect", "strict_valuation_effect", "ttm_effect"))
        assert result["is_actionable"] is False
    for report in reports:
        facts = {r["citation_id"]: r for r in report["facts"]}
        for measurement in report["profitability"]["measurements"]:
            profit, revenue = facts[measurement["profit_citation_id"]], facts[measurement["revenue_citation_id"]]
            assert measurement["margin_ratio"] == profit["normalized_value"] / revenue["normalized_value"]
            assert profit["document_sha256"] == revenue["document_sha256"] == measurement["document_sha256"]
            assert measurement["bounds"] == [profit["period_start"], profit["period_end"]]
        for change in report["profitability"]["changes"]:
            assert change["change_percentage_points"] == 100 * (change["current_margin_ratio"] - change["prior_margin_ratio"])
    assert reviewed_comparative_research("HPG", "2026-11-13T15:00:00+07:00", receipts) is None
    assert receipts == saved


def test_margin_change_refuses_a_restated_or_missing_comparison():
    from stocklookup_core.financial.interim_earnings_cash_research import reviewed_comparative_research
    receipts = pairing.load_reviewed_comparatives(PUBLIC)
    receipt = next(r for r in receipts if r["ticker"] == "HPG")
    receipt["original_comparative_checks"].append({"metric": "revenue", "status": "DIFFERS_FROM_ORIGINAL"})
    report = reviewed_comparative_research("HPG", "2026-11-16T15:00:00+07:00", [receipt])["reports"][0]
    assert report["profitability"]["measurements"]  # source-period margins still meaningful
    assert not report["profitability"]["changes"]
    assert all(b["reason_codes"] == ["NO_QUALIFIED_LIKE_FOR_LIKE_MARGIN_PAIR"] for b in report["profitability"]["blockers"])


@pytest.mark.parametrize("revenue", [0, -1])
def test_non_positive_revenue_never_yields_a_reported_margin(revenue):
    from stocklookup_core.financial.interim_earnings_cash_research import reviewed_comparative_research
    receipt = pairing.load_reviewed_comparatives(PUBLIC)[0]
    for row in receipt["rows"]:
        if row.get("canonical_metric") == "revenue":
            row["normalized_value"] = revenue
    report = reviewed_comparative_research(receipt["ticker"], "2026-11-16T15:00:00+07:00", [receipt])["reports"][0]
    assert not report["profitability"]["measurements"] and not report["profitability"]["changes"]
    assert all(b["reason_codes"] == ["MISSING_OR_NON_POSITIVE_SAME_STATEMENT_REVENUE"] for b in report["profitability"]["blockers"])


def test_negative_cash_base_is_an_outflow_transition_not_earnings_growth():
    from stocklookup_core.financial.interim_earnings_cash_research import reviewed_comparative_research
    result = reviewed_comparative_research("PNJ", "2026-11-16T15:00:00+07:00", pairing.load_reviewed_comparatives(PUBLIC))
    report = next(r for r in result["reports"] if r["document"]["reporting_period"] == "2026-H1")
    cash = next(c for c in report["comparisons"] if c["metric"] == "operating_cash_flow")
    assert cash["growth_ratio"] is None
    assert cash["semantic_transition"] == "OUTFLOW_TO_INFLOW"
