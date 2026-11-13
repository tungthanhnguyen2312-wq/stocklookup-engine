"""Real retained evidence and label guards for conditional research cases."""
from __future__ import annotations

import json

import pytest

from tools.build_conditional_research_cases import build_cases, main
from stocklookup_core.valuation.current_valuation_denominator_integrity import diagnose_multiple


@pytest.mark.retained_evidence(
    "official-financial-quarterly-intake-v1/REAL_FINANCIAL_INTAKE_CANDIDATES.json",
    "vn30-financial-metrics-unlock-20261014/work/valuation_examples.json",
)
def test_retained_hpg_kbc_fpt_cases_match_their_sources(request):
    from pathlib import Path
    from _test_tiers import retained_evidence_root
    from tools.build_conditional_research_cases import DEFAULT_FPT

    root = retained_evidence_root(Path(request.config.rootpath))
    packet = build_cases(
        intake_path=root / "official-financial-quarterly-intake-v1/REAL_FINANCIAL_INTAKE_CANDIDATES.json",
        examples_path=root / "vn30-financial-metrics-unlock-20261014/work/valuation_examples.json",
        fpt_path=DEFAULT_FPT,
    )
    assert packet["failed_expectations"] == []
    hpg = packet["cases"]["HPG"]
    assert hpg["strict_authority"]["strict_decision_eligible"] is False
    assert "not annual or TTM P/E" in " ".join(hpg["reading_notes"])
    kbc = packet["cases"]["KBC"]["bridge"]["findings"]
    assert any(item["name"] == "Q3_TOTAL_EQUALS_PARENT_PLUS_NCI" and item["residual"] == 0 for item in kbc)
    fpt = packet["cases"]["FPT"]
    assert fpt["conditional_interpretation"]["market_cap_vnd"] is None
    assert fpt["press_not_statement"] == []
    assert fpt["strict_authority"]["target_price"] is None


def test_interim_earnings_and_total_equity_are_not_strict_labels():
    interim = diagnose_multiple({
        "method_id": "P/E_TTM",
        "price": 172658624434000,
        "denominator": 15365022248705,
        "reported_period_role": "H1",
        "price_unit": "VND",
        "denominator_unit": "VND",
    })
    assert interim["display_method"] == "PRICE_OVER_REPORTED_INTERIM_EARNINGS"
    assert "INTERIM_OR_UNPROVEN_PERIOD_IS_NOT_A_TTM_PE" in interim["reason_codes"]
    assert interim["strict_valuation_use"] == "STRICT_VALUATION_QUARANTINED"
    assert interim["target_price"] is None
    book = diagnose_multiple({
        "method_id": "P/B",
        "price": 100,
        "denominator": 80,
        "equity_identity": "TOTAL_EQUITY_INCLUDING_NCI",
        "price_unit": "VND",
        "denominator_unit": "VND",
    })
    assert book["display_method"] == "PRICE_OVER_TOTAL_EQUITY_INCLUDING_NCI"
    assert "TOTAL_EQUITY_INCLUDING_NCI_IS_NOT_PARENT_BOOK_PB" in book["reason_codes"]
    plain = diagnose_multiple({
        "method_id": "P/B",
        "price": 100,
        "denominator": 50,
        "price_unit": "VND",
        "denominator_unit": "VND",
    })
    assert "display_method" not in plain
    assert plain["status"] == "UNKNOWN"


def test_supplied_inputs_cover_a_future_issuer_without_strict_authority(tmp_path):
    source = tmp_path / "issuer-inputs.json"
    source.write_text(json.dumps({"records": [
        {
            "ticker": "zzz",
            "entity": "corporate",
            "inputs": {"price": {}, "share_components": {}, "facts": {}},
        },
        {
            "ticker": "YYY",
            "entity": "corporate",
            "inputs": {
                "canonical_facts": [{
                    "metric": "revenue",
                    "value": 10,
                    "factual_status": "qualified",
                    "period": {"start": "2025-01-01", "end": "2025-12-31"},
                    "scope": "consolidated_statements",
                    "line_code": "10",
                    "currency": "VND",
                }],
                "blocked": [{
                    "canonical_metric": "attributable_net_income",
                    "reason": "OCR_NUMERIC_AMBIGUITY",
                    "raw": "9,376,1²7,6²9,501",
                }],
                "press_highlights": [{"text": "later operating commentary"}],
                "document_sha256": "abc",
                "knowledge_available_at": "2026-10-08T00:07:56.779802+00:00",
            },
        },
    ]}), encoding="utf-8")
    out_json = tmp_path / "cases.json"
    out_md = tmp_path / "cases.md"
    assert main(["--inputs", str(source), "--out-json", str(out_json), "--out-md", str(out_md)]) == 0
    packet = json.loads(out_json.read_text(encoding="utf-8"))
    assert packet["automatic_production_daily"] is False
    assert [case["ticker"] for case in packet["cases"]] == ["ZZZ", "YYY"]
    zzz = packet["cases"][0]
    assert zzz["conditional_interpretation"]["market_cap_vnd"] is None
    assert zzz["strict_authority"]["is_actionable"] is False
    assert zzz["strict_authority"]["target_price"] is None
    yyy = packet["cases"][1]
    facts = yyy["descriptive_evidence"]["canonical_facts"]
    assert [row["metric"] for row in facts] == ["revenue"]
    assert facts[0]["valuation_use"] == "NOT_PERMITTED_AUDITED_ANNUAL_CONTEXT"
    assert yyy["descriptive_evidence"]["blocked"][0]["reason"] == "OCR_NUMERIC_AMBIGUITY"
    assert yyy["press_not_statement"][0]["used_as_statement_fact"] is False
    assert yyy["conditional_interpretation"]["market_cap_vnd"] is None
    reading = out_md.read_text(encoding="utf-8")
    assert "ZZZ" in reading and "YYY" in reading
    assert "Automatic production Daily is not attached." in reading
    again = tmp_path / "cases-again.json"
    assert main(["--inputs", str(source), "--out-json", str(again), "--out-md", str(tmp_path / "cases-again.md")]) == 0
    assert again.read_bytes() == out_json.read_bytes()
