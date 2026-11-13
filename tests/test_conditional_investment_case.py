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
