import pytest

from stocklookup_core.decision.market_close_current_research import (
    close_blocker, current_research_artifact, posthoc_benchmark, weekend_source_closures_20261107,
)

BENCHMARK = {
    "index": "VNINDEX", "session": "2026-11-06", "close": 1725.36, "previous_close": 1740.73,
    "previous_session": "2026-11-05",
    "source_identity": "dnse_index_return_series/4cf91c602cb69b01a5acfb1bf6e772806a5ee09f7b22d9a0d216f8b78340511e",
    "knowledge_available_at": "2026-11-07T09:49:56+07:00",
    "authority": "DNSE_CURRENT_STATE_REPUBLISHED_INDEX_NOT_HOSE_ADMINISTRATOR",
}


def test_later_knowledge_is_posthoc_and_not_sealed():
    out = posthoc_benchmark(BENCHMARK)
    assert out["status"] == "POSTHOC_CURRENT_RESEARCH"
    assert out["change_points"] == -15.37
    assert out["session_binding"] == "NOT_WRITTEN_INTO_SEALED_DAILY"
    assert out["seal_time_knowledge"] == "NOT_CLAIMED"
    assert out["same_knowledge_as_sealed_breadth"] is False
    assert out["derivation_from_constituents"] == "NOT_PERMITTED"


def test_same_day_knowledge_is_not_relabelled_as_posthoc():
    same_day = dict(BENCHMARK, knowledge_available_at="2026-11-06T15:05:00+07:00")
    out = posthoc_benchmark(same_day)
    assert out["status"] == "REFUSED"
    assert "NOT_POSTHOC_USE_THE_SESSION_BIND" in out["reason_codes"]


def test_source_closures_carry_evidence_and_no_missing_measurement():
    closures = weekend_source_closures_20261107()
    assert [row["source"] for row in closures] == [
        "NSO_CPI_OCTOBER_2026", "SBV_CENTRAL_RATE",
        "HOSE_AGGREGATE_TRADING_VALUE_2026-11-06", "WHOLE_EXCHANGE_FOREIGN_VALUE",
    ]
    cpi = closures[0]["evidence"]
    assert cpi["october_2026_present"] is False
    assert "2026-10" not in cpi["cpi_periods"]
    assert cpi["latest_retained_observation"] == "2026-07"
    artifact = current_research_artifact(benchmark=BENCHMARK, closures=closures)
    assert artifact["compatibility"]["regime_breadth_and_benchmark"] == "NOT_JOINED"
    assert artifact["session_binding"] == "NOT_WRITTEN_INTO_SEALED_DAILY"
    with pytest.raises(ValueError):
        close_blocker(source="HOSE", reason="MISSING", evidence={})
    with pytest.raises(ValueError):
        close_blocker(source="HOSE", reason="HAS_VALUE", evidence={"value": 1})
