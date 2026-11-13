"""Owner research case from already qualified or candidate financial evidence.

The case repeats deterministic labels. It does not invent a target price, a
probability, a TTM multiple, or a parent-book ratio from total equity.
"""
from __future__ import annotations

from typing import Any, Mapping

from stocklookup_core.valuation.conditional_research_valuation import (
    industrial_research_profile,
    scope_and_period_bridge,
)

CONTRACT_VERSION = "conditional_investment_case/v1"
CONDITIONAL = "CONDITIONAL_RESEARCH"
DESCRIPTIVE = "DESCRIPTIVE_EVIDENCE"
UNAVAILABLE = "UNAVAILABLE"
PRESS = "RECORDED_PRESS_HIGHLIGHT_NOT_A_STATEMENT"


def _use(profile: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    return (profile.get("multiples") or {}).get(name) or {}


def _lines(profile: Mapping[str, Any]) -> list[str]:
    shares = profile.get("share_basis") or {}
    cash = profile.get("cash_conversion") or {}
    interim = _use(profile, "price_over_reported_interim_parent_profit")
    equity = _use(profile, "price_over_total_equity_including_nci")
    lines = [
        "Research capitalization uses the owner-accepted thousand-VND close and the same-filing post-dividend share count.",
        "The close is not a verified endpoint unit and is not a qualified raw-as-traded price.",
        f"Interim parent-profit multiple eligibility is {interim.get('eligibility')}; it is a reported-period column, not annual or TTM P/E.",
        f"Total-equity multiple eligibility is {equity.get('eligibility')}; the denominator includes non-controlling interests and is not parent-shareholder P/B.",
        "P/E TTM, parent P/B and EV/EBITDA stay unusable until their own evidence exists.",
    ]
    if shares.get("research_shares"):
        lines.append(
            f"Research share count {shares.get('research_shares')} comes from one filing. "
            "A provider field that repeats it is not a second source."
        )
    if cash.get("scope_warning"):
        lines.append(
            "Operating cash flow and parent profit share a consolidated column. "
            "The ratio is group cash flow over parent-attributable profit, not a parent-only cash conversion."
        )
    if cash.get("status"):
        lines.append(f"Cash-conversion status is {cash.get('status')}.")
    return lines


def case_from_industrial_profile(
    profile: Mapping[str, Any],
    *,
    bridge: Mapping[str, Any] | None = None,
    missing: list[str] | None = None,
) -> dict[str, Any]:
    """Turn one industrial research profile into a bounded investment case."""
    interim = _use(profile, "price_over_reported_interim_parent_profit")
    cap = _use(profile, "market_cap")
    gaps = list(missing or [])
    gaps.extend([
        "FOUR_COMPATIBLE_QUARTER_COLUMNS",
        "PRINTED_PARENT_BOOK_EQUITY",
        "SEPARATED_INTEREST_BEARING_DEBT",
        "VSDC_OR_EXCHANGE_LISTING_CERTIFICATE",
        "PROOF_OF_NO_ISSUANCE_AFTER_THE_QUOTED_TRADE_DATE",
    ])
    thesis = []
    if cap.get("eligibility") == "CONDITIONAL_RESEARCH_ESTIMATE":
        thesis.append(
            "A conditional research capitalization can be stated because the price session is on or after "
            "the filing's quoted dividend trade date and the share-count cross-foot is exact."
        )
    if interim.get("eligibility") == "CONDITIONAL_RESEARCH_ESTIMATE":
        thesis.append(
            "Parent profit in the reported column cross-foots to total profit, so a price-to-that-column "
            "ratio can be shown with an interim label."
        )
    counter = [
        "One blocked strict multiple does not remove the other labeled research figures.",
        "The share count is not current-common-outstanding authority.",
        "No target price or probability is implied.",
    ]
    if profile.get("incompatible_pre_dividend_market_cap"):
        counter.append("The pre-dividend share count under the post-trade price is unusable.")
    findings = list((bridge or {}).get("findings") or [])
    for item in findings:
        if item.get("name") == "CONSOLIDATED_PARENT_VERSUS_SEPARATE_PROFIT" and item.get("same_number") is False:
            counter.append("Consolidated parent profit and separate profit are different scopes and are not substitutes.")
        if item.get("name") == "QUARTER_IS_NOT_YEAR_TO_DATE":
            counter.append("The quarter is not added to the nine-month column and is not multiplied into a year.")
    return {
        "contract_version": CONTRACT_VERSION,
        "ticker": profile.get("ticker"),
        "fitness": CONDITIONAL if cap.get("value") or interim.get("value") else DESCRIPTIVE,
        "descriptive_evidence": {
            "statement_cross_foots": profile.get("statement_cross_foots"),
            "scope_period_findings": findings,
        },
        "conditional_interpretation": {
            "market_cap_vnd": profile.get("market_cap_vnd"),
            "market_cap_eligibility": cap.get("eligibility"),
            "interim_parent_profit_multiple": interim.get("value"),
            "interim_parent_profit_period": interim.get("period"),
            "total_equity_multiple": _use(profile, "price_over_total_equity_including_nci").get("value"),
            "research_price_vnd_per_share": (profile.get("price") or {}).get("research_vnd_per_share"),
            "source_unit_verified": (profile.get("price") or {}).get("source_unit_verified"),
            "research_shares": (profile.get("share_basis") or {}).get("research_shares"),
            "cash_conversion": profile.get("cash_conversion"),
        },
        "strict_authority": {
            "strict_decision_eligible": False,
            "execution_eligible": False,
            "official_fact_admitted": False,
            "is_actionable": False,
            "target_price": None,
            "probability": None,
        },
        "thesis": thesis or ["No conditional capitalization is supported. Descriptive statement relations still stand."],
        "counter_thesis": counter,
        "reading_notes": _lines(profile),
        "missing": gaps,
        "catalysts": ["NO_CATALYST_EVIDENCE_SUPPLIED"],
        "risks": [
            "SHARE_COUNT_CONTINUITY_AFTER_THE_FILING_IS_UNPROVEN",
            "PRICE_ADJUSTMENT_BASIS_UNRESOLVED",
            "INTERIM_EARNINGS_ARE_NOT_A_FULL_YEAR",
        ],
        "invalidation": [
            "A later official share count that differs from the same-filing post-dividend count.",
            "Evidence that the price session is before the quoted dividend trade date.",
            "A same-scope quarter set that replaces the interim column as the earnings base.",
            "A printed parent-book equity line, which would replace the total-equity ratio rather than rename it.",
        ],
        "profile": profile,
        "bridge": bridge,
    }


def case_from_annual_context(
    *,
    ticker: str,
    canonical_facts: list[Mapping[str, Any]],
    blocked: list[Mapping[str, Any]] | None = None,
    press_highlights: list[Mapping[str, Any]] | None = None,
    document_sha256: str | None = None,
    knowledge_available_at: str | None = None,
) -> dict[str, Any]:
    """Qualified annual facts stay historical. A press highlight never becomes a statement fact."""
    facts = []
    for row in canonical_facts:
        if row.get("factual_status") != "qualified" and row.get("research_status") != "qualified":
            continue
        facts.append({
            "metric": row.get("metric"),
            "value": row.get("value"),
            "period": row.get("period"),
            "period_type": row.get("period_type"),
            "scope": row.get("scope"),
            "line_code": row.get("line_code"),
            "currency": row.get("currency"),
            "audit_or_review_status": row.get("audit_or_review_status"),
            "fitness": DESCRIPTIVE,
            "valuation_use": "NOT_PERMITTED_AUDITED_ANNUAL_CONTEXT",
        })
    equity = next((row for row in facts if row.get("metric") == "shareholders_equity"), None)
    press = []
    for item in press_highlights or []:
        press.append({
            "status": PRESS,
            "text": item.get("text"),
            "used_as_statement_fact": False,
            "valuation_use": "CLOSED",
        })
    missing = [
        "CURRENT_PERIOD_REVIEWED_OR_AUDITED_INCOME",
        "PARENT_PROFIT_AFTER_TAX",
        "OPERATING_CASH_FLOW",
        "CASH_AND_DEBT",
        "CURRENT_COMMON_SHARES",
        "PRICE_FOR_THIS_RESEARCH_DATE",
    ]
    notes = [
        "Qualified annual facts are historical context. They do not open a current multiple.",
    ]
    if equity is not None:
        notes.append(
            "Line 400 shareholders' equity is not used as parent-shareholder book. "
            "No P/B is calculated."
        )
    if any(row.get("metric") == "revenue" for row in facts):
        notes.append("Annual revenue is descriptive. It is not a TTM sales base.")
    return {
        "contract_version": CONTRACT_VERSION,
        "ticker": ticker.upper(),
        "fitness": DESCRIPTIVE if facts else UNAVAILABLE,
        "document_sha256": document_sha256,
        "knowledge_available_at": knowledge_available_at,
        "descriptive_evidence": {"canonical_facts": facts, "blocked": list(blocked or [])},
        "conditional_interpretation": {
            "market_cap_vnd": None,
            "reason": "NO_CONDITIONAL_PRICE_OR_SHARE_BASIS_SUPPLIED",
        },
        "press_not_statement": press,
        "strict_authority": {
            "strict_decision_eligible": False,
            "execution_eligible": False,
            "official_fact_admitted": False,
            "is_actionable": False,
            "target_price": None,
            "probability": None,
        },
        "thesis": [
            "The usable research statement is the audited annual context that actually qualified. "
            "Current-period earnings, cash flow and valuation remain open questions."
        ] if facts else ["No qualified annual fact was supplied."],
        "counter_thesis": [
            "An investor highlight or a later operating commentary is not a substitute for the missing statement lines.",
            "Ambiguous parent-profit digits stay blocked rather than repaired.",
        ],
        "reading_notes": notes,
        "missing": missing,
        "catalysts": ["NO_CATALYST_EVIDENCE_SUPPLIED"],
        "risks": ["CURRENT_PERIOD_FINANCIAL_CONDITION_IS_NOT_IN_THIS_PACKET"],
        "invalidation": [
            "A later reviewed or audited statement for the current period that qualifies the missing lines.",
            "A printed parent-profit figure that replaces the blocked ambiguous line.",
        ],
    }


def case_from_supplied_inputs(*, ticker: str, entity: str, inputs: Mapping[str, Any]) -> dict[str, Any]:
    """Adapter for a valuation record that already carries retained research inputs."""
    if inputs.get("canonical_facts"):
        return case_from_annual_context(
            ticker=ticker,
            canonical_facts=list(inputs.get("canonical_facts") or []),
            blocked=list(inputs.get("blocked") or []),
            press_highlights=list(inputs.get("press_highlights") or []),
            document_sha256=inputs.get("document_sha256"),
            knowledge_available_at=inputs.get("knowledge_available_at"),
        )
    profile = industrial_research_profile(
        ticker=ticker,
        price=inputs.get("price") or {},
        share_components=inputs.get("share_components") or {},
        facts=inputs.get("facts") or {},
        provider_share=inputs.get("provider_share"),
        entity=entity if entity not in {None, "", "unknown"} else inputs.get("entity") or "corporate",
    )
    bridge = None
    if inputs.get("bridge_rows"):
        bridge = scope_and_period_bridge(list(inputs["bridge_rows"]))
    case = case_from_industrial_profile(profile, bridge=bridge, missing=list(inputs.get("missing") or []))
    case["attached_without_changing_strict_metrics"] = True
    return case
