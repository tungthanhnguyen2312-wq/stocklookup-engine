"""Build offline conditional research cases from retained evidence.

The default command rebuilds the HPG, KBC and FPT acceptance packet. A separate
``--inputs`` command reads an explicit JSON list and uses the same supplied-input
contract for any issuer. Neither command fetches, OCRs, writes a production
database, or attaches Daily authority.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stocklookup_core.research.conditional_investment_case import (
    case_from_annual_context,
    case_from_industrial_profile,
    case_from_supplied_inputs,
)
from stocklookup_core.valuation.conditional_research_valuation import (
    industrial_research_profile,
    scope_and_period_bridge,
)

DEFAULT_INTAKE = Path(r"C:\Projects\StockLookup\agent-reports\official-financial-quarterly-intake-v1\REAL_FINANCIAL_INTAKE_CANDIDATES.json")
DEFAULT_EXAMPLES = Path(r"C:\Projects\StockLookup\agent-reports\vn30-financial-metrics-unlock-20261014\work\valuation_examples.json")
DEFAULT_FPT = ROOT / "derived" / "financial-evidence-currency-refresh-v1" / "fpt_official_annual_context_report.json"

HPG_LINES = {
    "hpg-h1-2026-gross-revenue": "GROSS_REVENUE",
    "hpg-h1-2026-deductions": "REVENUE_DEDUCTIONS",
    "hpg-h1-2026-net-revenue": "NET_REVENUE",
    "hpg-h1-2026-net-income-total": "TOTAL_PROFIT_AFTER_TAX",
    "hpg-h1-2026-net-income-parent": "PARENT_PROFIT_AFTER_TAX",
    "hpg-h1-2026-net-income-nci": "NCI_PROFIT_AFTER_TAX",
    "hpg-h1-2026-equity-total": "TOTAL_EQUITY_INCLUDING_NCI",
    "hpg-h1-2026-operating-cash-flow": "OPERATING_CASH_FLOW",
}
KBC_LINES = {
    "kbc-consol-q3-parent-npat": ("consolidated", "2026-Q3", "PARENT_PROFIT_AFTER_TAX"),
    "kbc-consol-q3-npat": ("consolidated", "2026-Q3", "TOTAL_PROFIT_AFTER_TAX"),
    "kbc-consol-q3-nci-npat": ("consolidated", "2026-Q3", "NCI_PROFIT_AFTER_TAX"),
    "kbc-consol-9m-parent-npat": ("consolidated", "2026-9M", "PARENT_PROFIT_AFTER_TAX"),
    "kbc-separate-q3-npat": ("separate", "2026-Q3", "TOTAL_PROFIT_AFTER_TAX"),
}


def _load(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def _hpg_fact(wrapper: dict, identity: str) -> dict:
    candidate = wrapper["candidate"]
    return {
        "ticker": "HPG",
        "accounting_identity": identity,
        "normalized_integer": candidate["normalized_value"],
        "statement_scope": candidate.get("statement_scope"),
        "reporting_period": candidate.get("reporting_period"),
        "currency": candidate.get("currency"),
        "unit_scale": candidate.get("unit_scale"),
        "period_semantic_state": candidate.get("period_semantic_state"),
        "document_sha256": candidate.get("document_sha256"),
        "origin": wrapper.get("origin"),
        "source_page": candidate.get("source_page"),
        "source_field_identity": candidate.get("source_field_identity"),
        "official_fact_admitted": wrapper.get("official_fact_admitted"),
    }


def build_cases(*, intake_path: Path = DEFAULT_INTAKE, examples_path: Path = DEFAULT_EXAMPLES,
                fpt_path: Path = DEFAULT_FPT) -> dict:
    packet = _load(intake_path)
    rows = {row["evidence_id"]: row for row in packet["results"]}
    example = _load(examples_path)["HPG"]
    facts = {identity: _hpg_fact(rows[evidence], identity) for evidence, identity in HPG_LINES.items()}
    listing = rows["hpg-h1-2026-subsequent-listing-shares"]["candidate"]
    components = {
        "opening_ordinary_shares": rows["hpg-h1-2026-opening-ordinary-shares"]["candidate"]["normalized_value"],
        "stock_dividend_shares": rows["hpg-h1-2026-eps-stock-dividend-impact"]["candidate"]["normalized_value"],
        "eps_denominator_shares": rows["hpg-h1-2026-eps-average-shares"]["candidate"]["normalized_value"],
        "june_contributed_capital_vnd": rows["hpg-h1-2026-owners-contributed-capital"]["candidate"]["normalized_value"],
        "subsequent_charter_capital_vnd": rows["hpg-h1-2026-subsequent-charter-capital"]["candidate"]["normalized_value"],
        "listing_quote": (listing.get("original_candidate") or {}).get("quote"),
    }
    profile = industrial_research_profile(
        ticker="HPG",
        price=example["price"],
        share_components=components,
        facts=facts,
        provider_share=example["share"]["value"],
    )
    hpg = case_from_industrial_profile(profile)
    bridge_rows = []
    for evidence, (scope, period, identity) in KBC_LINES.items():
        candidate = rows[evidence]["candidate"]
        bridge_rows.append({
            "scope": scope,
            "period": period,
            "identity": identity,
            "normalized_integer": candidate["normalized_value"],
            "native_numeric_literal_proven": rows[evidence].get("native_numeric_literal_proven"),
            "source_sha256": candidate.get("document_sha256"),
            "origin": rows[evidence].get("origin"),
        })
    bridge = scope_and_period_bridge(bridge_rows)
    kbc = {
        "ticker": "KBC",
        "fitness": "DESCRIPTIVE_EVIDENCE",
        "bridge": bridge,
        "market_cap_vnd": None,
        "strict_authority": {
            "strict_decision_eligible": False,
            "execution_eligible": False,
            "official_fact_admitted": False,
            "is_actionable": False,
            "target_price": None,
            "probability": None,
        },
        "thesis": [
            "KBC can be read as two scopes and two periods. Consolidated parent profit is not separate profit, "
            "and the third quarter is not the nine-month cumulative."
        ],
        "counter_thesis": [
            "The figures are OCR candidates. native_numeric_literal_proven is false.",
            "No price was supplied, so no capitalization is calculated.",
        ],
        "missing": ["QUALIFIED_PRICE", "NATIVE_NUMERIC_LEXEME", "PARENT_BOOK_EQUITY"],
        "invalidation": [
            "A native text span that disagrees with an OCR candidate.",
            "A price observation, which would still need its own share basis before a capitalization.",
        ],
    }
    fpt_report = _load(fpt_path)
    document = fpt_report["documents"][0]
    fpt = case_from_annual_context(
        ticker="FPT",
        canonical_facts=document["canonical_facts"],
        blocked=document["blocked_candidates"],
        document_sha256=document.get("document_sha256"),
        knowledge_available_at=document.get("knowledge_available_at"),
    )
    uses = profile["multiples"]
    expectations = {
        "hpg_research_price": profile["price"]["research_vnd_per_share"] == "20450.00",
        "hpg_source_unit_not_verified": profile["price"]["source_unit_verified"] is False,
        "hpg_shares": profile["share_basis"]["research_shares"] == 8442964520,
        "hpg_market_cap": profile["market_cap_vnd"] == "172658624434000.00",
        "hpg_interim_not_ttm": uses["pe_ttm"]["eligibility"] == "UNUSABLE" and uses["pe_ttm"]["value"] is None,
        "hpg_parent_pb_unusable": uses["pb_parent"]["eligibility"] == "UNUSABLE",
        "hpg_total_equity_labeled": uses["price_over_total_equity_including_nci"]["eligibility"] == "CONDITIONAL_RESEARCH_ESTIMATE",
        "hpg_pre_dividend_unusable": profile["incompatible_pre_dividend_market_cap"]["eligibility"] == "UNUSABLE",
        "hpg_cash_scope_warning": (profile["cash_conversion"] or {}).get("scope_warning") == "CONSOLIDATED_OPERATING_CASH_FLOW_OVER_PARENT_ATTRIBUTABLE_PROFIT",
        "hpg_not_actionable": hpg["strict_authority"]["is_actionable"] is False and hpg["strict_authority"]["target_price"] is None,
        "kbc_scopes_differ": any(item["name"] == "CONSOLIDATED_PARENT_VERSUS_SEPARATE_PROFIT" and item["same_number"] is False for item in bridge["findings"]),
        "kbc_quarter_not_added": any(item["name"] == "QUARTER_IS_NOT_YEAR_TO_DATE" and item["quarter_plus_nine_month"] is None for item in bridge["findings"]),
        "kbc_q3_foots": any(item["name"] == "Q3_TOTAL_EQUALS_PARENT_PLUS_NCI" and item["residual"] == 0 for item in bridge["findings"]),
        "kbc_no_market_cap": kbc["market_cap_vnd"] is None,
        "fpt_revenue_retained": any(row["metric"] == "revenue" and row["value"] == 70112825100710 for row in fpt["descriptive_evidence"]["canonical_facts"]),
        "fpt_no_market_cap": fpt["conditional_interpretation"]["market_cap_vnd"] is None,
        "fpt_no_parent_profit_fact": all(row["metric"] != "attributable_net_income" for row in fpt["descriptive_evidence"]["canonical_facts"]),
        "fpt_parent_line_stays_blocked": any(row.get("canonical_metric") == "attributable_net_income" and row.get("reason") == "OCR_NUMERIC_AMBIGUITY" for row in fpt["descriptive_evidence"]["blocked"]),
    }
    failed = [name for name, ok in expectations.items() if not ok]
    return {
        "contract_version": "conditional_research_acceptance/v1",
        "producer_checkout_written": False,
        "ocr_invoked": False,
        "cases": {"HPG": hpg, "KBC": kbc, "FPT": fpt},
        "expectations": expectations,
        "failed_expectations": failed,
    }


def build_supplied_cases(records: list[Mapping[str, Any]]) -> dict:
    """Build cases from explicit records. Business rules stay in the shared engines."""
    if not isinstance(records, list) or not records:
        raise ValueError("inputs must be a non-empty list of {ticker, entity, inputs}")
    cases = []
    for index, record in enumerate(records):
        if not isinstance(record, Mapping):
            raise ValueError(f"record {index} must be an object")
        ticker = str(record.get("ticker") or "").strip()
        if not ticker:
            raise ValueError(f"record {index} is missing ticker")
        inputs = record.get("inputs")
        if not isinstance(inputs, Mapping):
            raise ValueError(f"record {index} is missing inputs")
        entity = str(record.get("entity") or inputs.get("entity") or "corporate")
        case = case_from_supplied_inputs(ticker=ticker, entity=entity, inputs=inputs)
        authority = case.get("strict_authority") or {}
        if authority.get("strict_decision_eligible") or authority.get("execution_eligible") or authority.get("official_fact_admitted") or authority.get("is_actionable"):
            raise RuntimeError(f"{ticker} conditional case entered strict authority")
        if authority.get("target_price") is not None or authority.get("probability") is not None:
            raise RuntimeError(f"{ticker} conditional case invented a target or probability")
        cases.append(case)
    return {
        "contract_version": "conditional_research_supplied_cases/v1",
        "producer_checkout_written": False,
        "automatic_production_daily": False,
        "ocr_invoked": False,
        "cases": cases,
    }


def _interpretation_lines(case: Mapping[str, Any]) -> list[str]:
    cond = case.get("conditional_interpretation") or {}
    order = (
        "research_price_vnd_per_share",
        "source_unit_verified",
        "research_shares",
        "market_cap_vnd",
        "market_cap_eligibility",
        "reason",
        "interim_parent_profit_multiple",
        "interim_parent_profit_period",
        "total_equity_multiple",
    )
    lines = []
    for key in order:
        if key in cond:
            lines.append(f"- {key}: {cond.get(key)}")
    cash = cond.get("cash_conversion") or {}
    if cash:
        lines.append(f"- cash_conversion_status: {cash.get('status')}")
        if cash.get("scope_warning"):
            lines.append(f"- cash_conversion_scope_warning: {cash.get('scope_warning')}")
    return lines


def render_supplied_markdown(packet: Mapping[str, Any]) -> str:
    """Owner reading of supplied cases. Labels come from the case, not from a ticker list."""
    lines = [
        "# Conditional research cases",
        "",
        "Inputs were supplied explicitly. These cases do not enter strict valuation, investment posture, sizing, execution, or official fact authority.",
        "Automatic production Daily is not attached.",
        "",
    ]
    for case in packet.get("cases") or []:
        authority = case.get("strict_authority") or {}
        lines.extend([
            f"## {case.get('ticker')}",
            "",
            f"Fitness: {case.get('fitness')}.",
            (
                f"Strict decision eligible: {authority.get('strict_decision_eligible')}. "
                f"Execution eligible: {authority.get('execution_eligible')}. "
                f"Official fact admitted: {authority.get('official_fact_admitted')}. "
                f"Actionable: {authority.get('is_actionable')}."
            ),
            f"Target price: {authority.get('target_price')}. Probability: {authority.get('probability')}.",
        ])
        if case.get("document_sha256"):
            lines.append(f"Document SHA-256: {case.get('document_sha256')}.")
        if case.get("knowledge_available_at"):
            lines.append(f"Knowledge available at: {case.get('knowledge_available_at')}.")
        lines.append("")
        lines.append("Conditional interpretation:")
        lines.extend(_interpretation_lines(case) or ["- none"])
        lines.append("")
        for label, key in (
            ("Reading notes", "reading_notes"),
            ("Thesis", "thesis"),
            ("Counter-thesis", "counter_thesis"),
            ("Missing", "missing"),
            ("Risks", "risks"),
            ("Invalidation", "invalidation"),
        ):
            values = case.get(key) or []
            if not values:
                continue
            lines.append(f"{label}:")
            lines.extend(f"- {item}" for item in values)
            lines.append("")
        press = case.get("press_not_statement") or []
        if press:
            lines.append("Press highlights kept out of the statements:")
            lines.extend(f"- {item.get('status')}: used as a statement fact = {item.get('used_as_statement_fact')}." for item in press)
            lines.append("")
        findings = ((case.get("bridge") or {}).get("findings") or [])
        if findings:
            lines.append("Scope and period findings:")
            for item in findings:
                lines.append(
                    f"- {item.get('name')}: eligibility {item.get('eligibility')}; residual {item.get('residual')}; "
                    f"same number {item.get('same_number')}; quarter plus nine-month {item.get('quarter_plus_nine_month')}."
                )
            lines.append("")
        facts = ((case.get("descriptive_evidence") or {}).get("canonical_facts") or [])
        if facts:
            lines.append("Qualified facts kept as descriptive context:")
            for row in facts:
                lines.append(
                    f"- {row.get('metric')} {row.get('value')} {row.get('currency') or ''} "
                    f"period {row.get('period')} scope {row.get('scope')} line {row.get('line_code')} "
                    f"valuation use {row.get('valuation_use')}."
                )
            lines.append("")
        blocked = ((case.get("descriptive_evidence") or {}).get("blocked") or [])
        if blocked:
            lines.append("Blocked candidates:")
            for row in blocked:
                lines.append(f"- {row.get('canonical_metric') or row.get('metric')}: {row.get('reason')}.")
            lines.append("")
    return "\n".join(lines).rstrip() + "\n"


def render_markdown(packet: dict) -> str:
    hpg = packet["cases"]["HPG"]
    cond = hpg["conditional_interpretation"]
    kbc = packet["cases"]["KBC"]
    fpt = packet["cases"]["FPT"]
    revenue = next(row["value"] for row in fpt["descriptive_evidence"]["canonical_facts"] if row["metric"] == "revenue")
    equity = next(row["value"] for row in fpt["descriptive_evidence"]["canonical_facts"] if row["metric"] == "shareholders_equity")
    lines = [
        "# Conditional research cases — HPG, KBC, FPT",
        "",
        "Strict decision, execution and official-fact admission stay closed. No target price is stated.",
        "",
        "## HPG — research date 2026-10-13",
        "",
        f"Research price {cond['research_price_vnd_per_share']} VND per share. Source unit verified: {cond['source_unit_verified']}.",
        f"Research shares {cond['research_shares']}. Conditional market capitalization {cond['market_cap_vnd']} VND.",
        f"Price over reported H1 parent profit: {cond['interim_parent_profit_multiple']}. This is the six-month column, not annual P/E and not TTM P/E.",
        f"Price over total equity including non-controlling interests: {cond['total_equity_multiple']}. This is not parent-shareholder P/B.",
        "Parent P/B, TTM P/E and EV/EBITDA are unusable.",
        "Consolidated operating cash flow over parent-attributable profit carries that scope warning. The ratio is a visual review, not an admitted fact.",
        "",
        "## KBC — Q3 and nine-month 2026",
        "",
        "Consolidated and separate profits stay apart. The quarter is not added to the nine-month column.",
        "OCR candidates are not native lexemes. No price was supplied, so there is no market capitalization.",
        "",
        "## FPT — audited FY2025 context",
        "",
        f"Qualified consolidated revenue {revenue} VND and line-400 equity {equity} VND are historical context.",
        "Parent profit stays blocked on ambiguous digits. Cash, debt, current shares and a current price are absent, so no multiple is calculated.",
        "A later company highlight is not used as a statement fact.",
        "",
        f"Failed checks: {', '.join(packet['failed_expectations']) or 'none'}.",
        "",
    ]
    return "\n".join(lines)


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(text)


def _load_input_records(path: Path) -> list:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict) and isinstance(payload.get("records"), list):
        payload = payload["records"]
    if not isinstance(payload, list):
        raise SystemExit("inputs must be a JSON list or an object with a records list")
    return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build offline conditional research cases from retained evidence.")
    parser.add_argument("--inputs", type=Path, help="JSON list of {ticker, entity, inputs} for the supplied-input contract.")
    parser.add_argument("--intake", type=Path, help="Retained quarterly intake for the HPG/KBC/FPT examples.")
    parser.add_argument("--valuation-examples", type=Path, help="Retained price and share examples.")
    parser.add_argument("--fpt-annual", type=Path, help="Retained audited FPT annual context.")
    parser.add_argument("--out-json", type=Path, required=True, help="New machine-readable output file.")
    parser.add_argument("--out-md", type=Path, required=True, help="New Owner-readable output file.")
    args = parser.parse_args(argv)
    outputs = [args.out_json.resolve(), args.out_md.resolve()]
    if outputs[0] == outputs[1] or any(path.exists() for path in outputs):
        parser.error("Output files must be distinct and must not already exist.")
    if args.inputs is not None:
        if any((args.intake, args.valuation_examples, args.fpt_annual)):
            parser.error("--inputs cannot be combined with retained example options.")
        packet = build_supplied_cases(_load_input_records(args.inputs))
        markdown = render_supplied_markdown(packet)
    else:
        packet = build_cases(intake_path=args.intake or DEFAULT_INTAKE,
                             examples_path=args.valuation_examples or DEFAULT_EXAMPLES,
                             fpt_path=args.fpt_annual or DEFAULT_FPT)
        if packet["failed_expectations"]:
            raise SystemExit("failed: " + ", ".join(packet["failed_expectations"]))
        markdown = render_markdown(packet)
    _write(args.out_json, json.dumps(packet, ensure_ascii=False, indent=2) + "\n")
    _write(args.out_md, markdown)
    print(args.out_json)
    print(args.out_md)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
