"""Offline tests for the valuation-input gate. No network and no Producer write."""
from __future__ import annotations

import copy
import unittest
from decimal import Decimal

from stocklookup_core.evidence.investment_evidence_assembly import (
    assess_valuation_uses,
    cash_conversion,
    classify_price_for_monetary_valuation,
    classify_share_for_valuation,
    comparability,
    project_corporate_action,
    reject_par_division,
    scale_invariant_return,
)


def hpg_price():
    return {
        "status": "PRICE_READY",
        "session": "2026-10-13",
        "currency": "VND",
        "price_unit": "vnd_per_share",
        "native_price_scale_token": "SOURCE_PRICE_UNIT_UNDOCUMENTED",
        "raw_as_traded": "NOT_PROMOTED",
        "provider_native_value": "20.45",
        "value": 20450.0,
        "volume_unit": None,
        "price_representation": {
            "canonical_unit": "vnd_per_share",
            "canonical_value": "20450.00",
            "contract_basis_tier": "owner_directed_contractual_assumption",
            "contract_id": "DNSE:ohlc_1D:VN_LISTED_EQUITY:kvnd_to_vnd/v1",
            "provider_native_unit": "thousands_of_vnd_per_share",
            "provider_native_value": "20.45",
        },
    }


def hpg_share():
    return {
        "share_concept": "ISSUED_SHARES",
        "authority": "provider_reported_lagged",
        "authoritative_current_market_cap_eligible": False,
        "research_proxy_eligible": True,
        "value": 8442964520,
        "retained_evidence": {
            "unit": "shares",
            "official_anchor_not_promoted_because": "common_outstanding_share_semantics_not_proven",
            "official_anchor_effective_date": "2026-07-02",
            "official_anchor_value": 8442964520,
        },
    }


def documented_price():
    return {
        "session": "2026-10-13",
        "currency": "VND",
        "price_unit": "vnd_per_share",
        "native_price_scale_token": "DOCUMENTED_VND_PER_SHARE",
        "raw_as_traded": "QUALIFIED_RAW_AS_TRADED",
        "adjustment_basis": "UNADJUSTED_TRADE_PRICE",
        "volume_unit": "shares",
        "price_representation": {
            "canonical_unit": "vnd_per_share",
            "canonical_value": "25000",
            "contract_basis_tier": "documented_endpoint_unit",
            "provider_native_unit": "vnd_per_share",
            "provider_native_value": "25000",
        },
    }


def current_shares():
    return {
        "share_concept": "CURRENT_COMMON_SHARES_OUTSTANDING",
        "authority": "qualified_official",
        "authoritative_current_market_cap_eligible": True,
        "research_proxy_eligible": False,
        "continuity": "QUALIFIED",
        "value": 1000,
        "effective_date": "2026-10-01",
        "retained_evidence": {"unit": "shares"},
    }


class PriceAndShareTests(unittest.TestCase):
    def test_owner_directed_thousand_scale_is_not_a_vnd_price(self):
        state = classify_price_for_monetary_valuation(hpg_price())
        self.assertFalse(state["strict_price_eligible"])
        self.assertIsNone(state["monetary_vnd_per_share"])
        self.assertEqual("20450.00", state["research_vnd_per_share"])
        self.assertEqual("OWNER_ACCEPTED_VN_LISTED_EQUITY_THOUSAND_VND", state["research_unit_basis"])
        self.assertTrue(state["price_multiplied_by_one_thousand"])
        self.assertFalse(state["extra_scale_applied_by_gate"])
        self.assertFalse(state["source_unit_verified"])
        self.assertIn("OWNER_CONVENTION_NOT_ENDPOINT_DOCUMENTATION", state["reason_codes"])
        self.assertIn("SOURCE_PRICE_UNIT_UNDOCUMENTED", state["reason_codes"])

    def test_native_vnd_field_rejects_the_price_scale(self):
        price = documented_price()
        price["price_representation"]["provider_native_unit"] = "vnd"
        price["price_representation"]["provider_native_value"] = "1000"
        price["price_representation"]["canonical_value"] = "1000000"
        state = classify_price_for_monetary_valuation(price)
        self.assertIn("NATIVE_VND_FIELD_MUST_NOT_TAKE_PRICE_SCALE", state["reason_codes"])
        self.assertIsNone(state["monetary_vnd_per_share"])

    def test_eps_denominator_collision_overrides_research_proxy(self):
        state = classify_share_for_valuation(hpg_share(), eps_denominator_values=[8442964520], price_session="2026-10-13")
        self.assertIsNone(state["current_common_shares"])
        self.assertTrue(state["research_proxy_overridden"])
        self.assertIn("NUMERIC_COLLISION_WITH_EPS_DENOMINATOR", state["reason_codes"])
        self.assertIn("PROVIDER_SHARE_FIELD_IS_NOT_CURRENT_COMMON_AUTHORITY", state["reason_codes"])

    def test_charter_capital_par_division_does_not_create_shares(self):
        refused = reject_par_division(84429645200000, 10000, 8442964520)
        self.assertIsNone(refused["shares_created"])
        self.assertEqual(8442964520, refused["rejected_quotient"])
        self.assertIn("PAR_DIVISION_MATCHES_A_SHARE_FIELD_AND_STAYS_REJECTED", refused["reason_codes"])
        missing_par = reject_par_division(84429645200000, None, None)
        self.assertIsNone(missing_par["rejected_quotient"])
        self.assertIn("MISSING_PAR_IS_NOT_ASSUMED_AT_10000", missing_par["reason_codes"])

    def test_later_share_knowledge_cannot_backfill_the_price_cutoff(self):
        share = current_shares()
        share["knowledge_available_at"] = "2026-10-21"
        state = classify_share_for_valuation(share, price_session="2026-10-13", knowledge_cutoff="2026-10-13")
        self.assertIn("SHARE_KNOWLEDGE_AFTER_PRICE_CUTOFF", state["reason_codes"])
        self.assertIsNone(state["current_common_shares"])

    def test_planned_issuance_does_not_change_the_bar_or_the_share_count(self):
        action = project_corporate_action(
            {"lifecycle": "PLANNED", "event_type": "PRIVATE_PLACEMENT", "shares_planned": 550_000_000,
             "ex_date_qualified": False, "adjust_historical_ohlc": True},
            price_session="2026-10-22",
        )
        self.assertIsNone(action["shares_added"])
        self.assertIsNone(action["price_factor_applied"])
        self.assertFalse(action["historical_bar_adjusted"])
        self.assertIn("PLANNED_SHARES_ARE_NOT_OUTSTANDING", action["reason_codes"])
        self.assertIn("HISTORICAL_OHLC_ADJUSTMENT_REFUSED", action["reason_codes"])


class ValuationUseTests(unittest.TestCase):
    def test_hpg_shaped_research_usable_multiples_are_blocked(self):
        original_price = hpg_price()
        snapshot = copy.deepcopy(original_price)
        verdict = assess_valuation_uses(
            ticker="HPG", entity="corporate", price=original_price, share=hpg_share(),
            eps_denominator_values=[8442964520],
            earnings={"accounting_identity": "PARENT_PROFIT_AFTER_TAX", "normalized_integer": 15365022248705,
                      "reporting_period": "2026-H1", "period_semantic_state": "UNKNOWN_DURATION",
                      "statement_scope": "consolidated", "status": "CANDIDATE_ONLY"},
            prior_metric_status={"market_cap": "RESEARCH_USABLE", "P/E": "RESEARCH_USABLE", "P/B": "RESEARCH_USABLE", "P/S": "RESEARCH_USABLE"},
        )
        self.assertEqual(snapshot, original_price)
        self.assertEqual("BLOCKED_BY_EVIDENCE", verdict["uses"]["market_cap"]["status"])
        self.assertEqual("20450.00", verdict["price"]["research_vnd_per_share"])
        self.assertTrue(verdict["uses"]["P/E"]["prior_research_usable_now_blocked"])
        self.assertEqual("BLOCKED_BY_EVIDENCE", verdict["uses"]["P/B"]["status"])
        self.assertEqual("BLOCKED_BY_EVIDENCE", verdict["uses"]["P/S"]["status"])
        self.assertIsNone(verdict["rejected_arithmetic"])
        self.assertFalse(verdict["historical_basis_modified"])
        self.assertFalse(verdict["pit_backfill"])
        self.assertFalse(verdict["official_fact_admitted"])
        self.assertEqual("BLOCKED_BY_EVIDENCE", verdict["volume_traded_value"])

    def test_documented_price_and_current_shares_produce_a_market_cap_candidate_only(self):
        verdict = assess_valuation_uses(
            ticker="EX", entity="corporate", price=documented_price(), share=current_shares(),
            earnings={"accounting_identity": "PARENT_PROFIT_AFTER_TAX", "normalized_integer": 5000000,
                      "reporting_period": "FY2025", "period_semantic_state": "ANNUAL",
                      "statement_scope": "consolidated", "official_fact_admitted": False},
            book_equity={"accounting_identity": "PARENT_BOOK_EQUITY_PRINTED_NOT_DERIVED", "normalized_integer": 20000000},
            sales={"accounting_identity": "NET_REVENUE", "normalized_integer": 8000000,
                   "period_semantic_state": "ANNUAL", "reporting_period": "FY2025"},
        )
        self.assertEqual("RESEARCH_CANDIDATE_NOT_ADMITTED", verdict["uses"]["market_cap"]["status"])
        self.assertEqual("25000000", verdict["uses"]["market_cap"]["value"])
        self.assertEqual("5", verdict["uses"]["P/E"]["value"])
        self.assertEqual("1.25", verdict["uses"]["P/B"]["value"])
        self.assertEqual("3.125", verdict["uses"]["P/S"]["value"])
        self.assertEqual("CLOSED", verdict["valuation_use"])
        self.assertFalse(verdict["uses"]["P/E"]["is_actionable"])
        self.assertIsNone(verdict["uses"]["P/E"]["target_price"])

    def test_interim_parent_profit_does_not_become_a_ttm_pe(self):
        verdict = assess_valuation_uses(
            ticker="EX", entity="corporate", price=documented_price(), share=current_shares(),
            earnings={"accounting_identity": "PARENT_PROFIT_AFTER_TAX", "normalized_integer": 5000000,
                      "reporting_period": "2026-H1", "period_semantic_state": "UNKNOWN_DURATION",
                      "statement_scope": "consolidated"},
        )
        self.assertEqual("RESEARCH_CANDIDATE_NOT_ADMITTED", verdict["uses"]["market_cap"]["status"])
        self.assertEqual("BLOCKED_BY_EVIDENCE", verdict["uses"]["P/E"]["status"])
        self.assertIn("NO_TTM_FROM_UNPROVEN_OR_INTERIM_PERIOD", verdict["uses"]["P/E"]["reason_codes"])

    def test_total_equity_does_not_support_pb(self):
        verdict = assess_valuation_uses(
            ticker="EX", entity="corporate", price=documented_price(), share=current_shares(),
            book_equity={"accounting_identity": "TOTAL_EQUITY_INCLUDING_NCI", "normalized_integer": 20000000},
        )
        self.assertEqual("BLOCKED_BY_EVIDENCE", verdict["uses"]["P/B"]["status"])
        self.assertIn("TOTAL_OR_UNLABELED_EQUITY_IS_NOT_PARENT_BOOK", verdict["uses"]["P/B"]["reason_codes"])

    def test_press_highlight_cannot_support_pe(self):
        verdict = assess_valuation_uses(
            ticker="FPT", entity="corporate", price=documented_price(), share=current_shares(),
            earnings={"status": "RECORDED_PRESS_HIGHLIGHT_NOT_A_STATEMENT", "fact_origin": "PRESS_HIGHLIGHT",
                      "accounting_identity": "PARENT_PROFIT_AFTER_TAX", "normalized_integer": 7778000000000,
                      "reporting_period": "2026-9M", "period_semantic_state": "YTD_CUMULATIVE_INTERIM",
                      "statement_scope": "UNKNOWN"},
        )
        self.assertEqual("BLOCKED_BY_EVIDENCE", verdict["uses"]["P/E"]["status"])
        self.assertIn("PRESS_RELEASE_IS_NOT_A_STATEMENT", verdict["uses"]["P/E"]["reason_codes"])
        self.assertIn("STATEMENT_SCOPE_NOT_EXPLICIT", verdict["uses"]["P/E"]["reason_codes"])

    def test_bank_ev_ebitda_is_not_comparable_with_an_industrial_company(self):
        industrial = assess_valuation_uses(ticker="HPG", entity="corporate", price=hpg_price(), share=hpg_share())
        bank = assess_valuation_uses(ticker="ACB", entity="bank", price=hpg_price(), share=hpg_share())
        industrial["reporting_period_class"] = "UNPROVEN"
        bank["reporting_period_class"] = "UNPROVEN"
        compared = comparability(industrial, bank, "EV/EBITDA")
        self.assertEqual("NOT_COMPARABLE", compared["status"])
        self.assertFalse(compared["ranking_produced"])
        self.assertIn("SECTOR_SPECIALIST_METHOD_NOT_APPLICABLE", compared["reason_codes"])

    def test_same_native_series_return_stays_available_without_a_vnd_unit(self):
        result = scale_invariant_return("21.25", "21.35", same_representation=True)
        self.assertEqual("SCALE_INVARIANT_RETURN_ALLOWED", result["status"])
        self.assertIsNone(result["monetary_market_cap"])
        self.assertEqual(format(Decimal("21.35") / Decimal("21.25") - Decimal(1), "f"), result["return"])
        refused = scale_invariant_return("21.25", "21350", same_representation=False)
        self.assertEqual("BLOCKED_BY_EVIDENCE", refused["status"])


class CashQualityTests(unittest.TestCase):
    def test_visual_same_document_pair_is_a_ratio_and_not_an_admission(self):
        common = {
            "ticker": "HPG", "statement_scope": "consolidated", "reporting_period": "2026-H1",
            "currency": "VND", "unit_scale": 1, "period_semantic_state": "UNKNOWN_DURATION",
            "document_sha256": "009c0c4054d1fc28fb853040045f6a1bfb153321d664cf4b5c7c88147c3056fb",
            "origin": "REAL_GROK_VISUAL_PAGE_REVIEW_CANDIDATE_NOT_OFFICIAL_ADMISSION",
        }
        result = cash_conversion(
            {**common, "accounting_identity": "PARENT_PROFIT_AFTER_TAX", "normalized_integer": 15365022248705},
            {**common, "accounting_identity": "OPERATING_CASH_FLOW", "normalized_integer": 12641697117285},
        )
        self.assertEqual("VISUAL_REVIEW_RATIO_NOT_ADMITTED", result["status"])
        self.assertEqual(format(Decimal(12641697117285) / Decimal(15365022248705), "f"), result["ratio"])
        self.assertFalse(result["ttm_constructed"])
        self.assertFalse(result["official_fact_admitted"])
        self.assertEqual("CLOSED", result["valuation_use"])
        self.assertIn("DURATION_UNPROVEN_NO_ANNUALIZATION", result["reason_codes"])
        self.assertEqual(
            "CONSOLIDATED_OPERATING_CASH_FLOW_OVER_PARENT_ATTRIBUTABLE_PROFIT",
            result["scope_warning"],
        )

    def test_press_and_depreciation_line_do_not_create_cash_quality(self):
        profit = {"ticker": "FPT", "status": "RECORDED_PRESS_HIGHLIGHT_NOT_A_STATEMENT",
                  "accounting_identity": "PARENT_PROFIT_AFTER_TAX", "normalized_integer": 100, "statement_scope": "UNKNOWN"}
        cash = {"ticker": "FPT", "accounting_identity": "COMPOSITE_CASH_FLOW_DEPRECIATION_ADJUSTMENT",
                "normalized_integer": 40, "statement_scope": "UNKNOWN"}
        result = cash_conversion(profit, cash)
        self.assertEqual("BLOCKED_BY_EVIDENCE", result["status"])
        self.assertIsNone(result["ratio"])
        self.assertIn("PRESS_RELEASE_IS_NOT_A_STATEMENT", result["reason_codes"])
        self.assertIn("DEPRECIATION_ADJUSTMENT_IS_NOT_EBITDA", result["reason_codes"])


if __name__ == "__main__":
    unittest.main()
