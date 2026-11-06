"""OCR glyph variants of explicit unit labels and the VAS interim operating-period phrase."""
from financial_statement_unit_resolution import parse_explicit_unit_declaration
from official_financial_period_identity import recognize_statement_period, recognize_unit_scale
from tools.run_reviewed_interim_canonical_ingress import ocr_page_text


def test_ocr_unit_label_variants_on_a_bare_declaration_line():
    for line in ("Bon vi: VND", "Don vj: VND", "Đơn vi: VND", "Don vj : VND"):
        parsed = parse_explicit_unit_declaration(line)
        assert parsed and parsed["currency"] == "VND" and parsed["unit_scale"] == 1, line


def test_ocr_unit_label_variant_refused_with_prose_scale_or_amount():
    for line in ("Bon vi: trieu VND", "Bon vi VND 1.000", "cac bon vi khac: VND va USD", "Bon vi VND", "Bonvi: EUR"):
        assert parse_explicit_unit_declaration(line) is None, line


def test_vas_interim_operating_period_phrase_is_h1():
    text = "Chº kỳ hºạt động 6 tháng kết thúc ngày 30 tháng 6 năm 2026"
    claim = recognize_statement_period(text)
    assert claim["period"] == "2026-H1" and claim["status"] == "EXPLICIT"


def test_operating_phrase_needs_six_months_and_june_end():
    assert recognize_statement_period("kỳ hoạt động 3 tháng kết thúc ngày 31 tháng 3 năm 2026")["period"] is None
    assert recognize_statement_period("kỳ hoạt động 6 tháng kết thúc ngày 31 tháng 12 năm 2026")["period"] is None


def test_ocr_page_text_keeps_line_boundaries_so_prose_is_not_a_unit_claim():
    def tok(order, line, text):
        return {"raw_token_order": order, "text": text, "tsv_hierarchy": {"block_num": 1, "par_num": 1, "line_num": line}}
    page = {"ocr_derived_text_evidence": {"tokens": [
        tok(1, 1, "Ban"), tok(2, 1, "giam"), tok(3, 1, "doc"), tok(4, 2, "cac"), tok(5, 2, "don"), tok(6, 2, "vi"),
        tok(7, 2, "thanh"), tok(8, 2, "vien"), tok(9, 3, "Tel:"), tok(10, 3, "1"), tok(11, 3, "ty"),
    ]}}
    text = ocr_page_text(page)
    assert text.splitlines() == ["Ban giam doc", "cac don vi thanh vien", "Tel: 1 ty"]
    assert recognize_unit_scale(text)["unit_scale"] != 1_000_000_000


def test_source_transition_peels_both_recognizers_and_refuses_drift(tmp_path):
    import hashlib, json, shutil
    from pathlib import Path
    import pytest
    from tools import verify_retention_reader_transition as v
    repo = Path(__file__).resolve().parents[1]
    rels = [v.OCR_RECOGNITION_MANIFEST, *v.OCR_RECOGNITION_SOURCES,
            *("tests/fixtures/ocr_unit_period_recognition_sources/" + s + ".txt" for s in v.OCR_RECOGNITION_SOURCES)]
    for rel in rels:
        (tmp_path / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo / rel, tmp_path / rel)
    spec = json.loads((repo / v.OCR_RECOGNITION_MANIFEST).read_bytes())
    for rel in v.OCR_RECOGNITION_SOURCES:
        live = (tmp_path / rel).read_bytes().replace(b"\r\n", b"\n")
        prior = v._ocr_recognition_prior_bytes(tmp_path, rel, live)
        assert hashlib.sha256(prior).hexdigest() == spec["sources"][rel]["prior_sha256_lf"]
    with pytest.raises(ValueError, match="OCR_RECOGNITION_SOURCE_TRANSITION_BINDING_INVALID"):
        v._ocr_recognition_prior_bytes(tmp_path, v.OCR_RECOGNITION_SOURCES[0], b"drift")
    assert v._ocr_recognition_prior_bytes(tmp_path, "other.py", b"x") == b"x"
