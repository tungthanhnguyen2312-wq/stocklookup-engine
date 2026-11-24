"""Synthetic admission controls and retained-token regressions for HOL-02C."""
import json
from pathlib import Path

import pytest

from stocklookup_core.evidence.financial_row_identity import (
    resolve_reported_row_identity as identity, row_label_supports_metric,
    LINE_CODE_IDENTITY_CONFLICTS,
)
from official_financial_filing_evidence import admit_official_financial_fact
from tests.test_official_financial_source_integrity import proved_fixture


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
    row = identity('income_statement', code, label)
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
