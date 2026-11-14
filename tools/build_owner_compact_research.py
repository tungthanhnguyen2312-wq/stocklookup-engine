"""Project a sealed session into compact Owner-private research, without rebuilding it."""
from __future__ import annotations

import argparse
from collections.abc import Mapping
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from daily_research_session_operations import _identity as operation_identity
from daily_research_session_operations import brief_retention_identity
from stocklookup_core.acquisition.artifact_io import retain_immutable_bytes
from stocklookup_core.decision.current_daily_decision_research_product import content_identity as product_identity
from stocklookup_core.decision.current_thesis_case_context import _identity as thesis_identity
from stocklookup_core.decision.daily_integrated_decision_brief import content_identity as brief_identity
from stocklookup_core.decision.daily_opportunity_decision_queue import content_identity as queue_identity
from stocklookup_core.decision.screener_master_projection import content_identity as screener_identity
from tools.build_conditional_research_cases import build_reviewed_packet, render_reviewed_markdown

MAX_TICKERS = 12
TOP_ROWS = 5
TACTICAL_CARD_SCOPE = (
    "Independent tactical classifier context. Its entry state and action are research labels "
    "for the stated horizon. Use the Integrated Decision for the current research posture; "
    "if it is unavailable, the tactical card does not supply a substitute."
)
VN_TIME = timezone(timedelta(hours=7))


def read_json(path: Path):
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def select(record, *fields):
    return {key: record[key] for key in fields if key in record}


def index(rows, tickers):
    return {row["ticker"]: row for row in rows if row.get("ticker") in tickers}


def verify(source, identity, declared):
    if identity["artifact_identity"] != declared or any(source.get(k) != v for k, v in identity.items()):
        raise ValueError("RETAINED_ARTIFACT_IDENTITY_MISMATCH:" + str(declared))


def build(operation_dir: Path, session: str, tickers=(), *, reviewed=None):
    """Use the exact operation directory and its self-verifying research artifacts."""
    if date.fromisoformat(session).isoformat() != session:
        raise ValueError("SESSION_MUST_BE_YYYY_MM_DD")
    if len(tickers) > MAX_TICKERS or any(not re.fullmatch(r"[A-Z0-9]{2,12}", t) for t in tickers):
        raise ValueError("EXPECTED_AT_MOST_12_EXPLICIT_TICKERS")
    tickers = sorted(set(tickers))
    sources = {}

    def load(filename):
        value, digest = read_json(operation_dir / filename)
        sources[filename] = {"sha256": digest, "identity": value.get("artifact_identity") or value.get("operation_identity")}
        return value

    run = load("run_manifest.json")
    outputs = run["outputs"]
    operation = run["operation_identity"]
    integrated = outputs["integrated_investment_decision_product"]
    envelope = load("daily_integrated_decision_brief_artifact.json")
    brief = envelope["daily_integrated_decision_brief"]
    product = load("current_daily_decision_research_product_artifact.json")
    delivery = load("ai_research_bundle_manifest.json")
    if (operation_identity(run) != operation or run["market_session"] != session
            or run["session_coherence"]["session"] != session
            or any(row["session"] != session for row in (envelope, brief, product, delivery))
            or envelope["daily_operation_identity"] != operation or delivery["operation_identity"] != operation
            or any(row["integrated_investment_decision_product_identity"] != integrated for row in (envelope, delivery))
            or delivery["daily_integrated_decision_brief_identity"] != outputs["daily_integrated_decision_brief"]):
        raise ValueError("RETAINED_SESSION_OR_OPERATION_BINDING_MISMATCH")
    verify(envelope, brief_retention_identity(envelope), envelope["artifact_identity"])
    verify(brief, brief_identity(brief), outputs["daily_integrated_decision_brief"])
    verify(product, product_identity(product), outputs["daily_product"])

    queue = {}
    queue_id = outputs.get("daily_opportunity_decision_queue")
    if delivery["source_artifact_identities"].get("opportunity_decision_queue") != queue_id:
        raise ValueError("RETAINED_QUEUE_DELIVERY_BINDING_MISMATCH")
    if queue_id:
        queue = load("daily_opportunity_decision_queue_artifact.json")
        if queue["research_session"] != session:
            raise ValueError("RETAINED_QUEUE_SESSION_MISMATCH")
        verify(queue, queue_identity(queue), queue_id)

    screener = {}
    screener_file = "screener_master_projection.json"
    if tickers and (operation_dir / screener_file).is_file():
        screener = load(screener_file)
        official_universe = (run["input_artifacts"].get("official_universe") or {}).get("artifact_identity")
        if (screener["as_of_session"] != session
                or screener["source_artifacts"].get("official_market_universe") != official_universe):
            raise ValueError("RETAINED_SCREENER_SESSION_OR_UNIVERSE_MISMATCH")
        verify(screener, screener_identity(screener), screener["artifact_identity"])

    thesis = {}
    thesis_file = "current_thesis_case_context_artifact.json"
    if tickers and (operation_dir / thesis_file).is_file():
        thesis = load(thesis_file)
        if thesis["as_of_session"] != session:
            raise ValueError("RETAINED_THESIS_SESSION_MISMATCH")
        verify(thesis, thesis_identity(thesis), thesis["artifact_identity"])
        event_identity = (run["input_artifacts"].get("event_context") or {}).get("artifact_identity")
        financial_context_id = screener.get("source_artifacts", {}).get("financial_analysis_product_integration")
        if (thesis["source_artifacts"].get("corporate_event_context") != event_identity
                or (financial_context_id and
                    thesis["source_artifacts"].get("financial_analysis_product_context") != financial_context_id)):
            raise ValueError("RETAINED_THESIS_EVENT_BINDING_MISMATCH")

    comparison = brief.get("comparison_metadata") or {}
    qualified = (comparison.get("comparison_fitness") == "FRESH_ADJACENT"
                 and comparison.get("comparison_session") == brief.get("previous_qualified_session")
                 and brief["what_changed_today"].get("availability") == "AVAILABLE")
    manifest_claim = delivery["files"]["ai_research_session_bundle.json"]
    market = {
        "session": session,
        "operation_identity": operation,
        "integrated_decision_identity": integrated,
        "primary_bundle_manifest_claim": manifest_claim,
        "sources": sources,
        "market": brief["market_summary"],
        "coverage": brief["coverage"],
        "sectors": [r for r in brief["sector_summary"]["sectors"]
                    if r.get("relative_strength_leadership_state") == "LEADING"],
        "sector_authority": brief["sector_summary"]["authority_boundary"],
        "opportunities": {k: brief["opportunity_sets"][k][:TOP_ROWS]
                          for k in ("top_current_opportunities", "top_early_setups", "highest_risk_names")},
        "opportunity_ordering": brief["opportunity_sets"]["ordering_method"],
        "opportunity_counts": brief["opportunity_sets"]["set_counts"],
        "risk": brief["risk_summary"],
        "queue_coverage": queue.get("entry_relevant_summary"),
        "gaps": product["risk_data_gap_panel"],
        "limitations": run["warnings"],
        "comparison": comparison,
        "changes": brief["what_changed_today"] if qualified else None,
        "authority": brief["authority_boundary"],
    }

    financial_cases = {}
    if reviewed:
        cutoff = datetime.fromisoformat(reviewed["research_cutoff"]).astimezone(VN_TIME)
        if cutoff.date().isoformat() > session:
            raise ValueError("REVIEWED_RESEARCH_CUTOFF_AFTER_SESSION")
        financial_cases = reviewed["cases"]

    watch = index(brief["watchlist"]["records"], tickers)
    posture = index(brief["decision_surface_index"]["rows"], tickers)
    cards = product["detailed_research_cards"]
    briefs = {}
    for ticker in tickers:
        row = watch.get(ticker, {})
        screen = screener.get("cards", {}).get(ticker, {})
        card = cards.get(ticker, {})
        research_case = thesis.get("records", {}).get(ticker, {})
        opportunity = queue.get("records", {}).get(ticker, {})
        fundamental = card.get("fundamental_context") or {}
        financial = row.get("financial_analysis") or {}
        methods = row.get("valuation_methods") or {}
        boundaries = select(row, "trigger_type", "trigger_state", "trigger_level", "distance_to_trigger_pct",
                            "invalidation_level", "invalidation_method", "distance_to_invalidation_pct")
        research_card = select(card, "current_decision_state", "data_quality", "trigger", "invalidation",
                               "authority_limitations")
        if research_card:
            research_card = {"decision_scope": TACTICAL_CARD_SCOPE, **research_card}
        brief_row = {
            "ticker": ticker,
            "integrated_decision": posture.get(ticker),
            "market_position": select(screen, "price", "tactical", "freshness", "authority_boundary"),
            "technical": select(row, "market_structure_state", "tactical_phase", "breakout_state",
                                "bos_state", "choch_state", "tactical_confirmation_context", "decision_identity"),
            "entry_boundaries": boundaries,
            "research_card": research_card,
            "fundamentals": {**select(row, "fundamental_state"),
                             **select(fundamental, "authority_tier", "earnings_direction", "revenue_direction",
                                      "operating_cash_flow_direction", "limitations"),
                             **({"financial_analysis": select(financial, "status", "as_of_financial_period",
                                                          "financial_content_identity", "source_context_identity",
                                                          "growth_state", "margin_state", "cash_conversion_state",
                                                          "balance_sheet_state", "missing_dimensions", "warnings")}
                                if financial else {})},
            "valuation": {**select(card, "valuation_context"),
                          **({"retained_methods": {name: select(methods[name], "value", "status", "source_status",
                                                             "method_id", "period_basis", "book_period",
                                                             "share_basis", "share_identity", "price_session",
                                                             "price_representation", "equity_definition",
                                                             "equity_source_status", "monetary_compatibility",
                                                             "blocker_reason_codes", "limitations", "warnings")
                                               for name in ("P/E", "P/E_TTM", "P/B", "P/B_CURRENT_RESEARCH", "EV/EBITDA")
                                               if isinstance(methods.get(name), Mapping)}} if methods else {})},
            "thesis_summary": select(row, "why_now", "counter_thesis"),
            "thesis_evidence": select(research_case, "supporting_evidence", "counter_thesis_evidence_detail",
                                      "risk_evidence", "catalysts", "technical_invalidation", "fundamental_invalidation",
                                      "evidence_gaps", "lineage", "authority_boundaries"),
            "opportunity_queue": select(opportunity, "content_identity", "source_input_identities",
                                        "research_priority_tier", "entry_action", "tactical_state", "authority_note",
                                        "invalidation_or_context_warnings", "blocking_reasons"),
            "remaining_uncertainties": select(row, "evidence_currency", "material_uncertainties"),
            "availability": {
                "integrated_decision": ticker in posture, "detailed_watchlist": bool(row),
                "research_card": bool(card), "thesis_evidence": bool(research_case),
                "opportunity_queue": bool(opportunity),
            },
        }
        if ticker in financial_cases:
            brief_row["reviewed_financial_research"] = {
                "scope": "OFFLINE_NON_VOTING_CONDITIONAL_RESEARCH",
                "packet_sha256": reviewed["packet_sha256"], "research_cutoff": reviewed["research_cutoff"],
                "case": financial_cases[ticker],
                "source_documents": {sha: doc for sha, doc in reviewed["documents"].items() if doc["ticker"] == ticker},
            }
        briefs[ticker] = brief_row
    return {"contract_version": "owner_compact_session_research/v1", "is_actionable": False,
            "market_summary": market, "ticker_briefs": briefs}


def render_market(market):
    regime = market["market"]["market_regime"]
    breadth = market["market"]["breadth"]
    lines = [f"# Market research for {market['session']}", "", f"Regime **{regime}**.",
             f"Breadth: {breadth.get('advancing')} advancing, {breadth.get('declining')} declining, "
             f"{breadth.get('unchanged')} unchanged across the covered cohort.",
             "", "## Leading sectors", ""]
    lines.extend(f"- {r['sector_label']} ({r['exact_session_observed_count']} observed)" for r in market["sectors"])
    for heading, key in (("Current opportunities", "top_current_opportunities"),
                         ("Early setups", "top_early_setups"), ("Higher-risk names", "highest_risk_names")):
        lines.extend(["", f"## {heading}", ""])
        lines.extend(f"- **{r['ticker']}** · {r['research_action_posture']} · {r.get('why_now')}"
                     for r in market["opportunities"][key])
    lines.extend(["", "## What changed", "",
                  f"Comparison with {market['comparison'].get('comparison_session')}: "
                  f"{market['comparison'].get('comparison_fitness')}."])
    if market["changes"]:
        for key in ("new_breakdowns", "new_failed_breakouts", "new_early_setups"):
            values = market["changes"].get(key, [])
            lines.append(f"- {key.replace('_', ' ').capitalize()}: {', '.join(values[:TOP_ROWS]) or 'none reported'}")
    lines.extend(["", "## Coverage and limits", "",
                  f"- Evidence currency: {market['coverage']['evidence_currency_distribution']}",
                  f"- Strict valuation-ready count: {market['gaps'].get('strict_valuation_ready')}",
                  *[f"- {warning}" for warning in market["limitations"]],
                  "", f"Operation: `{market['operation_identity']}`",
                  f"Integrated Decision: `{market['integrated_decision_identity']}`",
                  f"Primary bundle SHA-256 (manifest): `{market['primary_bundle_manifest_claim']['sha256']}`"])
    return "\n".join(lines) + "\n"


def render_ticker(session, row, reviewed, sources):
    lines = [f"# {row['ticker']} research for {session}", ""]
    labels = (("Integrated Decision: current research posture", "integrated_decision"),
              ("Market position", "market_position"),
              ("Technical structure", "technical"),
              ("Integrated Decision triggers and invalidation", "entry_boundaries"),
              ("Independent tactical research card", "research_card"),
              ("Fundamentals", "fundamentals"), ("Valuation", "valuation"), ("Thesis summary", "thesis_summary"),
              ("Thesis, catalysts and risks", "thesis_evidence"),
              ("Opportunity Queue: research priority and tactical context", "opportunity_queue"),
              ("Freshness and limitations", "remaining_uncertainties"))
    for heading, key in labels:
        lines.extend([f"## {heading}", ""])
        value = row[key]
        if value:
            for label, item in value.items():
                if item is not None and item != [] and item != {}:
                    text = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False, sort_keys=True)
                    display_label = ("tactical classifier state"
                                     if key == "research_card" and label == "current_decision_state"
                                     else label.replace("_", " "))
                    lines.append(f"- **{display_label}** · {text}")
        else:
            lines.append("Unavailable in the retained source for this ticker.")
        lines.append("")
    if "reviewed_financial_research" in row:
        lines.extend(["## Offline conditional financial research", "", render_reviewed_markdown(
            {**reviewed, "cases": {row["ticker"]: reviewed["cases"][row["ticker"]]}}
        ).split("\n", 2)[2]])
    lines.extend(["", "## Retained sources", ""])
    lines.extend(f"- {name} · SHA-256 `{meta['sha256']}`" for name, meta in sources.items())
    return "\n".join(lines).rstrip() + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--operation-dir", type=Path, required=True)
    parser.add_argument("--session", required=True)
    parser.add_argument("--tickers", nargs="+", default=[])
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--reviewed-packet", type=Path)
    parser.add_argument("--packet-sha256")
    parser.add_argument("--source-map", type=Path)
    args = parser.parse_args()
    finance = (args.reviewed_packet, args.packet_sha256, args.source_map)
    if any(finance) and not all(finance):
        parser.error("reviewed financial evidence requires --reviewed-packet, --packet-sha256 and --source-map")
    reviewed = build_reviewed_packet(finance[0], finance[2], expected_sha256=finance[1]) if all(finance) else None
    result = build(args.operation_dir, args.session, [t.upper() for t in args.tickers], reviewed=reviewed)
    files = {"market.md": render_market(result["market_summary"]),
             "research.json": json.dumps(result, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"}
    for ticker, row in result["ticker_briefs"].items():
        files[f"{ticker}.md"] = render_ticker(args.session, row, reviewed, result["market_summary"]["sources"])
    if args.output_dir.resolve().is_relative_to(args.operation_dir.resolve()):
        parser.error("use an output directory outside the retained operation")
    for name, value in files.items():
        retain_immutable_bytes(args.output_dir / name, value.encode("utf-8"))
    print(json.dumps({name: len(value.encode("utf-8")) for name, value in files.items()}, sort_keys=True))


if __name__ == "__main__":
    main()
