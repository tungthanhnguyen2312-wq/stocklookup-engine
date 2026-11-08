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
from datetime import date, timedelta
from typing import Any, Mapping

CONTRACT_VERSION = "market_close_intelligence/v1"
SNAPSHOT_CONTRACT = "market_close_participation_snapshot/v1"
SESSION_CHANGE_RULE = "matched_cohort_session_change/v1"

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


# ---------------------------------------------------------------------------
# Matched-cohort session change (market_close_participation_snapshot/v1 +
# matched_cohort_session_change/v1). Pure functions; no I/O.
#
# Aggregate breadth ratios from two sessions have different denominators whenever
# technical coverage changes (it has moved between 763 and 956 names), so their
# difference mixes participation with coverage. The snapshot keeps, per ticker,
# only the three signs the breadth statistics are built from (1-day return, MA20
# side, 20-day momentum) for exactly the cohort market_breadth uses. Comparing two
# snapshots on the tickers present in BOTH gives before/after ratios that share one
# denominator; cohort churn is reported, never blended in. No threshold is
# introduced: changes are signed differences, and the Market Close brief's own
# published "Participation improves" condition is evaluated verbatim.
# The previous session is never chosen here: callers pass two governed sessions.
# ---------------------------------------------------------------------------

_TREND_CODE = {"ABOVE_MA20": 1, "AT_OR_BELOW_MA20": 0}
SNAPSHOT_COHORT_RULE = ("Same-session SHADOW_ONLY technical features inside the current descriptive scope - "
                        "the exact cohort of market_breadth. Row = [ticker, sign(return_1d), MA20 side (1 above, "
                        "0 at/below, null unknown), sign(momentum_20d)].")


def _sign(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return 1 if value > 0 else -1 if value < 0 else 0


def participation_snapshot(*, session: str, descriptive: Mapping[str, Any]) -> dict[str, Any]:
    """Compact per-ticker participation signs for one governed descriptive artifact."""
    if not isinstance(session, str) or not session:
        raise ValueError("MARKET_CLOSE_SESSION_MISSING:descriptive")
    if descriptive.get("session") != session:
        raise ValueError("MARKET_CLOSE_SESSION_MISMATCH:descriptive")
    base: dict[str, Any] = {"schema_version": "1.0.0", "contract_version": SNAPSHOT_CONTRACT, "session": session,
                            "descriptive_artifact_identity": descriptive.get("artifact_identity"),
                            "cohort_rule": SNAPSHOT_COHORT_RULE}
    records = descriptive.get("records")
    if not isinstance(records, Mapping) or not records:
        base.update({"status": "UNAVAILABLE", "reason_codes": ["DESCRIPTIVE_PER_TICKER_RECORDS_ABSENT"], "cohort": [], "cohort_count": 0})
    else:
        rows: list[list[Any]] = []
        for ticker in sorted(records):
            row = records[ticker]
            if not isinstance(row, Mapping) or not row.get("in_current_descriptive_scope"):
                continue
            technical = row.get("technical_features") or {}
            if technical.get("status") != "SHADOW_ONLY" or not technical.get("is_current_session"):
                continue
            values = technical.get("values") or {}
            direction = _sign(values.get("return_1d"))
            if direction is None:
                continue
            rows.append([str(ticker), direction, _TREND_CODE.get(row.get("trend_state")), _sign(values.get("momentum_20d"))])
        expected = (descriptive.get("market_breadth") or {}).get("same_session_technical_feature_available_count")
        base.update({"status": "AVAILABLE", "cohort": rows, "cohort_count": len(rows),
                     "cohort_reconciliation": ("MATCHES_MARKET_BREADTH" if expected == len(rows)
                                               else "DIFFERS_FROM_MARKET_BREADTH_COUNT" if isinstance(expected, int)
                                               else "MARKET_BREADTH_COUNT_ABSENT")})
    base["artifact_sha256"] = _hash(base)
    base["artifact_identity"] = "market_close_participation_snapshot:" + base["artifact_sha256"]
    return base


def _direction(delta: float | None) -> str:
    if delta is None:
        return "UNKNOWN"
    return "UP" if delta > 0 else "DOWN" if delta < 0 else "FLAT"


def _weekdays_between(earlier: str, later: str) -> int | None:
    """Mon-Fri dates strictly between two sessions. A warning input only: this is not an
    exchange calendar and is never used to choose or validate a comparison session."""
    try:
        start, end = date.fromisoformat(earlier), date.fromisoformat(later)
    except (TypeError, ValueError):
        return None
    days = (end - start).days
    return sum(1 for k in range(1, days) if (start + timedelta(days=k)).weekday() < 5) if days > 1 else 0


def _cohort_stats(rows: Mapping[str, list[Any]], tickers: list[str], trend_tickers: list[str],
                  momentum_tickers: list[str]) -> dict[str, Any]:
    """Each share uses a denominator shared by both sessions: matched tickers for advance/decline,
    tickers with a known MA20 side in both sessions for MA20, and tickers with a known momentum
    sign in both sessions for momentum. UNKNOWN stays missing; it is never counted as negative."""
    n = len(tickers)
    adv = sum(1 for t in tickers if rows[t][1] == 1)
    dec = sum(1 for t in tickers if rows[t][1] == -1)
    above = sum(1 for t in trend_tickers if rows[t][2] == 1)
    pos = sum(1 for t in momentum_tickers if rows[t][3] == 1)
    return {"advancing": adv, "declining": dec, "unchanged": n - adv - dec,
            "advance_ratio": _ratio(adv, n), "decline_ratio": _ratio(dec, n),
            "above_ma20": above, "above_ma20_share": _ratio(above, len(trend_tickers)),
            "positive_momentum_20d": pos, "positive_momentum_share": _ratio(pos, len(momentum_tickers))}


def _pp(after: float | None, before: float | None) -> float | None:
    return round((after - before) * 100, 2) if isinstance(after, float) and isinstance(before, float) else None


def session_change(current: Mapping[str, Any] | None, previous: Mapping[str, Any] | None, *,
                   adjacency: str = "ADJACENCY_UNVERIFIED") -> dict[str, Any]:
    """Matched-cohort participation change between two governed sessions. Descriptive only."""
    if not isinstance(current, Mapping) or current.get("status") != "AVAILABLE":
        return _unavailable("CURRENT_PARTICIPATION_SNAPSHOT_UNAVAILABLE", rule=SESSION_CHANGE_RULE)
    if not isinstance(previous, Mapping):
        return _unavailable("NO_PREVIOUS_PARTICIPATION_SNAPSHOT", rule=SESSION_CHANGE_RULE)
    if previous.get("contract_version") != SNAPSHOT_CONTRACT or previous.get("status") != "AVAILABLE":
        return _unavailable("PREVIOUS_PARTICIPATION_SNAPSHOT_UNAVAILABLE", rule=SESSION_CHANGE_RULE)
    if not str(previous.get("session") or "") < str(current.get("session") or ""):
        return _unavailable("PREVIOUS_SESSION_NOT_EARLIER", rule=SESSION_CHANGE_RULE)
    if previous.get("cohort_rule") != current.get("cohort_rule"):
        return _unavailable("COHORT_RULE_CHANGED_NOT_COMPARABLE", rule=SESSION_CHANGE_RULE)
    # A snapshot whose row count disagrees with its own market_breadth count is not the cohort the
    # Market Close brief describes; comparing it would evaluate that brief's condition on other data.
    # An absent breadth count (older descriptive artifacts) is not a disagreement.
    for side, snap in (("CURRENT", current), ("PREVIOUS", previous)):
        if snap.get("cohort_reconciliation") == "DIFFERS_FROM_MARKET_BREADTH_COUNT":
            return _unavailable(f"{side}_PARTICIPATION_COHORT_DIFFERS_FROM_MARKET_BREADTH", rule=SESSION_CHANGE_RULE)
    now_rows = {r[0]: r for r in current.get("cohort") or []}
    then_rows = {r[0]: r for r in previous.get("cohort") or []}
    matched = sorted(set(now_rows) & set(then_rows))
    if not matched:
        return _unavailable("NO_MATCHED_TICKERS_BETWEEN_SESSIONS", rule=SESSION_CHANGE_RULE)
    trend_matched = [t for t in matched if now_rows[t][2] is not None and then_rows[t][2] is not None]
    momentum_matched = [t for t in matched if now_rows[t][3] is not None and then_rows[t][3] is not None]
    before = _cohort_stats(then_rows, matched, trend_matched, momentum_matched)
    after = _cohort_stats(now_rows, matched, trend_matched, momentum_matched)
    crossed_up = sum(1 for t in trend_matched if then_rows[t][2] == 0 and now_rows[t][2] == 1)
    crossed_down = sum(1 for t in trend_matched if then_rows[t][2] == 1 and now_rows[t][2] == 0)
    changes = {
        "advance_ratio_pp": _pp(after["advance_ratio"], before["advance_ratio"]),
        "decline_ratio_pp": _pp(after["decline_ratio"], before["decline_ratio"]),
        "above_ma20_share_pp": _pp(after["above_ma20_share"], before["above_ma20_share"]),
        "positive_momentum_share_pp": _pp(after["positive_momentum_share"], before["positive_momentum_share"]),
    }
    adv_dir, ma_dir = _direction(changes["advance_ratio_pp"]), _direction(changes["above_ma20_share_pp"])
    if "UNKNOWN" in (adv_dir, ma_dir):
        character = "UNKNOWN"
    elif adv_dir == ma_dir == "UP":
        character = "BROADENING"
    elif adv_dir == ma_dir == "DOWN":
        character = "NARROWING"
    elif adv_dir == ma_dir == "FLAT":
        character = "UNCHANGED"
    elif "FLAT" in (adv_dir, ma_dir):
        character = "UNCHANGED_ON_ONE_MEASURE"
    else:
        character = "DIVERGENT"
    # Market Close's published next-session condition, evaluated verbatim on the matched cohort.
    participation = ("CONFIRMED" if after["advancing"] > after["declining"] and ma_dir == "UP"
                     else "REFUTED" if after["declining"] > after["advancing"] and ma_dir == "DOWN"
                     else "NEITHER_CONFIRMED_NOR_REFUTED")
    limitations = ["Cohort-level statistics on the observed technical cohort; not whole-market breadth.",
                   "A session-to-session change is descriptive; it is not a trend, forecast or timing signal."]
    if adjacency != "REGISTRY_IMMEDIATE_PREVIOUS_COMPLETED_SESSION":
        limitations.append("The previous session is not verified as the immediately preceding completed session.")
    weekdays = _weekdays_between(str(previous["session"]), str(current["session"]))
    if weekdays:
        limitations.append(f"{weekdays} weekday(s) lie between the two sessions; unless all were exchange holidays, "
                           "this change spans more than one trading session.")
    return {
        "status": "AVAILABLE", "rule": SESSION_CHANGE_RULE,
        "current_session": current["session"], "previous_session": previous["session"], "adjacency": adjacency,
        "span": {"calendar_weekdays_between": weekdays, "basis": "MON_FRI_CALENDAR_WARNING_ONLY_NOT_EXCHANGE_CALENDAR",
                 "may_span_multiple_trading_sessions": bool(weekdays)},
        "previous_snapshot_identity": previous.get("artifact_identity"), "current_snapshot_identity": current.get("artifact_identity"),
        "cohort": {"matched": len(matched), "matched_with_ma20_side_both_sessions": len(trend_matched),
                   "matched_with_momentum_both_sessions": len(momentum_matched),
                   "current_only": len(set(now_rows) - set(then_rows)), "previous_only": len(set(then_rows) - set(now_rows)),
                   "rule": "Every before/after ratio uses the matched tickers only, so both sessions share one denominator."},
        "previous": before, "current": after, "changes": changes,
        "ma20_crossings": {"crossed_above": crossed_up, "crossed_below": crossed_down, "net": crossed_up - crossed_down},
        "participation_character": character,
        "participation_character_rule": ("BROADENING = matched advance ratio and above-MA20 share both rose; NARROWING = both fell; "
                                         "DIVERGENT = opposite signs; UNCHANGED = neither moved. Signed differences only; no threshold."),
        "market_close_condition_evaluation": {"hypothesis": "Participation improves", "state": participation,
                                              "condition_source": CONTRACT_VERSION + ":interpretation.next_session_conditions"},
        "limitations": limitations,
    }


def _index_breadth_concordance(c: Mapping[str, Any]) -> dict[str, Any]:
    bi, b = c["benchmark_index"], c["breadth"]
    question = "Was the index move broad or concentrated?"
    missing = [n for n, ok in (("benchmark_index", bi["status"] == "AVAILABLE"), ("breadth", b["status"] == "AVAILABLE")) if not ok]
    if missing:
        return {"question": question, "answer_state": "CANNOT_ANSWER", "missing_evidence": missing}
    move = _sign(bi.get("change_points"))
    majority = _sign(b["advancing"] - b["declining"])
    if move in (None, 0) or majority == 0:
        fact = "NO_DIRECTIONAL_DISAGREEMENT_EVALUABLE"
    elif move == majority:
        fact = "INDEX_AND_COHORT_MAJORITY_AGREE"
    else:
        fact = "INDEX_UP_WHILE_MORE_OF_COHORT_DECLINED" if move > 0 else "INDEX_DOWN_WHILE_MORE_OF_COHORT_ADVANCED"
    return {"question": question, "answer_state": "PARTIAL", "observed_cohort_facts": [fact],
            "note": ("VN-Index is cap-weighted on HOSE; the cohort is an equal-count cross-exchange technical cohort. "
                     "Disagreement suggests a move carried by fewer, larger names; it is context, not proof of concentration.")}


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
    out.append(_index_breadth_concordance(c))
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
