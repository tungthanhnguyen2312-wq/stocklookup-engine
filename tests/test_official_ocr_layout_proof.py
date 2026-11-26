"""Owner corrective 2026-11-07: coordinate proofs for a registered image-only layout (HPG H1/2026)."""
import copy

from financial_statement_unit_resolution import parse_explicit_unit_declaration as PU
from official_financial_value_evidence import parse_accounting_integer as PA

from stocklookup_core.evidence import official_ocr_layout_proof as lp

SHA = "9a2881a88ac8ca4cc5cd948b0fafa031ff30fd0332a372f362477a8a6b0c9968"
PAGE = 12

DECISION2_LAYOUTS = (
    ("54077f6abf8f31ce54eb92fd92e00ae107fe30cb9fabac2829dfb911b49bcbe7", "POW", "2025", 11,
     "Current year", "Prior year"),
    ("e56815b230d3130816b1169055691d3dc6ce6b67af932a651db69b6da52045c1", "POW", "2025-H1", 11,
     "Current period", "Prior period"),
    ("38f6bcd441d601fa94e2742ee7d6721c4f423110b656e90ba0f9e8ac2e123cd5", "POW", "2026-H1", 11,
     "Current period", "Prior period"),
    ("618d514b355387ade90d2266f8f8c4c7098d94339592dc696d900482c96b4e6c", "NVL", "2025-H1", 12,
     "06 tháng đầu năm 2025", "06 tháng đầu năm 2024"),
    ("20aa7254735542d470f12ada8d02786dfa5e673035274e42d3404352e266a007", "NVL", "2026-H1", 12,
     "06 tháng đầu năm 2026", "06 tháng đầu năm 2025 (Trình bày lại)"),
    ("8a1cb94cbe9ef5d98550ef6ab734f54f99ecb9376f43c8aa4a3662cd6d5d0353", "NVL", "2025", 12,
     "Năm 2025", "Năm 2024"),
)


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


def baseline_two_token(raw="1.²34.567", top=100, bottom=120):
    boxes = [{"text": char, "x0": i * 10, "x1": i * 10 + 8,
              "top": top if char == "²" else 100, "bottom": bottom if char == "²" else 120}
             for i, char in enumerate(raw)]
    return {"token_id": "synthetic", "text": raw, "x0": 0, "x1": len(raw)*10,
            "top": min(100, top), "bottom": max(120, bottom), "glyph_evidence": {
                "contract_version": "tesseract_makebox_same_render/v1", "rendered_image_sha256": "a"*64,
                "engine_version": "synthetic", "config": {"psm": 6}, "boxes": boxes}}


def test_baseline_two_proof_passes_only_for_bound_baseline_glyphs():
    token = baseline_two_token()
    raw, proof = lp.baseline_two_value(token, "a"*64)
    assert raw == "1.234.567"
    assert proof["tolerance_fraction"] == .10 and proof["tolerance_pixels"] == 2
    assert proof["glyph_evidence"]["boxes"] == token["glyph_evidence"]["boxes"]
    assert token["text"] == "1.²34.567"
    assert lp.baseline_two_value(token, "b"*64) == (token["text"], None)
    del token["glyph_evidence"]
    assert lp.baseline_two_value(token, "a"*64) == (token["text"], None)


def test_true_superscript_and_mixed_damage_still_block():
    for token in [baseline_two_token(top=90, bottom=103), baseline_two_token(top=100, bottom=113),
                  baseline_two_token(raw="1.²3O.567"), baseline_two_token(raw="1.²³4.567"),
                  baseline_two_token(raw="1.²34.5²²")]:
        # The last token has too few unaffected ASCII reference digits.
        if token["text"] == "1.²34.5²²":
            token["glyph_evidence"]["boxes"][2]["top"] = 90
        assert lp.baseline_two_value(token, "a"*64) == (token["text"], None)


def test_retained_baseline_two_character_boxes_replay_without_digit_algebra():
    import json
    from pathlib import Path
    fixture = Path(__file__).parent / "fixtures/retained_interim_geometry/baseline_two_glyphs.json"
    rows = json.loads(fixture.read_text(encoding="utf8"))["records"]
    assert len(rows) == 3
    for row in rows:
        normalized, proof = lp.baseline_two_value(row["token"], row["rendered_image_sha256"])
        assert normalized == row["expected"] and proof is not None
        assert proof["rendered_image_sha256"] == row["rendered_image_sha256"]
        assert proof["raw_value"] == row["token"]["text"]
        for field in ("top", "bottom"):
            damaged = copy.deepcopy(row["token"])
            next(b for b in damaged["glyph_evidence"]["boxes"] if b["text"] == "²")[field] -= 10
            assert lp.baseline_two_value(damaged, row["rendered_image_sha256"])[1] is None


def test_baseline_two_tolerance_boundary_and_malformed_boxes():
    assert lp.baseline_two_value(baseline_two_token(top=102, bottom=122), "a"*64)[1]
    assert lp.baseline_two_value(baseline_two_token(top=103, bottom=123), "a"*64)[1] is None
    for bad in (None, [], [None], "missing", [{"text": "²"}]):
        token = baseline_two_token()
        token["glyph_evidence"]["boxes"] = bad
        assert lp.baseline_two_value(token, "a"*64)[1] is None


def test_baseline_two_layout_row_and_admission_parse_are_bound_to_proof():
    tokens = base_tokens()
    token = tokens[12]
    raw = "108.059.749.601.²54"
    token["text"] = raw
    width = (token["x1"]-token["x0"])/len(raw)
    token["glyph_evidence"] = {"contract_version": "tesseract_makebox_same_render/v1",
        "rendered_image_sha256": "a"*64, "engine_version": "tesseract test", "config": {"dpi": 240},
        "boxes": [{"text": c, "x0": token["x0"]+i*width, "x1": token["x0"]+(i+1)*width-1,
                   "top": token["top"], "bottom": token["bottom"]} for i,c in enumerate(raw)]}
    proof = make_proof(tokens)
    proof["pages"][str(PAGE)]["rendered_image_sha256"] = "a"*64
    import hashlib
    proof["proof_sha256"] = hashlib.sha256(lp.canonical_json({k:v for k,v in proof.items() if k!="proof_sha256"}).encode()).hexdigest()
    assert verify(proof=proof, raw=raw, value=108059749601254) == []
    row = {"raw_value_text": raw, "document_sha256": SHA, "source_page": PAGE,
           "ocr_layout_proof": lp.proof_reference(proof), "ocr_row_object": ROW}
    assert lp.bound_numeric_value(row, proof) == "108.059.749.601.254"
    token["glyph_evidence"]["boxes"][14]["top"] -= 12
    assert lp.bound_numeric_value(row, proof) == raw  # changed boxes invalidate proof hash


def test_retained_zero_native_candidate_replay_requires_every_source_binding(tmp_path, monkeypatch):
    """Modern retained replay cannot trust a caller's zero-candidate assertion."""
    import hashlib
    import json
    import pypdf
    import official_financial_filing_evidence as filing
    import official_financial_pdf_page_evidence as native_owner
    from official_financial_ocr_table_evidence import _hash
    from stocklookup_core.evidence.official_document_qualification import admit_retained_financial_fact
    payload = b'%PDF synthetic zero-candidate fixture'
    sha = hashlib.sha256(payload).hexdigest()
    monkeypatch.setitem(lp.LAYOUT_PROOFS, sha, dict(lp.LAYOUT_PROOFS[SHA]))
    record = dict(sha256=sha, relative_path='original.pdf', ticker='HPG',
                  canonical_url='https://file.hoaphat.com.vn/synthetic.pdf', observed_at='2026-11-24T01:00:00Z')
    (tmp_path/'original.pdf').write_bytes(payload)
    (tmp_path/'official_document_acquisition_manifest.json').write_text(json.dumps({'records': [record]}))
    class Page:
        def extract_text(self):
            return 'unusable native font map'
    class Reader:
        def __init__(self, *args):
            self.pages = [Page()]
    monkeypatch.setattr(pypdf, 'PdfReader', Reader)
    artifact = dict(artifact_identity='native-zero', fact_candidates=[], p3f13_panel_facts=[],
                    page_evidence=[dict(page_number=1, page_text=Page().extract_text())])
    monkeypatch.setattr(native_owner, 'build_artifact', lambda **kw: artifact)
    monkeypatch.setattr(filing, 'admit_official_financial_fact', lambda row, **kw: kw['document_pages'])
    failure = dict(document_sha256=sha, native_artifact_identity='native-zero', candidate_count=0,
        trigger='EXPLICIT_OPT_IN_AFTER_NATIVE_ZERO_CANDIDATES',
        native_page_text_sha256={'1': _hash(Page().extract_text())})
    base = dict(contract_version=lp.CONTRACT_VERSION, document_sha256=sha, pages={'1': dict(
        tokens=[tok(1, 'retained OCR literal', 0, 10, 0, 10, 1)], native_failure_evidence=failure)})
    def replay(body):
        proof = dict(body, proof_sha256=hashlib.sha256(lp.canonical_json(body).encode()).hexdigest())
        ref = lp.proof_reference(proof)
        path = tmp_path/ref['relative_path'];path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(proof))
        row = dict(document_sha256=sha, ocr_layout_proof=ref, document_metadata={'metadata_claims': {}},
                   assurance_evidence={'page_number': 1}, source_span={'source_page': 1})
        return admit_retained_financial_fact(row, evidence_root=tmp_path, registry={})
    assert replay(base) == {1: 'retained OCR literal'}
    for change in ({'native_artifact_identity': 'forged'}, {'candidate_count': 1},
                   {'native_page_text_sha256': {'1': 'wrong'}}, {'document_sha256': 'f'*64},
                   {'trigger': 'caller asserted'}):
        bad = copy.deepcopy(base);bad['pages']['1']['native_failure_evidence'].update(change)
        assert replay(bad) == {1: Page().extract_text()}
    bad = copy.deepcopy(base);bad['pages']['1'].pop('native_failure_evidence')
    assert replay(bad) == {1: Page().extract_text()}
    artifact['fact_candidates'] = [{'native': 'candidate exists'}]
    assert replay(base) == {1: Page().extract_text()}


def _zero_native_candidate_fixture(tmp_path, monkeypatch):
    import hashlib
    import json
    import pypdf
    import official_financial_filing_evidence as filing
    from official_financial_ocr_table_evidence import _hash
    payload = b'%PDF synthetic zero-candidate di fixture'
    sha = hashlib.sha256(payload).hexdigest()
    monkeypatch.setitem(lp.LAYOUT_PROOFS, sha, dict(lp.LAYOUT_PROOFS[SHA]))
    record = dict(sha256=sha, relative_path='original.pdf', ticker='HPG',
                  canonical_url='https://file.hoaphat.com.vn/synthetic.pdf', observed_at='2026-11-24T01:00:00Z')
    (tmp_path/'original.pdf').write_bytes(payload)
    (tmp_path/'official_document_acquisition_manifest.json').write_text(json.dumps({'records': [record]}))
    class Page:
        def extract_text(self):
            return 'unusable native font map'
    class Reader:
        def __init__(self, *args):
            self.pages = [Page()]
    monkeypatch.setattr(pypdf, 'PdfReader', Reader)
    monkeypatch.setattr(filing, 'admit_official_financial_fact', lambda row, **kw: kw['document_pages'])
    native_text = Page().extract_text()
    artifact = dict(artifact_identity='native-zero', fact_candidates=[], p3f13_panel_facts=[],
                    page_evidence=[dict(page_number=1, page_text=native_text)])
    failure = dict(document_sha256=sha, native_artifact_identity='native-zero', candidate_count=0,
                   trigger='EXPLICIT_OPT_IN_AFTER_NATIVE_ZERO_CANDIDATES',
                   native_page_text_sha256={'1': _hash(native_text)})
    body = dict(contract_version=lp.CONTRACT_VERSION, document_sha256=sha, pages={'1': dict(
        tokens=[tok(1, 'retained OCR literal', 0, 10, 0, 10, 1)], native_failure_evidence=failure)})
    proof = dict(body, proof_sha256=hashlib.sha256(lp.canonical_json(body).encode()).hexdigest())
    ref = lp.proof_reference(proof)
    path = tmp_path/ref['relative_path']; path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(proof))
    row = dict(document_sha256=sha, ocr_layout_proof=ref, document_metadata={'metadata_claims': {}},
               assurance_evidence={'page_number': 1}, source_span={'source_page': 1})
    return row, native_text, artifact


def test_retained_zero_native_candidate_replay_fails_closed_without_builder(tmp_path, monkeypatch):
    """When no native PDF builder is registered or passed, OCR fallback must fail closed."""
    from stocklookup_core.evidence import official_document_qualification as odq
    row, native_text, _ = _zero_native_candidate_fixture(tmp_path, monkeypatch)
    previous = odq.register_native_artifact_builder(None)
    try:
        assert odq.admit_retained_financial_fact(row, evidence_root=tmp_path, registry={}) == {1: native_text}
    finally:
        odq.register_native_artifact_builder(previous)


def test_retained_zero_native_candidate_replay_accepts_explicit_builder(tmp_path, monkeypatch):
    """An explicit native_artifact_builder parameter replays even with no registered builder."""
    from stocklookup_core.evidence import official_document_qualification as odq
    row, _, artifact = _zero_native_candidate_fixture(tmp_path, monkeypatch)
    previous = odq.register_native_artifact_builder(None)
    try:
        result = odq.admit_retained_financial_fact(
            row, evidence_root=tmp_path, registry={}, native_artifact_builder=lambda **kw: artifact)
        assert result == {1: 'retained OCR literal'}
    finally:
        odq.register_native_artifact_builder(previous)


def test_nvl_exact_legal_name_requires_bound_layout_and_proof(monkeypatch):
    import hashlib
    from tools.run_dual_reader_transcription_admission import REGISTERED_ISSUER_FOLD
    name = 'CONG TY CO PHAN TAP DOAN DAU TU DIA OC NO VA'
    assert REGISTERED_ISSUER_FOLD['NVL'] == name.lower()
    monkeypatch.setitem(lp.LAYOUT_PROOFS, SHA, {**lp.LAYOUT_PROOFS[SHA], 'ticker': 'NVL'})
    body = {'contract_version': lp.CONTRACT_VERSION, 'document_sha256': SHA, 'pages': {}}
    digest = hashlib.sha256(lp.canonical_json(body).encode()).hexdigest()
    proof = {**body, 'proof_sha256': digest}
    row = {'ticker': 'NVL', 'document_sha256': SHA, 'ocr_layout_proof': {'proof_sha256': digest}}
    assert lp.retained_issuer_name_matches(row, proof, name)
    for bad in ('NOVALAND', name.replace('NO VA', 'NOVA'), name.replace('DIA OC', 'DIA O')):
        assert not lp.retained_issuer_name_matches(row, proof, bad)
    assert not lp.retained_issuer_name_matches({**row, 'ticker': 'POW'}, proof, name)
    assert not lp.retained_issuer_name_matches(row, {**proof, 'document_sha256': '0' * 64}, name)
    monkeypatch.delitem(lp.LAYOUT_PROOFS, SHA)
    assert not lp.retained_issuer_name_matches(row, proof, name)


def test_pow_english_name_is_exact_and_requires_bound_layout_and_proof(monkeypatch):
    import hashlib
    name = "PETROVIETNAM POWER CORPORATION"
    registration = lp.EXACT_REGISTERED_ISSUER_NAMES["POW"][0]
    assert registration["provenance"]["document_sha256"] == "3b06425b3d79803f9e7bf634c8bfd600f4aca998bcd15dabcd95ffb04877afbc"
    assert registration["provenance"]["source_page"] == 7
    monkeypatch.setitem(lp.LAYOUT_PROOFS, SHA, {**lp.LAYOUT_PROOFS[SHA], 'ticker': 'POW'})
    body = {'contract_version': lp.CONTRACT_VERSION, 'document_sha256': SHA, 'pages': {}}
    digest = hashlib.sha256(lp.canonical_json(body).encode()).hexdigest()
    proof = {**body, 'proof_sha256': digest}
    row = {'ticker': 'POW', 'document_sha256': SHA, 'ocr_layout_proof': {'proof_sha256': digest}}
    assert lp.exact_registered_issuer_name('POW', name)
    assert lp.retained_issuer_name_matches(row, proof, name)
    for bad in ('PETRO VIETNAM POWER CORPORATION', name.lower(), name.replace('POWER', 'POWR'), 'X' + name):
        assert not lp.exact_registered_issuer_name('POW', bad)
        assert not lp.retained_issuer_name_matches(row, proof, bad)
    assert not lp.retained_issuer_name_matches({**row, 'ticker': 'NVL'}, proof, name)
    assert not lp.retained_issuer_name_matches(row, {**proof, 'document_sha256': '0' * 64}, name)
    monkeypatch.delitem(lp.LAYOUT_PROOFS, SHA)
    assert not lp.retained_issuer_name_matches(row, proof, name)


def test_decision2_exact_original_registrations():
    for sha, ticker, period, page, current, comparative in DECISION2_LAYOUTS:
        layout = lp.layout_for(sha)
        assert (layout['ticker'], layout['reporting_period'], layout['statement_scope']) == (ticker, period, 'consolidated')
        assert layout['statement_pages'] == (page,)
        assert layout['current_headers'] == (current,)
        assert layout['comparative_headers'] == (comparative,)
        assert layout['metric_line_codes'] == {'revenue': '10', 'net_income': '60', 'attributable_net_income': '61'}
        assert layout['approval'] == 'Owner directive 2026-11-25 task 5: Decision 2 admission expansion (governed acquisition + dual-reader)'
        assert layout['text_layer_verification']['state'] == 'HOST_VERIFICATION_REQUIRED'
        wrong_sha = sha[:-1] + ('0' if sha[-1] != '0' else '1')
        assert lp.layout_for(wrong_sha) is None


def test_decision2_proof_scope_and_literal_headers_fail_closed():
    import hashlib
    for sha, ticker, period, page, current, _ in DECISION2_LAYOUTS:
        tokens = base_tokens()
        # Synthetic positioned literal: verifies the gate, not a real OCR result.
        tokens[3] = tok(4, current, 1390, 1480, 540, 570, 2)
        row_object = copy.deepcopy(ROW)
        row_object['current_period_label'] = current
        row_object['column_bands']['header_evidence']['period_identities']['current'] = {
            'raw_text': current, 'source_token_orders': [4]}
        body = {k: v for k, v in make_proof(tokens).items() if k != 'proof_sha256'}
        body.update(document_sha256=sha, layout=lp.layout_for(sha)['layout'])
        body['pages'] = {str(page): body['pages'][str(PAGE)]}
        proof = {**body, 'proof_sha256': hashlib.sha256(lp.canonical_json(body).encode()).hexdigest()}
        assert lp.verify_proof_identity(proof, document_sha256=sha, proof_sha256=proof['proof_sha256']) == []
        assert 'OCR_PROOF_DOCUMENT_OR_LAYOUT_MISMATCH' in lp.verify_proof_identity(
            proof, document_sha256=SHA, proof_sha256=proof['proof_sha256'])
        unit_evidence = copy.deepcopy(UNIT)
        unit_evidence['evidence'].update(document_sha256=sha, page_number=page)
        row = dict(document_sha256=sha, ticker=ticker, reporting_period=period, statement_scope='consolidated',
                   ocr_layout_proof=lp.proof_reference(proof), source_page=page, canonical_metric='revenue',
                   line_code='10', raw_value_text='108.059.749.601.554', normalized_value=108059749601554,
                   source_unit_scale=1, currency='VND', ocr_row_object=row_object, ocr_unit_evidence=unit_evidence)
        metadata = {'metadata_claims': {'unit_scale': {'evidence_span': {'citation_kind': lp.STATEMENT_UNIT_CITATION_KIND}}}}
        args = dict(parse_amount=PA, parse_unit=PU)
        reason = ['VALUE_SPAN_NOT_IN_RETAINED_DOCUMENT']
        assert lp.apply_layout_proof(row, proof, metadata, reason, [], **args) == ([], [])
        for change in ({'ticker': 'HPG'}, {'reporting_period': '2024'}):
            refused, _ = lp.apply_layout_proof({**row, **change}, proof, metadata, reason, [], **args)
            assert 'OCR_LAYOUT_SCOPE_MISMATCH' in refused
            assert reason[0] in refused
        refused, _ = lp.apply_layout_proof({**row, 'source_page': page + 1}, proof, metadata, reason, [], **args)
        assert 'ROW_PAGE_OUTSIDE_REGISTERED_LAYOUT' in refused
        assert reason[0] in refused
        for bad_header in (current.lower(), current + ' ', '2025'):
            if bad_header == current:
                continue
            wrong = copy.deepcopy(row_object)
            wrong['current_period_label'] = bad_header
            wrong['column_bands']['header_evidence']['period_identities']['current']['raw_text'] = bad_header
            assert 'CURRENT_PERIOD_HEADER_NOT_REGISTERED' in lp.verify_row(
                wrong, proof, metric='revenue', source_page=page, line_code='10',
                raw_value=row['raw_value_text'], value=row['normalized_value'], unit_scale=1, parse_amount=PA)
