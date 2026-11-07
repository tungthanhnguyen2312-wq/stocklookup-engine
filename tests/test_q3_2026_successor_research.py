from stocklookup_core.financial.q3_2026_successor_research import (
    HPG_9M_2026_LINES, HPG_CONSOLIDATED_Q3_URL, HPG_Q3_2026_LINES, HPG_TEXT_LAYER_SNIPPET,
    hpg_consolidated_statement_shadow, income_cross_foot, issuer_blocker, source_receipt,
    text_layer_fidelity, visual_income_shadow,
)


OBSERVED_AT = "2026-11-07T10:51:54+07:00"


def test_unfaithful_text_is_not_repaired_into_a_number():
    probed = text_layer_fidelity(HPG_TEXT_LAYER_SNIPPET)
    assert probed["faithful"] is False
    assert "TEXT_LAYER_NOT_SOURCE_FAITHFUL_NO_REPAIR" in probed["reason_codes"]
    assert "value" not in probed


def test_hpg_shadow_cross_foots_and_admits_no_official_fact():
    assert income_cross_foot(HPG_Q3_2026_LINES) == []
    assert income_cross_foot(HPG_9M_2026_LINES) == []
    out = hpg_consolidated_statement_shadow(observed_at=OBSERVED_AT)
    assert out["official_fact_admitted"] is False
    assert out["official_fact_admitted_count"] == 0
    assert out["valuation_use"] == "CLOSED"
    assert out["session_binding"] == "NOT_A_SEALED_SESSION_FACT"
    assert out["publication_date"] is None
    assert out["shadow_row_count"] == 6
    periods = {row["reporting_period"] for row in out["shadow_rows"]}
    assert periods == {"2026-Q3", "2026-9M"}
    q3_revenue = next(row for row in out["shadow_rows"] if row["reporting_period"] == "2026-Q3" and row["line_code"] == "10")
    nine_revenue = next(row for row in out["shadow_rows"] if row["reporting_period"] == "2026-9M" and row["line_code"] == "10")
    assert q3_revenue["value_vnd"] != nine_revenue["value_vnd"]
    assert all(row["official_fact_admitted"] is False and row["evidence_layer"] == "VISUAL_READ_NOT_BYTE_NATIVE" for row in out["shadow_rows"])
    assert out["columns"]["2026-9M"]["nine_month_promoted_to_standalone_quarter"] is False


def test_nine_month_label_cannot_become_a_quarter():
    statement = hpg_consolidated_statement_shadow(observed_at=OBSERVED_AT)
    refused = visual_income_shadow(
        receipt={"retained_shadow": True, "ticker": "HPG", "source_url": HPG_CONSOLIDATED_Q3_URL,
                 "sha256": statement["sha256"], "byte_length": statement["byte_length"]},
        page_text=HPG_TEXT_LAYER_SNIPPET, lines=HPG_9M_2026_LINES,
        period_kind="NINE_MONTH_CUMULATIVE", period_label="2026-Q3", pdf_page=6,
    )
    assert refused["shadow_rows"] == []
    assert "NINE_MONTH_CUMULATIVE_IS_NOT_Q3_STANDALONE" in refused["reason_codes"]
    assert refused["official_fact_admitted"] is False


def test_a_broken_cross_foot_emits_nothing():
    statement = hpg_consolidated_statement_shadow(observed_at=OBSERVED_AT)
    broken = dict(HPG_Q3_2026_LINES)
    broken["10"] += 1
    refused = visual_income_shadow(
        receipt={"retained_shadow": True, "ticker": "HPG", "source_url": HPG_CONSOLIDATED_Q3_URL,
                 "sha256": statement["sha256"], "byte_length": statement["byte_length"]},
        page_text=HPG_TEXT_LAYER_SNIPPET, lines=broken,
        period_kind="Q3_STANDALONE_UNREVIEWED", period_label="2026-Q3", pdf_page=6,
    )
    assert refused["shadow_rows"] == []
    assert "LINE_10_DOES_NOT_FOOT_01_MINUS_02" in refused["reason_codes"]


def test_receipt_stays_out_of_the_official_store():
    receipt = source_receipt(
        ticker="HPG", source_url=HPG_CONSOLIDATED_Q3_URL, pdf_bytes=b"%PDF-1.6\nnot-the-filing",
        observed_at=OBSERVED_AT,
    )
    assert receipt["official_store_adoption"] == "REFUSED"
    assert receipt["official_fact_admitted"] is False
    assert receipt["retained_shadow"] is True
    assert receipt["sha256"] != statement_sha()
    other = source_receipt(ticker="PAN", source_url="https://storage.thepangroup.vn/not-a-q3.pdf",
                           pdf_bytes=b"%PDF-1.6", observed_at=OBSERVED_AT)
    assert "NO_ADMITTED_HOST_FOR_THIS_STATEMENT" in other["reason_codes"]
    assert other["retained_shadow"] is False


def statement_sha():
    return hpg_consolidated_statement_shadow(observed_at=OBSERVED_AT)["sha256"]


def test_blocker_requires_a_reason_and_admits_nothing():
    blocked = issuer_blocker(ticker="EVF", reason_codes=["NO_ADMITTED_ISSUER_IR_HOST"])
    assert blocked["official_fact_admitted"] is False
    assert blocked["exact_statement_url"] is None
    try:
        issuer_blocker(ticker="SSI", reason_codes=[])
    except ValueError as exc:
        assert "BLOCKER_REQUIRES_A_REASON" in str(exc)
    else:
        raise AssertionError("empty blocker was accepted")
