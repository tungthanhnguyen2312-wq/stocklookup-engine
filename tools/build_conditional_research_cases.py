"""Build offline HPG, KBC and FPT research cases from retained evidence.

Reads existing intake and annual-context files. Does not fetch, OCR, or write
a production database.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stocklookup_core.research.conditional_investment_case import (
    case_from_annual_context,
    case_from_industrial_profile,
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


def main() -> int:
    packet = build_cases()
    out_dir = ROOT / "docs" / "internal"
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "CONDITIONAL_RESEARCH_CASES_20261113.json").write_text(
        json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (out_dir / "CONDITIONAL_RESEARCH_CASES_20261113.md").write_text(
        render_markdown(packet), encoding="utf-8")
    if packet["failed_expectations"]:
        raise SystemExit("failed: " + ", ".join(packet["failed_expectations"]))
    print("cases ok", ", ".join(packet["cases"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
