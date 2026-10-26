"""Real SSI/POW scan replay and fail-closed transport/authority regressions."""
import copy
import hashlib
import io
import json
from datetime import datetime, timedelta

import pytest
from pypdf import PdfWriter

from stocklookup_core.evidence import official_document_acquisition as intake
from stocklookup_core.evidence import official_corporate_action_ledger as ledger
from tools import run_official_ca_hose_ex_date_qualification as old
from tools import run_official_ssi_pow_ca_qualification as run

@pytest.fixture(scope='module')
def artifact():
    return run.build_artifact()


def observation(artifact, news_id, event):
    doc=run.all_records()[news_id]['document_id']
    return next(o for o in artifact['observations'] if o['document_id']==doc and o['event_type']==event)


def test_exact_three_pow_terms_and_distinct_ssi_legs(artifact):
    rights=observation(artifact,'2422161','rights_issue')
    assert (rights['ex_date'],rights['record_date'],rights['rights_ratio'],rights['subscription_price']) == (
        '2025-12-10','2025-12-11',.12,10000)
    assert observation(artifact,'2422161','stock_dividend')['stock_ratio']==.04
    assert observation(artifact,'2422161','bonus_shares')['stock_ratio']==.15
    assert observation(artifact,'2485374','cash_dividend')['cash_amount_per_share']==1000
    assert observation(artifact,'2485374','bonus_shares')['stock_ratio']==.2


def test_ssi_planned_distributed_fraction_and_after_only_treasury(artifact):
    report=observation(artifact,'2492611','bonus_shares')
    listing=observation(artifact,'2497826','bonus_shares')
    assert report['shares_planned']-report['shares_issued']==report['fractional_shares_cancelled']==14969
    assert listing['shares_before']+report['shares_issued']==report['shares_after']==listing['shares_after']==3003293801
    assert report['treasury_shares_after']==1991468
    assert report['shares_after']-report['treasury_shares_after']==3001302333
    assert report['treasury_shares_before'] is None
    assert report['issuance_completion_date']=='2026-08-18'
    assert listing['listing_effective_date']=='2026-09-18'
    assert observation(artifact,'2499239','bonus_shares')['trading_date']=='2026-10-01'


def test_pow_component_counts_remain_separate_from_combined_listing(artifact):
    a=observation(artifact,'2425221','stock_dividend')
    b=observation(artifact,'2425221','bonus_shares')
    anchor=observation(artifact,'2430881',None)
    assert a['shares_issued']==93672392 and b['shares_issued']==351277104
    assert a['shares_issued']+b['shares_issued']==a['combined_shares_issued']==anchor['shares_issued']==444949496
    assert a['shares_before']+a['combined_shares_issued']==a['shares_after']==2786821096
    assert a['shares_outstanding_before']==2341871600 and a['treasury_shares_before']==0
    assert a['shares_outstanding_after']==2786821096 and a['treasury_shares_after']==0
    assert a['fractional_shares_cancelled'] is None and b['fractional_shares_cancelled'] is None
    assert artifact['aggregate_fraction_citation']['printed']=='6.108'
    for event in ('stock_dividend','bonus_shares'):
        entry=next(e for e in artifact['ledger']['entries'] if e['ticker']=='POW' and e['event_type']==event)
        assert entry['qualification_state']=='qualified' and entry['lifecycle_state']=='executed'
        assert entry['composite_execution_anchor']['document_id']==anchor['document_id']
        assert anchor['document_id'] in entry['source_document_ids']
        assert entry['shares_issued'] != anchor['shares_issued']


def test_pow_rights_listing_continuity_and_future_restriction(artifact):
    result=observation(artifact,'2443111','rights_issue')
    notice=observation(artifact,'2444347','rights_issue')
    anchor=observation(artifact,'2430881',None)
    assert anchor['shares_after']==result['shares_before']==2786821096
    assert result['shares_before']+result['shares_issued']==result['shares_after']==3067845688
    assert notice['unrestricted_shares']+notice['restricted_shares']==result['shares_issued']==281024592
    assert notice['unrestricted_trading_date']=='2026-03-26'
    assert notice['restricted_trading_date']=='2027-01-28'
    assert datetime.fromisoformat(notice['observed_at'].replace('Z','+00:00')).date().isoformat()<notice['restricted_trading_date']
    assert notice['trading_date'] is None  # No single date for the entire issuance.
    assert result['listing_effective_date']=='2026-03-11'


def test_complete_ssi_original_and_corrected_notice_identity(artifact):
    r=run.records()['2492611']
    assert r['document_completeness']['pdf_pages']==5 and r['content_length']==1951939
    assert r['sha256']=='221c1507f533bdb7b8565ed905d9b9482355eb4bb2bf80ba71397ade5a3259be'
    assert r['sha256'] != next(x for x in run.REQUESTS if x['hose_news_id']=='2492611')['hub_partial_sha256']
    correction=artifact['source_identity_corrections']['2499239']
    assert correction=={'printed_notice':'1935/TB-SGDHCM','rejected_lead_label':'457/TB-SGDHCM'}
    record=run.records()['2499239']
    pages=run.load_pages(json.loads(run.SIDECAR.read_bytes()),record,'2499239')
    assert any(old._token_on_page('1935',p['text']) for p in pages)


def test_every_field_has_original_page_token_entity_unit_and_hash(artifact):
    records={r['document_id']:r for r in run.all_records().values()}
    for obs in artifact['observations']:
        record=records[obs['document_id']]
        assert obs['published_at'] is None
        for c in obs['citations']:
            assert c['page']>0 and c['excerpt'] and c['ocr_citation_id']
            assert c['source_url']==record['canonical_url'] and c['original_sha256']==record['sha256']
            assert c['entity']==obs['ticker'] and c['unit']


def test_all_price_chains_refuse_mixed_unsupported_legs(artifact):
    cohort=artifact['factor_chain_cohort']
    assert cohort['qualified_count']==0
    for event in cohort['events']:
        chain=event['factor_chain']
        assert chain['status']!='QUALIFIED'
        if event['event_type']=='rights_issue':
            assert event['classification']=='FACTOR_NOT_APPLICABLE'
            assert 'UNSUPPORTED_FACTOR_TYPE' in chain['reason_codes']
        elif event['ticker']=='POW':
            assert 'same_ex_date_leg_without_adjustment_policy:rights_issue' in chain['reason_codes']
        else:
            assert 'same_ex_date_leg_without_adjustment_policy:cash_dividend' in chain['reason_codes']
    assert artifact['authority_boundary']['historical_pit_eligible'] is False
    for result in artifact['common_outstanding_continuity_gate'].values():
        assert result['current_shares']['qualified'] is False
        assert result['market_value_ready'] is False


def test_receipt_cutoff_uses_latest_required_original_including_composite_anchor(artifact):
    records={r['document_id']:r for r in run.all_records().values()}
    resolve=old.resolve_knowledge(records)
    for entry in artifact['ledger']['entries']:
        cutoff,reasons=resolve(entry)
        expected=max(records[d]['observed_at'] for d in entry['source_document_ids'])
        assert datetime.fromisoformat(cutoff.replace('Z','+00:00'))==datetime.fromisoformat(expected.replace('Z','+00:00'))
        assert 'FROM_FIRST_OBSERVED_FORWARD_ONLY' in reasons
        future=copy.deepcopy(records)
        for r in future.values():
            r['published_at']='2025-01-01'
            r['temporal_retention']['http_last_modified']='Mon, 01 Jan 2024 00:00:00 GMT'
            r['postedDate']='2025-01-01'
        assert old.resolve_knowledge(future)(entry)==(cutoff,reasons)
        before=(datetime.fromisoformat(cutoff.replace('Z','+00:00'))-timedelta(microseconds=1)).isoformat()
        import price_basis_feature_fitness as fitness
        event=next(e for e in artifact['factor_chain_cohort']['events'] if e['event_id']==entry['event_id'])
        context=fitness.price_series_context(ticker=entry['ticker'],provider='HOSE',source_identity='hose:tradingresult',
            session_start='2025-12-01',session_end='2026-09-04',observed_basis=fitness.POINT_IN_TIME_ADJUSTED,
            basis_provenance=['retained official scans'],factor_chain=event['factor_chain'])
        verdict=fitness.evaluate_feature_fitness(feature=fitness.PIT_BACKTEST,current_context=context,decision_as_of=before)
        assert verdict['state']=='POINT_IN_TIME_SEMANTICS_UNQUALIFIED'
        assert verdict['reason_codes']==['PIT_QUALIFIED_FACTOR_CHAIN_REQUIRED']
        at_receipt=fitness.evaluate_feature_fitness(feature=fitness.PIT_BACKTEST,current_context=context,decision_as_of=cutoff)
        assert at_receipt['reason_codes']==['PIT_QUALIFIED_FACTOR_CHAIN_REQUIRED']


@pytest.mark.parametrize('mutation',['wrong_ticker','wrong_total','not_executed','wrong_type','ambiguous','missing_companion','unverified_anchor','unverified_report','fractional_total'])
def test_composite_anchor_refuses_unsupported_links(artifact,mutation):
    report=copy.deepcopy(observation(artifact,'2425221','stock_dividend'))
    anchor=copy.deepcopy(observation(artifact,'2430881',None))
    candidates=[anchor]
    if mutation=='wrong_ticker':anchor['ticker']='SSI'
    if mutation=='wrong_total':anchor['shares_issued']+=1
    if mutation=='not_executed':anchor['lifecycle_state']='announced'
    if mutation=='wrong_type':anchor['event_type']='stock_dividend'
    if mutation=='missing_companion':report.pop('co_issued_shares')
    if mutation=='unverified_anchor':anchor['source_authority']='unverified'
    if mutation=='unverified_report':report['source_authority']='unverified'
    if mutation=='fractional_total':report['combined_shares_issued']+=.5
    if mutation=='ambiguous':candidates.append(anchor|{'observation_id':'another-observation'})
    assert ledger._composite_execution_anchor([report],candidates) is None


@pytest.mark.parametrize('mutation',['text','source_hash','row_hash','extra_profile','profile_psm'])
def test_sidecar_integrity_and_bounded_profile_scope(mutation):
    sidecar=json.loads(run.SIDECAR.read_bytes());r=run.records()['2492611']
    profiles=sidecar['documents'][r['document_id']]
    if mutation=='text':profiles['vie']['pages'][0]['text']+=' fabricated'
    if mutation=='source_hash':profiles['vie']['document_sha256']='f'*64
    if mutation=='row_hash':profiles['vie']['pages'][0]['document_sha256']='f'*64
    if mutation=='extra_profile':profiles['unreviewed']=profiles['vie']
    if mutation=='profile_psm':profiles['vie']['pages'][0]['ocr_psm']=13
    with pytest.raises(ValueError):run.load_pages(sidecar,r,'2492611')


def test_ocr_superscript_not_silently_repaired():
    sidecar=json.loads(run.SIDECAR.read_bytes());record=run.all_records()['2485374']
    base=old.load_ocr_pages(sidecar,record)
    changed=copy.deepcopy(old.REVIEWS['2485374'][1])
    changed['fields']['shares_planned']=old._field(1,'500.219.550','planned')
    with pytest.raises(ValueError,match='token_absent'):
        old.reviewed_scan_observation(old._document(record,record['document_class']),changed,base)
    assert any(o['shares_planned']==500219550 for o in run.build_observations(sidecar) if o['ticker']=='SSI')


def test_entire_predecessor_ledger_and_factor_cohort_replay_exactly():
    frozen=json.loads(old.OUTPUT.read_bytes())
    observations=old.build_observations(old.load_sidecar())
    replay=old.build_ledger(observations)
    cohort=old.build_factor_chain_cohort(replay,knowledge_cutoff_resolver=old.knowledge_resolver())
    assert observations==frozen['observations']
    assert replay==frozen['ledger']
    assert cohort==frozen['factor_chain_cohort']


def test_partial_ssi_metadata_is_not_complete(monkeypatch):
    records=copy.deepcopy(run.records());records['2492611']['document_completeness']['pdf_pages']=1
    monkeypatch.setattr(run,'records',lambda:records)
    with pytest.raises(ValueError,match='page_count'):run.build_artifact()


def pdf_bytes():
    writer=PdfWriter();writer.add_blank_page(width=72,height=72);out=io.BytesIO();writer.write(out)
    return out.getvalue()


@pytest.mark.parametrize('status,headers,damage,reason',[
    (206,{},False,'partial_document_response'),(200,{'Content-Range':'bytes 0-100/200'},False,'partial_document_response'),
    (200,{'Content-Length':'1'},False,'content_length_mismatch'),
    (200,{'Content-Encoding':'gzip'},False,'encoded_length_unverified'),
    (200,{},True,'final_eof_missing')])
def test_complete_pdf_proof_refuses_partial_or_unverifiable_transport(tmp_path,status,headers,damage,reason):
    p=tmp_path/'scan.pdf';data=pdf_bytes();p.write_bytes(data[:-6] if damage else data)
    with pytest.raises(ValueError,match=reason):intake.complete_pdf_proof(p,status,headers)


def test_complete_pdf_proof_checks_all_pages_not_just_eof(tmp_path):
    p=tmp_path/'scan.pdf';p.write_bytes(b'%PDF-1.4\nnot a PDF object structure\n%%EOF')
    with pytest.raises(ValueError,match='structure_incomplete'):intake.complete_pdf_proof(p,200,{})


def test_strict_acquisition_cache_verifies_proof_and_preserves_receipt(tmp_path):
    data=pdf_bytes();spec=run.acquisition_specs()[0]
    calls=[]
    def fetch(*args,**kwargs):
        calls.append(1);return 200,{'Content-Type':'application/pdf','Content-Length':str(len(data))},data
    first=intake.acquire([spec],tmp_path,fetcher=fetch,max_attempts=1)
    assert first['outcomes'][0]['state']=='retained'
    manifest=tmp_path/intake.MANIFEST;original=manifest.read_bytes()
    assert intake.acquire([spec],tmp_path,fetcher=fetch,max_attempts=1)['outcomes'][0]['state']=='cached_valid'
    assert len(calls)==1 and manifest.read_bytes()==original
    tampered=json.loads(original);tampered['records'][0]['document_completeness']['pdf_pages']=99
    manifest.write_text(json.dumps(tampered),encoding='utf8');bad=manifest.read_bytes()
    outcome=intake.acquire([spec],tmp_path,fetcher=fetch,max_attempts=1)['outcomes'][0]
    assert outcome['state']=='document_completeness_metadata_conflict'
    assert len(calls)==2 and manifest.read_bytes()==bad


@pytest.mark.retained_evidence(*[(run.RETENTION/run.records()[n]["relative_path"]).relative_to(run.ROOT).as_posix() for n in sorted(run.records())])
def test_all_eight_new_originals_rehash_and_replay_complete_document_proof():
    verified=run.verify_originals()
    assert len(verified)==8
    assert all(r['authority_effect']=='NONE_TRANSPORT_AND_STRUCTURE_ONLY' for r in verified)


def test_offline_default_preserves_manifests_sidecars_prior_artifact_and_is_deterministic(tmp_path,monkeypatch):
    monkeypatch.setattr(run,'OUTPUT',tmp_path/'qualification.json')
    monkeypatch.setattr(run,'ROOT',tmp_path)
    monkeypatch.setattr(run,'acquire',lambda *a,**k:pytest.fail('offline replay attempted network acquisition'))
    before={n:r['sha256'] for n,r in run.records().items()}
    manifests=(run.MANIFEST.read_bytes(),run.SIDECAR.read_bytes(),old.OUTPUT.read_bytes())
    # Raw-file verification itself is covered in the retained-evidence tier.
    monkeypatch.setattr(run,'verify_originals',lambda:None)
    assert run.main([])==0
    first=run.OUTPUT.read_bytes()
    assert run.main([])==0 and run.OUTPUT.read_bytes()==first
    assert before=={n:r['sha256'] for n,r in run.records().items()}
    assert manifests==(run.MANIFEST.read_bytes(),run.SIDECAR.read_bytes(),old.OUTPUT.read_bytes())


@pytest.mark.parametrize('field,value',[('ticker','HPG'),('canonical_url','https://candidate.example/scan.pdf'),
    ('document_class','agm_resolution'),('source_authority','candidate'),('published_at','2025-12-01')])
def test_original_source_identity_cannot_be_relabelled(monkeypatch,field,value):
    records=copy.deepcopy(run.records());records['2492611'][field]=value
    monkeypatch.setattr(run,'records',lambda:records)
    with pytest.raises(ValueError,match='original_identity_mismatch'):run.build_artifact()
