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
from stocklookup_core.evidence.official_document_acquisition import acquire, MANIFEST
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
