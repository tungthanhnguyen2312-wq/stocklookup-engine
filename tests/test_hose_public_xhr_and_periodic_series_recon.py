from __future__ import annotations

import json
from io import BytesIO
from pathlib import Path
from types import SimpleNamespace
from urllib.error import HTTPError, URLError
import ssl

import pytest
import hose_public_xhr_and_periodic_series_recon as hose
from official_acquisition_budget import AcquisitionBudget

from hose_public_xhr_and_periodic_series_recon import PUBLIC_XHR, _disclosure_urls, build, replay


def _response(url: str):
    if "stock?page" in url:
        data = {"success": True, "data": {"list": [{"id": 1, "code": "AAA", "name": "A", "isin": "VNAAA", "securitiesType": 1, "listingStatusId": 11, "listingVolume": "100", "outStanding": "90"}], "paging": {"totalCount": 1}}}
    elif "listing-dashboard" in url:
        data = {"success": True, "data": {"securitiesTotal": 1}}
    elif "indicies/0" in url:
        data = {"success": True, "data": [{"id": 5, "name": "VN30"}]}
    elif "indicies/5/" in url:
        data = {"success": True, "data": {"list": [{"id": 1, "code": "AAA"}], "paging": {"totalCount": 1}}}
    elif "foreign" in url:
        data = {"success": True, "data": {"list": [{"reportDate": 1, "totalRoom": 2, "currentRoom": 3}]}}
    elif "market/securities/HPG" in url:
        data = {"success": True, "data": {"mainValue": 4}}
    elif "dividend" in url:
        data = {"success": True, "data": [{"type": "cash", "transNoRightDate": 1, "lastRegDate": 2}]}
    elif "news/securities/2458" in url:
        data = {"success": True, "data": {"list": [{"id": 2, "title": "HPG"}]}}
    elif "news/securitiesType" in url:
        data = {"success": True, "data": {"list": [{"id": 3, "title": "Market"}]}}
    elif "NewsFeed" in url:
        return {"requested_url": url, "official_url": url, "retrieved_at": "2026-08-24T00:00:00Z", "http_status": 200, "content_type": "application/rss+xml", "data": b"<rss/>"}
    else:
        data = {"success": True, "data": {}}
    return {"requested_url": url, "official_url": url, "retrieved_at": "2026-08-24T00:00:00Z", "http_status": 200, "content_type": "application/json", "data": json.dumps(data).encode()}


def test_public_xhr_snapshot_replays_and_preserves_share_boundary(tmp_path: Path):
    universe = tmp_path / "universe.json"
    universe.write_text(json.dumps({"records": {f"T{i:04}": {} for i in range(1683)}}), encoding="utf-8")
    hnx = tmp_path / "hnx.json"
    hnx.write_text(json.dumps({"datasets": {"hnx_official_equity_universe/v1": [{"ticker": "T0000"}]}}), encoding="utf-8")
    artifact = build(destination=tmp_path, stocklookup_universe=universe, hnx_universe=hnx, fetcher=_response)
    replay(artifact, destination=tmp_path)
    assert artifact["coverage"]["hose_public_universe_rows"] == 1
    assert artifact["coverage"]["public_issued_share_rows"] == 0
    assert artifact["share_semantics"]["public_current_kllh_result"].startswith("HOSE_OUTSTANDING_VOLUME")
    expected_surfaces = set(PUBLIC_XHR) | set(_disclosure_urls("2026-08-24"))
    assert expected_surfaces == {capture["surface"] for capture in artifact["captures"]}


def test_as_of_date_defaults_to_today_and_accepts_explicit_override(tmp_path: Path):
    """Regression guard for OFFICIAL_CORPORATE_EVENT_INCREMENTAL_ACQUISITION_AND_FRESHNESS_V1:
    AS_OF_DATE used to be a permanently frozen 2026-08-24 module constant, so every disclosure
    fetch stayed capped at that literal date forever regardless of when the acquisition actually
    ran. build() now defaults to the real current Vietnam civil date and still accepts an explicit
    override for deterministic/historical replay."""
    universe = tmp_path / "universe.json"
    universe.write_text(json.dumps({"records": {f"T{i:04}": {} for i in range(1683)}}), encoding="utf-8")
    hnx = tmp_path / "hnx.json"
    hnx.write_text(json.dumps({"datasets": {"hnx_official_equity_universe/v1": [{"ticker": "T0000"}]}}), encoding="utf-8")
    seen_urls: list[str] = []

    def _tracking_response(url: str):
        seen_urls.append(url)
        return _response(url)

    explicit = build(destination=tmp_path / "explicit", stocklookup_universe=universe, hnx_universe=hnx,
                      fetcher=_tracking_response, as_of_date="2026-01-15")
    assert explicit["as_of_date"] == "2026-01-15"
    assert any("endDate=2026-01-15" in url for url in seen_urls)

    default = build(destination=tmp_path / "default", stocklookup_universe=universe, hnx_universe=hnx, fetcher=_response)
    from vn_time import vn_today
    assert default["as_of_date"] == vn_today()


@pytest.mark.parametrize('error,status,reason_type',[
    (TimeoutError('read timed out'),None,None),
    (HTTPError('https://api.hsx.vn/public',429,'Too Many Requests',{},None),429,'str'),
    (URLError(ssl.SSLCertVerificationError(1,'certificate verify failed')),None,'SSLCertVerificationError'),
])
def test_original_transport_failure_survives_budget_receipt(monkeypatch,error,status,reason_type):
    budget=AcquisitionBudget()
    calls=[]
    def failed(request): calls.append(request.full_url); raise error
    monkeypatch.setattr(budget,'open',failed)
    clocks=iter(['2026-10-28T12:00:00Z','2026-10-28T12:00:30Z'])
    monkeypatch.setattr(hose,'_now',lambda:next(clocks))
    url=_disclosure_urls('2026-10-28')['market_disclosures']
    budget.request(hose.fetch,url,surface='market_disclosures',page=1)
    receipt=budget.report()['requests'][0]
    assert calls==[url] and receipt['status']=='SOURCE_FAILURE'
    assert receipt['error']==type(error).__name__ and receipt['error_message']==str(error)
    assert receipt['http_status']==status and receipt['error_reason_type']==reason_type
    assert receipt['error_phase']=='OPEN_OR_WAIT_HTTP_HEADERS'
    assert receipt['requested_at']=='2026-10-28T12:00:00Z'
    assert receipt['retrieved_at']=='2026-10-28T12:00:30Z'
    assert budget.report()['limits']['request_timeout_seconds']==30


class _TransportResponse(BytesIO):
    status=200
    headers=SimpleNamespace(get_content_type=lambda:'application/json')
    def geturl(self):return 'https://api.hsx.vn/public'


def test_http_200_body_timeout_is_not_classified_as_returned(monkeypatch):
    budget=AcquisitionBudget()
    class Broken(_TransportResponse):
        def read1(self,size):raise TimeoutError('body timed out')
    monkeypatch.setattr(budget,'open',lambda request:Broken())
    result=budget.request(hose.fetch,'https://api.hsx.vn/public',surface='market_disclosures')
    receipt=budget.report()['requests'][0]
    assert result['data']==b'' and receipt['http_status']==200
    assert receipt['status']=='SOURCE_FAILURE' and receipt['error_phase']=='READ_BODY'
    assert receipt['error']=='TimeoutError' and len(budget.requests)==1


@pytest.mark.parametrize('requested,completed',[
    ('2026-10-28T12:00:00Z','2026-10-28T12:00:24Z'),
    ('2026-10-28T16:59:50Z','2026-10-28T17:00:05Z'),  # Vietnam midnight crossed during I/O.
])
def test_success_retains_actual_completed_clock_separate_from_request(tmp_path,monkeypatch,requested,completed):
    budget=AcquisitionBudget()
    clocks=iter([requested,completed])
    monkeypatch.setattr(hose,'_now',lambda:next(clocks))
    payload=b'{"success":true,"data":{"list":[]}}'
    monkeypatch.setattr(budget,'open',lambda request:_TransportResponse(payload))
    response=budget.request(hose.fetch,'https://api.hsx.vn/public',surface='market_disclosures')
    capture=hose.retain(response=response,destination=tmp_path,surface='market_disclosures')
    assert capture['requested_at']==requested
    assert capture['retrieved_at']==completed
    assert (tmp_path/capture['relative_path']).read_bytes()==payload
    assert budget.requests[0]['status']=='RETURNED'


def test_market_source_failure_is_saved_without_retry_or_false_success(tmp_path,monkeypatch):
    import official_corporate_event_incremental_acquisition as acquisition
    import stocklookup_core.evidence.hnx_enumerable_universe_kllh_event_disclosure_scaleout as hnx
    from test_official_corporate_event_incremental_acquisition import _stocklookup_universe,_make_hnx_fetch,_hose_response
    _stocklookup_universe(tmp_path)
    monkeypatch.setattr(hnx,'fetch',_make_hnx_fetch())
    calls=[]
    def response(url):
        calls.append(url)
        if 'news/securitiesType' in url:
            return {'data':b'','http_status':None,'error':'TimeoutError','error_message':'read timed out',
                    'error_phase':'OPEN_OR_WAIT_HTTP_HEADERS','requested_at':'2026-10-28T12:00:00Z',
                    'retrieved_at':'2026-10-28T12:00:30Z'}
        return _hose_response(url)
    result=acquisition.acquire(tmp_path,session='2026-10-28',hose_fetcher=response)
    assert result['disposition']=='FAILURE'
    assert result['error_message']=='PUBLIC_XHR_FETCH_FAILED:market_disclosures'
    receipt=result['budget_usage']['requests'][-1]
    assert receipt['error']=='TimeoutError' and receipt['error_phase']=='OPEN_OR_WAIT_HTTP_HEADERS'
    saved=tmp_path/acquisition.SESSIONS_RELATIVE/'2026-10-28'/acquisition.ATTEMPT_FILENAME
    assert json.loads(saved.read_bytes())==result
    assert sum('news/securitiesType' in url for url in calls)==1
