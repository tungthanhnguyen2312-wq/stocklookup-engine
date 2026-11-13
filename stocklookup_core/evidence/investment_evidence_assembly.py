"""Gate price scale, share identity, and earnings quality before a valuation use.

The gate reads observations that already exist. It does not fetch, OCR, adjust a
historical bar, admit an official fact, or treat an owner-directed scale contract
as proof of the DNSE OHLC unit.
"""
from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

CONTRACT_VERSION = "investment_evidence_assembly/v1"

BLOCKED = "BLOCKED_BY_EVIDENCE"
RESEARCH_CANDIDATE = "RESEARCH_CANDIDATE_NOT_ADMITTED"
REJECTED_ARITHMETIC = "REJECTED_NOT_A_RESULT"

OWNER_DIRECTED_SCALE = "owner_directed_contractual_assumption"
UNDOCUMENTED_PRICE_TOKENS = frozenset({
    None, "", "UNKNOWN", "SOURCE_PRICE_UNIT_UNDOCUMENTED",
    "PROVIDER_NUMERIC_REPRESENTATION_UNIT_UNDOCUMENTED", "UNRESOLVED",
})
NOT_CURRENT_SHARE = frozenset({
    "EPS_DENOMINATOR_SHARES", "EPS_OPENING_SHARES", "EPS_RESTATED_DIVIDEND_IMPACT",
    "SHARE_COUNT_NOTE", "CHARTER_CAPITAL_AMOUNT", "CONTRIBUTED_SHARE_CAPITAL",
    "ORDINARY_VOTING_SHARE_CAPITAL_AMOUNT", "WEIGHTED_AVERAGE_SHARES",
    "ISSUED_SHARES", "provider_reported_outstanding_shares",
})
PROVIDER_SHARE_AUTHORITIES = frozenset({
    "provider_reported", "provider_reported_lagged", "provider_reported_unverifiable_freshness",
})
SPECIALIST_ENTITIES = frozenset({
    "bank", "securities", "securities_company", "insurance", "finance_company",
})
INDUSTRIAL_ONLY = frozenset({"EV/EBITDA", "EV/Sales", "EV"})
EARNINGS_USES = frozenset({"P/E"})
PRESS_STATUS = "RECORDED_PRESS_HIGHLIGHT_NOT_A_STATEMENT"
VISUAL_ORIGIN = "REAL_GROK_VISUAL_PAGE_REVIEW_CANDIDATE_NOT_OFFICIAL_ADMISSION"
PLANNED = frozenset({"PLANNED", "PROPOSED", "ANNOUNCED", "APPROVED", "CONFIRMED_UPCOMING"})


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite():
        return None
    return number


def _text(value: Any) -> str:
    return "" if value is None else str(value)


def classify_price_for_monetary_valuation(price: Mapping[str, Any]) -> dict[str, Any]:
    """Owner thousand-VND convention can price research. It does not verify the endpoint unit.

    Strict monetary use still requires a documented endpoint unit and a qualified
    trade-or-adjustment basis. A native VND amount is never multiplied by 1,000.
    """
    representation = price.get("price_representation") or {}
    tier = representation.get("contract_basis_tier") or price.get("contract_basis_tier")
    native_token = price.get("native_price_scale_token")
    native_value = _decimal(representation.get("provider_native_value"))
    if native_value is None:
        native_value = _decimal(price.get("provider_native_value"))
    canonical_value = _decimal(representation.get("canonical_value"))
    native_unit = representation.get("provider_native_unit") or price.get("provider_native_unit")
    instrument = price.get("instrument_class") or "VN_LISTED_EQUITY"
    capability = price.get("capability_id") or "ohlc_1D"
    reasons: list[str] = []
    research = None
    convention = (
        instrument == "VN_LISTED_EQUITY" and capability == "ohlc_1D"
        and tier == OWNER_DIRECTED_SCALE and native_value is not None and canonical_value == native_value * Decimal(1000)
        and native_unit != "vnd"
    )
    if convention:
        research = canonical_value
        reasons.append("OWNER_CONVENTION_NOT_ENDPOINT_DOCUMENTATION")
    elif tier == OWNER_DIRECTED_SCALE:
        reasons.append("OWNER_CONVENTION_NOT_APPLIED_RELATION_IS_NOT_EXACT_1000")
    if native_token in UNDOCUMENTED_PRICE_TOKENS:
        reasons.append("SOURCE_PRICE_UNIT_UNDOCUMENTED")
    if price.get("raw_as_traded") != "QUALIFIED_RAW_AS_TRADED" and price.get("adjustment_basis") != "QUALIFIED_EXPLICIT_FACTOR":
        reasons.append("PRICE_ADJUSTMENT_BASIS_UNRESOLVED")
    if native_unit == "vnd" and canonical_value is not None and native_value is not None and canonical_value == native_value * Decimal(1000):
        reasons.append("NATIVE_VND_FIELD_MUST_NOT_TAKE_PRICE_SCALE")
        research = None
    strict_reasons = [
        code for code in reasons
        if code in {
            "SOURCE_PRICE_UNIT_UNDOCUMENTED", "PRICE_ADJUSTMENT_BASIS_UNRESOLVED",
            "NATIVE_VND_FIELD_MUST_NOT_TAKE_PRICE_SCALE", "OWNER_CONVENTION_NOT_ENDPOINT_DOCUMENTATION",
            "OWNER_CONVENTION_NOT_APPLIED_RELATION_IS_NOT_EXACT_1000",
        }
    ]
    monetary = None
    if not strict_reasons and canonical_value is not None and representation.get("canonical_unit") == "vnd_per_share":
        monetary = canonical_value
    return {
        "contract_version": CONTRACT_VERSION,
        "monetary_vnd_per_share": None if monetary is None else format(monetary, "f"),
        "research_vnd_per_share": None if research is None else format(research, "f"),
        "research_unit_basis": "OWNER_ACCEPTED_VN_LISTED_EQUITY_THOUSAND_VND" if research is not None else None,
        "provider_native_value": None if native_value is None else format(native_value, "f"),
        "rejected_scale_assumption_vnd": None,
        "price_multiplied_by_one_thousand": research is not None,
        "extra_scale_applied_by_gate": False,
        "historical_bar_adjusted": False,
        "monetary_valuation_permitted": monetary is not None,
        "strict_price_eligible": monetary is not None,
        "research_price_eligible": research is not None,
        "reason_codes": sorted(set(reasons)),
        "official_fact_admitted": False,
        "source_unit_verified": False,
        "authority_effect": "NONE",
    }


def classify_share_for_valuation(
    share: Mapping[str, Any],
    *,
    eps_denominator_values: list[int] | None = None,
    price_session: str | None = None,
    knowledge_cutoff: str | None = None,
) -> dict[str, Any]:
    """Current common shares are a separate identity from an EPS denominator or a provider issue field."""
    value = share.get("value")
    integer = int(value) if isinstance(value, int) and not isinstance(value, bool) and value > 0 else None
    concept = _text(share.get("share_concept") or share.get("accounting_identity"))
    authority = _text(share.get("authority"))
    reasons: list[str] = []
    if concept in NOT_CURRENT_SHARE or concept == "":
        reasons.append("SHARE_IDENTITY_IS_NOT_CURRENT_COMMON_OUTSTANDING")
    if authority in PROVIDER_SHARE_AUTHORITIES:
        reasons.append("PROVIDER_SHARE_FIELD_IS_NOT_CURRENT_COMMON_AUTHORITY")
    retained = share.get("retained_evidence") or {}
    if "common_outstanding_share_semantics_not_proven" in _text(retained.get("official_anchor_not_promoted_because")):
        reasons.append("COMMON_OUTSTANDING_SEMANTICS_NOT_PROVEN")
    if share.get("authoritative_current_market_cap_eligible") is not True:
        reasons.append("AUTHORITATIVE_CURRENT_SHARES_NOT_ELIGIBLE")
    if share.get("continuity") != "QUALIFIED" and share.get("share_continuity") != "QUALIFIED":
        reasons.append("SHARE_CONTINUITY_THROUGH_PRICE_SESSION_NOT_PROVEN")
    for denominator in eps_denominator_values or []:
        if integer is not None and integer == denominator:
            reasons.append("NUMERIC_COLLISION_WITH_EPS_DENOMINATOR")
            reasons.append("EPS_DENOMINATOR_IS_NOT_CURRENT_OUTSTANDING")
    known = _text(share.get("knowledge_available_at") or retained.get("knowledge_available_at"))[:10]
    if knowledge_cutoff and known and known > knowledge_cutoff[:10]:
        reasons.append("SHARE_KNOWLEDGE_AFTER_PRICE_CUTOFF")
    session = _text(price_session)[:10]
    effective = _text(share.get("effective_date") or retained.get("official_anchor_effective_date"))[:10]
    if session and effective and effective > session:
        reasons.append("SHARE_EFFECTIVE_AFTER_PRICE_SESSION")
    usable = (
        not reasons and concept == "CURRENT_COMMON_SHARES_OUTSTANDING" and integer is not None
    )
    caller_proxy = share.get("research_proxy_eligible") is True
    return {
        "contract_version": CONTRACT_VERSION,
        "current_common_shares": integer if usable else None,
        "research_multiple_share_allowed": usable,
        "caller_research_proxy_eligible": caller_proxy,
        "research_proxy_overridden": caller_proxy and not usable,
        "reason_codes": sorted(set(reasons)),
        "official_fact_admitted": False,
        "charter_capital_divided_by_par": False,
        "authority_effect": "NONE",
    }


def reject_par_division(charter_capital_amount: int, par_value: int | None, share_value: int | None) -> dict[str, Any]:
    """Charter capital stays an amount. Dividing by a par, supplied or assumed, does not create shares."""
    reasons = ["CHARTER_CAPITAL_IS_NOT_A_SHARE_COUNT"]
    divided = None
    if par_value is not None:
        reasons.append("SUPPLIED_PAR_DOES_NOT_CREATE_A_SHARE_COUNT")
        if par_value > 0:
            divided = charter_capital_amount // par_value
            if share_value is not None and divided == share_value:
                reasons.append("PAR_DIVISION_MATCHES_A_SHARE_FIELD_AND_STAYS_REJECTED")
    else:
        reasons.append("MISSING_PAR_IS_NOT_ASSUMED_AT_10000")
    return {
        "contract_version": CONTRACT_VERSION,
        "shares_created": None,
        "rejected_quotient": divided,
        "reason_codes": sorted(set(reasons)),
        "official_fact_admitted": False,
    }


def project_corporate_action(action: Mapping[str, Any] | None, *, price_session: str) -> dict[str, Any]:
    """Keep the traded bar. A plan or an unproven ex-date does not change shares or history."""
    payload = dict(action or {})
    lifecycle = _text(payload.get("lifecycle") or payload.get("event_status") or "UNKNOWN")
    reasons: list[str] = []
    if not payload:
        reasons.append("NO_CORPORATE_ACTION_SUPPLIED")
    else:
        if payload.get("ex_date_qualified") is not True:
            reasons.append("EX_DATE_NOT_QUALIFIED_PRICE_UNCHANGED")
        if lifecycle in PLANNED:
            reasons.append("PLANNED_SHARES_ARE_NOT_OUTSTANDING")
        if payload.get("adjust_historical_ohlc") is True:
            reasons.append("HISTORICAL_OHLC_ADJUSTMENT_REFUSED")
    return {
        "contract_version": CONTRACT_VERSION,
        "price_session": price_session,
        "lifecycle": lifecycle,
        "shares_added": None,
        "price_factor_applied": None,
        "historical_bar_adjusted": False,
        "reason_codes": sorted(set(reasons)),
        "official_fact_admitted": False,
    }


def _same_statement_pair(profit: Mapping[str, Any], cash: Mapping[str, Any]) -> list[str]:
    reasons: list[str] = []
    if profit.get("ticker") != cash.get("ticker"):
        reasons.append("TICKER_MISMATCH")
    if profit.get("statement_scope") != cash.get("statement_scope") or profit.get("statement_scope") in {None, "", "UNKNOWN"}:
        reasons.append("STATEMENT_SCOPE_MISMATCH")
    if profit.get("reporting_period") != cash.get("reporting_period"):
        reasons.append("PERIOD_MISMATCH")
    if profit.get("currency") != cash.get("currency") or profit.get("currency") in {None, "", "UNKNOWN"}:
        reasons.append("CURRENCY_MISMATCH")
    if profit.get("document_sha256") != cash.get("document_sha256") or not profit.get("document_sha256"):
        reasons.append("DOCUMENT_HASH_MISMATCH")
    if str(profit.get("unit_scale")) != str(cash.get("unit_scale")):
        reasons.append("UNIT_SCALE_MISMATCH")
    return reasons


def cash_conversion(profit: Mapping[str, Any], operating_cash: Mapping[str, Any]) -> dict[str, Any]:
    """Pair printed parent profit with printed operating cash from the same statement column."""
    reasons = _same_statement_pair(profit, operating_cash)
    if profit.get("status") == PRESS_STATUS or operating_cash.get("status") == PRESS_STATUS:
        reasons.append("PRESS_RELEASE_IS_NOT_A_STATEMENT")
    if profit.get("accounting_identity") != "PARENT_PROFIT_AFTER_TAX":
        reasons.append("EARNINGS_LINE_IS_NOT_PARENT_PROFIT")
    if operating_cash.get("accounting_identity") != "OPERATING_CASH_FLOW":
        reasons.append("CASH_LINE_IS_NOT_OPERATING_CASH_FLOW")
    if operating_cash.get("accounting_identity") == "COMPOSITE_CASH_FLOW_DEPRECIATION_ADJUSTMENT":
        reasons.append("DEPRECIATION_ADJUSTMENT_IS_NOT_EBITDA")
    profit_value = profit.get("normalized_integer")
    cash_value = operating_cash.get("normalized_integer")
    if not isinstance(profit_value, int) or isinstance(profit_value, bool) or profit_value == 0:
        reasons.append("PARENT_PROFIT_ABSENT_OR_ZERO")
    if not isinstance(cash_value, int) or isinstance(cash_value, bool):
        reasons.append("OPERATING_CASH_FLOW_ABSENT")
    visual = profit.get("origin") == VISUAL_ORIGIN or operating_cash.get("origin") == VISUAL_ORIGIN
    if visual:
        reasons.append("VISUAL_REVIEW_IS_NOT_NATIVE_TEXT")
    scope_warning = None
    if (
        profit.get("accounting_identity") == "PARENT_PROFIT_AFTER_TAX"
        and operating_cash.get("accounting_identity") == "OPERATING_CASH_FLOW"
        and profit.get("statement_scope") == operating_cash.get("statement_scope") == "consolidated"
    ):
        scope_warning = "CONSOLIDATED_OPERATING_CASH_FLOW_OVER_PARENT_ATTRIBUTABLE_PROFIT"
    if profit.get("period_semantic_state") == "UNKNOWN_DURATION" or operating_cash.get("period_semantic_state") == "UNKNOWN_DURATION":
        reasons.append("DURATION_UNPROVEN_NO_ANNUALIZATION")
    ratio = None
    if isinstance(profit_value, int) and not isinstance(profit_value, bool) and profit_value != 0 and isinstance(cash_value, int) and not isinstance(cash_value, bool):
        if not any(code in reasons for code in (
            "TICKER_MISMATCH", "STATEMENT_SCOPE_MISMATCH", "PERIOD_MISMATCH", "CURRENCY_MISMATCH",
            "DOCUMENT_HASH_MISMATCH", "UNIT_SCALE_MISMATCH", "PRESS_RELEASE_IS_NOT_A_STATEMENT",
            "EARNINGS_LINE_IS_NOT_PARENT_PROFIT", "CASH_LINE_IS_NOT_OPERATING_CASH_FLOW",
            "PARENT_PROFIT_ABSENT_OR_ZERO", "OPERATING_CASH_FLOW_ABSENT",
        )):
            ratio = Decimal(cash_value) / Decimal(profit_value)
    status = BLOCKED if ratio is None else ("VISUAL_REVIEW_RATIO_NOT_ADMITTED" if visual else RESEARCH_CANDIDATE)
    return {
        "contract_version": CONTRACT_VERSION,
        "status": status,
        "ratio": None if ratio is None else format(ratio, "f"),
        "operating_cash_flow": cash_value if isinstance(cash_value, int) else None,
        "parent_profit_after_tax": profit_value if isinstance(profit_value, int) else None,
        "ttm_constructed": False,
        "scope_warning": scope_warning,
        "reason_codes": sorted(set(reasons)),
        "official_fact_admitted": False,
        "valuation_use": "CLOSED",
        "is_actionable": False,
    }


def scale_invariant_return(previous_close: Any, current_close: Any, *, same_representation: bool) -> dict[str, Any]:
    """A return inside one native series does not require a VND unit."""
    previous = _decimal(previous_close)
    current = _decimal(current_close)
    reasons: list[str] = []
    if not same_representation:
        reasons.append("CROSS_REPRESENTATION_RETURN_REFUSED")
    if previous is None or current is None or previous <= 0 or current <= 0:
        reasons.append("NON_POSITIVE_NATIVE_CLOSE")
    value = None if reasons else (current / previous) - Decimal(1)
    return {
        "contract_version": CONTRACT_VERSION,
        "status": BLOCKED if reasons else "SCALE_INVARIANT_RETURN_ALLOWED",
        "return": None if value is None else format(value, "f"),
        "monetary_market_cap": None,
        "reason_codes": sorted(set(reasons)),
        "official_fact_admitted": False,
        "authority_effect": "NONE",
    }


def _earnings_blockers(earnings: Mapping[str, Any] | None, *, entity: str) -> list[str]:
    if not earnings:
        return ["EARNINGS_ABSENT"]
    reasons: list[str] = []
    if earnings.get("status") == PRESS_STATUS or earnings.get("fact_origin") == "PRESS_HIGHLIGHT":
        reasons.append("PRESS_RELEASE_IS_NOT_A_STATEMENT")
    if earnings.get("accounting_identity") != "PARENT_PROFIT_AFTER_TAX":
        reasons.append("EARNINGS_IDENTITY_IS_NOT_PARENT_PROFIT")
    if earnings.get("statement_scope") in {None, "", "UNKNOWN"}:
        reasons.append("STATEMENT_SCOPE_NOT_EXPLICIT")
    if earnings.get("period_semantic_state") in {None, "", "UNKNOWN_DURATION"} or _text(earnings.get("reporting_period")).endswith("-H1"):
        reasons.append("NO_TTM_FROM_UNPROVEN_OR_INTERIM_PERIOD")
    if entity in SPECIALIST_ENTITIES and earnings.get("accounting_identity") == "NET_REVENUE":
        reasons.append("INDUSTRIAL_REVENUE_IS_NOT_A_SPECIALIST_EARNINGS_LINE")
    return reasons


def assess_valuation_uses(
    *,
    ticker: str,
    entity: str,
    price: Mapping[str, Any],
    share: Mapping[str, Any],
    earnings: Mapping[str, Any] | None = None,
    book_equity: Mapping[str, Any] | None = None,
    sales: Mapping[str, Any] | None = None,
    eps_denominator_values: list[int] | None = None,
    corporate_action: Mapping[str, Any] | None = None,
    prior_metric_status: Mapping[str, str] | None = None,
    knowledge_cutoff: str | None = None,
) -> dict[str, Any]:
    """Say which displayed research multiple is blocked, and which arithmetic was refused."""
    session = _text(price.get("session"))
    price_state = classify_price_for_monetary_valuation(price)
    share_state = classify_share_for_valuation(
        share, eps_denominator_values=eps_denominator_values, price_session=session, knowledge_cutoff=knowledge_cutoff,
    )
    action_state = project_corporate_action(corporate_action, price_session=session)
    monetary = _decimal(price_state["monetary_vnd_per_share"])
    shares = share_state["current_common_shares"]
    base_reasons = list(price_state["reason_codes"]) + list(share_state["reason_codes"])
    if "EX_DATE_NOT_QUALIFIED_PRICE_UNCHANGED" in action_state["reason_codes"] and corporate_action:
        base_reasons.append("CORPORATE_ACTION_CONTINUITY_UNPROVEN")
    if "PLANNED_SHARES_ARE_NOT_OUTSTANDING" in action_state["reason_codes"]:
        base_reasons.append("PLANNED_DILUTION_NOT_IN_SHARE_COUNT")

    def use(name: str, extra: list[str], value: Decimal | None) -> dict[str, Any]:
        reasons = sorted(set(base_reasons + extra))
        permitted = not reasons and value is not None
        prior = (prior_metric_status or {}).get(name)
        return {
            "use": name,
            "status": RESEARCH_CANDIDATE if permitted else BLOCKED,
            "value": None if not permitted or value is None else format(value, "f"),
            "prior_status": prior,
            "prior_research_usable_now_blocked": prior == "RESEARCH_USABLE" and not permitted,
            "reason_codes": reasons,
            "official_fact_admitted": False,
            "is_actionable": False,
            "target_price": None,
        }

    market_cap = monetary * Decimal(shares) if monetary is not None and shares is not None else None
    earnings_reasons = _earnings_blockers(earnings, entity=entity)
    earnings_value = earnings.get("normalized_integer") if earnings else None
    pe = None
    if market_cap is not None and isinstance(earnings_value, int) and not isinstance(earnings_value, bool) and earnings_value > 0 and not earnings_reasons:
        pe = market_cap / Decimal(earnings_value)
    equity_reasons: list[str] = []
    equity_value = None
    if not book_equity:
        equity_reasons.append("BOOK_EQUITY_ABSENT")
    else:
        if book_equity.get("accounting_identity") != "PARENT_BOOK_EQUITY_PRINTED_NOT_DERIVED":
            equity_reasons.append("TOTAL_OR_UNLABELED_EQUITY_IS_NOT_PARENT_BOOK")
        equity_value = book_equity.get("normalized_integer")
        if not isinstance(equity_value, int) or isinstance(equity_value, bool) or equity_value <= 0:
            equity_reasons.append("PARENT_BOOK_EQUITY_ABSENT")
    pb = market_cap / Decimal(equity_value) if market_cap is not None and isinstance(equity_value, int) and not isinstance(equity_value, bool) and equity_value > 0 and not equity_reasons else None
    sales_reasons: list[str] = []
    sales_value = None
    if not sales:
        sales_reasons.append("SALES_ABSENT")
    else:
        if sales.get("accounting_identity") != "NET_REVENUE":
            sales_reasons.append("SALES_IDENTITY_IS_NOT_NET_REVENUE")
        if sales.get("period_semantic_state") in {None, "", "UNKNOWN_DURATION"}:
            sales_reasons.append("NO_TTM_FROM_UNPROVEN_OR_INTERIM_PERIOD")
        sales_value = sales.get("normalized_integer")
    ps = market_cap / Decimal(sales_value) if market_cap is not None and isinstance(sales_value, int) and not isinstance(sales_value, bool) and sales_value > 0 and not sales_reasons else None
    specialist = ["SECTOR_SPECIALIST_METHOD_NOT_APPLICABLE"] if entity in SPECIALIST_ENTITIES else ["ENTERPRISE_VALUE_COMPONENTS_ABSENT"]

    rejected = None
    raw_shares = share.get("value")
    if (
        price_state.get("research_vnd_per_share") is None
        and _decimal((price.get("price_representation") or {}).get("canonical_value")) is not None
        and isinstance(raw_shares, int) and not isinstance(raw_shares, bool) and raw_shares > 0
        and "NATIVE_VND_FIELD_MUST_NOT_TAKE_PRICE_SCALE" in price_state["reason_codes"]
    ):
        rejected = {
            "label": REJECTED_ARITHMETIC,
            "reason": "NATIVE_VND_FIELD_MUST_NOT_TAKE_PRICE_SCALE",
        }
    uses = {
        "market_cap": use("market_cap", [], market_cap),
        "P/E": use("P/E", earnings_reasons, pe),
        "P/B": use("P/B", equity_reasons, pb),
        "P/S": use("P/S", sales_reasons, ps),
        "EV/EBITDA": use("EV/EBITDA", specialist, None),
        "EV/Sales": use("EV/Sales", specialist + sales_reasons, None),
    }
    return {
        "contract_version": CONTRACT_VERSION,
        "ticker": ticker.upper(),
        "entity": entity,
        "price": price_state,
        "share": share_state,
        "corporate_action": action_state,
        "uses": uses,
        "rejected_arithmetic": rejected,
        "volume_traded_value": "BLOCKED_BY_EVIDENCE" if price.get("volume_unit") in UNDOCUMENTED_PRICE_TOKENS else "VOLUME_UNIT_PRESENT_VALUE_STILL_UNCOMPUTED",
        "historical_basis_modified": False,
        "pit_backfill": False,
        "official_fact_admitted": False,
        "valuation_use": "CLOSED",
        "is_actionable": False,
    }


def comparability(left: Mapping[str, Any], right: Mapping[str, Any], method: str) -> dict[str, Any]:
    """Two research rows support a comparison only when the method's identities match."""
    reasons: list[str] = []
    if left.get("entity") in SPECIALIST_ENTITIES or right.get("entity") in SPECIALIST_ENTITIES:
        if method in INDUSTRIAL_ONLY:
            reasons.append("SECTOR_SPECIALIST_METHOD_NOT_APPLICABLE")
    if left.get("entity") != right.get("entity") and method in INDUSTRIAL_ONLY:
        reasons.append("ENTITY_CLASS_DIFFERS")
    left_price = (left.get("price") or {}).get("monetary_valuation_permitted")
    right_price = (right.get("price") or {}).get("monetary_valuation_permitted")
    if left_price is not True or right_price is not True:
        reasons.append("PRICE_UNIT_NOT_COMPARABLE")
    left_earnings = ((left.get("uses") or {}).get(method) or {}).get("reason_codes") or []
    right_earnings = ((right.get("uses") or {}).get(method) or {}).get("reason_codes") or []
    if "EARNINGS_IDENTITY_IS_NOT_PARENT_PROFIT" in left_earnings or "EARNINGS_IDENTITY_IS_NOT_PARENT_PROFIT" in right_earnings:
        reasons.append("EARNINGS_IDENTITY_DIFFERS")
    if left.get("reporting_period_class") != right.get("reporting_period_class"):
        reasons.append("PERIOD_CLASS_DIFFERS")
    return {
        "contract_version": CONTRACT_VERSION,
        "method": method,
        "status": "COMPARABLE_RESEARCH_CONTEXT" if not reasons else "NOT_COMPARABLE",
        "reason_codes": sorted(set(reasons)),
        "ranking_produced": False,
        "official_fact_admitted": False,
    }
