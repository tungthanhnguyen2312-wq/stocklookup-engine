"""Offline VSDC prototype: synthetic notice facts, real acquirer receipt shape."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import types

import pytest

import market_wide_current_shares_resolver as shares
from stocklookup_core.evidence.corporate_action_events import parse_retained_vsdc_notice
from stocklookup_core.evidence.official_document_acquisition import acquire, MANIFEST, TICKERS
from stocklookup_core.evidence.official_source_registry import load_registry
from test_share_basis_official_event_staleness import _runtime, _context, _event, CUTOFF

FIXTURES = Path(__file__).parent / "fixtures" / "vsdc_notices"
URL = "https://vsdc.vn/vi/ad/202076"


def _notice(root, *, fixture="bmi_202076_synthetic.html", retrieved="2026-11-02T08:10:00Z"):
    payload = (FIXTURES / fixture).read_bytes()
    acquire([{"ticker": "BMI", "source_id": "vsdc", "canonical_url": URL,
              "document_class": "last_registration_date_notice", "reporting_period": "2026"}],
            root, fetcher=lambda *a, **k: (200, {"Content-Type": "text/html"}, payload, URL),
            observed_at=retrieved, additional_allowed_tickers=["BMI"])
    document = json.loads((root / MANIFEST).read_text(encoding="utf-8"))["records"][0]
    return document, payload


def _load(root, *, enabled=True, cutoff=CUTOFF, session="2026-11-23"):
    return shares.retained_official_share_events([root], session, known_by=cutoff,
                                                vsdc_hose_events_enabled=enabled)


def test_bmi_parser_preserves_stated_facts_and_missing_fields(tmp_path):
    doc, payload = _notice(tmp_path)
    event = parse_retained_vsdc_notice(doc, payload)
    assert (event["ticker"], event["isin"], event["exchange"]) == ("BMI", "VN000000BMI0", "HOSE")
    assert event["event_type"] == "stock_dividend"
    assert event["record_date"] == "2026-11-12" and event["ratio_terms"] == "10:1"
    assert event["rounding_rule"] == "ROUND_DOWN_FRACTIONAL_SHARES"
    assert event["updated_at"] == "2026-11-02T15:05:00+07:00"
    assert event["published_at"] is None
    assert event["retrieved_at"] == doc["observed_at"]
    assert event["content_sha256"] == hashlib.sha256(payload).hexdigest()
    assert event["notice_url"] == URL
    for field in ("ex_date", "new_share_count", "listing_effective_date"):
        assert event[field] is None and event["absent_fields"][field]
    assert event["entitlement_date_inference"]["classification"] == "INFERENCE"
    assert event["event_observation"]["lifecycle_state"] == "record_date_confirmed"


def test_real_retained_bmi_notice_parses_and_withholds(tmp_path):
    # bmi_202076_retained_20261124.html is the live VSDC page retrieved 2026-11-24 07:4x +07:00
    # (sha256 8b830f8c7ee91b0ececa4c6aec40344186e06eab12d7c41f308f3ddab99f7968); only the per-session
    # __VPToken anti-forgery meta value is redacted, nothing else is modified.
    doc, payload = _notice(tmp_path, fixture="bmi_202076_retained_20261124.html",
                           retrieved="2026-11-23T08:00:00Z")
    assert hashlib.sha256(payload).hexdigest() == "8b830f8c7ee91b0ececa4c6aec40344186e06eab12d7c41f308f3ddab99f7968"
    event = parse_retained_vsdc_notice(doc, payload)
    assert (event["ticker"], event["isin"], event["exchange"]) == ("BMI", "VN000000BMI0", "HOSE")
    assert event["event_type"] == "stock_dividend" and event["record_date"] == "2026-11-12"
    assert event["ratio_terms"] == "10:1" and event["rounding_rule"] == "ROUND_DOWN_FRACTIONAL_SHARES"
    assert event["updated_at"] == "2026-11-02T15:05:00+07:00"
    assert event["ex_date"] is None and event["new_share_count"] is None
    root = _runtime(tmp_path / "runtime", [("BMI", 1000.0, "2026-08-14")])
    enabled = _load(tmp_path)
    row = shares.resolve_market_wide_shares(root, "2026-11-23", official_events=enabled["events"],
                                            known_by=CUTOFF)["tickers"]["BMI"]
    assert row["authority"] == "provider_reported_stale" and row["value"] is None


def test_bmi_withheld_only_when_enabled_and_never_replaced(tmp_path, monkeypatch):
    _notice(tmp_path)
    root = _runtime(tmp_path / "runtime", [("BMI", 1000.0, "2026-08-14")])
    monkeypatch.setattr(shares, "vn_now_iso", lambda: "fixed-run-time")
    disabled = _load(tmp_path, enabled=False)
    enabled = _load(tmp_path)
    before = shares.resolve_market_wide_shares(root, "2026-11-23", official_events=disabled["events"])
    after = shares.resolve_market_wide_shares(root, "2026-11-23", official_events=enabled["events"], known_by=CUTOFF)
    assert before["tickers"]["BMI"]["value"] == 1000
    row = after["tickers"]["BMI"]
    assert row["authority"] == "provider_reported_stale" and row["value"] is None
    assert URL in row["reason"]
    assert row["official_share_event_evidence"][0]["used_as_share_count"] is False
    assert after["known_by"] == CUTOFF.isoformat() and after["counts_reconcile"]
    # Byte-level baseline comparison against the exact task base, including mixed HNX rows.
    _context(tmp_path, "2026-10-16", [_event("DHT", "BONUS", "2026-10-05")])
    legacy = types.ModuleType("baseline_shares")
    source = subprocess.check_output(["git", "show", "7ea5b514:market_wide_current_shares_resolver.py"])
    exec(compile(source, "baseline_shares.py", "exec"), legacy.__dict__)
    legacy.vn_now_iso = lambda: "fixed-run-time"
    old_events = legacy.retained_official_share_events([tmp_path], "2026-11-23")
    off = _load(tmp_path, enabled=False)
    assert {k: v for k, v in off.items() if k not in {"known_by", "diagnostics"}} == old_events
    old_output = legacy.resolve_market_wide_shares(root, "2026-11-23", official_events=old_events["events"])
    new_output = shares.resolve_market_wide_shares(root, "2026-11-23", official_events=off["events"])
    assert json.dumps(old_output, sort_keys=True).encode() == json.dumps(new_output, sort_keys=True).encode()


def test_late_retrieval_does_not_leak_into_replay(tmp_path):
    _notice(tmp_path, retrieved="2026-11-23T11:00:00Z")
    replay = _load(tmp_path)
    assert replay["events"] == {} and replay["diagnostics"][0]["reason"] == "NOT_KNOWN_BY_CUTOFF"
    assert "BMI" in _load(tmp_path, cutoff=datetime(2026, 11, 23, 11, tzinfo=timezone.utc))["events"]


@pytest.mark.parametrize("retrieved", [None, "bad", "2026-11-02T08:10:00"])
def test_unusable_retrieval_is_diagnostic_only(tmp_path, retrieved):
    _notice(tmp_path)
    manifest = tmp_path / MANIFEST
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["records"][0]["observed_at"] = retrieved
    manifest.write_text(json.dumps(data), encoding="utf-8")
    result = _load(tmp_path)
    assert result["events"] == {} and result["diagnostics"][0]["reason"] == "KNOWN_AT_UNAVAILABLE"


def test_cash_dividend_does_not_withhold(tmp_path):
    doc, payload = _notice(tmp_path, fixture="cash_dividend_synthetic.html")
    assert parse_retained_vsdc_notice(doc, payload)["event_type"] == "cash_dividend"
    assert _load(tmp_path)["events"] == {}


@pytest.mark.parametrize("session,observed,stale", [
    ("2026-11-11", "2026-08-14", False),
    ("2026-11-12", "2026-08-14", True),
    ("2026-11-23", "2026-11-12", False),
    ("2026-11-23", "2026-11-13", False),
])
def test_record_entitlement_bound_never_means_effective_count(tmp_path, session, observed, stale):
    _notice(tmp_path)
    root = _runtime(tmp_path / "runtime", [("BMI", 1000.0, observed)])
    events = _load(tmp_path, session=session)["events"]
    row = shares.resolve_market_wide_shares(root, session, official_events=events)["tickers"]["BMI"]
    assert (row["authority"] == "provider_reported_stale") is stale
    assert row["value"] == (None if stale else 1000)


def test_flag_defaults_off_and_no_vsd_acquisition_when_off(tmp_path, monkeypatch):
    assert load_registry()["feature_flags"]["vsdc_hose_share_staleness_prototype"] is False
    (tmp_path / MANIFEST).write_text("invalid JSON", encoding="utf-8")
    assert _load(tmp_path, enabled=False)["events"] == {}
    with pytest.raises(shares.ShareStoreUnreadable):
        _load(tmp_path)


def test_hash_identity_and_route_checks_fail_closed(tmp_path):
    doc, payload = _notice(tmp_path)
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        parse_retained_vsdc_notice(doc, payload + b" changed")
    with pytest.raises(ValueError, match="ROUTE_NOT_SUPPORTED"):
        parse_retained_vsdc_notice({**doc, "final_url": "https://example.com/vi/ad/202076"}, payload)
    with pytest.raises(ValueError, match="TICKER_MISMATCH"):
        parse_retained_vsdc_notice({**doc, "ticker": "FPT"}, payload)


def test_entitlement_inference_cannot_change_official_anchor_authority(tmp_path, monkeypatch):
    _notice(tmp_path)
    root = _runtime(tmp_path / "runtime", [("BMI", 1000.0, "2026-08-14")])
    anchor = {"value": 1000, "identity_type": shares._EVENT_IDENTITY,
              "share_count_identity": "common_shares_outstanding", "share_class": "common_outstanding",
              "effective_date": "2026-08-01", "reporting_period": "2026", "citation_id": "fixture-only",
              "corroborated_value": 1000, "corroborated_on": "2026-08-14", "coverage_through": "2026-11-23"}
    monkeypatch.setattr(shares, "load_official_anchors", lambda *a: {"BMI": anchor})
    result = shares.resolve_market_wide_shares(root, "2026-11-23", official_events=_load(tmp_path)["events"])
    assert result["tickers"]["BMI"]["authority"] == "qualified_official"
    assert result["tickers"]["BMI"]["value"] == 1000


def test_materializer_passes_enabled_vsdc_events_and_the_same_cutoff(tmp_path, monkeypatch):
    from tools import derive_market_wide_current_valuation_input_scaleout as runner
    from stocklookup_core.evidence import official_source_registry as registry
    _notice(tmp_path / "notices")
    original = registry.load_registry()
    original["feature_flags"]["vsdc_hose_share_staleness_prototype"] = True
    monkeypatch.setattr(registry, "load_registry", lambda: original)
    monkeypatch.setattr(runner, "_load", lambda *a: {"resolved_completed_session": "2026-11-23"})
    monkeypatch.setattr(runner, "_verify_sources", lambda *a: None)
    class Stop(Exception):
        pass
    def resolve(root, session, *, official_events, exchange_observations, known_by):
        assert "BMI" in official_events and session == "2026-11-23"
        assert known_by == CUTOFF and exchange_observations == {}
        raise Stop
    monkeypatch.setattr(runner, "resolve_market_wide_shares", resolve)
    with pytest.raises(Stop):
        runner.materialize(tmp_path / "out.json", price=Path("price"), runtime_root=tmp_path,
                           official_event_roots=[tmp_path / "notices"], known_by=CUTOFF)
    with pytest.raises(ValueError, match="KNOWN_BY_REQUIRED"):
        runner.materialize(tmp_path / "out.json", price=Path("price"), runtime_root=tmp_path,
                           official_event_roots=[tmp_path / "notices"])

from stocklookup_core.evidence.corporate_action_events import parse_retained_vsdc_registration

REGISTRATIONS = [
    ('vds', '203041', 'e315866be0cb1af2e3fc33744de7c3f4b5f31dfddfce3acb4aa60ea150b7a9fe', 'VN000000VDS6', 27200000, 299200000, '2026-11-23T13:35:59+07:00', 'STOCK_DIVIDEND'),
    ('fpt', '202030', 'f95c782666abd88331fd63276358a4072d9ad70640a0f276e373a948bafbb5bd', 'VN000000FPT1', 171401226, 1885727648, '2026-10-30T16:28:08+07:00', 'BONUS_SHARES'),
    ('nvl', '202081', 'f528b452d65c6bb125f64324320b14433de6bfad9152ee7a336ccdc258e50ecf', 'VN000000NVL0', 1737080, 2403805052, '2026-11-02T16:26:54+07:00', 'CONVERTIBLE_BOND_CONVERSION'),
    ('ssb', '200363', '157f5dc3354b4621c6c867c4da58c6fef24a5dcfadd7a5bcd7d9b9b57a78c5af', 'VN000000SSB6', 40000000, 3468800000, '2026-09-18T14:19:20+07:00', 'ESOP'),
]


def _registration(root, case=REGISTRATIONS[0]):
    ticker, number, digest, *_ = case
    payload = (FIXTURES / f'{ticker}_{number}_registration_retained_20261124.html').read_bytes()
    assert hashlib.sha256(payload).hexdigest() == digest
    url = 'https://vsdc.vn/vi/ad/' + number
    acquire([dict(ticker=ticker.upper(), source_id='vsdc', canonical_url=url,
                  document_class='corporate_action_notice', reporting_period='2026')], root,
            fetcher=lambda *a, **k: (200, {'Content-Type': 'text/html'}, payload, url),
            observed_at='2026-11-24T01:00:00Z', additional_allowed_tickers=None if ticker.upper() in TICKERS else [ticker.upper()])
    doc = json.loads((root / MANIFEST).read_text(encoding='utf8'))['records'][-1]
    return doc, payload


def _synthetic_venue(root, *, isin='VN000000VDS6', exchange='HOSE'):
    # Explicit synthetic linkage test, not retained factual evidence about VDS.
    payload = (FIXTURES / 'bmi_202076_synthetic.html').read_bytes().replace(b'BMI', b'VDS')
    payload = payload.replace(b'VN000000VDS0', isin.encode()).replace(b'HOSE', exchange.encode())
    url = 'https://vsdc.vn/vi/ad/999999'
    acquire([dict(ticker='VDS', source_id='vsdc', canonical_url=url,
                  document_class='last_registration_date_notice', reporting_period='2026')], root,
            fetcher=lambda *a, **k: (200, {'Content-Type': 'text/html'}, payload, url),
            observed_at='2026-11-02T08:10:00Z', additional_allowed_tickers=['VDS'])


@pytest.mark.parametrize('case', REGISTRATIONS, ids=lambda c: c[0])
def test_retained_registration_exact_facts(tmp_path, case):
    doc, payload = _registration(tmp_path, case)
    row = parse_retained_vsdc_registration(doc, payload)
    t, number, digest, isin, change, after, published, reason = case
    assert (row['ticker'], row['isin'], row['shares_change'], row['shares_after']) == (t.upper(), isin, change, after)
    assert row['change_direction'] == 'INCREASE' and row['exchange'] == 'UNKNOWN'
    assert row['published_at'] == published and row['reason_class'] == reason
    assert row['reason_text'] and row['share_concept'] == 'ISSUED_SHARES'
    assert row['content_sha256'] == digest and row['source_url'].endswith('/' + number)


@pytest.mark.parametrize('old,new', [
    ('299.200.000', '299.20.000'), ('299.200.000', '0'),
    ('27.200.000', '27.bad.000'), ('Mã ISIN:', 'Absent:'),
    ('Mã chứng khoán:', 'Absent:'), ('Số lượng chứng khoán hiện tại:', 'Absent:'),
    ('Số lượng chứng khoán tăng:', 'Absent:'), ('Lý do:', 'Absent:'),
    ('Cập nhật', 'Absent'), ('13:35:59', '25:35:59'),
])
def test_registration_damaged_or_missing_fields_block(tmp_path, old, new):
    import html
    doc, payload = _registration(tmp_path)
    payload = html.unescape(payload.decode('utf8')).replace(old, new).encode('utf8')
    doc['sha256'] = hashlib.sha256(payload).hexdigest()
    with pytest.raises(ValueError):
        parse_retained_vsdc_registration(doc, payload)


def test_registration_is_venue_independent_and_isin_bound(tmp_path):
    _registration(tmp_path)
    regs = [e for e in _load(tmp_path)['events'].get('VDS', []) if e['source'] == 'vsdc_retained_registration_prototype/v1']
    assert len(regs) == 1 and regs[0]['exchange'] == 'UNKNOWN' and regs[0]['isin'] == 'VN000000VDS6'


@pytest.mark.parametrize('isin,exchange,expected', [('VN000000VDS6', 'HOSE', 'HOSE'), ('VN000000VDS6', 'HNX', 'HNX'),
                                                     ('VN000000BMI0', 'HOSE', 'UNKNOWN')])
def test_registration_venue_recorded_only_from_same_isin_witness(tmp_path, isin, exchange, expected):
    _registration(tmp_path)
    _synthetic_venue(tmp_path, isin=isin, exchange=exchange)
    regs = [e for e in _load(tmp_path)['events'].get('VDS', []) if e['source'] == 'vsdc_retained_registration_prototype/v1']
    assert len(regs) == 1 and regs[0]['exchange'] == expected


@pytest.mark.parametrize('observed,cutoff,expected', [
    ('2026-08-14', '2026-11-23T06:35:58+00:00', None),
    ('2026-08-14', '2026-11-23T06:35:59+00:00', 299200000),
    ('2026-11-24', '2026-11-24T10:00:00+00:00', 1000),
    ('2026-11-23', '2026-11-24T10:00:00+00:00', 1000),
])
def test_registration_cutoff_and_provider_recency(tmp_path, observed, cutoff, expected):
    _registration(tmp_path)
    _synthetic_venue(tmp_path)
    clock = datetime.fromisoformat(cutoff)
    events = _load(tmp_path, cutoff=clock)['events']
    root = _runtime(tmp_path / 'runtime', [('VDS', 1000.0, observed)])
    row = shares.resolve_market_wide_shares(root, '2026-11-24', official_events=events, known_by=clock)['tickers']['VDS']
    assert row['value'] == expected
    assert (row['authority'] == 'official_registered_shares') is (expected == 299200000)
    if expected == 299200000:
        # Resolver defends the cutoff even with events loaded by a later caller.
        earlier = datetime.fromisoformat('2026-11-23T06:35:58+00:00')
        assert shares.resolve_market_wide_shares(root, '2026-11-24', official_events=events, known_by=earlier)['tickers']['VDS']['value'] is None


def test_registration_flag_off_byte_parity_with_task_head(tmp_path, monkeypatch):
    _registration(tmp_path)
    _synthetic_venue(tmp_path)
    root = _runtime(tmp_path / 'runtime', [('VDS', 1000.0, '2026-08-14')])
    legacy = types.ModuleType('task_head_shares')
    source = subprocess.check_output(['git', 'show', '19a8a908:market_wide_current_shares_resolver.py'])
    exec(compile(source, 'task_head_shares.py', 'exec'), legacy.__dict__)
    legacy.vn_now_iso = lambda: 'fixed-run-time'
    monkeypatch.setattr(shares, 'vn_now_iso', lambda: 'fixed-run-time')
    before = legacy.retained_official_share_events([tmp_path], '2026-11-23', known_by=CUTOFF)
    after = _load(tmp_path, enabled=False)
    assert before == after
    old = legacy.resolve_market_wide_shares(root, '2026-11-23', official_events=before['events'], known_by=CUTOFF)
    new = shares.resolve_market_wide_shares(root, '2026-11-23', official_events=after['events'], known_by=CUTOFF)
    assert json.dumps(old, sort_keys=True).encode() == json.dumps(new, sort_keys=True).encode()


def test_registration_decrease_preserves_direction_and_literal_reason(tmp_path):
    doc, payload = _registration(tmp_path)
    payload = payload.replace('Số lượng chứng khoán tăng:'.encode(), 'Số lượng chứng khoán giảm:'.encode())
    doc['sha256'] = hashlib.sha256(payload).hexdigest()
    row = parse_retained_vsdc_registration(doc, payload)
    assert row['change_direction'] == 'DECREASE' and row['shares_change'] == 27200000
    assert row['shares_after'] == 299200000
    assert row['reason_text'] == 'Phát hành cổ phiếu để trả cổ tức'


def test_registration_identity_and_route_are_hash_bound(tmp_path):
    doc, payload = _registration(tmp_path)
    with pytest.raises(ValueError, match='HASH_MISMATCH'):
        parse_retained_vsdc_registration(doc, payload + b' changed')
    with pytest.raises(ValueError, match='ROUTE_NOT_SUPPORTED'):
        parse_retained_vsdc_registration({**doc, 'final_url': 'https://example.com/vi/ad/203041'}, payload)
    with pytest.raises(ValueError, match='INSTRUMENT_UNPROVEN'):
        parse_retained_vsdc_registration({**doc, 'ticker': 'FPT'}, payload)


def test_official_source_registry_vsdc_flag_source_transition_reconstructs_and_fails_closed(tmp_path):
    from tools import verify_retention_reader_transition as vrt
    root = Path(__file__).resolve().parents[1]
    rel = vrt.OFFICIAL_SOURCE_REGISTRY_VSDC_FLAG_SOURCE
    live = (root / rel).read_bytes().replace(b'\r\n', b'\n')
    prior_e31 = subprocess.check_output(
        ['git', 'show', vrt.OFFICIAL_SOURCE_REGISTRY_VSDC_FLAG_BASE + ':' + rel], cwd=root
    ).replace(b'\r\n', b'\n')
    assert vrt._official_source_registry_vsdc_flag_prior_bytes(root, rel, live) == prior_e31
    assert vrt.historical_bytes(root, rel) == prior_e31

    # Flipping the flag to true or making any extra edit must fail closed.
    flipped = live.replace(b': false},', b': true},', 1)
    with pytest.raises(ValueError, match='OFFICIAL_SOURCE_REGISTRY_VSDC_FLAG_SOURCE_TRANSITION_BINDING_INVALID'):
        vrt._official_source_registry_vsdc_flag_prior_bytes(root, rel, flipped)
    with pytest.raises(ValueError, match='OFFICIAL_SOURCE_REGISTRY_VSDC_FLAG_SOURCE_TRANSITION_BINDING_INVALID'):
        vrt._official_source_registry_vsdc_flag_prior_bytes(root, rel, live + b'\n')

    # Tampered manifest scope or archive must fail closed.
    manifest_dst = tmp_path / vrt.OFFICIAL_SOURCE_REGISTRY_VSDC_FLAG_MANIFEST
    archive_dst = tmp_path / vrt.OFFICIAL_SOURCE_REGISTRY_VSDC_FLAG_ARCHIVE
    manifest_dst.parent.mkdir(parents=True, exist_ok=True)
    archive_dst.parent.mkdir(parents=True, exist_ok=True)
    spec = json.loads((root / vrt.OFFICIAL_SOURCE_REGISTRY_VSDC_FLAG_MANIFEST).read_bytes())
    archive_dst.write_bytes(prior_e31)
    manifest_dst.write_text(json.dumps({**spec, 'scope': 'EXPANDED'}), encoding='utf-8')
    with pytest.raises(ValueError, match='OFFICIAL_SOURCE_REGISTRY_VSDC_FLAG_SOURCE_TRANSITION_SCOPE_INVALID'):
        vrt._official_source_registry_vsdc_flag_prior_bytes(tmp_path, rel, live)
    manifest_dst.write_text(json.dumps(spec), encoding='utf-8')
    archive_dst.write_bytes(prior_e31 + b'x')
    with pytest.raises(ValueError, match='OFFICIAL_SOURCE_REGISTRY_VSDC_FLAG_SOURCE_TRANSITION_BINDING_INVALID'):
        vrt._official_source_registry_vsdc_flag_prior_bytes(tmp_path, rel, live)
