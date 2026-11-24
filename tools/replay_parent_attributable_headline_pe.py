"""Offline Owner Decision 1 compatibility replay; never reads an integrated product.

Only the supplied valuation/financial product inputs speak for available earnings.
This does not discover or qualify new source facts, or reproduce missing upstream panels.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stocklookup_core.valuation.current_research_valuation_context import evaluate_ticker_valuation, attach_peer_relative
from stocklookup_core.decision.integrated_investment_decision_product import _select_headline_method

FOCUS = "FPT GAS HPG NVL PAN PNJ POW PVD QNS SSI VCB VNM VRE".split()


def load(path):
    if "integrated" in path.name.lower():
        raise ValueError("INTEGRATED_PRODUCT_READ_FORBIDDEN")
    with path.open(encoding="utf-8") as stream:
        return json.load(stream)


def source(path, artifact):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return {"file": path.name, "sha256": digest.hexdigest(), "artifact_identity": artifact["artifact_identity"]}


def headline(row):
    key, item = _select_headline_method(row.get("methods") or {}, "P/E")
    return {"method": key, "value": item.get("value") if item.get("status") in {"READY", "RESEARCH_USABLE"} else None,
            "period": item.get("period_basis"), "status": item.get("status"),
            "earnings_attribution": item.get("earnings_attribution"), "display_label": item.get("display_label"),
            "reasons": item.get("blocker_reason_codes") or []}


def replay(raw_path, evaluated_path, financial_path):
    raw = load(raw_path)
    sources = {"raw_valuation": source(raw_path, raw)}
    financial = load(financial_path)
    sources["financial_product"] = source(financial_path, financial)
    financial_records = financial["financial_analysis_product"]["records"]
    # Retain only explicitly named parent-profit TTM features. Total TTM is not
    # relabelled parent, and dimensionless ratios never supply an absolute amount.
    parent_features = {}
    parent_ids = {"attributable_net_income_ttm", "net_income_parent_ttm", "net_profit_parent_ttm", "profit_after_tax_parent_ttm"}
    for ticker, row in financial_records.items():
        for key, feature in (row.get("feature_fitness") or {}).items():
            context = feature.get("source_feature_context") or {}
            if context.get("feature_id") in parent_ids:
                parent_features.setdefault(ticker, {})[context["feature_id"]] = {
                    **feature, **context, "provider_source_provenance": context.get("source_fact_refs") or []}
    del financial, financial_records
    evaluated = load(evaluated_path)
    if evaluated["source_valuation_identity"] != raw["artifact_identity"]:
        raise ValueError("VALUATION_SOURCE_IDENTITY_MISMATCH")
    sources["evaluated_valuation"] = source(evaluated_path, evaluated)
    before = {ticker: headline(row) for ticker, row in evaluated["records"].items()}
    del evaluated
    rows = {ticker: evaluate_ticker_valuation(ticker=ticker, feature_record=None, valuation_record=raw["records"].get(ticker),
        financial_analysis_record={"features": parent_features.get(ticker, {})},
        decision_session=raw["valuation_session"]) for ticker in sorted(set(before) | set(raw["records"]))}
    rows = attach_peer_relative(rows)
    after = {ticker: headline(row) for ticker, row in rows.items()}
    official = [ticker for ticker, row in raw["records"].items() if row["financial_input"]["authority"] == "OFFICIAL_QUALIFIED"]
    return {"task_id": "HL-20261124-HOL-06", "mode": "SUPPLIED_RETAINED_INPUT_COMPATIBILITY_REPLAY",
        "sources": sources, "session": raw["valuation_session"], "evaluated_denominator": len(before),
        "raw_denominator": len(raw["records"]), "after_denominator": len(rows), "official_qualified_names": sorted(official),
        "parent_ttm_feature_names_retained": sorted(parent_features),
        "before_headline_count": sum(r["value"] is not None for r in before.values()),
        "after_headline_count": sum(r["value"] is not None for r in after.values()),
        "lost_names": sorted(t for t, r in before.items() if r["value"] is not None and after.get(t, {}).get("value") is None),
        "focus": {ticker: {"before": before.get(ticker), "after": after.get(ticker),
            "supplementary": rows.get(ticker, {}).get("methods", {}).get("P/E_TOTAL_INCLUDING_NCI"),
            "peer": rows.get(ticker, {}).get("peer_relative", {}).get("P/E")} for ticker in FOCUS},
        "limitation": "No upstream official panel supplied; no new annual parent facts acquired or admitted. Missing evaluated-only names have no raw input and gain no headline."}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--evaluated", type=Path, required=True)
    parser.add_argument("--financial", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    target = args.output.resolve()
    if not target.is_relative_to(ROOT):
        raise ValueError("OUTPUT_MUST_STAY_IN_WORKTREE")
    result = replay(args.raw, args.evaluated, args.financial)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("before_headline_count", "after_headline_count", "lost_names")}))


if __name__ == "__main__":
    main()
