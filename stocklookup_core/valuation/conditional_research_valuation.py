"""Research valuation from a filing and a provider close.

Owner-accepted thousand-VND quotes and a same-filing share count can support a
conditional research market cap. They do not become a verified source unit,
current-share authority, a TTM multiple, or an execution input.
"""
from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from typing import Any, Mapping

from stocklookup_core.evidence.investment_evidence_assembly import (
    CONTRACT_VERSION,
    SPECIALIST_ENTITIES,
    cash_conversion,
    classify_price_for_monetary_valuation,
)

CONDITIONAL = "CONDITIONAL_RESEARCH_ESTIMATE"
UNUSABLE = "UNUSABLE"
STRICT = "STRICT_DECISION_ELIGIBLE"

_MONTHS = {
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5, "june": 6,
    "july": 7, "august": 8, "september": 9, "october": 10, "november": 11, "december": 12,
}


def _decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    return number if number.is_finite() else None


def _integer(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int):
        return None
    return value


def parse_reported_integer(raw: str, *, unit_scale: int = 1) -> dict[str, Any]:
    """Parse a printed integer. Parentheses are negative. Scale must be explicit."""
    text = str(raw or "").strip().replace(" ", "")
    reasons: list[str] = []
    if unit_scale not in {1, 1_000, 1_000_000, 1_000_000_000}:
        reasons.append("UNIT_SCALE_NOT_AN_EXPLICIT_POWER_OF_1000")
    if not re.fullmatch(r"\(?\d{1,3}(?:[,.]\d{3})*\)?|\(?\d+\)?", text):
        reasons.append("NUMERIC_TEXT_AMBIGUOUS")
        return {"value": None, "reason_codes": reasons}
    negative = text.startswith("(") and text.endswith(")")
    digits = text.strip("()").replace(",", "").replace(".", "")
    if not digits.isdigit() or reasons:
        return {"value": None, "reason_codes": reasons or ["NUMERIC_TEXT_AMBIGUOUS"]}
    value = int(digits) * unit_scale
    return {"value": -value if negative else value, "reason_codes": [], "fractional": False}


def quoted_iso_date(text: str, *, phrase: str) -> str | None:
    """Read one English date that the supplied quote actually prints after a phrase."""
    match = re.search(phrase + r"\s+(\d{1,2})\s+([A-Za-z]+)\s+(\d{4})", text or "", flags=re.IGNORECASE)
    if match is None:
        return None
    month = _MONTHS.get(match.group(2).lower())
    day = int(match.group(1))
    if month is None or not 1 <= day <= 31:
        return None
    return f"{int(match.group(3)):04d}-{month:02d}-{day:02d}"


def _money(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f")


def _ratio(left: Decimal, right: Decimal) -> str | None:
    if right == 0:
        return None
    return format(left / right, "f")


def filing_share_basis(components: Mapping[str, Any], *, price_session: str, provider_share: int | None = None) -> dict[str, Any]:
    """One filing can support a post-dividend research count. It is still one source."""
    opening = _integer(components.get("opening_ordinary_shares"))
    dividend = _integer(components.get("stock_dividend_shares"))
    denominator = _integer(components.get("eps_denominator_shares"))
    june_capital = _integer(components.get("june_contributed_capital_vnd"))
    charter = _integer(components.get("subsequent_charter_capital_vnd"))
    quote = str(components.get("listing_quote") or "")
    trade_from = quoted_iso_date(quote, phrase="traded from")
    listing_effective = quoted_iso_date(quote, phrase="effective date of the listing change")
    reasons: list[str] = []
    foots: list[dict[str, Any]] = []

    def foot(name: str, ok: bool) -> None:
        foots.append({"name": name, "exact": ok})
        if not ok:
            reasons.append(name)

    foot("OPENING_PLUS_DIVIDEND_EQUALS_EPS_DENOMINATOR", opening is not None and dividend is not None and denominator is not None and opening + dividend == denominator)
    foot(
        "JUNE_CONTRIBUTED_CAPITAL_EQUALS_OPENING_TIMES_10000",
        june_capital is not None and opening not in (None, 0) and june_capital == opening * 10_000,
    )
    foot(
        "SUBSEQUENT_CHARTER_EQUALS_EPS_DENOMINATOR_TIMES_10000",
        charter is not None and denominator not in (None, 0) and charter == denominator * 10_000,
    )
    if trade_from is None:
        reasons.append("DIVIDEND_TRADE_DATE_NOT_IN_QUOTED_TEXT")
    if listing_effective is None:
        reasons.append("LISTING_EFFECTIVE_DATE_NOT_IN_QUOTED_TEXT")
    session_after = bool(trade_from and price_session >= trade_from)
    if trade_from and not session_after:
        reasons.append("PRICE_SESSION_BEFORE_QUOTED_TRADE_DATE")
    same_number = provider_share == denominator
    usable = not any(item["name"].startswith(("OPENING_", "JUNE_", "SUBSEQUENT_")) and not item["exact"] for item in foots)
    usable = usable and session_after and denominator is not None
    limits = [
        "SINGLE_FILING_IS_NOT_MULTIPLE_INDEPENDENT_SOURCES",
        "VISUAL_OR_NOTE_TEXT_IS_NOT_A_VSDC_CERTIFICATE",
        "NO_PROOF_THAT_NO_LATER_ISSUANCE_OCCURRED",
        "STRICT_CURRENT_COMMON_OUTSTANDING_NOT_ESTABLISHED",
        "PAR_10000_IS_THE_FILING_RATIO_NOT_A_SEPARATE_SHARE_COUNT",
    ]
    if same_number:
        limits.append("PROVIDER_ISSUE_SHARE_REPEATS_THE_FILING_COUNT")
    return {
        "contract_version": CONTRACT_VERSION,
        "research_shares": denominator if usable else None,
        "pre_dividend_shares": opening,
        "eligibility": CONDITIONAL if usable else UNUSABLE,
        "role": "POST_DIVIDEND_ORDINARY_COUNT_SAME_FILING" if usable else None,
        "independent_source_count": 1 if usable else 0,
        "provider_share_is_independent": False,
        "quoted_trade_from": trade_from,
        "quoted_listing_effective": listing_effective,
        "price_session": price_session,
        "cross_foots": foots,
        "limits": limits,
        "reason_codes": sorted(set(reasons)),
        "strict_current_common_outstanding": False,
        "official_fact_admitted": False,
    }


def _line(facts: Mapping[str, Any], identity: str) -> Mapping[str, Any] | None:
    row = facts.get(identity)
    return row if isinstance(row, Mapping) else None


def _column_key(row: Mapping[str, Any]) -> tuple:
    return tuple(row.get(key) for key in (
        "ticker", "document_sha256", "statement_scope", "reporting_period", "currency", "unit_scale",
    ))


def _line_amount(facts: Mapping[str, Any], identity: str) -> int | None:
    row = _line(facts, identity)
    if row is None:
        return None
    return _integer(row.get("normalized_integer"))


def statement_cross_foot(facts: Mapping[str, Mapping[str, Any]]) -> list[dict[str, Any]]:
    """Exact identities inside one reported column. A residual blocks dependent uses."""
    results = []

    def add(name: str, left: int | None, right: int | None, parts: list[str]) -> None:
        if left is None or right is None:
            results.append({"name": name, "status": "INCOMPLETE", "residual": None, "parts": parts})
            return
        rows = [facts[key] for key in parts]
        column = _column_key(rows[0])
        if not all(column) or any(_column_key(row) != column for row in rows[1:]):
            results.append({"name": name, "status": "INCOMPATIBLE_COLUMN", "residual": None, "parts": parts})
            return
        residual = left - right
        results.append({
            "name": name, "status": "EXACT" if residual == 0 else "RESIDUAL",
            "residual": residual, "parts": parts,
        })

    add(
        "NET_REVENUE_EQUALS_GROSS_MINUS_DEDUCTIONS",
        _line_amount(facts, "NET_REVENUE"),
        None if _line_amount(facts, "GROSS_REVENUE") is None or _line_amount(facts, "REVENUE_DEDUCTIONS") is None
        else _line_amount(facts, "GROSS_REVENUE") - _line_amount(facts, "REVENUE_DEDUCTIONS"),
        ["GROSS_REVENUE", "REVENUE_DEDUCTIONS", "NET_REVENUE"],
    )
    add(
        "TOTAL_PAT_EQUALS_PARENT_PLUS_NCI",
        _line_amount(facts, "TOTAL_PROFIT_AFTER_TAX"),
        None if _line_amount(facts, "PARENT_PROFIT_AFTER_TAX") is None or _line_amount(facts, "NCI_PROFIT_AFTER_TAX") is None
        else _line_amount(facts, "PARENT_PROFIT_AFTER_TAX") + _line_amount(facts, "NCI_PROFIT_AFTER_TAX"),
        ["TOTAL_PROFIT_AFTER_TAX", "PARENT_PROFIT_AFTER_TAX", "NCI_PROFIT_AFTER_TAX"],
    )
    return results


def _use(name: str, *, eligibility: str, value: str | None, period: str | None, identity: str, limits: list[str]) -> dict[str, Any]:
    return {
        "use": name,
        "eligibility": eligibility,
        "value": value,
        "period": period,
        "denominator_identity": identity,
        "limits": limits,
        "strict_decision_eligible": False,
        "is_actionable": False,
        "target_price": None,
        "official_fact_admitted": False,
    }


def industrial_research_profile(
    *,
    ticker: str,
    price: Mapping[str, Any],
    share_components: Mapping[str, Any],
    facts: Mapping[str, Mapping[str, Any]],
    provider_share: int | None = None,
    entity: str = "corporate",
) -> dict[str, Any]:
    """Build the research profile. Missing TTM or parent book stays unusable without blanking the rest."""
    session = str(price.get("session") or "")
    price_state = classify_price_for_monetary_valuation(price)
    shares = filing_share_basis(share_components, price_session=session, provider_share=provider_share)
    research_px = _decimal(price_state.get("research_vnd_per_share"))
    count = shares.get("research_shares")
    facts = {
        identity: row for identity, row in facts.items()
        if isinstance(row, Mapping)
        and row.get("ticker") == ticker.upper()
        and row.get("accounting_identity") == identity
        and row.get("statement_scope") == "consolidated"
        and row.get("currency") == "VND"
        and row.get("unit_scale") == 1
        and row.get("document_sha256")
        and row.get("reporting_period")
    }
    foots = statement_cross_foot(facts)
    foot_state = {item["name"]: item["status"] for item in foots}
    market_cap = research_px * Decimal(count) if research_px is not None and isinstance(count, int) else None
    pre = shares.get("pre_dividend_shares")
    incompatible = research_px * Decimal(pre) if research_px is not None and isinstance(pre, int) and shares.get("quoted_trade_from") and session >= shares["quoted_trade_from"] else None
    parent = _line(facts, "PARENT_PROFIT_AFTER_TAX")
    revenue = _line(facts, "NET_REVENUE")
    equity = _line(facts, "TOTAL_EQUITY_INCLUDING_NCI")
    parent_equity = _line(facts, "PARENT_BOOK_EQUITY_PRINTED_NOT_DERIVED")
    parent_amount = _integer((parent or {}).get("normalized_integer"))
    revenue_amount = _integer((revenue or {}).get("normalized_integer"))
    equity_amount = _integer((equity or {}).get("normalized_integer"))
    visual_limits = ["VISUAL_REVIEW_NOT_NATIVE_TEXT", "SAME_FILING_COLUMN", "NOT_TTM", "NOT_ANNUALIZED"]
    period = (parent or {}).get("reporting_period")
    revenue_ok = foot_state.get("NET_REVENUE_EQUALS_GROSS_MINUS_DEDUCTIONS") == "EXACT"
    profit_ok = foot_state.get("TOTAL_PAT_EQUALS_PARENT_PLUS_NCI") == "EXACT"
    cap_limits = list(shares.get("limits") or []) + [
        "PRICE_IS_OWNER_CONVENTION_NOT_ENDPOINT_PROOF",
        "ADJUSTMENT_BASIS_UNRESOLVED_USES_PROVIDER_CLOSE_AS_QUOTED",
    ]
    multiples = {
        "market_cap": _use(
            "market_cap",
            eligibility=CONDITIONAL if market_cap is not None else UNUSABLE,
            value=_money(market_cap),
            period=session,
            identity="POST_DIVIDEND_ORDINARY_COUNT_SAME_FILING",
            limits=cap_limits,
        ),
        "price_over_reported_interim_parent_profit": _use(
            "price_over_reported_interim_parent_profit",
            eligibility=CONDITIONAL if market_cap is not None and parent_amount not in (None, 0) and profit_ok else UNUSABLE,
            value=_ratio(market_cap, Decimal(parent_amount)) if market_cap is not None and parent_amount not in (None, 0) and profit_ok else None,
            period=period,
            identity="PARENT_PROFIT_AFTER_TAX",
            limits=visual_limits + ["H1_OR_INTERIM_COLUMN_IS_NOT_A_TTM_PE"],
        ),
        "pe_ttm": _use("pe_ttm", eligibility=UNUSABLE, value=None, period=None, identity="PARENT_PROFIT_AFTER_TAX",
                      limits=["FOUR_COMPATIBLE_QUARTER_COLUMNS_ABSENT", "NO_ANNUALIZATION"]),
        "price_over_reported_interim_net_revenue": _use(
            "price_over_reported_interim_net_revenue",
            eligibility=CONDITIONAL if market_cap is not None and revenue_amount not in (None, 0) and revenue_ok else UNUSABLE,
            value=_ratio(market_cap, Decimal(revenue_amount)) if market_cap is not None and revenue_amount not in (None, 0) and revenue_ok else None,
            period=(revenue or {}).get("reporting_period"),
            identity="NET_REVENUE",
            limits=visual_limits + ["INTERIM_REVENUE_IS_NOT_A_TTM_PS"],
        ),
        "ps_ttm": _use("ps_ttm", eligibility=UNUSABLE, value=None, period=None, identity="NET_REVENUE",
                      limits=["FOUR_COMPATIBLE_QUARTER_COLUMNS_ABSENT"]),
        "price_over_total_equity_including_nci": _use(
            "price_over_total_equity_including_nci",
            eligibility=CONDITIONAL if market_cap is not None and equity_amount not in (None, 0) else UNUSABLE,
            value=_ratio(market_cap, Decimal(equity_amount)) if market_cap is not None and equity_amount not in (None, 0) else None,
            period=(equity or {}).get("reporting_period"),
            identity="TOTAL_EQUITY_INCLUDING_NCI",
            limits=["THIS_IS_NOT_PARENT_BOOK_PB", "NCI_REMAINS_INSIDE_THE_DENOMINATOR"],
        ),
        "pb_parent": _use(
            "pb_parent",
            eligibility=UNUSABLE,
            value=None,
            period=None,
            identity="PARENT_BOOK_EQUITY_PRINTED_NOT_DERIVED",
            limits=["PARENT_BOOK_EQUITY_NOT_PRINTED"] if parent_equity is None else ["PARENT_BOOK_PRESENT_BUT_PROFILE_REQUIRES_EXPLICIT_LINE"],
        ),
        "ev_ebitda": _use(
            "ev_ebitda",
            eligibility=UNUSABLE if entity not in SPECIALIST_ENTITIES else UNUSABLE,
            value=None,
            period=None,
            identity="EV_EBITDA",
            limits=(["SECTOR_SPECIALIST_METHOD_NOT_APPLICABLE"] if entity in SPECIALIST_ENTITIES else [
                "LOAN_AND_FINANCE_LEASE_LINES_ARE_NOT_A_DEBT_BALANCE",
                "CASH_FLOW_DEPRECIATION_LINE_IS_NOT_EBITDA",
            ]),
        ),
    }
    if parent_equity is not None and market_cap is not None:
        book = _integer(parent_equity.get("normalized_integer"))
        if book not in (None, 0):
            multiples["pb_parent"] = _use(
                "pb_parent", eligibility=CONDITIONAL, value=_ratio(market_cap, Decimal(book)),
                period=parent_equity.get("reporting_period"), identity="PARENT_BOOK_EQUITY_PRINTED_NOT_DERIVED",
                limits=visual_limits,
            )
    operating = _line(facts, "OPERATING_CASH_FLOW")
    cash = None
    if parent is not None and operating is not None:
        cash = cash_conversion(parent, operating)
    return {
        "contract_version": CONTRACT_VERSION,
        "ticker": ticker.upper(),
        "entity": entity,
        "session": session,
        "price": price_state,
        "share_basis": shares,
        "statement_cross_foots": foots,
        "market_cap_vnd": _money(market_cap),
        "incompatible_pre_dividend_market_cap": {
            "eligibility": UNUSABLE,
            "value_vnd": _money(incompatible),
            "reason": "PRICE_ON_OR_AFTER_DIVIDEND_TRADE_DATE_CANNOT_USE_OPENING_SHARES",
        } if incompatible is not None else None,
        "multiples": multiples,
        "cash_conversion": cash,
        "strict_decision_eligible": False,
        "execution_eligible": False,
        "official_fact_admitted": False,
        "historical_basis_modified": False,
        "is_actionable": False,
    }


def specialist_research_guard(entity: str, method: str) -> dict[str, Any]:
    """Industrial enterprise value stays off bank, broker, insurer, and finance-company statements."""
    blocked = entity in SPECIALIST_ENTITIES and method in {"EV/EBITDA", "EV/Sales", "EV"}
    return {
        "entity": entity,
        "method": method,
        "eligibility": UNUSABLE if blocked else CONDITIONAL,
        "reason_codes": ["SECTOR_SPECIALIST_METHOD_NOT_APPLICABLE"] if blocked else [],
        "replacement_research_line": "PARENT_PROFIT_AFTER_TAX" if blocked else None,
        "official_fact_admitted": False,
    }


def scope_and_period_bridge(rows: list[Mapping[str, Any]]) -> dict[str, Any]:
    """Keep consolidated apart from separate, and a quarter apart from the year-to-date column."""
    def amount(row: Mapping[str, Any]) -> int | None:
        return _integer(row.get("normalized_integer"))

    indexed = {(row.get("scope"), row.get("period"), row.get("identity")): row for row in rows}
    findings = []
    consol_q = indexed.get(("consolidated", "2026-Q3", "PARENT_PROFIT_AFTER_TAX"))
    separate_q = indexed.get(("separate", "2026-Q3", "TOTAL_PROFIT_AFTER_TAX")) or indexed.get(("separate", "2026-Q3", "PROFIT_AFTER_TAX"))
    nine = indexed.get(("consolidated", "2026-9M", "PARENT_PROFIT_AFTER_TAX"))
    if consol_q and separate_q and amount(consol_q) is not None and amount(separate_q) is not None:
        findings.append({
            "name": "CONSOLIDATED_PARENT_VERSUS_SEPARATE_PROFIT",
            "eligibility": CONDITIONAL,
            "consolidated_parent": amount(consol_q),
            "separate_profit": amount(separate_q),
            "same_number": amount(consol_q) == amount(separate_q),
            "limits": ["SEPARATE_PROFIT_IS_NOT_GROUP_PROFIT", "OCR_CANDIDATE_NOT_NATIVE_LEXEME"],
        })
    if consol_q and nine and amount(consol_q) is not None and amount(nine) is not None:
        findings.append({
            "name": "QUARTER_IS_NOT_YEAR_TO_DATE",
            "eligibility": CONDITIONAL,
            "quarter_parent": amount(consol_q),
            "nine_month_parent": amount(nine),
            "quarter_plus_nine_month": None,
            "limits": ["ADDING_Q3_TO_9M_WOULD_DOUBLE_COUNT", "Q3_TIMES_FOUR_IS_NOT_A_YEAR"],
        })
    q_total = indexed.get(("consolidated", "2026-Q3", "TOTAL_PROFIT_AFTER_TAX"))
    q_nci = indexed.get(("consolidated", "2026-Q3", "NCI_PROFIT_AFTER_TAX"))
    if consol_q and q_total and q_nci:
        left = amount(q_total)
        right = None if amount(consol_q) is None or amount(q_nci) is None else amount(consol_q) + amount(q_nci)
        findings.append({
            "name": "Q3_TOTAL_EQUALS_PARENT_PLUS_NCI",
            "eligibility": CONDITIONAL if left is not None and left == right else UNUSABLE,
            "residual": None if left is None or right is None else left - right,
            "limits": ["OCR_CANDIDATE_NOT_NATIVE_LEXEME"],
        })
    return {
        "contract_version": CONTRACT_VERSION,
        "findings": findings,
        "market_cap": None,
        "reason_no_market_cap": "NO_PRICE_OBSERVATION_SUPPLIED_FOR_THIS_PROFILE",
        "strict_decision_eligible": False,
        "official_fact_admitted": False,
    }
