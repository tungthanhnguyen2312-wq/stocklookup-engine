"""Build offline conditional research cases from retained evidence.

The default command rebuilds the HPG, KBC and FPT acceptance packet. A separate
``--inputs`` command reads an explicit JSON list and uses the same supplied-input
contract for any issuer. Neither command fetches, OCRs, writes a production
database, or attaches Daily authority.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from decimal import Decimal
from pathlib import Path
from typing import Any, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from stocklookup_core.research.conditional_investment_case import (
    case_from_annual_context,
    case_from_industrial_profile,
    case_from_reviewed_evidence,
    case_from_supplied_inputs,
)
from stocklookup_core.valuation.conditional_research_valuation import (
    derive_parent_equity_research,
    financing_research,
    industrial_research_profile,
    known_by,
    price_over_derived_parent_equity,
    printed_cash_to_earnings,
    scope_and_period_bridge,
    trailing_twelve_month_earnings,
)

DEFAULT_INTAKE = Path(r"C:\Projects\StockLookup\agent-reports\official-financial-quarterly-intake-v1\REAL_FINANCIAL_INTAKE_CANDIDATES.json")
DEFAULT_EXAMPLES = Path(r"C:\Projects\StockLookup\agent-reports\vn30-financial-metrics-unlock-20261014\work\valuation_examples.json")
DEFAULT_FPT = ROOT / "derived" / "financial-evidence-currency-refresh-v1" / "fpt_official_annual_context_report.json"
DEFAULT_QUALIFIED = ROOT / "derived" / "financial-evidence-currency-refresh-v1" / "qualified_official_facts.jsonl"
COHORT_CUTOFF = "2026-10-13T23:59:59+00:00"

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


def _flow_column(candidate: Mapping[str, Any], *, role: str, year: int, months: int | None, qualification: str) -> dict:
    return {
        "ticker": candidate.get("ticker"),
        "accounting_identity": candidate.get("accounting_identity"),
        "statement_scope": candidate.get("statement_scope"),
        "currency": candidate.get("currency"),
        "unit_scale": candidate.get("unit_scale"),
        "reporting_period": candidate.get("reporting_period"),
        "period_role": role,
        "fiscal_year": year,
        "months": months,
        "normalized_integer": candidate.get("normalized_value") if isinstance(candidate.get("normalized_value"), int) else None,
        "qualification": qualification,
        "document_sha256": candidate.get("document_sha256"),
    }


def _qualified_row(row: Mapping[str, Any], identity: str) -> dict:
    return {
        "ticker": row.get("ticker"),
        "accounting_identity": identity,
        "statement_scope": row.get("statement_scope") or "consolidated",
        "currency": row.get("currency"),
        "unit_scale": 1,
        "reporting_period": f"{row.get('period_start')}/{row.get('period_end')}",
        "normalized_integer": row.get("normalized_value") if isinstance(row.get("normalized_value"), int) else None,
        "qualification": "VERIFIED" if row.get("qualification_state") == "QUALIFIED" else "CONDITIONAL_RESEARCH",
        "document_sha256": row.get("document_sha256"),
        "canonical_metric": row.get("canonical_metric"),
        "period_type": row.get("period_type"),
        "knowledge_available_at": row.get("knowledge_available_at"),
    }


def _load_qualified(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        if str(row.get("knowledge_available_at") or "") > COHORT_CUTOFF:
            continue
        rows.append(row)
    return rows


def _issuer_set(values: set[str]) -> list[str]:
    return sorted(values)


def build_cases(*, intake_path: Path = DEFAULT_INTAKE, examples_path: Path = DEFAULT_EXAMPLES,
                fpt_path: Path = DEFAULT_FPT, qualified_path: Path = DEFAULT_QUALIFIED) -> dict:
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
    hpg_depth = _hpg_depth(rows, profile)
    kbc_depth = _kbc_depth(rows)
    qualified = _load_qualified(qualified_path)
    cohort = _cohort_depth(qualified, hpg_depth, kbc_depth, profile)
    hpg["research_depth"] = hpg_depth
    kbc["research_depth"] = kbc_depth
    expectations.update({
        "hpg_derived_parent_equity": hpg_depth["parent_equity"]["value_vnd"] == 140656346514229 and hpg_depth["parent_equity"]["printed_parent_line"] is False,
        "hpg_derived_parent_multiple_not_pb": hpg_depth["price_over_derived_parent_equity"]["display_method"] == "PRICE_OVER_DERIVED_PARENT_EQUITY" and hpg_depth["price_over_derived_parent_equity"]["strict_valuation_use"] == "STRICT_VALUATION_QUARANTINED",
        "hpg_ttm_absent": hpg_depth["parent_ttm"]["ttm"] is None and "ANNUALIZATION_REFUSED" not in hpg_depth["parent_ttm"]["reason_codes"] and "NO_COMPATIBLE_TTM_BRIDGE" in hpg_depth["parent_ttm"]["reason_codes"],
        "hpg_financing_not_debt": hpg_depth["financing"]["interest_bearing_debt_vnd"] is None and hpg_depth["financing"]["mixed_loans_and_finance_leases_vnd"] == 98529977232553 and hpg_depth["financing"]["ev_ebitda"] is None,
        "hpg_pb_parent_stays_unusable": uses["pb_parent"]["eligibility"] == "UNUSABLE",
        "kbc_ttm_absent": kbc_depth["parent_ttm"]["ttm"] is None and kbc_depth["revenue_yoy"]["not_ttm"] is True,
        "kbc_revenue_yoy": kbc_depth["revenue_yoy"]["change_vnd"] == 205818765509,
        "cohort_ttm_pe_stays_zero": cohort["after"]["true_ttm_pe"]["verified"] == 0 and cohort["after"]["true_ttm_pe"]["conditional_research"] == 0,
        "cohort_parent_equity_research_gained": cohort["before"]["parent_equity_research"]["conditional_research"] == 0 and cohort["after"]["parent_equity_research"]["conditional_research"] == 1,
        "vre_cash_quality_names_total_profit": any(item["ticker"] == "VRE" and item["earnings_identity"] == "TOTAL_PROFIT_AFTER_TAX" and item["ratio"] is not None for item in cohort["cash_quality"]),
        "line_400_not_parent_book": all(item["counted_as_parent_equity"] is False for item in cohort["line_400_equity"]),
    })
    failed = [name for name, ok in expectations.items() if not ok]
    return {
        "contract_version": "conditional_research_acceptance/v1",
        "producer_checkout_written": False,
        "ocr_invoked": False,
        "automatic_production_daily": False,
        "cases": {"HPG": hpg, "KBC": kbc, "FPT": fpt},
        "valuation_depth": {"hpg": hpg_depth, "kbc": kbc_depth, "cohort": cohort},
        "expectations": expectations,
        "failed_expectations": failed,
    }


def _hpg_depth(rows: Mapping[str, Any], profile: Mapping[str, Any]) -> dict:
    def fact(evidence: str, identity: str) -> dict:
        built = _hpg_fact(rows[evidence], identity)
        built["qualification"] = "CONDITIONAL_RESEARCH"
        return built

    total = fact("hpg-h1-2026-equity-total", "TOTAL_EQUITY_INCLUDING_NCI")
    nci = fact("hpg-h1-2026-nci-equity", "NON_CONTROLLING_INTERESTS")
    parent_equity = derive_parent_equity_research(total, nci)
    financing_rows = [
        fact("hpg-h1-2026-cash-and-cash-equivalents", "CASH_AND_EQUIVALENTS"),
        fact("hpg-h1-2026-short-term-loans-and-finance-leases", "SHORT_TERM_LOANS_AND_FINANCE_LEASES"),
        fact("hpg-h1-2026-long-term-loans-and-finance-leases", "LONG_TERM_LOANS_AND_FINANCE_LEASES"),
    ]
    depreciation = fact("hpg-h1-2026-depreciation-line", "COMPOSITE_CASH_FLOW_DEPRECIATION_ADJUSTMENT")
    flows = [fact("hpg-h1-2026-net-income-parent", "PARENT_PROFIT_AFTER_TAX")]
    flows[0]["period_role"] = "UNKNOWN_DURATION"
    flows[0]["fiscal_year"] = 2026
    flows[0]["months"] = None
    return {
        "parent_equity": parent_equity,
        "price_over_derived_parent_equity": price_over_derived_parent_equity(
            market_cap_vnd=profile.get("market_cap_vnd"),
            parent_equity_vnd=parent_equity.get("value_vnd"),
            price_session="2026-10-13",
            equity_period="2026-06-30",
        ),
        "financing": financing_research(financing_rows, depreciation=depreciation),
        "parent_ttm": trailing_twelve_month_earnings(flows, identity="PARENT_PROFIT_AFTER_TAX"),
        "share_authority": "CONDITIONAL_RESEARCH_ESTIMATE",
    }


def _kbc_depth(rows: Mapping[str, Any]) -> dict:
    def column(evidence: str, role: str, year: int, months: int) -> dict:
        candidate = rows[evidence]["candidate"]
        built = _flow_column(candidate, role=role, year=year, months=months, qualification="CONDITIONAL_RESEARCH")
        built["accounting_identity"] = {
            "kbc-consol-9m-net-sales": "NET_REVENUE",
            "kbc-consol-9m-2025-net-sales": "NET_REVENUE",
            "kbc-consol-9m-parent-npat": "PARENT_PROFIT_AFTER_TAX",
        }[evidence]
        return built

    revenue_columns = [
        column("kbc-consol-9m-net-sales", "YTD", 2026, 9),
        column("kbc-consol-9m-2025-net-sales", "YTD", 2025, 9),
    ]
    parent_columns = [column("kbc-consol-9m-parent-npat", "YTD", 2026, 9)]
    revenue = trailing_twelve_month_earnings(revenue_columns, identity="NET_REVENUE")
    parent = trailing_twelve_month_earnings(parent_columns, identity="PARENT_PROFIT_AFTER_TAX")
    return {
        "revenue_ttm": revenue,
        "revenue_yoy": revenue["same_ytd_comparisons"][0],
        "parent_ttm": parent,
        "market_cap_vnd": None,
    }


def _bucket(verified: set[str], conditional: set[str], cohort: list[str]) -> dict[str, int]:
    usable = verified | conditional
    return {
        "verified": len(verified),
        "conditional_research": len(conditional - verified),
        "unusable": len([ticker for ticker in cohort if ticker not in usable]),
    }


def _cohort_depth(qualified: list[dict], hpg_depth: Mapping[str, Any], kbc_depth: Mapping[str, Any], profile: Mapping[str, Any]) -> dict:
    cohort = _issuer_set({str(row.get("ticker")) for row in qualified} | {"HPG", "KBC", "FPT"})
    verified_parent = {row["ticker"] for row in qualified if row.get("canonical_metric") == "attributable_net_income" and row.get("qualification_state") == "QUALIFIED"}
    conditional_parent = {"HPG", "KBC"}
    line_400 = []
    for row in qualified:
        if row.get("canonical_metric") != "shareholders_equity":
            continue
        line_400.append({
            "ticker": row.get("ticker"),
            "value": row.get("normalized_value"),
            "counted_as_parent_equity": False,
            "reason": "LINE_400_IS_NOT_PROVEN_PARENT_BOOK",
        })
    cash_quality = []
    by_ticker: dict[str, list[dict]] = {}
    for row in qualified:
        by_ticker.setdefault(row["ticker"], []).append(row)
    for ticker, rows in sorted(by_ticker.items()):
        earnings = next((row for row in rows if row.get("canonical_metric") == "net_income"), None)
        cash = next((row for row in rows if row.get("canonical_metric") == "operating_cash_flow" and row.get("period_end") == (earnings or {}).get("period_end") and row.get("document_sha256") == (earnings or {}).get("document_sha256")), None)
        if earnings and cash and earnings.get("currency") == cash.get("currency"):
            quality = printed_cash_to_earnings(_qualified_row(earnings, "TOTAL_PROFIT_AFTER_TAX"), _qualified_row(cash, "OPERATING_CASH_FLOW"))
            quality["ticker"] = ticker
            cash_quality.append(quality)
    before = {
        "parent_net_income": _bucket(verified_parent, conditional_parent, cohort),
        "compatible_ttm_earnings": _bucket(set(), set(), cohort),
        "parent_equity_research": _bucket(set(), set(), cohort),
        "market_cap": _bucket(set(), {"HPG"} if profile.get("market_cap_vnd") else set(), cohort),
        "reported_period_earnings_multiple": _bucket(set(), {"HPG"}, cohort),
        "true_ttm_pe": _bucket(set(), set(), cohort),
        "compatible_parent_pb": _bucket(set(), set(), cohort),
        "cash_or_financing_quality": _bucket(set(), {"HPG"}, cohort),
        "ev_ebitda": _bucket(set(), set(), cohort),
    }
    after_parent_equity = {"HPG"} if hpg_depth["parent_equity"]["value_vnd"] is not None else set()
    after_financing = set()
    if hpg_depth["financing"]["mixed_loans_and_finance_leases_vnd"] is not None or hpg_depth["financing"]["cash_and_equivalents_vnd"] is not None:
        after_financing.add("HPG")
    after_financing.update(item["ticker"] for item in cash_quality if item.get("ratio") is not None)
    after = {
        "parent_net_income": before["parent_net_income"],
        "compatible_ttm_earnings": before["compatible_ttm_earnings"],
        "parent_equity_research": _bucket(set(), after_parent_equity, cohort),
        "market_cap": before["market_cap"],
        "reported_period_earnings_multiple": before["reported_period_earnings_multiple"],
        "true_ttm_pe": before["true_ttm_pe"],
        "compatible_parent_pb": before["compatible_parent_pb"],
        "conditional_price_over_derived_parent_equity": _bucket(set(), after_parent_equity, cohort),
        "cash_or_financing_quality": _bucket(
            {item["ticker"] for item in cash_quality if item.get("fitness") == "VERIFIED"},
            after_financing,
            cohort,
        ),
        "ev_ebitda": before["ev_ebitda"],
    }
    return {
        "cohort": cohort,
        "cutoff": COHORT_CUTOFF,
        "before": before,
        "after": after,
        "cash_quality": cash_quality,
        "line_400_equity": line_400,
        "blocked_reasons": {
            "HPG_TTM": hpg_depth["parent_ttm"]["reason_codes"],
            "KBC_PARENT_TTM": kbc_depth["parent_ttm"]["reason_codes"],
            "KBC_REVENUE_TTM": kbc_depth["revenue_ttm"]["reason_codes"],
            "EV_EBITDA": ["MIXED_OR_MISSING_DEBT", "DEPRECIATION_NOT_EBITDA", "NO_COMPATIBLE_PARENT_EBIT"],
            "STRICT_PB": ["NO_PRINTED_PARENT_EQUITY_LINE"],
            "FPT_PARENT_PROFIT": ["OCR_NUMERIC_AMBIGUITY"],
            "PVD_H1_CURRENCY": ["USD_INTERIM_IS_NOT_COMBINED_WITH_VND_ANNUAL"],
        },
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
        "## Valuation depth",
        "",
    ]
    depth = packet.get("valuation_depth") or {}
    hpg_depth = depth.get("hpg") or {}
    kbc_depth = depth.get("kbc") or {}
    parent_equity = hpg_depth.get("parent_equity") or {}
    derived_multiple = hpg_depth.get("price_over_derived_parent_equity") or {}
    financing = hpg_depth.get("financing") or {}
    revenue_yoy = kbc_depth.get("revenue_yoy") or {}
    cohort = depth.get("cohort") or {}
    lines.extend([
        f"HPG derived parent equity {parent_equity.get('value_vnd')} VND. Method: total consolidated equity minus printed non-controlling interest. Printed parent line: {parent_equity.get('printed_parent_line')}.",
        f"Price over that derived equity: {derived_multiple.get('value')}. Display method {derived_multiple.get('display_method')}. The 30 June book is not the 13 October price session, and this is not parent P/B.",
        f"HPG combined loans and finance leases {financing.get('mixed_loans_and_finance_leases_vnd')} VND. Cash and equivalents {financing.get('cash_and_equivalents_vnd')} VND. Interest-bearing debt, net debt and EV/EBITDA: {financing.get('interest_bearing_debt_vnd')}, {financing.get('net_debt_vnd')}, {financing.get('ev_ebitda')}.",
        f"KBC nine-month consolidated revenue changed by {revenue_yoy.get('change_vnd')} VND versus the prior nine-month column. That comparison is not TTM. Parent TTM remains absent.",
        f"Cohort {', '.join(cohort.get('cohort') or [])}. True TTM P/E stays 0. Strict parent P/B stays 0.",
        "",
    ])
    return "\n".join(lines)


def _file_sha256(path: Path) -> str:
    with path.open("rb") as handle:
        return hashlib.file_digest(handle, "sha256").hexdigest()


def build_reviewed_packet(packet_path: Path, source_map_path: Path, *, expected_sha256: str) -> dict:
    """Validate the exact reviewed packet and its original document bytes before building."""
    raw = packet_path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256) or digest != expected_sha256:
        raise ValueError("REVIEWED_PACKET_SHA256_MISMATCH")
    packet = json.loads(raw)
    if (not isinstance(packet, dict) or packet.get("contract_version") != "financial_evidence_research_packet/v1"
            or packet.get("authority") != "RESEARCH_CANDIDATES_ONLY_NO_OFFICIAL_FACT_ADMISSION_NO_NEW_SOURCE_AUTHORITY"):
        raise ValueError("REVIEWED_PACKET_CONTRACT_INVALID")
    cutoff = packet.get("research_cutoff")
    if not isinstance(cutoff, str) or known_by({"knowledge_available_at": cutoff}, cutoff) != "KNOWN":
        raise ValueError("REVIEWED_PACKET_CUTOFF_INVALID")
    documents = packet.get("documents")
    paths = _load(source_map_path)
    if (not isinstance(documents, dict) or not documents or not isinstance(paths, dict)
            or set(documents) != set(paths)):
        raise ValueError("REVIEWED_PACKET_SOURCE_MAP_MISMATCH")
    for sha, document in sorted(documents.items()):
        if not re.fullmatch(r"[0-9a-f]{64}", sha):
            raise ValueError("REVIEWED_PACKET_SOURCE_SHA256_INVALID")
        if (not isinstance(document, dict) or document.get("text_layer") not in {"NATIVE_TEXT", "SCANNED", "SCANNED_OCR_LAYER"}
                or not all(isinstance(document.get(key), str) and document[key].strip()
                           for key in ("ticker", "source_url", "retained_filename"))
                or not isinstance(paths[sha], str) or not paths[sha].strip()):
            raise ValueError("REVIEWED_PACKET_SOURCE_METADATA_INVALID")
        path = source_map_path.parent / paths[sha]
        if not path.is_file():
            raise ValueError(f"REVIEWED_PACKET_SOURCE_MISSING:{sha}")
        if _file_sha256(path) != sha:
            raise ValueError(f"REVIEWED_PACKET_SOURCE_SHA256_MISMATCH:{sha}")

    basis_limits = packet.get("basis_limits", {})
    rows = packet.get("rows")
    if not isinstance(rows, list) or not rows or not isinstance(basis_limits, dict):
        raise ValueError("REVIEWED_PACKET_ROWS_INVALID")
    groups = {}
    keys = set()
    for row in rows:
        if not isinstance(row, dict) or not all(isinstance(row.get(key), str) and row[key].strip()
                                               for key in ("ticker", "accounting_identity", "statement_scope",
                                                           "reporting_period", "locator", "verification",
                                                           "evidence_quality", "document_sha256", "knowledge_basis")):
            raise ValueError("REVIEWED_PACKET_ROW_METADATA_INVALID")
        ticker = row["ticker"]
        document = documents.get(row["document_sha256"])
        if document is None or document["ticker"] != ticker:
            raise ValueError("REVIEWED_PACKET_ROW_SOURCE_UNBOUND")
        corroboration = row.get("corroborating_document_sha256")
        if corroboration is not None and (not isinstance(corroboration, str)
                                          or documents.get(corroboration, {}).get("ticker") != ticker):
            raise ValueError("REVIEWED_PACKET_CORROBORATION_UNBOUND")
        native = row["evidence_quality"].startswith("NATIVE_TEXT") or row["verification"] == "NATIVE_TEXT_LOCATED"
        if native and document["text_layer"] != "NATIVE_TEXT":
            raise ValueError("REVIEWED_PACKET_SCANNED_SOURCE_CANNOT_BE_NATIVE")
        if (row.get("official_fact_admitted") is not False or row.get("qualification") != "CONDITIONAL_RESEARCH"
                or row.get("annualize") is not False or type(row.get("normalized_integer")) is not int
                or type(row.get("unit_scale")) is not int or row["unit_scale"] <= 0
                or "currency" not in row or row["currency"] not in (None, "VND", "USD")):
            raise ValueError("REVIEWED_PACKET_ROW_BOUNDARY_INVALID")
        if row.get("period_role") in ("FULL_YEAR", "YTD"):
            year, months = row.get("fiscal_year"), row.get("months")
            if (type(year) is not int or type(months) is not int
                    or months not in ((12,) if row["period_role"] == "FULL_YEAR" else (3, 6, 9))
                    or row["reporting_period"] != (str(year) if months == 12 else f"{year}-{months}M")
                    or not all(isinstance(row.get(key), str) and row[key].strip()
                               for key in ("consolidation_basis", "presentation_basis"))):
                raise ValueError("REVIEWED_PACKET_FLOW_PERIOD_INVALID")
        key = (ticker, row["accounting_identity"], row["statement_scope"], row["reporting_period"])
        if key in keys:
            raise ValueError("REVIEWED_PACKET_DUPLICATE_COLUMN")
        keys.add(key)
        groups.setdefault(ticker, []).append(row)
    for ticker, limit in basis_limits.items():
        if (ticker not in groups or not isinstance(limit, dict)
                or not all(isinstance(limit.get(key), str) and limit[key].strip() for key in ("reason_code", "detail"))
                or ("document_sha256" in limit and (not isinstance(limit["document_sha256"], str)
                    or documents.get(limit["document_sha256"], {}).get("ticker") != ticker))):
            raise ValueError("REVIEWED_PACKET_BASIS_LIMIT_INVALID")

    return {
        "contract_version": "conditional_research_reviewed_cases/v1",
        "packet_identity": f"financial_evidence_research_packet:{digest}",
        "packet_sha256": digest,
        "research_cutoff": cutoff,
        "row_count": len(rows),
        "documents": documents,
        "verification_summary": packet.get("verification_summary"),
        "structural_levels_context_only": packet.get("retained_levels", []),
        "automatic_production_daily": False,
        "cases": {ticker: case_from_reviewed_evidence(ticker=ticker, rows=groups[ticker], cutoff=cutoff,
                                                       basis_limit=basis_limits.get(ticker))
                  for ticker in sorted(groups)},
    }


def render_reviewed_markdown(packet: Mapping[str, Any]) -> str:
    lines = [
        "# Reviewed financial research cases",
        "",
        f"Cutoff `{packet['research_cutoff']}`. Reviewed packet `{packet['packet_sha256']}`.",
        "",
        "Original source bytes were matched to the packet digests. Numeric review status is shown per row.",
        "Current market capitalization and multiples require a source-bound close with a verified monetary unit.",
    ]
    for ticker, case in packet["cases"].items():
        lines.extend(["", f"## {ticker}", "", f"Case identity `{case['case_identity']}`.", ""])
        if case["basis_limit"]:
            lines.extend([case["basis_limit"]["detail"], ""])
        earnings = case["parent_earnings"]
        ttm = earnings["ttm"]
        if ttm:
            lines.append(f"- Conditional TTM parent profit **{ttm['value_vnd']:,} VND** using the three listed periods.")
            for row in ttm["inputs"]:
                lines.append(f"  - {row['role']} | {row['reporting_period']} | {row['normalized_integer']:,} VND | {row['evidence_quality']}")
            lines.append(f"  - Caveats `{', '.join(ttm['basis_caveats']) or 'none'}`.")
        else:
            lines.append(f"- TTM parent profit unavailable. `{', '.join(earnings['reason_codes'])}`.")
        for row in earnings["same_ytd_comparisons"]:
            lines.append(f"- Same-duration YTD parent profit changed by {row['change_vnd']:,} VND.")
        for period, metrics in case["metrics_by_period"].items():
            for label, key, field in (
                ("Operating cash / parent profit", "cash_to_parent_profit", "ratio"),
                ("Operating cash less printed purchases", "operating_cash_less_printed_purchases", "value_vnd"),
                ("Derived parent equity", "derived_parent_equity", "value_vnd"),
                ("Cash over printed borrowing lines", "financing", "cash_cover_of_printed_loan_lines"),
            ):
                metric = metrics.get(key, {})
                value = metric.get(field)
                if value is not None:
                    display = f"{value:,} VND" if isinstance(value, int) else f"{Decimal(value):.4f}×"
                    lines.append(f"- {period} | {label} **{display}**.")
                    if metric.get("scope_warning"):
                        lines.append("  - The numerator is consolidated cash flow and the denominator is parent-attributable profit.")
        lines.extend(["", "| Period | Printed identity | Value | Extraction | Calculation |",
                      "|---|---|---:|---|---|"])
        for row in case["evidence_rows"]:
            lines.append(f"| {row['reporting_period']} | {row['accounting_identity']} | {row['normalized_integer']:,} | "
                         f"{row['evidence_quality']} | {row['calculation_state']} |")
        lines.extend(["", "Original digests, page locators, knowledge times and basis qualifiers are in the JSON."])
    return "\n".join(lines) + "\n"



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
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--reviewed-packet", type=Path, help="Explicit reviewed financial evidence packet.")
    mode.add_argument("--inputs", type=Path, help="JSON list of {ticker, entity, inputs} for the supplied-input contract.")
    parser.add_argument("--packet-sha256", help="Exact reviewed packet SHA-256.")
    parser.add_argument("--source-map", type=Path, help="JSON map of document SHA-256 to local original file path.")
    parser.add_argument("--intake", type=Path, help="Retained quarterly intake for the HPG/KBC/FPT examples.")
    parser.add_argument("--valuation-examples", type=Path, help="Retained price and share examples.")
    parser.add_argument("--fpt-annual", type=Path, help="Retained audited FPT annual context.")
    parser.add_argument("--out-json", type=Path, required=True, help="New machine-readable output file.")
    parser.add_argument("--out-md", type=Path, required=True, help="New Owner-readable output file.")
    args = parser.parse_args(argv)
    outputs = [args.out_json.resolve(), args.out_md.resolve()]
    if outputs[0] == outputs[1] or any(path.exists() for path in outputs):
        parser.error("Output files must be distinct and must not already exist.")
    if args.reviewed_packet is not None:
        if not args.source_map or not args.packet_sha256 or any((args.intake, args.valuation_examples, args.fpt_annual)):
            parser.error("--reviewed-packet requires --source-map and --packet-sha256, without retained example options.")
        try:
            packet = build_reviewed_packet(args.reviewed_packet, args.source_map, expected_sha256=args.packet_sha256)
        except (OSError, ValueError) as exc:
            parser.error(str(exc))
        markdown = render_reviewed_markdown(packet)
    elif args.source_map is not None or args.packet_sha256 is not None:
        parser.error("--source-map and --packet-sha256 require --reviewed-packet.")
    elif args.inputs is not None:
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
