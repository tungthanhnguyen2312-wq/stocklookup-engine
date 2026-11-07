"""Market Close Intelligence: one deterministic post-close market brief composed from
artifacts the Daily already builds.

This module computes no new market measurement and owns no threshold. It binds the
existing exact-session breadth (``market_wide_current_descriptive_research``), the
provider-taxonomy sector leadership context, the macro/market regime context and the
optional benchmark / official-liquidity / flow inputs into one view that states, for
every component, its value, denominator, source scope, authority and - when absent -
the exact reason. Interpretation is limited to (a) direct count comparisons that need
no threshold and (b) explicit "cannot answer" statements naming the missing evidence.

Hard rules (contract ``market_close_intelligence/v1``):
- The benchmark index is never derived from constituent prices; without a bound
  index level it is ``UNAVAILABLE``.
- Observed-cohort breadth is never presented as the whole market; every ratio carries
  its denominator and the wider denominators are listed separately.
- Trading value is never price x volume; without an exchange-basis matched/negotiated/
  total value the liquidity component is ``UNAVAILABLE``.
- Provider sector taxonomy is never compared to a broker's sector count.
- No forecast, probability, score, recommendation, sizing or execution.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

CONTRACT_VERSION = "market_close_intelligence/v1"

_MACRO_AXES = ("INFLATION_PRESSURE", "FX_PRESSURE", "USD_PRESSURE", "DOMESTIC_RATES",
               "DOMESTIC_LIQUIDITY", "CREDIT_CONTEXT", "GLOBAL_RATES", "COMMODITY_CONTEXT")


def _hash(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def _ratio(n: Any, d: Any) -> float | None:
    return n / d if isinstance(n, (int, float)) and isinstance(d, (int, float)) and d else None


def _unavailable(reason: str, **extra: Any) -> dict[str, Any]:
    return {"status": "UNAVAILABLE", "reason_codes": [reason], **extra}


def _benchmark(benchmark: Mapping[str, Any] | None, session: str) -> dict[str, Any]:
    if not isinstance(benchmark, Mapping):
        return _unavailable("NO_QUALIFIED_INDEX_LEVEL_BOUND_TO_DAILY",
                            index="VNINDEX", derivation_from_constituents="NOT_PERMITTED")
    required = ("index", "session", "close", "previous_close", "previous_session", "source_identity",
                "knowledge_available_at", "authority")
    if any(benchmark.get(k) in (None, "") for k in required) or benchmark.get("session") != session:
        return _unavailable("INDEX_LEVEL_INPUT_INCOMPLETE_OR_WRONG_SESSION", index=benchmark.get("index"),
                            derivation_from_constituents="NOT_PERMITTED")
    close, prev = benchmark["close"], benchmark["previous_close"]
    return {"status": "AVAILABLE", "index": benchmark["index"], "session": session,
            "close": close, "previous_close": prev, "previous_session": benchmark["previous_session"],
            "change_points": round(close - prev, 2), "change_percent": round((close / prev - 1) * 100, 2) if prev else None,
            "source_identity": benchmark["source_identity"], "authority": benchmark["authority"],
            "knowledge_available_at": benchmark["knowledge_available_at"],
            "scope": "CURRENT_RESEARCH_ONLY_NOT_HISTORICAL_PIT",
            "derivation_from_constituents": "NOT_PERMITTED"}


def _denominators(descriptive: Mapping[str, Any]) -> dict[str, Any]:
    breadth = descriptive.get("market_breadth") or {}
    coverage = ((descriptive.get("validation") or {}).get("coverage") or {})
    return {
        "input_candidates": {"count": coverage.get("input_candidates"),
                             "meaning": "Every security considered at universe resolution (all listed instrument kinds)."},
        "current_active_equity": {"count": breadth.get("current_active_equity_denominator"),
                                  "meaning": "Active equity universe for this session; the widest denominator a market ratio may cite."},
        "exact_session_observed": {"count": breadth.get("observed_session_cohort"),
                                   "meaning": "Equities with a same-session price observation."},
        "technical_coverage": {"count": breadth.get("same_session_technical_feature_available_count"),
                               "meaning": "Observed equities with same-session technical features; the denominator of every breadth ratio below."},
        "rule": "Breadth ratios are cohort statistics on technical_coverage; they are not whole-market statistics.",
    }


def _breadth(descriptive: Mapping[str, Any]) -> dict[str, Any]:
    b = descriptive.get("market_breadth") or {}
    adv, dec, unch = b.get("advancing"), b.get("declining"), b.get("unchanged")
    n = b.get("same_session_technical_feature_available_count")
    trend = b.get("trend") or {}
    mom = (b.get("momentum_descriptor") or {}).get("input_statistics") or {}
    if not all(isinstance(x, int) for x in (adv, dec, unch, n)) or not n:
        return _unavailable("EXACT_SESSION_BREADTH_ABSENT")
    above, below = trend.get("above_ma20"), trend.get("at_or_below_ma20")
    eligible = (above or 0) + (below or 0)
    descriptor = (b.get("breadth_descriptor") or {})
    return {
        "status": "AVAILABLE", "denominator": n, "scope": "EXACT_SESSION_TECHNICAL_COHORT_NOT_WHOLE_MARKET",
        "advancing": adv, "declining": dec, "unchanged": unch,
        "advance_ratio": _ratio(adv, n), "decline_ratio": _ratio(dec, n), "unchanged_ratio": _ratio(unch, n),
        "advancers_per_decliner": _ratio(adv, dec),
        "above_ma20": above, "at_or_below_ma20": below, "above_ma20_ratio": _ratio(above, eligible),
        "positive_momentum_20d": mom.get("positive_count"), "negative_momentum_20d": mom.get("negative_count"),
        "existing_descriptor": descriptor.get("descriptor"),
        "existing_descriptor_rule": {"rule_identity": descriptor.get("rule_identity"), "threshold": descriptor.get("threshold"),
                                     "meaning": ("MIXED means neither advancers nor decliners reached the threshold share "
                                                 "of the cohort; it does not mean the session was balanced.")},
    }


def _sectors(sector: Mapping[str, Any] | None) -> dict[str, Any]:
    records = (((sector or {}).get("groups") or {}).get("records") or {}) if isinstance(sector, Mapping) else {}
    if not records:
        return _unavailable("SECTOR_LEADERSHIP_CONTEXT_ABSENT")
    by_state: dict[str, list[dict[str, Any]]] = {}
    namespaces = set()
    for key in sorted(records):
        row = records[key]
        namespaces.add(row.get("classification_namespace"))
        state = row.get("leadership_state") or "UNKNOWN"
        by_state.setdefault(state, []).append({
            "group": row.get("group_identity"), "observed": row.get("exact_session_observed_count"),
            "advancing": row.get("advancing"), "declining": row.get("declining"),
            "advance_ratio": row.get("advance_ratio"), "decline_ratio": row.get("decline_ratio"),
            "median_momentum_20d": row.get("median_momentum_20d"),
            "breadth_state": (row.get("leadership_rule") or {}).get("breadth_state")})
    groups = [g for rows in by_state.values() for g in rows]
    more_dec = sum(1 for g in groups if isinstance(g["declining"], int) and isinstance(g["advancing"], int)
                   and g["declining"] > g["advancing"])
    more_adv = sum(1 for g in groups if isinstance(g["declining"], int) and isinstance(g["advancing"], int)
                   and g["advancing"] > g["declining"])
    return {
        "status": "AVAILABLE", "taxonomy": sorted(n for n in namespaces if n),
        "taxonomy_authority": "PROVIDER_DESCRIPTIVE_CLASSIFICATION",
        "group_count": len(groups), "leadership_state_counts": {k: len(v) for k, v in sorted(by_state.items())},
        "groups_with_more_decliners_than_advancers": more_dec,
        "groups_with_more_advancers_than_decliners": more_adv,
        "groups_by_leadership_state": {k: sorted(v, key=lambda g: (g["group"] or "")) for k, v in sorted(by_state.items())},
        "comparability": "NOT_COMPARABLE_WITH_BROKER_SECTOR_COUNTS_DIFFERENT_TAXONOMY",
        "prior_session_comparison": "NOT_EMITTED_REQUIRES_PRIOR_COMPARABLE_SESSION",
    }


def _liquidity(official_liquidity: Mapping[str, Any] | None) -> dict[str, Any]:
    components = {"matched_value": "UNAVAILABLE", "negotiated_value": "UNAVAILABLE", "total_value": "UNAVAILABLE",
                  "matched_value_vs_20_session_average": "UNAVAILABLE"}
    base = {"basis_required": "EXCHANGE_BASIS_VALUE_SAME_SOURCE_SCOPE_UNIT_AND_REFERENCE_WINDOW",
            "price_times_volume": "NOT_PERMITTED", "components": components,
            "liquidity_expansion_label": "NOT_EMITTED"}
    if not isinstance(official_liquidity, Mapping):
        return _unavailable("OFFICIAL_LIQUIDITY_NOT_BOUND_TO_DAILY", **base)
    status = str(official_liquidity.get("status") or "UNKNOWN")
    if status != "AVAILABLE":
        return _unavailable(str(official_liquidity.get("reason_code") or status), **base,
                            source_status={k: official_liquidity.get(k) for k in (
                                "status", "planned_requests", "hard_request_budget", "http_requests_made")})
    return _unavailable("MARKET_AGGREGATE_VALUE_NOT_IN_PER_SYMBOL_RESEARCH_ARTIFACT", **base)


def _foreign_flow(regime: Mapping[str, Any] | None, flow: Mapping[str, Any] | None) -> dict[str, Any]:
    dim = (((regime or {}).get("dimensions") or {}).get("FOREIGN_FLOW") or {}) if isinstance(regime, Mapping) else {}
    state = dim.get("state") or "UNKNOWN"
    bound = isinstance(flow, Mapping) and bool(flow.get("artifact_identity"))
    if state in ("UNKNOWN", "UNAVAILABLE") and not bound:
        return _unavailable("NO_MARKET_WIDE_QUALIFIED_FOREIGN_VALUE_BOUND",
                            scope_rule="An observed-cohort net value must carry its cohort and is never whole-exchange flow.",
                            regime_dimension={"state": state, "authority": dim.get("authority"),
                                              "limitations": dim.get("limitations")},
                            institutional_intent_from_relative_volume="NOT_PERMITTED")
    return {"status": "OBSERVED_COHORT_ONLY", "regime_dimension": {"state": state, "authority": dim.get("authority"),
                                                                  "limitations": dim.get("limitations")},
            "flow_artifact_identity": (flow or {}).get("artifact_identity"),
            "scope_rule": "Observed-cohort flow is never whole-exchange flow.",
            "institutional_intent_from_relative_volume": "NOT_PERMITTED"}


def _macro(regime: Mapping[str, Any] | None) -> dict[str, Any]:
    dims = ((regime or {}).get("dimensions") or {}) if isinstance(regime, Mapping) else {}
    if not dims:
        return _unavailable("MACRO_REGIME_CONTEXT_ABSENT")
    rows = {}
    for axis in _MACRO_AXES:
        d = dims.get(axis) or {}
        fresh = d.get("freshness") or {}
        rows[axis] = {"state": d.get("state") or "UNKNOWN", "authority": d.get("authority") or "ABSENT",
                      "freshness_status": fresh.get("status"), "valid_through": fresh.get("valid_through"),
                      "next_expected_official_release": fresh.get("next_expected_official_release"),
                      "reason_codes": list(fresh.get("reason_codes") or []) + list(d.get("limitations") or [])}
    usable = sorted(a for a, r in rows.items() if r["state"] not in ("UNKNOWN", "UNAVAILABLE"))
    return {"status": "PARTIAL" if usable and len(usable) < len(rows) else ("AVAILABLE" if usable else "UNAVAILABLE"),
            "usable_axes": usable, "axes": rows,
            "rule": "Only official/qualified series inside their freshness window are used; press reports are never macro authority."}


def _questions(c: Mapping[str, Any]) -> list[dict[str, Any]]:
    breadth, sectors = c["breadth"], c["sectors"]
    index_ok = c["benchmark_index"]["status"] == "AVAILABLE"
    flow_ok = c["foreign_flow"]["status"] != "UNAVAILABLE"
    liq_ok = c["liquidity"]["status"] != "UNAVAILABLE"
    out = []
    missing = [n for n, ok in (("benchmark_index", index_ok), ("market_wide_foreign_value", flow_ok)) if not ok]
    out.append({"question": "Index fell while foreign investors bought: was that supportive?",
                "answer_state": "CANNOT_ANSWER" if missing else "PARTIAL", "missing_evidence": missing,
                "note": "Requires a bound index level and exchange-wide (not observed-cohort) foreign net value."})
    missing = [n for n, ok in (("exchange_basis_matched_value", liq_ok),) if not ok]
    out.append({"question": "Matched value rose while breadth was weak: supply pressure or accumulation?",
                "answer_state": "CANNOT_ANSWER" if missing else "PARTIAL", "missing_evidence": missing,
                "note": "Relative volume is a provider proxy, not trading value or order aggression."})
    if sectors["status"] == "AVAILABLE":
        counts = sectors["leadership_state_counts"]
        out.append({"question": "Which sector groups led or weakened?", "answer_state": "ANSWERED",
                    "evidence": {"leadership_state_counts": counts,
                                 "groups_with_more_decliners_than_advancers": sectors["groups_with_more_decliners_than_advancers"],
                                 "groups_with_more_advancers_than_decliners": sectors["groups_with_more_advancers_than_decliners"],
                                 "taxonomy": sectors["taxonomy"]}})
    else:
        out.append({"question": "Which sector groups led or weakened?", "answer_state": "CANNOT_ANSWER",
                    "missing_evidence": ["sector_leadership_context"]})
    if breadth["status"] == "AVAILABLE":
        facts = []
        if breadth["declining"] > breadth["advancing"]:
            facts.append("DECLINERS_OUTNUMBER_ADVANCERS")
        elif breadth["advancing"] > breadth["declining"]:
            facts.append("ADVANCERS_OUTNUMBER_DECLINERS")
        if isinstance(breadth["above_ma20_ratio"], float):
            facts.append("MAJORITY_AT_OR_BELOW_MA20" if breadth["above_ma20_ratio"] < 0.5 else "MAJORITY_ABOVE_MA20")
        pos, neg = breadth["positive_momentum_20d"], breadth["negative_momentum_20d"]
        if isinstance(pos, int) and isinstance(neg, int):
            facts.append("MAJORITY_NEGATIVE_20D_MOMENTUM" if neg > pos else "MAJORITY_POSITIVE_20D_MOMENTUM" if pos > neg else "EVEN_20D_MOMENTUM")
        out.append({"question": "Technical rebound, bottoming, sideways or confirmed uptrend?",
                    "answer_state": "PARTIAL", "observed_cohort_facts": facts,
                    "missing_evidence": ([] if index_ok else ["benchmark_index"]) + ["multi_session_same_cohort_comparison"],
                    "note": ("Cohort facts describe participation only. A confirmed broad uptrend would need most of the cohort "
                             "above MA20 with positive momentum; bottoming versus continuation cannot be separated from one session.")})
    out.append({"question": "Is there a false-breakout / bull-trap signature?", "answer_state": "CANNOT_ANSWER_FROM_ONE_SESSION",
                "missing_evidence": ["next_session_same_cohort_follow_through"],
                "note": "Per-ticker breakout setups are judged on their own trigger and invalidation in each card."})
    return out


def _next_session(c: Mapping[str, Any]) -> list[dict[str, str]]:
    rows = [
        {"hypothesis": "Participation improves",
         "confirm_if": "On the same exact-session cohort advancers exceed decliners and the above-MA20 share rises versus this session.",
         "refute_if": "Decliners again outnumber advancers and the above-MA20 share falls."},
        {"hypothesis": "Sector weakness is broad rather than isolated",
         "confirm_if": "The count of groups with more decliners than advancers stays at or above this session's count.",
         "refute_if": "That count falls and at least one group moves to more advancers than decliners."},
    ]
    if c["benchmark_index"]["status"] != "AVAILABLE":
        rows.append({"hypothesis": "Index direction", "confirm_if": "NOT_EVALUABLE: no bound index level.",
                     "refute_if": "NOT_EVALUABLE: no bound index level."})
    return rows


def build(*, session: str, descriptive: Mapping[str, Any], sector_leadership: Mapping[str, Any] | None = None,
          regime_context: Mapping[str, Any] | None = None, market_flow_positioning: Mapping[str, Any] | None = None,
          benchmark: Mapping[str, Any] | None = None, official_liquidity: Mapping[str, Any] | None = None) -> dict[str, Any]:
    if descriptive.get("session") != session:
        raise ValueError("MARKET_CLOSE_SESSION_MISMATCH:descriptive")
    if isinstance(sector_leadership, Mapping) and sector_leadership.get("session") not in (None, session):
        raise ValueError("MARKET_CLOSE_SESSION_MISMATCH:sector_leadership")
    components = {
        "benchmark_index": _benchmark(benchmark, session),
        "breadth": _breadth(descriptive),
        "sectors": _sectors(sector_leadership),
        "liquidity": _liquidity(official_liquidity),
        "foreign_flow": _foreign_flow(regime_context, market_flow_positioning),
        "macro": _macro(regime_context),
    }
    artifact = {
        "schema_version": "1.0.0", "contract_version": CONTRACT_VERSION, "session": session,
        "source_artifact_identities": {
            "descriptive": descriptive.get("artifact_identity"),
            "sector_leadership": (sector_leadership or {}).get("artifact_identity") if isinstance(sector_leadership, Mapping) else None,
            "regime_context": (regime_context or {}).get("artifact_identity") if isinstance(regime_context, Mapping) else None,
            "market_flow_positioning": (market_flow_positioning or {}).get("artifact_identity") if isinstance(market_flow_positioning, Mapping) else None,
            "benchmark": (benchmark or {}).get("source_identity") if isinstance(benchmark, Mapping) else None,
            "official_liquidity": (official_liquidity or {}).get("artifact_identity") if isinstance(official_liquidity, Mapping) else None,
        },
        "denominators": _denominators(descriptive),
        "components": components,
        "component_status": {k: v["status"] for k, v in components.items()},
        "interpretation": {"questions": _questions(components), "next_session_conditions": _next_session(components),
                           "regime_label_note": components["breadth"].get("existing_descriptor_rule", {}).get("meaning")},
        "authority_boundary": {"not_whole_market_unless_stated": True, "no_forecast_probability_or_score": True,
                               "no_recommendation_sizing_or_execution": True, "no_threshold_owned_here": True,
                               "index_never_derived_from_constituents": True, "value_never_price_times_volume": True},
    }
    artifact["artifact_sha256"] = _hash(artifact)
    artifact["artifact_identity"] = "market_close_intelligence:" + artifact["artifact_sha256"]
    return artifact


def markdown_lines(mci: Mapping[str, Any]) -> list[str]:
    c, d = mci["components"], mci["denominators"]
    lines = ["## Market close intelligence",
             f"- Denominators: candidates {d['input_candidates']['count']} / active equities {d['current_active_equity']['count']} / "
             f"exact-session observed {d['exact_session_observed']['count']} / technical coverage {d['technical_coverage']['count']}. "
             "Breadth ratios use technical coverage only; they are not whole-market statistics."]
    bi = c["benchmark_index"]
    lines.append(f"- VN-Index: {bi['close']} ({bi['change_points']:+} pts, {bi['change_percent']:+}%), {bi['authority']}."
                 if bi["status"] == "AVAILABLE" else f"- VN-Index: UNAVAILABLE ({', '.join(bi['reason_codes'])}); never derived from constituent prices.")
    b = c["breadth"]
    if b["status"] == "AVAILABLE":
        lines.append(f"- Breadth ({b['denominator']} names): {b['advancing']} up / {b['declining']} down / {b['unchanged']} unchanged; "
                     f"advance ratio {b['advance_ratio']:.1%}, decline ratio {b['decline_ratio']:.1%}; above MA20 {b['above_ma20']} "
                     f"({b['above_ma20_ratio']:.1%}), at/below {b['at_or_below_ma20']}; 20d momentum +{b['positive_momentum_20d']} / -{b['negative_momentum_20d']}.")
        lines.append(f"- Label {b['existing_descriptor']}: {b['existing_descriptor_rule']['meaning']}")
    s = c["sectors"]
    if s["status"] == "AVAILABLE":
        weak = [g["group"] for g in s["groups_by_leadership_state"].get("WEAKENING", [])]
        lines.append(f"- Sector groups ({s['group_count']}, provider taxonomy, not comparable with broker sector counts): "
                     f"{s['groups_with_more_decliners_than_advancers']} with more decliners, {s['groups_with_more_advancers_than_decliners']} with more advancers; "
                     f"states {s['leadership_state_counts']}." + (f" Weakening: {', '.join(weak)}." if weak else ""))
    lines.append(f"- Liquidity (matched/negotiated/total value): {c['liquidity']['status']} ({', '.join(c['liquidity'].get('reason_codes') or [])}); price x volume is not used.")
    ff = c["foreign_flow"]
    lines.append(f"- Foreign flow: {ff['status']}" + (f" ({', '.join(ff.get('reason_codes') or [])})" if ff.get("reason_codes") else "") + "; observed-cohort flow is never whole-exchange flow.")
    m = c["macro"]
    if m["status"] != "UNAVAILABLE" or m.get("axes"):
        infl = (m.get("axes") or {}).get("INFLATION_PRESSURE") or {}
        lines.append(f"- Macro: usable axes {', '.join(m.get('usable_axes') or []) or 'none'}; inflation {infl.get('state')} "
                     f"({infl.get('freshness_status')}, valid through {infl.get('valid_through')}).")
    for q in mci["interpretation"]["questions"]:
        detail = q.get("observed_cohort_facts") or q.get("missing_evidence") or ""
        lines.append(f"- Q: {q['question']} -> {q['answer_state']}" + (f" ({', '.join(detail)})" if isinstance(detail, list) and detail else ""))
    for row in mci["interpretation"]["next_session_conditions"]:
        lines.append(f"- Next session - {row['hypothesis']}: confirm if {row['confirm_if']} Refute if {row['refute_if']}")
    lines.append("- Descriptive research only: no forecast, probability, recommendation or sizing.")
    return lines
