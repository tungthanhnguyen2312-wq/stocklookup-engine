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
