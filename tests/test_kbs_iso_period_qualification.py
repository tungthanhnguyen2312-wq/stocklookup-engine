"""SOURCE_RECOVERY_SPEC_KBS_AND_FIVE section 8: hermetic, no network, no vnstock, no Daily."""
from __future__ import annotations

import pytest

import kbs_quarterly_financial_retention as kbs
import provider_financial_source_metadata as source
import stocklookup_core.financial.financial_flow_semantics_ttm_bridge as bridge

ENDS = {1: "03-31", 2: "06-30", 3: "09-30", 4: "12-31"}


def fact(period, value, *, start=None, end=None, metric="revenue", ticker="AAA", scope="CONSOLIDATED",
         currency="VND", src="raw-1", ordinal=None, provider="KBS"):
    year, q = int(period[:4]), int(period[6])
    row = {"ticker": ticker, "canonical_metric": metric, "provider": provider,
           "statement_family": "income_statement", "reporting_period": period, "period_type": "quarterly",
           "value": value, "status": "provider_reported", "statement_scope": scope, "currency": currency,
           "scale": 1, "source_sha256": src, "fact_id": f"{ticker}-{metric}-{period}-{ordinal}",
           "period_start": start if start is not None else f"{year}-{(q - 1) * 3 + 1:02d}-01",
           "period_end": end if end is not None else f"{year}-{ENDS[q]}"}
    if ordinal is not None:
        row["head_ordinal"] = ordinal
    return row


def q(rows):
    return bridge.qualify_kbs_income_from_retained_head(rows)


def test_iso_quarter_qualifies_as_provider_research_only():
    [row] = q([fact("2025-Q1", 10, start="2025-01-01", end="2025-03-31")])
    assert row["qualified_normalized_period"] == "2025-Q1"
    assert row["period_normalization"] == "QUALIFIED_KBS_ISO_BOUNDS"
    assert row["reporting_period"] == "2025-Q1" and row["status"] == "provider_reported"
    assert "flow_period_basis" not in row
    assert bridge.flow_semantics(row)["duration_months"] == 3


def test_compact_yyyymm_bounds_stay_unverified_and_raw():
    [row] = q([fact("2025-Q1", 10, start="202501", end="202503")])
    assert row.get("qualified_normalized_period") is None
    assert row["canonical_period_qualification"] == bridge.KBS_PERIOD_IDENTITY_UNVERIFIED
    assert row["period_start"] == "202501"
    assert bridge.flow_semantics(row)["reason"] == bridge.KBS_PERIOD_IDENTITY_UNVERIFIED


def test_label_quarter_disagreeing_with_bounds_is_refused():
    [row] = q([fact("2025-Q1", 10, start="2025-04-01", end="2025-06-30")])
    assert row.get("qualified_normalized_period") is None
    assert row["canonical_period_qualification"] == bridge.KBS_LABEL_BOUNDS_DISAGREE


def test_equal_duplicate_heads_keep_one_observation():
    rows = q([fact("2025-Q1", 10, ordinal=1), fact("2025-Q1", 10, ordinal=2)] +
             [fact(f"2025-Q{n}", n) for n in (2, 3, 4)])
    record = bridge.build_ticker_record(ticker="AAA", entity_type="corporate", facts=rows)
    assert record["ttm"]["revenue"]["value"] == 19.0  # 10 + 2 + 3 + 4, Q1 counted once
    assert [r["canonical_period_qualification"] for r in rows[:2]] == ["QUALIFIED", "EQUAL_RESTATEMENT_VARIANT_REDUNDANT"]


def test_conflicting_duplicate_heads_gate_the_whole_payload():
    rows = q([fact("2025-Q1", 10, ordinal=1), fact("2025-Q1", 11, ordinal=2)] +
             [fact(f"2025-Q{n}", n) for n in (2, 3, 4)])
    assert all(r["ttm_blocker"] == bridge.KBS_PERIOD_ALIGNMENT_BLOCKER for r in rows)
    assert all(bridge.flow_semantics(r)["flow_period_basis"] == "UNKNOWN" for r in rows)
    record = bridge.build_ticker_record(ticker="AAA", entity_type="corporate", facts=rows)
    assert "revenue" not in record.get("ttm", {})


def test_same_label_two_iso_ranges_is_ambiguous():
    rows = q([fact("2025-Q1", 10, start="2025-01-01", end="2025-03-31"),
              fact("2025-Q1", 10, start="2025-04-01", end="2025-06-30")])
    assert {r["canonical_period_qualification"] for r in rows} == {bridge.KBS_AMBIGUOUS_PERIOD_HEAD}
    assert all(r.get("qualified_normalized_period") is None for r in rows)


def test_overlapping_ranges_are_ambiguous_not_cut():
    rows = q([fact("2025-Q1", 10), fact("2025-Q2", 30, start="2025-01-01", end="2025-06-30")])
    assert {r["canonical_period_qualification"] for r in rows} == {bridge.KBS_AMBIGUOUS_PERIOD_HEAD}
    assert all(r.get("qualified_normalized_period") is None for r in rows)


def test_six_month_duration_is_not_a_single_quarter():
    [row] = q([fact("2025-Q2", 10, start="2025-01-01", end="2025-06-30")])
    assert row["canonical_period_qualification"] == bridge.KBS_PERIOD_NOT_SINGLE_QUARTER


def test_unmapped_scope_and_non_vnd_currency_do_not_qualify():
    [scope] = q([fact("2025-Q1", 10, scope="UNKNOWN")])
    [money] = q([fact("2025-Q1", 10, currency="USD")])
    assert scope["canonical_period_qualification"] == bridge.KBS_STATEMENT_SCOPE_UNKNOWN
    assert money["canonical_period_qualification"] == bridge.KBS_CURRENCY_NOT_VND


def _hpg(label, value, start, end):
    return {**fact(label, value, start=start, end=end, ticker="HPG", src="raw-hpg"), "scale": 1}


HPG_REV = {"2025-Q3": 40_000_000_000_000, "2025-Q4": 38_000_000_000_000,
           "2025-Q4_1": 37_116_094_618_482, "2026-Q1": 41_000_000_000_000}


def test_hpg_map_kept_when_iso_agrees_and_refused_when_iso_disagrees():
    rows = [_hpg(k, v, None, None) for k, v in HPG_REV.items()]
    for row in rows:
        row["period_start"] = row["period_end"] = None
    mapped = q(bridge.qualify_proven_kbs_income_period(rows))
    assert {r["qualified_normalized_period"] for r in mapped} == {"2025-Q1", "2025-Q2", "2025-Q3", "2025-Q4"}
    assert [r["reporting_period"] for r in mapped] == list(HPG_REV)
    # ISO bounds that put raw 2025-Q3 (map: 2025-Q2) in the label's own quarter disagree with the map.
    disagree = [_hpg(k, v, None, None) for k, v in HPG_REV.items()]
    for row in disagree:
        row["period_start"] = row["period_end"] = None
    disagree[0].update(period_start="2025-07-01", period_end="2025-09-30")
    out = q(bridge.qualify_proven_kbs_income_period(disagree))
    assert out[0]["qualified_normalized_period"] is None
    assert out[0]["ttm_blocker"] == bridge.KBS_PERIOD_ALIGNMENT_UNRECONCILED


def test_sidecar_label_claim_is_not_adopted_by_a_canonical_fact():
    row = {**fact("2025-Q1", 10), "period_start": None, "period_end": None,
           "flow_period_basis": "STANDALONE_QUARTER", "flow_period_basis_evidence": "kbs_kqkd_quarter_endpoint"}
    assert bridge.flow_semantics(row)["flow_period_basis"] == "UNKNOWN"


def test_four_clean_iso_quarters_give_research_ttm_three_do_not():
    four = q([fact(f"2025-Q{n}", n * 10) for n in (1, 2, 3, 4)])
    record = bridge.build_ticker_record(ticker="AAA", entity_type="corporate", facts=four)
    assert record["ttm"]["revenue"]["value"] == 100.0
    assert record["ttm"]["revenue"].get("is_actionable", False) is False
    three = q([fact(f"2025-Q{n}", n * 10) for n in (1, 2, 3)])
    assert "revenue" not in bridge.build_ticker_record(ticker="AAA", entity_type="corporate", facts=three).get("ttm", {})


def test_vci_income_and_vci_ocf_semantics_unchanged():
    vci = fact("2025-Q1", 1, provider="VCI")
    assert bridge.flow_semantics(q([vci])[0])["reason"] == "VCI_PERIOD_DURATION_REMAINS_UNKNOWN"
    ocf = {**fact("2025-Q1", 1, provider="VCI", metric="operating_cash_flow"), "cumulative_state": "period_only"}
    assert bridge.flow_semantics(q([ocf])[0])["method"] == "DIRECT_RETAINED_CASH_FLOW_RESOLVER"


def test_retention_sidecar_carries_closed_canonical_qualification():
    request = kbs.plan_for_tickers(["AAA"])[0]
    heads = [{"YearPeriod": 2025, "TermName": "Quý 1", "PeriodBegin": "2025-01-01", "PeriodEnd": "2025-03-31",
              "United": "HN", "Currency": "VND"},
             {"YearPeriod": 2025, "TermName": "Quý 2", "PeriodBegin": "202504", "PeriodEnd": "202506",
              "United": "HN", "Currency": "VND"}]
    rows = kbs.metadata_rows(request, {"Unit": [{"UnitedCode": "HN", "UnitedName": "Hợp nhất"}], "Head": heads},
                             raw_hash="h")
    assert [r["canonical_period_qualification"] for r in rows] == ["QUALIFIED", bridge.KBS_PERIOD_IDENTITY_UNVERIFIED]
    assert [r["canonical_qualified_period"] for r in rows] == ["2025-Q1", None]
    assert rows[1]["flow_period_basis"] == "STANDALONE_QUARTER"  # endpoint claim retained, not canonical


def test_fetch_stays_retired_without_owner_gate():
    with pytest.raises(RuntimeError, match="RETIRED_PROVIDER|GOVERNED"):
        source.fetch_raw_once(kbs.plan_for_tickers(["HPG"])[0])
