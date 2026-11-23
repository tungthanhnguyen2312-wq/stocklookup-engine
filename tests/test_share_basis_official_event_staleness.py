"""Retained official share-changing events withhold a provider share count observed before them.

2026-11-23: every provider share observation in the research universe dated from 2026-08-14,
and the retained ledger in vn_stock.db carried no later event, so 30 tickers kept a pre-event
count as research-usable market cap although the retained official HNX/HOSE event context held
an officially qualified stock-dividend, bonus or rights ex-date after that observation (PVS
2026-09-14, DHT 2026-10-05, IPA 2026-08-21, VC3 2026-08-27, ...). The count is withheld as
stale, never adjusted by the event ratio.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pytest

import market_wide_current_shares_resolver as shares
from stocklookup_core.valuation.market_wide_current_valuation_input_scaleout import STALE_FAIL_CLOSED_AUTHORITIES


def _runtime(root: Path, metadata, events=()) -> Path:
    evidence = root / "data" / "official-evidence"
    evidence.mkdir(parents=True, exist_ok=True)
    (evidence / "share_basis_citations.jsonl").write_text("", encoding="utf-8")
    connection = sqlite3.connect(root / "vn_stock.db")
    connection.execute("CREATE TABLE metadata (ticker TEXT, shares_outstanding REAL, updated TEXT)")
    connection.execute("CREATE TABLE corporate_event_records (ticker TEXT, event_code TEXT, exright_date TEXT, coverage_status TEXT)")
    connection.executemany("INSERT INTO metadata VALUES (?, ?, ?)", metadata)
    connection.executemany("INSERT INTO corporate_event_records VALUES (?, ?, ?, ?)", events)
    connection.commit()
    connection.close()
    return root


def _context(root: Path, acquired: str, rows, *, identity: str | None = None) -> Path:
    directory = root / "operations-review" / ("current-official-event-context-integration-v1-" + acquired.replace("-", ""))
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "current_official_event_context_artifact.json"
    path.write_text(json.dumps({
        "contract_version": "current_official_event_context/v1", "research_session": acquired,
        "artifact_identity": identity or ("current_official_event_context:" + acquired),
        "all_current_universe_event_records": rows}), encoding="utf-8")
    return path


def _event(ticker, event_type, ex_date, qualification="EX_DATE_OFFICIAL_QUALIFIED", event_id=None):
    return {"ticker": ticker, "event_type": event_type, "ex_date": ex_date, "qualification": qualification,
            "event_id": event_id or f"{ticker}:{event_type}:{ex_date}", "source": "hnx_official_rights_event_index/v1"}


def test_only_official_share_changing_events_known_by_the_session_are_kept(tmp_path):
    _context(tmp_path, "2026-10-16", [
        _event("DHT", "BONUS", "2026-10-05"),
        _event("PVS", "STOCK_DIVIDEND", "2026-09-14"),
        _event("AAA", "RIGHTS", "2026-10-01"),
        _event("CSH", "CASH_DIVIDEND", "2026-10-02"),                      # not share changing
        _event("BBB", "BONUS", "2026-10-03", qualification="MISSING_EX_DATE"),  # not officially dated
        _event("LATE", "BONUS", "2026-12-01"),                             # after the session
    ])
    _context(tmp_path, "2026-11-30", [_event("FUT", "BONUS", "2026-11-20")])  # acquired after the session
    found = shares.retained_official_share_events([tmp_path], "2026-11-23")
    assert found["status"] == "APPLIED" and found["context_sessions"] == ["2026-10-16"]
    assert sorted(found["events"]) == ["AAA", "DHT", "PVS"]
    assert found["events"]["DHT"] == [{"event_id": "DHT:BONUS:2026-10-05", "event_type": "BONUS", "ex_date": "2026-10-05",
                                       "source": "hnx_official_rights_event_index/v1", "first_retained_in_context": "2026-10-16"}]


def test_the_same_context_in_two_governed_roots_counts_once(tmp_path):
    for root in (tmp_path / "checkout", tmp_path / "retained"):
        _context(root, "2026-10-16", [_event("DHT", "BONUS", "2026-10-05")], identity="current_official_event_context:same")
    found = shares.retained_official_share_events([tmp_path / "checkout", tmp_path / "retained"], "2026-11-23")
    assert found["context_count"] == 1 and len(found["events"]["DHT"]) == 1


def test_no_context_is_reported_and_an_unreadable_one_fails_closed(tmp_path):
    assert shares.retained_official_share_events([tmp_path], "2026-11-23")["status"] == "NO_RETAINED_OFFICIAL_EVENT_CONTEXT"
    _context(tmp_path, "2026-10-16", []).write_text("{not json", encoding="utf-8")
    with pytest.raises(shares.ShareStoreUnreadable):
        shares.retained_official_share_events([tmp_path], "2026-11-23")


def test_official_ex_date_after_the_observation_withholds_the_count(tmp_path):
    root = _runtime(tmp_path / "rt", [("DHT", 90574038.0, "2026-08-14 10:00"), ("OLD", 1000.0, "2026-08-14 10:00"),
                                     ("TCB", 7086240414.0, "2026-08-14 10:00")])
    events = {"DHT": [{"event_type": "BONUS", "ex_date": "2026-10-05"}],
              "OLD": [{"event_type": "BONUS", "ex_date": "2026-08-01"}],    # before the observation
              "TCB": [{"event_type": "STOCK_DIVIDEND", "ex_date": "2026-12-01"}]}  # after the session
    before = shares.resolve_market_wide_shares(root, "2026-11-23")
    after = shares.resolve_market_wide_shares(root, "2026-11-23", official_events=events)
    assert {t: r["authority"] for t, r in before["tickers"].items()} == dict.fromkeys(("DHT", "OLD", "TCB"), "provider_reported_lagged")
    dht = after["tickers"]["DHT"]
    assert dht["authority"] == "provider_reported_stale" and dht["value"] is None
    assert dht["share_changing_after_observation"] == ["OFFICIAL_BONUS"]
    assert dht["authority"] in STALE_FAIL_CLOSED_AUTHORITIES
    assert after["tickers"]["OLD"]["authority"] == "provider_reported_lagged" and after["tickers"]["OLD"]["value"] == 1000
    assert after["tickers"]["TCB"]["authority"] == "provider_reported_lagged"
    assert after["official_share_events_applied"] == 2 and after["counts_reconcile"]


def test_valuation_materializer_passes_retained_official_events_to_the_resolver(tmp_path, monkeypatch):
    from tools import derive_market_wide_current_valuation_input_scaleout as runner

    _context(tmp_path / "retained", "2026-10-16", [_event("DHT", "BONUS", "2026-10-05")])
    sources = {"price": {"resolved_completed_session": "2026-11-23", "retained_snapshot_session": "2026-11-23"}}
    monkeypatch.setattr(runner, "_load", lambda path: sources.get(Path(path).name, {}))
    monkeypatch.setattr(runner, "_verify_sources", lambda *a: None)
    seen = {}

    class Stop(Exception):
        pass

    def resolver(runtime_root, session, *, official_events=None, exchange_observations=None):
        seen.update(session=session, events=official_events, exchange=exchange_observations)
        raise Stop

    monkeypatch.setattr(runner, "resolve_market_wide_shares", resolver)
    with pytest.raises(Stop):
        runner.materialize(tmp_path / "out" / "a.json", price=Path("price"), fundamental=Path("f"), shares=Path("s"),
                           p3e=Path("p"), official_universe=None, runtime_root=tmp_path, report=tmp_path / "r.json",
                           official_event_roots=[tmp_path / "retained"],
                           known_by=datetime(2026, 11, 23, 10, 30, tzinfo=timezone.utc))
    assert seen["session"] == "2026-11-23" and [e["ex_date"] for e in seen["events"]["DHT"]] == ["2026-10-05"]
    assert seen["exchange"] == {}


def _listing_sources(root: Path, known_at: str, rows) -> Path:
    directory = root / "operations-review" / "prospective-universe-evidence-v1" / "listing-sources"
    directory.mkdir(parents=True, exist_ok=True)
    records = [{"knowledge_available_at": known_at, "current_universe_projection": {"ticker": t, "official_source": src},
                "source_observation": obs} for t, src, obs in rows]
    body = {"records": records, "known": known_at}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True).encode()).hexdigest()
    path = directory / (digest + ".json")
    path.write_text(json.dumps({**body, "artifact_identity": "prospective_listing_source_observations:" + digest}), encoding="utf-8")
    return path


def test_latest_exchange_observation_known_by_the_cutoff_and_session_is_selected(tmp_path):
    _listing_sources(tmp_path, "2026-11-19T23:34:43Z", [
        ("TCB", "hose_public_stock_master/v1", {"exchange_outstanding_volume": "7,086,240,414"}),
        ("PVS", "hnx_official_equity_universe/v1", {"hnx_kllh_shares": 613699317})])
    _listing_sources(tmp_path, "2026-11-23T12:48:47Z", [   # captured after the 17:33 valuation
        ("TCB", "hose_public_stock_master/v1", {"exchange_outstanding_volume": "10,629,355,539"})])
    _listing_sources(tmp_path, "2026-11-24T08:00:00Z", [   # next session: never seen by a 11-23 replay
        ("TCB", "hose_public_stock_master/v1", {"exchange_outstanding_volume": "1"})])
    at_daily = shares.retained_exchange_share_observations(
        [tmp_path], "2026-11-23", known_by=datetime(2026, 11, 23, 10, 33, tzinfo=timezone.utc))
    assert at_daily["knowledge_available_at"] == "2026-11-19T23:34:43+00:00"
    assert at_daily["observations"]["TCB"]["value"] == 7086240414
    assert at_daily["observations"]["PVS"] == {"value": 613699317, "field": "hnx_kllh_shares",
                                               "semantic": "HNX_KLLH_EXCHANGE_REPORTED_CIRCULATING_SHARES",
                                               "source": "hnx_official_equity_universe/v1", "known_at": "2026-11-19T23:34:43Z"}
    later = shares.retained_exchange_share_observations(
        [tmp_path], "2026-11-23", known_by=datetime(2026, 11, 30, tzinfo=timezone.utc))
    assert later["observations"]["TCB"]["value"] == 10629355539
    with pytest.raises(ValueError):
        shares.retained_exchange_share_observations([tmp_path], "2026-11-23", known_by=datetime(2026, 11, 23))
    assert shares.retained_exchange_share_observations(
        [tmp_path / "none"], "2026-11-23", known_by=datetime(2026, 11, 23, tzinfo=timezone.utc))["status"] == \
        "NO_RETAINED_EXCHANGE_SHARE_OBSERVATION"


def test_contradicting_exchange_observation_withholds_and_is_never_used_as_the_count(tmp_path):
    root = _runtime(tmp_path / "rt", [("GMD", 432892509.0, "2026-08-14 10:00"), ("TCB", 7086240414.0, "2026-08-14 10:00"),
                                     ("TRS", 1000000.0, "2026-08-14 10:00"), ("LOW", 1000000.0, "2026-08-14 10:00")])
    witness = {"GMD": {"value": 649337392, "field": "exchange_outstanding_volume"},   # +50%: contradicts
               "TCB": {"value": 7086240414, "field": "exchange_outstanding_volume"},  # equal: no evidence
               "TRS": {"value": 1009000, "field": "hnx_kllh_shares"},                # +0.9%: share semantics
               "LOW": {"value": 980000, "field": "hnx_kllh_shares"}}                 # -2%: contradicts too
    result = shares.resolve_market_wide_shares(root, "2026-11-23", exchange_observations=witness)
    gmd = result["tickers"]["GMD"]
    assert gmd["authority"] == "provider_reported_stale" and gmd["value"] is None
    assert gmd["reason"] == "contradicted_by_official_exchange_share_observation"
    assert gmd["exchange_share_observation"]["used_as_share_count"] is False
    assert gmd["exchange_share_observation"]["relative_gap"] == pytest.approx(0.5, abs=1e-4)
    assert result["tickers"]["LOW"]["authority"] == "provider_reported_stale"
    for ticker, value in (("TCB", 7086240414), ("TRS", 1000000)):
        assert result["tickers"][ticker]["authority"] == "provider_reported_lagged"
        assert result["tickers"][ticker]["value"] == value
    assert result["exchange_share_witnesses"] == 4 and result["counts_reconcile"]
