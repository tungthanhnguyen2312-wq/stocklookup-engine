from pathlib import Path

from stocklookup_core.financial.q3_2026_successor_research import (
    FOOT_CODES, HPG_9M_2026_LINES, HPG_ALTERNATE_Q3_SHA256, HPG_CONSOLIDATED_Q3_SHA256,
    HPG_CONSOLIDATED_Q3_URL, HPG_Q3_2026_LINES, HPG_TEXT_LAYER_SNIPPET,
    PAN_SEPARATE_Q3_SHA256, POW_INCOME_COLUMNS, POW_OCF_COLUMNS, POW_Q3_SHA256,
    hpg_consolidated_statement_shadow, income_cross_foot, issuer_blocker, operating_cash_flow_cross_foot,
    EVF_INCOME_COLUMNS, evf_reviewed_page_research, evf_reviewed_statement_shadow,
    finance_company_income_cross_foot, pan_consolidated_statement_shadow,
    pow_consolidated_statement_shadow, pow_reviewed_page_research,
    source_receipt, ssi_consolidated_page_research, ssi_consolidated_statement_shadow,
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


def test_pow_keeps_reconciled_rows_and_rejects_the_one_dong_income_columns():
    current_quarter = dict(zip(FOOT_CODES, POW_INCOME_COLUMNS["2026-Q3"], strict=True))
    current_nine = dict(zip(FOOT_CODES, POW_INCOME_COLUMNS["2026-9M"], strict=True))
    assert current_quarter["61"] + current_quarter["62"] - current_quarter["60"] == 1
    assert current_nine["60"] - (current_nine["50"] - current_nine["51"] - current_nine["52"]) == 1
    assert income_cross_foot(current_quarter) == ["LINE_60_DOES_NOT_FOOT_61_PLUS_62"]
    assert income_cross_foot(current_nine) == ["LINE_60_DOES_NOT_FOOT_50_MINUS_51_MINUS_52"]
    assert income_cross_foot(dict(zip(FOOT_CODES, POW_INCOME_COLUMNS["2025-Q3"], strict=True))) == []
    assert income_cross_foot(dict(zip(FOOT_CODES, POW_INCOME_COLUMNS["2025-9M"], strict=True))) == []
    assert operating_cash_flow_cross_foot(POW_OCF_COLUMNS["2026-9M"]) == []
    assert operating_cash_flow_cross_foot(POW_OCF_COLUMNS["2025-9M"]) == []
    broken_cash = dict(POW_OCF_COLUMNS["2026-9M"])
    broken_cash["20"] += 1
    assert "LINE_20_DOES_NOT_FOOT_OPERATING_BRIDGE" in operating_cash_flow_cross_foot(broken_cash)


def test_pow_sha_and_scope_when_bytes_match():
    try:
        pow_consolidated_statement_shadow(pdf_bytes=b"%PDF-1.3\nnot-the-filing")
    except ValueError as exc:
        assert "POW_RETAINED_PDF_DOES_NOT_MATCH" in str(exc)
    else:
        raise AssertionError("wrong POW bytes were accepted")
    out = pow_reviewed_page_research()
    assert out["sha256"] == POW_Q3_SHA256
    assert out["official_fact_admitted"] is False
    assert out["valuation_use"] == "CLOSED"
    assert out["statement_scope"] == "consolidated"
    assert out["audit_or_review_status"] == "unreviewed"
    assert out["publication_precision"] == "DATE_ONLY"
    periods = {(row["metric"], row["period"]) for row in out["observations"]}
    assert ("revenue", "2026-Q3") not in periods
    assert ("net_income", "2026-9M") not in periods
    assert ("operating_cash_flow", "2026-9M") in periods
    assert ("operating_cash_flow", "2025-9M") in periods
    assert ("revenue", "2025-Q3") in periods
    assert len(out["observations"]) == 12
    assert out["gas_balance_is_not_cash_collection"] is True
    assert out["prior_research_lead"]["bytes_rechecked"] is False
    assert out["prior_research_lead"]["hub_memo_is_fact_authority"] is False
    amounts = {(row["metric"], row["period"]): row["value"] for row in out["observations"]}
    payable = amounts["trade_payable_pv_gas", "2026-09-30"]
    accrual = amounts["accrued_uninvoiced_gas_purchase", "2026-09-30"]
    assert payable + accrual != amounts["operating_cash_flow", "2026-9M"]
    assert all(row["value"] != 8870358006299 for row in out["observations"])
    assert out["operating_cash_flow_yoy_pct"] == -19.78
    assert out["rejected_income_columns"]["2026-Q3"] == ["LINE_60_DOES_NOT_FOOT_61_PLUS_62"]
    assert all(row["value"] != 2073116246766 for row in out["observations"])
    path = Path(r"T:\StockLookup\scratch\codex-product-gap-closeout-20261107\pow-q3-2026.pdf")
    if path.is_file():
        bound = pow_consolidated_statement_shadow(pdf_bytes=path.read_bytes())
        assert bound["observations"] == out["observations"]


def test_evf_reviewed_nine_month_rows_are_not_a_standalone_quarter_or_a_bank():
    for period in ("2026-9M", "2025-9M"):
        assert finance_company_income_cross_foot(EVF_INCOME_COLUMNS[period]) == []
    out = evf_reviewed_page_research()
    assert out["official_fact_admitted"] is False
    assert out["valuation_use"] == "CLOSED"
    assert out["entity_class"] == "finance_company"
    assert out["commercial_bank"] is False
    assert out["statement_scope"] == "separate"
    assert out["audit_or_review_status"] == "reviewed"
    assert out["standalone_quarter_column"] is False
    assert out["unit"] == "MILLION_VND"
    assert out["industrial_ratios"] == "NOT_APPLICABLE"
    assert len(out["observations"]) == 16
    assert {row["period"] for row in out["observations"]} == {"2026-9M", "2025-9M"}
    assert all(row["unit"] == "MILLION_VND" for row in out["observations"])
    assert out["net_income_yoy_pct"] == round(100 * (835339 / 736213 - 1), 2)
    assert out["pre_provision_profit_yoy_pct"] < 0
    assert out["credit_loss_provision_yoy_pct"] < 0
    try:
        evf_reviewed_statement_shadow(pdf_bytes=b"%PDF-1.3\nnot-the-filing")
    except ValueError as exc:
        assert "EVF_RETAINED_PDF_DOES_NOT_MATCH" in str(exc)
    else:
        raise AssertionError("wrong EVF bytes were accepted")
    path = Path(r"T:\StockLookup\scratch\codex-product-gap-closeout-20261107\evf-q3-2026-reviewed.pdf")
    if path.is_file():
        bound = evf_reviewed_statement_shadow(pdf_bytes=path.read_bytes())
        assert bound["observations"] == out["observations"]


def test_pan_segments_stay_on_the_consolidated_note_and_nine_month_profit_stays_rejected():
    path = Path(r"T:\StockLookup\scratch\codex-product-gap-closeout-20261107\pan-q3-2026.pdf")
    separate = Path(r"T:\StockLookup\scratch\grok-weekend-continuation-20261107\pan-q3-2026-separate.pdf")
    if not path.is_file():
        return
    out = pan_consolidated_statement_shadow(pdf_bytes=path.read_bytes())
    amounts = {(row["metric"], row["period"]): row["value"] for row in out["observations"]}
    assert amounts["segment_external_revenue_total", "2026-9M"] == 11431754137920
    assert out["rejected_income_columns"]["2026-9M"]
    assert ("attributable_net_income", "2026-9M") not in amounts
    assert out["holding_cash_sha256"] is None
    assert out["prior_research_lead"]["bytes_rechecked"] is True
    assert out["prior_research_lead"]["hub_memo_is_fact_authority"] is False
    if separate.is_file():
        bound = pan_consolidated_statement_shadow(
            pdf_bytes=path.read_bytes(), separate_pdf_bytes=separate.read_bytes(),
        )
        holding = {(row["metric"], row["period"]): row for row in bound["observations"]}
        assert holding["holding_cash_and_equivalents", "2026-09-30"]["value"] == 19968968615
        assert holding["holding_cash_and_equivalents", "2026-09-30"]["source_sha256"] == PAN_SEPARATE_Q3_SHA256
        assert bound["holding_company_short_term_borrowing"] == "OCR_DIGIT_AMBIGUOUS_NOT_EMITTED"


def test_ssi_rows_are_securities_research_and_reject_a_different_hash():
    out = ssi_consolidated_page_research()
    amounts = {(row["metric"], row["period"]): row["value"] for row in out["observations"]}
    assert out["entity_class"] == "securities"
    assert out["industrial_ratios"] == "NOT_APPLICABLE"
    assert out["official_fact_admitted"] is False
    assert out["official_store_adoption"] == "REFUSED"
    assert out["nine_month_profit_after_tax"] == "OCR_DIGIT_AMBIGUOUS_NOT_EMITTED"
    assert amounts["net_income", "2026-Q3"] == amounts["pretax_profit", "2026-Q3"] - amounts["income_tax", "2026-Q3"]
    assert amounts["brokerage_revenue", "2026-Q3"] == 348933594669
    assert out["prior_research_lead"]["done_label_is_product_verified"] is False
    assert out["sha256"] == "caa48d6f0ec4122c12ba69f1c1c6a71c84cb8c53fec3ea57ce6f3655eaee2d09"
    try:
        ssi_consolidated_statement_shadow(pdf_bytes=b"%PDF-1.4\nnot-the-filing")
    except ValueError as exc:
        assert "SSI_RETAINED_PDF_DOES_NOT_MATCH" in str(exc)
    else:
        raise AssertionError("wrong SSI bytes were accepted")
    path = Path(r"T:\StockLookup\scratch\grok-weekend-continuation-20261107\ssi-q3-2026-consolidated.pdf")
    if path.is_file():
        assert ssi_consolidated_statement_shadow(pdf_bytes=path.read_bytes())["observations"] == out["observations"]


def test_hpg_alternate_pdf_does_not_replace_the_retained_statement():
    out = hpg_consolidated_statement_shadow(observed_at=OBSERVED_AT)
    assert out["sha256"] == HPG_CONSOLIDATED_Q3_SHA256
    assert out["shadow_row_count"] == 6
    assert out["alternate_document"]["retained_source_replaced"] is False
    assert out["alternate_document"]["bytes_rechecked"] is False
    assert out["alternate_document"]["reported_sha256"] == HPG_ALTERNATE_Q3_SHA256
    assert out["alternate_document"]["pdf_creation_is_not_a_pit_clock"] is True
    path = Path(r"T:\StockLookup\scratch\grok-weekend-continuation-20261107\hpg-q3-20261029-consolidated.pdf")
    if path.is_file():
        bound = hpg_consolidated_statement_shadow(observed_at=OBSERVED_AT, alternate_pdf_bytes=path.read_bytes())
        assert bound["sha256"] == HPG_CONSOLIDATED_Q3_SHA256
        assert bound["alternate_document"]["bytes_rechecked"] is True
        assert bound["shadow_rows"] == out["shadow_rows"]


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
