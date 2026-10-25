"""HOSE ex-date corporate-action qualification for HPG/PVD/SSI/POW against retained evidence.

The observations come from the tracked acquisition manifest and governed OCR sidecar of the
retained HOSE scans. Refusal tests that need a counterfactual alter one field of a real
observation and say so; none substitutes a synthetic source.
"""
from __future__ import annotations

import copy
import json
from datetime import datetime, timedelta

import pytest

import canonical_market_bars
import pit_price_reconstruction_contract as pit

# PR #191 moves the market-only gate from the root into `stocklookup_core.evidence`, and the
# architecture guard rejects any import of the side that does not exist. `canonical_market_bars`
# stays put and binds the gate as `pit` on both sides, so reach it through that one import.
market_only = canonical_market_bars.pit
assert market_only.CONTRACT_VERSION == "market_only_pit_eligibility/v1"
import price_basis_feature_fitness as fitness
from stocklookup_core.evidence import official_corporate_action_ledger as ledger
from stocklookup_core.evidence import qualified_corporate_action_factor_chain as factor_chain
from stocklookup_core.evidence.corporate_action_events import parse_entitlement_ratio, reviewed_scan_observation
from stocklookup_core.evidence.price_representation_contract import RepresentationContractError, lookup_contract
from tools import run_official_ca_hose_ex_date_qualification as runner

HAS_TRACKED_EVIDENCE = runner.MANIFEST.is_file() and runner.OCR_SIDECAR.is_file()
HAS_RETAINED_BYTES = HAS_TRACKED_EVIDENCE and all(
    (runner.RETENTION / row["relative_path"]).is_file()
    for row in json.loads(runner.MANIFEST.read_text(encoding="utf-8"))["records"])
requires_evidence = pytest.mark.skipif(not HAS_TRACKED_EVIDENCE, reason="tracked manifest/OCR sidecar absent")
requires_bytes = pytest.mark.skipif(not HAS_RETAINED_BYTES, reason="retained HOSE bodies stay in the ignored evidence root")

HPG_RECEIPT_ERA_CUTOFF = "2026-10-26T00:00:00+07:00"


@pytest.fixture(scope="module")
def observations():
    return runner.build_observations(runner.load_sidecar())


@pytest.fixture(scope="module")
def built(observations):
    return ledger.build_ledger(observations)


@pytest.fixture(scope="module")
def cohort(built):
    return factor_chain.build_factor_chain_cohort(built, knowledge_cutoff_resolver=runner.knowledge_resolver())


def _entry(built, ticker):
    return next(entry for entry in built["entries"] if entry["ticker"] == ticker)


def _chain(cohort, ticker):
    return next(event["factor_chain"] for event in cohort["events"] if event["ticker"] == ticker)


def _from(observations, ticker, document_class=None, event_type=None):
    return [copy.deepcopy(o) for o in observations if o["ticker"] == ticker
            and (document_class is None or o["document_type"] == document_class)
            and (event_type is None or o["event_type"] == event_type)]


# --- retained identity -------------------------------------------------------------------

@requires_bytes
def test_retained_bytes_rehash_and_agree_with_grokbot_51():
    documents = runner._verify_retained(runner._records())
    assert len(documents) == 9
    compared = [d for d in documents if d["grokbot_51_sha256_agreement"] is not None]
    assert len(compared) == 6 and all(d["grokbot_51_sha256_agreement"] for d in compared)
    assert all(d["extraction_status"] == "needs_ocr" for d in documents)


@requires_bytes
def test_tracked_artifact_replays_from_retained_bytes():
    tracked = json.loads(runner.OUTPUT.read_text(encoding="utf-8"))
    rebuilt = runner.build_artifact()
    rebuilt["artifact_sha256"] = runner.hashlib.sha256(runner._canonical(rebuilt).encode("utf-8")).hexdigest()
    assert rebuilt == tracked


@requires_evidence
def test_ocr_sidecar_tampering_fails_closed():
    sidecar = runner.load_sidecar()
    record = runner._records()["2462408"]
    sidecar["documents"][record["document_id"]]["vie+eng"]["pages"][0]["text"] += " 25/05/2026"
    with pytest.raises(ValueError, match="ocr_text_hash_mismatch"):
        runner.load_ocr_pages(sidecar, record)


@requires_evidence
def test_reviewed_token_must_be_on_its_cited_page():
    sidecar, record = runner.load_sidecar(), runner._records()["2462408"]
    review = copy.deepcopy(runner.REVIEWS["2462408"][0])
    review["fields"]["shares_planned"]["printed"] = "767.546.586"
    with pytest.raises(ValueError, match="reviewed_token_absent_from_governed_ocr:shares_planned"):
        reviewed_scan_observation(runner._document(record, record["document_class"]), review,
                                  runner.load_ocr_pages(sidecar, record))


@requires_evidence
def test_ocr_unreadable_token_is_not_cited_rather_than_repaired(observations):
    ssi_bonus = _from(observations, "SSI", event_type="bonus_shares")[0]
    assert ssi_bonus["shares_planned"] is None
    assert "shares_planned_unreadable_in_every_governed_ocr_read" in ssi_bonus["warnings"]


# --- what qualifies, and on what scope ----------------------------------------------------

@requires_evidence
def test_hpg_links_ex_date_notice_result_report_and_listing_change(built, cohort):
    entry = _entry(built, "HPG")
    assert (entry["ex_date"], entry["record_date"]) == ("2026-05-25", "2026-05-26")
    assert entry["lifecycle_state"] == "executed" and entry["qualification_state"] == "qualified"
    assert (entry["shares_planned"], entry["shares_issued"]) == (767546585, 767498665)
    assert entry["planned_count_bridge"]["planned_shares"] == 767546585
    assert entry["arithmetic_corroboration"] == {**entry["arithmetic_corroboration"], "state": "confirmed",
                                                 "cross_document": True}
    assert entry["ratio_basis_corroboration"]["state"] == "confirmed"
    assert len(entry["source_document_ids"]) == 3
    chain = _chain(cohort, "HPG")
    assert chain["classification"] == "FACTOR_CHAIN_QUALIFIED"
    assert chain["adjustment_factor"] == round(1 / 1.1, 12)
    assert chain["knowledge_cutoff"].startswith("2026-10-25T")
    assert "FROM_FIRST_OBSERVED_FORWARD_ONLY" in chain["reason_codes"]


@requires_evidence
def test_pvd_entitlement_rate_applies_to_outstanding_shares_excluding_treasury(built, cohort):
    entry = _entry(built, "PVD")
    assert (entry["ex_date"], entry["record_date"]) == ("2026-07-14", "2026-07-15")
    assert (entry["shares_before"], entry["treasury_shares_before"]) == (556296006, 416000)
    assert entry["ratio_basis_corroboration"]["state"] == "confirmed"
    assert entry["ratio_basis_corroboration"]["entitled_shares"] == 555880006
    assert entry["shares_issued"] == 371862185 and entry["shares_after"] == 928158191
    assert _chain(cohort, "PVD")["adjustment_factor"] == round(1 / 1.669, 12)


@requires_evidence
def test_pvd_correction_supersedes_the_28_july_report_without_changing_execution():
    artifact = json.loads(runner.OUTPUT.read_text(encoding="utf-8"))
    (supersession,) = artifact["supersessions"]
    assert supersession["superseded_token"]["printed"] == "371.883.632,03"
    assert supersession["corrected_token"]["printed"] == supersession["unchanged_token"]["printed"] == "371.862.185"
    superseded_id = supersession["superseded_document_id"]
    assert all(o["document_id"] != superseded_id for o in artifact["observations"])


# --- mandatory refusals ------------------------------------------------------------------

@requires_evidence
def test_record_date_is_never_used_as_ex_date(observations):
    stripped = _from(observations, "HPG")
    for observation in stripped:
        observation["ex_date"] = None  # counterfactual: the HOSE notice without its ex-date line
    entry = ledger.build_ledger(stripped)["entries"][0]
    classification, reasons = factor_chain.classify_ledger_entry(entry)
    assert entry["record_date"] == "2026-05-26"
    assert classification == "MISSING_EXPLICIT_EX_DATE"
    assert "record_date_does_not_establish_ex_date" in reasons


@requires_evidence
def test_planned_shares_are_never_treated_as_issued(observations):
    notice = _from(observations, "HPG", "ex_right_notice")
    assert notice[0]["shares_issued"] is None and notice[0]["shares_planned"] == 767546585
    entry = ledger.build_ledger(notice)["entries"][0]
    assert entry["shares_issued"] is None and entry["lifecycle_state"] == "record_date_confirmed"
    assert factor_chain.classify_ledger_entry(entry)[0] == "NOT_EXECUTED"


@requires_evidence
def test_count_derived_ratio_over_treasury_inclusive_total_is_refused(observations):
    pvd = _from(observations, "PVD")
    for observation in pvd:  # counterfactual: only an issued/total-issued ratio is available
        if observation.get("stock_ratio") is not None:
            observation["ratio_source"] = None
            observation["stock_ratio"] = round(371862185 / 556296006, 10)
    entry = ledger.build_ledger(pvd)["entries"][0]
    assert entry["stock_ratio"] is None and entry["adjustment_factor"] is None
    assert "stock_ratio_denominator_includes_treasury_shares" in entry["adjustment_factor_blocked_by"]


@requires_evidence
def test_wrong_treasury_basis_contradicts_the_planned_count(observations):
    pvd = _from(observations, "PVD")
    for observation in pvd:  # counterfactual: treasury shares misread as entitled
        if observation.get("treasury_shares_before") is not None:
            observation["treasury_shares_before"] = 0
            observation["shares_outstanding_before"] = None
    entry = ledger.build_ledger(pvd)["entries"][0]
    assert entry["ratio_basis_corroboration"]["state"] == "violated"
    assert entry["qualification_state"] == "conflicted" and entry["adjustment_factor"] is None


@requires_evidence
def test_later_retrieval_is_not_backdated_into_a_historic_decision(cohort, observations):
    chain = _chain(cohort, "HPG")
    context = fitness.price_series_context(
        ticker="HPG", provider="HOSE", source_identity="hose:tradingresult", session_start="2026-05-04",
        session_end="2026-05-22", observed_basis=fitness.POINT_IN_TIME_ADJUSTED, basis_provenance=["test"],
        factor_chain=chain)
    verdict = fitness.evaluate_feature_fitness(feature=fitness.PIT_BACKTEST, current_context=context,
                                               decision_as_of="2026-05-22T15:00:00+07:00")
    assert verdict["state"] == fitness.POINT_IN_TIME_SEMANTICS_UNQUALIFIED
    assert verdict["reason_codes"] == [fitness.REASON_PIT_FACTOR_AFTER_DECISION]
    hpg = _from(observations, "HPG")
    before = pit.classify_price_reconstruction(ticker="HPG", session="2026-05-22", knowledge_cutoff="2026-05-24T17:00:00+07:00",
                                               mode=pit.MODE_PIT_AS_KNOWN, corporate_action_observations=hpg)
    assert before["corporate_action"]["reason"] == pit.REASON_NO_EVIDENCE_KNOWABLE_BY_CUTOFF
    assert before["pit_backtest_eligible"] is False
    after = pit.classify_price_reconstruction(ticker="HPG", session="2026-05-22", knowledge_cutoff=HPG_RECEIPT_ERA_CUTOFF,
                                              mode=pit.MODE_PIT_AS_KNOWN, corporate_action_observations=hpg)
    assert after["corporate_action"]["state"] == pit.QUALIFIED
    assert after["pit_backtest_eligible"] is False  # price basis is still not raw-as-traded


@requires_evidence
def test_mixed_event_keeps_its_cash_leg_and_blocks_the_share_factor(observations):
    ssi = _from(observations, "SSI")
    cash = next(o for o in ssi if o["event_type"] == "cash_dividend")
    assert (cash["ex_date"], cash["cash_amount_per_share"], cash["payment_date"]) == ("2026-08-17", 1000.0, "2026-09-14")
    bonus = next(o for o in ssi if o["event_type"] == "bonus_shares")
    assert bonus["stock_ratio"] == 0.2 and bonus["ex_date"] == "2026-08-17"
    # counterfactual: give the bonus leg an executed share-change identity
    bonus.update(shares_issued=500204581, shares_before=2503089220, shares_after=3003293801,
                 lifecycle_state="executed")
    entry = next(e for e in ledger.build_ledger(ssi)["entries"] if e["event_type"] == "bonus_shares")
    assert [leg["event_type"] for leg in entry["co_documented_legs"]] == ["cash_dividend"]
    classification, reasons = factor_chain.classify_ledger_entry(entry)
    assert classification == "OTHER_EVIDENCE_GAP"
    assert reasons == ["same_ex_date_leg_without_adjustment_policy:cash_dividend"]
    state = pit.classify_price_reconstruction(ticker="SSI", session="2026-08-14", knowledge_cutoff=HPG_RECEIPT_ERA_CUTOFF,
                                              mode=pit.MODE_PIT_AS_KNOWN, corporate_action_observations=[cash])
    assert state["corporate_action"]["reason"] == pit.REASON_CASH_DIVIDEND_NO_FACTOR_METHODOLOGY


def test_hose_vnd_price_cannot_join_another_scale_without_a_contract():
    with pytest.raises(RepresentationContractError):
        lookup_contract("HOSE", "tradingresult", "equity")


@requires_evidence
def test_empirical_price_ratio_is_never_the_official_factor(cohort):
    empirical = 24100 / 26350  # HOSE closes 22/05 -> 25/05/2026, research context only
    chain = _chain(cohort, "HPG")
    assert chain["adjustment_factor"] == round(1 / 1.1, 12) != round(empirical, 12)
    context = fitness.price_series_context(
        ticker="HPG", provider="HOSE", source_identity="hose:tradingresult", session_start="2026-05-04",
        session_end="2026-05-22", observed_basis=fitness.POINT_IN_TIME_ADJUSTED, basis_provenance=["test"],
        factor_chain=chain)
    verdict = fitness.evaluate_feature_fitness(feature=fitness.PIT_BACKTEST, current_context=context,
                                               decision_as_of="2026-05-22T15:00:00+07:00",
                                               observed_price_divergence_pct=(1 - empirical) * 100)
    assert verdict["numeric_divergence"]["authority_gate"] is False
    assert verdict["state"] == fitness.POINT_IN_TIME_SEMANTICS_UNQUALIFIED


@requires_evidence
def test_membership_coverage_and_t0_stay_unknown_even_with_a_qualified_chain(cohort):
    chain = _chain(cohort, "PVD")
    requirements = market_only.SignalRequirements("HOSE_CA_QUALIFICATION_REFUSAL", 5,
                                                  price_mode=market_only.PIT_CA_ADJUSTED)
    ca_row = {"ticker": "PVD", "exchange": None, "source_identity": chain["factor_chain_identity"],
              "knowledge_available_at": chain["knowledge_cutoff"], "window_start": "2026-07-01",
              "window_end": "2026-07-31", "state": "QUALIFIED_FACTOR_CHAIN", "factor_chain": [chain]}
    verdict = market_only.evaluate(requirements=requirements, ticker="PVD", session="2026-07-13",
                                   knowledge_cutoff="2026-07-13T15:00:00+07:00", market_versions=[],
                                   calendar_sessions=list(runner.GOVERNED_SESSIONS), ca_versions=[ca_row])
    assert verdict["state"] == "EXCLUDED"
    assert {"ACTIVE_UNIVERSE_UNKNOWN", "CA_FACTOR_REQUIRED_UNAVAILABLE", "KNOWLEDGE_CUTOFF_VIOLATION",
            "PRICE_NOT_PIT_ELIGIBLE", "LOOKBACK_WINDOW_INSUFFICIENT"} <= set(verdict["reason_codes"])
    artifact = json.loads(runner.OUTPUT.read_text(encoding="utf-8"))
    boundary = artifact["authority_boundary"]
    assert boundary["applicable_corporate_action_coverage"] == "UNKNOWN"
    assert boundary["event_free_interval_proven"] is False and boundary["active_universe"] == "UNKNOWN"
    assert boundary["historical_pit_eligible"] is False and boundary["authority_promotion"] is False


@requires_evidence
def test_pow_combined_listing_change_has_no_ex_date_and_no_factor(observations, built):
    (pow_observation,) = _from(observations, "POW")
    assert pow_observation["ex_date"] is None and pow_observation["event_type"] is None
    assert pow_observation["listing_effective_date"] == "2026-01-13" and pow_observation["trading_date"] == "2026-01-27"
    assert all(entry["ticker"] != "POW" for entry in built["entries"])


# --- determinism and compatibility -------------------------------------------------------

@requires_evidence
def test_ledger_replay_is_order_independent(observations):
    assert (ledger.build_ledger(observations)["replay_fingerprint"]
            == ledger.build_ledger(list(reversed(observations)))["replay_fingerprint"])


def test_legacy_observation_ledger_gains_no_new_fields():
    observation = {"observation_id": "o1", "document_id": "d1", "ticker": "HPG", "event_type": "stock_dividend",
                   "lifecycle_state": "executed", "shares_issued": 767498665, "shares_after": 8442964520,
                   "content_sha256": "a" * 64}
    entry = ledger.build_ledger([observation])["entries"][0]
    for field in ("shares_planned", "treasury_shares_before", "ratio_basis_corroboration",
                  "planned_count_bridge", "co_documented_legs", "ratio_source"):
        assert field not in entry


@requires_evidence
def test_no_governed_session_before_receipt_can_use_either_factor(cohort):
    """The downstream PIT gate, swept over every governed session close before Producer's receipt."""
    for ticker in ("HPG", "PVD"):
        chain = _chain(cohort, ticker)
        context = fitness.price_series_context(
            ticker=ticker, provider="HOSE", source_identity="hose:tradingresult", session_start="2026-06-03",
            session_end="2026-09-04", observed_basis=fitness.POINT_IN_TIME_ADJUSTED, basis_provenance=["test"],
            factor_chain=chain)
        decisions = [f"{session}T15:00:00+07:00" for session in runner.GOVERNED_SESSIONS]
        cutoff = datetime.fromisoformat(chain["knowledge_cutoff"].replace("Z", "+00:00"))
        decisions.append((cutoff - timedelta(seconds=1)).isoformat())
        for decision in decisions:
            verdict = fitness.evaluate_feature_fitness(feature=fitness.PIT_BACKTEST, current_context=context,
                                                       decision_as_of=decision)
            assert verdict["reason_codes"] == [fitness.REASON_PIT_FACTOR_AFTER_DECISION], (ticker, decision)


def test_token_match_refuses_a_value_inside_a_longer_number():
    from stocklookup_core.evidence.corporate_action_events import _token_on_page
    assert _token_on_page("10%", "Tỷ lệ thực hiện: 10% (Người")
    assert not _token_on_page("10%", "tỷ lệ 110%")
    assert not _token_on_page("1.000", "Mệnh giá 21.000 đồng")
    assert not _token_on_page("1.000", "1.000.000 đồng")
    assert _token_on_page("1.000", "được nhận 1.000 đồng)")
    assert not _token_on_page("767.546.585", "767.546.5850")


@pytest.mark.parametrize("printed,expected", [("10%", 0.1), ("66,9%", 0.669), ("100:10", 0.1), ("5:1", 0.2),
                                              ("10% hoặc 5:1", None), ("", None)])
def test_entitlement_ratio_parsing(printed, expected):
    assert parse_entitlement_ratio(printed) == expected
