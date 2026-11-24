"""Offline OFF/ON share-basis replay using the existing valuation builder.

Owner decision 2026-11-24 admits VSDC registered counts/share events, distinct
from listed and outstanding ex-treasury shares. Existing valuation gates apply.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from market_wide_current_shares_resolver import (
    resolve_market_wide_shares, retained_official_share_events, retained_exchange_share_observations,
)
from stocklookup_core.valuation.market_wide_current_valuation_input_scaleout import build_current_valuation_artifact
from tools.derive_market_wide_current_valuation_input_scaleout import _verify_sources
from tools.run_p3f6_mva_provider_share_proxy import _metadata

METRICS = ("market_cap", "P/E", "P/B", "P/S", "enterprise_value", "EV/Sales", "EV/EBITDA")


def replay(*, evidence_roots, runtime_root, known_by, price, fundamental, shares, p3e,
           official_universe=None):
    if known_by.tzinfo is None or known_by.utcoffset() is None:
        raise ValueError("AWARE_KNOWN_BY_REQUIRED")
    session = price["resolved_completed_session"]
    if price.get("retained_snapshot_session", session) != session:
        raise ValueError("EXACT_PRICE_SESSION_REQUIRED")
    exchange = retained_exchange_share_observations(evidence_roots, session, known_by=known_by)
    provider = _metadata(Path(runtime_root))
    resolutions, artifacts = [], []
    for enabled in (False, True):
        events = retained_official_share_events(evidence_roots, session, known_by=known_by,
                                               vsdc_hose_events_enabled=enabled)
        resolution = resolve_market_wide_shares(runtime_root, session, known_by=known_by,
            official_events=events["events"], exchange_observations=exchange["observations"])
        if resolution.get("status") != "measured" or not resolution.get("counts_reconcile"):
            raise ValueError("SHARE_INVENTORY_UNREADABLE_OR_NONRECONCILING")
        resolutions.append(resolution)
        artifacts.append(build_current_valuation_artifact(price_snapshot=price,
            fundamental_artifact=fundamental, share_promotion_artifact=shares, p3e_artifact=p3e,
            official_universe=official_universe, share_resolution=resolution))
    rows = []
    missing = []
    for ticker, after in resolutions[1]["tickers"].items():
        before = resolutions[0]["tickers"][ticker]
        if (before["authority"], before["value"]) == (after["authority"], after["value"]):
            continue
        evidence = after.get("official_registration_evidence") or {}
        metrics = {}
        for name in METRICS:
            old = artifacts[0]["records"].get(ticker, {}).get("metrics", {}).get(name, {})
            new = artifacts[1]["records"].get(ticker, {}).get("metrics", {}).get(name, {})
            a, b = old.get("value"), new.get("value")
            metrics[name] = {"before": a, "after": b,
                "percent_change": (b - a) / abs(a) * 100 if a not in (None, 0) and b is not None else None,
                "status_before": old.get("status", "NOT_IN_VALUATION_UNIVERSE"),
                "status_after": new.get("status", "NOT_IN_VALUATION_UNIVERSE"),
                "blocked_reasons_before": old.get("blocked_reasons", []),
                "blocked_reasons_after": new.get("blocked_reasons", [])}
        if ticker not in artifacts[0]["records"]:
            missing.append(ticker)
        rows.append({"ticker": ticker, "authority_before": before["authority"],
            "authority_after": after["authority"], "shares_before": before["value"],
            "shares_after": after["value"], "provider_shares": provider.get(ticker, {}).get("value"),
            "shares_percent_change": ((after["value"] - before["value"]) / abs(before["value"]) * 100
                if before["value"] not in (None, 0) and after["value"] is not None else None),
            "share_basis_after": artifacts[1]["records"].get(ticker, {}).get("share_basis_input"),
            "provider_observation_date": after.get("provider_observation_date", before.get("observation_date")),
            "vsdc_registered_shares": evidence.get("shares_after"),
            "notice_url": evidence.get("source_url"), "published_at": evidence.get("published_at"),
            "registration_evidence": evidence, "metrics": metrics})
    return {"schema_version": "vsdc_valuation_impact/v1", "valuation_session": session,
        "known_by": known_by.isoformat(), "prototype_passes": [False, True],
        "authority_boundary": "OFFLINE_CURRENT_RESEARCH_NO_PIT_OR_OUTSTANDING_PROMOTION",
        "source_artifacts": {"price": price.get("snapshot_identity"),
            "fundamental": fundamental.get("artifact_identity"), "shares": shares.get("artifact_identity"),
            "p3e": p3e.get("artifact_identity"),
            "official_universe": (official_universe or {}).get("artifact_identity")},
        "changed_tickers": len(rows), "missing_valuation_tickers": missing, "rows": rows}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--evidence-root", type=Path, action="append", required=True)
    parser.add_argument("--runtime-root", type=Path, required=True, help="Read-only retained provider inventory")
    parser.add_argument("--known-by", required=True)
    for name in ("price", "fundamental", "shares", "p3e"):
        parser.add_argument("--" + name, type=Path, required=True)
    parser.add_argument("--official-universe", type=Path)
    parser.add_argument("--expected-session", default="2026-11-23")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    # Explicit input files only; never open integrated-investment-decision artifacts.
    sources = {name: json.loads(getattr(args, name).read_text(encoding="utf-8"))
               for name in ("price", "fundamental", "shares", "p3e")}
    official = json.loads(args.official_universe.read_text(encoding="utf-8")) if args.official_universe else None
    _verify_sources(**sources, official=official)
    if sources["price"]["resolved_completed_session"] != args.expected_session:
        raise ValueError("VALUATION_PRICE_SESSION_MISMATCH")
    result = replay(**sources, official_universe=official, evidence_roots=args.evidence_root,
        runtime_root=args.runtime_root, known_by=datetime.fromisoformat(args.known_by.replace("Z", "+00:00")))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.output.exists():
        raise ValueError("REFUSING_TO_OVERWRITE_REPLAY")
    with args.output.open("x", encoding="utf-8") as handle:
        handle.write(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"changed_tickers": result["changed_tickers"], "known_by": result["known_by"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
