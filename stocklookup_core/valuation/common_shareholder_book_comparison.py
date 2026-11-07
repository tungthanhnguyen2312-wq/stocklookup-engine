"""Compare a displayed research P/B with common-shareholder book equity.

The displayed research multiple uses consolidated total equity, which includes
non-controlling interest when that interest exists. That multiple is not a
common-shareholder P/B and is not evidence that the shares are cheap.

A common-shareholder multiple is emitted only from an explicit parent-equity
input that names its period, scope, currency and knowledge time. Nine-month
figures are not relabelled as a quarter. Pretax non-recurring income is never
subtracted from net income to invent a normalized EPS.
"""
from __future__ import annotations

from typing import Any, Mapping

CONTRACT_VERSION = "common_shareholder_book_comparison/v1"
LABEL = "COMMON_SHAREHOLDER_RESEARCH"
PARENT_SCOPE = "EQUITY_ATTRIBUTABLE_TO_PARENT_COMMON_SHAREHOLDERS"


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def compare(
    *,
    proxy_pb: float | None = None,
    proxy_equity_definition: str | None = None,
    proxy_book_period: str | None = None,
    proxy_numerator_vnd: float | None = None,
    proxy_denominator_vnd: float | None = None,
    parent_equity_vnd: float | None = None,
    parent_period: str | None = None,
    parent_scope: str | None = None,
    parent_currency: str | None = None,
    parent_knowledge_available_at: str | None = None,
    price_vnd: float | None = None,
    common_shares: float | None = None,
) -> dict[str, Any]:
    """Return both bases, or an explicit refusal for the missing one."""
    proxy_value = _number(proxy_pb)
    proxy = {
        "status": "VERIFIED_DISPLAYED_MULTIPLE" if proxy_value is not None else "ABSENT",
        "value": proxy_value,
        "equity_definition": proxy_equity_definition,
        "book_period": proxy_book_period,
        "numerator_vnd": _number(proxy_numerator_vnd),
        "denominator_vnd": _number(proxy_denominator_vnd),
        "scope": "CONSOLIDATED_TOTAL_EQUITY_INCLUDES_NCI_WHEN_PRESENT",
    }
    reasons: list[str] = []
    parent_value = None
    parent_inputs = {
        "equity_vnd": _number(parent_equity_vnd),
        "period": parent_period,
        "scope": parent_scope,
        "currency": parent_currency,
        "knowledge_available_at": parent_knowledge_available_at,
        "price_vnd": _number(price_vnd),
        "common_shares": _number(common_shares),
    }
    if parent_inputs["equity_vnd"] is None:
        reasons.append("PARENT_EQUITY_NOT_ADMITTED")
    elif parent_scope != PARENT_SCOPE:
        reasons.append("PARENT_SCOPE_NOT_COMMON_SHAREHOLDER_EQUITY")
    elif parent_currency != "VND" or not parent_period or not parent_knowledge_available_at:
        reasons.append("PARENT_EQUITY_PERIOD_CURRENCY_OR_KNOWLEDGE_INCOMPLETE")
    elif parent_inputs["price_vnd"] is None or parent_inputs["common_shares"] is None or parent_inputs["common_shares"] <= 0:
        reasons.append("PRICE_OR_COMMON_SHARES_NOT_BOUND")
    else:
        market_cap = parent_inputs["price_vnd"] * parent_inputs["common_shares"]
        if parent_inputs["equity_vnd"] <= 0:
            reasons.append("PARENT_EQUITY_NOT_POSITIVE")
        else:
            parent_value = market_cap / parent_inputs["equity_vnd"]
    same_period = bool(proxy_book_period and parent_period and proxy_book_period == parent_period)
    if parent_value is not None and not same_period:
        reasons.append("PROXY_AND_PARENT_PERIODS_DIFFER")
    return {
        "contract_version": CONTRACT_VERSION,
        "label": LABEL,
        "proxy_pb": proxy,
        "common_shareholder_pb": {
            "status": "AVAILABLE" if parent_value is not None else "UNAVAILABLE",
            "value": parent_value,
            "reason_codes": [] if parent_value is not None and same_period else reasons,
            "period": parent_period if parent_value is not None else None,
            "scope": PARENT_SCOPE if parent_value is not None else None,
            "knowledge_available_at": parent_knowledge_available_at if parent_value is not None else None,
        },
        "periods_comparable": bool(parent_value is not None and same_period),
        "cheapness_claim": "NOT_SUPPORTED",
        "earnings_quality": {
            "normalized_eps": "NOT_COMPUTED",
            "reason": "PRETAX_NONRECURRING_INCOME_IS_NOT_SUBTRACTED_FROM_NET_INCOME",
        },
    }


def from_pb_diagnostic(diagnostic: Mapping[str, Any]) -> dict[str, Any]:
    """Build the comparison from the P/B diagnostic already on the card.

    Parent equity is read only from an explicit nested ``parent_equity`` object.
    A missing object stays unavailable. Nothing is inferred by subtracting NCI.
    """
    parent = diagnostic.get("parent_equity") if isinstance(diagnostic.get("parent_equity"), Mapping) else {}
    return compare(
        proxy_pb=diagnostic.get("value"),
        proxy_equity_definition=diagnostic.get("equity_definition"),
        proxy_book_period=diagnostic.get("book_period"),
        proxy_numerator_vnd=diagnostic.get("numerator_value_vnd"),
        proxy_denominator_vnd=diagnostic.get("denominator_value_vnd"),
        parent_equity_vnd=parent.get("value_vnd"),
        parent_period=parent.get("period"),
        parent_scope=parent.get("scope"),
        parent_currency=parent.get("currency"),
        parent_knowledge_available_at=parent.get("knowledge_available_at"),
        price_vnd=parent.get("price_vnd"),
        common_shares=parent.get("common_shares"),
    )


def earnings_quality_assessment(
    *,
    disposal_income_admitted: bool = False,
    operating_cash_flow_admitted: bool = False,
    inventory_admitted: bool = False,
) -> dict[str, Any]:
    """State the earnings-quality gap. Never invent a normalized EPS or a target."""
    reasons = []
    if not disposal_income_admitted:
        reasons.append("DISPOSAL_INCOME_NOT_ADMITTED")
    if not operating_cash_flow_admitted:
        reasons.append("OPERATING_CASH_FLOW_NOT_ADMITTED")
    if not inventory_admitted:
        reasons.append("INVENTORY_NOT_ADMITTED")
    return {
        "normalized_eps": "NOT_COMPUTED",
        "target_price": "NOT_EMITTED",
        "effect_on_research_pe": "NOT_EVALUABLE",
        "effect_on_research_pb": "NOT_EVALUABLE",
        "reason_codes": reasons,
        "rule": "PRETAX_NONRECURRING_INCOME_IS_NOT_SUBTRACTED_FROM_NET_INCOME",
    }


def research_dependency(
    *,
    ticker: str,
    parent_equity_admitted: bool = False,
    common_shares_admitted: bool = False,
    treasury_shares_admitted: bool = False,
    share_effective_time: str | None = None,
    reporting_period: str | None = None,
    price_basis: str | None = None,
    exact_statement_url: str | None = None,
    index_host_admitted: bool = False,
) -> dict[str, Any]:
    """Name every missing common-shareholder input. Do not fill one from another."""
    missing = []
    if not parent_equity_admitted:
        missing.append("PARENT_EQUITY_NOT_ADMITTED")
    if not common_shares_admitted:
        missing.append("COMMON_SHARES_OUTSTANDING_NOT_ADMITTED")
    if not treasury_shares_admitted:
        missing.append("TREASURY_SHARES_NOT_ADMITTED")
    if not share_effective_time:
        missing.append("SHARE_COUNT_EFFECTIVE_TIME_UNKNOWN")
    if not reporting_period:
        missing.append("REPORTING_PERIOD_NOT_BOUND")
    if not price_basis:
        missing.append("PRICE_BASIS_NOT_BOUND")
    if not exact_statement_url:
        missing.append("NO_EXACT_OFFICIAL_Q3_STATEMENT_URL")
    if not index_host_admitted:
        missing.append("NO_ADMITTED_IR_INDEX_HOST")
    return {
        "contract_version": CONTRACT_VERSION,
        "ticker": str(ticker or "").upper(),
        "label": LABEL,
        "common_shareholder_pb": "UNAVAILABLE" if missing else "INPUTS_PRESENT_NOT_COMPUTED_HERE",
        "missing": missing,
        "earnings_quality": earnings_quality_assessment(),
        "cheapness_claim": "NOT_SUPPORTED",
    }
