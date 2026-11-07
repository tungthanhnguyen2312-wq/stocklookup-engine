from datetime import datetime

from vn_time import VN_TZ

from stocklookup_core.evidence import dnse_vnindex_session_level as level


def _epoch(day: str) -> int:
    y, m, d = (int(x) for x in day.split("-"))
    return int(datetime(y, m, d, 15, 0, tzinfo=VN_TZ).timestamp())


def _bars(dates, closes):
    return {
        "o": [c - 1 for c in closes],
        "h": [c + 1 for c in closes],
        "l": [c - 2 for c in closes],
        "c": list(closes),
        "t": [_epoch(d) for d in dates],
    }


QUERY = {"type": "INDEX", "symbol": "VNINDEX", "resolution": "1D"}


def test_friday_session_uses_previous_returned_bar_not_constituents():
    raw = _bars(["2026-11-05", "2026-11-06"], [1740.73, 1725.36])
    out = level.qualify_session_level(raw, session="2026-11-06", knowledge_available_at="2026-11-06T15:05:00+07:00", query=QUERY)
    assert out["status"] == "QUALIFIED"
    bench = out["benchmark"]
    assert bench["close"] == 1725.36 and bench["previous_close"] == 1740.73
    assert bench["previous_session"] == "2026-11-05"
    assert bench["authority"] == level.AUTHORITY
    assert bench["vn_stock_db_used"] is False
    assert bench["constituent_average"] == "NOT_PERMITTED"


def test_holiday_gap_is_refused():
    raw = _bars(["2026-11-04", "2026-11-06"], [1740.0, 1725.0])
    out = level.qualify_session_level(raw, session="2026-11-06", knowledge_available_at="2026-11-06T15:05:00+07:00", query=QUERY)
    assert out["status"] == "REFUSED"
    assert "PREVIOUS_BAR_GAP_UNEXPLAINED_NO_HOLIDAY_CALENDAR" in out["reason_codes"]


def test_weekend_gap_is_allowed():
    raw = _bars(["2026-11-06", "2026-11-09"], [1725.36, 1730.0])
    out = level.qualify_session_level(raw, session="2026-11-09", knowledge_available_at="2026-11-09T15:05:00+07:00", query=QUERY)
    assert out["status"] == "QUALIFIED"
    assert out["benchmark"]["previous_session"] == "2026-11-06"


def test_later_capture_does_not_bind_to_the_sealed_session(tmp_path):
    raw = _bars(["2026-11-05", "2026-11-06"], [1740.73, 1725.36])
    now = datetime(2026, 11, 7, 10, 0, tzinfo=VN_TZ)
    captured = level.capture_current_session(session="2026-11-06", now=now, raw_ohlc=raw, query=QUERY, root=tmp_path)
    assert captured["status"] == "SKIPPED"
    captured = level.capture_current_session(
        session="2026-11-06", now=datetime(2026, 11, 6, 15, 5, tzinfo=VN_TZ),
        raw_ohlc=raw, query=QUERY, root=tmp_path,
    )
    assert captured["status"] == "RETAINED" and captured["http_requests"] == 0
    assert level.load_session_benchmark("2026-11-06", root=tmp_path)["close"] == 1725.36
    # A file rewritten with a next-day knowledge time must not bind.
    path = tmp_path / level.RETAINED_DIR_NAME / "2026-11-06.json"
    text = path.read_text(encoding="utf-8").replace("2026-11-06T15:05:00+07:00", "2026-11-07T10:00:00+07:00")
    path.write_text(text, encoding="utf-8")
    assert level.load_session_benchmark("2026-11-06", root=tmp_path) is None


def test_stock_symbol_query_is_refused():
    raw = _bars(["2026-11-05", "2026-11-06"], [20.0, 21.0])
    out = level.qualify_session_level(
        raw, session="2026-11-06", knowledge_available_at="2026-11-06T15:05:00+07:00",
        query={"type": "STOCK", "symbol": "HPG", "resolution": "1D"},
    )
    assert out["reason_codes"] == ["QUERY_NOT_THE_QUALIFIED_VNINDEX_1D_ROUTE"]
