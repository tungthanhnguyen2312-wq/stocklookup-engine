"""Current-research market observations that are not part of a sealed Daily.

A benchmark whose knowledge time falls on a later Vietnam calendar date than
the session is a post-hoc observation. It is not written back into that
session. A source that was checked and is not available is closed with the
evidence of the check. This module does not fetch, does not derive an index
from constituents, and does not turn price times volume into trading value.
"""
from __future__ import annotations

from typing import Any, Mapping

CONTRACT_VERSION = "market_close_current_research/v1"


def _vietnam_date(timestamp: str) -> str:
    text = str(timestamp or "")
    if len(text) < 10 or text[4] != "-" or text[7] != "-":
        return ""
    return text[:10]


def posthoc_benchmark(benchmark: Mapping[str, Any] | None) -> dict[str, Any]:
    """Accept a qualified level only as research after the session, not as seal-time knowledge."""
    if not isinstance(benchmark, Mapping):
        return {"status": "ABSENT", "reason_codes": ["NO_BENCHMARK"], "session_binding": "NOT_WRITTEN_INTO_SEALED_DAILY"}
    required = ("index", "session", "close", "previous_close", "previous_session",
                "source_identity", "knowledge_available_at", "authority")
    if any(benchmark.get(key) in (None, "") for key in required):
        return {"status": "REFUSED", "reason_codes": ["BENCHMARK_INPUT_INCOMPLETE"],
                "session_binding": "NOT_WRITTEN_INTO_SEALED_DAILY"}
    session = str(benchmark["session"])
    knowledge_date = _vietnam_date(str(benchmark["knowledge_available_at"]))
    if not knowledge_date:
        return {"status": "REFUSED", "reason_codes": ["KNOWLEDGE_TIME_UNPARSEABLE"],
                "session_binding": "NOT_WRITTEN_INTO_SEALED_DAILY"}
    if knowledge_date == session:
        return {"status": "REFUSED", "reason_codes": ["NOT_POSTHOC_USE_THE_SESSION_BIND"],
                "session_binding": "NOT_WRITTEN_INTO_SEALED_DAILY"}
    if knowledge_date < session:
        return {"status": "REFUSED", "reason_codes": ["KNOWLEDGE_TIME_BEFORE_SESSION"],
                "session_binding": "NOT_WRITTEN_INTO_SEALED_DAILY"}
    close, previous = benchmark["close"], benchmark["previous_close"]
    return {
        "status": "POSTHOC_CURRENT_RESEARCH",
        "index": benchmark["index"],
        "session": session,
        "close": close,
        "previous_close": previous,
        "previous_session": benchmark["previous_session"],
        "change_points": round(close - previous, 2),
        "change_percent": round((close / previous - 1) * 100, 2) if previous else None,
        "source_identity": benchmark["source_identity"],
        "authority": benchmark["authority"],
        "knowledge_available_at": benchmark["knowledge_available_at"],
        "knowledge_date": knowledge_date,
        "seal_time_knowledge": "NOT_CLAIMED",
        "session_binding": "NOT_WRITTEN_INTO_SEALED_DAILY",
        "same_knowledge_as_sealed_breadth": False,
        "derivation_from_constituents": "NOT_PERMITTED",
        "pit_backtest_eligible": False,
    }


def close_blocker(*, source: str, reason: str, evidence: Mapping[str, Any]) -> dict[str, Any]:
    """Close one unavailable source. An empty evidence record is not a closure."""
    if not source or not reason or not evidence:
        raise ValueError("SOURCE_CLOSURE_REQUIRES_EVIDENCE")
    if any(evidence.get(key) not in (None, "", [], {}) for key in ("value", "matched_value_vnd", "foreign_net_value_vnd")):
        raise ValueError("SOURCE_CLOSURE_CANNOT_CARRY_A_MEASUREMENT")
    return {
        "source": source,
        "status": "CLOSED_UNAVAILABLE",
        "reason": reason,
        "evidence": dict(evidence),
        "session_binding": "NOT_WRITTEN_INTO_SEALED_DAILY",
    }


def weekend_source_closures_20261107() -> list[dict[str, Any]]:
    """Closures measured on 2026-11-07. They do not invent the missing figures."""
    return [
        close_blocker(
            source="NSO_CPI_OCTOBER_2026",
            reason="OCTOBER_2026_CPI_NOT_ON_ADMITTED_NSO_ENGLISH_ROUTE",
            evidence={
                "route": "vietnam_official_macro_evidence.acquire",
                "retrieved_at": "2026-11-07T03:47:44Z",
                "cpi_periods": ["2026-06", "2026-07"],
                "latest_retained_observation": "2026-07",
                "latest_retained_value_percent_yoy": 4.45,
                "latest_released_at": "2026-08-03",
                "freshness_status": "STALE_OR_UNAVAILABLE",
                "valid_through": "2026-09-30",
                "freshness_reason_codes": ["FRESHNESS_CEILING_EXCEEDED"],
                "next_expected_official_release": "2026-12-03",
                "next_reference_period": "2026-11",
                "discovered_new_release_count": 0,
                "october_2026_present": False,
            },
        ),
        close_blocker(
            source="SBV_CENTRAL_RATE",
            reason="NO_MACHINE_READABLE_CURRENT_OFFICIAL_SBV_FX_OBSERVATION_RETAINED",
            evidence={"machine_readable_observation_retained": False, "new_route_opened": False},
        ),
        close_blocker(
            source="HOSE_AGGREGATE_TRADING_VALUE_2026-11-06",
            reason="NO_BOUNDED_LOCATOR_FOR_HOSE_DAILY_TRADING_SUMMARY",
            evidence={
                "locator_attempt": "duckduckgo_html",
                "locator_http_status": 202,
                "official_urls_found": 0,
                "known_sample_urls": [
                    "https://staticfile.hsx.vn/Uploads/UploadDocuments/2437581/20260206%20Tong%20hop%20thong%20tin%20giao%20dich.pdf",
                    "https://staticfile.hsx.vn/Uploads/UploadDocuments/2439241/20260213%20Tong%20hop%20thong%20tin%20giao%20dich.pdf",
                ],
                "news_id_derivable": False,
                "price_times_volume": "NOT_PERMITTED",
            },
        ),
        close_blocker(
            source="WHOLE_EXCHANGE_FOREIGN_VALUE",
            reason="NO_AUTHORIZED_WHOLE_EXCHANGE_FOREIGN_VALUE_ROUTE",
            evidence={
                "dnse_cohort_is_whole_exchange": False,
                "institutional_intent_from_relative_volume": "NOT_PERMITTED",
            },
        ),
    ]


def current_research_artifact(*, benchmark: Mapping[str, Any] | None, closures: list[dict[str, Any]]) -> dict[str, Any]:
    posthoc = posthoc_benchmark(benchmark)
    return {
        "contract_version": CONTRACT_VERSION,
        "session_binding": "NOT_WRITTEN_INTO_SEALED_DAILY",
        "posthoc_benchmark": posthoc,
        "source_closures": closures,
        "compatibility": {
            "regime_breadth_and_benchmark": "NOT_JOINED",
            "reason": "BENCHMARK_KNOWLEDGE_TIME_IS_AFTER_THE_SEALED_SESSION"
            if posthoc.get("status") == "POSTHOC_CURRENT_RESEARCH" else "BENCHMARK_NOT_POSTHOC",
        },
    }
