"""Owner research case from already qualified or candidate financial evidence.

The case repeats deterministic labels. It does not invent a target price, a
probability, a TTM multiple, or a parent-book ratio from total equity.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from collections import Counter
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Mapping

from stocklookup_core.evidence.field_identity import stable_id
from stocklookup_core.valuation.conditional_research_valuation import (
    derive_parent_equity_research,
    financing_research,
    free_cash_flow_research,
    industrial_research_profile,
    known_by,
    printed_cash_to_earnings,
    scope_and_period_bridge,
    trailing_twelve_month_earnings,
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

_REVIEWED_EXTRACTION = {
    "NATIVE_TEXT_LOCATED": ("NATIVE_TEXT", "NATIVE_TEXT_CROSS_FOOT"),
    "PAGE_IMAGE_READ_CONFIRMED": ("SCANNED_PAGE_VISUAL",),
    "PAGE_IMAGE_READ_AND_CROSS_FOOT_CONFIRMED": ("SCANNED_PAGE_VISUAL", "SCANNED_PAGE_VISUAL_CROSS_FOOT"),
}


def case_from_reviewed_evidence(
    *, ticker: str, rows: list[Mapping[str, Any]], cutoff: str, basis_limit: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Use only independently reviewed numeric rows from an already byte-bound packet."""
    evidence = []
    for row in rows:
        time_state = known_by(row, cutoff)
        extraction = row["evidence_quality"]
        reviewed = extraction in _REVIEWED_EXTRACTION.get(row["verification"], ())
        state = (f"KNOWLEDGE_{time_state}" if time_state != "KNOWN" else
                 "REVIEWED_RESEARCH" if reviewed else "CANDIDATE_EXCLUDED_FROM_CALCULATION")
        evidence.append({**row, "calculation_state": state})

    usable = [row for row in evidence if row["calculation_state"] == "REVIEWED_RESEARCH"
              and row["currency"] == "VND"]
    periods = {}
    for row in usable:
        periods.setdefault(row["reporting_period"], []).append(row)

    def unique(items, identity):
        matches = [row for row in items if row["accounting_identity"] == identity]
        return matches[0] if len(matches) == 1 else {}

    metrics = {}
    for period, items in sorted(periods.items()):
        parent = unique(items, "PARENT_PROFIT_AFTER_TAX")
        cash = unique(items, "OPERATING_CASH_FLOW")
        total_equity = unique(items, "CAPITAL_AND_RESERVES_INCLUDING_NCI") or unique(items, "TOTAL_EQUITY_INCLUDING_NCI")
        nci = unique(items, "NON_CONTROLLING_INTERESTS")
        capex_rows = [row for row in items if row["accounting_identity"].startswith("CAPEX_")]
        period_metrics = {}
        if parent or cash:
            period_metrics["cash_to_parent_profit"] = printed_cash_to_earnings(parent, cash)
        if cash or capex_rows:
            period_metrics["operating_cash_less_printed_purchases"] = free_cash_flow_research(
                cash, capex_rows[0] if len(capex_rows) == 1 else {},
            )
        if total_equity or nci:
            period_metrics["derived_parent_equity"] = derive_parent_equity_research(total_equity, nci)
        financing_rows = [row for row in items if row["accounting_identity"] == "CASH_AND_EQUIVALENTS"
                          or row["accounting_identity"].endswith(("LOANS_AND_FINANCE_LEASES", "LOANS_LEASE_CONTENT_UNKNOWN"))]
        if financing_rows:
            period_metrics["financing"] = financing_research(financing_rows)
        if period_metrics:
            metrics[period] = period_metrics

    earnings = trailing_twelve_month_earnings(
        usable, identity="PARENT_PROFIT_AFTER_TAX",
        allow_conditional_presentation_bridge=(
            bool(basis_limit) and basis_limit.get("reason_code") == "ANNUAL_AND_INTERIM_PRESENTATION_DIFFER"
        ),
    )
    if any(row["accounting_identity"] == "PARENT_PROFIT_AFTER_TAX"
           and row["calculation_state"] != "REVIEWED_RESEARCH" for row in evidence):
        earnings["reason_codes"].append("PARENT_PROFIT_CANDIDATES_EXCLUDED")
    if basis_limit and earnings["ttm"] is None:
        earnings["reason_codes"].append(basis_limit["reason_code"])
    body = {
        "contract_version": CONTRACT_VERSION,
        "ticker": ticker,
        "research_cutoff": cutoff,
        "basis_limit": basis_limit,
        "evidence_rows": evidence,
        "metrics_by_period": metrics,
        "parent_earnings": earnings,
        "valuation": {
            "price_vnd_per_share": None, "market_cap_vnd": None, "pe_ttm": None, "pb_parent": None,
            "ev_ebitda": None, "reason_codes": ["NO_SOURCE_BOUND_SESSION_CLOSE_WITH_VERIFIED_MONETARY_UNIT"],
        },
        "strict_authority": {
            "official_fact_admitted": False, "strict_decision_eligible": False, "execution_eligible": False,
            "is_actionable": False, "target_price": None, "probability": None,
        },
    }
    return {**body, "case_identity": "conditional_investment_case:" + stable_id(body)}


COHORT_CONTRACT = "current_statement_research_cohort/v1"
_INDUSTRIAL_METRICS = (
    ("10", "net_revenue"),
    ("20", "gross_profit"),
    ("50", "profit_before_tax"),
    ("60", "group_profit_after_tax"),
    ("61", "parent_profit_after_tax"),
    ("62", "noncontrolling_profit"),
)
_YOY_PAIRS = (("2026-Q3", "2025-Q3"), ("2026-9M", "2025-9M"))


def _ratio(numerator: int, denominator: int) -> dict[str, Any]:
    if denominator == 0:
        return {"status": "NOT_COMPUTED", "reason_codes": ["ZERO_DENOMINATOR"], "rounded_6dp": None}
    return {
        "status": "COMPUTED",
        "numerator": numerator,
        "denominator": denominator,
        "rounded_6dp": format(round(numerator / denominator, 6), ".6f"),
        "reason_codes": [],
    }


def _yoy(current: int, prior: int) -> dict[str, Any]:
    if prior == 0:
        return {"status": "NOT_COMPUTED", "reason_codes": ["ZERO_BASE"], "percent": None}
    return {
        "status": "COMPUTED",
        "percent": round(100 * (current / prior - 1), 2),
        "method": "SAME_SCOPE_REPORTED_COLUMN_OVER_PRIOR_COLUMN",
        "reason_codes": [],
    }


def _measure(**fields: Any) -> dict[str, Any]:
    return {
        "official_fact_admitted": False,
        "historical_pit": "UNKNOWN",
        "valuation_use": "CLOSED",
        "strict_consumer_usable": False,
        "attribution": "SOURCE_ATTRIBUTED",
        "annualized": False,
        "ttm": False,
        **fields,
    }


def _industrial_columns(source: Any) -> list[dict[str, Any]]:
    """One issuer's already cross-footed income columns. A failed column emits nothing usable."""
    measures: list[dict[str, Any]] = []
    accepted: dict[str, Mapping[str, int]] = {}
    for period, lines, kind in source["columns"]:
        reasons = source["cross_foot"](lines)
        common = {
            "ticker": source["ticker"], "period": period, "period_kind": kind,
            "analysis_family": "INDUSTRIAL", "statement_scope": "consolidated",
            "unit": "VND", "unit_scale": 1, "currency": "VND",
            "evidence_layer": source["evidence_layer"], "source_sha256": source["sha256"],
            "source_url": source["source_url"], "audit_or_review_status": "unreviewed",
        }
        if reasons:
            for _code, metric in _INDUSTRIAL_METRICS:
                measures.append(_measure(
                    **common, metric=metric, status="BLOCKED", value=None,
                    use_scope="NOT_AVAILABLE", reason_codes=list(reasons),
                ))
            continue
        accepted[period] = lines
        for code, metric in _INDUSTRIAL_METRICS:
            measures.append(_measure(
                **common, metric=metric, status="USABLE", value=lines[code],
                use_scope="CURRENT_RESEARCH", reason_codes=[],
                statement_line=code,
            ))
        for metric, numerator, denominator in (
            ("gross_margin", lines["20"], lines["10"]),
            ("group_profit_margin", lines["60"], lines["10"]),
            ("parent_profit_margin", lines["61"], lines["10"]),
        ):
            ratio = _ratio(numerator, denominator)
            measures.append(_measure(
                **common, metric=metric, status="USABLE" if ratio["status"] == "COMPUTED" else "BLOCKED",
                value=ratio.get("rounded_6dp"), use_scope="CURRENT_RESEARCH" if ratio["status"] == "COMPUTED" else "NOT_AVAILABLE",
                reason_codes=list(ratio["reason_codes"]), numerator=numerator, denominator=denominator,
                identity=f"{metric.upper()}_OVER_NET_REVENUE",
            ))
    for current, prior in _YOY_PAIRS:
        for _code, metric in _INDUSTRIAL_METRICS:
            base = {
                "ticker": source["ticker"], "period": f"{current}_VS_{prior}", "period_kind": "YEAR_OVER_YEAR",
                "analysis_family": "INDUSTRIAL", "statement_scope": "consolidated", "unit": "PERCENT",
                "unit_scale": 1, "currency": "VND", "metric": f"{metric}_yoy",
                "evidence_layer": source["evidence_layer"], "source_sha256": source["sha256"],
                "source_url": source["source_url"], "audit_or_review_status": "unreviewed",
            }
            if current not in accepted or prior not in accepted:
                measures.append(_measure(
                    **base, status="BLOCKED", value=None, use_scope="NOT_AVAILABLE",
                    reason_codes=["PRIOR_OR_CURRENT_COLUMN_ABSENT_OR_REJECTED"],
                ))
                continue
            change = _yoy(accepted[current][_code], accepted[prior][_code])
            measures.append(_measure(
                **base, status="USABLE" if change["status"] == "COMPUTED" else "BLOCKED",
                value=change.get("percent"),
                use_scope="CURRENT_RESEARCH" if change["status"] == "COMPUTED" else "NOT_AVAILABLE",
                reason_codes=list(change["reason_codes"]), method=change.get("method"),
            ))
    return measures


def _period_kind(period: str) -> str:
    text = str(period)
    if text.endswith("Q3"):
        return "STANDALONE_QUARTER"
    if text.endswith("9M"):
        return "CUMULATIVE_NINE_MONTH"
    return "REPORTED_PERIOD"


def _named_rows(packet: Mapping[str, Any], *, family: str, scope: str, unit: str, scale: int) -> list[dict[str, Any]]:
    measures = []
    for row in packet.get("observations") or []:
        measures.append(_measure(
            ticker=packet["ticker"], period=row["period"], period_kind=_period_kind(str(row["period"])),
            analysis_family=family, statement_scope=scope, unit=unit, unit_scale=scale,
            currency="VND", metric=row["metric"], status="USABLE", value=row["value"],
            use_scope="CURRENT_RESEARCH", reason_codes=[], evidence_layer=packet["evidence_layer"],
            source_sha256=packet["sha256"], source_url=packet["source_url"],
            audit_or_review_status=packet.get("audit_or_review_status"),
        ))
    return measures


def build_statement_research_cohort() -> dict[str, Any]:
    """Project retained statement readings into one current-research comparison.

    The readings already live in ``q3_2026_successor_research``. This function does
    not read a PDF, admit an official fact, annualize a nine-month column, or build
    a second financial store. Banks are absent because no retained bank column is
    cross-footed here. Securities and the finance company stay outside industrial ratios.
    """
    from stocklookup_core.financial import q3_2026_successor_research as source

    hpg_columns = (
        ("2026-Q3", source.HPG_Q3_2026_LINES, "STANDALONE_QUARTER"),
        ("2026-9M", source.HPG_9M_2026_LINES, "CUMULATIVE_NINE_MONTH"),
    )
    pow_columns = tuple(
        (period, dict(zip(source.FOOT_CODES, values, strict=True)),
         "STANDALONE_QUARTER" if period.endswith("Q3") else "CUMULATIVE_NINE_MONTH")
        for period, values in source.POW_INCOME_COLUMNS.items()
    )
    pan_columns = tuple(
        (period, dict(zip(source.FOOT_CODES, values, strict=True)),
         "STANDALONE_QUARTER" if period.endswith("Q3") else "CUMULATIVE_NINE_MONTH")
        for period, values in source.PAN_INCOME_COLUMNS.items()
    )
    industrial_sources = (
        {"ticker": "HPG", "columns": hpg_columns, "cross_foot": source.income_cross_foot,
         "sha256": source.HPG_CONSOLIDATED_Q3_SHA256, "source_url": source.HPG_CONSOLIDATED_Q3_URL,
         "evidence_layer": "VISUAL_READ_NOT_BYTE_NATIVE"},
        {"ticker": "POW", "columns": pow_columns, "cross_foot": source.income_cross_foot,
         "sha256": source.POW_Q3_SHA256, "source_url": source.POW_Q3_URL,
         "evidence_layer": "VISUAL_READ_NOT_BYTE_NATIVE"},
        {"ticker": "PAN", "columns": pan_columns, "cross_foot": source.income_cross_foot,
         "sha256": source.PAN_Q3_SHA256, "source_url": source.PAN_Q3_URL,
         "evidence_layer": "VISUAL_READ_NOT_BYTE_NATIVE"},
    )
    measures: list[dict[str, Any]] = []
    for item in industrial_sources:
        measures.extend(_industrial_columns(item))
    for period, lines in source.POW_OCF_COLUMNS.items():
        reasons = source.operating_cash_flow_cross_foot(lines)
        measures.append(_measure(
            ticker="POW", period=period, period_kind="CUMULATIVE_NINE_MONTH",
            analysis_family="INDUSTRIAL", statement_scope="consolidated", unit="VND",
            unit_scale=1, currency="VND", metric="operating_cash_flow",
            status="USABLE" if not reasons else "BLOCKED",
            value=lines["20"] if not reasons else None,
            use_scope="CURRENT_RESEARCH" if not reasons else "NOT_AVAILABLE",
            reason_codes=reasons, evidence_layer="VISUAL_READ_NOT_BYTE_NATIVE",
            source_sha256=source.POW_Q3_SHA256, source_url=source.POW_Q3_URL,
            audit_or_review_status="unreviewed", statement_line="20",
            identity="INDIRECT_OPERATING_CASH_FLOW_NOT_A_QUARTER",
        ))
    measures.append(_measure(
        ticker="POW", period="2026-9M", period_kind="CUMULATIVE_NINE_MONTH",
        analysis_family="INDUSTRIAL", statement_scope="consolidated", unit="VND",
        unit_scale=1, currency="VND", metric="interest_bearing_debt", status="BLOCKED",
        value=None, use_scope="NOT_AVAILABLE",
        reason_codes=["LEASE_INCLUSIVE_LINES_NOT_SEPARATED"],
        evidence_layer="VISUAL_READ_NOT_BYTE_NATIVE", source_sha256=source.POW_Q3_SHA256,
        source_url=source.POW_Q3_URL, audit_or_review_status="unreviewed",
    ))
    ssi = source.ssi_consolidated_page_research()
    measures.extend(_named_rows(
        ssi, family="SECURITIES", scope="consolidated", unit="VND", scale=1,
    ))
    measures.append(_measure(
        ticker="SSI", period="2026-9M", period_kind="CUMULATIVE_NINE_MONTH",
        analysis_family="SECURITIES", statement_scope="consolidated", unit="VND",
        unit_scale=1, currency="VND", metric="profit_after_tax", status="BLOCKED",
        value=None, use_scope="NOT_AVAILABLE", reason_codes=["OCR_DIGIT_AMBIGUOUS_NOT_EMITTED"],
        evidence_layer=ssi["evidence_layer"], source_sha256=ssi["sha256"],
        source_url=ssi["source_url"], audit_or_review_status="unreviewed",
    ))
    measures.append(_measure(
        ticker="SSI", period="2026-Q3", period_kind="STANDALONE_QUARTER",
        analysis_family="SECURITIES", statement_scope="consolidated", unit="RATIO",
        unit_scale=1, currency="VND", metric="industrial_profit_margin", status="NOT_APPLICABLE",
        value=None, use_scope="NOT_AVAILABLE", reason_codes=["SECURITIES_TEMPLATE_IS_NOT_INDUSTRIAL"],
        evidence_layer=ssi["evidence_layer"], source_sha256=ssi["sha256"],
        source_url=ssi["source_url"], audit_or_review_status="unreviewed",
    ))
    evf = source.evf_reviewed_page_research()
    measures.extend(_named_rows(
        evf, family="FINANCE_COMPANY", scope="separate", unit="MILLION_VND", scale=1000000,
    ))
    measures.append(_measure(
        ticker="EVF", period="2026-Q3", period_kind="STANDALONE_QUARTER",
        analysis_family="FINANCE_COMPANY", statement_scope="separate", unit="MILLION_VND",
        unit_scale=1000000, currency="VND", metric="net_income", status="BLOCKED",
        value=None, use_scope="NOT_AVAILABLE", reason_codes=["NO_STANDALONE_QUARTER_COLUMN"],
        evidence_layer=evf["evidence_layer"], source_sha256=evf["sha256"],
        source_url=evf["source_url"], audit_or_review_status="reviewed",
    ))
    for ticker in ("HPG", "POW", "PAN", "SSI", "EVF"):
        measures.append(_measure(
            ticker=ticker, period="TTM", period_kind="TRAILING_TWELVE_MONTHS",
            analysis_family="UNSET", statement_scope="UNSET", unit="VND", unit_scale=1,
            currency="VND", metric="profit_after_tax_ttm", status="BLOCKED", value=None,
            use_scope="NOT_AVAILABLE", reason_codes=["NO_FOUR_COMPATIBLE_STANDALONE_QUARTERS"],
            evidence_layer="NOT_DERIVED", source_sha256=None, source_url=None,
            audit_or_review_status=None,
        ))
        measures.append(_measure(
            ticker=ticker, period="CURRENT", period_kind="UNSET", analysis_family="UNSET",
            statement_scope="UNSET", unit="MULTIPLE", unit_scale=1, currency="VND",
            metric="research_multiple", status="BLOCKED", value=None, use_scope="NOT_AVAILABLE",
            reason_codes=["VALUATION_CLOSED_NO_QUALIFIED_PRICE_AND_SHARE_BASE"],
            evidence_layer="NOT_DERIVED", source_sha256=None, source_url=None,
            audit_or_review_status=None,
        ))

    def _usable(ticker: str, period: str, metric: str) -> dict[str, Any] | None:
        found = [row for row in measures if row["ticker"] == ticker and row["period"] == period
                 and row["metric"] == metric and row["status"] == "USABLE"]
        return found[0] if len(found) == 1 else None

    margin_rows = []
    for ticker in ("HPG", "PAN", "POW"):
        row = _usable(ticker, "2026-Q3", "parent_profit_margin")
        if row is not None:
            margin_rows.append({"ticker": ticker, "rounded_6dp": row["value"],
                                "numerator": row["numerator"], "denominator": row["denominator"]})
    revenue_yoy = []
    for ticker in ("HPG", "PAN", "POW"):
        row = _usable(ticker, "2026-Q3_VS_2025-Q3", "net_revenue_yoy")
        if row is not None:
            revenue_yoy.append({"ticker": ticker, "percent": row["value"]})
    parent_yoy = []
    for ticker in ("HPG", "PAN", "POW"):
        row = _usable(ticker, "2026-Q3_VS_2025-Q3", "parent_profit_after_tax_yoy")
        if row is not None:
            parent_yoy.append({"ticker": ticker, "percent": row["value"]})
    pow_ocf = _usable("POW", "2026-9M", "operating_cash_flow")
    pow_ocf_prior = _usable("POW", "2025-9M", "operating_cash_flow")
    pow_profit = _usable("POW", "2026-9M", "group_profit_after_tax")
    if pow_ocf and pow_profit and pow_profit["value"]:
        cash_conversion = _ratio(pow_ocf["value"], pow_profit["value"])
        cash_conversion["identity"] = "NINE_MONTH_OPERATING_CASH_FLOW_OVER_GROUP_PROFIT_AFTER_TAX"
        cash_conversion["not_parent_cash_conversion"] = True
    else:
        cash_conversion = {
            "status": "NOT_COMPUTED",
            "identity": "NINE_MONTH_OPERATING_CASH_FLOW_OVER_GROUP_PROFIT_AFTER_TAX",
            "not_parent_cash_conversion": True,
            "reason_codes": ["GROUP_PROFIT_COLUMN_FAILED_IDENTITY" if pow_ocf else "OPERATING_CASH_FLOW_UNUSABLE"],
            "operating_cash_flow_value_vnd": None if pow_ocf is None else pow_ocf["value"],
        }
    identity_residuals = []
    residual_sources = (
        ("HPG", {"2026-Q3": source.HPG_Q3_2026_LINES, "2026-9M": source.HPG_9M_2026_LINES}),
        ("POW", {period: dict(zip(source.FOOT_CODES, values, strict=True))
                 for period, values in source.POW_INCOME_COLUMNS.items()}),
        ("PAN", {period: dict(zip(source.FOOT_CODES, values, strict=True))
                 for period, values in source.PAN_INCOME_COLUMNS.items()}),
    )
    for ticker, columns in residual_sources:
        for period, lines in columns.items():
            reasons = source.income_cross_foot(lines)
            if "LINE_60_DOES_NOT_FOOT_61_PLUS_62" in reasons or "LINE_60_DOES_NOT_FOOT_50_MINUS_51_MINUS_52" in reasons:
                identity_residuals.append({
                    "ticker": ticker,
                    "period": period,
                    "reason_codes": reasons,
                    "group_minus_parent_and_nci_vnd": lines["60"] - (lines["61"] + lines["62"]),
                    "group_minus_pretax_bridge_vnd": lines["60"] - (lines["50"] - lines["51"] - lines["52"]),
                    "use": "COLUMN_WITHHELD_RESIDUAL_NOT_REPAIRED",
                })
    ocf_yoy = None
    if pow_ocf and pow_ocf_prior:
        ocf_yoy = _yoy(pow_ocf["value"], pow_ocf_prior["value"])
        ocf_yoy["period"] = "2026-9M_VS_2025-9M"
        ocf_yoy["identity"] = "CUMULATIVE_NINE_MONTH_OPERATING_CASH_FLOW"
    pow_profit_prior = _usable("POW", "2025-9M", "group_profit_after_tax")
    prior_cash_conversion = None
    if pow_ocf_prior and pow_profit_prior and pow_profit_prior["value"]:
        prior_cash_conversion = _ratio(pow_ocf_prior["value"], pow_profit_prior["value"])
        prior_cash_conversion["identity"] = "NINE_MONTH_OPERATING_CASH_FLOW_OVER_GROUP_PROFIT_AFTER_TAX"
        prior_cash_conversion["period"] = "2025-9M"
        prior_cash_conversion["not_parent_cash_conversion"] = True
    segment_sum = sum(value for _name, value in source.PAN_SEGMENT_EXTERNAL_REVENUE)
    pan_line_10 = source.PAN_INCOME_COLUMNS["2026-9M"][source.FOOT_CODES.index("10")]
    brokerage = _usable("SSI", "2026-Q3", "brokerage_revenue")
    brokerage_prior = _usable("SSI", "2025-Q3", "brokerage_revenue")
    interest = _usable("SSI", "2026-Q3", "interest_expense")
    interest_prior = _usable("SSI", "2025-Q3", "interest_expense")
    loan_interest = _usable("SSI", "2026-Q3", "loan_and_receivable_interest")
    loan_interest_prior = _usable("SSI", "2025-Q3", "loan_and_receivable_interest")
    readings = {
        "industrial_q3_parent_profit_margin": margin_rows,
        "industrial_q3_revenue_yoy_percent": revenue_yoy,
        "industrial_q3_parent_profit_yoy_percent": parent_yoy,
        "pow_nine_month_cash_conversion": cash_conversion,
        "pow_prior_nine_month_cash_conversion": prior_cash_conversion,
        "pow_nine_month_operating_cash_flow_yoy": ocf_yoy,
        "industrial_identity_residuals": identity_residuals,
        "pan_segment_versus_rejected_income_line": {
            "segment_external_revenue_sum_vnd": segment_sum,
            "printed_nine_month_line_10_vnd": pan_line_10,
            "difference_vnd": pan_line_10 - segment_sum,
            "income_column_status": "REJECTED" if not _usable("PAN", "2026-9M", "net_revenue") else "USABLE",
            "use": "SEGMENT_NOTE_IS_NOT_A_REPLACEMENT_REVENUE",
        },
        "ssi_q3_component_yoy_percent": {
            "brokerage_revenue": None if not brokerage or not brokerage_prior else _yoy(brokerage["value"], brokerage_prior["value"]),
            "interest_expense": None if not interest or not interest_prior else _yoy(interest["value"], interest_prior["value"]),
            "loan_and_receivable_interest": None if not loan_interest or not loan_interest_prior else _yoy(
                loan_interest["value"], loan_interest_prior["value"]),
        },
        "evf_nine_month_yoy_percent": {
            "net_income": evf["net_income_yoy_pct"],
            "pre_provision_profit": evf["pre_provision_profit_yoy_pct"],
            "credit_loss_provision": evf["credit_loss_provision_yoy_pct"],
            "unit": "MILLION_VND",
            "statement_scope": "separate",
            "standalone_quarter": False,
        },
    }
    usable = [row for row in measures if row["status"] == "USABLE"]
    blocked = [row for row in measures if row["status"] != "USABLE"]
    coverage = {
        "issuer_period_metric_records": len(measures),
        "source_identity_present": sum(bool(row.get("source_sha256")) and bool(row.get("ticker")) for row in measures),
        "accounting_semantics_present": sum(
            bool(row.get("period_kind")) and bool(row.get("statement_scope")) and bool(row.get("unit"))
            for row in measures
        ),
        "current_research_usable": len(usable),
        "blocked_or_not_applicable": len(blocked),
        "official_fact_admitted_count": 0,
        "companies_in_industrial_margin_comparison": len(margin_rows),
        "valuation_measures_usable": sum(row["metric"] == "research_multiple" and row["status"] == "USABLE" for row in measures),
        "ttm_measures_usable": sum(row["metric"] == "profit_after_tax_ttm" and row["status"] == "USABLE" for row in measures),
    }
    higher = max(margin_rows, key=lambda row: (row["numerator"] / row["denominator"], row["ticker"])) if margin_rows else None
    lower = min(margin_rows, key=lambda row: (row["numerator"] / row["denominator"], row["ticker"])) if margin_rows else None
    body = {
        "contract_version": COHORT_CONTRACT,
        "use_scope": "CURRENT_RESEARCH",
        "attribution": "SOURCE_ATTRIBUTED",
        "evidence_role": "RETAINED_STATEMENT_READING",
        "not_provider_market_data": True,
        "official_fact_admitted": False,
        "historical_pit": "UNKNOWN",
        "valuation_use": "CLOSED",
        "execution_eligible": False,
        "is_actionable": False,
        "target_price": None,
        "probability": None,
        "ordinal_rank": None,
        "financial_v2_authority_unchanged": "2026-09-05.1",
        "issuers": ["EVF", "HPG", "PAN", "POW", "SSI"],
        "families": {
            "INDUSTRIAL": ["HPG", "PAN", "POW"],
            "SECURITIES": ["SSI"],
            "FINANCE_COMPANY": ["EVF"],
            "BANK": [],
        },
        "measures": measures,
        "readings": readings,
        "coverage": coverage,
        "comparison": {
            "question": "CONSOLIDATED_STANDALONE_2026_Q3_PARENT_PROFIT_OVER_NET_REVENUE",
            "higher_on_this_ratio": None if higher is None else higher["ticker"],
            "lower_on_this_ratio": None if lower is None else lower["ticker"],
            "does_not_establish": [
                "OVERALL_FINANCIAL_STRENGTH", "PEER_RANK", "TARGET_PRICE", "OFFICIAL_FACT", "VALUATION",
            ],
        },
        "thesis": [
            "HPG, PAN and POW can be compared only on the consolidated industrial columns that cross-foot.",
            "SSI brokerage, interest expense and loan interest are securities components, not industrial revenue or profit margins.",
            "EVF nine-month profit moved differently from pre-provision profit; the change is not identified as spread expansion.",
        ],
        "counter_thesis": [
            "A higher parent-profit margin on one unreviewed quarter is not a ranking and is not a valuation.",
            "Nine-month figures are cumulative. They are not multiplied into a year and are not a trailing twelve months.",
            "Group profit is not parent profit. Operating cash flow over group profit is not parent cash conversion.",
            "PAN's nine-month income column stays out when it does not cross-foot. The segment note does not replace it.",
            "No qualified price and share base is attached, so no P/E, P/B or EV multiple is computed.",
            "These readings are not official facts and have no historical point-in-time clock.",
        ],
        "unavailable": [
            "BANK_TEMPLATE", "INTEREST_BEARING_DEBT", "TTM", "RESEARCH_MULTIPLE",
            "SSI_NINE_MONTH_PROFIT_AFTER_TAX", "EVF_STANDALONE_QUARTER", "PAN_NINE_MONTH_INCOME_WHEN_REJECTED",
        ],
    }
    return {**body, "cohort_identity": "current_statement_research_cohort:" + stable_id(body)}


STRUCTURED_INPUT_CONTRACT = "structured_financial_research_input/v1"
_REQUIRED_INPUT_FIELDS = (
    "ticker", "period_label", "consolidation", "unit", "item", "value", "statement",
    "source", "source_file", "source_sha256", "period_year", "period_kind", "period_basis",
)
_PERIOD_TOKENS = {
    ("Q1", "quarterly_discrete"): ("Q1", "STANDALONE_QUARTER"),
    ("Q2", "quarterly_discrete"): ("Q2", "STANDALONE_QUARTER"),
    ("Q3", "quarterly_discrete"): ("Q3", "STANDALONE_QUARTER"),
    ("Q4", "quarterly_discrete"): ("Q4", "STANDALONE_QUARTER"),
    ("6M", "cumulative_ytd"): ("6M", "CUMULATIVE_SIX_MONTH"),
    ("9M", "cumulative_ytd"): ("9M", "CUMULATIVE_NINE_MONTH"),
    ("FY", "cumulative_ytd"): ("FY", "FISCAL_YEAR"),
}
_SCOPE_TOKENS = {"Hợp nhất": "consolidated", "Riêng": "separate", "Công ty mẹ": "separate"}
_FAMILY_MARKERS = (
    ("BANK_STATEMENT", "XV. Lợi nhuận sau thuế của cổ đông của Ngân hàng mẹ (XIII-XIV)"),
    ("SECURITIES_STATEMENT", "1.6. Doanh thu môi giới chứng khoán"),
    ("INDUSTRIAL_STATEMENT", "3. Doanh thu thuần về bán hàng và cung cấp dịch vụ"),
)
_FLOW_LABELS = {
    "INDUSTRIAL_STATEMENT": (
        ("net_revenue", "IS", "3. Doanh thu thuần về bán hàng và cung cấp dịch vụ"),
        ("gross_profit", "IS", "5. Lợi nhuận gộp về bán hàng và cung cấp dịch vụ"),
        ("profit_before_tax", "IS", "15. Tổng lợi nhuận kế toán trước thuế"),
        ("current_tax_expense", "IS", "16. Chi phí thuế TNDN hiện hành"),
        ("deferred_tax_expense", "IS", "17. Chi phí thuế TNDN hoãn lại"),
        ("group_profit_after_tax", "IS", "18. Lợi nhuận sau thuế thu nhập doanh nghiệp"),
        ("parent_profit_after_tax", "IS", "Lợi nhuận sau thuế của cổ đông của Công ty mẹ"),
        ("noncontrolling_profit", "IS", "Lợi ích của cổ đông thiểu số"),
        ("operating_cash_flow", "CF", "Lưu chuyển tiền thuần từ hoạt động kinh doanh"),
    ),
    "BANK_STATEMENT": (
        ("net_interest_income", "IS", "I. Thu nhập lãi thuần (1-2)"),
        ("pre_provision_profit", "IS", "IX. Lợi nhuận thuần từ hoạt động kinh doanh trước chi phí dự phòng rủi ro tín dụng (I+II+III+IV+V+VI+VII-VIII)"),
        ("credit_loss_provision", "IS", "X. Chi phí dự phòng rủi ro tín dụng"),
        ("group_profit_after_tax", "IS", "XIII. Lợi nhuận sau thuế (XI-XII)"),
        ("parent_profit_after_tax", "IS", "XV. Lợi nhuận sau thuế của cổ đông của Ngân hàng mẹ (XIII-XIV)"),
    ),
    "SECURITIES_STATEMENT": (
        ("brokerage_revenue", "IS", "1.6. Doanh thu môi giới chứng khoán"),
        ("loan_and_receivable_interest", "IS", "1.3. Lãi từ các khoản cho vay và phải thu"),
        ("interest_expense", "IS", "4.2. Chi phí lãi vay"),
        ("securities_net_revenue", "IS", "Doanh thu thuần"),
        ("parent_profit_after_tax", "IS", "11.1. Lợi nhuận sau thuế phân bổ cho chủ sở hữu"),
        ("operating_cash_flow", "CF", "Lưu chuyển tiền thuần từ hoạt động kinh doanh chứng khoán"),
    ),
}
_STOCK_LABELS = {
    "INDUSTRIAL_STATEMENT": (
        ("cash_and_equivalents", "BS", "I. Tiền và các khoản tương đương tiền"),
        ("total_assets", "BS", "TỔNG CỘNG TÀI SẢN"),
        ("total_liabilities", "BS", "C. NỢ PHẢI TRẢ"),
        ("borrowings_and_finance_leases_short", "BS", "11. Vay và nợ thuê tài chính ngắn hạn"),
        ("borrowings_and_finance_leases_long", "BS", "9. Vay và nợ thuê tài chính dài hạn"),
    ),
    "BANK_STATEMENT": (
        ("total_assets", "BS", "TỔNG CỘNG TÀI SẢN"),
        ("total_liabilities", "BS", "TỔNG NỢ PHẢI TRẢ"),
    ),
    "SECURITIES_STATEMENT": (
        ("cash_and_equivalents", "BS", "1. Tiền và các khoản tương đương tiền"),
        ("total_assets", "BS", "TỔNG CỘNG TÀI SẢN (270=100+200)"),
        ("total_liabilities", "BS", "A. NỢ PHẢI TRẢ (300=310+340)"),
    ),
}
_BANK_OCF_LABELS = (
    "I. Lưu chuyển tiền thuần từ hoạt động kinh doanh",
    "I - Lưu chuyển tiền thuần từ hoạt động kinh doanh",
)
_SHA256_TEXT = re.compile(r"^[0-9a-f]{64}$")


def _aware_instant(value: str | None, code: str) -> datetime | None:
    if value is None or value == "":
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(code) from exc
    if parsed.tzinfo is None:
        raise ValueError(code + "_REQUIRES_TIMEZONE")
    return parsed


def _structured_unit(text: str) -> tuple[str, int, str] | None:
    compact = " ".join(text.casefold().replace("đ", "d").split())
    if "usd" in compact and "vnd" not in compact:
        return ("USD", 1, "USD")
    if "1.000.000" in text or "1,000,000" in text or "trieu" in compact:
        return ("MILLION_VND", 1_000_000, "VND")
    if re.search(r"1\.000(?!\.)", text) or "nghin" in compact:
        return ("THOUSAND_VND", 1000, "VND")
    if compact.endswith("1 vnd") or re.search(r"(^|:\s*)1\s*vnd$", compact):
        return ("VND", 1, "VND")
    return None


def _structured_integer(text: str) -> int | None:
    token = text.strip()
    if token.startswith("(") and token.endswith(")"):
        token = "-" + token[1:-1]
    token = token.replace(",", "")
    if re.fullmatch(r"-?\d+", token):
        return int(token)
    whole = re.fullmatch(r"-?\d+\.0+", token)
    if whole is not None:
        return int(token.split(".", 1)[0])
    return None


def _blank_flag(text: str) -> bool:
    return text.strip().casefold() in {"true", "1", "yes"}


def _load_structured_rows(path: Path) -> tuple[str, list[tuple[int, dict[str, str] | None]]]:
    raw = path.read_bytes()
    digest = hashlib.sha256(raw).hexdigest()
    suffix = path.suffix.lower()
    if suffix == ".csv":
        try:
            text = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ValueError("STRUCTURED_INPUT_ENCODING") from exc
        reader = csv.DictReader(io.StringIO(text))
        if not reader.fieldnames:
            raise ValueError("STRUCTURED_INPUT_HEADER_MISSING")
        fields = [name.strip() for name in reader.fieldnames if name is not None]
        missing = [name for name in _REQUIRED_INPUT_FIELDS if name not in fields]
        if missing:
            raise ValueError("STRUCTURED_INPUT_HEADER_MISSING:" + ",".join(missing))
        rows: list[tuple[int, dict[str, str] | None]] = []
        for line_number, row in enumerate(reader, start=2):
            rows.append((line_number, {key: (row.get(key) or "").strip() for key in (*_REQUIRED_INPUT_FIELDS, "audit_status", "auditor", "audit_opinion", "vendor_publish_date", "vendor_audit_sign_date", "vendor_data_updated", "is_blank")}))
        return digest, rows
    if suffix == ".json":
        try:
            payload = json.loads(raw.decode("utf-8-sig"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("STRUCTURED_INPUT_JSON_INVALID") from exc
        if isinstance(payload, list):
            observations = payload
        elif isinstance(payload, dict) and isinstance(payload.get("observations"), list):
            observations = payload["observations"]
        else:
            raise ValueError("STRUCTURED_INPUT_JSON_SHAPE")
        rows = []
        optional = ("audit_status", "auditor", "audit_opinion", "vendor_publish_date", "vendor_audit_sign_date", "vendor_data_updated", "is_blank")
        for line_number, item in enumerate(observations, start=1):
            if not isinstance(item, dict):
                rows.append((line_number, None))
                continue
            normalized: dict[str, str] = {}
            for key in (*_REQUIRED_INPUT_FIELDS, *optional):
                value = item.get(key)
                if isinstance(value, bool):
                    normalized[key] = "true" if value else "false"
                elif value is None:
                    normalized[key] = ""
                else:
                    normalized[key] = str(value).strip()
            rows.append((line_number, normalized))
        return digest, rows
    raise ValueError("STRUCTURED_INPUT_SUFFIX")


def _accept_structured_row(line_number: int, row: dict[str, str] | None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    if row is None:
        return None, {"line_number": line_number, "reason_codes": ["ROW_NOT_AN_OBJECT"], "ticker": None, "item": None}
    missing = [name for name in _REQUIRED_INPUT_FIELDS if row.get(name, "") == "" and name not in {"value"}]
    if missing:
        return None, {"line_number": line_number, "reason_codes": ["MISSING_FIELD:" + ",".join(missing)], "ticker": row.get("ticker") or None, "item": row.get("item") or None}
    if _blank_flag(row.get("is_blank", "")):
        if row.get("value", "") not in {"", "0"} and _structured_integer(row.get("value", "")) not in {None, 0}:
            return None, {"line_number": line_number, "reason_codes": ["INCONSISTENT_BLANK_FLAG"], "ticker": row.get("ticker") or None, "item": row.get("item") or None}
        return None, None
    if row.get("value", "") == "":
        return None, None
    reasons: list[str] = []
    ticker = row["ticker"].upper()
    if not re.fullmatch(r"[A-Z0-9]{1,12}", ticker):
        reasons.append("TICKER_SHAPE")
    period = _PERIOD_TOKENS.get((row["period_kind"], row["period_basis"]))
    if period is None:
        reasons.append("INCOMPATIBLE_PERIOD")
    if not re.fullmatch(r"\d{4}", row["period_year"]):
        reasons.append("PERIOD_YEAR")
    scope = _SCOPE_TOKENS.get(row["consolidation"])
    if scope is None:
        reasons.append("UNKNOWN_SCOPE")
    unit = _structured_unit(row["unit"])
    if unit is None:
        reasons.append("UNKNOWN_UNIT")
    if row["statement"] not in {"IS", "BS", "CF"}:
        reasons.append("UNKNOWN_STATEMENT")
    digest = row["source_sha256"].lower()
    if _SHA256_TEXT.fullmatch(digest) is None:
        reasons.append("SOURCE_HASH_INVALID")
    number = _structured_integer(row["value"])
    if number is None:
        reasons.append("VALUE_NOT_INTEGER")
    if reasons or period is None or unit is None or scope is None:
        return None, {"line_number": line_number, "reason_codes": reasons or ["ROW_REJECTED"], "ticker": ticker or None, "item": row.get("item") or None}
    suffix, kind = period
    return {
        "line_number": line_number,
        "ticker": ticker,
        "period": f"{int(row['period_year'])}-{suffix}",
        "year": int(row["period_year"]),
        "period_suffix": suffix,
        "period_kind": kind,
        "period_basis": row["period_basis"],
        "period_label": row["period_label"],
        "statement_scope": scope,
        "scope_text": row["consolidation"],
        "unit": unit[0],
        "unit_scale": unit[1],
        "currency": unit[2],
        "unit_text": row["unit"],
        "statement": row["statement"],
        "item": row["item"],
        "value": number,
        "native_text": row["value"],
        "source": row["source"],
        "source_file": row["source_file"],
        "source_sha256": digest,
        "audit_status": row.get("audit_status") or None,
        "auditor": row.get("auditor") or None,
        "audit_opinion": row.get("audit_opinion") or None,
        "vendor_publish_date": row.get("vendor_publish_date") or None,
        "vendor_audit_sign_date": row.get("vendor_audit_sign_date") or None,
        "vendor_data_updated": row.get("vendor_data_updated") or None,
    }, None


def _change_percent(current: int, prior: int) -> dict[str, Any]:
    if prior == 0:
        return {"status": "NOT_COMPUTED", "reason_codes": ["ZERO_BASE"], "percent": None}
    percent = (Decimal(current) / Decimal(prior) - 1) * Decimal(100)
    quantized = percent.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return {
        "status": "COMPUTED",
        "percent": format(quantized, "f"),
        "method": "SAME_SCOPE_SAME_KIND_SAME_UNIT_PRIOR_YEAR",
        "reason_codes": [],
    }


def _cell_key(cell: Mapping[str, Any]) -> tuple[Any, ...]:
    return (cell["ticker"], cell["period"], cell["statement_scope"], cell["unit"], cell["statement"], cell["item"])


def _lookup(index: Mapping[tuple[Any, ...], dict[str, Any]], ticker: str, period: str, scope: str, unit: str, statement: str, item: str) -> dict[str, Any] | None:
    return index.get((ticker, period, scope, unit, statement, item))


def _source_view(cell: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "value": item["value"],
            "native_text": item["native_text"],
            "source_sha256": item["source_sha256"],
            "source_file": item["source_file"],
            "source": item["source"],
            "vendor_publish_date": item["vendor_publish_date"],
            "audit_status": item["audit_status"],
        }
        for item in sorted(cell["sources"], key=lambda item: (item["source_sha256"], item["value"], item["source_file"]))
    ]


def _structured_measure(cell: Mapping[str, Any] | None, **fields: Any) -> dict[str, Any]:
    sources = [] if cell is None else _source_view(cell)
    shas = sorted({item["source_sha256"] for item in sources})
    base = cell or {}
    return _measure(
        ticker=fields.get("ticker", base.get("ticker")),
        period=fields.get("period", base.get("period")),
        period_kind=fields.get("period_kind", base.get("period_kind")),
        analysis_family=fields["analysis_family"],
        statement_scope=fields.get("statement_scope", base.get("statement_scope")),
        unit=fields.get("unit", base.get("unit")),
        unit_scale=fields.get("unit_scale", base.get("unit_scale", 1)),
        currency=fields.get("currency", base.get("currency", "VND")),
        metric=fields["metric"],
        status=fields["status"],
        value=fields.get("value"),
        use_scope=fields["use_scope"],
        reason_codes=list(fields.get("reason_codes") or []),
        original_label=fields.get("original_label", base.get("item")),
        period_label=base.get("period_label"),
        period_basis=base.get("period_basis"),
        fiscal_calendar=None,
        fiscal_calendar_basis="NOT_SUPPLIED_IN_SOURCE",
        assurance_status=None if cell is None else cell.get("audit_status"),
        restatement=None,
        restatement_basis="NOT_SUPPLIED_IN_SOURCE",
        native_representation=None if cell is None else [item["native_text"] for item in sources],
        normalization_method=fields.get("normalization_method", "EXACT_LABEL_MATCH_NO_UNIT_CONVERSION"),
        research_use_restriction="CURRENT_RESEARCH_NOT_OFFICIAL_NOT_PIT_NOT_VALUATION",
        source_name=None if cell is None else cell.get("source"),
        source_sha256=shas[0] if len(shas) == 1 else None,
        source_sha256_list=shas,
        source_file=None if len(sources) != 1 else sources[0]["source_file"],
        retained_originals=sources,
        vendor_supplied_dates=sorted({item["vendor_publish_date"] for item in sources if item["vendor_publish_date"]}),
        vendor_date_basis="VENDOR_SUPPLIED_NOT_INDEPENDENT" if sources else None,
        publication_time=None,
        publication_basis="NOT_INFERRED_FROM_VENDOR_EXPORT_OR_FILE_TIME",
        evidence_layer="PROVIDER_STRUCTURED_EXPORT",
        numerator=fields.get("numerator"),
        denominator=fields.get("denominator"),
        identity=fields.get("identity"),
        method=fields.get("method"),
        temporal_status=fields["temporal_status"],
        available_at_cutoff=fields["available_at_cutoff"],
        input_sha256=fields["input_sha256"],
    )


def build_structured_financial_research(
    path: str | Path,
    *,
    knowledge_cutoff: str | None = None,
    observed_at: str | None = None,
) -> dict[str, Any]:
    """Read one permitted structured export and project current-research measures.

    The same file bytes are the input identity. A later file is a new result.
    This function does not read file modification time, infer publication, admit
    an official fact, or replace the hardcoded statement-cohort regression.
    """
    source_path = Path(path)
    if not source_path.is_file():
        raise ValueError("STRUCTURED_INPUT_NOT_A_FILE")
    cutoff = _aware_instant(knowledge_cutoff, "KNOWLEDGE_CUTOFF_INVALID")
    observed = _aware_instant(observed_at, "OBSERVED_AT_INVALID")
    if cutoff is None and observed is None:
        temporal_status, usable_now = "NO_CUTOFF", True
    elif cutoff is None:
        temporal_status, usable_now = "OBSERVED_WITHOUT_CUTOFF", True
    elif observed is None:
        temporal_status, usable_now = "OBSERVATION_TIME_ABSENT", False
    elif observed > cutoff:
        temporal_status, usable_now = "AFTER_KNOWLEDGE_CUTOFF", False
    else:
        temporal_status, usable_now = "OBSERVED_AT_OR_BEFORE_CUTOFF", True
    available_at_cutoff = True if usable_now and cutoff is not None else (False if cutoff is not None else None)
    input_sha256, loaded = _load_structured_rows(source_path)
    accepted: list[dict[str, Any]] = []
    rejections: list[dict[str, Any]] = []
    for line_number, row in loaded:
        observation, rejection = _accept_structured_row(line_number, row)
        if observation is not None:
            accepted.append(observation)
        elif rejection is not None:
            rejections.append(rejection)

    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for observation in accepted:
        grouped.setdefault(_cell_key(observation), []).append(observation)
    cells: dict[tuple[Any, ...], dict[str, Any]] = {}
    for key, observations in grouped.items():
        unique = {(item["value"], item["source_sha256"], item["native_text"]) for item in observations}
        values = {item[0] for item in unique}
        sample = observations[0]
        status = "USABLE" if len(values) == 1 else "CONFLICT"
        if status == "USABLE" and not usable_now:
            status = "BLOCKED"
        cells[key] = {
            **sample,
            "status": status,
            "value": sample["value"] if len(values) == 1 else None,
            "sources": observations,
            "reason_codes": [] if len(values) == 1 and usable_now else (
                ["VALUE_CONFLICT_RETAINED"] if len(values) != 1 else [temporal_status]
            ),
        }

    labels_by_ticker: dict[str, set[str]] = {}
    for cell in cells.values():
        labels_by_ticker.setdefault(cell["ticker"], set()).add(cell["item"])
    families: dict[str, str] = {}
    for ticker, labels in labels_by_ticker.items():
        matched = [family for family, marker in _FAMILY_MARKERS if marker in labels]
        families[ticker] = matched[0] if len(matched) == 1 else ("MIXED_STATEMENT" if matched else "UNKNOWN_STATEMENT")

    measures: list[dict[str, Any]] = []
    label_maps = {**{name: _FLOW_LABELS[name] + _STOCK_LABELS[name] for name in _FLOW_LABELS}}

    def emit_from_cell(cell: Mapping[str, Any], metric: str, identity: str | None = None) -> None:
        use = "CURRENT_RESEARCH" if cell["status"] == "USABLE" else "NOT_AVAILABLE"
        measures.append(_structured_measure(
            cell, metric=metric, status=cell["status"], value=cell["value"] if cell["status"] != "BLOCKED" else cell["value"],
            use_scope=use, reason_codes=list(cell["reason_codes"]), analysis_family=families[cell["ticker"]],
            identity=identity, temporal_status=temporal_status, available_at_cutoff=available_at_cutoff,
            input_sha256=input_sha256,
        ))

    for ticker, family in sorted(families.items()):
        labels = label_maps.get(family, ())
        for metric, statement, item in labels:
            matches = [cell for cell in cells.values() if cell["ticker"] == ticker and cell["statement"] == statement and cell["item"] == item]
            for cell in sorted(matches, key=lambda item: (item["period"], item["statement_scope"], item["unit"])):
                emit_from_cell(cell, metric, "REPORTED_LABEL")
        if family == "BANK_STATEMENT":
            periods = {(cell["period"], cell["statement_scope"], cell["unit"]) for cell in cells.values() if cell["ticker"] == ticker and cell["statement"] == "CF"}
            for period, scope, unit in sorted(periods):
                found = [cell for label in _BANK_OCF_LABELS if (cell := _lookup(cells, ticker, period, scope, unit, "CF", label)) is not None]
                if len(found) == 1:
                    emit_from_cell(found[0], "operating_cash_flow", "SINGLE_BANK_NET_OPERATING_CASH_FLOW_LABEL")
                elif len(found) > 1:
                    measures.append(_structured_measure(
                        found[0], metric="operating_cash_flow", status="BLOCKED", value=None,
                        use_scope="NOT_AVAILABLE", reason_codes=["MULTIPLE_NET_OPERATING_CASH_FLOW_LABELS_NOT_EQUATED"],
                        analysis_family=family, identity="BANK_OPERATING_CASH_FLOW_LABELS_NOT_MERGED",
                        temporal_status=temporal_status, available_at_cutoff=available_at_cutoff, input_sha256=input_sha256,
                    ))
        measures.append(_structured_measure(
            None, ticker=ticker, period="TTM", period_kind="TRAILING_TWELVE_MONTHS", analysis_family=family,
            statement_scope="UNSET", unit="UNSET", unit_scale=1, currency="UNSET", metric="profit_after_tax_ttm",
            status="BLOCKED", value=None, use_scope="NOT_AVAILABLE",
            reason_codes=["NO_TRAILING_WINDOW_ANCHOR"], temporal_status=temporal_status,
            available_at_cutoff=available_at_cutoff, input_sha256=input_sha256,
            normalization_method="NOT_DERIVED",
        ))
        measures.append(_structured_measure(
            None, ticker=ticker, period="CURRENT", period_kind="UNSET", analysis_family=family,
            statement_scope="UNSET", unit="MULTIPLE", unit_scale=1, currency="UNSET", metric="research_multiple",
            status="BLOCKED", value=None, use_scope="NOT_AVAILABLE",
            reason_codes=["VALUATION_CLOSED_NO_QUALIFIED_PRICE_AND_SHARE_BASE"], temporal_status=temporal_status,
            available_at_cutoff=available_at_cutoff, input_sha256=input_sha256,
            normalization_method="NOT_DERIVED",
        ))
        if family != "INDUSTRIAL_STATEMENT":
            measures.append(_structured_measure(
                None, ticker=ticker, period="UNSET", period_kind="UNSET", analysis_family=family,
                statement_scope="UNSET", unit="RATIO", unit_scale=1, currency="UNSET", metric="industrial_profit_margin",
                status="NOT_APPLICABLE", value=None, use_scope="NOT_AVAILABLE",
                reason_codes=["STATEMENT_TEMPLATE_IS_NOT_INDUSTRIAL"], temporal_status=temporal_status,
                available_at_cutoff=available_at_cutoff, input_sha256=input_sha256,
                normalization_method="NOT_DERIVED",
            ))

    def usable_metric(ticker: str, period: str, scope: str, unit: str, metric: str) -> dict[str, Any] | None:
        found = [row for row in measures if row["ticker"] == ticker and row["period"] == period and row["statement_scope"] == scope and row["unit"] == unit and row["metric"] == metric and row["status"] == "USABLE"]
        return found[0] if len(found) == 1 else None

    derived: list[dict[str, Any]] = []
    industrial_flow = {item[0] for item in _FLOW_LABELS["INDUSTRIAL_STATEMENT"]}
    for row in list(measures):
        if row["status"] != "USABLE" or row["analysis_family"] != "INDUSTRIAL_STATEMENT":
            continue
        if row["metric"] not in {"gross_profit", "group_profit_after_tax", "parent_profit_after_tax"}:
            continue
        revenue = usable_metric(row["ticker"], row["period"], row["statement_scope"], row["unit"], "net_revenue")
        if revenue is None or not isinstance(row["value"], int) or not isinstance(revenue["value"], int):
            continue
        ratio = _ratio(row["value"], revenue["value"])
        metric = {
            "gross_profit": "gross_margin",
            "group_profit_after_tax": "group_profit_margin",
            "parent_profit_after_tax": "parent_profit_margin",
        }[row["metric"]]
        derived.append(_structured_measure(
            None, ticker=row["ticker"], period=row["period"], period_kind=row["period_kind"],
            analysis_family="INDUSTRIAL_STATEMENT", statement_scope=row["statement_scope"], unit="RATIO",
            unit_scale=1, currency=row["currency"], metric=metric,
            status="USABLE" if ratio["status"] == "COMPUTED" else "BLOCKED",
            value=ratio.get("rounded_6dp"), use_scope="CURRENT_RESEARCH" if ratio["status"] == "COMPUTED" else "NOT_AVAILABLE",
            reason_codes=list(ratio["reason_codes"]), numerator=row["value"], denominator=revenue["value"],
            identity=f"{metric.upper()}_OVER_NET_REVENUE", normalization_method="RATIO_OF_REPORTED_CELLS_NO_UNIT_CONVERSION",
            temporal_status=temporal_status, available_at_cutoff=available_at_cutoff, input_sha256=input_sha256,
        ))
        if row["metric"] == "group_profit_after_tax":
            cash = usable_metric(row["ticker"], row["period"], row["statement_scope"], row["unit"], "operating_cash_flow")
            if cash is not None and isinstance(cash["value"], int):
                conversion = _ratio(cash["value"], row["value"])
                derived.append(_structured_measure(
                    None, ticker=row["ticker"], period=row["period"], period_kind=row["period_kind"],
                    analysis_family="INDUSTRIAL_STATEMENT", statement_scope=row["statement_scope"], unit="RATIO",
                    unit_scale=1, currency=row["currency"], metric="cash_conversion",
                    status="USABLE" if conversion["status"] == "COMPUTED" else "BLOCKED",
                    value=conversion.get("rounded_6dp"),
                    use_scope="CURRENT_RESEARCH" if conversion["status"] == "COMPUTED" else "NOT_AVAILABLE",
                    reason_codes=list(conversion["reason_codes"]) + (["NEGATIVE_GROUP_PROFIT"] if row["value"] < 0 else []),
                    numerator=cash["value"], denominator=row["value"],
                    identity="OPERATING_CASH_FLOW_OVER_GROUP_PROFIT_AFTER_TAX",
                    normalization_method="RATIO_OF_REPORTED_CELLS_NO_UNIT_CONVERSION",
                    temporal_status=temporal_status, available_at_cutoff=available_at_cutoff, input_sha256=input_sha256,
                ))
    for row in list(measures):
        if row["status"] != "USABLE" or row["metric"] not in industrial_flow | {
            "net_interest_income", "pre_provision_profit", "credit_loss_provision", "group_profit_after_tax",
            "parent_profit_after_tax", "brokerage_revenue", "loan_and_receivable_interest", "interest_expense",
            "securities_net_revenue", "operating_cash_flow", "cash_and_equivalents", "total_assets", "total_liabilities",
            "borrowings_and_finance_leases_short", "borrowings_and_finance_leases_long",
        }:
            continue
        year_text, suffix = str(row["period"]).split("-", 1)
        if not year_text.isdigit() or "_" in suffix:
            continue
        year = int(year_text)
        prior_period = f"{year - 1}-{suffix}"
        prior = usable_metric(row["ticker"], prior_period, row["statement_scope"], row["unit"], row["metric"])
        change = None if prior is None or not isinstance(row["value"], int) or not isinstance(prior["value"], int) else _change_percent(row["value"], prior["value"])
        yoy_period = f"{row['period']}_VS_{prior_period}"
        if change is None:
            derived.append(_structured_measure(
                None, ticker=row["ticker"], period=yoy_period,
                period_kind="YEAR_OVER_YEAR", analysis_family=row["analysis_family"], statement_scope=row["statement_scope"],
                unit="PERCENT", unit_scale=1, currency=row["currency"], metric=f"{row['metric']}_yoy",
                status="BLOCKED", value=None, use_scope="NOT_AVAILABLE", reason_codes=["PRIOR_REPORTED_PERIOD_ABSENT"],
                normalization_method="NOT_DERIVED", temporal_status=temporal_status,
                available_at_cutoff=available_at_cutoff, input_sha256=input_sha256,
            ))
            continue
        derived.append(_structured_measure(
            None, ticker=row["ticker"], period=yoy_period,
            period_kind="YEAR_OVER_YEAR", analysis_family=row["analysis_family"], statement_scope=row["statement_scope"],
            unit="PERCENT", unit_scale=1, currency=row["currency"], metric=f"{row['metric']}_yoy",
            status="USABLE" if change["status"] == "COMPUTED" else "BLOCKED", value=change.get("percent"),
            use_scope="CURRENT_RESEARCH" if change["status"] == "COMPUTED" else "NOT_AVAILABLE",
            reason_codes=list(change["reason_codes"]), method=change.get("method"),
            normalization_method="PRIOR_YEAR_SAME_REPORTED_CELL",
            temporal_status=temporal_status, available_at_cutoff=available_at_cutoff, input_sha256=input_sha256,
        ))

    ratio_pairs = (
        ("cash_to_total_assets", "cash_and_equivalents", "total_assets", "CASH_AND_EQUIVALENTS_OVER_TOTAL_ASSETS"),
        ("liabilities_to_total_assets", "total_liabilities", "total_assets", "TOTAL_LIABILITIES_OVER_TOTAL_ASSETS"),
        ("credit_provision_to_pre_provision", "credit_loss_provision", "pre_provision_profit", "CREDIT_PROVISION_OVER_PRE_PROVISION_PROFIT"),
    )
    seen_pairs: set[tuple[Any, ...]] = set()
    for row in list(measures):
        if row["status"] != "USABLE":
            continue
        for metric, numerator_name, denominator_name, identity in ratio_pairs:
            if row["metric"] != numerator_name:
                continue
            denominator = usable_metric(row["ticker"], row["period"], row["statement_scope"], row["unit"], denominator_name)
            pair_key = (row["ticker"], row["period"], row["statement_scope"], row["unit"], metric)
            if denominator is None or pair_key in seen_pairs or not isinstance(row["value"], int) or not isinstance(denominator["value"], int):
                continue
            seen_pairs.add(pair_key)
            ratio = _ratio(row["value"], denominator["value"])
            derived.append(_structured_measure(
                None, ticker=row["ticker"], period=row["period"], period_kind=row["period_kind"],
                analysis_family=row["analysis_family"], statement_scope=row["statement_scope"], unit="RATIO",
                unit_scale=1, currency=row["currency"], metric=metric,
                status="USABLE" if ratio["status"] == "COMPUTED" else "BLOCKED", value=ratio.get("rounded_6dp"),
                use_scope="CURRENT_RESEARCH" if ratio["status"] == "COMPUTED" else "NOT_AVAILABLE",
                reason_codes=list(ratio["reason_codes"]), numerator=row["value"], denominator=denominator["value"],
                identity=identity, normalization_method="RATIO_OF_REPORTED_CELLS_NO_UNIT_CONVERSION",
                temporal_status=temporal_status, available_at_cutoff=available_at_cutoff, input_sha256=input_sha256,
            ))

    for ticker, family in sorted(families.items()):
        if family != "INDUSTRIAL_STATEMENT":
            continue
        if any(cell["ticker"] == ticker and cell["item"] in {
            "11. Vay và nợ thuê tài chính ngắn hạn", "9. Vay và nợ thuê tài chính dài hạn",
        } for cell in cells.values()):
            derived.append(_structured_measure(
                None, ticker=ticker, period="UNSET", period_kind="UNSET", analysis_family=family,
                statement_scope="UNSET", unit="VND", unit_scale=1, currency="VND", metric="interest_bearing_debt",
                status="BLOCKED", value=None, use_scope="NOT_AVAILABLE",
                reason_codes=["LEASE_INCLUSIVE_LABEL_NOT_SEPARATED"], normalization_method="NOT_DERIVED",
                temporal_status=temporal_status, available_at_cutoff=available_at_cutoff, input_sha256=input_sha256,
            ))
        flow_metrics = ("parent_profit_after_tax", "net_revenue", "group_profit_after_tax")
        scopes = set()
        for row in measures:
            if row["ticker"] != ticker or row["metric"] not in flow_metrics or row["status"] != "USABLE" or row["period_kind"] != "STANDALONE_QUARTER":
                continue
            year_text, _suffix = str(row["period"]).split("-", 1)
            if year_text.isdigit():
                scopes.add((row["statement_scope"], row["unit"], int(year_text)))
        for scope, unit, year in sorted(scopes):
            for metric in flow_metrics:
                quarters = [usable_metric(ticker, f"{year}-{suffix}", scope, unit, metric) for suffix in ("Q1", "Q2", "Q3", "Q4")]
                if not all(item is not None and isinstance(item["value"], int) for item in quarters):
                    continue
                derived.append(_structured_measure(
                    None, ticker=ticker, period=f"{year}-FOUR_DISCRETE_QUARTERS", period_kind="SUM_OF_FOUR_REPORTED_QUARTERS",
                    analysis_family=family, statement_scope=scope, unit=unit, unit_scale=quarters[0]["unit_scale"],
                    currency=quarters[0]["currency"], metric=f"{metric}_four_discrete_quarter_sum",
                    status="USABLE", value=sum(item["value"] for item in quarters), use_scope="CURRENT_RESEARCH",
                    reason_codes=[], identity="SUM_OF_FOUR_REPORTED_DISCRETE_QUARTERS_NOT_TTM",
                    normalization_method="SUM_OF_REPORTED_DISCRETE_QUARTERS",
                    temporal_status=temporal_status, available_at_cutoff=available_at_cutoff, input_sha256=input_sha256,
                ))

    measures.extend(derived)
    measures.sort(key=lambda row: (str(row["ticker"]), str(row["period"]), str(row["metric"]), str(row["statement_scope"]), str(row["unit"]), str(row["status"])))

    def comparison_rows(metric: str) -> list[dict[str, Any]]:
        groups: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
        for row in measures:
            if row["metric"] == metric and row["status"] == "USABLE" and isinstance(row.get("numerator"), int) and isinstance(row.get("denominator"), int):
                groups.setdefault((row["period"], row["statement_scope"], row["currency"], row["analysis_family"]), []).append(row)
        results = []
        for key, rows in sorted(groups.items()):
            if len({row["ticker"] for row in rows}) < 2:
                continue
            chosen = sorted(rows, key=lambda row: row["ticker"])
            higher = max(chosen, key=lambda row: (row["numerator"] / row["denominator"], row["ticker"]))
            lower = min(chosen, key=lambda row: (row["numerator"] / row["denominator"], row["ticker"]))
            results.append({
                "question": metric,
                "period": key[0],
                "statement_scope": key[1],
                "currency": key[2],
                "analysis_family": key[3],
                "rows": [{"ticker": row["ticker"], "rounded_6dp": row["value"], "numerator": row["numerator"], "denominator": row["denominator"]} for row in chosen],
                "higher_on_this_ratio": higher["ticker"],
                "lower_on_this_ratio": lower["ticker"],
                "ordinal_rank": None,
                "does_not_establish": ["OVERALL_FINANCIAL_STRENGTH", "PEER_RANK", "TARGET_PRICE", "OFFICIAL_FACT", "VALUATION"],
            })
        return results

    residuals = []
    zero_residuals = 0
    for ticker, family in sorted(families.items()):
        if family != "INDUSTRIAL_STATEMENT":
            continue
        periods = sorted({(row["period"], row["statement_scope"], row["unit"]) for row in measures if row["ticker"] == ticker and row["status"] == "USABLE" and row["metric"] == "group_profit_after_tax"})
        for period, scope, unit in periods:
            group = usable_metric(ticker, period, scope, unit, "group_profit_after_tax")
            parent = usable_metric(ticker, period, scope, unit, "parent_profit_after_tax")
            nci = usable_metric(ticker, period, scope, unit, "noncontrolling_profit")
            if not group or not parent or not nci:
                continue
            residual = group["value"] - (parent["value"] + nci["value"])
            if residual == 0:
                zero_residuals += 1
                continue
            residuals.append({
                "ticker": ticker, "period": period, "statement_scope": scope, "unit": unit,
                "group_minus_parent_and_nci": residual,
                "use": "REPORTED_LINES_KEPT_RESIDUAL_NOT_REPAIRED",
            })

    yoy_rows = [row for row in measures if row["metric"].endswith("_yoy") and row["status"] == "USABLE"]
    companies = []
    for ticker, family in sorted(families.items()):
        ticker_rows = [row for row in measures if row["ticker"] == ticker]
        companies.append({
            "ticker": ticker,
            "analysis_family": family,
            "template_inference": "FROM_LABELS_NOT_AN_ENTITY_CLASSIFICATION",
            "usable_measures": sum(row["status"] == "USABLE" for row in ticker_rows),
            "blocked_or_not_applicable": sum(row["status"] != "USABLE" for row in ticker_rows),
            "periods": sorted({row["period"] for row in ticker_rows if row["status"] == "USABLE" and row["period_kind"] not in {"YEAR_OVER_YEAR", "UNSET", "TRAILING_TWELVE_MONTHS"}}),
        })
    reason_counts = Counter(reason for row in rejections for reason in row["reason_codes"])
    coverage = {
        "issuer_count": len(families),
        "issuer_period_metric_records": len(measures),
        "current_research_usable": sum(row["status"] == "USABLE" for row in measures),
        "blocked_or_not_applicable": sum(row["status"] != "USABLE" for row in measures),
        "conflict_measures": sum(row["status"] == "CONFLICT" for row in measures),
        "official_fact_admitted_count": 0,
        "valuation_measures_usable": sum(row["metric"] == "research_multiple" and row["status"] == "USABLE" for row in measures),
        "ttm_measures_usable": sum(row["metric"] == "profit_after_tax_ttm" and row["status"] == "USABLE" for row in measures),
        "companies_with_usable_measures": sum(item["usable_measures"] > 0 for item in companies),
        "accepted_observations": len(accepted),
        "rejected_rows": len(rejections),
        "identity_residuals_nonzero": len(residuals),
        "identity_residuals_zero": zero_residuals,
    }
    body = {
        "contract_version": STRUCTURED_INPUT_CONTRACT,
        "use_scope": "CURRENT_RESEARCH",
        "attribution": "SOURCE_ATTRIBUTED",
        "evidence_role": "PROVIDER_STRUCTURED_EXPORT",
        "not_provider_market_data": True,
        "official_fact_admitted": False,
        "historical_pit": "UNKNOWN",
        "valuation_use": "CLOSED",
        "execution_eligible": False,
        "is_actionable": False,
        "target_price": None,
        "probability": None,
        "ordinal_rank": None,
        "financial_v2_authority_unchanged": "2026-09-05.1",
        "input_sha256": input_sha256,
        "input_name": source_path.name,
        "caller_observed_at": observed_at or None,
        "knowledge_cutoff": knowledge_cutoff or None,
        "temporal_status": temporal_status,
        "publication_time": None,
        "publication_basis": "NOT_INFERRED_FROM_VENDOR_EXPORT_OR_FILE_TIME",
        "file_modification_time_used": False,
        "providers": sorted({cell["source"] for cell in cells.values()}),
        "issuers": sorted(families),
        "families": {
            family: sorted(ticker for ticker, name in families.items() if name == family)
            for family in ("INDUSTRIAL_STATEMENT", "BANK_STATEMENT", "SECURITIES_STATEMENT", "MIXED_STATEMENT", "UNKNOWN_STATEMENT")
        },
        "measures": measures,
        "companies": companies,
        "comparisons": comparison_rows("parent_profit_margin") + comparison_rows("gross_margin") + comparison_rows("credit_provision_to_pre_provision"),
        "yoy_usable": [{"ticker": row["ticker"], "period": row["period"], "metric": row["metric"], "percent": row["value"], "statement_scope": row["statement_scope"], "analysis_family": row["analysis_family"]} for row in yoy_rows],
        "identity_residuals": residuals,
        "rejections": {
            "count": len(rejections),
            "identity": stable_id(rejections),
            "reason_counts": dict(sorted(reason_counts.items())),
            "examples": rejections[:20],
        },
        "coverage": coverage,
        "regression_control": {
            "statement_cohort_contract": COHORT_CONTRACT,
            "this_path_does_not_replace_it": True,
        },
        "consumers": {
            "conditional_research_case_tool": "tools/build_conditional_research_cases.py --structured-input",
            "ai_research_preview": {
                "status": "NOT_FED",
                "reason": "EXISTING_PREVIEW_REQUIRES_A_DECISION_WORKFLOW_RECORD",
                "daily_packet_activated": False,
            },
            "financial_v2_authority": "UNCHANGED_2026-09-05.1",
        },
        "restrictions": [
            "NOT_AN_OFFICIAL_FACT",
            "HISTORICAL_PIT_UNKNOWN",
            "VALUATION_CLOSED",
            "NO_SHARE_COUNT",
            "NO_PRICE",
            "NO_TTM",
            "NO_ANNUALIZATION",
            "PUBLICATION_TIME_NOT_INFERRED",
            "LABEL_TEMPLATE_IS_NOT_AN_ENTITY_CLASSIFICATION",
        ],
    }
    return {**body, "research_identity": "structured_financial_research:" + stable_id(body)}
