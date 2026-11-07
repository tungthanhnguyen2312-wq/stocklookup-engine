"""Fail-closed Q3/2026 research freshness gate.

``financial_evidence_currency_refresh/v1`` admits FY2025 and 2026-H1/2026-Q2
only. 2026-Q3 stays out of that contract. This module does not widen it, does
not turn a nine-month cumulative column into a standalone quarter, and does
not treat a press release as a reviewed statement.

A future retained filing can be classified here. The result is a shadow
candidate. ``official_fact_admitted`` stays false and ``valuation_use`` stays
closed until a successor admission contract is explicitly opened.
"""
from __future__ import annotations

from typing import Any

from financial_evidence_currency_contract import OUT_OF_SCOPE_PERIODS, is_out_of_scope_period

CONTRACT_VERSION = "q3_2026_research_freshness/v1"
FOCUS_TICKERS = ("PAN", "HPG", "SSI", "EVF", "POW")

_KINDS = {
    "Q3_STANDALONE_UNREVIEWED": "duration_quarter",
    "Q3_STANDALONE_REVIEWED": "duration_quarter",
    "NINE_MONTH_CUMULATIVE": "duration_nine_month",
    "ANNUAL_AUDITED": "duration_year",
    "PRESS_RELEASE": "not_a_financial_statement",
    "H1_OR_Q2": "not_q3",
}


def classify_document(*, document_kind: str, period_label: str) -> dict[str, Any]:
    """Classify one candidate. Unknown kinds fail closed."""
    kind = str(document_kind or "").strip().upper()
    period = str(period_label or "").strip()
    known = kind in _KINDS
    out_of_currency_refresh = is_out_of_scope_period(period) or period in {"2026-Q3", "2026-9M"}
    nine_month_used_as_quarter = kind == "NINE_MONTH_CUMULATIVE" and period.endswith("-Q3")
    h1_used_as_q3 = kind == "H1_OR_Q2" and period.endswith("-Q3")
    press_as_statement = kind == "PRESS_RELEASE"
    admissible = False
    reasons = []
    if not known:
        reasons.append("DOCUMENT_KIND_UNKNOWN")
    if period in OUT_OF_SCOPE_PERIODS or period == "2026-Q3":
        reasons.append("OUT_OF_FINANCIAL_EVIDENCE_CURRENCY_REFRESH_SCOPE")
    if nine_month_used_as_quarter:
        reasons.append("NINE_MONTH_CUMULATIVE_IS_NOT_Q3_STANDALONE")
    if h1_used_as_q3:
        reasons.append("H1_DURATION_IS_NOT_Q3")
    if press_as_statement:
        reasons.append("PRESS_RELEASE_IS_NOT_A_REVIEWED_STATEMENT")
    if kind == "Q3_STANDALONE_REVIEWED":
        reasons.append("REVIEWED_Q3_REQUIRES_SUCCESSOR_ADMISSION_CONTRACT")
    if kind == "Q3_STANDALONE_UNREVIEWED":
        reasons.append("UNREVIEWED_Q3_STAYS_RESEARCH_TIER_NOT_OFFICIAL_FACT")
    return {
        "contract_version": CONTRACT_VERSION,
        "document_kind": kind if known else "UNKNOWN",
        "period_label": period,
        "duration_semantics": _KINDS.get(kind, "UNKNOWN"),
        "currency_refresh_in_scope": not out_of_currency_refresh and period not in OUT_OF_SCOPE_PERIODS,
        "official_fact_admitted": admissible,
        "valuation_use": "CLOSED",
        "existing_consumer_usable": False,
        "reason_codes": reasons or ["NOT_ADMITTED"],
        "nine_month_promoted_to_standalone_quarter": False,
    }


def shadow_candidate(*, ticker: str, document_kind: str, period_label: str, source_identity: str | None = None) -> dict[str, Any]:
    """A retained-candidate record. It is not an admitted official fact."""
    classification = classify_document(document_kind=document_kind, period_label=period_label)
    return {
        **classification,
        "ticker": str(ticker or "").upper(),
        "focus_cohort": str(ticker or "").upper() in FOCUS_TICKERS,
        "source_identity": source_identity,
        "admission_effect": "NONE",
        "candidate_only": True,
    }
