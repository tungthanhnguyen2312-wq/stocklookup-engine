"""Retained official share-changing events withhold a provider share count observed before them.

2026-11-23: every provider share observation in the research universe dated from 2026-08-14,
and the retained ledger in vn_stock.db carried no later event, so 30 tickers kept a pre-event
count as research-usable market cap although the retained official HNX/HOSE event context held
an officially qualified stock-dividend, bonus or rights ex-date after that observation (PVS
2026-09-14, DHT 2026-10-05, IPA 2026-08-21, VC3 2026-08-27, ...). The count is withheld as
stale, never adjusted by the event ratio.
"""
from __future__ import annotations

import json
import sqlite3
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

    def resolver(runtime_root, session, *, official_events=None):
        seen.update(session=session, events=official_events)
        raise Stop

    monkeypatch.setattr(runner, "resolve_market_wide_shares", resolver)
    with pytest.raises(Stop):
        runner.materialize(tmp_path / "out" / "a.json", price=Path("price"), fundamental=Path("f"), shares=Path("s"),
                           p3e=Path("p"), official_universe=None, runtime_root=tmp_path, report=tmp_path / "r.json",
                           official_event_roots=[tmp_path / "retained"])
    assert seen["session"] == "2026-11-23" and [e["ex_date"] for e in seen["events"]["DHT"]] == ["2026-10-05"]
