"""Finite SSI/POW continuation of PR192; receipt-forward evidence, no production promotion."""
from __future__ import annotations
import argparse
import hashlib
import json
import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from stocklookup_core.evidence.official_document_acquisition import acquire, complete_pdf_proof
from tools import run_official_ca_hose_ex_date_qualification as predecessor
EVIDENCE = ROOT / "operations-review/official-ssi-pow-ca-evidence-qualification-v1-20261026"
RETENTION = EVIDENCE / "official_document_retention"
MANIFEST = RETENTION / "official_document_acquisition_manifest.json"
SIDECAR = EVIDENCE / "derived/ssi_pow_scan_ocr_sidecar.json"
OUTPUT = EVIDENCE / "official_ssi_pow_ca_qualification.json"
REQUESTS = json.loads(r'''[{"ticker":"POW","hose_news_id":"2422161","document_class":"ex_right_notice","canonical_url":"https://staticfile.hsx.vn/Uploads/UploadDocuments/2422161/20251205%20-%20POW%20-%20TB%20ngay%20dkcc%20de%20thuc%20hien%20quyen.pdf","hub_complete_sha256":"22c9abea2fdfdfb34ffc595ebf628a2d2ab48ad0f45b6734ef592b646193a5d4","hub_partial_sha256":null},{"ticker":"POW","hose_news_id":"2425695","document_class":"corporate_action_notice","canonical_url":"https://staticfile.hsx.vn/Uploads/UploadDocuments/2425695/20251223%20-%20POW%20-%20CV%20cua%20UBCKNN%20Vv%20Bao%20cao%20ket%20qua%20phat%20hanh%20cua%20POW.pdf","hub_complete_sha256":"cb47737e190fd1017dc91af25fb94e6d7951a10787d8377ad01a508973167761","hub_partial_sha256":null},{"ticker":"POW","hose_news_id":"2443111","document_class":"listing_change_notice","canonical_url":"https://staticfile.hsx.vn/Uploads/UploadDocuments/2443111/20260309%20-%20POW%20-%20QD%20226%20vv%20thay%20doi%20dang%20ky%20niem%20yet.pdf","hub_complete_sha256":"4e292966d2e9f791c13ecfd6e7e37a166656b84a4763d0b741c58b5a4bcbe31c","hub_partial_sha256":null},{"ticker":"POW","hose_news_id":"2444347","document_class":"listing_change_notice","canonical_url":"https://staticfile.hsx.vn/Uploads/UploadDocuments/2444347/20260313%20-%20POW%20-%20TB%20708%20GD%20CK%20thay%20doi%20DKNY.pdf","hub_complete_sha256":"d397e8e440711fecf1e48b0f02adf8e6d46b6d3ee5688eaa679868bf04d0dae1","hub_partial_sha256":null},{"ticker":"SSI","hose_news_id":"2492611","document_class":"corporate_action_notice","canonical_url":"https://staticfile.hsx.vn/Uploads/UploadDocuments/2492611/20260827%20-%20SSI%20-%20NQ%20HDQT%20thong%20qua%20ket%20qua%20phat%20hanh%20co%20phieu%20tang%20VCP%20tu%20NVCSH_signed.pdf","hub_complete_sha256":null,"hub_partial_sha256":"d2f99e40d86d9243cdb39014952e368df873975e5ad14296da25bf4858a00051"},{"ticker":"SSI","hose_news_id":"2497826","document_class":"listing_change_notice","canonical_url":"https://staticfile.hsx.vn/Uploads/UploadDocuments/2497826/20260916%20-%20SSI%20-%20QD%20ve%20viec%20thay%20doi%20DKNY.pdf","hub_complete_sha256":"6e156b76ec7e513a43a23e7d586c11bbe5798ca9c5e5bdcbbedfaf21dd9a0ea9","hub_partial_sha256":null},{"ticker":"SSI","hose_news_id":"2499239","document_class":"listing_change_notice","canonical_url":"https://staticfile.hsx.vn/Uploads/UploadDocuments/2499239/20260923%20-%20SSI%20-%20TB%20GD%20CK%20thay%20doi%20DK%20NY.pdf","hub_complete_sha256":"4b12bb8d3c549661d0bd1fb9c861ba956f48d6846ddafb492a617a995d9fcb00","hub_partial_sha256":null}]''')
REQUESTS.append({"ticker":"POW", "hose_news_id":"2425221", "document_class":"corporate_action_notice",
    "canonical_url":"https://staticfile.hsx.vn/Uploads/UploadDocuments/2425221/20251219%20-%20POW%20-%20Bao%20cao%20ket%20qua%20dot%20phat%20hanh.pdf",
    "hub_complete_sha256":"8609d428fa5bcebf55d5ab70be558835f985c1416355de748cfe3944d0dd575a", "hub_partial_sha256":None})

EXPECTED_PAGES = {"2422161":3,"2425695":2,"2443111":2,"2444347":1,"2492611":5,"2497826":2,"2499239":1,"2425221":3}

def acquisition_specs():
    return [{k:r[k] for k in ("ticker","document_class","canonical_url")} | {
        "reporting_period":"2025" if r["ticker"]=="POW" and r["hose_news_id"] in {"2422161","2425695","2425221"} else "2026",
        "source_id":"hose","source_authority":"exchange","require_complete_pdf":True,
        "discovery_provenance":"grokbot_issue_53_locator:hose_news_id="+r["hose_news_id"]}
        for r in REQUESTS]
def records():
    return {r["discovery_provenance"].rsplit("=",1)[1]:r for r in json.loads(MANIFEST.read_bytes())["records"]}
# Every field below was read on rendered original pages, then independently
# corroborated by a finite, byte-bound OCR profile. Tokens are never repaired.
def review(event, phrase, **fields):
    return {"event_type": event, "event_type_printed": phrase,
            "fields": {k: predecessor._field(page, token, k) for k,(page,token) in fields.items()}}

REVIEWS = {
 "2422161": [
    review("rights_issue", "quyền mua", ex_date=(1,"10/12/2025"), record_date=(1,"11/12/2025"),
           rights_ratio=(1,"100:12"), subscription_price=(1,"10.000"), shares_planned=(1,"281.024.592")),
    review("stock_dividend", "trả cổ tức", ex_date=(1,"10/12/2025"), record_date=(1,"11/12/2025"),
           stock_ratio=(2,"100:4"), shares_planned=(2,"93.674.864")),
    review("bonus_shares", "tăng vốn cổ phần", ex_date=(1,"10/12/2025"), record_date=(1,"11/12/2025"),
           stock_ratio=(3,"100:15"), shares_planned=(3,"351.280.740"))],
 "2425695": [review("stock_dividend", "để trả cổ tức", shares_issued=(2,"93.672.392")),
             review("bonus_shares", "nguồn vốn chủ sở hữu", shares_issued=(2,"351.277.104"))],
 "2425221": [review(event, "trả cổ tức" if event=="stock_dividend" else "nguồn vốn chủ sở hữu",
    shares_before=(2,"2.341.871.600"), shares_outstanding_before=(2,"2.341.871.600"),
    treasury_shares_before=(2,"0"), shares_planned=(2,planned), stock_ratio=(page,ratio),
    shares_issued=(3,issued), co_issued_shares=(3,other), combined_shares_issued=(3,"444.949.496"),
    shares_after=(3,"2.786.821.096"), shares_outstanding_after=(3,"2.786.821.096"),
    treasury_shares_after=(3,"0"), issuance_completion_date=(3,"11/12/2025"))
    for event,ratio,page,planned,issued,other in [
      ("stock_dividend","100:4",2,"93.674.864","93.672.392","351.277.104"),
      ("bonus_shares","100:15",3,"351.280.740","351.277.104","93.672.392")]],
 "2443111": [review("rights_issue", "bán thêm cổ phiếu",
    shares_before=(2,"2.786.821.096"), shares_issued=(2,"281.024.592"), shares_after=(2,"3.067.845.688"),
    listing_effective_date=(2,"11/03/2026"))],
 "2444347": [review("rights_issue", "bán thêm cổ phiếu",
    shares_issued=(1,"281.024.592"), shares_after=(1,"3.067.845.688"), listing_effective_date=(1,"11/03/2026"),
    unrestricted_shares=(1,"276.606.691"), restricted_shares=(1,"4.417.901"),
    unrestricted_trading_date=(1,"26/03/2026"), restricted_trading_date=(1,"28/01/2027"))],
 "2492611": [review("bonus_shares", "owner's equity", shares_planned=(4,"500.219.550"),
    shares_issued=(4,"500.204.581"), fractional_shares_cancelled=(4,"14.969"),
    shares_after=(4,"3.003.293.801"), treasury_shares_after=(4,"1.991.468"),
    issuance_completion_date=(4,"18/8/2026"))],
 "2497826": [review("bonus_shares", "chủ sở hữu", shares_before=(1,"2.503.089.220"),
    shares_issued=(2,"500.204.581"), shares_after=(2,"3.003.293.801"), listing_effective_date=(2,"18/09/2026"))],
 "2499239": [review("bonus_shares", "tăng vốn cổ phần", shares_issued=(1,"500.204.581"),
    shares_after=(1,"3.003.293.801"), listing_effective_date=(1,"18/09/2026"), trading_date=(1,"01/10/2026"))],
}

# A closed profile set: additional whole-page reads are bounded acquisition
# derivatives, not arbitrary supplied text or silently normalized OCR tokens.
EXTRA_PROFILES = {"2444347": {"vie+eng_psm11":(1,"vie+eng",11)},
    "2499239": {"vie+eng_psm11":(1,"vie+eng",11), "eng_psm6":(1,"eng",6)},
    "2485374": {"vie+eng_psm11":(1,"vie+eng",11), "eng_psm6":(1,"eng",6)},
    "2497826": {"eng_psm6":(1,"eng",6)}, "2425221": {"eng_psm6":(2,"eng",6)}}

def all_records():
    old=predecessor._records()
    return {**records(), **{n:old[n] for n in ("2485374","2430881")}}

def load_pages(sidecar, record, news_id):
    profiles=sidecar["documents"][record["document_id"]]
    expected=set(predecessor.OCR_LANGUAGES) | set(EXTRA_PROFILES.get(news_id,{}))
    if set(profiles)!=expected:
        raise ValueError("unexpected_or_missing_ocr_profile")
    rows=[]
    for key in sorted(expected):
        result=profiles[key]
        if result['document_id']!=record['document_id'] or result['document_sha256']!=record['sha256']:
            raise ValueError("ocr_sidecar_bound_to_other_bytes")
        page_scope,language,psm=EXTRA_PROFILES.get(news_id,{}).get(key,(None,key,6))
        if result.get('ocr_language')!=language or any(
            p.get('ocr_psm')!=psm or (page_scope is not None and p['page']!=page_scope)
            for p in result['pages']):
            raise ValueError('ocr_profile_outside_reviewed_scope')
        for page in result['pages']:
            if page['document_id']!=record['document_id'] or page['document_sha256']!=record['sha256']:
                raise ValueError("ocr_row_bound_to_other_bytes")
            if hashlib.sha256(page['text'].encode()).hexdigest()!=page['text_sha256']:
                raise ValueError("ocr_text_hash_mismatch")
            predecessor.replay_ocr([{k:page[k] for k in predecessor._SIDECAR_ROW_FIELDS if k in page}])
            rows.append(dict(page))
    return rows

def materialize_ocr(prior_retention_root=None):
    from annual_financial_ocr_materialization import render_and_ocr
    sidecar=json.loads(SIDECAR.read_bytes()) if SIDECAR.exists() else {
        "schema_version":"1.0.0", "render_dpi":300, "psm":6,
        "languages":list(predecessor.OCR_LANGUAGES), "documents":{}}
    old_sidecar=predecessor.load_sidecar()
    for news_id,record in sorted(all_records().items()):
        if news_id=="2430881":
            continue  # Its immutable predecessor sidecar is reused directly.
        profiles=sidecar['documents'].setdefault(record['document_id'],{})
        root=Path(prior_retention_root) if news_id=="2485374" and prior_retention_root else RETENTION
        if news_id=="2485374":
            for lang in predecessor.OCR_LANGUAGES:
                profiles.setdefault(lang,old_sidecar['documents'][record['document_id']][lang])
        plan={lang:(None,lang,6) for lang in predecessor.OCR_LANGUAGES}
        plan.update(EXTRA_PROFILES.get(news_id,{}))
        for key,(page,lang,psm) in plan.items():
            if key in profiles:
                continue
            path=root/record['relative_path']
            proof=complete_pdf_proof(path,200,{})
            if proof['sha256']!=record['sha256']:
                raise ValueError('retained_document_hash_mismatch')
            profiles[key]=render_and_ocr(record,root=root,pages=[page] if page else range(1,proof['pdf_pages']+1),language=lang,psm=psm,dpi=300)
    SIDECAR.parent.mkdir(parents=True,exist_ok=True)
    SIDECAR.write_text(json.dumps(sidecar,ensure_ascii=False,sort_keys=True,indent=1)+'\n',encoding='utf8')
    return sidecar

def build_observations(sidecar=None):
    import copy
    sidecar=sidecar if sidecar is not None else json.loads(SIDECAR.read_bytes())
    source_records=all_records()
    reviews=copy.deepcopy(REVIEWS)
    reviews['2485374']=copy.deepcopy(predecessor.REVIEWS['2485374'])
    bonus=reviews['2485374'][1]
    bonus.pop('warnings',None)
    bonus['fields']['shares_planned']=predecessor._field(1,'500.219.550','planned bonus shares')
    observations=[]
    for n,items in sorted(reviews.items()):
        r=source_records[n]; pages=load_pages(sidecar,r,n)
        for item in items:
            observations.append(predecessor.reviewed_scan_observation(predecessor._document(r,r['document_class']),item,pages))
    observations += predecessor.build_observations(predecessor.load_sidecar(),source_records,
        reviews={'2430881':predecessor.REVIEWS['2430881']})
    issuer_names={'SSI':'Công ty Cổ phần Chứng khoán SSI',
                  'POW':'Tổng Công ty Điện lực Dầu khí Việt Nam - CTCP'}
    authors={source_records[n]['document_id']:author for n,author in {
        '2425221':'PV Power issuer report 2545/BC-ĐLDK',
        '2425695':'State Securities Commission 9119/UBCK-QLCB (page 2)',
        '2492611':'SSI Board resolution 27/2026/NQ-SSI.HĐQT'}.items()}
    for observation in observations:
        for citation in observation['citations']:
            field=citation['field']
            citation.update(entity=observation['ticker'], entity_name=issuer_names[observation['ticker']],
                source_id='hose', source_role='OFFICIAL_EXCHANGE_HOSTED_ORIGINAL',
                document_author=authors.get(observation['document_id'],'Hochiminh Stock Exchange'),
                source_url=observation['source_url'],
                original_sha256=observation['content_sha256'], source_document_id=observation['document_id'],
                unit=('date' if field.endswith('_date') else 'VND_per_share' if field in
                    {'subscription_price','cash_amount_per_share'} else 'new_shares_per_existing_share'
                    if field.endswith('_ratio') else 'shares'))
    return observations

def verify_originals():
    results=[]
    for n,r in sorted(records().items()):
        proof=complete_pdf_proof(RETENTION/r['relative_path'],r['http_status'],{
            'Content-Length':str(r['document_completeness']['http_content_length'])})
        if proof!=r['document_completeness'] or proof['sha256']!=r['sha256']:
            raise ValueError('original_completeness_or_hash_mismatch:'+n)
        results.append({'hose_news_id':n,**proof})
    return results

def build_artifact(sidecar=None):
    source_records=all_records()
    if set(records())!={r['hose_news_id'] for r in REQUESTS}:
        raise ValueError('retained_manifest_does_not_match_request_set')
    expected={r['hose_news_id']:r for r in REQUESTS}
    for news_id,r in records().items():
        request=expected[news_id]
        if (any(r[k]!=request[k] for k in ('ticker','canonical_url','document_class'))
                or r.get('source_id')!='hose' or r.get('source_authority')!='exchange'
                or r.get('published_at') is not None):
            raise ValueError('official_original_identity_mismatch')
        proof=r.get('document_completeness',{})
        if proof.get('pdf_pages')!=EXPECTED_PAGES[news_id]:
            raise ValueError('complete_original_page_count_required')
        if proof.get('state')!='COMPLETE_HTTP_BODY_AND_PDF_STRUCTURE' or proof.get('sha256')!=r['sha256']:
            raise ValueError('complete_original_required')
    observations=build_observations(sidecar)
    ledger=predecessor.build_ledger(observations)
    cohort=predecessor.build_factor_chain_cohort(ledger,knowledge_cutoff_resolver=predecessor.resolve_knowledge(
        {r['document_id']:r for r in source_records.values()}))
    docs=[{'hose_news_id':n, **{k:r[k] for k in ('document_id','ticker','sha256','canonical_url','observed_at','document_class')},
        'completeness':r.get('document_completeness'), 'availability_basis':'PRODUCER_RECEIPT_FORWARD_ONLY',
        'http_last_modified_role':'SERVER_FILE_CLOCK_ONLY', 'portal_posted_date_role':'NOT_HISTORICAL_AVAILABILITY'}
        for n,r in sorted(source_records.items())]
    # This aggregate cancellation cannot be assigned to either component leg.
    r=source_records['2425221']
    pages=load_pages(sidecar if sidecar is not None else json.loads(SIDECAR.read_bytes()),r,'2425221')
    if not any(p['page']==3 and predecessor._token_on_page('6.108',p['text']) for p in pages):
        raise ValueError('combined_fraction_cancellation_token_absent')
    from stocklookup_core.evidence.share_transition_bridge import resolve_share_transition
    continuity={}
    for ticker,value,news_id in [('SSI',2503089220,'2497826'),('POW',2786821096,'2443111')]:
        source=source_records[news_id]
        continuity[ticker]=resolve_share_transition({'value':value,'unit':'shares','share_class':'listed_shares',
            'identity_scope':'issuer','qualification':'qualified','source_hash':source['sha256'],
            'citation_id':source['document_id']},[],target_date='2026-10-26',coverage_through=None)
    return {'contract_version':'official_ssi_pow_ca_qualification/v1',
        'common_outstanding_continuity_gate':continuity,
        'aggregate_fraction_citation':{'document_id':r['document_id'],'sha256':r['sha256'],
            'page':3,'printed':'6.108','unit':'shares','scope':'combined_stock_and_bonus_only'},

        'milestone':'OFFICIAL_SSI_POW_CORPORATE_ACTION_EVIDENCE_QUALIFICATION_V1',
        'documents':docs,'observations':observations,'ledger':ledger,'factor_chain_cohort':cohort,
        'source_identity_corrections':{'2499239':{'printed_notice':'1935/TB-SGDHCM','rejected_lead_label':'457/TB-SGDHCM'},
           '2492611':{'complete_pages':5,'partial_hub_bytes_admissible':False}},
        'bounded_facts':{
          'SSI':{'listed_before':2503089220,'new_shares':500204581,'listed_after':3003293801,
            'planned_minus_distributed':14969,'treasury_after_issuance_only':1991468,
            'issued_total_excluding_reported_treasury_after':3001302333,'treasury_before':None,
            'common_outstanding_before_authority':'BLOCKED_NO_PRE_EVENT_TREASURY_STATEMENT',
            'issuance_completed':'2026-08-18','listing_effective':'2026-09-18','trading':'2026-10-01'},
          'POW':{'stock_and_bonus_before':2341871600,'stock_issued':93672392,'bonus_issued':351277104,
            'combined_issued':444949496,'combined_fractions_cancelled':6108,'combined_after':2786821096,
            'rights_issued':281024592,'rights_after':3067845688,
            'unrestricted_shares':276606691,'unrestricted_trading':'2026-03-26',
            'restricted_shares':4417901,'restricted_trading':'2027-01-28',
            'restricted_tradable_at_receipt':False}},
        'blockers':['SSI_MIXED_CASH_BONUS_NO_CASH_FACTOR_POLICY','SSI_PRE_EVENT_TREASURY_UNKNOWN',
            'POW_RIGHTS_UNSUPPORTED_FACTOR_TYPE','POW_RIGHTS_PLAN_EXECUTION_DIRECT_LINK_UNPROVEN','HISTORICAL_AVAILABILITY_UNPROVEN',
            'GOVERNED_SESSION_CALENDAR_DOES_NOT_REACH_RECEIPTS','NO_MARKET_WIDE_COVERAGE'],
        'authority_boundary':{'historical_pit_eligible':False,'raw_as_traded_promoted':False,
            'execution_eligible':False,'liquidity_eligible':False,'authority_promotion':False,
            'cash_factor_policy':'NONE','complete_pow_factor':'UNSUPPORTED_FACTOR_TYPE',
            'knowledge_basis':'LATEST_REQUIRED_PRODUCER_RECEIPT_ONLY'}}

def main(argv=None):
    p=argparse.ArgumentParser(__doc__)
    p.add_argument('--acquire',action='store_true');p.add_argument('--ocr',action='store_true')
    p.add_argument('--prior-retention-root',type=Path)
    args=p.parse_args(argv)
    if args.acquire:
        result=acquire(acquisition_specs(),RETENTION,timeout_seconds=30,max_attempts=1)
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0 if all(r['state'] in {'retained','cached_valid','refreshed_same_bytes'} for r in result['outcomes']) else 2
    if args.ocr:
        materialize_ocr(args.prior_retention_root);return 0
    verify_originals()
    artifact=build_artifact()
    artifact['artifact_sha256']=hashlib.sha256(predecessor._canonical(artifact).encode()).hexdigest()
    OUTPUT.write_text(json.dumps(artifact,ensure_ascii=False,sort_keys=True,indent=2)+'\n',encoding='utf8')
    print('Wrote',OUTPUT.relative_to(ROOT))
    return 0
if __name__=='__main__':
    raise SystemExit(main())
