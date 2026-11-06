import json
import unittest
from datetime import date, timedelta

from stocklookup_core.tactical import current_session_candlestick_projection as projection

SESSION = "2026-11-05"
BASIS = "CURRENT_DESCRIPTIVE_DNSE_REST_ADJUSTED_RETROSPECTIVE_RAW_AS_TRADED_NOT_PROMOTED"


def sessions(count, end=SESSION):
    out, day = [], date.fromisoformat(end)
    while len(out) < count:
        if day.weekday() < 5:
            out.append(day.isoformat())
        day -= timedelta(days=1)
    return list(reversed(out))


def obs(session, o, h, l, c, v=1000, basis=BASIS, qualification=projection.QUALIFIED):
    return {"session": session, "open": o, "high": h, "low": l, "close": c, "volume": v,
            "price_basis": basis, "qualification": qualification, "dataset": projection.DATASET}


def flat_series(count=60, end=SESSION):
    rows = []
    for s in sessions(count, end):  # identical 60%-body candles: no registered pattern fires
        rows.append(obs(s, 19.8, 20.5, 19.5, 20.4))
    return rows


def engulfing_series():
    """Down-trend then a large bullish engulfing candle on SESSION."""
    days = sessions(40)
    rows = []
    price = 30.0
    for s in days[:-1]:
        rows.append(obs(s, price + 0.2, price + 0.4, price - 0.4, price - 0.2))
        price -= 0.3
    prev = rows[-1]
    rows.append(obs(days[-1], prev["close"] - 0.3, prev["open"] + 0.8, prev["close"] - 0.4, prev["open"] + 0.6, v=5000))
    return rows


def snapshot(records, session=SESSION):
    return {"contract_version": projection.SOURCE_CONTRACT, "target_session": session,
            "resolved_completed_session": session, "retained_snapshot_session": session,
            "snapshot_identity": "p3f9_exact_session_snapshot:test", "snapshot_sha256": "test",
            "records": {t: {"observations": o} for t, o in records.items()}}


class CurrentSessionCandlestickProjectionTest(unittest.TestCase):
    def build(self, records):
        return projection.build_projection(snapshot(records), session=SESSION)

    def test_pattern_present_and_absent_and_exclusions(self):
        mixed = flat_series()
        mixed[0] = dict(mixed[0], price_basis="OTHER_BASIS")
        bad = flat_series()
        bad[-1] = dict(bad[-1], high=1.0)  # high below close on the session bar
        payload = self.build({
            "ENG": engulfing_series(),
            "FLAT": flat_series(),
            "STALE": flat_series(end="2026-11-04"),
            "MIX": mixed,
            "BAD": bad,
            "NOQ": [obs(s, 1, 2, 0.5, 1.5, qualification="OTHER") for s in sessions(30)],
            "SHORT": flat_series(count=5),
        })
        tickers = payload["tickers"]
        self.assertEqual(tickers["STALE"], {"status": "EXCLUDED", "reason_code": "NO_EXACT_SESSION_BAR"})
        self.assertEqual(tickers["MIX"]["reason_code"], "MIXED_PRICE_BASIS")
        self.assertEqual(tickers["BAD"]["reason_code"], "MISSING_OR_INVALID_OHLC")
        self.assertEqual(tickers["NOQ"]["reason_code"], "NO_QUALIFIED_OBSERVATION")
        self.assertEqual(tickers["SHORT"]["reason_code"], "INSUFFICIENT_HISTORY")
        self.assertEqual(tickers["ENG"]["status"], "CONFIRMED_1D_PATTERN_ON_SESSION")
        eng = [p for p in payload["patterns"] if p["ticker"] == "ENG" and p["timeframe"] == "1D" and p["bars_ago"] == 0]
        self.assertIn("bullish_engulfing", {p["pattern_key"] for p in eng})
        row = next(p for p in eng if p["pattern_key"] == "bullish_engulfing")
        self.assertEqual(row["confirmation_state"], "CONFIRMED_PERIOD_CLOSED")
        self.assertEqual(row["invalidation"]["rule"], "CLOSE_BELOW_PATTERN_LOW")
        self.assertEqual(row["volume_confirmation"], "VOLUME_ABOVE_20_SESSION_AVERAGE")
        self.assertIsNone(row["gtgd20_ty"])
        self.assertNotIn("low_liquidity", row["warnings"])
        self.assertEqual(tickers["FLAT"]["status"], "NO_PATTERN_DETECTED")
        self.assertEqual(tickers["FLAT"]["pattern_count"], 0)
        self.assertEqual(tickers["FLAT"]["indicators"]["bars_1d"], 60)
        self.assertEqual(tickers["FLAT"]["history"]["1D"]["status"], "PARTIAL_HISTORY")
        cov = payload["coverage"]
        self.assertEqual((cov["scanned_count"], cov["excluded_count"]), (2, 5))
        self.assertFalse(payload["authority_boundary"]["is_trade_signal"])
        self.assertEqual(payload["scan_date"], SESSION)
        self.assertEqual(payload["source_session"], SESSION)

    def test_weekly_bar_is_forming_before_week_close(self):
        payload = self.build({"ENG": engulfing_series()})
        weekly = [p for p in payload["patterns"] if p["timeframe"] == "1W" and p["bars_ago"] == 0]
        for row in weekly:  # 2026-11-05 is a Thursday: the week is not closed
            self.assertEqual(row["confirmation_state"], "FORMING_PERIOD_OPEN")

    def test_source_session_mismatch_refused(self):
        snap = snapshot({"ENG": engulfing_series()})
        snap["resolved_completed_session"] = "2026-11-04"
        with self.assertRaises(projection.CandlestickProjectionError):
            projection.build_projection(snap, session=SESSION)
        snap = snapshot({"ENG": engulfing_series()})
        snap["contract_version"] = "other"
        with self.assertRaises(projection.CandlestickProjectionError):
            projection.build_projection(snap, session=SESSION)

    def test_component_state_freshness_and_identity(self):
        payload = self.build({"ENG": engulfing_series()})
        state = projection.component_state(payload, SESSION)
        self.assertEqual(state["status"], "CURRENT")
        self.assertEqual(state["source_session"], SESSION)
        self.assertEqual(projection.component_state(payload, "2026-11-06")["status"], "STALE")
        tampered = json.loads(json.dumps(payload))
        tampered["patterns"] = []
        self.assertEqual(projection.component_state(tampered, SESSION)["reason_codes"],
                         ["CANDLESTICK_PROJECTION_IDENTITY_MISMATCH"])
        legacy = {"schema_version": 1, "scan_date": "2026-08-25", "patterns": []}
        self.assertEqual(projection.component_state(legacy, SESSION)["status"], "UNAVAILABLE_FOR_CURRENT_SESSION")

    def test_projection_is_deterministic(self):
        records = {"ENG": engulfing_series(), "FLAT": flat_series()}
        a = projection.build_projection(snapshot(records), session=SESSION)
        b = projection.build_projection(snapshot(records), session=SESSION)
        self.assertEqual(a["projection_identity"], b["projection_identity"])


class TickerStatusTest(unittest.TestCase):
    def test_closed_higher_timeframe_period_is_confirmed_not_forming(self):
        d1 = {"timeframe": "1D", "status": "completed", "bars_ago": 0}
        w_closed = {"timeframe": "1W", "status": "completed", "bars_ago": 0}
        m_open = {"timeframe": "1M", "status": "forming", "bars_ago": 0}
        old = {"timeframe": "1D", "status": "completed", "bars_ago": 3}
        self.assertEqual(projection.ticker_status([d1, m_open]), "CONFIRMED_1D_PATTERN_ON_SESSION")
        self.assertEqual(projection.ticker_status([w_closed, m_open]), "CONFIRMED_HIGHER_TIMEFRAME_ON_SESSION")
        self.assertEqual(projection.ticker_status([m_open, old]), "FORMING_HIGHER_TIMEFRAME_ONLY")
        self.assertEqual(projection.ticker_status([old]), "RECENT_PATTERN_ONLY")
        self.assertEqual(projection.ticker_status([]), "NO_PATTERN_DETECTED")


class PublishDashboardCandlestickDomainTest(unittest.TestCase):
    def test_manifest_domain_current_stale_legacy_absent(self):
        import tempfile
        from pathlib import Path
        from unittest import mock
        import publish_dashboard

        payload = projection.build_projection(snapshot({"ENG": engulfing_series()}), session=SESSION)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "data").mkdir()
            with mock.patch.object(publish_dashboard, "WEB_ROOT", root),                     mock.patch.object(publish_dashboard, "BACKEND_ROOT", root / "absent-backend"):
                self.assertIsNone(publish_dashboard.candlestick_signal_domain(SESSION))
                (root / "data" / "candlestick_patterns.json").write_text(json.dumps(payload), encoding="utf-8")
                current = publish_dashboard.candlestick_signal_domain(SESSION)
                self.assertEqual(current["status"], "CURRENT")
                self.assertEqual(current["components"]["candlestick_patterns"]["source_session"], SESSION)
                stale = publish_dashboard.candlestick_signal_domain("2026-11-06")
                self.assertEqual(stale["status"], "STALE")
                self.assertEqual(stale["components"]["candlestick_patterns"]["reason_codes"], ["SIGNAL_SOURCE_SESSION_MISMATCH"])
                (root / "data" / "candlestick_patterns.json").write_text(
                    json.dumps({"schema_version": 1, "scan_date": "2026-08-25", "patterns": []}), encoding="utf-8")
                legacy = publish_dashboard.candlestick_signal_domain(SESSION)
                self.assertNotEqual(legacy["status"], "CURRENT")
                self.assertIsNone(legacy["source_session"])

    def test_manifest_attests_the_backend_sidecar_this_run_will_copy(self):
        """compute_manifest runs before copy_public_artifacts(): the domain must describe the
        BACKEND_ROOT sidecar about to be served, not the previous release left in WEB_ROOT."""
        import tempfile
        from pathlib import Path
        from unittest import mock
        import publish_dashboard

        payload = projection.build_projection(snapshot({"ENG": engulfing_series()}), session=SESSION)
        legacy = {"schema_version": 1, "scan_date": "2026-08-25", "patterns": []}
        with tempfile.TemporaryDirectory() as tmp:
            web, backend = Path(tmp) / "web", Path(tmp) / "backend"
            for root in (web, backend):
                (root / "data").mkdir(parents=True)
            (web / "data" / "candlestick_patterns.json").write_text(json.dumps(legacy), encoding="utf-8")
            (backend / "data" / "candlestick_patterns.json").write_text(json.dumps(payload), encoding="utf-8")
            with mock.patch.object(publish_dashboard, "WEB_ROOT", web),                     mock.patch.object(publish_dashboard, "BACKEND_ROOT", backend):
                self.assertEqual(publish_dashboard.candlestick_signal_domain(SESSION)["status"], "CURRENT")
                (backend / "data" / "candlestick_patterns.json").write_text(json.dumps(legacy), encoding="utf-8")
                (web / "data" / "candlestick_patterns.json").write_text(json.dumps(payload), encoding="utf-8")
                self.assertNotEqual(publish_dashboard.candlestick_signal_domain(SESSION)["status"], "CURRENT")


if __name__ == "__main__":
    unittest.main()
