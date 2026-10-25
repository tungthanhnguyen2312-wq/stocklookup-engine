"""Offline source-bound explanations; synthetic mechanics and retained projections are distinct."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import pytest

import market_wide_current_fundamental_research as owner
from stocklookup_core.financial.interim_earnings_cash_research import financial_quality_decision_bridge as build, render_financial_quality
from tests.test_interim_earnings_cash_research import fact
from tools import inspect_decision_research as cli

ROOT = Path(__file__).resolve().parents[1]
RETAINED = ROOT / "tests/fixtures/official_income_research_actual_sessions_v1.json"
CUTOFF = "2026-10-25T15:00:00+07:00"


def row(metric, value, **kw):
    return fact(metric, value, **({"observed_at": "2026-09-01T00:00:00Z", "publication_date": None, "source_page": 1} | kw))


def run(rows, entity="corporate", cutoff=CUTOFF):
    return build({"ticker": "SYN", "entity_class": entity, "official_field_context": rows},
                 ticker="SYN", knowledge_cutoff=cutoff)


def retained():
    return json.loads(RETAINED.read_bytes())["sessions"]["2026-10-22"]


def source(tmp_path, records=None):
    capture = retained()
    # A source-bound projected SUBSET for offline acceptance, not a claim that
    # this new test seal is the original full Producer artifact or authenticates facts.
    body = {"contract_version": owner.CONTRACT_VERSION, "research_session": "2026-10-22",
            "session_cutoff": capture["cutoff"],
            "records": records if records is not None else {t: r["fundamental"] for t, r in capture["rows"].items()},
            "retained_subset_provenance": {k: capture[k] for k in ("source_fundamental", "source_fundamental_sha256", "operation_identity")}}
    body.update(owner.content_identity(body))
    path = tmp_path / "fundamental.json"
    path.write_text(json.dumps(body), encoding="utf8")
    return path


def args(path, *extra):
    parser = argparse.ArgumentParser()
    cli.configure_parser(parser.add_subparsers(dest="command", required=True))
    return parser.parse_args(["research", "financial-quality", "--fundamental", str(path),
                              "--cutoff", CUTOFF, "--ticker", "PNJ", *extra])


@pytest.mark.parametrize("ticker,count", [("PNJ", 6), ("HPG", 2), ("FPT", 3), ("QNS", 1), ("VNM", 1), ("PVD", 7)])
def test_retained_projected_cases_preserve_exact_facts_without_global_company_verdict(ticker, count):
    capture = retained()
    record = capture["rows"][ticker]["fundamental"]
    original = deepcopy(record)
    out = build(record, ticker=ticker, knowledge_cutoff=capture["cutoff"])
    assert len(out["facts"]) == count and record == original
    originals = {f["citation_id"]: f for f in record["official_field_context"]}
    for f in out["facts"]:
        for key in ("normalized_value", "currency", "period_start", "period_end", "statement_scope",
                    "audit_or_review_status", "document_sha256", "source_page", "knowledge_available_at", "observed_at"):
            assert f[key] == originals[f["citation_id"]][key]
    assert not out["cash_conversion"]  # these actual captures contain no compatible cash/PAT pair
    assert out["non_voting"] and not out["is_actionable"] and out["strict_valuation_effect"] == "NONE"
    assert "company_verdict" not in out and "WAIT" not in json.dumps(out)
    assert out["retained_research_context"]["metrics"] == record["metrics"]
    text = render_financial_quality(out)
    assert "Thesis checks / invalidation" in text
    if ticker == "PNJ":
        assert "728386009054 VND" in text and "2667248523366 VND" in text
        assert "Historical annual cash cannot explain current interim profit" in text
        assert "not cash received" in text
    if ticker == "HPG":
        assert "15514931571606 VND" in text
        assert not out["reported_components"]  # Hub disposal/ex-RE numbers are not admitted
    if ticker == "FPT":
        assert "2025 provision_charge_or_reversal_adjustment: 651406282654 VND" in text
        assert not out["confirming_evidence"]  # a provision does not manufacture profit
    if ticker == "PVD":
        assert {f["currency"] for f in out["facts"]} == {"USD", "VND"}


def test_cash_conversion_is_exact_bounded_arithmetic_not_cause_or_earnings_normalization():
    out = run([row("net_income", 100), row("operating_cash_flow", -30),
               row("investment_property_disposal_result", 40)])
    m, = out["cash_conversion"]
    assert m["conversion_ratio"] == -.3 and m["operating_cash_minus_profit"] == -130
    codes = {x["code"] for x in out["counterevidence"]}
    assert {"POSITIVE_PROFIT_NEGATIVE_OPERATING_CASH", "REPORTED_DISPOSAL_COMPONENT"} <= codes
    assert out["thesis_tests"][0]["status"] == "UNSUPPORTED"
    assert "recurrence and tax treatment are unproven" in render_financial_quality(out)
    assert "normalized_eps" not in out and "adjusted_profit" not in out


@pytest.mark.parametrize("changes", [
    {"document_sha256": "e"*64}, {"statement_scope": "standalone"}, {"currency": "USD"},
    {"audit_or_review_status": "audited"}, {"period_type": "quarter"},
    {"period_start": "2025-01-01", "period_end": "2025-12-31"},
])
def test_cash_profit_incompatible_basis_never_forms_a_ratio(changes):
    assert not run([row("net_income", 100), row("operating_cash_flow", 50, **changes)])["cash_conversion"]


def test_parent_only_profit_does_not_form_group_cash_conversion():
    assert not run([row("attributable_net_income", 100), row("operating_cash_flow", 50)])["cash_conversion"]


@pytest.mark.parametrize("changes", [
    {"normalized_value": float("nan")}, {"normalized_value": True}, {"unit_scale": 1000},
    {"already_normalized": False}, {"qualification_state": "CANDIDATE_NOT_PRODUCER_QUALIFIED"},
    {"existing_consumer_usable": False}, {"audit_or_review_status": "unreviewed"},
    {"knowledge_available_at": "2026-10-26T00:00:00Z"}, {"observed_at": "2026-10-26T00:00:00Z"},
    {"publication_date": "2026-10-26"}, {"observed_at": None}, {"ticker": "OTHER"},
    {"source_page": None}, {"source_page": True}, {"document_sha256": "not-a-source-hash"},
])
def test_unsafe_rows_leave_other_facts_available(changes):
    out = run([row("net_income", 100), row("operating_cash_flow", 50, **changes)])
    assert not out["cash_conversion"] and len(out["facts"]) == 1 and out["rejected"]


@pytest.mark.parametrize("entity", ["bank", "securities", "insurance", None])
def test_specialist_entities_do_not_get_industrial_cash_or_net_debt_interpretation(entity):
    out = run([row("net_income", 100), row("operating_cash_flow", -30)], entity=entity)
    assert not out["facts"] and not out["cash_conversion"]
    assert "specialist accounting evidence is required" in render_financial_quality(out)
    assert "PAT alone cannot establish comprehensive income" in render_financial_quality(out)


def test_conflict_duplicate_order_and_missing_components_never_establish_clean_earnings():
    rows = [row("net_income", 100), row("net_income", 101, citation_id="revision"), row("operating_cash_flow", 50)]
    out = run(rows)
    assert not out["cash_conversion"] and all(f["canonical_metric"] != "net_income" for f in out["facts"])
    assert out == run(list(reversed(rows)) + rows)
    assert "absence of a component is not proof of clean earnings" in render_financial_quality(out)


def test_cli_source_to_human_packet_and_markdown_keeps_real_captured_case_limits(tmp_path):
    path = source(tmp_path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    out = cli.inspect(args(path, "--ticker", "HPG", "--ticker", "FPT", "--ticker", "QNS", "--ticker", "POW", "--ticker", "VCI"))
    assert set(out["records"]) == {"PNJ", "HPG", "FPT", "QNS", "POW", "VCI"}
    assert out["source_references"]["fundamental"]["sha256"] == digest
    assert hashlib.sha256(path.read_bytes()).hexdigest() == digest
    for ticker, packet in out["packets"].items():
        field = packet["sections"]["stock"]["fields"]["financial_quality_research"]
        assert field["claim"] == "DATA_WARNING" and field["value"] == out["records"][ticker]
        assert packet["capital_decision"]["value"] is None and not packet["is_actionable"]
    assert not out["records"]["POW"]["facts"] and not out["records"]["VCI"]["facts"]
    assert len(out["records"]["QNS"]["facts"]) == 1  # equity survives; Hub 9M CFO/PAT is not copied
    completed = subprocess.run([sys.executable, str(ROOT/"stocklookup.py"), "research", "financial-quality",
        "--fundamental", str(path), "--cutoff", CUTOFF, "--ticker", "PNJ", "--format", "markdown"],
        capture_output=True, text=True, encoding="utf8", errors="replace", timeout=30)
    assert completed.returncode == 0, completed.stderr
    assert "728386009054 VND" in completed.stdout and "Historical annual cash" in completed.stdout


@pytest.mark.parametrize("mutation", ["hash", "contract", "future_source", "future_field", "subject"])
def test_cli_integrity_and_source_cutoff_fail_closed(tmp_path, mutation):
    path = source(tmp_path)
    body = json.loads(path.read_bytes())
    if mutation == "hash": body["artifact_identity"] = "changed"
    elif mutation == "contract": body["contract_version"] = "hub_report/v1"
    elif mutation == "future_source": body["session_cutoff"] = "2026-10-26T15:00:00+07:00"
    elif mutation == "future_field":
        for f in body["records"]["PNJ"]["official_field_context"]: f["observed_at"] = "2026-10-23T00:00:00Z"
    elif mutation == "subject": body["records"]["PNJ"]["ticker"] = "OTHER"
    if mutation != "hash": body.update(owner.content_identity(body))
    path.write_text(json.dumps(body), encoding="utf8")
    if mutation == "future_field":
        out = cli.inspect(args(path))
        assert not out["records"]["PNJ"]["facts"] and out["records"]["PNJ"]["rejected"]
    else:
        with pytest.raises(ValueError): cli.inspect(args(path))


def test_read_changed_during_projection_cannot_publish_success(tmp_path, monkeypatch):
    path = source(tmp_path)
    hashes = iter(["before", "after"])
    monkeypatch.setattr(cli, "_digest", lambda _: next(hashes))
    with pytest.raises(ValueError, match="SOURCE_CHANGED_DURING_INSPECTION"):
        cli.inspect(args(path))


def test_a_citation_cannot_be_rebound_to_a_different_amount_or_account():
    rows = [row("net_income", 100, citation_id="same"), row("operating_cash_flow", 50, citation_id="same")]
    out = run(rows)
    assert not out["facts"] and not out["cash_conversion"]
    assert out["rejected"] == [{"citation_id": "same", "reason_codes": ["CITATION_IDENTITY_COLLISION"]}]


def test_overflowing_derived_ratio_is_refused_without_dropping_source_observations():
    out = run([row("net_income", 1e-300), row("operating_cash_flow", 1e300)])
    assert len(out["facts"]) == 2 and not out["cash_conversion"]
    assert "CASH_PROFIT_ARITHMETIC_NOT_FINITE" in json.dumps(out["rejected"])
    json.dumps(out, allow_nan=False)


def test_self_labelled_hub_oci_or_receivable_values_cannot_enter_output():
    candidate = row("net_income", -1858600000000, canonical_metric="other_comprehensive_income")
    out = run([candidate], entity="securities")
    assert not out["facts"] and not out["cash_conversion"]
    assert "1858600000000" not in json.dumps(out)
    assert "METRIC_NOT_ADMITTED_TO_QUALITY_BRIDGE" in json.dumps(out["rejected"])
