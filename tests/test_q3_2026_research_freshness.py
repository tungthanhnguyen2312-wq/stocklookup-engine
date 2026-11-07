from stocklookup_core.financial.q3_2026_research_freshness import classify_document, shadow_candidate


def test_nine_month_is_not_a_standalone_quarter():
    out = classify_document(document_kind="NINE_MONTH_CUMULATIVE", period_label="2026-Q3")
    assert out["official_fact_admitted"] is False
    assert "NINE_MONTH_CUMULATIVE_IS_NOT_Q3_STANDALONE" in out["reason_codes"]
    assert out["nine_month_promoted_to_standalone_quarter"] is False


def test_h1_duration_is_not_q3():
    out = classify_document(document_kind="H1_OR_Q2", period_label="2026-Q3")
    assert "H1_DURATION_IS_NOT_Q3" in out["reason_codes"]
    assert out["valuation_use"] == "CLOSED"


def test_press_release_is_not_a_reviewed_statement():
    row = shadow_candidate(ticker="HPG", document_kind="PRESS_RELEASE", period_label="2026-Q3", source_identity="issuer-release")
    assert row["candidate_only"] is True and row["admission_effect"] == "NONE"
    assert row["focus_cohort"] is True
    assert "PRESS_RELEASE_IS_NOT_A_REVIEWED_STATEMENT" in row["reason_codes"]


def test_reviewed_q3_stays_outside_the_current_currency_contract():
    out = classify_document(document_kind="Q3_STANDALONE_REVIEWED", period_label="2026-Q3")
    assert out["currency_refresh_in_scope"] is False
    assert out["official_fact_admitted"] is False
    assert "REVIEWED_Q3_REQUIRES_SUCCESSOR_ADMISSION_CONTRACT" in out["reason_codes"]
