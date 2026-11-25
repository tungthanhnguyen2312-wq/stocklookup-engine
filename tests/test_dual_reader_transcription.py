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


def _pdf(text):
    # Owned, single-page ASCII PDF; the accounting value is deliberately absent
    # from its text layer. It is supplied only by the separately retained image readings.
    lines = [line.replace('\\', '\\\\').replace('(', '\\(').replace(')', '\\)') for line in text.splitlines()]
    stream = ('BT /F1 10 Tf 40 760 Td ' + ' 0 -14 Td '.join('(' + line + ') Tj' for line in lines) + ' ET').encode('ascii')
    objects = [b'<< /Type /Catalog /Pages 2 0 R >>', b'<< /Type /Pages /Kids [3 0 R] /Count 1 >>',
        b'<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>',
        b'<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>',
        b'<< /Length ' + str(len(stream)).encode() + b' >>\nstream\n' + stream + b'\nendstream']
    output = b'%PDF-1.4\n'; offsets = []
    for n, obj in enumerate(objects, 1):
        offsets.append(len(output)); output += str(n).encode() + b' 0 obj\n' + obj + b'\nendobj\n'
    xref = len(output)
    output += b'xref\n0 6\n0000000000 65535 f \n' + b''.join(f'{n:010d} 00000 n \n'.encode() for n in offsets)
    return output + b'trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n' + str(xref).encode() + b'\n%%EOF\n'


def _fixture(tmp_path, period="2026-H1", value=123, metric="attributable_net_income"):
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
    payload = _pdf(native_text); sha = _sha(payload)
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


def test_identical_reader_unit_does_not_silently_waive_common_metadata_text_gate(tmp_path):
    row, context, directory, proof = _fixture(tmp_path)
    # The new lower-owner unit evidence is not yet wired into the common owner:
    # that file is outside CDX-17's lease. Keep the independent gate fail-closed.
    context['document_pages'] = {1: context['document_pages'][1].replace('Unit: VND', 'garbled')}
    assert 'RETAINED_UNIT_SCALE_NOT_EXPLICIT' in _pure(row, context, directory)['reason_codes']
