"""Owner corrective 2026-11-07: coordinate proofs for a registered image-only layout (HPG H1/2026)."""
import copy

from financial_statement_unit_resolution import parse_explicit_unit_declaration as PU
from official_financial_value_evidence import parse_accounting_integer as PA

from stocklookup_core.evidence import official_ocr_layout_proof as lp

SHA = "9a2881a88ac8ca4cc5cd948b0fafa031ff30fd0332a372f362477a8a6b0c9968"
PAGE = 12


def tok(order, text, x0, x1, top, bottom, line):
    return {"token_id": f"t{order}", "raw_token_order": order, "text": text, "x0": x0, "x1": x1, "top": top,
            "bottom": bottom, "tsv_hierarchy": {"block_num": 1, "par_num": 1, "line_num": line}}


def base_tokens():
    return [
        tok(1, "Don", 100, 150, 300, 330, 1), tok(2, "vj:", 155, 190, 300, 330, 1), tok(3, "VND", 195, 260, 300, 330, 1),
        tok(4, "Kỳ", 1390, 1420, 540, 570, 2), tok(5, "này", 1425, 1480, 540, 570, 2),
        tok(6, "Kỳ", 1700, 1740, 540, 570, 2), tok(7, "trước", 1745, 1820, 540, 570, 2),
        tok(8, "3.", 290, 310, 774, 797, 3), tok(9, "Doanh", 320, 400, 774, 797, 3), tok(10, "thu", 405, 450, 774, 797, 3),
        tok(11, "10", 965, 995, 774, 797, 3), tok(12, "31", 1080, 1110, 774, 797, 3),
        tok(13, "108.059.749.601.554", 1181, 1484, 774, 797, 3), tok(14, "73.532.193.664.787", 1540, 1827, 773, 797, 3),
    ]


def make_proof(tokens=None):
    body = {"contract_version": lp.CONTRACT_VERSION, "document_sha256": SHA,
            "layout": lp.LAYOUT_PROOFS[SHA]["layout"], "engine_version": "tesseract test",
            "ocr_config": {"dpi": 240}, "pages": {str(PAGE): {"rendered_image_sha256": "img", "ocr_adapters": {},
                                                             "tokens": tokens if tokens is not None else base_tokens()}}}
    import hashlib
    return {**body, "proof_sha256": hashlib.sha256(lp.canonical_json(body).encode()).hexdigest()}


ROW = {
    "line_code": "10", "current_period_label": "Kỳ này", "comparative_raw_value": "73.532.193.664.787",
    "current_value_bbox": {"x0": 1181, "x1": 1484, "top": 774, "bottom": 797},
    "row_bbox": {"x0": 281, "x1": 1827, "top": 771, "bottom": 845},
    "raw_label_fragments": ["3.", "Doanh", "thu"], "label_source_token_orders": [8, 9, 10],
    "physical_line_reconstruction": {"row_baseline_bounds": [755.5, 817.0]},
    "column_bands": {
        "header_evidence": {"bbox": {"top": 524, "bottom": 598},
                            "period_identities": {"current": {"raw_text": "Kỳ này", "source_token_orders": [4, 5]}}},
        "bands": {"line_code": {"x0": 962, "x1": 1001}, "note_reference": {"x0": 1079, "x1": 1118},
                  "current_period_value": {"x0": 1179, "x1": 1487}, "comparative_period_value": {"x0": 1538, "x1": 1831},
                  "label": {"x0": 0, "x1": 962}},
    },
}
UNIT = {"state": "QUALIFIED", "evidence": {"currency": "VND", "unit_scale": 1, "evidence_text": "Don vj: VND",
        "document_sha256": SHA, "page_number": PAGE, "source_span": {"token_ids": ["t1", "t2", "t3"]}}}


def verify(row=ROW, proof=None, raw="108.059.749.601.554", value=108059749601554, code="10", metric="revenue"):
    return lp.verify_row(row, proof or make_proof(), metric=metric, source_page=PAGE, line_code=code,
                         raw_value=raw, value=value, unit_scale=1, parse_amount=PA)


def unit(evidence=UNIT, proof=None):
    return lp.verify_statement_unit(evidence, proof or make_proof(), source_page=PAGE, header_top=524,
                                    currency="VND", unit_scale=1, parse_unit=PU)


def test_valid_row_and_unit_prove():
    assert verify() == []
    assert unit() == []


def test_wrong_year_column_is_refused():
    row = copy.deepcopy(ROW)
    row["current_value_bbox"] = {"x0": 1540, "x1": 1827, "top": 773, "bottom": 797}
    assert "VALUE_NOT_IN_CURRENT_PERIOD_COLUMN" in verify(row, raw="73.532.193.664.787", value=73532193664787)
    row = copy.deepcopy(ROW)
    row["column_bands"]["header_evidence"]["period_identities"]["current"]["raw_text"] = "Kỳ trước"
    assert "CURRENT_PERIOD_HEADER_NOT_REGISTERED" in verify(row)


def test_wrong_row_or_line_code_is_refused():
    assert "ROW_LINE_CODE_NOT_EXPECTED_FOR_METRIC" in verify(code="20")
    tokens = base_tokens()
    tokens[10] = tok(11, "10", 965, 995, 900, 925, 4)  # line code sits on another physical row
    assert "LINE_CODE_NOT_ON_VALUE_ROW" in verify(proof=make_proof(tokens))


def test_two_amounts_side_by_side_in_current_column_are_ambiguous():
    tokens = base_tokens() + [tok(15, "1.234.567", 1300, 1400, 776, 796, 3)]
    assert "ADJACENT_AMOUNT_AMBIGUITY" in verify(proof=make_proof(tokens))


def test_ocr_line_shift_is_refused():
    tokens = base_tokens()
    tokens[12] = tok(13, "108.059.749.601.554", 1181, 1484, 840, 863, 5)  # value drifted below the row
    assert verify(proof=make_proof(tokens))  # value token no longer at the cited box
    row = copy.deepcopy(ROW)
    row["physical_line_reconstruction"] = {"row_baseline_bounds": [900, 950]}
    assert "VALUE_OUTSIDE_ROW_BASELINE" in verify(row)


def test_missing_coordinates_or_evidence_fail_closed():
    row = copy.deepcopy(ROW)
    del row["current_value_bbox"]
    assert verify(row) == ["ROW_GEOMETRY_MISSING"]
    assert verify({}) == ["ROW_PROOF_MISSING"]
    tokens = [t for t in base_tokens() if t["raw_token_order"] != 9]
    assert "LABEL_TOKENS_NOT_IN_PROOF" in verify(proof=make_proof(tokens))
    assert unit({"state": "QUALIFIED"}) == ["STATEMENT_UNIT_EVIDENCE_MISSING"]


def test_value_text_sign_and_parse_must_match_exactly():
    assert "VALUE_PARSE_MISMATCH" in verify(value=108059749601553)
    tokens = base_tokens()
    tokens[12] = tok(13, "(108.059.749.601.554)", 1181, 1484, 774, 797, 3)
    assert "VALUE_SIGN_MISMATCH" in verify(proof=make_proof(tokens), raw="(108.059.749.601.554)", value=108059749601554)


def test_conflicting_or_scaled_or_unbound_unit_is_blocked():
    tokens = base_tokens() + [tok(20, "Đơn", 100, 150, 2000, 2030, 9), tok(21, "vị:", 155, 190, 2000, 2030, 9),
                              tok(22, "triệu", 195, 260, 2000, 2030, 9), tok(23, "VND", 265, 320, 2000, 2030, 9)]
    assert "STATEMENT_UNIT_DECLARATIONS_CONFLICT" in unit(proof=make_proof(tokens))
    assert "STATEMENT_UNIT_NOT_ABOVE_TABLE_HEADER" in lp.verify_statement_unit(
        UNIT, make_proof(), source_page=PAGE, header_top=200, currency="VND", unit_scale=1, parse_unit=PU)
    other = copy.deepcopy(UNIT)
    other["evidence"]["page_number"] = 13
    assert "STATEMENT_UNIT_NOT_BOUND_TO_FACT_TABLE" in unit(other)
    assert "STATEMENT_UNIT_VALUE_MISMATCH" in lp.verify_statement_unit(
        UNIT, make_proof(), source_page=PAGE, header_top=524, currency="VND", unit_scale=1000, parse_unit=PU)


def test_proof_hash_and_registry_scope():
    proof = make_proof()
    assert lp.verify_proof_identity(proof, document_sha256=SHA, proof_sha256=proof["proof_sha256"]) == []
    tampered = copy.deepcopy(proof)
    tampered["pages"][str(PAGE)]["tokens"][12]["text"] = "999.999.999.999.999"
    assert "OCR_PROOF_HASH_MISMATCH" in lp.verify_proof_identity(tampered, document_sha256=SHA, proof_sha256=proof["proof_sha256"])
    assert "OCR_PROOF_DOCUMENT_OR_LAYOUT_MISMATCH" in lp.verify_proof_identity(proof, document_sha256="0" * 64, proof_sha256=None)


def test_apply_replaces_only_the_two_text_checks_and_only_for_registered_layouts():
    proof = make_proof()
    row = {"ocr_layout_proof": lp.proof_reference(proof), "document_sha256": SHA, "ticker": "HPG",
           "reporting_period": "2026-H1", "statement_scope": "consolidated", "canonical_metric": "revenue",
           "source_page": PAGE, "line_code": "10", "raw_value_text": "108.059.749.601.554",
           "normalized_value": 108059749601554, "source_unit_scale": 1, "currency": "VND",
           "ocr_row_object": ROW, "ocr_unit_evidence": UNIT}
    metadata = {"metadata_claims": {"unit_scale": {"evidence_span": {"citation_kind": lp.STATEMENT_UNIT_CITATION_KIND}}}}
    reasons = ["VALUE_SPAN_NOT_IN_RETAINED_DOCUMENT", "RETAINED_UNIT_SCALE_NOT_EXPLICIT", "KNOWLEDGE_TIME_INVALID"]
    assert lp.apply_layout_proof(row, proof, metadata, list(reasons), [], parse_amount=PA, parse_unit=PU)[0] == ["KNOWLEDGE_TIME_INVALID"]
    # Unit claims not statement-page based: the unit recognizer reason is NOT replaced.
    assert "RETAINED_UNIT_SCALE_NOT_EXPLICIT" in lp.apply_layout_proof(row, proof, {}, list(reasons), [], parse_amount=PA, parse_unit=PU)[0]
    # Unregistered document: nothing changes.
    other = dict(row, document_sha256="0" * 64)
    assert lp.apply_layout_proof(other, proof, metadata, list(reasons), [], parse_amount=PA, parse_unit=PU) == (reasons, [])
    # Proof missing downstream: stays UNKNOWN, nothing replaced.
    assert lp.apply_layout_proof(row, None, metadata, list(reasons), [], parse_amount=PA, parse_unit=PU) == (reasons, ["OCR_LAYOUT_PROOF_UNAVAILABLE"])
    # Wrong issuer/period for the registered layout.
    assert "OCR_LAYOUT_SCOPE_MISMATCH" in lp.apply_layout_proof(dict(row, ticker="VNM"), proof, metadata, [], [], parse_amount=PA, parse_unit=PU)[0]


def test_modern_overlay_rows_require_a_registered_layout_proof(tmp_path):
    import json
    import pytest
    from financial_evidence_currency_contract import PUBLIC_ARTIFACT_DIR
    from financial_evidence_currency_refresh import (PUBLIC_LAYOUT_PROOF_FACTS, OfficialOverlayArtifactError,
                                                     load_public_official_fact_rows)
    public = tmp_path / PUBLIC_ARTIFACT_DIR
    public.mkdir(parents=True)
    good = {"ticker": "HPG", "canonical_metric": "revenue", "reporting_period": "2026-H1", "qualification_state": "QUALIFIED",
            "document_sha256": SHA, "ocr_layout_proof": {"proof_sha256": "x"}}
    (public / PUBLIC_LAYOUT_PROOF_FACTS).write_text(json.dumps(good) + "\n", encoding="utf-8")
    assert load_public_official_fact_rows(tmp_path) == [good]
    bad = dict(good, document_sha256="0" * 64)
    (public / PUBLIC_LAYOUT_PROOF_FACTS).write_text(json.dumps(bad) + "\n", encoding="utf-8")
    with pytest.raises(OfficialOverlayArtifactError, match="UNPROVEN"):
        load_public_official_fact_rows(tmp_path)


def test_registered_layout_records_verified_absent_text_layer():
    verification = lp.LAYOUT_PROOFS[SHA]["text_layer_verification"]
    assert verification["state"] == "NONE_VERIFIED" and verification["non_empty_pages"] == 0
