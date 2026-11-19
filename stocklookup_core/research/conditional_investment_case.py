"""Owner research case from already qualified or candidate financial evidence.

The case repeats deterministic labels. It does not invent a target price, a
probability, a TTM multiple, or a parent-book ratio from total equity.
"""
from __future__ import annotations

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
