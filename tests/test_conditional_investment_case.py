"""Real retained evidence and label guards for conditional research cases."""
from __future__ import annotations

from tools.build_conditional_research_cases import build_cases
from stocklookup_core.valuation.current_valuation_denominator_integrity import diagnose_multiple


def test_retained_hpg_kbc_fpt_cases_match_their_sources():
    packet = build_cases()
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
    assert plain["display_method"] == "P/B"
    assert plain["status"] == "UNKNOWN"
