"""Network-free finite-list retention and real-fixture valuation replay."""
import csv
from datetime import datetime
import json

import pytest
import copy
import subprocess
import types

from stocklookup_core.evidence.official_document_acquisition import acquire, MANIFEST
from tools.retain_vsdc_share_notices import plan, main
from tools.replay_vsdc_valuation_impact import replay
from test_vsdc_hose_share_events import REGISTRATIONS, FIXTURES
from test_share_basis_official_event_staleness import _runtime, CUTOFF
from test_market_wide_current_valuation_input_scaleout import _corporate_facts
from stocklookup_core.evidence.official_source_registry import load_registry
import stocklookup_core.valuation.market_wide_current_valuation_input_scaleout as valuation


def spec(ticker="ZZZ", **overrides):
    return dict(ticker=ticker, source_id="vsdc", canonical_url="https://vsdc.vn/vi/ad/123",
                document_class="corporate_action_notice", reporting_period="2026") | overrides


def test_market_wide_list_cache_provenance_and_interval(tmp_path):
    calls, waits = [], []
    rows = [spec(ticker=t, canonical_url=f"https://vsdc.vn/vi/ad/{i}")
            for i, t in enumerate(("VDS", "SSB", "AAA", "ZZZ"), 1)]
    def fetch(url, **kwargs):
        calls.append(url)
        return 200, {"Content-Type": "text/html"}, b"<html>retained</html>", url
    result = acquire(iter(rows), tmp_path, vsdc_operator_notice_list=True, fetcher=fetch,
                     clock=lambda: 0, sleep=waits.append)
    assert len(calls) == 4 and waits == [15, 15, 15]
    assert all(r["state"] == "retained" for r in result["outcomes"])
    manifest = (tmp_path / MANIFEST).read_bytes()
    again = acquire(rows, tmp_path, vsdc_operator_notice_list=True,
                    fetcher=lambda *a, **k: pytest.fail("cached request"))
    assert all(r["state"] == "cached_valid" for r in again["outcomes"])
    assert (tmp_path / MANIFEST).read_bytes() == manifest


@pytest.mark.parametrize("override", [
    {"source_id": "issuer_ir"}, {"document_class": "audited_annual_financial_statements"},
    {"canonical_url": "http://vsdc.vn/vi/ad/123"},
    {"canonical_url": "https://vsdc.vn/vi/ad/123?q=1"},
    {"canonical_url": "https://vsdc.vn/vi/ad/123#x"},
    {"canonical_url": "https://vsdc.vn/vi/ad/123/"},
    {"canonical_url": "https://vsdc.vn.evil/vi/ad/123"},
    {"canonical_url": "https://vsdc.vn/vi/ad/not-a-number"},
    {"ticker": "../VDS"}, {"reporting_period": "2027"},
])
def test_whole_list_rejected_before_fetch_or_storage(tmp_path, override):
    destination = tmp_path / "must-not-exist"
    with pytest.raises(ValueError):
        acquire([spec(), spec(**override)], destination, vsdc_operator_notice_list=True,
                fetcher=lambda *a, **k: pytest.fail("network"))
    assert not destination.exists()


def test_legacy_scope_and_financial_cohort_unchanged(tmp_path):
    result = acquire([spec()], tmp_path, fetcher=lambda *a, **k: pytest.fail("network"))
    assert result["outcomes"][0]["state"] == "unsupported_request"
    with pytest.raises(ValueError, match="EXCLUSIVE"):
        acquire([spec()], tmp_path, vsdc_operator_notice_list=True, additional_allowed_tickers=["ZZZ"])
    with pytest.raises(ValueError, match="EMPTY"):
        acquire([], tmp_path, vsdc_operator_notice_list=True)


def test_market_wide_scope_still_requires_registry_admission(tmp_path):
    registry = copy.deepcopy(load_registry())
    registry["sources"] = [r for r in registry["sources"] if r["source_id"] != "vsdc"]
    with pytest.raises(ValueError, match="REGISTRY_REFUSED"):
        acquire([spec()], tmp_path / "absent", registry=registry, vsdc_operator_notice_list=True,
                fetcher=lambda *a, **k: pytest.fail("HTTP before admission"))
    assert not (tmp_path / "absent").exists()


def test_market_wide_scope_preserves_final_host_guard(tmp_path):
    result = acquire([spec()], tmp_path, vsdc_operator_notice_list=True,
        fetcher=lambda *a, **k: (200, {"Content-Type": "text/html"}, b"<html>bad host</html>",
                                "https://example.com/vi/ad/123"))
    assert result["outcomes"][0]["state"] == "redirect_refused_by_source_registry"
    assert json.loads((tmp_path / MANIFEST).read_text())["records"] == []


def write_csv(path, rows):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["ticker", "notice_kind", "url", "published", "title", "venue_from_crawl"])
        writer.writerows(rows)


def test_csv_dry_run_no_storage_no_http_and_all_errors(tmp_path, monkeypatch, capsys):
    import tools.retain_vsdc_share_notices as cli
    monkeypatch.setattr(cli, "acquire", lambda *a, **k: pytest.fail("HTTP forbidden"))
    path = tmp_path / "urls.csv"
    row = ["ZZZ", "registration_change", "https://vsdc.vn/vi/ad/123", "23/11/2026", "title", "HOSE"]
    write_csv(path, [row, ["AAA", "record_date_notice", "https://vsdc.vn/vi/ad/124", *row[3:]]])
    destination = tmp_path / "no-write"
    assert main(["--urls", str(path), "--destination", str(destination), "--dry-run"]) == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["planned_requests"] == 2 and summary["minimum_wall_seconds"] == 15
    requests, _ = plan(path)
    assert "published_at" not in requests[0]
    assert requests[0]["discovery_provenance"]["venue_from_crawl"] == "HOSE"
    assert not destination.exists()
    write_csv(path, [row, [*row[:2], "https://evil/123", *row[3:]],
                     [row[0], "bad_kind", *row[2:]], [*row[:3], "bad_date", *row[4:]]])
    _, summary = plan(path)
    assert len(summary["rejected_rows"]) == 3 and not summary["execution_allowed"]
    assert main(["--urls", str(path), "--destination", str(destination)]) == 2
    assert not destination.exists()


@pytest.mark.parametrize("case", REGISTRATIONS, ids=lambda c: c[0])
def test_four_retained_registration_fixtures_through_real_resolver_and_valuation(tmp_path, case, monkeypatch):
    ticker, number, digest, isin, change, count, published, reason = case
    t = ticker.upper()
    root = tmp_path / "notices"
    # Venue witness is synthetic linkage evidence, not a factual venue claim.
    witness = (FIXTURES / "bmi_202076_synthetic.html").read_bytes().replace(b"BMI", t.encode())
    witness = witness.replace(f"VN000000{t}0".encode(), isin.encode())
    payloads = {"https://vsdc.vn/vi/ad/" + number:
        (FIXTURES / f"{ticker}_{number}_registration_retained_20261124.html").read_bytes(),
        "https://vsdc.vn/vi/ad/999999": witness}
    rows = [spec(t, canonical_url=url,
                 document_class="corporate_action_notice" if url.endswith(number) else "last_registration_date_notice")
            for url in payloads]
    acquire(rows, root, vsdc_operator_notice_list=True, sleep=lambda _: None,
        fetcher=lambda url, **kw: (200, {"Content-Type": "text/html"}, payloads[url], url),
        observed_at="2026-11-24T01:00:00Z")
    runtime = _runtime(tmp_path / "runtime", [(t, 1000., "2026-08-14")])
    price = {"resolved_completed_session": "2026-11-23", "source": "DNSE", "records": {
        t: {"disposition": "EXACT_SESSION_RETAINED", "observations": [{"session": "2026-11-23", "close": 10}]}}}
    fundamental = {"records": {t: {"entity_class": "corporate", "authority_tier": "OFFICIAL_QUALIFIED",
                                  "metrics": [{"metric_id": "revenue"}]}}}
    p3e = {"refreshed_panel_data": {"issuers": [{"issuer_identity": {"ticker": t, "entity_type": "corporate"},
                                              "facts": _corporate_facts()}]}}
    kwargs = dict(evidence_roots=[root], runtime_root=runtime, known_by=CUTOFF, price=price,
                  fundamental=fundamental, shares={}, p3e=p3e)
    report = replay(**kwargs)
    assert report["changed_tickers"] == 1
    row = report["rows"][0]
    assert row["provider_shares"] == 1000 and row["vsdc_registered_shares"] == count
    assert row["authority_before"] == "provider_reported_lagged"
    assert row["authority_after"] == "official_registered_shares"
    assert row["notice_url"].endswith(number) and row["published_at"] == published
    basis = row["share_basis_after"]
    assert basis["share_basis"] == "VSDC_REGISTERED_SHARES"
    assert basis["share_concept"] == "ISSUED_SHARES"
    assert basis["status"] == "OFFICIAL_REGISTERED_SHARES"
    assert basis["observation_date"] == published
    assert basis["authoritative_current_market_cap_eligible"] is False
    assert "includes treasury shares" in basis["limitations"][0]
    assert "not outstanding ex-treasury" in basis["limitations"][0]
    assert "not a listing effective date" in basis["limitations"][0]
    assert row["shares_percent_change"] == pytest.approx((count - 1000) / 1000 * 100)
    for name, metric in row["metrics"].items():
        if name == "EV/EBITDA":
            assert metric["status_after"] == "BLOCKED" and metric["after"] is None
            continue
        assert metric["status_before"] == "RESEARCH_USABLE"
        assert metric["status_after"] == "RESEARCH_USABLE"
        if name in {"enterprise_value", "EV/Sales"}:
            expected = 10_000 * count + 50 - 20
            if name == "EV/Sales":
                expected /= 200
        else:
            expected = 10_000 * count / {"market_cap": 1, "P/E": 10, "P/B": 100, "P/S": 200}[name]
        assert metric["after"] == pytest.approx(expected)
        assert metric["percent_change"] == pytest.approx((expected - metric["before"]) / abs(metric["before"]) * 100)

    # Capture the real ON artifact to verify labels on every metric, including blocked ones.
    captured = []
    original = valuation.build_current_valuation_artifact
    def capture(**inputs):
        artifact = original(**inputs)
        captured.append((inputs, artifact))
        return artifact
    monkeypatch.setattr("tools.replay_vsdc_valuation_impact.build_current_valuation_artifact", capture)
    replay(**kwargs)
    for metric in captured[1][1]["records"][t]["metrics"].values():
        assert metric["share_basis"] == "VSDC_REGISTERED_SHARES"
        assert metric["share_concept"] == "ISSUED_SHARES"
        assert metric["share_authority_tier"] == "OFFICIAL_REGISTERED_SHARES"
        assert metric["observation_date"] == published
        assert metric["limitations"] == basis["limitations"]
        if metric["status"] == "RESEARCH_USABLE":
            assert "NOT_COMMON_OUTSTANDING_SHARE_BASIS" in metric["labels"]
            assert metric["historical_pit_eligible"] is False

    # Extend flag-OFF byte parity through the builder against this task's exact HEAD.
    legacy = types.ModuleType("hol07_head_valuation")
    source = subprocess.check_output(["git", "show", "15c77ffe:stocklookup_core/valuation/market_wide_current_valuation_input_scaleout.py"])
    exec(compile(source, "hol07_head_valuation.py", "exec"), legacy.__dict__)
    old = legacy.build_current_valuation_artifact(**captured[0][0])
    assert json.dumps(old, sort_keys=True).encode() == json.dumps(captured[0][1], sort_keys=True).encode()
    before_publication = datetime.fromisoformat(published).replace(year=2025)
    assert replay(**(kwargs | {"known_by": before_publication}))["changed_tickers"] == 0
    with pytest.raises(ValueError, match="AWARE"):
        replay(**(kwargs | {"known_by": datetime(2026, 11, 23)}))


@pytest.mark.parametrize("authority", [
    key for key in valuation.SHARE_STATUS_BY_AUTHORITY if key != "official_registered_shares"
] + ["unrecognized_authority"])
def test_every_other_resolver_authority_has_byte_identical_valuation(authority):
    from test_market_wide_current_valuation_input_scaleout import _inputs
    price, fundamental, shares, p3e = _inputs()
    legacy = types.ModuleType("hol07_head_valuation")
    source = subprocess.check_output(["git", "show", "15c77ffe:stocklookup_core/valuation/market_wide_current_valuation_input_scaleout.py"])
    exec(compile(source, "hol07_head_valuation.py", "exec"), legacy.__dict__)
    inputs = dict(price_snapshot=price, fundamental_artifact=fundamental,
                  share_promotion_artifact=shares, p3e_artifact=p3e,
                  share_resolution={"tickers": {"HPG": {"authority": authority, "value": 200}}})
    assert json.dumps(legacy.build_current_valuation_artifact(**inputs), sort_keys=True).encode() == json.dumps(
        valuation.build_current_valuation_artifact(**inputs), sort_keys=True).encode()
