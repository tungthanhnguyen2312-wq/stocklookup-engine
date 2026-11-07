from stocklookup_core.valuation.common_shareholder_book_comparison import (
    compare, earnings_quality_assessment, from_pb_diagnostic, research_dependency,
)


def test_proxy_without_parent_equity_does_not_support_cheapness():
    out = from_pb_diagnostic({
        "value": 0.4397,
        "equity_definition": "TOTAL_OWNERS_EQUITY_AS_REPORTED_INCLUDES_NCI_WHERE_PRESENT",
        "book_period": "2026-Q1",
        "numerator_value_vnd": 4_236_376_505_400,
        "denominator_value_vnd": 9_634_000_000_000,
    })
    assert out["label"] == "COMMON_SHAREHOLDER_RESEARCH"
    assert out["proxy_pb"]["value"] == 0.4397
    assert out["common_shareholder_pb"]["status"] == "UNAVAILABLE"
    assert "PARENT_EQUITY_NOT_ADMITTED" in out["common_shareholder_pb"]["reason_codes"]
    assert out["cheapness_claim"] == "NOT_SUPPORTED"
    assert out["earnings_quality"]["normalized_eps"] == "NOT_COMPUTED"


def test_parent_equity_on_a_different_period_stays_labelled():
    out = compare(
        proxy_pb=0.4397, proxy_book_period="2026-Q1",
        proxy_equity_definition="TOTAL_OWNERS_EQUITY_AS_REPORTED_INCLUDES_NCI_WHERE_PRESENT",
        parent_equity_vnd=5_558_900_000_000, parent_period="2026-Q3",
        parent_scope="EQUITY_ATTRIBUTABLE_TO_PARENT_COMMON_SHAREHOLDERS",
        parent_currency="VND", parent_knowledge_available_at="2026-10-27T00:00:00+07:00",
        price_vnd=16900, common_shares=250_673_166,
    )
    assert out["common_shareholder_pb"]["status"] == "AVAILABLE"
    assert round(out["common_shareholder_pb"]["value"], 4) == round(16900 * 250_673_166 / 5_558_900_000_000, 4)
    assert out["periods_comparable"] is False
    assert "PROXY_AND_PARENT_PERIODS_DIFFER" in out["common_shareholder_pb"]["reason_codes"] or out["periods_comparable"] is False


def test_nci_subtraction_is_not_a_parent_scope():
    out = compare(
        proxy_pb=0.44, proxy_book_period="2026-Q3",
        parent_equity_vnd=1, parent_period="2026-Q3", parent_scope="TOTAL_EQUITY_MINUS_NCI",
        parent_currency="VND", parent_knowledge_available_at="2026-10-27T00:00:00+07:00",
        price_vnd=10, common_shares=10,
    )
    assert out["common_shareholder_pb"]["status"] == "UNAVAILABLE"
    assert "PARENT_SCOPE_NOT_COMMON_SHAREHOLDER_EQUITY" in out["common_shareholder_pb"]["reason_codes"]


def test_pan_common_shareholder_research_stays_closed_without_official_inputs():
    out = research_dependency(ticker="PAN")
    assert out["common_shareholder_pb"] == "UNAVAILABLE"
    for code in (
        "PARENT_EQUITY_NOT_ADMITTED", "COMMON_SHARES_OUTSTANDING_NOT_ADMITTED",
        "TREASURY_SHARES_NOT_ADMITTED", "SHARE_COUNT_EFFECTIVE_TIME_UNKNOWN",
        "REPORTING_PERIOD_NOT_BOUND", "PRICE_BASIS_NOT_BOUND",
        "NO_EXACT_OFFICIAL_Q3_STATEMENT_URL", "NO_ADMITTED_IR_INDEX_HOST",
    ):
        assert code in out["missing"]
    quality = earnings_quality_assessment()
    assert quality["normalized_eps"] == "NOT_COMPUTED"
    assert quality["target_price"] == "NOT_EMITTED"
    assert quality["effect_on_research_pe"] == "NOT_EVALUABLE"
    assert "DISPOSAL_INCOME_NOT_ADMITTED" in quality["reason_codes"]
    assert "OPERATING_CASH_FLOW_NOT_ADMITTED" in quality["reason_codes"]
    assert "INVENTORY_NOT_ADMITTED" in quality["reason_codes"]
