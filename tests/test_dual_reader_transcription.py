"""Owned synthetic image evidence through the common admission and H1 consumer.

No real issuer facts, model calls, source acquisition or admission are performed.
"""
from copy import deepcopy
import hashlib
import json
import unicodedata

import pytest
from official_financial_filing_evidence import admit_official_financial_fact, qualify_document_metadata
from stocklookup_core.evidence import dual_reader_transcription as dual
from stocklookup_core.evidence.official_document_qualification import admit_retained_financial_fact


@pytest.mark.parametrize("literal,expected", [("10", "10"), ("Trang 10", "10"),
    ("Trang 010", "010"), ("trang 10", "trang 10"), ("Trang  10", "Trang  10"),
    ("Trang Trang 10", "Trang Trang 10"), ("Trang 10 ", "Trang 10 "),
    ("Trang ١٠", "Trang ١٠"), ("Trang +10", "Trang +10")])
def test_exact_printed_page_identity(literal, expected):
    assert dual.printed_page_identity(literal) == expected


@pytest.mark.parametrize("suffix,accepted", [("\nThông tư số 43/2026/TT-BTC", True),
    (" Thông tư số 43/2026/TT-BTC", True), ("\nThông tư số 99/2025/TT-BTC", True),
    ("\nThông tư số 43/26/TT-BTC", False), ("\nThông tư số 43/2026/TT-BTC ", False),
    ("\nThông tư số 43/2026/TT-BTC\nextra", False), ("\nthông tư số 43/2026/TT-BTC", False),
    ("\tThông tư số 43/2026/TT-BTC", False)])
def test_exact_form_circular_suffix(suffix, accepted):
    form = "Mẫu số B 02a - DN/HN"
    assert (dual.form_code_literal(form + suffix) == form) is accepted


def test_agreed_unit_requires_two_identical_explicit_vnd_literals():
    from financial_statement_unit_resolution import parse_explicit_unit_declaration as parse
    literal = "Đơn vị tính: Đồng Việt Nam"
    tables = [{"currency_unit_literal": literal}, {"currency_unit_literal": literal}]
    assert dual.agreed_vnd_unit(tables, parse)["unit_scale"] == 1
    for other in (literal + " ", "Đơn vị tính: USD", None, "UNREADABLE"):
        assert dual.agreed_vnd_unit([tables[0], {"currency_unit_literal": other}], parse) is None
    assert dual.agreed_vnd_unit(tables[:1], parse) is None
    for literal in ("USD", "Đơn vị tính: USD", "UNREADABLE", ""):
        assert dual.agreed_vnd_unit([{"currency_unit_literal": literal}] * 2, parse) is None

def _sha(payload):
    return hashlib.sha256(payload).hexdigest()


def _bytes(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True).encode("utf-8")


def _pdf(text, *, image_only=False):
    # Owned, single-page ASCII PDF; the accounting value is deliberately absent
    # from its text layer. It is supplied only by the separately retained image readings.
    lines = [line.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)') for line in text.splitlines()]
    stream = ('BT /F1 10 Tf 40 760 Td ' + ' 0 -14 Td '.join('(' + line + ') Tj' for line in lines) + ' ET').encode('ascii')
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream']
    if image_only:
        # Owned raster-only PDF: no font or text operators for the loader to extract.
        objects[2] = (b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] '
                      b'/Resources << /XObject << /Im0 6 0 R >> >> /Contents 5 0 R >>')
        image_stream = b'q 612 0 0 792 0 0 cm /Im0 Do Q'
        objects[4] = (b'<< /Length ' + str(len(image_stream)).encode() + b' >>\nstream\n'
                      + image_stream + b'\nendstream')
        objects.append(b'<< /Type /XObject /Subtype /Image /Width 1 /Height 1 '
                       b'/ColorSpace /DeviceGray /BitsPerComponent 8 /Length 1 >>\nstream\n'
                       b'\xff\nendstream')
    output = b'%PDF-1.4\n'; offsets = []
    for n, obj in enumerate(objects, 1):
        offsets.append(len(output)); output += str(n).encode() + b' 0 obj\n' + obj + b'\nendobj\n'
    xref = len(output)
    output += b'xref\n0 ' + str(len(objects) + 1).encode() + b'\n0000000000 65535 f \n' + b''.join(f'{n:010d} 00000 n \n'.encode() for n in offsets)
    return output + b'trailer\n<< /Size ' + str(len(objects) + 1).encode() + b' /Root 1 0 R >>\nstartxref\n' + str(xref).encode() + b'\n%%EOF\n'


def _fixture(tmp_path, period="2026-H1", value=123, metric="attributable_net_income", *, image_only=False,
             native_text_override=None):
    from official_financial_assurance_evidence import resolve_native_document_assurance
    from official_financial_period_identity import period_bounds
    from official_source_registry import load_registry
    from financial_statement_template_recognizer import GENERIC_METRIC_RULES
    from financial_evidence_currency_contract import ISSUER_IR_INDEX_SEEDS
    from urllib.parse import urlsplit

    directory = tmp_path / (period + '-' + metric)
    directory.mkdir()
    proof_dir = directory / dual.PROOF_DIR; proof_dir.mkdir()
    annual = period == "2025"
    period_text = {"2025": "financial year ended 31 December 2025",
        "2026-H1": "six months ended 30 June 2026", "2025-H1": "six months ended 30 June 2025"}[period]
    status = "audited" if annual else "reviewed"
    assurance_title = ("BAO CAO KIEM TOAN DOC LAP chung toi da kiem toan hop nhat" if annual else
        "BAO CAO SOAT XET hop dong dich vu soat xet so 2410 hop nhat giua nien do")
    issuer = "PNJ synthetic fixture"
    native_text = '\n'.join([issuer, period_text, assurance_title, "consolidated", "Unit: VND"])
    payload = _pdf(native_text if native_text_override is None else native_text_override,
                   image_only=image_only); sha = _sha(payload)
    (directory / 'fixture.pdf').write_bytes(payload)
    label = GENERIC_METRIC_RULES[metric]["source_label"]
    label = ''.join(c for c in unicodedata.normalize('NFD', label.replace('đ', 'd').replace('Đ', 'D')) if not unicodedata.combining(c))
    code = {"revenue": "10", "net_income": "60", "attributable_net_income": "61"}[metric]
    raw = str(value) if value >= 0 else '(' + str(-value) + ')'
    url = "https://" + urlsplit(ISSUER_IR_INDEX_SEEDS["PNJ"]).hostname + "/test-only-synthetic-fixture.pdf"
    image_bytes = b'owned synthetic page image fixture ' + period.encode()
    (proof_dir / 'page.png').write_bytes(image_bytes)
    image = {"relative_path": dual.PROOF_DIR + '/page.png', "sha256": _sha(image_bytes),
             "source_page": 1, "printed_page": "1"}
    source = {"ticker": "PNJ", "issuer_name": issuer, "sha256": sha, "document_id": "synthetic-" + period,
        "source_id": "issuer_ir", "canonical_url": url, "final_url": url,
        "document_class": "audited_annual_financial_statements" if annual else "reviewed_interim_financial_statements",
        "acquisition_status": "retained", "observed_at": "2026-11-24T08:00:00+00:00",
        "reporting_period": period, "relative_path": "fixture.pdf", "rights_route": dual.RIGHTS_ROUTE,
        "acquisition_route": "INDEPENDENT_OFFICIAL_SOURCE", "rights_status": "RESEARCH_AND_AI_READING_APPROVED",
        "page_image_bindings": [image]}
    def span(text):
        return {"citation_id": "synthetic", "document_sha256": sha, "source_page": 1, "text": text}
    claims = {name: {"value": val, "evidence_span": span(text)} for name, val, text in (
        ("reporting_period", period, period_text), ("periodicity", "annual" if annual else "interim", period_text),
        ("statement_scope", "consolidated", "consolidated"), ("currency", "VND", "VND"),
        ("unit_scale", 1, "Unit: VND"))}
    metadata = qualify_document_metadata({"issuer_identity": "PNJ", "entity_type": "corporate",
        "document": {"document_id": source["document_id"], "sha256": sha, "source_locator": url,
            "source_id": "issuer_ir", "observed_at": source["observed_at"], "immutable_bytes_verified": True}, "metadata": claims})
    start, end = period_bounds(period)
    row = {"ticker": "PNJ", "canonical_metric": metric, "line_code": code, "reporting_period": period,
        "period_start": start, "period_end": end, "period_type": "annual" if annual else "interim",
        "statement_family": "income_statement", "statement_scope": "consolidated", "currency": "VND",
        "unit_scale": 1, "source_unit_scale": 1, "raw_row_label": label, "raw_value_text": raw,
        "normalized_value": value, "source_span": span(label + ' ' + raw), "citation_id": "synthetic",
        "source_page": 1, "document_sha256": sha, "document_metadata": metadata,
        "audit_or_review_status": status, "assurance_evidence": resolve_native_document_assurance(sha, {1: native_text}),
        "observed_at": source["observed_at"], "knowledge_available_at": "2026-11-24T09:03:00+00:00",
        "qualification_state": "QUALIFIED", "issuer_literal": issuer, "column_id": "current",
        "current_period_label": "Current period", "form_reference_literal": "B 02a-DN/HN",
        "statement_title_literal": "Consolidated income statement", "evidence_subdir": directory.name}
    table = {"issuer_literal": issuer, "statement_title_literal": row["statement_title_literal"],
        "scope_literal": "consolidated", "form_reference_literal": row["form_reference_literal"],
        "currency_unit_literal": "Unit: VND", "period_caption_literal": period_text,
        "columns": [{"column_id": "current", "label_literal": "Current period", "reporting_period": period, "role": "current"}],
        "rows": [{"line_code_literal": code, "row_label_literal": label, "cells": [{"column_id": "current",
            "raw_value_literal": raw, "sign_literal": "parentheses" if value < 0 else "unsigned", "uncertainty": []}]}]}
    refs = []
    for i, family in enumerate(("openai-gpt", "google-gemini")):
        reading = {"contract_version": dual.RAW_VERSION, "model_family": family, "reader_id": family,
            "recorded_at": f"2026-11-24T09:0{i}:00+00:00", "method": "DIRECT_PAGE_IMAGE",
            "independent_input": True, "saw_other_reader_output": False,
            "input": {"document_sha256": sha, "document_id": source["document_id"],
                "image_sha256": image["sha256"], "source_page": 1, "printed_page": "1"}, "table": deepcopy(table)}
        content = _bytes(reading); name = f'reader-{i}.raw.json'
        (proof_dir / name).write_bytes(content)
        refs.append({"relative_path": dual.PROOF_DIR + '/' + name, "sha256": _sha(content),
                     "retained_at": f"2026-11-24T09:0{i}:01+00:00"})
    proof = {"contract_version": dual.CONTRACT_VERSION, "document_sha256": sha,
        "document_id": source["document_id"], "page_image": image, "readings": refs,
        "comparison_started_at": "2026-11-24T09:02:00+00:00", "admission_completed_at": "2026-11-24T09:03:00+00:00"}
    row["dual_reader_transcription"] = {"relative_path": dual.PROOF_DIR + '/agreement.json'}
    _seal(directory, row, proof)
    (directory / 'official_document_acquisition_manifest.json').write_bytes(_bytes({"records": [source]}))
    context = {"source_record": source, "retained_bytes": payload, "registry": load_registry(), "document_pages": {1: native_text}}
    return row, context, directory, proof


def _seal(directory, row, proof):
    content = _bytes(proof)
    (directory / row["dual_reader_transcription"]["relative_path"]).write_bytes(content)
    row["dual_reader_transcription"]["proof_sha256"] = _sha(content)


def _change_reader(directory, row, proof, change, index=1):
    path = directory / proof["readings"][index]["relative_path"]
    raw = json.loads(path.read_bytes()); change(raw)
    content = _bytes(raw); path.write_bytes(content)
    proof["readings"][index]["sha256"] = _sha(content)
    _seal(directory, row, proof)


def _pure(row, context, directory):
    return admit_official_financial_fact(row, dual_reader_proof=dual.load_retained_dual_reader_proof(row, directory), **context)


@pytest.mark.parametrize("metric,literal,value", [
    ("revenue", "6.965.748.286.065", 6965748286065),
    ("net_income", "1.861.407.508.211", 1861407508211),
    ("attributable_net_income", "1.743.741.158.759", 1743741158759),
])
def test_explicit_annual_header_repeated_as_column_period(tmp_path, metric, literal, value):
    row, context, directory, proof = _fixture(tmp_path, period="2025", metric=metric, value=value)
    row.update(current_period_label="Năm 2025", raw_value_text=literal)
    row["source_span"]["text"] = row["raw_row_label"] + " " + literal
    def change(raw):
        raw["table"]["columns"][0].update(label_literal="Năm 2025", reporting_period="Năm 2025")
        raw["table"]["rows"][0]["cells"][0]["raw_value_literal"] = literal
    for index in (0, 1):
        _change_reader(directory, row, proof, change, index=index)
    # The owned PDF contains none of these amounts. Admission must therefore
    # verify the dual proof, including sign/scale, to waive text presence.
    result = _pure(row, context, directory)
    assert result["state"] == "ADMITTED", result["reason_codes"]


@pytest.mark.parametrize("period,column_period,caption", [
    ("2025", "Năm 2024", None),
    ("2025", "Năm 2025", "financial year ended 31 December 2024"),
    ("2026-H1", "Năm 2026", None),
])
def test_annual_header_binding_preserves_period_conflicts(tmp_path, period, column_period, caption):
    row, context, directory, proof = _fixture(tmp_path, period=period)
    row["current_period_label"] = "Năm " + period[:4]
    def change(raw):
        raw["table"]["columns"][0].update(label_literal=row["current_period_label"], reporting_period=column_period)
        if caption is not None:
            raw["table"]["period_caption_literal"] = caption
    for index in (0, 1):
        _change_reader(directory, row, proof, change, index=index)
    assert "DUAL_READER_SEMANTIC_BINDING_MISMATCH" in _pure(row, context, directory)["reason_codes"]


@pytest.mark.parametrize("metric", ["revenue", "net_income", "attributable_net_income"])
@pytest.mark.parametrize("difference", ["missing_scope", "form_suffix"])
def test_h1_scope_and_form_literal_differences_still_block(tmp_path, metric, difference):
    row, context, directory, proof = _fixture(tmp_path, metric=metric)
    if difference == "missing_scope":
        _change_reader(directory, row, proof, lambda raw: raw["table"].update(scope_literal=None), index=0)
    else:
        _change_reader(directory, row, proof, lambda raw: raw["table"].update(
            # HL rule 2026-11-25: an exact trailing "Thông tư số N/YYYY/TT-BTC" line is excluded
            # (admitted in test_form_circular_suffix_admits_and_preserves_raw); any other suffix still disagrees.
            form_reference_literal=row["form_reference_literal"] + " Thông tư 43/2026/TT-BTC"))
    assert "DUAL_READER_LITERAL_DISAGREEMENT" in _pure(row, context, directory)["reason_codes"]


def test_same_common_pipeline_requires_raw_replay_and_labels_research(tmp_path):
    row, context, directory, _ = _fixture(tmp_path)
    no_proof = admit_official_financial_fact(row, **context)
    assert no_proof['state'] == 'BLOCKED'
    assert 'DUAL_READER_RETAINED_PROOF_UNAVAILABLE' in no_proof['reason_codes']
    pure = _pure(row, context, directory)
    retained = admit_retained_financial_fact(row, evidence_root=tmp_path, registry=context['registry'])
    assert pure['state'] == retained['state'] == 'ADMITTED', (pure, retained)
    assert retained['admission_basis'] == dual.EVIDENCE_TIER
    assert retained['evidence_classification']['authority_effect'] == 'OFFLINE_RESEARCH_ONLY'
    assert retained['evidence_classification']['knowledge_floor'] == row['knowledge_available_at']
    assert retained['evidence_classification']['pit_backtest_eligible'] is False
    native = deepcopy(row); native.pop('dual_reader_transcription')
    assert admit_official_financial_fact(native, **context)['state'] != 'ADMITTED'


@pytest.mark.parametrize('family', ['openai-gpt', 'gpt', 'codex'])
def test_same_family_account_or_product_is_not_independent(tmp_path, family):
    row, context, directory, proof = _fixture(tmp_path)
    _change_reader(directory, row, proof, lambda r: r.update(model_family=family))
    assert 'DUAL_READER_DIFFERENT_MODEL_FAMILIES_REQUIRED' in _pure(row, context, directory)['reason_codes']


def test_two_gemini_accounts_are_one_family(tmp_path):
    row, context, directory, proof = _fixture(tmp_path)
    _change_reader(directory, row, proof, lambda r: r.update(model_family='gemini'), index=0)
    assert 'DUAL_READER_DIFFERENT_MODEL_FAMILIES_REQUIRED' in _pure(row, context, directory)['reason_codes']


def test_overlay_success_flags_never_replace_retained_files(tmp_path):
    row, context, directory, _ = _fixture(tmp_path)
    row['dual_reader_transcription'] = {'valid': True, 'state': 'ADMITTED', 'model_families': ['gpt', 'gemini']}
    assert admit_retained_financial_fact(row, evidence_root=tmp_path, registry=context['registry'])['state'] == 'BLOCKED'
    assert admit_official_financial_fact(row, dual_reader_proof={'valid': True}, **context)['state'] == 'BLOCKED'


@pytest.mark.parametrize('key', ['issuer_literal', 'scope_literal', 'form_reference_literal',
    'statement_title_literal', 'currency_unit_literal', 'period_caption_literal'])
def test_header_disagreement_cannot_be_normalized_away(tmp_path, key):
    row, context, directory, proof = _fixture(tmp_path)
    _change_reader(directory, row, proof, lambda r: r['table'].update({key: 'different literal'}))
    assert 'DUAL_READER_LITERAL_DISAGREEMENT' in _pure(row, context, directory)['reason_codes']


@pytest.mark.parametrize('key,value', [('document_sha256', 'f'*64), ('image_sha256', 'e'*64),
    ('source_page', 2), ('printed_page', '2'), ('document_id', 'other document')])
def test_reader_input_is_exact_document_image_and_page(tmp_path, key, value):
    row, context, directory, proof = _fixture(tmp_path)
    _change_reader(directory, row, proof, lambda r: r['input'].update({key: value}))
    assert 'DUAL_READER_INPUT_BINDING_MISMATCH' in _pure(row, context, directory)['reason_codes']


@pytest.mark.parametrize('case,reason', [
    ('comparative', 'DUAL_READER_CURRENT_COLUMN_NOT_EXPLICIT'),
    ('unit', 'DUAL_READER_CURRENCY_UNIT_MISMATCH'),
    ('sign', 'DUAL_READER_VALUE_OR_SIGN_MISMATCH'),
    ('unknown', 'DUAL_READER_UNREADABLE_OR_MISSING_LITERAL'),
    ('uncertainty', 'DUAL_READER_UNRESOLVED_CELL_UNCERTAINTY'),
])
def test_agreement_alone_cannot_prove_false_semantics(tmp_path, case, reason):
    row, context, directory, proof = _fixture(tmp_path)
    def change(raw):
        table = raw['table']
        if case == 'comparative': table['columns'][0]['label_literal'] = 'Kỳ trước'
        if case == 'unit': table['currency_unit_literal'] = 'Unit: thousand VND'
        if case == 'sign': table['rows'][0]['cells'][0]['sign_literal'] = 'parentheses'
        if case == 'unknown': table['rows'][0]['row_label_literal'] = 'UNREADABLE'
        if case == 'uncertainty': table['rows'][0]['cells'][0]['uncertainty'] = ['uncertain digit']
    for index in (0, 1): _change_reader(directory, row, proof, change, index=index)
    if case == 'comparative': row['current_period_label'] = 'Kỳ trước'
    assert reason in _pure(row, context, directory)['reason_codes']


@pytest.mark.parametrize('independence', [True, None])
def test_reader_who_saw_other_output_is_rejected(tmp_path, independence):
    row, context, directory, proof = _fixture(tmp_path)
    _change_reader(directory, row, proof, lambda r: r.update(saw_other_reader_output=independence))
    assert 'DUAL_READER_INDEPENDENCE_NOT_PROVEN' in _pure(row, context, directory)['reason_codes']


@pytest.mark.parametrize('field,value', [('raw_value_literal', '124'), ('sign_literal', 'parentheses'), ('uncertainty', ['UNREADABLE'])])
def test_literal_sign_and_uncertainty_disagreement_blocks(tmp_path, field, value):
    row, context, directory, proof = _fixture(tmp_path)
    _change_reader(directory, row, proof, lambda r: r['table']['rows'][0]['cells'][0].update({field: value}))
    assert 'DUAL_READER_LITERAL_DISAGREEMENT' in _pure(row, context, directory)['reason_codes']


@pytest.mark.parametrize('target', ['raw', 'image', 'proof', 'source', 'escape'])
def test_retained_loader_refuses_tampered_bytes_and_path_escape(tmp_path, target):
    row, context, directory, proof = _fixture(tmp_path)
    if target == 'raw':
        (directory / proof['readings'][1]['relative_path']).write_bytes(b'{"forged":true}')
    elif target == 'image':
        (directory / proof['page_image']['relative_path']).write_bytes(b'changed')
    elif target == 'proof':
        (directory / row['dual_reader_transcription']['relative_path']).write_bytes(b'{"valid":true}')
    elif target == 'source':
        (directory / 'fixture.pdf').write_bytes(b'%PDF changed')
    else:
        row['dual_reader_transcription']['relative_path'] = '../agreement.json'
    result = admit_retained_financial_fact(row, evidence_root=tmp_path, registry=context['registry'])
    assert result['state'] != 'ADMITTED', result


@pytest.mark.parametrize('field', ['rights_route', 'rights_status', 'acquisition_route', 'page_image_bindings'])
def test_source_rights_unknown_or_image_unbound_is_not_admission(tmp_path, field):
    row, context, directory, _ = _fixture(tmp_path)
    context['source_record'].pop(field)
    (directory / 'official_document_acquisition_manifest.json').write_bytes(_bytes({'records': [context['source_record']]}))
    result = admit_retained_financial_fact(row, evidence_root=tmp_path, registry=context['registry'])
    assert result['state'] == 'BLOCKED'
    assert any(r.startswith('DUAL_READER_') for r in result['reason_codes'])


def test_knowledge_floor_and_cutoff_never_backdate(tmp_path):
    row, context, directory, proof = _fixture(tmp_path)
    old = deepcopy(row); old['knowledge_available_at'] = '2026-11-24T09:01:00+00:00'
    assert 'DUAL_READER_KNOWLEDGE_PRECEDES_COMPLETION' in _pure(old, context, directory)['reason_codes']
    early = admit_retained_financial_fact(row, evidence_root=tmp_path, registry=context['registry'], cutoff='2026-11-24T09:02:00+00:00')
    assert early['state'] == 'BLOCKED' and 'AFTER_KNOWLEDGE_CUTOFF' in early['reason_codes']
    proof['readings'][1]['retained_at'] = proof['comparison_started_at']; _seal(directory, row, proof)
    assert 'DUAL_READER_RAW_NOT_RETAINED_BEFORE_COMPARISON' in _pure(row, context, directory)['reason_codes']


@pytest.mark.parametrize('change,reason', [
    ({'blockers': ['unresolved restatement']}, 'FACT_QUALIFICATION_BLOCKED'),
    ({'conflicts': ['other fact value']}, 'FACT_QUALIFICATION_BLOCKED'),
    ({'normalized_value': 999}, 'LITERAL_VALUE_NORMALIZATION_NOT_BOUND'),
    ({'currency': 'USD'}, 'DOCUMENT_CURRENCY_MISMATCH'),
    ({'statement_scope': 'separate'}, 'FACT_SEMANTIC_IDENTITY_INCOMPLETE'),
    ({'line_code': '60'}, 'METRIC_LINE_CODE_IDENTITY_CONFLICT'),
])
def test_dual_reading_never_removes_other_admission_gates(tmp_path, change, reason):
    row, context, directory, _ = _fixture(tmp_path); row.update(change)
    result = _pure(row, context, directory)
    assert result['state'] == 'BLOCKED' and reason in result['reason_codes'], result


def test_metadata_and_assurance_are_still_independently_required(tmp_path):
    row, context, directory, _ = _fixture(tmp_path)
    no_metadata = deepcopy(context); no_metadata['document_pages'] = {1: ''}
    result = _pure(row, no_metadata, directory)
    assert result['state'] == 'BLOCKED' and 'METADATA_LITERAL_NOT_IN_RETAINED_DOCUMENT' in result['reason_codes']
    row['assurance_evidence'] = None
    assert _pure(row, context, directory)['state'] != 'ADMITTED'


def test_unrelated_row_conflict_does_not_block_this_fact(tmp_path):
    row, context, directory, proof = _fixture(tmp_path)
    for index in (0, 1):
        _change_reader(directory, row, proof, lambda r, i=index: r['table']['rows'].append({
            'line_code_literal': '60', 'row_label_literal': 'Other metric',
            'cells': [{'column_id': 'current', 'raw_value_literal': str(999+i), 'sign_literal': 'unsigned', 'uncertainty': []}]}), index=index)
    assert _pure(row, context, directory)['state'] == 'ADMITTED'


def test_real_common_admission_supplies_h1_bridge_and_fact_local_conflict(tmp_path, monkeypatch):
    from stocklookup_core.financial.financial_analysis_engine_v2 import official_h1_ttm_features
    import stocklookup_core.evidence.official_document_qualification as owner
    rows = []
    registry = None
    for period, value in (('2025', 100), ('2026-H1', 60), ('2025-H1', 40)):
        row, context, directory, proof = _fixture(tmp_path, period, value)
        rows.append(row); registry = context['registry']
    # Only supply an existing registry fixture. The retained loader and pure
    # admission are real and are never replaced with a success stub.
    monkeypatch.setattr(owner, 'load_registry', lambda: registry)
    result = official_h1_ttm_features(ticker='PNJ', rows=rows, cutoff='2026-11-24T09:04:00+00:00', evidence_root=tmp_path)
    feature = result['attributable_net_income_ttm']
    assert feature['fitness'] == 'READY' and feature['value'] == 120, feature
    assert all(p['evidence_tier'] == dual.EVIDENCE_TIER for p in feature['provider_source_provenance'])
    assert all(not p['evidence_classification']['pit_backtest_eligible'] for p in feature['provider_source_provenance'])
    early = official_h1_ttm_features(ticker='PNJ', rows=rows, cutoff='2026-11-24T09:02:00+00:00', evidence_root=tmp_path)
    assert early['attributable_net_income_ttm']['fitness'] == 'BLOCKED_BY_EVIDENCE'
    # A second, independently admitted source for the same fact conflicts.
    other_root = tmp_path / 'other'; other_root.mkdir()
    other, _, _, _ = _fixture(other_root, '2025-H1', 41)
    other['evidence_subdir'] = 'other/' + other['evidence_subdir']
    conflicted = official_h1_ttm_features(ticker='PNJ', rows=rows + [other], cutoff='2026-11-24T09:04:00+00:00', evidence_root=tmp_path)
    assert 'OFFICIAL_H1_OPERAND_CONFLICT:2025-H1' in conflicted['attributable_net_income_ttm']['reason_codes']


# --- Real-shaped (still synthetic) retained readings: HPG-like page layout -------------
# Two columns read as printed (current/comparative), the current column's period stated by
# the shared caption (one reader leaves it null, the other copies the caption), and the
# outline enumerator from the numbering column included by only one reader.
_ENUMERATORS = {"10": "3.", "60": "17.", "61": "17.1"}


def _real_shape(directory, row, proof, *, enumerators=("", None), periods=(None, "caption"), labels=(None, None)):
    for index in (0, 1):
        def change(raw, i=index):
            table = raw['table']
            base = table['rows'][0]
            code = base['line_code_literal']
            prefix = {None: _ENUMERATORS[code] + ' ', '': ''}.get(enumerators[i], (enumerators[i] or '') + ' ')
            current = {'caption': table['period_caption_literal']}.get(periods[i], periods[i])
            table['columns'] = [
                {'column_id': 'c1', 'label_literal': 'Kỳ này', 'reporting_period': current, 'role': 'current'},
                {'column_id': 'c2', 'label_literal': 'Kỳ trước', 'reporting_period': None, 'role': 'comparative'}]
            table['rows'] = [
                {'line_code_literal': code, 'row_label_literal': prefix + (labels[i] or base['row_label_literal']),
                 'cells': [{**base['cells'][0], 'column_id': 'c1'},
                           {'column_id': 'c2', 'raw_value_literal': '6.189.851.834.853', 'sign_literal': 'unsigned', 'uncertainty': []}]},
                {'line_code_literal': '62', 'row_label_literal': '17.2 Lợi nhuận/(Lỗ) sau thuế của cổ đông không kiểm soát',
                 'cells': [{'column_id': 'c1', 'raw_value_literal': '1.094.513.836', 'sign_literal': 'parentheses', 'uncertainty': []},
                           {'column_id': 'c2', 'raw_value_literal': '13.557.615.464', 'sign_literal': 'unsigned', 'uncertainty': []}]}]
        _change_reader(directory, row, proof, change, index=index)
    row.update(column_id='c1', current_period_label='Kỳ này')


@pytest.mark.parametrize('metric', ['revenue', 'net_income', 'attributable_net_income'])
def test_real_shaped_retained_proof_replays_through_common_admission(tmp_path, metric):
    row, context, directory, proof = _fixture(tmp_path, '2025-H1', 7600771906152, metric)
    _real_shape(directory, row, proof)
    retained = admit_retained_financial_fact(row, evidence_root=tmp_path, registry=context['registry'])
    assert retained['state'] == 'ADMITTED', retained
    assert retained['admission_basis'] == dual.EVIDENCE_TIER
    assert retained['evidence_classification']['pit_backtest_eligible'] is False
    assert retained['evidence_classification']['authority_effect'] == 'OFFLINE_RESEARCH_ONLY'


def test_outline_enumerator_split_keeps_text_verbatim():
    assert dual.split_outline_enumerator('17.1 Lợi nhuận sau thuế') == ('17.1', 'Lợi nhuận sau thuế')
    assert dual.split_outline_enumerator('18 Lãi cơ bản') == ('18', 'Lãi cơ bản')
    assert dual.split_outline_enumerator('3. Doanh thu') == ('3.', 'Doanh thu')
    assert dual.split_outline_enumerator('2025 revenue') == (None, '2025 revenue')
    assert dual.split_outline_enumerator('Doanh thu 10') == (None, 'Doanh thu 10')


@pytest.mark.parametrize('kwargs', [
    {'enumerators': ('17.1', '17.2')},                               # both printed, disagree
    {'labels': (None, 'Lợi nhuận khác')},                            # line item text differs
    {'periods': (None, 'Cho kỳ hoạt động 6 tháng kết thúc ngày 30 tháng 6 năm 2024')},  # one non-caption period
])
def test_real_shaped_literal_disagreement_still_blocks(tmp_path, kwargs):
    row, context, directory, proof = _fixture(tmp_path, '2025-H1', 7600771906152)
    _real_shape(directory, row, proof, **kwargs)
    assert 'DUAL_READER_LITERAL_DISAGREEMENT' in _pure(row, context, directory)['reason_codes']


def test_agreed_column_period_must_still_be_the_fact_period(tmp_path):
    row, context, directory, proof = _fixture(tmp_path, '2025-H1', 7600771906152)
    other = 'Cho kỳ hoạt động 6 tháng kết thúc ngày 30 tháng 6 năm 2024'
    _real_shape(directory, row, proof, periods=(other, other))
    assert 'DUAL_READER_SEMANTIC_BINDING_MISMATCH' in _pure(row, context, directory)['reason_codes']


def test_row_label_with_enumerator_is_not_the_bound_label(tmp_path):
    row, context, directory, proof = _fixture(tmp_path, '2025-H1', 7600771906152)
    _real_shape(directory, row, proof)
    row['raw_row_label'] = '17.1 ' + row['raw_row_label']
    row['source_span']['text'] = row['raw_row_label'] + ' ' + row['raw_value_text']
    assert 'DUAL_READER_SEMANTIC_BINDING_MISMATCH' in _pure(row, context, directory)['reason_codes']


def _ocr_page_proof(monkeypatch, row):
    from stocklookup_core.evidence import official_ocr_layout_proof as ocr
    sha = row['document_sha256']
    monkeypatch.setitem(ocr.LAYOUT_PROOFS, sha, {'ticker': row['ticker'], 'reporting_period': row['reporting_period'],
        'statement_scope': 'consolidated', 'layout': 'SYNTHETIC_TEST_ONLY', 'statement_pages': (1,)})
    body = {'contract_version': ocr.CONTRACT_VERSION, 'document_sha256': sha, 'layout': 'SYNTHETIC_TEST_ONLY',
            'engine_version': 'synthetic', 'ocr_config': {}, 'pages': {}}
    proof = {**body, 'proof_sha256': _sha(ocr.canonical_json(body).encode('utf-8'))}
    row['ocr_layout_proof'] = {'contract_version': ocr.CONTRACT_VERSION, 'proof_sha256': proof['proof_sha256'],
                               'relative_path': ocr.PROOF_DIR + '/synthetic.json'}
    return proof


def test_dual_row_reuses_ocr_page_proof_only_for_document_text(tmp_path, monkeypatch):
    row, context, directory, proof = _fixture(tmp_path, '2025-H1', 7600771906152)
    _real_shape(directory, row, proof)
    ocr_proof = _ocr_page_proof(monkeypatch, row)
    loaded = dual.load_retained_dual_reader_proof(row, directory)
    admitted = admit_official_financial_fact(row, dual_reader_proof=loaded, ocr_layout_proof=ocr_proof, **context)
    assert admitted['state'] == 'ADMITTED' and admitted['admission_basis'] == dual.EVIDENCE_TIER, admitted
    # The reused page proof keeps its own identity and scope gates.
    forged = {**ocr_proof, 'engine_version': 'changed'}
    result = admit_official_financial_fact(row, dual_reader_proof=loaded, ocr_layout_proof=forged, **context)
    assert result['state'] == 'BLOCKED' and 'OCR_PROOF_HASH_MISMATCH' in result['reason_codes']
    missing = admit_official_financial_fact(row, dual_reader_proof=loaded, **context)
    assert missing['state'] != 'ADMITTED' and 'OCR_LAYOUT_PROOF_UNAVAILABLE' in missing['reason_codes']
    # Without a valid dual reading the OCR row proof is required again.
    invalid = admit_official_financial_fact(row, ocr_layout_proof=ocr_proof, **context)
    assert invalid['state'] == 'BLOCKED' and 'ROW_PROOF_MISSING' in invalid['reason_codes'], invalid


def test_real_shaped_rows_feed_h1_bridge_for_codes_60_and_61(tmp_path, monkeypatch):
    from stocklookup_core.financial.financial_analysis_engine_v2 import official_h1_ttm_features
    import stocklookup_core.evidence.official_document_qualification as owner
    rows, registry = [], None
    values = {('2025', 'net_income'): 100, ('2026-H1', 'net_income'): 60, ('2025-H1', 'net_income'): 40,
              ('2025', 'attributable_net_income'): 90, ('2026-H1', 'attributable_net_income'): 55,
              ('2025-H1', 'attributable_net_income'): 35}
    for (period, metric), value in values.items():
        row, context, directory, proof = _fixture(tmp_path, period, value, metric)
        if period == '2025-H1':
            _real_shape(directory, row, proof)
        rows.append(row); registry = context['registry']
    monkeypatch.setattr(owner, 'load_registry', lambda: registry)
    result = official_h1_ttm_features(ticker='PNJ', rows=rows, cutoff='2026-11-24T09:04:00+00:00', evidence_root=tmp_path)
    for fid, expected, attribution in (('net_income_ttm', 120, 'TOTAL_PROFIT_AFTER_TAX_INCLUDING_NCI'),
                                       ('attributable_net_income_ttm', 110, 'PARENT_ATTRIBUTABLE')):
        feature = result[fid]
        assert feature['fitness'] == 'READY' and feature['value'] == expected, feature
        assert feature['earnings_attribution'] == attribution
        assert feature['authority_effect'] == 'OFFLINE_RESEARCH_ONLY' and feature['pit_backtest_eligible'] is False
        prior = [p for p in feature['provider_source_provenance'] if p['reporting_period'] == '2025-H1']
        assert prior and prior[0]['evidence_tier'] == dual.EVIDENCE_TIER


# --- Annual B 02 - DN/HN shape (PNJ-like, still synthetic): owner-approved rules 1-3 ----------
_YEARLESS_CAPTION = 'Năm tài chính kết thúc ngày 31 tháng 12 năm'
_COLUMN_PERIOD = 'Năm tài chính kết thúc ngày 31 tháng 12 năm 2025'


def _annual_shape(directory, row, proof, *, labels=('2025', '2025 VND'), unit='VND', caption=_YEARLESS_CAPTION,
                  periods=(_COLUMN_PERIOD, _COLUMN_PERIOD), roles=('current', 'current')):
    for index in (0, 1):
        def change(raw, i=index):
            table = raw['table']
            table.update(currency_unit_literal=unit, period_caption_literal=caption)
            table['columns'] = [
                {'column_id': 'c1', 'label_literal': labels[i], 'reporting_period': periods[i], 'role': roles[i]},
                {'column_id': 'c2', 'label_literal': labels[i].replace('2025', '2024'),
                 'reporting_period': _COLUMN_PERIOD.replace('2025', '2024'), 'role': 'comparative'}]
            base = table['rows'][0]
            base['cells'] = [{**base['cells'][0], 'column_id': 'c1'},
                             {'column_id': 'c2', 'raw_value_literal': '2.112.916.282.946', 'sign_literal': 'unsigned', 'uncertainty': []}]
        _change_reader(directory, row, proof, change, index=index)
    row.update(column_id='c1', current_period_label=min(labels, key=len))


@pytest.mark.parametrize('metric', ['revenue', 'net_income', 'attributable_net_income'])
def test_annual_trailing_unit_label_yearless_caption_and_bare_vnd_admit(tmp_path, metric):
    row, context, directory, proof = _fixture(tmp_path, '2025', 2828497462890, metric)
    _annual_shape(directory, row, proof)
    retained = admit_retained_financial_fact(row, evidence_root=tmp_path, registry=context['registry'])
    assert retained['state'] == 'ADMITTED' and retained['admission_basis'] == dual.EVIDENCE_TIER, retained
    assert retained['evidence_classification']['literal_normalizations'] == [{
        'field': 'column.label_literal', 'column_id': 'c1', 'reader_literals': ['2025', '2025 VND'],
        'agreed': '2025', 'rule': 'TRAILING_CURRENCY_UNIT_TOKEN'}]


def test_identical_annual_labels_record_no_normalization(tmp_path):
    row, context, directory, proof = _fixture(tmp_path, '2025', 2828497462890)
    _annual_shape(directory, row, proof, labels=('2025', '2025'))
    result = _pure(row, context, directory)
    assert result['state'] == 'ADMITTED', result
    assert 'literal_normalizations' not in result['evidence_classification']


@pytest.mark.parametrize('labels', [('2025', '2025 USD'), ('2025', '2024'), ('2025', 'VND 2025'),
                                    ('2025', '2025 VND VND'), ('2025', '2025VND'), ('2025', '2025 vnd')])
def test_column_label_rule_one_only_accepts_trailing_agreed_unit(tmp_path, labels):
    row, context, directory, proof = _fixture(tmp_path, '2025', 2828497462890)
    _annual_shape(directory, row, proof, labels=labels)
    assert 'DUAL_READER_LITERAL_DISAGREEMENT' in _pure(row, context, directory)['reason_codes']


@pytest.mark.parametrize('case', ['column_year_mismatch', 'metadata_period_mismatch', 'role_not_current',
                                  'no_period_anywhere'])
def test_yearless_caption_needs_current_column_period_matching_fact_and_metadata(tmp_path, case):
    row, context, directory, proof = _fixture(tmp_path, '2025', 2828497462890)
    if case == 'column_year_mismatch':
        _annual_shape(directory, row, proof, labels=('2024', '2024 VND'), periods=(None, None))
        row['current_period_label'] = '2024'
    elif case == 'metadata_period_mismatch':
        _annual_shape(directory, row, proof, periods=(None, None))
        row['document_metadata']['metadata_claims']['reporting_period']['value'] = '2024'
    elif case == 'role_not_current':
        _annual_shape(directory, row, proof, roles=('unknown', 'unknown'))
    else:
        _annual_shape(directory, row, proof, labels=('Năm nay', 'Năm nay VND'), periods=(None, None))
        row['current_period_label'] = 'Năm nay'
    result = _pure(row, context, directory)
    assert result['state'] == 'BLOCKED'
    assert ('DUAL_READER_SEMANTIC_BINDING_MISMATCH' in result['reason_codes']
            or 'DUAL_READER_CURRENT_COLUMN_NOT_EXPLICIT' in result['reason_codes']), result


@pytest.mark.parametrize('unit', ['VNĐ triệu', 'Triệu VND', 'Nghìn VND', 'vnd', 'VND ', 'USD', 'VND/USD'])
def test_only_whole_bare_vnd_is_added_other_units_keep_existing_handling(tmp_path, unit):
    row, context, directory, proof = _fixture(tmp_path, '2025', 2828497462890)
    _annual_shape(directory, row, proof, labels=('2025', '2025'), unit=unit)
    assert 'DUAL_READER_CURRENCY_UNIT_MISMATCH' in _pure(row, context, directory)['reason_codes']


def test_bare_vnd_mapping_is_single_and_delegates_otherwise():
    from financial_statement_unit_resolution import parse_explicit_unit_declaration as parse
    assert dual._unit('VND', parse)['currency'] == 'VND' and dual._unit('VND', parse)['unit_scale'] == 1
    for literal in ('Đơn vị: VND', 'Đơn vị: Triệu VND', 'Nghìn VND', 'VNĐ triệu', 'vnd'):
        assert dual._unit(literal, parse) == parse(literal)
    assert dual._unit('Đơn vị: VND', parse)['unit_scale'] == 1


# --- Form reference dash variants (Head Leader decision): identity matching only ----------------
def _set_form(directory, row, proof, forms):
    for index in (0, 1):
        _change_reader(directory, row, proof,
                       lambda raw, i=index: raw['table'].update(form_reference_literal=forms[i]), index=index)
    row['form_reference_literal'] = forms[0]


@pytest.mark.parametrize('form', ['Mẫu số B 02 – DN/HN', 'Mẫu số B 02 — DN/HN', 'Mẫu số B 02a‐DN/HN',
                                  'MẪU SỐ B 02a ‑ DN/HN'])
def test_form_reference_dash_variants_match_and_are_recorded(tmp_path, form):
    row, context, directory, proof = _fixture(tmp_path, '2025', 2828497462890)
    _annual_shape(directory, row, proof)
    _set_form(directory, row, proof, (form, form))
    result = admit_retained_financial_fact(row, evidence_root=tmp_path, registry=context['registry'])
    assert result['state'] == 'ADMITTED', result
    recorded = [n for n in result['evidence_classification']['literal_normalizations']
                if n['rule'] == 'FORM_REFERENCE_DASH_VARIANT']
    assert recorded == [{'field': 'form_reference_literal', 'agreed': form,
                         'matched_as': recorded[0]['matched_as'], 'rule': 'FORM_REFERENCE_DASH_VARIANT'}]
    assert '-DN/HN' in recorded[0]['matched_as']


def test_ascii_form_records_no_dash_normalization(tmp_path):
    row, context, directory, proof = _fixture(tmp_path, '2025', 2828497462890)
    _annual_shape(directory, row, proof, labels=('2025', '2025'))
    _set_form(directory, row, proof, ('Mẫu số B 02 - DN/HN', 'Mẫu số B 02 - DN/HN'))
    result = _pure(row, context, directory)
    assert result['state'] == 'ADMITTED' and 'literal_normalizations' not in result['evidence_classification'], result


@pytest.mark.parametrize('form', ['Mẫu số B 03 – DN/HN', 'Mẫu số B 02 – DN', 'Mẫu số B 02 – TCTD/HN',
                                  'Mẫu số B 02b – DN/HN', 'Mẫu số B 02 ~ DN/HN', 'Mẫu số B 02 − DN/HN',
                                  'Mẫu số B 02 DN/HN'])
def test_wrong_form_letters_codes_or_other_marks_stay_blocked(tmp_path, form):
    row, context, directory, proof = _fixture(tmp_path, '2025', 2828497462890)
    _annual_shape(directory, row, proof, labels=('2025', '2025'))
    _set_form(directory, row, proof, (form, form))
    assert 'DUAL_READER_ACCOUNTING_FORM_OR_ROW_IDENTITY_UNSUPPORTED' in _pure(row, context, directory)['reason_codes']


def test_reader_form_literals_must_still_agree_exactly(tmp_path):
    row, context, directory, proof = _fixture(tmp_path, '2025', 2828497462890)
    _annual_shape(directory, row, proof, labels=('2025', '2025'))
    _set_form(directory, row, proof, ('Mẫu số B 02 – DN/HN', 'Mẫu số B 02 - DN/HN'))
    assert 'DUAL_READER_LITERAL_DISAGREEMENT' in _pure(row, context, directory)['reason_codes']


@pytest.mark.parametrize('periods', [(None, None), (_YEARLESS_CAPTION, _YEARLESS_CAPTION)])
def test_yearless_caption_resolved_period_is_reused_for_caption_bound_column(tmp_path, periods):
    row, context, directory, proof = _fixture(tmp_path, '2025', 123)
    _annual_shape(directory, row, proof, labels=('2025', '2025'), periods=periods)
    result = _pure(row, context, directory)
    assert result['state'] == 'ADMITTED', result


def test_explicit_contradictory_column_period_still_blocks_after_caption_resolution(tmp_path):
    row, context, directory, proof = _fixture(tmp_path, '2025', 123)
    _annual_shape(directory, row, proof, labels=('2025', '2025'), periods=('2024', '2024'))
    assert 'DUAL_READER_SEMANTIC_BINDING_MISMATCH' in _pure(row, context, directory)['reason_codes']


def test_printed_page_exact_trang_prefix_admits(tmp_path):
    row, context, directory, proof = _fixture(tmp_path)
    _change_reader(directory, row, proof, lambda raw: raw['input'].update(printed_page='Trang 1'))
    result = _pure(row, context, directory)
    assert result['state'] == 'ADMITTED', result
    assert result['evidence_classification']['literal_normalizations'][0]['rule'] == 'LEADING_TRANG_PAGE_PREFIX'


@pytest.mark.parametrize('literal', ['trang 1', 'Trang  1', 'Trang 01', 'Trang 2', 'Trang 1 ', 'Trang Trang 1'])
def test_printed_page_near_miss_still_refused(tmp_path, literal):
    row, context, directory, proof = _fixture(tmp_path)
    _change_reader(directory, row, proof, lambda raw: raw['input'].update(printed_page=literal))
    assert 'DUAL_READER_INPUT_BINDING_MISMATCH' in _pure(row, context, directory)['reason_codes']


@pytest.mark.parametrize('reader', [0, 1])
def test_form_circular_suffix_admits_and_preserves_raw(tmp_path, reader):
    row, context, directory, proof = _fixture(tmp_path)
    form = row['form_reference_literal']
    _change_reader(directory, row, proof, lambda raw: raw['table'].update(
        form_reference_literal=form + '\nThông tư số 43/2026/TT-BTC'), index=reader)
    result = _pure(row, context, directory)
    assert result['state'] == 'ADMITTED', result
    assert result['evidence_classification']['literal_normalizations'][0]['rule'] == 'TRAILING_CIRCULAR_REFERENCE_LINE'


def test_missing_scope_against_explicit_scope_remains_literal_disagreement(tmp_path):
    row, context, directory, proof = _fixture(tmp_path)
    _change_reader(directory, row, proof, lambda raw: raw['table'].update(scope_literal=None))
    assert 'DUAL_READER_LITERAL_DISAGREEMENT' in _pure(row, context, directory)['reason_codes']


def _replay_metadata(row):
    metadata = row['document_metadata']
    document = metadata['document']
    row['document_metadata'] = qualify_document_metadata({
        'issuer_identity': metadata['issuer_identity'], 'entity_type': metadata['entity_type'],
        'document': {**document, 'sha256': document['document_sha256']},
        'metadata': {**metadata['metadata_claims'], **metadata['optional_metadata_claims']}})


def _unit_gap_fixture(tmp_path, period='2026-H1', *, missing_units=True, image_only=False):
    row, context, directory, proof = _fixture(tmp_path, period, image_only=image_only)
    for index in (0, 1):
        _change_reader(directory, row, proof, lambda raw: raw['table'].update(
            currency_unit_literal='Đơn vị tính: Đồng Việt Nam'), index=index)
    context['document_pages'][1] = context['document_pages'][1].replace('Unit: VND', 'garbled')
    from official_financial_assurance_evidence import resolve_native_document_assurance
    row['assurance_evidence'] = resolve_native_document_assurance(
        row['document_sha256'], context['document_pages'])
    if missing_units:
        for name in ('currency', 'unit_scale'):
            row['document_metadata']['metadata_claims'].pop(name)
        _replay_metadata(row)
    return row, context, directory, proof


@pytest.mark.parametrize('period', ['2025-H1', '2026-H1'])
@pytest.mark.parametrize('missing_units', [True, False])
def test_identical_reader_unit_waives_common_metadata_text_gate_only_after_full_verification(
        tmp_path, period, missing_units):
    row, context, directory, _ = _unit_gap_fixture(tmp_path, period, missing_units=missing_units)
    before = deepcopy(row), deepcopy(context)
    metadata = row['document_metadata']
    if missing_units:
        assert metadata['qualification_status'] == 'DOCUMENT_METADATA_BLOCKED'
        assert set(metadata['blockers']) == {'CURRENCY_MISSING', 'UNIT_SCALE_MISSING'}
    else:
        assert metadata['qualification_status'] == 'DOCUMENT_METADATA_QUALIFIED'
    result = _pure(row, context, directory)
    assert result['state'] == 'ADMITTED', result
    assert row['source_unit_scale'] == row['unit_scale'] == 1
    assert result['admission_basis'] == result['evidence_tier'] == dual.EVIDENCE_TIER
    assert result['evidence_classification']['authority_effect'] == 'OFFLINE_RESEARCH_ONLY'
    assert result['evidence_classification']['pit_backtest_eligible'] is False
    effective = deepcopy(row)
    for name, value in (('currency', 'VND'), ('unit_scale', 1)):
        effective['document_metadata']['metadata_claims'][name] = {'value': value, 'evidence_span': {
            'citation_id': 'effective', 'document_sha256': row['document_sha256'],
            'source_page': 1, 'text': 'Đơn vị tính: Đồng Việt Nam'}}
    _replay_metadata(effective)
    assert result['metadata_evidence_id'] == effective['document_metadata']['evidence_envelope_id']
    if missing_units:
        assert result['metadata_evidence_id'] != metadata['evidence_envelope_id']
    assert (row, context) == before


@pytest.mark.parametrize('case', ['reader_disagreement', 'non_vnd', 'fact_page', 'span_page',
    'reader_page', 'document_sha', 'proof_reference', 'no_dual', 'no_ocr_dual',
    'missing_scope', 'missing_period', 'stale_id', 'forged_status',
    'assurance', 'rights', 'source', 'cutoff', 'knowledge_floor'])
def test_statement_unit_waiver_refused_without_all_other_proofs(tmp_path, monkeypatch, case):
    row, context, directory, proof = _unit_gap_fixture(tmp_path)
    if case == 'reader_disagreement':
        _change_reader(directory, row, proof, lambda raw: raw['table'].update(
            currency_unit_literal='Đơn vị tính: Đồng Việt Nam '))
    elif case == 'non_vnd':
        for index in (0, 1):
            _change_reader(directory, row, proof, lambda raw: raw['table'].update(
                currency_unit_literal='Đơn vị tính: USD'), index=index)
    elif case == 'fact_page':
        row['source_page'] = 2
    elif case == 'span_page':
        row['source_span']['source_page'] = 2
    elif case == 'reader_page':
        _change_reader(directory, row, proof, lambda raw: raw['input'].update(source_page=2))
    elif case == 'document_sha':
        row['document_sha256'] = '0' * 64
    elif case == 'proof_reference':
        row['dual_reader_transcription']['proof_sha256'] = '0' * 64
    elif case in ('no_dual', 'no_ocr_dual'):
        row.pop('dual_reader_transcription')
        if case == 'no_ocr_dual':
            context['ocr_layout_proof'] = _ocr_page_proof(monkeypatch, row)
    elif case in ('missing_scope', 'missing_period'):
        name = 'statement_scope' if case == 'missing_scope' else 'reporting_period'
        row['document_metadata']['metadata_claims'].pop(name)
        _replay_metadata(row)
    elif case == 'stale_id':
        row['document_metadata']['evidence_envelope_id'] = '0' * 64
    elif case == 'forged_status':
        row['document_metadata']['qualification_status'] = 'DOCUMENT_METADATA_QUALIFIED'
    elif case == 'assurance':
        row['assurance_evidence'] = None
    elif case == 'rights':
        context['source_record']['rights_status'] = 'UNKNOWN'
    elif case == 'source':
        context['source_record']['canonical_url'] = context['source_record']['final_url'] = 'https://invalid.example/test.pdf'
    elif case == 'cutoff':
        context['cutoff'] = '2026-11-24T09:02:00+00:00'
    elif case == 'knowledge_floor':
        row['knowledge_available_at'] = '2026-11-24T09:01:00+00:00'
    result = _pure(row, context, directory)
    assert result['state'] != 'ADMITTED', (case, result)
    if case in ('reader_disagreement', 'non_vnd', 'reader_page', 'document_sha',
                'proof_reference', 'rights', 'knowledge_floor'):
        assert any(reason.startswith('DUAL_READER_') for reason in result['reason_codes']), result
    if case in ('no_dual', 'no_ocr_dual', 'stale_id', 'forged_status', 'missing_scope', 'missing_period'):
        assert 'DOCUMENT_METADATA_NOT_QUALIFIED' in result['reason_codes'], result


@pytest.mark.parametrize('text', ['Unit: USD', 'Unit: million VND'])
@pytest.mark.parametrize('location', ['selected_page', 'outside_selected_ocr_page'])
def test_statement_unit_waiver_rejects_contrary_retained_declarations(tmp_path, monkeypatch, text, location):
    row, context, directory, _ = _unit_gap_fixture(tmp_path)
    if location == 'selected_page':
        context['document_pages'][1] += '\n' + text
    else:
        proof = _ocr_page_proof(monkeypatch, row)
        _seal_ocr_pages(row, proof, {9: text})
        context['ocr_layout_proof'] = proof
        assert 9 not in context['document_pages']
    result = _pure(row, context, directory)
    assert result['state'] == 'BLOCKED', result
    assert 'DUAL_READER_STATEMENT_UNIT_CONFLICT' in result['reason_codes'], result


def test_statement_unit_waiver_rejects_contrary_metadata_value(tmp_path):
    row, context, directory, _ = _unit_gap_fixture(tmp_path, missing_units=False)
    row['document_metadata']['metadata_claims']['unit_scale']['value'] = 1000000
    _replay_metadata(row)
    result = _pure(row, context, directory)
    assert result['state'] == 'BLOCKED', result
    assert 'DUAL_READER_STATEMENT_UNIT_CONFLICT' in result['reason_codes'], result


def _seal_ocr_pages(row, proof, pages):
    from stocklookup_core.evidence import official_ocr_layout_proof as ocr
    proof['pages'] = {str(number): {'tokens': [
        {'text': line, 'raw_token_order': index, 'tsv_hierarchy': {'line_num': index}}
        for index, line in enumerate(text.splitlines(), 1)]} for number, text in pages.items()}
    body = {key: value for key, value in proof.items() if key != 'proof_sha256'}
    proof['proof_sha256'] = _sha(ocr.canonical_json(body).encode('utf-8'))
    row['ocr_layout_proof']['proof_sha256'] = proof['proof_sha256']


@pytest.mark.parametrize('metric', ['revenue', 'attributable_net_income'])
@pytest.mark.parametrize('case', ['ready', 'cutoff', 'wrong_root', 'pdf_hash', 'row_value',
                                  'missing_operand', 'native_proof_hash'])
def test_dual_h1_engine_replays_zero_native_proof_only_with_registered_builder(tmp_path, monkeypatch, metric, case):
    from official_financial_pdf_page_evidence import build_artifact
    from stocklookup_core.evidence import official_document_qualification as owner
    from stocklookup_core.evidence import official_ocr_layout_proof as ocr
    from stocklookup_core.financial.financial_analysis_engine_v2 import official_h1_ttm_features
    from stocklookup_core.valuation import current_research_valuation_context as valuation

    rows, directories = [], []
    for period, value in [('2025', 100), ('2026-H1', 60), ('2025-H1', 40)]:
        row, context, directory, _ = _fixture(
            tmp_path, period, value, metric, native_text_override='unusable native text layer ' + period)
        proof = _ocr_page_proof(monkeypatch, row)
        _seal_ocr_pages(row, proof, context['document_pages'])
        source = context['source_record']
        native = build_artifact(document={**source, 'entity_type': 'corporate',
            'official_url': source['canonical_url'], 'retrieved_at': source['observed_at']},
            path=directory / 'fixture.pdf')
        assert not native['fact_candidates'] and not native['p3f13_panel_facts']
        proof['pages']['1']['native_failure_evidence'] = {
            'document_sha256': row['document_sha256'], 'candidate_count': 0,
            'trigger': 'EXPLICIT_OPT_IN_AFTER_NATIVE_ZERO_CANDIDATES',
            'native_artifact_identity': native['artifact_identity'],
            'native_page_text_sha256': {str(p['page_number']): owner._native_page_text_sha256(p['page_text'])
                                        for p in native['page_evidence']}}
        if case == 'native_proof_hash' and period == '2026-H1':
            proof['pages']['1']['native_failure_evidence']['native_artifact_identity'] = 'tampered'
        proof['proof_sha256'] = _sha(ocr.canonical_json(
            {k: v for k, v in proof.items() if k != 'proof_sha256'}).encode('utf8'))
        row['ocr_layout_proof']['proof_sha256'] = proof['proof_sha256']
        target = directory / row['ocr_layout_proof']['relative_path']
        target.parent.mkdir(exist_ok=True)
        target.write_bytes(_bytes(proof))
        rows.append(row)
        directories.append(directory)

    # Reproduce a fresh engine process, even if other tests imported the OCR runner.
    monkeypatch.setattr(owner, '_NATIVE_ARTIFACT_BUILDER', None)
    monkeypatch.setattr(owner, 'load_registry', lambda: context['registry'])
    controls = []
    for keep_ocr in (True, False):
        control = deepcopy(rows[0])
        control.pop('dual_reader_transcription')
        if not keep_ocr:
            control.pop('ocr_layout_proof')
        controls.append((control, owner.admit_retained_financial_fact(control, evidence_root=tmp_path)))
    if case == 'ready':
        # Same row, bytes and cutoff: only supplying the existing builder differs.
        assert owner.admit_retained_financial_fact(rows[0], evidence_root=tmp_path)['state'] == 'BLOCKED'
        assert owner.admit_retained_financial_fact(rows[0], evidence_root=tmp_path,
            native_artifact_builder=build_artifact)['state'] == 'ADMITTED'
    cutoff = '2026-11-24T09:02:00+00:00' if case == 'cutoff' else '2026-11-24T09:04:00+00:00'
    root = tmp_path / 'absent' if case == 'wrong_root' else tmp_path
    if case == 'pdf_hash':
        with (directories[1] / 'fixture.pdf').open('ab') as stream:
            stream.write(b'\n% tampered retained bytes\n')
    elif case == 'row_value':
        rows[1]['normalized_value'] += 1
    elif case == 'missing_operand':
        rows.pop(1)
    before = deepcopy(rows)
    fid = metric + '_ttm'
    # Core never imports the root builder: without the composition root's registration the
    # engine fails closed on the zero-native-candidate replay.
    unregistered = official_h1_ttm_features(ticker='PNJ', rows=rows, cutoff=cutoff, evidence_root=root)
    assert unregistered[fid]['fitness'] == 'BLOCKED_BY_EVIDENCE' and unregistered[fid]['value'] is None
    # The composition root (admission runner, Daily) registers the existing builder by importing
    # official_financial_ocr_table_evidence; reproduce exactly that registration.
    monkeypatch.setattr(owner, '_NATIVE_ARTIFACT_BUILDER', build_artifact)
    features = official_h1_ttm_features(ticker='PNJ', rows=rows, cutoff=cutoff, evidence_root=root)
    feature = features[fid]
    assert rows == before
    monkeypatch.setattr(owner, '_NATIVE_ARTIFACT_BUILDER', None)
    for control, original in controls:
        assert owner.admit_retained_financial_fact(control, evidence_root=tmp_path) == original
    selected = valuation._qualified_ttm(fid, {'features': features}, 'SYNTHETIC_DUAL_REPLAY')
    if case == 'ready':
        assert feature['fitness'] == 'READY' and feature['value'] == 120, feature
        assert selected['value'] == 120
        method = valuation._ttm_method(method_id='P/S_TTM' if metric == 'revenue' else 'P/E_TTM',
            metric=fid, ttm=selected, market_cap={'status': 'RESEARCH_USABLE', 'value': 1200,
                'currency': 'VND', 'scale': 'units'},
            share_class=valuation.share_basis_class({'research_proxy_eligible': True}),
            entity='corporate', earnings_state=None)
        assert method['value'] == 10, method
        assert method['status'] == 'RESEARCH_USABLE', method
    else:
        assert feature['fitness'] == 'BLOCKED_BY_EVIDENCE' and feature['value'] is None, feature
        assert selected is None


@pytest.mark.parametrize('period', ['2025-H1', '2026-H1'])
@pytest.mark.parametrize('contrary', [False, True])
def test_retained_loader_replays_dual_statement_unit_with_unreadable_ocr(tmp_path, monkeypatch, period, contrary):
    from stocklookup_core.evidence import official_ocr_layout_proof as ocr
    row, context, directory, _ = _unit_gap_fixture(tmp_path, period, image_only=True)
    proof = _ocr_page_proof(monkeypatch, row)
    # Register only this owned fixture; the loader and both verifiers run normally.
    monkeypatch.setitem(ocr.LAYOUT_PROOFS[row['document_sha256']], 'text_layer_verification', {
        'state': 'NONE_VERIFIED'})
    pages = {1: context['document_pages'][1]}
    if contrary:
        pages[9] = 'Unit: USD'  # retained proof page outside the loader's required set
    _seal_ocr_pages(row, proof, pages)
    target = directory / row['ocr_layout_proof']['relative_path']
    target.parent.mkdir(exist_ok=True)
    target.write_bytes(_bytes(proof))
    before = deepcopy(row)
    retained_paths = [directory / 'fixture.pdf', directory / 'official_document_acquisition_manifest.json',
                      target, *[path for path in (directory / dual.PROOF_DIR).iterdir() if path.is_file()]]
    retained_bytes = {path: path.read_bytes() for path in retained_paths}
    result = admit_retained_financial_fact(row, evidence_root=tmp_path, registry=context['registry'])
    if contrary:
        assert result['state'] == 'BLOCKED', result
        assert 'DUAL_READER_STATEMENT_UNIT_CONFLICT' in result['reason_codes'], result
    else:
        assert result['state'] == 'ADMITTED', result
        assert result['admission_basis'] == dual.EVIDENCE_TIER
        assert result['evidence_classification']['authority_effect'] == 'OFFLINE_RESEARCH_ONLY'
        assert result['evidence_classification']['pit_backtest_eligible'] is False
    assert row == before
    assert {path: path.read_bytes() for path in retained_paths} == retained_bytes


@pytest.mark.parametrize("label", ["06 tháng đầu năm 2026", "6 tháng đầu năm 2026"])
def test_h1_explicit_half_year_current_header_admits(tmp_path, label):
    row, context, directory, proof = _fixture(tmp_path, period="2026-H1")
    row["current_period_label"] = label
    def change(raw):
        raw["table"]["columns"][0].update(label_literal=label, reporting_period=label)
    for index in (0, 1):
        _change_reader(directory, row, proof, change, index=index)
    result = _pure(row, context, directory)
    assert result["state"] == "ADMITTED", result["reason_codes"]


@pytest.mark.parametrize("period,label", [
    ("2026-H1", "06 tháng đầu năm 2025"),   # another year's half-year header
    ("2026-H1", "06 tháng cuối năm 2026"),  # not the first half
    ("2026-H1", "9 tháng đầu năm 2026"),    # not a half year
    ("2025", "06 tháng đầu năm 2025"),      # annual fact never takes an H1 header
])
def test_h1_half_year_header_rule_is_exact(tmp_path, period, label):
    row, context, directory, proof = _fixture(tmp_path, period=period)
    row["current_period_label"] = label
    def change(raw):
        raw["table"]["columns"][0].update(label_literal=label, reporting_period=label)
    for index in (0, 1):
        _change_reader(directory, row, proof, change, index=index)
    result = _pure(row, context, directory)
    assert result["state"] != "ADMITTED"
    assert set(result["reason_codes"]) & {"DUAL_READER_CURRENT_COLUMN_NOT_EXPLICIT",
                                          "DUAL_READER_SEMANTIC_BINDING_MISMATCH"}, result["reason_codes"]


@pytest.mark.parametrize("literal,expected", [
    ("06 tháng đầu năm 2026", "2026-H1"), ("6 tháng đầu năm 2025", "2025-H1"),
    ("Cho kỳ kế toán 06 tháng đầu năm 2025", "2025-H1"),
    ("06 tháng cuối năm 2026", None), ("9 tháng đầu năm 2026", None),
    ("06 tháng đầu năm 2025 (Trình bày lại)", None), ("Cho kỳ 06 tháng đầu năm 2025", None), (None, None),
    ("For the 6-month period ended 30 June 2025", "2025-H1"), ("6-month period ended 30 June 2026", "2026-H1"),
    ("For the 6-month period ended 30 September 2025", None), ("For the 9-month period ended 30 June 2025", None),
    ("For the 6-month period ended 30 June 2025 (restated)", None),
])
def test_vn_first_half_period_literal_is_exact(literal, expected):
    assert dual.vn_first_half_period(literal) == expected


@pytest.mark.parametrize("metric,label,supported", [
    ("attributable_net_income", "Net profit after tax attributable to the parent entity", True),
    ("attributable_net_income", "Profit after tax attributable to Parent Company", True),
    ("attributable_net_income", "Net profit after tax attributable to non-controlling interests", False),
    ("attributable_net_income", "Net profit after tax attributable to the parent's non-controlling interests", False),
    ("net_income", "Net profit after tax attributable to the parent entity", False),
])
def test_english_parent_attributable_row_label_is_exact(metric, label, supported):
    from stocklookup_core.evidence.financial_row_identity import row_label_supports_metric
    assert row_label_supports_metric(metric, label) is supported


def test_h1_vietnamese_caption_and_header_bind_the_same_half_year(tmp_path):
    row, context, directory, proof = _fixture(tmp_path, period="2026-H1")
    label = "06 tháng đầu năm 2026"
    row["current_period_label"] = label
    def change(raw):
        raw["table"]["period_caption_literal"] = "Cho kỳ kế toán 06 tháng đầu năm 2026"
        raw["table"]["columns"][0].update(label_literal=label, reporting_period=label)
    for index in (0, 1):
        _change_reader(directory, row, proof, change, index=index)
    assert _pure(row, context, directory)["state"] == "ADMITTED"
    def contrary(raw):
        raw["table"]["period_caption_literal"] = "Cho kỳ kế toán 06 tháng đầu năm 2025"
    for index in (0, 1):
        _change_reader(directory, row, proof, contrary, index=index)
    assert "DUAL_READER_SEMANTIC_BINDING_MISMATCH" in _pure(row, context, directory)["reason_codes"]


@pytest.mark.parametrize("raw,sign,expected", [
    ("603.917.668.121", "parentheses", "(603.917.668.121)"),
    ("(603.917.668.121)", "parentheses", "(603.917.668.121)"),
    ("603.917.668.121", "unsigned", "603.917.668.121"),
    ("(603.917.668.121)", "unsigned", None),
    ("603.917.668.121)", "parentheses", None),
    ("-603.917.668.121", "minus", None),
    ("603.917.668.121", None, None),
    ("", "parentheses", None),
])
def test_signed_cell_literal_is_exact(raw, sign, expected):
    assert dual.signed_cell_literal(raw, sign) == expected


def test_parenthesized_loss_admits_only_when_both_readers_record_it(tmp_path):
    row, context, directory, proof = _fixture(tmp_path, metric="attributable_net_income")
    digits = row["raw_value_text"].strip("()")
    row.update(raw_value_text="(" + digits + ")", normalized_value=-abs(row["normalized_value"]))
    if "value" in row:
        row["value"] = -abs(row["value"])
    row["source_span"]["text"] = row["raw_row_label"] + " " + row["raw_value_text"]
    def loss(raw):
        raw["table"]["rows"][0]["cells"][0].update(raw_value_literal=digits, sign_literal="parentheses")
    for index in (0, 1):
        _change_reader(directory, row, proof, loss, index=index)
    result = _pure(row, context, directory)
    assert result["state"] == "ADMITTED", result["reason_codes"]
    def unsigned(raw):
        raw["table"]["rows"][0]["cells"][0].update(sign_literal="unsigned")
    _change_reader(directory, row, proof, unsigned, index=1)
    assert _pure(row, context, directory)["state"] != "ADMITTED"
