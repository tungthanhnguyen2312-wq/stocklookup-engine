"""Current-session VN-Index level from the already-qualified DNSE index route.

Reuses ``dnse_index_return_series_capability`` for benchmark eligibility,
published-level parsing and the index-point unit established on 2026-08-10.
This module does not read ``vn_stock.db``, does not average constituents,
and does not treat DNSE as the HOSE index administrator.

A level binds into a Daily session only when the capture's Vietnam calendar
date is that same session. A later capture stays retained evidence and is
refused for the sealed session (no backfill).

The previous close is the previous returned DNSE bar only when the gap is a
single weekday or a Friday-to-Monday weekend. A longer gap (holiday or a
missing bar) fails closed. There is no exchange holiday calendar on this route.
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import date, datetime
from pathlib import Path
from typing import Any, Mapping

import dnse_index_return_series_capability as index_capability
from dnse_current_state_price_analytics import normalize_bars
from vn_time import VN_TZ

CONTRACT_VERSION = "dnse_vnindex_session_level/v1"
BENCHMARK_ID = "VNINDEX"
AUTHORITY = "DNSE_CURRENT_STATE_REPUBLISHED_INDEX_NOT_HOSE_ADMINISTRATOR"
EVIDENCE_CLASS = "EXTERNAL_ATTRIBUTED"
PLAUSIBLE_RANGE = (200.0, 5000.0)
RETAINED_DIR_NAME = "dnse-vnindex-session-level"
RETAINED_ROOT_ENV = "STOCK_LOOKUP_RETAINED_EVIDENCE_ROOT"


class VnIndexSessionLevelError(ValueError):
    """Fail-closed rejection of an index-level claim this route cannot support."""


def _canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _hash(value: Any) -> str:
    return hashlib.sha256(_canonical(value).encode("utf-8")).hexdigest()


def _vn_date(value: str) -> str | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=VN_TZ)
    return parsed.astimezone(VN_TZ).date().isoformat()


def _gap_allowed(session: str, previous: str) -> bool:
    current, prior = date.fromisoformat(session), date.fromisoformat(previous)
    delta = (current - prior).days
    if delta == 1 and current.weekday() < 5 and prior.weekday() < 5:
        return True
    return delta == 3 and current.weekday() == 0 and prior.weekday() == 4


def _in_range(level: float) -> bool:
    low, high = PLAUSIBLE_RANGE
    return low <= level <= high


def qualify_session_level(
    raw_ohlc: Mapping[str, Any],
    *,
    session: str,
    knowledge_available_at: str,
    query: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Qualify one VN-Index close and its previous returned bar.

    Returns a record. ``status == QUALIFIED`` carries ``benchmark`` in the
    shape ``market_close_intelligence`` already accepts. Anything else is a
    refusal with reason codes and no invented level.
    """
    refusal: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION, "status": "REFUSED", "session": session,
        "benchmark_id": BENCHMARK_ID, "evidence_class": EVIDENCE_CLASS,
        "derivation_from_constituents": "NOT_PERMITTED", "vn_stock_db_used": False,
    }
    if not index_capability.benchmark_current_state_eligible(BENCHMARK_ID):
        return {**refusal, "reason_codes": ["BENCHMARK_NOT_EVIDENCE_QUALIFIED"]}
    sent = dict(query or {})
    if sent and (sent.get("symbol") != BENCHMARK_ID or sent.get("type") != "INDEX" or sent.get("resolution") != "1D"):
        return {**refusal, "reason_codes": ["QUERY_NOT_THE_QUALIFIED_VNINDEX_1D_ROUTE"]}
    try:
        normalized = normalize_bars(BENCHMARK_ID, raw_ohlc)
    except Exception as exc:  # noqa: BLE001 - fail closed on a malformed provider body
        return {**refusal, "reason_codes": ["OHLC_BODY_REJECTED", type(exc).__name__]}
    series = index_capability.build_index_return_series(
        BENCHMARK_ID, raw_ohlc, fetch_provenance={"query_sent": sent} if sent else None,
    )
    if series.get("index_level_unit") != index_capability.INDEX_LEVEL_UNIT_QUALIFIED:
        return {**refusal, "reason_codes": ["INDEX_LEVEL_UNIT_UNQUALIFIED"]}
    if normalized.get("dropped_sessions"):
        return {**refusal, "reason_codes": ["DROPPED_SESSION_IN_WINDOW"]}
    bars = list(normalized["observations"])
    by_date = {row["session_date"]: row for row in bars}
    current = by_date.get(session)
    if current is None:
        return {**refusal, "reason_codes": ["SESSION_BAR_ABSENT"]}
    earlier = [row for row in bars if row["session_date"] < session]
    if not earlier:
        return {**refusal, "reason_codes": ["PREVIOUS_BAR_ABSENT"]}
    previous = earlier[-1]
    if not _gap_allowed(session, previous["session_date"]):
        return {**refusal, "reason_codes": ["PREVIOUS_BAR_GAP_UNEXPLAINED_NO_HOLIDAY_CALENDAR"],
                "previous_returned_session": previous["session_date"]}
    if not (index_capability.ohlc_internally_consistent(current) and index_capability.ohlc_internally_consistent(previous)):
        return {**refusal, "reason_codes": ["OHLC_INTERNALLY_INCONSISTENT"]}
    close, prev_close = float(current["close"]), float(previous["close"])
    if not (_in_range(close) and _in_range(prev_close)):
        return {**refusal, "reason_codes": ["LEVEL_OUTSIDE_QUALIFIED_POINT_RANGE"]}
    published = {row["session_date"]: row["close_level"] for row in series.get("observations") or []}
    if published.get(session) != close or published.get(previous["session_date"]) != prev_close:
        return {**refusal, "reason_codes": ["SERIES_CLOSE_DIVERGED_FROM_NORMALIZED_BAR"]}
    if _vn_date(knowledge_available_at) is None:
        return {**refusal, "reason_codes": ["KNOWLEDGE_TIME_UNPARSEABLE"]}
    source_identity = "dnse_index_return_series/" + _hash({"query": sent, "raw_ohlc": {
        key: list(raw_ohlc.get(key) or []) for key in ("o", "h", "l", "c", "t")}})
    benchmark = {
        "index": BENCHMARK_ID, "session": session, "close": close, "previous_close": prev_close,
        "previous_session": previous["session_date"], "source_identity": source_identity,
        "knowledge_available_at": knowledge_available_at, "authority": AUTHORITY,
        "unit": index_capability.INDEX_LEVEL_UNIT_QUALIFIED,
        "evidence_class": EVIDENCE_CLASS,
        "previous_session_basis": "PREVIOUS_RETURNED_DNSE_BAR_WEEKDAY_OR_WEEKEND_GAP_ONLY",
        "hose_administrator": False, "pit_backtest_eligible": False,
        "constituent_average": "NOT_PERMITTED", "vn_stock_db_used": False,
    }
    return {"contract_version": CONTRACT_VERSION, "status": "QUALIFIED", "session": session,
            "reason_codes": [], "benchmark": benchmark, "source_identity": source_identity}


def retained_dir(root: Path | None = None) -> Path | None:
    if root is not None:
        return Path(root) / RETAINED_DIR_NAME
    configured = os.environ.get(RETAINED_ROOT_ENV, "").strip()
    if not configured:
        return None
    return Path(configured) / RETAINED_DIR_NAME


def write_retained(record: Mapping[str, Any], *, root: Path | None = None) -> Path:
    folder = retained_dir(root)
    if folder is None:
        raise VnIndexSessionLevelError("RETAINED_ROOT_UNCONFIGURED")
    session = str(record.get("session") or "")
    if not session:
        raise VnIndexSessionLevelError("SESSION_MISSING")
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{session}.json"
    payload = _canonical(record) + "\n"
    if path.exists() and path.read_text(encoding="utf-8") != payload:
        raise VnIndexSessionLevelError("RETAINED_SESSION_LEVEL_CONTENT_CONFLICT")
    path.write_text(payload, encoding="utf-8", newline="\n")
    return path


def load_session_benchmark(session: str, *, root: Path | None = None) -> dict[str, Any] | None:
    """Return a benchmark only when this capture was known on that session date."""
    folder = retained_dir(root)
    if folder is None:
        return None
    path = folder / f"{session}.json"
    if not path.is_file():
        return None
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(record, Mapping):
        return None
    qualified = qualify_session_level(
        record.get("raw_ohlc") or {}, session=session,
        knowledge_available_at=str(record.get("knowledge_available_at") or ""),
        query=record.get("query") if isinstance(record.get("query"), Mapping) else {},
    )
    if qualified.get("status") != "QUALIFIED":
        return None
    benchmark = qualified["benchmark"]
    if _vn_date(benchmark["knowledge_available_at"]) != session:
        return None
    return benchmark


def capture_current_session(
    *,
    session: str,
    now: datetime,
    raw_ohlc: Mapping[str, Any] | None = None,
    query: Mapping[str, Any] | None = None,
    root: Path | None = None,
    fetcher=None,
) -> dict[str, Any]:
    """One bounded VNINDEX 1D capture for the Vietnam date of ``now``.

    ``fetcher`` is a test seam. The live path issues exactly one OHLC GET on
    the qualified index route. A miss never raises into Daily.
    """
    if now.astimezone(VN_TZ).date().isoformat() != session:
        return {"status": "SKIPPED", "reason_code": "SESSION_IS_NOT_CURRENT_VN_DATE", "http_requests": 0}
    if retained_dir(root) is None:
        return {"status": "SKIPPED", "reason_code": "RETAINED_ROOT_UNCONFIGURED", "http_requests": 0}
    window_start = date.fromordinal(date.fromisoformat(session).toordinal() - 14).isoformat()
    from datetime import datetime as _dt
    start = _dt.strptime(window_start, "%Y-%m-%d").replace(tzinfo=VN_TZ)
    end = _dt.strptime(session, "%Y-%m-%d").replace(tzinfo=VN_TZ)
    from datetime import timedelta
    sent = {"type": "INDEX", "symbol": BENCHMARK_ID, "resolution": "1D",
            "from": int(start.timestamp()), "to": int((end + timedelta(days=1) - timedelta(seconds=1)).timestamp())}
    http_requests = 0
    if raw_ohlc is None:
        if fetcher is None:
            fetcher = _live_fetch
        fetched = fetcher(sent)
        http_requests = int(fetched.get("http_requests") or 0)
        if not fetched.get("ok"):
            return {"status": "UNAVAILABLE", "reason_code": fetched.get("error_code") or "FETCH_FAILED",
                    "http_requests": http_requests}
        raw_ohlc = fetched.get("body") or {}
        sent = fetched.get("query") or sent
    knowledge = now.astimezone(VN_TZ).isoformat(timespec="seconds")
    qualified = qualify_session_level(raw_ohlc, session=session, knowledge_available_at=knowledge, query=query or sent)
    if qualified.get("status") != "QUALIFIED":
        return {"status": "REFUSED", "reason_codes": qualified.get("reason_codes"), "http_requests": http_requests}
    record = {"contract_version": CONTRACT_VERSION, "session": session, "knowledge_available_at": knowledge,
              "query": dict(query or sent), "raw_ohlc": {key: list(raw_ohlc.get(key) or []) for key in ("o", "h", "l", "c", "t")},
              "benchmark": qualified["benchmark"], "http_requests": http_requests}
    path = write_retained(record, root=root)
    return {"status": "RETAINED", "reason_code": None, "path": str(path), "http_requests": http_requests,
            "source_identity": qualified["source_identity"]}


def _live_fetch(query: Mapping[str, Any]) -> dict[str, Any]:
    from dnse_access import credential_status, credentials_for_request
    from dnse_secrets_env import ensure_credentials_loaded
    from stocklookup_core.acquisition.dnse_bulk_market_data import fetch_capability_raw

    ensure_credentials_loaded()
    status = credential_status()
    if not status.get("configured"):
        return {"ok": False, "error_code": "DNSE_CREDENTIALS_ABSENT", "http_requests": 0, "query": dict(query)}
    api_key, api_secret = credentials_for_request()
    response = fetch_capability_raw("ohlc", api_key=api_key, api_secret=api_secret, query=dict(query))
    return {"ok": bool(response.get("ok")), "error_code": response.get("error_code"), "body": response.get("body"),
            "http_requests": 1, "query": dict(query)}
