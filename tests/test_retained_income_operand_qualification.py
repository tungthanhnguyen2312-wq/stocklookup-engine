"""Synthetic admission controls and retained-token regressions for HOL-02C."""
import json
import copy
from pathlib import Path

import pytest

from stocklookup_core.evidence.financial_row_identity import (
    resolve_reported_row_identity as identity, row_label_supports_metric,
    LINE_CODE_IDENTITY_CONFLICTS,
)
from official_financial_filing_evidence import admit_official_financial_fact
from tests.test_official_financial_source_integrity import proved_fixture


def annual_income_page():
    from official_financial_ocr_table_evidence import _pages_by_statement_family
    path = Path(__file__).parent / 'fixtures/retained_interim_geometry/PNJ_FY25_income.json'
    return _pages_by_statement_family(json.loads(path.read_text(encoding='utf8')))['income_statement'][0]


def test_annual_locator_excludes_off_row_gutter_without_repairing_amount():
    from official_financial_structural_table import match_geometry_table_row
    from annual_financial_ocr_materialization import parse_accounting_integer
    page = annual_income_page()
    original = copy.deepcopy(page)
    row = match_geometry_table_row(page, line_code='60', target_period='2025')
    assert row['page'] == 10
    assert row['current_raw'] == '².8²8.497.46².890'
    assert 'I' not in row['row_object']['raw_label_fragments']
    with pytest.raises(ValueError, match='OCR_NUMERIC_AMBIGUITY'):
        parse_accounting_integer(row['current_raw'])
    assert page == original
    # A competing comparative token and a split current amount remain blocked.
    assert match_geometry_table_row(page, line_code='10', target_period='2025') is None
    assert match_geometry_table_row(page, line_code='61', target_period='2025') is None


@pytest.mark.parametrize('top,bottom,expected', [(1880, 1910, False), (1850, 1950, True), (1951, 1980, True)])
def test_label_side_requires_overlap_of_both_boxes(top, bottom, expected):
    from official_financial_structural_table import match_geometry_table_row
    page = annual_income_page()
    gutter = next(t for t in page['positioned_tokens'] if t['text'] == 'I' and t['x0'] < 100 and t['top'] == 1951)
    gutter.update(top=top, bottom=bottom)
    # Synthetic geometry perturbation: aligned competing labels must still block;
    # tall annotations cannot borrow a short code's entire height as row proof.
    found = match_geometry_table_row(page, line_code='60', target_period='2025')
    assert (found is not None) == expected


@pytest.mark.parametrize('tickers,expected', [([], ['HPG', 'PNJ', 'PVD']), (['VRE'], ['VRE'])])
def test_annual_document_list_registers_vre_without_widening_default_batch(monkeypatch, capsys, tickers, expected):
    from tools import run_retained_audited_annual_context as annual
    calls = []
    def run(**kwargs):
        calls.append(kwargs)
        return {'report': {}}
    monkeypatch.setattr(annual, 'run', run)
    monkeypatch.setattr('sys.argv', ['annual'] + (['--tickers'] + tickers if tickers else []))
    assert annual.main() == 0
    capsys.readouterr()
    kwargs = calls[0]
    assert [s['ticker'] for s in kwargs['document_specs']] == expected
    assert kwargs['reporting_period'] == '2025' and kwargs['allow_audited_annual_context']
    assert len(kwargs['document_specs']) <= 3
    assert sum(6 + len(s['pages']) for s in kwargs['document_specs']) <= 40
    if tickers:
        assert kwargs['document_specs'][0]['sha256'] == '85b250e9bd3b87aac9a1f650363f7063b2a830f6f4f1dda07eb6eecd09063a3e'
        assert kwargs['document_specs'][0]['pages'] == (7, 8, 9, 10, 11, 12)


@pytest.mark.parametrize('label', [
    'Lợi nhuận sau thuế của công ty mẹ',
    'Lợi nhuận sau thuế của cổ đông của công ty mẹ',
    'Loi nhuan sau thue cua cong tyme',
])
def test_tt43_parent_labels_pass_both_existing_owners(label, monkeypatch):
    from financial_statement_template_recognizer import GENERIC_METRIC_RULES
    # Entire document fixture is synthetic. Only its printed label differs.
    monkeypatch.setitem(GENERIC_METRIC_RULES['attributable_net_income'], 'source_label', label)
    row, context = proved_fixture(metric='attributable_net_income')
    row['line_code'] = '61'
    assert admit_official_financial_fact(row, **context)['state'] == 'ADMITTED'
    assert row_label_supports_metric('attributable_net_income', label)
    if 'tyme' not in label:
        assert identity('income_statement', '61', label)['blockers'] == []


@pytest.mark.parametrize('metric,code,label,reason', [
    ('net_income', '61', 'Loi nhuan sau thue', 'METRIC_LINE_CODE_IDENTITY_CONFLICT'),
    ('attributable_net_income', '60', 'Loi nhuan sau thue cua cong tyme', 'METRIC_LINE_CODE_IDENTITY_CONFLICT'),
    ('attributable_net_income', '61', 'Loi nhuan sau thue cua cong tyme va co dong khong kiem soat', 'METRIC_LITERAL_LABEL_NOT_SUPPORTED'),
    ('attributable_net_income', '61', 'Loi nhuan sau thue cua Ceng ty me', 'METRIC_LITERAL_LABEL_NOT_SUPPORTED'),
])
def test_admission_keeps_crossed_nci_and_damaged_letter_guards(metric, code, label, reason, monkeypatch):
    from financial_statement_template_recognizer import GENERIC_METRIC_RULES
    monkeypatch.setitem(GENERIC_METRIC_RULES[metric], 'source_label', label)
    row, context = proved_fixture(metric=metric)
    row['line_code'] = code
    result = admit_official_financial_fact(row, **context)
    assert result['state'] != 'ADMITTED'
    assert reason in result['reason_codes']
    assert LINE_CODE_IDENTITY_CONFLICTS == {('net_income','61'),('attributable_net_income','60')}


@pytest.mark.parametrize('code', ['24', '27'])
@pytest.mark.parametrize('label', ['Phần lãi hoặc lỗ trong công ty liên doanh, liên kết',
    'Share of profit of associates and joint ventures'])
def test_legacy_and_tt43_jv_share_codes_keep_literal_identity(code, label):
    row = identity('income_statement', code, label, form_reference='TT43/2026' if code == '27' else 'TT202/2014')
    assert row == dict(canonical_metric=None, accounting_identity='SHARE_OF_JOINT_VENTURE_ASSOCIATE_PROFIT', blockers=[])


@pytest.mark.parametrize('code,label', [('24','Chi phí lãi vay'), ('27','Chi phí lãi vay của công ty liên kết'),
    ('24','Phần lãi của công ty mẹ'), ('23','Phần lãi trong công ty liên kết')])
def test_interest_and_jv_labels_cannot_cross(code, label):
    assert identity('income_statement',code,label)['blockers']


def test_retained_hpg_annual_code23_is_interest_not_code24():
    from official_financial_ocr_table_evidence import _pages_by_statement_family
    from official_financial_structural_table import match_geometry_table_row
    fixture=Path(__file__).parent/'fixtures/retained_interim_geometry/HPG_FY25.json'
    mat=json.loads(fixture.read_text(encoding='utf8'))['statements']
    page=_pages_by_statement_family(mat)['income_statement'][0]
    row=match_geometry_table_row(page,line_code='23',target_period='2025')
    assert row['page']==10 and row['current_raw']=='3.114.855.868.974'
    found=identity('income_statement','23',row['line_text'])
    assert found['accounting_identity']=='REPORTED_BORROWING_COSTS' and not found['blockers']
    assert identity('income_statement','24',row['line_text'])['blockers']


def test_tt43_total_and_nci_conflicts_remain():
    label='Lợi nhuận sau thuế của công ty mẹ'
    assert 'TOTAL_PARENT_PROFIT_IDENTITY_CONFLICT' in identity('income_statement','60',label)['blockers']
    assert 'PARENT_NCI_PROFIT_IDENTITY_CONFLICT' in identity('income_statement','61',label+' và cổ đông không kiểm soát')['blockers']
    assert identity('income_statement','','Lợi nhuận sau thuế của công ty mẹ')['accounting_identity']=='PARENT_PROFIT_AFTER_TAX'


def test_annual_runner_never_backdates_knowledge_to_retention_time(monkeypatch, tmp_path):
    """PIT: without an explicit later floor, annual facts are known no earlier than qualification time."""
    from datetime import datetime, timezone
    from tools import run_reviewed_interim_canonical_ingress as runner
    record={'observed_at':'2026-09-29T11:31:14.408633Z','reporting_period':'2025'}
    monkeypatch.setattr(runner,'_record',lambda *a:record)
    monkeypatch.setattr(runner,'materialize_tsv_pages',lambda *a,**kw:{'pages':[]})
    monkeypatch.setattr(runner,'resolve_document_assurance_evidence',lambda *a:{'state':'BLOCKED'})
    monkeypatch.setattr(runner,'resolve_scoped_unit_evidence',lambda *a:{})
    monkeypatch.setattr(runner,'resolve_scoped_statement_scope_evidence',lambda *a:{})
    monkeypatch.setattr(runner,'qualify_table_facts',lambda *a,**kw:{'qualified_facts':[],'blocked_candidates':[]})
    start=datetime.now(timezone.utc)
    result=runner.run(landing_root=tmp_path,document_specs=[{'ticker':'PNJ','sha256':'a'*64,'pages':(7,)}],
        reporting_period='2025',allow_audited_annual_context=True)
    doc=result['report']['documents'][0]
    assert datetime.fromisoformat(doc['knowledge_available_at'].replace('Z','+00:00'))>=start
    assert doc['observed_at']==record['observed_at']


@pytest.mark.parametrize('reference,start,code,label,concept', [
    ('202/2014/TT-BTC', '2026-01-01', '23', 'Chi phí lãi vay', 'REPORTED_BORROWING_COSTS'),
    ('TT200/2014', None, '22', 'Chi phí tài chính', 'FINANCIAL_EXPENSE'),
    ('TT43/2026', '2025-01-01', '23', 'Chi phí tài chính', 'FINANCIAL_EXPENSE'),
    ('Kèm theo TT43/2026', None, '24', 'Trong đó: Chi phí đi vay', 'REPORTED_BORROWING_COSTS'),
    ('99/2025/TT-BTC', None, '22', 'Doanh thu hoạt động tài chính', 'FINANCIAL_INCOME'),
    ('', '2026-01-01', '24', 'Trong đó: Chi phí đi vay', 'REPORTED_BORROWING_COSTS'),
    ('', '2025-01-01', '24', 'Phần lãi công ty liên kết', 'SHARE_OF_JOINT_VENTURE_ASSOCIATE_PROFIT'),
])
def test_form_scoped_income_codes(reference, start, code, label, concept):
    row = identity('income_statement', code, label, form_reference=reference, fiscal_period_start=start)
    assert row['accounting_identity'] == concept and not row['blockers']


@pytest.mark.parametrize('reference,code,label', [
    ('TT43/2026','23','Chi phí lãi vay'), ('TT43/2026','24','Phần lãi công ty liên kết'),
    ('TT202/2014','24','Trong đó: Chi phí đi vay'), ('TT202/2014','27','Phần lãi công ty liên kết'),
    ('TT43/2026 TT202/2014','24','Trong đó: Chi phí đi vay'),
    ('TT999/2026','23','Chi phí tài chính'),
])
def test_form_and_final_literal_guards_cannot_cross(reference, code, label):
    assert identity('income_statement', code, label, form_reference=reference)['blockers']


def test_other_matters_never_establishes_current_document_period():
    from official_financial_period_identity import recognize_statement_period as period
    assert period('BÁO CÁO SOÁT XÉT\nVén đề khác\nGiữa niên độ cho kỳ 6 tháng kết thúc ngày 30 tháng 6 năm 2024')['period'] is None
    text = 'Cho nam tai chinh két thúc ngay 31 thang 12 nam 2025'
    assert period(text)['period'] == '2025'
    assert period(text)['evidence'] == text[4:]
    assert period(text.replace('2025','²0²5'))['period'] is None


def test_exact_legal_name_requires_registered_hash_bound_ocr_proof():
    from stocklookup_core.evidence import official_ocr_layout_proof as lp
    from tests.test_official_ocr_layout_proof import make_proof, SHA
    proof = make_proof()
    row = dict(ticker='HPG', document_sha256=SHA, ocr_layout_proof=lp.proof_reference(proof))
    assert lp.retained_issuer_name_matches(row, proof, 'CÔNG TY CỔ PHẦN TẬP ĐOÀN HÒA PHÁT')
    assert not lp.retained_issuer_name_matches(row, proof, 'CONG TY CO PHAN TAP DOAN H0A PHAT')
    assert not lp.retained_issuer_name_matches(dict(row, ticker='PNJ'), proof, 'CONG TY CO PHAN TAP DOAN HOA PHAT')
    proof['pages']['12']['tokens'][0]['text'] = 'changed'
    assert not lp.retained_issuer_name_matches(row, proof, 'CONG TY CO PHAN TAP DOAN HOA PHAT')


def test_hol11_retained_pnj_year_headers_are_bound_without_waiving_row_checks():
    from stocklookup_core.evidence import official_ocr_layout_proof as lp
    from official_financial_value_evidence import parse_accounting_integer
    page = annual_income_page()
    from official_financial_structural_table import match_geometry_table_row
    found = match_geometry_table_row(page, line_code='60', target_period='2025')
    row = found['row_object']
    identities = row['column_bands']['header_evidence']['period_identities']
    assert identities['current']['raw_text'] == '2025'
    assert identities['current']['source_token_orders'] == [52]
    assert identities['comparative']['source_token_orders'] == [53]
    from tests.test_official_ocr_layout_proof import make_proof
    proof = make_proof(page['positioned_tokens'])
    proof['document_sha256'] = page['document_sha256']
    proof['pages']['10'] = proof['pages'].pop('12')
    reasons = lp.verify_row(row, proof, metric='net_income', source_page=10,
        line_code='60', raw_value=found['current_raw'], value=2828497462890,
        unit_scale=1, parse_amount=parse_accounting_integer)
    assert 'CURRENT_PERIOD_HEADER_NOT_REGISTERED' not in reasons
    assert 'CURRENT_PERIOD_HEADER_NOT_IN_PROOF' not in reasons
    # PNJ prints the line code on the first baseline of a wrapped record.
    # Header provenance must not waive the existing physical-row check.
    assert 'LINE_CODE_NOT_ON_VALUE_ROW' in reasons
    assert match_geometry_table_row(page, line_code='10', target_period='2025') is None
    assert match_geometry_table_row(page, line_code='61', target_period='2025') is None
