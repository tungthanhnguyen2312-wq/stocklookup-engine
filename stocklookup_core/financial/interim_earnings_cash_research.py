"""Reviewed interim earnings and cash research (REVIEWED_INTERIM_EARNINGS_AND_CASH_RESEARCH_V1).

A non-voting description of what a company reports it earns and converts into operating cash,
built only from the admitted official exact-field stream (``official_field_context``) through the
same gate as the official income context. Every measurement names its method; nothing here is a
threshold, score, vote, valuation input, annualization, TTM, free cash flow or net cash.

- Earnings economics: revenue, total and parent profit, explicitly reported non-operating lines.
- Cash conversion: operating cash flow against profit of the *same statement set* (document,
  explicit bounds, scope, currency, comparative basis); a ratio only over a positive profit.
- Matched-period comparisons: same metric/line/scope/currency/assurance, explicit prior-year
  calendar bounds, and every issuer comparability caution satisfied.
- Earnings quality and comparability: divergence, exceptional lines and missing components
  stay explicit; unresolved items are UNKNOWN, never inferred.

``config/interim_earnings_cash_issuer_gates_v1.json`` is a closed registry of source-declared
comparability cautions and qualification blockers. It only refuses or explains; it carries no
amount. Financial-sector or unresolved entities receive no industrial cash interpretation.
"""
from __future__ import annotations

import copy
import json
from datetime import date, datetime
from functools import lru_cache
from pathlib import Path
from typing import Any, Mapping, Sequence

CONTRACT_VERSION = "interim_earnings_cash_research_context/v1"
GATES_CONTRACT = "interim_earnings_cash_issuer_gates/v1"
GATES_PATH = Path(__file__).resolve().parents[2] / "config" / "interim_earnings_cash_issuer_gates_v1.json"

FAMILY = {"revenue": "income_statement", "net_income": "income_statement",
          "attributable_net_income": "income_statement", "investment_property_disposal_result": "income_statement",
          "operating_cash_flow": "cash_flow", "provision_charge_or_reversal_adjustment": "cash_flow",
          "cash_and_equivalents": "balance_sheet"}
PROFIT_METRICS = ("net_income", "attributable_net_income")
COMPARED_METRICS = ("revenue", "net_income", "attributable_net_income", "operating_cash_flow")
#: Explicitly reported non-operating earnings lines (recurrence is never assessed).
NON_OPERATING_LINES = ("investment_property_disposal_result",)
#: Non-cash reconciling lines inside operating cash flow.
NON_CASH_RECONCILING_LINES = ("provision_charge_or_reversal_adjustment",)
#: Values a row may carry when it is a comparative column of its own document.
COMPARATIVE_BASES = ("RECLASSIFIED_COMPARATIVE", "ISSUER_LIKE_FOR_LIKE_RESTATEMENT", "AS_PREVIOUSLY_REPORTED")
CURRENT_COLUMN = "CURRENT_COLUMN"

CONVERSION_METHOD = "operating_cash_flow_over_profit_after_tax_same_statement_set/v1"
COMPARISON_METHOD = "same_metric_line_scope_currency_assurance_explicit_calendar_yoy_with_issuer_cautions/v1"
CO_MOVEMENT_METHOD = "profit_and_operating_cash_direction_same_matched_periods/v1"
CONVERSION_CHANGE_METHOD = "conversion_ratio_matched_period_change_positive_profit_only/v1"
COMPONENT_METHOD = "explicit_component_over_profit_after_tax_same_statement_set/v1"


@lru_cache(maxsize=4)
def _load(path: str) -> dict[str, Any]:
    spec = json.loads(Path(path).read_bytes())
    if spec.get("contract_version") != GATES_CONTRACT or spec.get("closed_set") is not True \
            or spec.get("authority_effect") != "NONE" or not isinstance(spec.get("issuers"), dict):
        raise ValueError("INTERIM_EARNINGS_CASH_ISSUER_GATES_INVALID")
    for gate in spec["issuers"].values():
        for caution in gate.get("comparability_cautions") or []:
            if not caution.get("caution_id") or not caution.get("kind") or not caution.get("effect"):
                raise ValueError("INTERIM_EARNINGS_CASH_CAUTION_INCOMPLETE")
        if any("value" in row or "normalized_value" in row for row in gate.get("candidate_rows") or []):
            raise ValueError("INTERIM_EARNINGS_CASH_GATE_MUST_NOT_CARRY_AMOUNTS")
    return spec


def load_issuer_gates(path: Path | str = GATES_PATH) -> dict[str, Any]:
    return copy.deepcopy(_load(str(path)))


def _date(value: Any) -> date:
    return date.fromisoformat(str(value))


def _fact(row: Mapping[str, Any]) -> dict[str, Any]:
    keys = ("ticker", "canonical_metric", "line_code", "statement_family", "statement_scope", "reporting_period",
            "period_type", "period_start", "period_end", "currency", "unit_scale", "normalized_value",
            "audit_or_review_status", "document_sha256", "citation_id", "source_page", "source_identity",
            "knowledge_available_at", "temporal_status", "context_kind")
    fact = {key: copy.deepcopy(row.get(key)) for key in keys}
    fact["comparative_basis"] = row.get("comparative_basis") or CURRENT_COLUMN
    return fact


def _set_key(fact: Mapping[str, Any]) -> tuple:
    return (fact["document_sha256"], fact["period_start"], fact["period_end"], fact["statement_scope"],
            fact["currency"], fact["comparative_basis"])


def _prior_year(prior: Mapping[str, Any], current: Mapping[str, Any]) -> bool:
    old_start, old_end = _date(prior["period_start"]), _date(prior["period_end"])
    new_start, new_end = _date(current["period_start"]), _date(current["period_end"])
    return (new_start.year == old_start.year + 1 and new_end.year == old_end.year + 1
            and (new_start.month, new_start.day, new_end.month, new_end.day)
            == (old_start.month, old_start.day, old_end.month, old_end.day))


def _caution_refusals(prior: Mapping[str, Any], current: Mapping[str, Any],
                      cautions: Sequence[Mapping[str, Any]]) -> tuple[list[str], list[str]]:
    """Return (refusal reasons, applied basis labels) from source-declared issuer cautions."""
    refusals, labels = [], []
    family = FAMILY[current["canonical_metric"]]
    in_document = (prior["document_sha256"] == current["document_sha256"]
                   and prior["comparative_basis"] != CURRENT_COLUMN)
    for caution in cautions:
        if family not in (caution.get("statement_families") or []):
            continue
        kind, effective = caution["kind"], caution.get("effective_from")
        crosses = bool(effective) and _date(prior["period_end"]) < _date(effective) <= _date(current["period_start"])
        if kind == "COMPARATIVES_RECLASSIFIED" and caution.get("document_sha256") == current["document_sha256"]:
            if in_document and prior["comparative_basis"] == "RECLASSIFIED_COMPARATIVE":
                labels.append("RECLASSIFIED_COMPARATIVE_PRESERVED:" + caution["caution_id"])
            else:
                refusals.append("PRIOR_VALUE_NOT_ON_RECLASSIFIED_COMPARATIVE_BASIS:" + caution["caution_id"])
        elif kind == "CONSOLIDATION_SCOPE_CHANGE" and crosses:
            basis = caution.get("like_for_like_basis") or {}
            if (in_document and prior["comparative_basis"] == "ISSUER_LIKE_FOR_LIKE_RESTATEMENT"
                    and family in (basis.get("statement_families") or [])
                    and str(current.get("line_code")) in (basis.get("line_codes") or [])):
                labels.append("ISSUER_LIKE_FOR_LIKE_BASIS:" + caution["caution_id"])
            else:
                refusals.append("COMPARATIVE_NOT_RESTATED_FOR_SCOPE_CHANGE:" + caution["caution_id"])
        elif kind == "TEMPLATE_LINE_CODE_CHANGE" and crosses \
                and str(current.get("line_code")) in (caution.get("line_codes") or []):
            refusals.append("TEMPLATE_LINE_CODE_IDENTITY_CHANGED:" + caution["caution_id"])
    return refusals, labels


def _comparisons(facts: Sequence[Mapping[str, Any]], cautions: Sequence[Mapping[str, Any]]):
    from stocklookup_core.financial.financial_analysis_engine_v2 import sign_transition
    measured, refused = [], []
    groups: dict[tuple, list[Mapping[str, Any]]] = {}
    for fact in facts:
        if fact["canonical_metric"] in COMPARED_METRICS:
            groups.setdefault((fact["canonical_metric"], fact["statement_scope"], fact["currency"],
                               fact["audit_or_review_status"]), []).append(fact)
    for (metric, *_), rows in sorted(groups.items(), key=lambda item: str(item[0])):
        for current in rows:
            if current["comparative_basis"] != CURRENT_COLUMN:
                continue
            for prior in rows:
                if prior is current or not _prior_year(prior, current):
                    continue
                reasons = []
                if str(prior.get("line_code")) != str(current.get("line_code")):
                    reasons.append("LINE_CODE_IDENTITY_MISMATCH")
                if prior["comparative_basis"] != CURRENT_COLUMN and prior["document_sha256"] != current["document_sha256"]:
                    reasons.append("COMPARATIVE_COLUMN_OF_ANOTHER_DOCUMENT")
                caution_reasons, labels = _caution_refusals(prior, current, cautions)
                reasons += caution_reasons
                pair = {"metric": metric, "prior_period": prior["reporting_period"],
                        "current_period": current["reporting_period"],
                        "prior_bounds": [prior["period_start"], prior["period_end"]],
                        "current_bounds": [current["period_start"], current["period_end"]],
                        "prior_citation_id": prior["citation_id"], "current_citation_id": current["citation_id"],
                        "prior_document_sha256": prior["document_sha256"],
                        "current_document_sha256": current["document_sha256"],
                        "prior_basis": prior["comparative_basis"]}
                if reasons:
                    refused.append(pair | {"reason_codes": sorted(set(reasons))})
                    continue
                old, new = prior["normalized_value"], current["normalized_value"]
                delta = new - old
                measured.append(pair | {"statement_scope": current["statement_scope"], "currency": current["currency"],
                    "assurance": current["audit_or_review_status"], "change": delta,
                    "direction": "INCREASED" if delta > 0 else "DECREASED" if delta < 0 else "UNCHANGED",
                    "growth_ratio": delta / old if old > 0 else None,
                    "semantic_transition": sign_transition(old, new, earnings=metric != "revenue"),
                    "basis_labels": sorted(labels), "method": COMPARISON_METHOD,
                    "limitations": ["REPORTED_CHANGE_NOT_BUSINESS_QUALITY", "RECURRENCE_UNKNOWN", "NON_VOTING"]})
    return measured, refused


def _relationship(profit: float, cash: float) -> str:
    if profit <= 0:
        return "PROFIT_NON_POSITIVE_RATIO_NOT_MEANINGFUL"
    if cash < 0:
        return "POSITIVE_PROFIT_NEGATIVE_OPERATING_CASH"
    return "OPERATING_CASH_AT_OR_ABOVE_PROFIT" if cash >= profit else "OPERATING_CASH_BELOW_PROFIT"


def _period_text(bounds: Sequence[str]) -> str:
    return f"{bounds[0]}..{bounds[1]}"


def interim_earnings_cash_research_context(record: Mapping[str, Any] | None, *, cutoff: str | None,
                                           ticker: str | None = None,
                                           gates: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Describe reported earnings and operating cash conversion from admitted official facts only."""
    from stocklookup_core.financial.fundamental_signal_consumption_contract import official_research_row_reasons
    record = record or {}
    ticker = ticker or record.get("ticker")
    entity = record.get("entity_class")
    spec = gates if gates is not None else load_issuer_gates()
    gate = copy.deepcopy((spec.get("issuers") or {}).get(str(ticker))) if ticker else None
    cautions = (gate or {}).get("comparability_cautions") or []
    base = {"contract_version": CONTRACT_VERSION, "ticker": ticker, "cutoff": cutoff, "entity_class": entity,
            "issuer_gate": gate, "vote_effect": "NONE", "strict_valuation_effect": "NONE", "is_actionable": False,
            "d1_gate": "UNREVIEWED_EXISTING_CONSUMER_USE_REFUSED",
            "availability_basis": "KNOWLEDGE_AT_RESEARCH_CUTOFF_NOT_PUBLICATION_OR_HISTORICAL_PIT_PROOF"}
    if entity != "corporate":
        return base | {"applicability": "NOT_APPLICABLE_FINANCIAL_OR_UNRESOLVED_ENTITY", "economics_status": "NOT_APPLICABLE",
                       "facts": [], "rejected": [], "statement_sets": [],
                       "cash_conversion": {"measurements": [], "blockers": []},
                       "matched_comparisons": [], "refused_comparisons": [], "profit_cash_co_movement": [],
                       "conversion_changes": [], "earnings_quality": None, "balance_context": [],
                       "comparability": {"statement_sets": [], "issuer_cautions": copy.deepcopy(cautions)},
                       "explanation": [{"code": "INDUSTRIAL_CASH_CONVERSION_NOT_APPLICABLE",
                       "text": "Industrial earnings-to-cash interpretation is not applied to this entity class."}]}
    try:
        boundary = datetime.fromisoformat(str(cutoff).replace("Z", "+00:00"))
        boundary = boundary if boundary.tzinfo is not None else None
    except ValueError:
        boundary = None
    facts, rejected = [], []
    for row in record.get("official_field_context") or []:
        metric = row.get("canonical_metric")
        if metric not in FAMILY:
            continue
        reasons = official_research_row_reasons(row, boundary=boundary, entity=entity, ticker=ticker,
                                                statement_family=FAMILY[metric])
        if row.get("comparative_basis") not in (None, *COMPARATIVE_BASES):
            reasons.append("UNKNOWN_COMPARATIVE_BASIS")
        if reasons:
            rejected.append({"citation_id": row.get("citation_id"), "metric": metric, "reason_codes": sorted(set(reasons))})
            continue
        facts.append(_fact(row))
    # One value per metric per statement set; a conflict drops the metric there, never picks a winner.
    sets: dict[tuple, dict[str, Any]] = {}
    for fact in facts:
        sets.setdefault(_set_key(fact), {}).setdefault(fact["canonical_metric"], []).append(fact)
    statement_sets, conflicted = [], set()
    for key, metrics in sorted(sets.items(), key=lambda item: (item[0][2], item[0][5], item[0][0])):
        values = {}
        for metric, rows in metrics.items():
            if len({r["normalized_value"] for r in rows}) == 1:
                values[metric] = rows[0]
            else:
                conflicted.add((key, metric))
                rejected.append({"metric": metric, "citation_ids": sorted(r["citation_id"] for r in rows),
                                 "reason_codes": ["CONFLICTING_OFFICIAL_VALUES_IN_STATEMENT_SET"]})
        statement_sets.append({"document_sha256": key[0], "bounds": [key[1], key[2]], "statement_scope": key[3],
            "currency": key[4], "comparative_basis": key[5], "metrics": values})
    usable = [fact for fact in facts if (_set_key(fact), fact["canonical_metric"]) not in conflicted]

    conversions, conversion_blockers, components, balance = [], [], [], []
    ocf_periods = sorted({tuple(s["bounds"]) for s in statement_sets if "operating_cash_flow" in s["metrics"]})
    for current in statement_sets:
        metrics, bounds = current["metrics"], current["bounds"]
        label = {"document_sha256": current["document_sha256"], "bounds": bounds,
                 "statement_scope": current["statement_scope"], "comparative_basis": current["comparative_basis"]}
        profits = [m for m in PROFIT_METRICS if m in metrics]
        cash = metrics.get("operating_cash_flow")
        for metric in profits:
            if cash is None:
                continue
            profit, ocf = metrics[metric]["normalized_value"], cash["normalized_value"]
            conversions.append(label | {"profit_metric": metric, "profit": profit, "operating_cash_flow": ocf,
                "operating_cash_minus_profit": ocf - profit,
                "conversion_ratio": ocf / profit if profit > 0 else None,
                "relationship": _relationship(profit, ocf), "assurance": cash["audit_or_review_status"],
                "profit_citation_id": metrics[metric]["citation_id"], "cash_citation_id": cash["citation_id"],
                "method": CONVERSION_METHOD,
                "limitations": ["SINGLE_PERIOD_IS_NOT_A_TREND", "TIMING_AND_WORKING_CAPITAL_ATTRIBUTION_UNKNOWN",
                                "NOT_FREE_CASH_FLOW", "NON_VOTING"]
                    + (["PARENT_PROFIT_EXCLUDES_NON_CONTROLLING_INTERESTS_OPERATING_CASH_IS_GROUP_WIDE"]
                       if metric == "attributable_net_income" else [])})
        if profits and cash is None and current["comparative_basis"] == CURRENT_COLUMN:
            conversion_blockers.append(label | {"reason_codes": ["NO_SAME_STATEMENT_SET_OPERATING_CASH_FLOW"]
                + (["OPERATING_CASH_FLOW_ONLY_FOR_OTHER_PERIODS"] if ocf_periods else []),
                "operating_cash_flow_periods": [list(p) for p in ocf_periods]})
        if cash is not None and not profits and current["comparative_basis"] == CURRENT_COLUMN:
            conversion_blockers.append(label | {"reason_codes": ["NO_SAME_STATEMENT_SET_QUALIFIED_PROFIT"]})
        net = metrics.get("net_income")
        for metric in NON_OPERATING_LINES + NON_CASH_RECONCILING_LINES:
            if metric in metrics:
                value = metrics[metric]["normalized_value"]
                share = value / net["normalized_value"] if metric in NON_OPERATING_LINES and net \
                    and net["normalized_value"] > 0 else None
                components.append(label | {"metric": metric, "value": value, "citation_id": metrics[metric]["citation_id"],
                    "role": "EXPLICIT_NON_OPERATING_EARNINGS_LINE" if metric in NON_OPERATING_LINES
                            else "NON_CASH_RECONCILING_LINE_IN_OPERATING_CASH_FLOW",
                    "share_of_profit_after_tax": share, "method": COMPONENT_METHOD if share is not None else None,
                    "recurrence_assessment": "UNKNOWN", "normalization_status": "NOT_CALCULATED"})
        if "cash_and_equivalents" in metrics:
            fact = metrics["cash_and_equivalents"]
            balance.append(label | {"metric": "cash_and_equivalents", "value": fact["normalized_value"],
                "citation_id": fact["citation_id"], "as_of": fact["period_end"],
                "limitations": ["CASH_BALANCE_IS_NOT_FREE_CASH_FLOW", "NET_CASH_NOT_CALCULATED_NO_QUALIFIED_DEFINITION",
                                "BALANCE_MAY_REFLECT_TAX_OR_DIVIDEND_PAYMENT_TIMING"]})

    measured, refused = _comparisons(usable, cautions)
    co_movement, conversion_changes = [], []
    def pair_key(p):
        return (tuple(p["prior_bounds"]), p["prior_document_sha256"], p["prior_basis"],
                tuple(p["current_bounds"]), p["current_document_sha256"])
    cash_pairs = {pair_key(p): p for p in measured if p["metric"] == "operating_cash_flow"}
    for pair in measured:
        if pair["metric"] not in PROFIT_METRICS:
            continue
        cash = cash_pairs.get(pair_key(pair))
        if cash is None:
            continue
        same = pair["direction"] == cash["direction"]
        co_movement.append({"profit_metric": pair["metric"], "prior_bounds": pair["prior_bounds"],
            "current_bounds": pair["current_bounds"], "profit_direction": pair["direction"],
            "operating_cash_direction": cash["direction"],
            "relationship": "SAME_DIRECTION" if same else "OPPOSITE_DIRECTION",
            "label": f"PROFIT_{pair['direction']}_OPERATING_CASH_{cash['direction']}", "method": CO_MOVEMENT_METHOD})
        ratios = {}
        for conversion in conversions:
            if conversion["profit_metric"] == pair["metric"] and conversion["conversion_ratio"] is not None:
                ratios.setdefault((tuple(conversion["bounds"]), conversion["document_sha256"],
                                   conversion["comparative_basis"]), set()).add(conversion["conversion_ratio"])
        old = ratios.get((tuple(pair["prior_bounds"]), pair["prior_document_sha256"], pair["prior_basis"]))
        new = ratios.get((tuple(pair["current_bounds"]), pair["current_document_sha256"], CURRENT_COLUMN))
        if old and new and len(old) == len(new) == 1:
            old, new = old.pop(), new.pop()
            conversion_changes.append({"profit_metric": pair["metric"], "prior_bounds": pair["prior_bounds"],
                "current_bounds": pair["current_bounds"], "prior_ratio": old, "current_ratio": new,
                "direction": "HIGHER" if new > old else "LOWER" if new < old else "UNCHANGED",
                "method": CONVERSION_CHANGE_METHOD, "limitations": ["TWO_PERIODS_ARE_NOT_A_TREND", "NON_VOTING"]})

    profit_up = [p for p in measured if p["metric"] in PROFIT_METRICS and p["direction"] == "INCREASED"]
    unresolved = ["QUALIFIED_SHARE_BASIS_UNAVAILABLE", "OPERATING_PROFIT_LINE_NOT_ADMITTED",
                  "WORKING_CAPITAL_COMPONENTS_NOT_QUALIFIED"]
    if not conversions:
        unresolved.append("OPERATING_CASH_CONVERSION_UNKNOWN")
    if not any(c["role"] == "EXPLICIT_NON_OPERATING_EARNINGS_LINE" for c in components):
        unresolved.append("EXCEPTIONAL_ITEMS_NOT_EXPLICITLY_QUALIFIED")
    quality = {"divergences": sorted({c["relationship"] for c in conversions
                                      if c["relationship"] in {"POSITIVE_PROFIT_NEGATIVE_OPERATING_CASH",
                                                               "OPERATING_CASH_BELOW_PROFIT"}}),
               "explicit_components": components, "unresolved_components": unresolved,
               "working_capital_pressure": "UNKNOWN", "operating_earnings": "UNKNOWN",
               "reported_profit_increase_interpretation": (
                   "REPORTED_PROFIT_INCREASE_ECONOMICS_UNRESOLVED" if profit_up else "NO_MEASURED_PROFIT_INCREASE")}

    explanation = []
    for c in conversions:
        if c["comparative_basis"] != CURRENT_COLUMN:
            continue
        ratio = "" if c["conversion_ratio"] is None else f" (operating cash/profit {c['conversion_ratio']:.2f})"
        text = {"POSITIVE_PROFIT_NEGATIVE_OPERATING_CASH": "reported a profit but negative operating cash flow",
                "OPERATING_CASH_BELOW_PROFIT": "converted less of its profit into operating cash",
                "OPERATING_CASH_AT_OR_ABOVE_PROFIT": "generated operating cash at or above its profit",
                "PROFIT_NON_POSITIVE_RATIO_NOT_MEANINGFUL": "had non-positive profit, so no conversion ratio is meaningful"}
        explanation.append({"code": c["relationship"], "text": f"{_period_text(c['bounds'])} {c['assurance']} "
            f"{c['statement_scope']} {c['profit_metric']}: the company {text[c['relationship']]}{ratio}; "
            "one period is not a trend."})
    for m in co_movement:
        if m["relationship"] == "OPPOSITE_DIRECTION":
            explanation.append({"code": m["label"], "text": f"Matched {_period_text(m['prior_bounds'])} -> "
                f"{_period_text(m['current_bounds'])}: {m['profit_metric']} {m['profit_direction'].lower()} while "
                f"operating cash flow {m['operating_cash_direction'].lower()}."})
    for r in refused:
        explanation.append({"code": "COMPARISON_REFUSED", "text": f"{r['metric']} {r['prior_period']} -> "
            f"{r['current_period']} not compared: " + ", ".join(r["reason_codes"]) + "."})
    for b in conversion_blockers:
        explanation.append({"code": b["reason_codes"][-1], "text": f"{_period_text(b['bounds'])}: no same-period "
            "operating cash flow and profit pair, so cash conversion is UNKNOWN."})
    if profit_up:
        explanation.append({"code": "REPORTED_PROFIT_INCREASE_ECONOMICS_UNRESOLVED", "text":
            "A reported profit increase is not by itself better economics: " + ", ".join(unresolved) + "."})
    for caution in cautions:
        explanation.append({"code": caution["kind"], "text": f"Source-declared caution {caution['caution_id']}: "
            f"{caution['effect']}."})
    if gate and not any(f["statement_family"] != "balance_sheet" and f["temporal_status"] == "CURRENT_OFFICIAL_FACT"
                        for f in usable):
        explanation.append({"code": "CURRENT_INCOME_AND_CASH_FACTS_NOT_QUALIFIED", "text":
            f"Reviewed statement {gate['document']['document_sha256'][:12]} is identified, but its income and "
            "cash-flow rows are not qualified: " + ", ".join(gate.get("qualification_blockers") or []) + "."})

    status = ("MEASURED" if conversions or measured else
              "PARTIAL_FACTS_NO_MEASUREMENT" if any(f["statement_family"] != "balance_sheet" for f in usable)
              else "UNKNOWN")
    return base | {"applicability": "CORPORATE_INDUSTRIAL_CASH_CONVERSION", "economics_status": status,
        "facts": usable, "rejected": rejected, "statement_sets": statement_sets,
        "cash_conversion": {"measurements": conversions, "blockers": conversion_blockers},
        "matched_comparisons": measured, "refused_comparisons": refused,
        "profit_cash_co_movement": co_movement, "conversion_changes": conversion_changes,
        "earnings_quality": quality, "balance_context": balance,
        "comparability": {"statement_sets": [{k: s[k] for k in ("document_sha256", "bounds", "statement_scope",
                              "currency", "comparative_basis")} | {
                              "duration_days": (_date(s["bounds"][1]) - _date(s["bounds"][0])).days + 1,
                              "assurance": sorted({f["audit_or_review_status"] for f in s["metrics"].values()}),
                              "knowledge_available_at": sorted({f["knowledge_available_at"] for f in s["metrics"].values()})}
                              for s in statement_sets],
                          "issuer_cautions": copy.deepcopy(cautions)},
        "explanation": explanation}


def financial_quality_decision_bridge(record: Mapping[str, Any] | None, *, ticker: str,
                                      knowledge_cutoff: str) -> dict[str, Any]:
    """Offline explanation over an existing admitted projection, never a fact intake.

    This opt-in consumer does not change the released context above. A source
    fingerprint verifies integrity, not authenticity or factual truth. Callers
    must supply the existing Producer projection, not self-labelled Hub rows.
    """
    from long_term_company_economics_evidence import _time, _temporal_reasons

    boundary = _time(knowledge_cutoff)
    record = record or {}
    if record.get("ticker") not in (None, ticker):
        raise ValueError("FINANCIAL_QUALITY_SUBJECT_MISMATCH")
    rows, receipt_refusals = [], []
    for row in record.get("official_field_context") or []:
        reasons = _temporal_reasons(row, boundary)
        digest = row.get("document_sha256")
        if (type(row.get("source_page")) is not int or row["source_page"] < 1
                or not row.get("line_code") or not isinstance(digest, str) or len(digest) != 64
                or any(c not in "0123456789abcdef" for c in digest)):
            reasons.append("EXACT_DOCUMENT_PAGE_LINE_REFERENCE_REQUIRED")
        if reasons:
            receipt_refusals.append({"citation_id": row.get("citation_id"), "reason_codes": reasons})
        else:
            rows.append(copy.deepcopy(row))
    rows = sorted({json.dumps(r, sort_keys=True, ensure_ascii=False): r for r in rows}.values(),
                  key=lambda r: json.dumps(r, sort_keys=True, ensure_ascii=False))
    citation_keys: dict[str, set[str]] = {}
    for row in rows:
        binding = {k: row.get(k) for k in ("canonical_metric", "document_sha256", "normalized_value",
                   "period_start", "period_end", "statement_scope", "currency", "audit_or_review_status")}
        citation_keys.setdefault(row.get("citation_id"), set()).add(json.dumps(binding, sort_keys=True))
    collisions = {key for key, bindings in citation_keys.items() if len(bindings) > 1}
    receipt_refusals.extend({"citation_id": key, "reason_codes": ["CITATION_IDENTITY_COLLISION"]} for key in collisions)
    rows = [row for row in rows if row.get("citation_id") not in collisions]
    context = interim_earnings_cash_research_context(
        dict(record) | {"official_field_context": rows}, cutoff=knowledge_cutoff, ticker=ticker)
    from stocklookup_core.financial.fundamental_signal_consumption_contract import official_research_row_reasons
    extra_facts, extra_refusals = [], []
    for row in rows:
        if row.get("canonical_metric") not in FAMILY and row.get("canonical_metric") not in {
                "total_assets", "shareholders_equity", "short_term_interest_bearing_debt", "long_term_interest_bearing_debt"}:
            extra_refusals.append({"citation_id": row.get("citation_id"), "metric": row.get("canonical_metric"),
                                   "reason_codes": ["METRIC_NOT_ADMITTED_TO_QUALITY_BRIDGE"]})
            continue
        if row.get("canonical_metric") not in {"total_assets", "shareholders_equity", "short_term_interest_bearing_debt", "long_term_interest_bearing_debt"}:
            continue
        reasons = official_research_row_reasons(row, boundary=boundary, entity=record.get("entity_class"),
                                               ticker=ticker, statement_family="balance_sheet")
        peers = [r for r in rows if all(r.get(k) == row.get(k) for k in (
            "canonical_metric", "document_sha256", "period_start", "period_end", "statement_scope", "currency"))]
        if len({r.get("normalized_value") for r in peers}) > 1:
            reasons.append("CONFLICTING_OFFICIAL_VALUES_IN_STATEMENT_SET")
        if reasons:
            extra_refusals.append({"citation_id": row.get("citation_id"), "reason_codes": reasons})
        else:
            extra_facts.append(_fact(row))
    facts = []
    for fact in context["facts"] + extra_facts:
        source = next(r for r in rows if r.get("citation_id") == fact["citation_id"]
                      and r.get("normalized_value") == fact["normalized_value"])
        facts.append(fact | {key: copy.deepcopy(source.get(key)) for key in (
            "observed_at", "publication_date", "valuation_use", "annualization", "ttm_derivation",
            "foreign_currency_conversion", "component_semantic_type", "component_direction")})
    facts.sort(key=lambda f: (f["period_end"], f["canonical_metric"], f["citation_id"]))
    by_id = {f["citation_id"]: f for f in facts}
    profits = [f for f in facts if f["canonical_metric"] in PROFIT_METRICS]
    components = [f for f in facts if f["canonical_metric"] in NON_OPERATING_LINES + NON_CASH_RECONCILING_LINES]
    cash_pairs, pairing_refusals = [], []
    for measured in context["cash_conversion"]["measurements"]:
        # Group-wide cash does not measure conversion of parent-only profit.
        if measured["profit_metric"] != "net_income":
            continue
        profit, cash = by_id[measured["profit_citation_id"]], by_id[measured["cash_citation_id"]]
        if any(profit[key] != cash[key] for key in ("audit_or_review_status", "period_type")):
            pairing_refusals.append({"citation_ids": [profit["citation_id"], cash["citation_id"]],
                                     "reason_codes": ["CASH_PROFIT_ASSURANCE_OR_PERIOD_TYPE_MISMATCH"]})
            continue
        import math
        if any(v is not None and not math.isfinite(v) for v in (
                measured["conversion_ratio"], measured["operating_cash_minus_profit"])):
            pairing_refusals.append({"citation_ids": [profit["citation_id"], cash["citation_id"]],
                                     "reason_codes": ["CASH_PROFIT_ARITHMETIC_NOT_FINITE"]})
            continue
        cash_pairs.append(copy.deepcopy(measured) | {"currency": cash["currency"]})

    confirming, counter, unknowns = [], [], []
    def statement(code, text, refs=()):
        return {"code": code, "text": text, "citation_ids": sorted(set(refs))}

    for f in profits:
        confirming.append(statement("REPORTED_PROFIT_OBSERVED",
            f"{f['reporting_period']} {f['statement_scope']} {f['audit_or_review_status']} "
            f"{f['canonical_metric']}: {f['normalized_value']} {f['currency']}. "
            "This is reported accounting profit; sustainable or normalized earnings are not established.", [f["citation_id"]]))
    for f in components:
        if not f["normalized_value"]:
            continue
        disposal = f["canonical_metric"] in NON_OPERATING_LINES
        counter.append(statement("REPORTED_DISPOSAL_COMPONENT" if disposal else "REPORTED_PROVISION_COMPONENT",
            f"{f['reporting_period']} {f['canonical_metric']}: {f['normalized_value']} {f['currency']}. "
            + ("A disposal line may distort a reported earnings multiple; recurrence and tax treatment are unproven."
               if disposal else "A provision reconciliation is not cash received, a one-off classification or an earnings add-back."),
            [f["citation_id"]]))
    for m in cash_pairs:
        refs = [m["profit_citation_id"], m["cash_citation_id"]]
        ratio = "not meaningful (profit is non-positive)" if m["conversion_ratio"] is None else f"{m['conversion_ratio']:.4f}x"
        item = statement(m["relationship"],
            f"{m['bounds'][0]}..{m['bounds'][1]} {m['statement_scope']}: operating cash "
            f"{m['operating_cash_flow']} versus total profit {m['profit']} {m['currency']}; "
            f"CFO/PAT {ratio}. One period does not establish durable cash conversion or its cause.", refs)
        (confirming if m["relationship"] == "OPERATING_CASH_AT_OR_ABOVE_PROFIT" else counter).append(item)

    industrial = context["applicability"] == "CORPORATE_INDUSTRIAL_CASH_CONVERSION"
    if not profits:
        unknowns.append(statement("REPORTED_PROFIT_NOT_QUALIFIED", "No admitted reported profit supports an earnings conclusion."))
    if not cash_pairs:
        unknowns.append(statement("CASH_CONVERSION_NOT_ESTABLISHED",
            "No comparable same-document total-profit/operating-cash pair. Historical annual cash cannot explain current interim profit."
            if industrial else "Industrial CFO/PAT is not applied to financial or unresolved entities; specialist accounting evidence is required."))
    unknowns.extend([
        statement("RECURRENCE_NOT_ESTABLISHED", "A reported component is not normalized earnings; absence of a component is not proof of clean earnings."),
        statement("WORKING_CAPITAL_CAUSALITY_NOT_ESTABLISHED", "Receivable/inventory/payable movements and collection or contractual due-date evidence are not admitted here. A cash gap does not prove its cause or that all receivables are overdue."),
        statement("CASH_OBLIGATIONS_NOT_ESTABLISHED", "Cash balances do not establish available cash after debt maturities, tax, dividends or capital commitments; no free cash flow or net-debt conclusion."),
        statement("OCI_NOT_ADMITTED", "No admitted OCI/tax/attribution bridge. For securities firms, PAT alone cannot establish comprehensive income; do not add pre-tax OCI to after-tax PAT."),
        statement("VALUATION_DENOMINATOR_NOT_QUALIFIED", "Reported profit context does not supply qualified EPS, a compatible share basis or a recurring earnings denominator. A low reported P/E alone does not establish attractive value."),
        statement("FISCAL_COMPARABILITY_LIMIT", "Explicit covered dates, source scope, currency and assurance apply to each observation. Calendar labels alone cannot establish fiscal or peer comparability."),
    ])
    for refusal in context["refused_comparisons"]:
        unknowns.append(statement("COMPARISON_REFUSED", ", ".join(refusal["reason_codes"]),
                                  [refusal["prior_citation_id"], refusal["current_citation_id"]]))
    for blocker in context["cash_conversion"]["blockers"]:
        unknowns.append(statement("CASH_PAIRING_REFUSED",
            f"{blocker['bounds'][0]}..{blocker['bounds'][1]}: " + ", ".join(blocker["reason_codes"]) + "."))
    if context.get("issuer_gate"):
        for reason in context["issuer_gate"].get("qualification_blockers") or []:
            unknowns.append(statement("SOURCE_QUALIFICATION_GAP", reason))
    # Preserve useful provider/Financial V2 context, without treating it as an
    # official amount, a specialist accounting qualification, or a quality vote.
    retained = {key: copy.deepcopy(record[key]) for key in (
        "entity_class", "fundamental_trajectory_context", "current_financial_momentum_context",
        "baseline_metric_temporal_context", "metrics") if key in record}
    return {"contract_version": "financial_quality_decision_bridge/v1", "ticker": ticker,
        "knowledge_cutoff": knowledge_cutoff, "applicability": context["applicability"],
        "assessment_scope": "OBSERVED_FIELDS_AND_UNSUPPORTED_CONCLUSIONS_NO_COMPANY_VERDICT",
        "facts": facts, "reported_components": [f | {"recurrence_assessment": "UNKNOWN",
            "normalization_status": "NOT_CALCULATED"} for f in components], "cash_conversion": cash_pairs,
        "confirming_evidence": confirming, "counterevidence": counter, "unknowns": unknowns,
        "rejected": [r for _, r in sorted({json.dumps(r, sort_keys=True): r for r in
                     receipt_refusals + context["rejected"] + pairing_refusals + extra_refusals}.items())],
        "cash_pairing_blockers": context["cash_conversion"]["blockers"],
        "issuer_comparability_cautions": context["comparability"]["issuer_cautions"],
        "retained_research_context": retained,
        "retained_context_use": "UPSTREAM_CONTEXT_ONLY_NOT_OFFICIAL_FINANCIAL_FACT_OR_QUALITY_VOTE",
        "investment_relevance": "Assess earnings repeatability and cash support before interpreting a valuation multiple; preserve the observed facts while withholding unsupported conclusions.",
        "thesis_tests": [
            {"claim": "Reported profit reflects sustainable earnings", "status": "UNSUPPORTED",
             "confirming_evidence_needed": "Source-qualified recurring/non-recurring reconciliation on the same tax and attribution basis across comparable periods.",
             "invalidation_condition": "A qualified same-period reconciliation demonstrates that reported earnings include non-recurring drivers; do not infer a normalized amount."},
            {"claim": "Accounting profit is supported by operating cash", "status": "BOUNDED_MEASUREMENT_ONLY" if cash_pairs else "UNSUPPORTED",
             "confirming_evidence_needed": "Comparable total PAT and CFO plus working-capital, collection and cash-obligation notes.",
             "invalidation_condition": "Same-basis source evidence shows negative CFO despite positive PAT, or invalidates the period/scope/currency/assurance pairing."},
            {"claim": "A low reported multiple represents attractive value", "status": "UNSUPPORTED",
             "confirming_evidence_needed": "Existing valuation owner qualification of price, shares and exact denominator, plus evidence about its recurrence and cash support.",
             "invalidation_condition": "Denominator contains unresolved unusual items or an incompatible period, scope, currency or share basis."}],
        "availability_basis": context["availability_basis"], "non_voting": True, "is_actionable": False,
        "authority_effect": "NONE", "strict_valuation_effect": "NONE", "production": "OFFLINE_OPT_IN_ONLY"}


def render_financial_quality(bridge: Mapping[str, Any]) -> str:
    """Investor-readable facts, counterevidence and exact unsupported conclusions."""
    lines = [f"## {bridge['ticker']} — financial quality research",
             f"Knowledge cutoff: {bridge['knowledge_cutoff']}; offline, non-voting."]
    if "source_session" in bridge:
        lines.append(f"Retained source session: {bridge['source_session']}; source cutoff: {bridge['source_cutoff']}.")
    lines.append("Source-bound projected observations; content integrity alone is not factual verification or historical PIT authority.")
    for title, key in (("Observed support", "confirming_evidence"), ("Counterevidence / accounting cautions", "counterevidence"),
                       ("Unsupported conclusions / evidence needed", "unknowns")):
        lines.extend(["", title])
        for item in bridge[key]:
            lines.append(f"- {item['text']}" + (" [" + ", ".join(item["citation_ids"]) + "]" if item["citation_ids"] else ""))
    lines.extend(["", "Source basis (exact fields, not a normalized earnings estimate)"])
    for f in bridge["facts"]:
        lines.append(f"- {f['citation_id']}: {f['canonical_metric']} {f['normalized_value']} {f['currency']}; "
            f"{f['period_start']}..{f['period_end']}, {f['statement_scope']}, "
            f"{f['currency']} normalized unit {f['unit_scale']}, {f['audit_or_review_status']}; "
            f"document {f['document_sha256']}, page {f['source_page']}; known {f['knowledge_available_at']}, "
            f"retrieved {f['observed_at']}, publication {f['publication_date'] or 'UNKNOWN'}.")
    lines.extend(["", "Thesis checks / invalidation"])
    for test in bridge["thesis_tests"]:
        lines.append(f"- {test['claim']}: {test['status']}. Need: {test['confirming_evidence_needed']} "
                     f"Invalidation: {test['invalidation_condition']}")
    return "\n".join(lines)
