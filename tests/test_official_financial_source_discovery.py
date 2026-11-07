import inspect
from stocklookup_core.evidence.official_financial_source_discovery import discover_routes, prior_inbox_research_lead
REG={'sources':[{'activation':'approved','allowed_hosts':['issuer.example']}]}
def test_discovery_is_not_approval_without_registry_host():
 r=discover_routes([{'ticker':'AAA'}],{'AAA':{'candidate_url':'https://mirror.example/x','issuer_domain_evidence':'claim'}},REG)
 assert r['route_candidates'][0]['disposition']=='CANDIDATE_ROUTE_NEEDS_MORE_EVIDENCE'
def test_identity_requirement_and_determinism():
 a=discover_routes([{'ticker':'BBB'}],{'BBB':{'candidate_url':'https://issuer.example/x'}},REG);b=discover_routes([{'ticker':'BBB'}],{'BBB':{'candidate_url':'https://issuer.example/x'}},REG)
 assert a['route_candidates'][0]['disposition']=='IDENTITY_AMBIGUOUS' and a['identity']==b['identity']
def test_approved_route_needs_explicit_evidence_and_no_ticker_branch():
 r=discover_routes([{'ticker':'CCC'}],{'CCC':{'candidate_url':'https://issuer.example/x','issuer_domain_evidence':'official exchange profile'}},REG)
 assert r['route_candidates'][0]['disposition']=='APPROVABLE_OFFICIAL_ROUTE_DISCOVERED'
 assert 'if ticker ==' not in inspect.getsource(discover_routes)
def test_inbox_lead_is_not_route_approval_or_a_verified_fact():
 lead=prior_inbox_research_lead(issue=109, reported_sha256='abc', byte_sha256='abc')
 assert lead['bytes_rechecked'] is True and lead['hub_memo_is_fact_authority'] is False
 assert lead['done_label_is_product_verified'] is False and lead['periodic_hub_scan'] is False
 assert lead['daily_critical_path'] is False and lead['authority']=='RESEARCH_ONLY_NOT_PRODUCT_VERIFIED'
 assert prior_inbox_research_lead(issue=66, reported_sha256='abc', byte_sha256='def')['bytes_rechecked'] is False
