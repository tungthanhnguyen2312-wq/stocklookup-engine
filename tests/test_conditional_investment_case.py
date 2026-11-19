"""Real retained evidence and label guards for conditional research cases."""
from __future__ import annotations

import json

import pytest

from tools.build_conditional_research_cases import build_cases, main
from stocklookup_core.valuation.conditional_research_valuation import diagnose_conditional_multiple


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
    interim = diagnose_conditional_multiple({
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
    book = diagnose_conditional_multiple({
        "method_id": "P/B",
        "price": 100,
        "denominator": 80,
        "equity_identity": "TOTAL_EQUITY_INCLUDING_NCI",
        "price_unit": "VND",
        "denominator_unit": "VND",
    })
    assert book["display_method"] == "PRICE_OVER_TOTAL_EQUITY_INCLUDING_NCI"
    assert "TOTAL_EQUITY_INCLUDING_NCI_IS_NOT_PARENT_BOOK_PB" in book["reason_codes"]
    plain = diagnose_conditional_multiple({
        "method_id": "P/B",
        "price": 100,
        "denominator": 50,
        "price_unit": "VND",
        "denominator_unit": "VND",
    })
    assert "display_method" not in plain
    assert plain["status"] == "UNKNOWN"


def test_statement_cohort_reaches_the_research_case_consumer(tmp_path):
    from stocklookup_core.research.conditional_investment_case import build_statement_research_cohort

    first = build_statement_research_cohort()
    second = build_statement_research_cohort()
    assert first == second
    assert first["official_fact_admitted"] is False
    assert first["coverage"]["official_fact_admitted_count"] == 0
    assert first["coverage"]["valuation_measures_usable"] == 0
    assert first["coverage"]["ttm_measures_usable"] == 0
    assert first["coverage"]["current_research_usable"] > 0
    assert first["families"]["BANK"] == []
    assert first["ordinal_rank"] is None
    usable = {(row["ticker"], row["period"], row["metric"]) for row in first["measures"] if row["status"] == "USABLE"}
    blocked = {(row["ticker"], row["period"], row["metric"]) for row in first["measures"] if row["status"] != "USABLE"}
    assert ("HPG", "2026-Q3", "parent_profit_after_tax") in usable
    assert ("HPG", "2026-9M", "parent_profit_after_tax") in usable
    assert ("HPG", "2026-Q3_VS_2025-Q3", "net_revenue_yoy") in blocked
    assert ("PAN", "2026-9M", "parent_profit_after_tax") in blocked
    assert ("PAN", "2026-Q3", "parent_profit_after_tax") in usable
    assert ("POW", "2026-9M", "operating_cash_flow") in usable
    assert ("POW", "2026-Q3", "operating_cash_flow") not in usable
    assert ("SSI", "2026-Q3", "industrial_profit_margin") in blocked
    assert ("SSI", "2026-9M", "profit_after_tax") in blocked
    assert ("EVF", "2026-Q3", "net_income") in blocked
    assert ("EVF", "2026-9M", "net_income") in usable
    hpg_parent = next(row for row in first["measures"]
                      if row["ticker"] == "HPG" and row["period"] == "2026-Q3" and row["metric"] == "parent_profit_after_tax")
    hpg_group = next(row for row in first["measures"]
                     if row["ticker"] == "HPG" and row["period"] == "2026-Q3" and row["metric"] == "group_profit_after_tax")
    assert hpg_parent["value"] != hpg_group["value"]
    assert hpg_parent["official_fact_admitted"] is False
    assert hpg_parent["use_scope"] == "CURRENT_RESEARCH"
    evf = next(row for row in first["measures"] if row["ticker"] == "EVF" and row["metric"] == "net_income" and row["status"] == "USABLE")
    assert evf["unit"] == "MILLION_VND"
    assert evf["statement_scope"] == "separate"
    assert {row["ticker"] for row in first["readings"]["industrial_q3_parent_profit_margin"]} == {"HPG", "PAN"}
    assert "SSI" not in {row["ticker"] for row in first["readings"]["industrial_q3_parent_profit_margin"]}
    assert "POW" not in {row["ticker"] for row in first["readings"]["industrial_q3_parent_profit_margin"]}
    cash = first["readings"]["pow_nine_month_cash_conversion"]
    assert cash["identity"] == "NINE_MONTH_OPERATING_CASH_FLOW_OVER_GROUP_PROFIT_AFTER_TAX"
    assert cash["status"] == "NOT_COMPUTED"
    assert cash["not_parent_cash_conversion"] is True
    assert first["readings"]["pow_nine_month_operating_cash_flow_yoy"]["status"] == "COMPUTED"
    assert first["readings"]["pow_prior_nine_month_cash_conversion"]["status"] == "COMPUTED"
    assert first["readings"]["pow_prior_nine_month_cash_conversion"]["period"] == "2025-9M"
    residuals = {(row["ticker"], row["period"]): row for row in first["readings"]["industrial_identity_residuals"]}
    assert residuals["POW", "2026-Q3"]["group_minus_parent_and_nci_vnd"] == -1
    assert residuals["POW", "2026-9M"]["group_minus_pretax_bridge_vnd"] == 1
    assert residuals["PAN", "2026-9M"]["group_minus_parent_and_nci_vnd"] == 1
    assert ("HPG", "2026-Q3") not in residuals
    pan = first["readings"]["pan_segment_versus_rejected_income_line"]
    assert pan["income_column_status"] == "REJECTED"
    assert pan["difference_vnd"] != 0
    evf_yoy = first["readings"]["evf_nine_month_yoy_percent"]
    assert evf_yoy["net_income"] > 0
    assert evf_yoy["pre_provision_profit"] < 0
    assert evf_yoy["credit_loss_provision"] < 0
    out_json = tmp_path / "cohort.json"
    out_md = tmp_path / "cohort.md"
    assert main(["--statement-cohort", "--out-json", str(out_json), "--out-md", str(out_md)]) == 0
    written = json.loads(out_json.read_text(encoding="utf-8"))
    assert written["cohort_identity"] == first["cohort_identity"]
    assert first["cohort_identity"] == "current_statement_research_cohort:0b691549cd1638c0599b46a6f0456b7e0613cd8a71037acac5ba5aa5a7070dc6"
    text = out_md.read_text(encoding="utf-8")
    assert "Official facts: 0" in text
    assert "not a score or a valuation" in text


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

@pytest.fixture
def reviewed_packet(tmp_path):
    from hashlib import sha256
    from pathlib import Path

    path = Path(__file__).resolve().parents[1] / "docs/internal/FINANCIAL_EVIDENCE_PACKET_20261113.json"
    packet = json.loads(path.read_bytes())
    documents = {}
    sources = {}
    replacements = {}
    for index, (digest, source) in enumerate(packet["documents"].items()):
        original = tmp_path / f"source-{index}.pdf"
        original.write_bytes(f"synthetic original {index}".encode())
        fake = sha256(original.read_bytes()).hexdigest()
        replacements[digest] = fake
        documents[fake] = source
        sources[fake] = original.name
    for row in packet["rows"] + list(packet["basis_limits"].values()):
        for field in ("document_sha256", "corroborating_document_sha256"):
            if field in row:
                row[field] = replacements[row[field]]
    packet["documents"] = documents
    return packet, sources


def _reviewed_files(tmp_path, packet, sources):
    from hashlib import sha256

    path = tmp_path / "packet.json"
    path.write_text(json.dumps(packet), encoding="utf-8")
    source_map = tmp_path / "sources.json"
    source_map.write_text(json.dumps(sources), encoding="utf-8")
    return path, source_map, sha256(path.read_bytes()).hexdigest()


def test_reviewed_packet_renders_stable_research_cases(tmp_path, reviewed_packet):
    from tools.build_conditional_research_cases import build_reviewed_packet, render_reviewed_markdown

    path, source_map, sha = _reviewed_files(tmp_path, *reviewed_packet)
    result = build_reviewed_packet(path, source_map, expected_sha256=sha)
    assert result == build_reviewed_packet(path, source_map, expected_sha256=sha)
    assert result["row_count"] == 39
    assert result["automatic_production_daily"] is False
    hpg, kbc, fpt = (result["cases"][ticker] for ticker in ("HPG", "KBC", "FPT"))
    bridge = hpg["parent_earnings"]["ttm"]
    assert bridge["value_vnd"] == 27446445485211
    assert len(bridge["inputs"]) == 3
    assert bridge["fitness"] == "CONDITIONAL_RESEARCH"
    assert "PRESENTATION_BASIS_DIFFERS_ACROSS_BRIDGE" in bridge["basis_caveats"]
    assert all(row["evidence_quality"] == "SCANNED_PAGE_VISUAL_CROSS_FOOT" for row in bridge["inputs"])
    assert any("OCR" in row["evidence_quality"] and row["calculation_state"] == "CANDIDATE_EXCLUDED_FROM_CALCULATION"
               for row in hpg["evidence_rows"])
    assert kbc["parent_earnings"]["ttm"] is None
    assert "KBC_RECLASSIFIED_COMPARATIVE_AND_OCR_INPUTS" in kbc["parent_earnings"]["reason_codes"]
    assert kbc["metrics_by_period"]["2025"]["operating_cash_less_printed_purchases"]["value_vnd"] == -17473940490632
    assert kbc["metrics_by_period"]["2025"]["cash_to_parent_profit"]["ratio"].startswith("-8.244")
    assert all(row["calculation_state"] == "REVIEWED_RESEARCH" for row in kbc["evidence_rows"] if row["evidence_quality"].startswith("NATIVE"))
    assert fpt["parent_earnings"]["ttm"] is None
    assert fpt["metrics_by_period"]["2025-12-31"]["derived_parent_equity"]["value_vnd"] == 36480193944772
    assert fpt["metrics_by_period"]["2025"]["cash_to_parent_profit"]["scope_warning"]
    for case in result["cases"].values():
        assert all(case["valuation"][key] is None for key in ("price_vnd_per_share", "market_cap_vnd", "pe_ttm", "pb_parent", "ev_ebitda"))
        assert not any(case["strict_authority"].values())
    md = render_reviewed_markdown(result)
    assert "27,446,445,485,211 VND" in md
    for prefix in ("first", "second"):
        assert main(["--reviewed-packet", str(path), "--source-map", str(source_map), "--packet-sha256", sha,
                     "--out-json", str(tmp_path / f"{prefix}.json"), "--out-md", str(tmp_path / f"{prefix}.md")]) == 0
    for suffix in ("json", "md"):
        assert (tmp_path / f"first.{suffix}").read_bytes() == (tmp_path / f"second.{suffix}").read_bytes()


@pytest.mark.parametrize("failure,reason", [
    ("packet_pin", "PACKET_SHA256_MISMATCH"),
    ("wrong_bytes", "SOURCE_SHA256_MISMATCH"),
    ("missing_file", "SOURCE_MISSING"),
    ("missing_mapping", "SOURCE_MAP_MISMATCH"),
    ("truncated", "SOURCE_SHA256_INVALID"),
    ("wrong_row_digest", "ROW_SOURCE_UNBOUND"),
    ("ocr_as_native", "SCANNED_SOURCE_CANNOT_BE_NATIVE"),
])
def test_reviewed_packet_fails_closed_on_source_mismatch(tmp_path, reviewed_packet, failure, reason):
    from tools.build_conditional_research_cases import build_reviewed_packet

    packet, sources = reviewed_packet
    digest = next(iter(sources))
    original = tmp_path / sources[digest]
    if failure == "wrong_bytes":
        original.write_bytes(b"wrong bytes")
    elif failure == "missing_file":
        original.unlink()
    elif failure == "missing_mapping":
        sources.pop(digest)
    elif failure == "truncated":
        packet["documents"][digest[:12]] = packet["documents"].pop(digest)
        sources[digest[:12]] = sources.pop(digest)
    elif failure == "wrong_row_digest":
        packet["rows"][0]["document_sha256"] = "0" * 64
    elif failure == "ocr_as_native":
        packet["rows"][0]["evidence_quality"] = "NATIVE_TEXT"
    path, source_map, sha = _reviewed_files(tmp_path, packet, sources)
    with pytest.raises(ValueError, match=reason):
        build_reviewed_packet(path, source_map, expected_sha256="0" * 64 if failure == "packet_pin" else sha)


@pytest.mark.parametrize("knowledge", [None, "not a date", "2026-11-14T00:00:00+07:00"])
def test_hpg_missing_or_future_reviewed_leg_leaves_ttm_incomplete(tmp_path, reviewed_packet, knowledge):
    from tools.build_conditional_research_cases import build_reviewed_packet

    packet, sources = reviewed_packet
    packet["rows"][0]["knowledge_available_at"] = knowledge
    path, source_map, sha = _reviewed_files(tmp_path, packet, sources)
    hpg = build_reviewed_packet(path, source_map, expected_sha256=sha)["cases"]["HPG"]
    assert hpg["parent_earnings"]["ttm"] is None
    assert hpg["evidence_rows"][0]["calculation_state"].startswith("KNOWLEDGE_")


def test_reviewed_fpt_equity_rejects_old_code_400_and_bad_cross_foot(tmp_path, reviewed_packet):
    from stocklookup_core.valuation.conditional_research_valuation import derive_parent_equity_research

    packet, _ = reviewed_packet
    fpt = [row for row in packet["rows"] if row["ticker"] == "FPT"]
    total = next(row for row in fpt if row.get("line_code") == "410")
    nci = next(row for row in fpt if row.get("line_code") == "429")
    old = {**total, "line_code": "400", "normalized_integer": 43748040747539,
           "accounting_identity": "TOTAL_EQUITY_INCLUDING_NCI"}
    assert derive_parent_equity_research(old, nci)["value_vnd"] is None
    assert derive_parent_equity_research(total, {**nci, "normalized_integer": 1})["value_vnd"] is None
    assert derive_parent_equity_research(total, nci)["value_vnd"] == 36480193944772


def test_reviewed_kbc_basis_and_cash_scope_gates(tmp_path, reviewed_packet):
    from stocklookup_core.valuation.conditional_research_valuation import (
        printed_cash_to_earnings,
        trailing_twelve_month_earnings,
    )

    packet, _ = reviewed_packet
    kbc = [row for row in packet["rows"] if row["ticker"] == "KBC"]
    bridge = trailing_twelve_month_earnings(kbc, identity="PARENT_PROFIT_AFTER_TAX")
    assert bridge["ttm"] is None
    assert "PRESENTATION_BASIS_DIFFERS_ACROSS_BRIDGE" in bridge["reason_codes"]
    annual_profit = next(row for row in kbc if row["accounting_identity"] == "PARENT_PROFIT_AFTER_TAX")
    annual_cash = next(row for row in kbc if row["accounting_identity"] == "OPERATING_CASH_FLOW")
    for changes in ({"statement_scope": "separate"}, {"months": 9}, {"currency": "USD"},
                    {"document_sha256": "0" * 64}, {"unit_scale": 1000}):
        assert printed_cash_to_earnings(annual_profit, {**annual_cash, **changes})["ratio"] is None


def _structured_row(**overrides):
    row = {
        "ticker": "ZZZ",
        "period_label": "9 tháng/2026",
        "consolidation": "Hợp nhất",
        "audit_status": "Chưa kiểm toán",
        "unit": "Đơn vị tính: 1 VNĐ",
        "item": "3. Doanh thu thuần về bán hàng và cung cấp dịch vụ",
        "value": "1000",
        "statement": "IS",
        "source": "EXAMPLE_EXPORT",
        "source_file": "example.xlsx",
        "source_sha256": "a" * 64,
        "period_year": "2026",
        "period_kind": "9M",
        "period_basis": "cumulative_ytd",
        "vendor_publish_date": "2020-01-01",
        "vendor_data_updated": "Ngày cập nhật: 16/11/2026",
        "is_blank": "false",
    }
    row.update(overrides)
    return row


def _write_structured(path, rows):
    path.write_text(json.dumps({"observations": rows}, ensure_ascii=False), encoding="utf-8")
    return path


def _metric(packet, ticker, period, metric):
    found = [row for row in packet["measures"] if row["ticker"] == ticker and row["period"] == period and row["metric"] == metric]
    assert len(found) == 1, (ticker, period, metric, len(found))
    return found[0]


def test_structured_input_is_deterministic_and_keeps_conflict_and_templates(tmp_path):
    from stocklookup_core.research.conditional_investment_case import build_structured_financial_research

    industrial = "3. Doanh thu thuần về bán hàng và cung cấp dịch vụ"
    gross = "5. Lợi nhuận gộp về bán hàng và cung cấp dịch vụ"
    parent = "Lợi nhuận sau thuế của cổ đông của Công ty mẹ"
    rows = [
        _structured_row(item=industrial, value="1000"),
        _structured_row(item=gross, value="400"),
        _structured_row(item=parent, value="100"),
        _structured_row(period_label="9 tháng/2025", period_year="2025", item=industrial, value="800"),
        _structured_row(ticker="YYY", item=industrial, value="500", source_sha256="b" * 64),
        _structured_row(ticker="YYY", item=gross, value="100", source_sha256="b" * 64),
        _structured_row(ticker="YYY", item=parent, value="50", source_sha256="b" * 64),
        _structured_row(ticker="QQQ", item="1.6. Doanh thu môi giới chứng khoán", value="10", source_sha256="c" * 64),
        _structured_row(ticker="QQQ", item="Doanh thu thuần", value="70", source_sha256="c" * 64),
        _structured_row(ticker="BBB", item="XV. Lợi nhuận sau thuế của cổ đông của Ngân hàng mẹ (XIII-XIV)", value="9", source_sha256="d" * 64),
        _structured_row(ticker="BBB", item="I. Thu nhập lãi thuần (1-2)", value="20", source_sha256="d" * 64),
        _structured_row(ticker="MIX", item=industrial, value="5", source_sha256="e" * 64),
        _structured_row(ticker="MIX", item="XV. Lợi nhuận sau thuế của cổ đông của Ngân hàng mẹ (XIII-XIV)", value="6", source_sha256="e" * 64),
        _structured_row(item="bad-row", value="not-a-number", statement="IS"),
        _structured_row(ticker="BAD", consolidation="Khác", item=industrial, value="1"),
    ]
    for suffix, value in (("Q1", 1), ("Q2", 2), ("Q3", 3), ("Q4", 4)):
        rows.append(_structured_row(
            period_label=f"Quý {suffix[-1]}/2026", period_kind=suffix, period_basis="quarterly_discrete",
            item=parent, value=str(value),
        ))
    path = _write_structured(tmp_path / "input.json", rows)
    first = build_structured_financial_research(path)
    second = build_structured_financial_research(path)
    assert first == second
    assert first["official_fact_admitted"] is False
    assert first["coverage"]["official_fact_admitted_count"] == 0
    assert first["coverage"]["valuation_measures_usable"] == 0
    assert first["coverage"]["ttm_measures_usable"] == 0
    assert first["publication_time"] is None
    assert first["file_modification_time_used"] is False
    assert first["consumers"]["ai_research_preview"]["daily_packet_activated"] is False
    assert first["financial_v2_authority_unchanged"] == "2026-09-05.1"
    margin = _metric(first, "ZZZ", "2026-9M", "parent_profit_margin")
    assert margin["status"] == "USABLE"
    assert margin["value"] == "0.100000"
    assert margin["numerator"] == 100
    assert margin["denominator"] == 1000
    yoy = _metric(first, "ZZZ", "2026-9M_VS_2025-9M", "net_revenue_yoy")
    assert yoy["status"] == "USABLE"
    assert yoy["value"] == "25.00"
    assert {row["ticker"] for row in first["comparisons"][0]["rows"]} >= {"YYY", "ZZZ"}
    assert _metric(first, "QQQ", "UNSET", "industrial_profit_margin")["status"] == "NOT_APPLICABLE"
    assert not any(row["ticker"] == "QQQ" and row["metric"] == "gross_margin" and row["status"] == "USABLE" for row in first["measures"])
    securities_revenue = _metric(first, "QQQ", "2026-9M", "securities_net_revenue")
    assert securities_revenue["original_label"] == "Doanh thu thuần"
    assert securities_revenue["metric"] != "net_revenue"
    assert _metric(first, "BBB", "UNSET", "industrial_profit_margin")["status"] == "NOT_APPLICABLE"
    assert not any(row["ticker"] == "BBB" and row["metric"] == "gross_margin" for row in first["measures"])
    assert first["families"]["MIXED_STATEMENT"] == ["MIX"]
    assert not any(row["ticker"] == "MIX" and row["metric"] == "parent_profit_margin" and row["status"] == "USABLE" for row in first["measures"])
    quarter_sum = _metric(first, "ZZZ", "2026-FOUR_DISCRETE_QUARTERS", "parent_profit_after_tax_four_discrete_quarter_sum")
    assert quarter_sum["value"] == 10
    assert quarter_sum["annualized"] is False
    assert quarter_sum["ttm"] is False
    assert _metric(first, "ZZZ", "TTM", "profit_after_tax_ttm")["status"] == "BLOCKED"
    assert not any(row["value"] == 120 for row in first["measures"])
    assert first["rejections"]["count"] == 2
    source = open(
        __import__("stocklookup_core.research.conditional_investment_case", fromlist=["build_structured_financial_research"]).build_structured_financial_research.__code__.co_filename,
        encoding="utf-8",
    ).read().split("def build_structured_financial_research", 1)[1]
    for ticker in ("HPG", "PAN", "POW", "SSI", "EVF", "FPT", "VCB", "MBB", "VNM", "ZZZ"):
        assert f'"{ticker}"' not in source
        assert f"'{ticker}'" not in source


def test_structured_conflict_cutoff_and_revision_do_not_overwrite(tmp_path):
    import os
    from stocklookup_core.research.conditional_investment_case import build_structured_financial_research

    label = "3. Doanh thu thuần về bán hàng và cung cấp dịch vụ"
    conflict = _write_structured(tmp_path / "conflict.json", [
        _structured_row(item=label, value="100", source_sha256="a" * 64, source_file="first.xlsx"),
        _structured_row(item=label, value="120", source_sha256="b" * 64, source_file="second.xlsx"),
    ])
    packet = build_structured_financial_research(conflict)
    row = _metric(packet, "ZZZ", "2026-9M", "net_revenue")
    assert row["status"] == "CONFLICT"
    assert row["value"] is None
    assert {item["value"] for item in row["retained_originals"]} == {100, 120}
    assert row["official_fact_admitted"] is False

    single = _write_structured(tmp_path / "single.json", [_structured_row(item=label, value="100")])
    early = build_structured_financial_research(
        single, knowledge_cutoff="2026-11-01T00:00:00+07:00", observed_at="2026-10-01T00:00:00+07:00",
    )
    usable = _metric(early, "ZZZ", "2026-9M", "net_revenue")
    assert usable["status"] == "USABLE"
    assert usable["publication_time"] is None
    assert usable["available_at_cutoff"] is True
    assert usable["vendor_supplied_dates"] == ["2020-01-01"]
    late = build_structured_financial_research(
        single, knowledge_cutoff="2026-11-01T00:00:00+07:00", observed_at="2026-11-02T00:00:00+07:00",
    )
    assert _metric(late, "ZZZ", "2026-9M", "net_revenue")["status"] == "BLOCKED"
    assert _metric(late, "ZZZ", "2026-9M", "net_revenue")["value"] == 100
    assert late["research_identity"] != early["research_identity"]
    missing_clock = build_structured_financial_research(single, knowledge_cutoff="2026-11-01T00:00:00+07:00")
    assert _metric(missing_clock, "ZZZ", "2026-9M", "net_revenue")["status"] == "BLOCKED"
    assert missing_clock["temporal_status"] == "OBSERVATION_TIME_ABSENT"
    before = build_structured_financial_research(single)
    os.utime(single, (1_700_000_000, 1_700_000_000))
    assert build_structured_financial_research(single) == before

    revised = _write_structured(tmp_path / "revised.json", [_structured_row(item=label, value="130", source_sha256="c" * 64)])
    out_json = tmp_path / "first.json"
    out_md = tmp_path / "first.md"
    assert main(["--structured-input", str(single), "--out-json", str(out_json), "--out-md", str(out_md)]) == 0
    snapshot = out_json.read_bytes()
    second_json = tmp_path / "second.json"
    second_md = tmp_path / "second.md"
    assert main(["--structured-input", str(revised), "--out-json", str(second_json), "--out-md", str(second_md)]) == 0
    assert out_json.read_bytes() == snapshot
    first_packet = json.loads(snapshot)
    second_packet = json.loads(second_json.read_text(encoding="utf-8"))
    assert first_packet["input_sha256"] != second_packet["input_sha256"]
    assert first_packet["research_identity"] != second_packet["research_identity"]
    assert _metric(second_packet, "ZZZ", "2026-9M", "net_revenue")["value"] == 130
    with pytest.raises(SystemExit):
        main(["--structured-input", str(tmp_path / "missing-header.csv"), "--out-json", str(tmp_path / "bad.json"), "--out-md", str(tmp_path / "bad.md")])


def test_structured_malformed_header_is_rejected(tmp_path):
    from stocklookup_core.research.conditional_investment_case import build_structured_financial_research

    path = tmp_path / "broken.csv"
    path.write_text("ticker,value\nZZZ,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="STRUCTURED_INPUT_HEADER_MISSING"):
        build_structured_financial_research(path)
    whole = _write_structured(tmp_path / "whole.json", [_structured_row(value="1000.0")])
    accepted = build_structured_financial_research(whole)
    assert _metric(accepted, "ZZZ", "2026-9M", "net_revenue")["value"] == 1000
    assert _metric(accepted, "ZZZ", "2026-9M", "net_revenue")["native_representation"] == ["1000.0"]
    fraction = _write_structured(tmp_path / "fraction.json", [_structured_row(value="1000.5")])
    assert build_structured_financial_research(fraction)["rejections"]["count"] == 1


def test_real_vietstock_export_reaches_research_without_issuer_constants():
    import hashlib
    from pathlib import Path
    from stocklookup_core.research.conditional_investment_case import (
        build_statement_research_cohort,
        build_structured_financial_research,
    )

    path = Path(r"C:\Projects\StockLookup\.stocklookup\scratch\q3-financial-evidence-20261118\vietstock_expansion_20261116_002\expansion_20261116_002\normalized_long_dedup_v2.csv")
    if not path.is_file():
        pytest.skip("RETAINED_VIETSTOCK_EXPORT_ABSENT")
    packet = build_structured_financial_research(path)
    again = build_structured_financial_research(path)
    assert packet == again
    assert packet["input_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert packet["official_fact_admitted"] is False
    assert packet["coverage"]["valuation_measures_usable"] == 0
    assert packet["coverage"]["ttm_measures_usable"] == 0
    assert packet["coverage"]["issuer_count"] >= 13
    assert packet["coverage"]["current_research_usable"] > 95
    assert packet["publication_time"] is None
    assert "FPT" in packet["families"]["INDUSTRIAL_STATEMENT"]
    assert "VCB" in packet["families"]["BANK_STATEMENT"]
    assert "SSI" in packet["families"]["SECURITIES_STATEMENT"]
    assert "EVF" in packet["families"]["BANK_STATEMENT"]
    cohort = build_statement_research_cohort()
    vendor = _metric(packet, "HPG", "2026-Q3", "parent_profit_margin")
    retained = next(row for row in cohort["measures"] if row["ticker"] == "HPG" and row["period"] == "2026-Q3" and row["metric"] == "parent_profit_margin")
    assert vendor["status"] == "USABLE"
    assert vendor["value"] == retained["value"]
    assert vendor["numerator"] == retained["numerator"]
    assert vendor["denominator"] == retained["denominator"]
    assert vendor["statement_scope"] == "consolidated"
    assert vendor["unit"] == "RATIO"
    revenue = _metric(packet, "HPG", "2026-Q3", "net_revenue")
    assert revenue["value"] == retained["denominator"]
    assert revenue["official_fact_admitted"] is False
    assert revenue["historical_pit"] == "UNKNOWN"
    q3_yoy = _metric(packet, "HPG", "2026-Q3_VS_2025-Q3", "net_revenue_yoy")
    assert q3_yoy["status"] == "BLOCKED"
    assert "PRIOR_REPORTED_PERIOD_ABSENT" in q3_yoy["reason_codes"]
    evf = _metric(packet, "EVF", "2026-9M", "group_profit_after_tax")
    retained_evf = next(row for row in cohort["measures"] if row["ticker"] == "EVF" and row["metric"] == "net_income" and row["status"] == "USABLE")
    assert evf["status"] == "USABLE"
    assert evf["unit"] == "VND"
    assert evf["unit_scale"] == 1
    assert evf["statement_scope"] == "consolidated"
    assert retained_evf["statement_scope"] == "separate"
    assert evf["analysis_family"] == "BANK_STATEMENT"
    assert not any(row["metric"] == "research_multiple" and row["status"] == "USABLE" for row in packet["measures"])
    assert not any(row["annualized"] for row in packet["measures"])


def _ai_row(ticker, item, value, *, year="2026", kind="9M", scope="Hợp nhất", unit="Đơn vị tính: 1 VNĐ", sha="a" * 64, statement="IS"):
    basis = "cumulative_ytd" if kind in {"6M", "9M", "FY"} else "quarterly_discrete"
    label = f"Quý {kind[-1]}/{year}" if kind.startswith("Q") else f"{kind}/{year}"
    return _structured_row(
        ticker=ticker, item=item, value=str(value), period_label=label, period_year=str(year),
        period_kind=kind, period_basis=basis, consolidation=scope, unit=unit, statement=statement,
        source_sha256=sha, source_file="PRIVATE_BOX_EXPORT_TOKEN.xlsx",
    )


_REV = "3. Doanh thu thuần về bán hàng và cung cấp dịch vụ"
_GROSS = "5. Lợi nhuận gộp về bán hàng và cung cấp dịch vụ"
_PARENT = "Lợi nhuận sau thuế của cổ đông của Công ty mẹ"
_GROUP = "18. Lợi nhuận sau thuế thu nhập doanh nghiệp"
_OCF = "Lưu chuyển tiền thuần từ hoạt động kinh doanh"
_ASSETS = "TỔNG CỘNG TÀI SẢN"
_LIAB = "C. NỢ PHẢI TRẢ"
_CASH = "I. Tiền và các khoản tương đương tiền"


def _ai_packet(tmp_path):
    from stocklookup_core.research.conditional_investment_case import build_structured_financial_research

    rows = []
    for ticker, parent, gross, cash in (("AAA", 100, 400, 40), ("BBB", 50, 100, -5)):
        for year in ("2025", "2026"):
            for kind in ("Q3", "9M"):
                revenue = 1000 if ticker == "AAA" else 500
                rows.extend([
                    _ai_row(ticker, _REV, revenue, year=year, kind=kind),
                    _ai_row(ticker, _GROSS, gross, year=year, kind=kind),
                    _ai_row(ticker, _PARENT, parent, year=year, kind=kind),
                    _ai_row(ticker, _GROUP, parent, year=year, kind=kind, statement="IS"),
                    _ai_row(ticker, _OCF, cash, year=year, kind=kind, statement="CF"),
                    _ai_row(ticker, _ASSETS, 1000, year=year, kind=kind, statement="BS"),
                    _ai_row(ticker, _LIAB, 400 if year == "2025" else 700, year=year, kind=kind, statement="BS"),
                    _ai_row(ticker, _CASH, 200, year=year, kind=kind, statement="BS"),
                ])
    rows.append(_ai_row("AAA", "11. Vay và nợ thuê tài chính ngắn hạn", 10, kind="Q3", statement="BS"))
    rows.append(_ai_row("AAA", _PARENT, 999, kind="Q3", scope="Công ty mẹ"))
    rows.append(_ai_row("AAA", _REV, 1000, kind="Q3", scope="Công ty mẹ"))
    rows.append(_ai_row("CCC", "XV. Lợi nhuận sau thuế của cổ đông của Ngân hàng mẹ (XIII-XIV)", 9, kind="Q3", sha="d" * 64))
    rows.append(_ai_row("CCC", "I. Thu nhập lãi thuần (1-2)", 20, kind="Q3", sha="d" * 64))
    rows.append(_ai_row("QQQ", "1.6. Doanh thu môi giới chứng khoán", 10, kind="9M", sha="c" * 64))
    rows.append(_ai_row("QQQ", "11.1. Lợi nhuận sau thuế phân bổ cho chủ sở hữu", 4, kind="9M", sha="c" * 64))
    rows.append(_ai_row("MIX", _REV, 5, sha="e" * 64))
    rows.append(_ai_row("MIX", "XV. Lợi nhuận sau thuế của cổ đông của Ngân hàng mẹ (XIII-XIV)", 6, sha="e" * 64))
    rows.append(_ai_row("EEE", _REV, 100, sha="a" * 64))
    rows.append(_ai_row("EEE", _REV, 120, sha="b" * 64))
    rows.append(_ai_row("EEE", _REV, 80, kind="Q3", sha="a" * 64))
    rows.append(_ai_row("EEE", _PARENT, 8, kind="Q3", sha="a" * 64))
    rows.append(_ai_row("MMM", _REV, 10, unit="Đơn vị: 1.000.000 VNĐ", sha="f" * 64))
    rows.append(_ai_row("MMM", _PARENT, 2, unit="Đơn vị: 1.000.000 VNĐ", sha="f" * 64))
    path = _write_structured(tmp_path / "ai-input.json", rows)
    return path, build_structured_financial_research(path)


def _assert_ai_boundary(artifact):
    assert artifact["validation"]["validation_status"] == "VALID"
    assert artifact["human_review"]["review_state"] == "HUMAN_REVIEW_REQUIRED"
    assert artifact["human_review"]["human_decision_required"] is True
    assert artifact["external_model_call"] is False
    assert artifact["licensed_remote_disclosure"] == "NOT_ESTABLISHED"
    assert artifact["daily_packet_activated"] is False
    assert artifact["official_fact_admitted"] is False
    assert artifact["historical_pit"] == "UNKNOWN"
    assert artifact["financial_v2_authority_unchanged"] == "2026-09-05.1"
    assert artifact["temporal"]["historical_claim"] is False
    assert artifact["temporal"]["sealed_t0"] is False
    assert artifact["deterministic_draft"]["draft_role"] == "VALIDATOR_FIXTURE_NOT_A_MODEL_RESPONSE"
    assert artifact["deterministic_draft"]["human_review_required"] is True
    assert "measures" not in artifact
    blob = json.dumps(artifact)
    assert "PRIVATE_BOX_EXPORT_TOKEN" not in blob
    assert "https://" not in blob
    assert artifact["coverage"]["ai_evidence_count"] < artifact["coverage"]["source_measure_records"] or artifact["coverage"]["source_measure_records"] < 50


def test_structured_ai_research_is_local_bounded_and_fail_closed(tmp_path):
    import inspect
    from stocklookup_core.research.conditional_investment_case import build_structured_financial_ai_research
    from stocklookup_core.research.evidence_bound_ai_research_human_review import validate_ai_draft

    path, packet = _ai_packet(tmp_path)
    assert packet["consumers"]["ai_research_preview"]["status"] == "NOT_FED"
    source = inspect.getsource(build_structured_financial_ai_research)
    assert "urllib" not in source and "requests" not in source and "openai" not in source

    industrial = build_structured_financial_ai_research(packet, question="industrial_profitability", tickers=["AAA", "BBB", "CCC"])
    _assert_ai_boundary(industrial)
    assert industrial["temporal"]["mode"] == "PRESENT_DAY_DESCRIPTIVE"
    values = {(row["ticker"], row["period"], row["metric"]): row for row in industrial["ai_input"]["evidence"]}
    assert values[("AAA", "2026-Q3", "parent_profit_margin")]["value"] == "0.100000"
    assert values[("AAA", "2026-9M", "parent_profit_margin")]["value"] == "0.100000"
    assert values[("AAA", "2026-Q3", "parent_profit_margin")]["statement_scope"] == "consolidated"
    assert not any(row.get("value") == 999 for row in industrial["ai_input"]["evidence"])
    assert not any(row.get("ticker") == "CCC" and row.get("metric") == "gross_margin" for row in industrial["ai_input"]["evidence"])
    assert any(row.get("ticker") == "CCC" and "STATEMENT_TEMPLATE_IS_NOT_INDUSTRIAL" in row["reason_codes"] for row in industrial["ai_input"]["evidence"])
    assert all(row["statement_scope"] == "consolidated" for row in industrial["comparisons"])
    assert {row["period"] for row in industrial["comparisons"]} >= {"2026-Q3", "2026-9M"}
    assert not any(row["metric"] == "net_revenue" for row in industrial["comparisons"])

    quality = build_structured_financial_ai_research(packet, question="earnings_quality", tickers=["BBB"])
    _assert_ai_boundary(quality)
    quality_text = " ".join(claim["claim_text"] for claim in quality["deterministic_draft"]["claims"])
    assert "opposite signs" in quality_text
    assert "weak conversion" not in quality_text
    assert "No cause is assigned" in quality_text

    balance = build_structured_financial_ai_research(packet, question="balance_sheet_risk", tickers=["AAA"])
    _assert_ai_boundary(balance)
    assert any(row["classification"] == "RATIO_CHANGE" and row["observation"] == "HIGHER" for row in balance["ai_input"]["evidence"])
    assert any(row["metric"] == "interest_bearing_debt" and row["status"] == "BLOCKED" for row in balance["ai_input"]["evidence"])
    assert not any(claim["claim_type"] == "FACT" and "interest_bearing_debt" in claim["claim_text"] for claim in balance["deterministic_draft"]["claims"])

    templates = build_structured_financial_ai_research(packet, question="template_earnings_trends")
    _assert_ai_boundary(templates)
    families = {row["ticker"]: row["analysis_family"] for row in templates["ai_input"]["evidence"] if row.get("analysis_family")}
    assert families["CCC"] == "BANK_STATEMENT"
    assert families["QQQ"] == "SECURITIES_STATEMENT"
    assert not any(row.get("metric") == "gross_margin" and row.get("analysis_family") != "INDUSTRIAL_STATEMENT" for row in templates["ai_input"]["evidence"])

    valuation = build_structured_financial_ai_research(packet, question="valuation_readiness", tickers=["AAA"])
    _assert_ai_boundary(valuation)
    assert any(row["metric"] == "research_multiple" and row["status"] == "BLOCKED" for row in valuation["ai_input"]["evidence"])
    assert not any(claim["claim_type"] == "FACT" and claim.get("authority_class") == "BLOCKED" for claim in valuation["deterministic_draft"]["claims"])
    assert all(claim["claim_type"] != "FACT" or "research_multiple" not in claim["claim_text"] for claim in valuation["deterministic_draft"]["claims"])
    valuation_text = " ".join(claim["claim_text"] for claim in valuation["deterministic_draft"]["claims"])
    assert "No multiple is computed" in valuation_text

    thesis = build_structured_financial_ai_research(packet, question="company_thesis", tickers=["AAA"])
    other = build_structured_financial_ai_research(packet, question="company_thesis", tickers=["QQQ"])
    _assert_ai_boundary(thesis)
    _assert_ai_boundary(other)
    assert thesis["deterministic_draft"]["draft_identity"] != other["deterministic_draft"]["draft_identity"]
    assert not any(row.get("metric") == "gross_margin" for row in other["ai_input"]["evidence"])
    with pytest.raises(ValueError, match="PEER_TEMPLATE_MISMATCH"):
        build_structured_financial_ai_research(packet, question="company_thesis", tickers=["AAA", "CCC"])

    mismatched = build_structured_financial_ai_research(packet, question="industrial_profitability", tickers=["AAA", "MMM"])
    units = {(row["ticker"], row["unit"]) for row in mismatched["ai_input"]["evidence"] if row.get("metric") == "net_revenue" and row.get("value") is not None}
    assert ("AAA", "VND") in units and ("MMM", "MILLION_VND") in units
    assert all(row["unit"] == "RATIO" for row in mismatched["comparisons"])

    conflict = build_structured_financial_ai_research(packet, question="industrial_profitability", tickers=["EEE"])
    assert any(row["classification"] == "CONFLICT" and row["period"] == "2026-9M" and row["value"] is None for row in conflict["ai_input"]["evidence"])
    assert not any(
        claim["claim_type"] == "FACT" and "2026-9M" in claim["claim_text"] and "net_revenue" in claim["claim_text"]
        for claim in conflict["deterministic_draft"]["claims"]
    )

    unsupported = build_structured_financial_ai_research(packet, question="company_thesis", tickers=["MIX"])
    _assert_ai_boundary(unsupported)
    assert any("UNSUPPORTED_ACCOUNTING_TEMPLATE" in row["reason_codes"] for row in unsupported["ai_input"]["evidence"])
    assert not any(row.get("metric") == "parent_profit_margin" and row.get("value") is not None for row in unsupported["ai_input"]["evidence"])

    clocked = build_structured_financial_ai_research(
        packet, question="industrial_profitability", tickers=["AAA"], knowledge_cutoff="2026-11-01T00:00:00+07:00",
    )
    assert clocked["temporal"]["mode"] == "HISTORICAL_AVAILABILITY_UNPROVEN"
    assert not any(claim["claim_type"] == "FACT" for claim in clocked["deterministic_draft"]["claims"])
    assert all(row.get("value") is None for row in clocked["ai_input"]["evidence"])
    assert packet["caller_observed_at"] is None

    receipt = {
        "contract_version": "structured_financial_observation_receipt/v1",
        "input_sha256": packet["input_sha256"],
        "observed_at": "2026-11-02T00:00:00+07:00",
        "observation_basis": "RETAINED_ACQUISITION_RECORD",
    }
    late = build_structured_financial_ai_research(
        packet, question="industrial_profitability", tickers=["AAA"],
        knowledge_cutoff="2026-11-01T00:00:00+07:00", observation_receipt=receipt,
    )
    assert late["temporal"]["mode"] == "AFTER_KNOWLEDGE_CUTOFF"
    assert all(row.get("value") is None for row in late["ai_input"]["evidence"])
    early_receipt = {**receipt, "observed_at": "2026-10-01T00:00:00+07:00"}
    early = build_structured_financial_ai_research(
        packet, question="company_thesis", tickers=["AAA"],
        knowledge_cutoff="2026-11-01T00:00:00+07:00", observation_receipt=early_receipt,
    )
    assert early["temporal"]["mode"] == "OBSERVED_AT_OR_BEFORE_CUTOFF_PUBLICATION_UNPROVEN"
    assert early["temporal"]["historical_pit"] == "UNKNOWN"
    assert early["temporal"]["publication_time"] is None
    assert any(claim["claim_type"] == "FACT" for claim in early["deterministic_draft"]["claims"])
    with pytest.raises(ValueError, match="SOURCE_INPUT_SHA_MISMATCH"):
        build_structured_financial_ai_research(
            packet, question="company_thesis", tickers=["AAA"],
            knowledge_cutoff="2026-11-01T00:00:00+07:00",
            observation_receipt={**receipt, "input_sha256": "b" * 64},
        )
    with pytest.raises(ValueError, match="OBSERVATION_RECEIPT_IS_NOT_PUBLICATION_OR_VENDOR_TIME"):
        build_structured_financial_ai_research(
            packet, question="company_thesis", tickers=["AAA"],
            observation_receipt={**receipt, "vendor_publish_date": "2026-10-30"},
        )

    tampered = json.loads(json.dumps(packet))
    tampered["official_fact_admitted"] = True
    with pytest.raises(ValueError, match="OFFICIAL_ADMISSION_ESCALATION"):
        build_structured_financial_ai_research(tampered, question="valuation_readiness", tickers=["AAA"])
    tampered = json.loads(json.dumps(packet))
    tampered["measures"][0]["value"] = 1
    with pytest.raises(ValueError, match="RESEARCH_IDENTITY_MISMATCH"):
        build_structured_financial_ai_research(tampered, question="valuation_readiness", tickers=["AAA"])
    bad_draft = json.loads(json.dumps(valuation["deterministic_draft"]))
    blocked = next(row for row in valuation["ai_input"]["evidence"] if row["metric"] == "research_multiple")
    bad_draft["claims"].append({
        "claim_id": "bad-fact",
        "claim_type": "FACT",
        "section": "VALUATION_CONTEXT",
        "claim_text": "The research multiple is 9.",
        "supporting_evidence_ids": [blocked["evidence_id"]],
        "conflicting_evidence_ids": [],
        "authority_class": "PROVIDER_REPORTED",
        "numeric_evidence_ids": [blocked["evidence_id"]],
        "referenced_dimension": "valuation",
    })
    rejected = validate_ai_draft(valuation["ai_input"], bad_draft)
    assert rejected["validation_status"] == "REJECTED"
    assert "FACT_WITHOUT_QUALIFIED_EVIDENCE" in rejected["reason_codes"] or "AUTHORITY_ESCALATION_OR_UNSUPPORTED_CLAIM" in rejected["reason_codes"]

    again = build_structured_financial_ai_research(packet, question="company_thesis", tickers=["AAA"])
    assert again == thesis
    out_json = tmp_path / "ai.json"
    out_md = tmp_path / "ai.md"
    assert main([
        "--structured-input", str(path), "--ai-question", "company_thesis", "--tickers", "AAA",
        "--out-json", str(out_json), "--out-md", str(out_md),
    ]) == 0
    written = json.loads(out_json.read_text(encoding="utf-8"))
    assert written["external_model_call"] is False
    assert "PRIVATE_BOX_EXPORT_TOKEN" not in out_json.read_text(encoding="utf-8")
    assert "Local evidence-bound validator only" in out_md.read_text(encoding="utf-8")
    plain_md = tmp_path / "plain.md"
    plain_json = tmp_path / "plain.json"
    assert main(["--structured-input", str(path), "--out-json", str(plain_json), "--out-md", str(plain_md)]) == 0
    assert "not fed to the AI research preview" in plain_md.read_text(encoding="utf-8")
    with pytest.raises(SystemExit):
        main([
            "--structured-input", str(path), "--ai-question", "company_thesis", "--tickers", "AAA",
            "--observed-at", "2026-11-01T00:00:00+07:00",
            "--out-json", str(tmp_path / "clock.json"), "--out-md", str(tmp_path / "clock.md"),
        ])


def test_real_vietstock_ai_research_accepts_bounded_questions():
    import hashlib
    from pathlib import Path
    from stocklookup_core.research.conditional_investment_case import (
        build_statement_research_cohort,
        build_structured_financial_ai_research,
        build_structured_financial_research,
    )

    path = Path(r"C:\Projects\StockLookup\.stocklookup\scratch\q3-financial-evidence-20261118\vietstock_expansion_20261116_002\expansion_20261116_002\normalized_long_dedup_v2.csv")
    if not path.is_file():
        pytest.skip("RETAINED_VIETSTOCK_EXPORT_ABSENT")
    packet = build_structured_financial_research(path)
    assert packet["input_sha256"] == "66112662d2423c5e7a244b796c5bd007e1455b0a26738f264d39e1072525f854"
    assert packet["input_sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()
    assert packet["research_identity"] == "structured_financial_research:75a5ff600f3204354dd60df83b7dcd1c51015ef318d00dbeca82f0986b4b3bad"
    assert packet["coverage"]["issuer_count"] == 13
    assert packet["coverage"]["issuer_period_metric_records"] == 2282
    assert packet["coverage"]["current_research_usable"] == 1542
    cohort = build_statement_research_cohort()
    assert cohort["cohort_identity"] == "current_statement_research_cohort:0b691549cd1638c0599b46a6f0456b7e0613cd8a71037acac5ba5aa5a7070dc6"
    retained = next(row for row in cohort["measures"] if row["ticker"] == "HPG" and row["period"] == "2026-Q3" and row["metric"] == "parent_profit_margin")
    pan = next(row for row in cohort["measures"] if row["ticker"] == "PAN" and row["period"] == "2026-Q3" and row["metric"] == "parent_profit_margin")
    industrial = build_structured_financial_ai_research(
        packet, question="industrial_profitability", tickers=["HPG", "PAN", "FPT", "PNJ", "POW", "PVD", "VNM", "QNS"],
    )
    _assert_ai_boundary(industrial)
    evidence = industrial["ai_input"]["evidence"]
    hpg = next(row for row in evidence if row["ticker"] == "HPG" and row["period"] == "2026-Q3" and row["metric"] == "parent_profit_margin")
    pan_row = next(row for row in evidence if row["ticker"] == "PAN" and row["period"] == "2026-Q3" and row["metric"] == "parent_profit_margin")
    hpg_nine = next(row for row in evidence if row["ticker"] == "HPG" and row["period"] == "2026-9M" and row["metric"] == "parent_profit_margin")
    assert hpg["value"] == retained["value"]
    assert hpg["statement_scope"] == "consolidated"
    assert pan_row["value"] == pan["value"]
    assert hpg_nine["period"] == "2026-9M"
    assert hpg["period"] != hpg_nine["period"]
    q3_margin = next(
        row for row in industrial["comparisons"]
        if row["metric"] == "parent_profit_margin" and row["period"] == "2026-Q3" and row["statement_scope"] == "consolidated"
    )
    q3_values = {item["ticker"]: item["value"] for item in q3_margin["rows"]}
    assert q3_values["HPG"] == hpg["value"]
    assert q3_values["PAN"] == pan_row["value"]
    assert q3_values["HPG"] > q3_values["PAN"]
    assert industrial["coverage"]["ai_measures_with_values"] < packet["coverage"]["current_research_usable"]
    assert industrial["coverage"]["ai_evidence_count"] < 500
    quality = build_structured_financial_ai_research(packet, question="earnings_quality")
    _assert_ai_boundary(quality)
    assert any(row["metric"] == "cash_conversion" and row.get("value") for row in quality["ai_input"]["evidence"])
    assert all("caused by" not in claim["claim_text"].lower() for claim in quality["deterministic_draft"]["claims"])
    templates = build_structured_financial_ai_research(packet, question="template_earnings_trends")
    _assert_ai_boundary(templates)
    assert any(row.get("ticker") == "VCB" and row.get("analysis_family") == "BANK_STATEMENT" for row in templates["ai_input"]["evidence"])
    assert any(row.get("ticker") == "EVF" and row.get("analysis_family") == "BANK_STATEMENT" for row in templates["ai_input"]["evidence"])
    assert any(row.get("ticker") == "SSI" and row.get("analysis_family") == "SECURITIES_STATEMENT" for row in templates["ai_input"]["evidence"])
    assert not any(row.get("metric") == "gross_margin" and row.get("analysis_family") in {"BANK_STATEMENT", "SECURITIES_STATEMENT"} for row in templates["ai_input"]["evidence"])
    valuation = build_structured_financial_ai_research(packet, question="valuation_readiness")
    _assert_ai_boundary(valuation)
    assert valuation["coverage"]["ai_measures_with_values"] == 0
    assert any(row["metric"] == "research_multiple" and row["value"] is None for row in valuation["ai_input"]["evidence"])
    hpg_thesis = build_structured_financial_ai_research(packet, question="company_thesis", tickers=["HPG"])
    ssi_thesis = build_structured_financial_ai_research(packet, question="company_thesis", tickers=["SSI"])
    _assert_ai_boundary(hpg_thesis)
    _assert_ai_boundary(ssi_thesis)
    assert any(claim["section"] == "COUNTER_THESIS" for claim in hpg_thesis["deterministic_draft"]["claims"])
    assert any(claim["section"] == "WHAT_WOULD_CHANGE_THE_VIEW" for claim in ssi_thesis["deterministic_draft"]["claims"])
    assert not any(row.get("metric") == "gross_margin" for row in ssi_thesis["ai_input"]["evidence"])
    withheld = build_structured_financial_ai_research(
        packet, question="company_thesis", tickers=["HPG"], knowledge_cutoff="2026-10-20T15:00:00+07:00",
    )
    assert withheld["temporal"]["mode"] == "HISTORICAL_AVAILABILITY_UNPROVEN"
    assert not any(claim["claim_type"] == "FACT" for claim in withheld["deterministic_draft"]["claims"])
    assert packet["consumers"]["ai_research_preview"]["daily_packet_activated"] is False
    assert build_statement_research_cohort()["cohort_identity"] == cohort["cohort_identity"]
