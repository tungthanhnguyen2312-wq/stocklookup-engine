"""Current-session candlestick projection over the retained exact-session market snapshot.

Why this exists: the legacy ``candle_scan.py`` reads ``vn_stock.db`` OHLCV, which stopped at
2026-08-25, so ``data/candlestick_patterns.json`` stayed frozen at that scan date and the
Dashboard correctly refused it. The Daily already retains a session-bound DNSE 1D OHLCV
window per ticker in the P3F9B exact-session snapshot. This bridge feeds exactly those
qualified observations into the existing detector (``candlestick_patterns.build_snapshot``);
it adds no pattern logic of its own.

Boundaries:
* Descriptive research context only. Never a buy/sell signal, rank, probability or target.
* A ticker enters the scan only with an exact-session bar for ``session`` and one price basis
  across its window; otherwise it is excluded with an explicit reason code.
* The provider price unit is undocumented, so traded value (GTGD) is never computed.
"""
from __future__ import annotations

import hashlib
import json
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Mapping

import pandas as pd

from stocklookup_core.tactical import candlestick_patterns as engine

CONTRACT_VERSION = "current_session_candlestick_projection/v1"
SOURCE_CONTRACT = "p3f9_exact_session_mva_snapshot/v2"
QUALIFIED = "CURRENT_MARKET_DESCRIPTIVE_QUALIFIED_ONLY"
DATASET = "DNSE_OHLC_1D"
ICT = timezone(timedelta(hours=7))
#: Minimum completed bars per timeframe for the engine's own default lookback context.
FULL_HISTORY_BARS = {"1D": 210, "1W": 60, "1M": 24}

REASONS = (
    "NO_EXACT_SESSION_BAR",
    "MISSING_OR_INVALID_OHLC",
    "MIXED_PRICE_BASIS",
    "NO_QUALIFIED_OBSERVATION",
    "INSUFFICIENT_HISTORY",
)

AUTHORITY_BOUNDARY = {
    "is_actionable": False,
    "is_trade_signal": False,
    "no_probability": True,
    "no_rank": True,
    "no_target_price": True,
    "PIT": "BLOCKED",
    "RAW_AS_TRADED": "NOT_PROMOTED",
    "use": "DESCRIPTIVE_TECHNICAL_RESEARCH_CONTEXT_ONLY",
}

LIMITATIONS = (
    "PRICE_BASIS_ADJUSTED_RETROSPECTIVE_NOT_RAW_AS_TRADED",
    "PROVIDER_PRICE_UNIT_UNDOCUMENTED_TRADED_VALUE_NOT_COMPUTED",
    "VOLUME_IS_TOTAL_MATCHED_VOLUME_NOT_ACTIVE_BUY_SELL",
    "WEEKLY_MONTHLY_LIMITED_TO_RETAINED_WINDOW",
    "PATTERN_IS_NOT_A_TRADE_SIGNAL",
)


class CandlestickProjectionError(ValueError):
    """Raised when the source snapshot cannot bind to the requested session."""


def _session_close(session: str) -> datetime:
    # 15:15 ICT: after HOSE close; makes the week ending on a Friday session complete.
    day = datetime.strptime(session, "%Y-%m-%d")
    return day.replace(hour=15, minute=15, tzinfo=ICT)


def verify_source(snapshot: Mapping[str, Any], session: str) -> None:
    if snapshot.get("contract_version") != SOURCE_CONTRACT:
        raise CandlestickProjectionError("SOURCE_CONTRACT_MISMATCH")
    for key in ("target_session", "resolved_completed_session", "retained_snapshot_session"):
        if snapshot.get(key) != session:
            raise CandlestickProjectionError(f"SOURCE_SESSION_MISMATCH:{key}")
    if not isinstance(snapshot.get("records"), dict):
        raise CandlestickProjectionError("SOURCE_RECORDS_MISSING")


def _valid_ohlc(obs: Mapping[str, Any]) -> bool:
    try:
        o, h, l, c = (float(obs[k]) for k in ("open", "high", "low", "close"))
    except (KeyError, TypeError, ValueError):
        return False
    if min(o, h, l, c) <= 0:
        return False
    return h >= max(o, c, l) and l <= min(o, c, h)


def extract_ticker_bars(record: Mapping[str, Any], session: str) -> tuple[pd.DataFrame | None, str | None, str | None]:
    """Return (daily bars, exclusion reason, price basis) for one snapshot record."""
    observations = [o for o in (record.get("observations") or []) if isinstance(o, Mapping)]
    qualified = [o for o in observations if o.get("qualification") == QUALIFIED and o.get("dataset") == DATASET]
    if not qualified:
        return None, "NO_QUALIFIED_OBSERVATION", None
    if not any(o.get("session") == session for o in qualified):
        return None, "NO_EXACT_SESSION_BAR", None
    window = [o for o in qualified if str(o.get("session", "")) <= session]
    bases = {o.get("price_basis") for o in window}
    if len(bases) != 1 or None in bases:
        return None, "MIXED_PRICE_BASIS", None
    exact = [o for o in window if o.get("session") == session]
    if not all(_valid_ohlc(o) for o in exact):
        return None, "MISSING_OR_INVALID_OHLC", None
    rows = [{"date": o["session"], "open": o["open"], "high": o["high"], "low": o["low"],
             "close": o["close"], "volume": o.get("volume")} for o in window if _valid_ohlc(o)]
    frame = engine.prepare_ohlcv(pd.DataFrame(rows))
    if len(frame) < 8:
        return None, "INSUFFICIENT_HISTORY", None
    return frame, None, next(iter(bases))


def _indicator_state(frame: pd.DataFrame) -> dict[str, Any]:
    """Last-bar readings from the engine's own feature set (no new indicator math)."""
    features = engine._features(frame, prepared=True, liquidity_value_unit_documented=False)
    last = features.iloc[-1]
    close = engine.safe_number(last.get("close"), default=float("nan"))

    def num(key: str, digits: int = 4) -> Any:
        return engine.safe_nullable(last.get(key), digits)

    def side(level_key: str) -> str | None:
        level = last.get(level_key)
        if level is None or pd.isna(level):
            return None
        return "ABOVE" if close >= float(level) else "BELOW"

    return {
        "close": num("close"), "sma50": num("sma50"), "sma200": num("sma200"),
        "close_vs_sma50": side("sma50"), "close_vs_sma200": side("sma200"),
        "rsi14": num("rsi14", 2), "macd_hist": num("macd_hist"),
        "bb_upper": num("bb_upper"), "bb_lower": num("bb_lower"), "atr14": num("atr14"),
        "relative_volume_20": num("rel_vol_calc", 2),
        "bars_1d": int(len(frame)),
    }


def _history_state(frame: pd.DataFrame, as_of: datetime) -> dict[str, Any]:
    out = {}
    for timeframe in engine.TIMEFRAMES:
        bars = engine.resample_ohlcv(frame, timeframe, as_of, prepared=True)
        completed = int(bars["is_complete"].sum()) if not bars.empty else 0
        out[timeframe] = {
            "completed_bars": completed,
            "status": "FULL_CONTEXT" if completed >= FULL_HISTORY_BARS[timeframe] else "PARTIAL_HISTORY",
        }
    return out


def _invalidation(pattern: Mapping[str, Any], frame: pd.DataFrame, as_of: datetime) -> dict[str, Any] | None:
    bars = engine.resample_ohlcv(frame, pattern["timeframe"], as_of, prepared=True)
    if bars.empty:
        return None
    end = bars.index[bars["date"].dt.strftime("%Y-%m-%d") == pattern.get("detected_at")]
    if not len(end):
        return None
    stop = int(end[-1])
    width = max(1, int((pattern.get("pattern_metadata") or {}).get("bars_required") or 1))
    span = bars.iloc[max(0, stop - width + 1): stop + 1]
    low, high = float(span["low"].min()), float(span["high"].max())
    direction = pattern.get("direction")
    if direction == "bullish":
        return {"rule": "CLOSE_BELOW_PATTERN_LOW", "level": round(low, 4)}
    if direction == "bearish":
        return {"rule": "CLOSE_ABOVE_PATTERN_HIGH", "level": round(high, 4)}
    return {"rule": "CLOSE_OUTSIDE_PATTERN_RANGE", "low": round(low, 4), "high": round(high, 4)}


def _trend_alignment(pattern: Mapping[str, Any], indicators: Mapping[str, Any]) -> str:
    vs = indicators.get("close_vs_sma50")
    direction = pattern.get("direction")
    if vs is None or direction not in ("bullish", "bearish"):
        return "TREND_CONTEXT_UNAVAILABLE" if vs is None else "NEUTRAL_PATTERN"
    with_trend = (direction == "bullish" and vs == "ABOVE") or (direction == "bearish" and vs == "BELOW")
    return "ALIGNED_WITH_SMA50_SIDE" if with_trend else "AGAINST_SMA50_SIDE"


def _volume_confirmation(pattern: Mapping[str, Any]) -> str:
    rel = pattern.get("rel_vol")
    if rel is None:
        return "VOLUME_CONTEXT_UNAVAILABLE"
    if rel >= 1.2:
        return "VOLUME_ABOVE_20_SESSION_AVERAGE"
    if rel < 0.8:
        return "VOLUME_BELOW_20_SESSION_AVERAGE"
    return "VOLUME_NEAR_20_SESSION_AVERAGE"


TICKER_STATUSES = (
    "CONFIRMED_1D_PATTERN_ON_SESSION",
    "FORMING_HIGHER_TIMEFRAME_ONLY",
    "RECENT_PATTERN_ONLY",
    "NO_PATTERN_DETECTED",
    "EXCLUDED",
)


def ticker_status(found: list[Mapping[str, Any]]) -> str:
    latest = [p for p in found if p.get("bars_ago") == 0]
    if any(p.get("timeframe") == "1D" and p.get("status") == "completed" for p in latest):
        return "CONFIRMED_1D_PATTERN_ON_SESSION"
    if latest:
        return "FORMING_HIGHER_TIMEFRAME_ONLY"
    return "RECENT_PATTERN_ONLY" if found else "NO_PATTERN_DETECTED"


def build_projection(snapshot: Mapping[str, Any], *, session: str, generated_at: datetime | None = None,
                     tickers: list[str] | None = None, workers: int = 1) -> dict[str, Any]:
    verify_source(snapshot, session)
    as_of = _session_close(session)
    generated_at = generated_at or datetime.now(ICT)
    allowed = set(tickers) if tickers else None
    frames: dict[str, pd.DataFrame] = {}
    bases: dict[str, str] = {}
    exclusions: dict[str, str] = {}
    for ticker in sorted(snapshot["records"]):
        if allowed is not None and ticker not in allowed:
            continue
        frame, reason, basis = extract_ticker_bars(snapshot["records"][ticker], session)
        if reason:
            exclusions[ticker] = reason
        else:
            frames[ticker] = frame
            bases[ticker] = basis
    if frames:
        market = pd.concat([f.assign(ticker=t) for t, f in frames.items()], ignore_index=True)
        scan = engine.build_snapshot(market, scan_date=session, generated_at=as_of, workers=workers,
                                     liquidity_value_unit_documented=False)
        scan["config"]["workers"] = None  # execution detail, not content
    else:
        scan = engine.build_snapshot(pd.DataFrame(columns=["ticker", "date", "open", "high", "low", "close", "volume"]),
                                     scan_date=session, generated_at=as_of, liquidity_value_unit_documented=False)
    per_ticker: dict[str, dict[str, Any]] = {}
    indicators = {t: _indicator_state(f) for t, f in frames.items()}
    by_ticker: dict[str, list[dict]] = {}
    for pattern in scan["patterns"]:
        ticker = pattern["ticker"]
        pattern["warnings"] = [w for w in pattern.get("warnings", []) if w != "low_liquidity"]
        pattern["gtgd20_ty"] = None
        pattern["invalidation"] = _invalidation(pattern, frames[ticker], as_of)
        pattern["trend_alignment"] = _trend_alignment(pattern, indicators[ticker])
        pattern["volume_confirmation"] = _volume_confirmation(pattern)
        pattern["confirmation_state"] = "CONFIRMED_PERIOD_CLOSED" if pattern["status"] == "completed" else "FORMING_PERIOD_OPEN"
        by_ticker.setdefault(ticker, []).append(pattern)
    for ticker, frame in frames.items():
        found = by_ticker.get(ticker, [])
        per_ticker[ticker] = {
            "status": ticker_status(found),
            "latest_bar_session": frame["date"].iloc[-1].strftime("%Y-%m-%d"),
            "price_basis": bases[ticker],
            "history": _history_state(frame, as_of),
            "indicators": indicators[ticker],
            "pattern_count": len(found),
        }
    for ticker, reason in exclusions.items():
        per_ticker[ticker] = {"status": "EXCLUDED", "reason_code": reason}
    reason_counts = Counter(exclusions.values())
    status_counts = Counter(v["status"] for v in per_ticker.values())
    source = {
        "contract_version": snapshot.get("contract_version"),
        "snapshot_identity": snapshot.get("snapshot_identity"),
        "snapshot_sha256": snapshot.get("snapshot_sha256"),
        "dataset": DATASET,
        "qualification": QUALIFIED,
    }
    payload = {
        **scan,
        "source_type": "retained_exact_session_snapshot",
        "contract_version": CONTRACT_VERSION,
        "source_session": session,
        "as_of": as_of.isoformat(),
        "generated_at": generated_at.isoformat(),
        "source": source,
        "price_basis": sorted(set(bases.values())),
        "authority_boundary": AUTHORITY_BOUNDARY,
        "limitations": list(LIMITATIONS),
        "coverage": {
            "candidate_count": len(per_ticker),
            "scanned_count": len(frames),
            "excluded_count": len(exclusions),
            "exclusion_reasons": {r: reason_counts.get(r, 0) for r in REASONS},
            "ticker_status_counts": dict(sorted(status_counts.items())),
        },
        "tickers": per_ticker,
    }
    payload = engine.sanitize_json(payload)
    payload["projection_identity"] = projection_identity(payload)
    return payload


def projection_identity(payload: Mapping[str, Any]) -> str:
    body = {k: v for k, v in payload.items() if k not in ("projection_identity", "generated_at", "summary")}
    digest = hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()
    return f"{CONTRACT_VERSION}:{digest}"


def component_state(payload: Mapping[str, Any] | None, session: str) -> dict[str, Any]:
    """build_info ``domains.signals.components.candlestick_patterns`` entry for a publisher."""
    if not isinstance(payload, Mapping) or payload.get("contract_version") != CONTRACT_VERSION:
        return {"status": "UNAVAILABLE_FOR_CURRENT_SESSION", "source_session": None,
                "reason_codes": ["CANDLESTICK_PROJECTION_NOT_CURRENT_CONTRACT"]}
    if payload.get("projection_identity") != projection_identity(payload):
        return {"status": "UNAVAILABLE_FOR_CURRENT_SESSION", "source_session": None,
                "reason_codes": ["CANDLESTICK_PROJECTION_IDENTITY_MISMATCH"]}
    if payload.get("source_session") != session or payload.get("scan_date") != session:
        return {"status": "STALE", "source_session": payload.get("source_session"),
                "reason_codes": ["SIGNAL_SOURCE_SESSION_MISMATCH"]}
    return {"status": "CURRENT", "source_session": session, "freshness": "EXACT_SESSION",
            "projection_identity": payload["projection_identity"],
            "source_snapshot_identity": (payload.get("source") or {}).get("snapshot_identity"),
            "scanned_count": (payload.get("coverage") or {}).get("scanned_count"),
            "reason_codes": []}
