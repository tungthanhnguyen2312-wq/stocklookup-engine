"""Economic profile tests. Strict authority stays closed while research figures remain."""
from __future__ import annotations

import unittest
from decimal import Decimal

from stocklookup_core.valuation.conditional_research_valuation import (
    filing_share_basis,
    industrial_research_profile,
    parse_reported_integer,
    scope_and_period_bridge,
    specialist_research_guard,
)

QUOTE = (
    "Decision No. 560/QD-SGDHCM dated 01 July 2026 approved the change in listing registration "
    "in respect of 767,498,665 shares issued for dividend payment, effective date of the listing "
    "change 02 July 2026. Notice No. 1475/TB-SGDHCM dated 06 July 2026: those shares were "
    "officially traded from 15 July 2026."
)


def price():
    return {
        "session": "2026-10-13",
        "instrument_class": "VN_LISTED_EQUITY",
        "capability_id": "ohlc_1D",
        "native_price_scale_token": "SOURCE_PRICE_UNIT_UNDOCUMENTED",
        "raw_as_traded": "NOT_PROMOTED",
        "price_representation": {
            "canonical_unit": "vnd_per_share",
            "canonical_value": "20450.00",
            "contract_basis_tier": "owner_directed_contractual_assumption",
            "provider_native_unit": "thousands_of_vnd_per_share",
            "provider_native_value": "20.45",
        },
    }


def components():
    return {
        "opening_ordinary_shares": 7_675_465_855,
        "stock_dividend_shares": 767_498_665,
        "eps_denominator_shares": 8_442_964_520,
        "june_contributed_capital_vnd": 76_754_658_550_000,
        "subsequent_charter_capital_vnd": 84_429_645_200_000,
        "listing_quote": QUOTE,
    }


def line(identity, value, period="2026-H1"):
    return {
        "ticker": "HPG", "accounting_identity": identity, "normalized_integer": value,
        "statement_scope": "consolidated", "reporting_period": period, "currency": "VND",
        "unit_scale": 1, "period_semantic_state": "UNKNOWN_DURATION",
        "document_sha256": "abc", "origin": "REAL_GROK_VISUAL_PAGE_REVIEW_CANDIDATE_NOT_OFFICIAL_ADMISSION",
    }


class ResearchProfileTests(unittest.TestCase):
    def test_hpg_shaped_profile_has_a_conditional_cap_and_interim_multiples(self):
        facts = {
            "GROSS_REVENUE": line("GROSS_REVENUE", 110),
            "REVENUE_DEDUCTIONS": line("REVENUE_DEDUCTIONS", 10),
            "NET_REVENUE": line("NET_REVENUE", 100),
            "TOTAL_PROFIT_AFTER_TAX": line("TOTAL_PROFIT_AFTER_TAX", 15),
            "PARENT_PROFIT_AFTER_TAX": line("PARENT_PROFIT_AFTER_TAX", 12),
            "NCI_PROFIT_AFTER_TAX": line("NCI_PROFIT_AFTER_TAX", 3),
            "TOTAL_EQUITY_INCLUDING_NCI": line("TOTAL_EQUITY_INCLUDING_NCI", 40, period="2026-06-30"),
            "OPERATING_CASH_FLOW": line("OPERATING_CASH_FLOW", 9),
        }
        profile = industrial_research_profile(
            ticker="HPG", price=price(), share_components=components(), facts=facts, provider_share=8_442_964_520,
        )
        self.assertEqual("20450.00", profile["price"]["research_vnd_per_share"])
        self.assertFalse(profile["price"]["source_unit_verified"])
        self.assertFalse(profile["strict_decision_eligible"])
        self.assertEqual(8_442_964_520, profile["share_basis"]["research_shares"])
        self.assertEqual(1, profile["share_basis"]["independent_source_count"])
        self.assertFalse(profile["share_basis"]["provider_share_is_independent"])
        cap = Decimal("20450.00") * Decimal(8_442_964_520)
        self.assertEqual(format(cap, "f"), profile["market_cap_vnd"])
        self.assertEqual("CONDITIONAL_RESEARCH_ESTIMATE", profile["multiples"]["market_cap"]["eligibility"])
        interim = profile["multiples"]["price_over_reported_interim_parent_profit"]
        self.assertEqual("CONDITIONAL_RESEARCH_ESTIMATE", interim["eligibility"])
        self.assertEqual(format(cap / Decimal(12), "f"), interim["value"])
        self.assertIn("H1_OR_INTERIM_COLUMN_IS_NOT_A_TTM_PE", interim["limits"])
        self.assertEqual("UNUSABLE", profile["multiples"]["pe_ttm"]["eligibility"])
        self.assertIsNone(profile["multiples"]["pe_ttm"]["value"])
        self.assertEqual("UNUSABLE", profile["multiples"]["pb_parent"]["eligibility"])
        self.assertEqual("CONDITIONAL_RESEARCH_ESTIMATE", profile["multiples"]["price_over_total_equity_including_nci"]["eligibility"])
        self.assertEqual("UNUSABLE", profile["multiples"]["ev_ebitda"]["eligibility"])
        self.assertEqual("UNUSABLE", profile["incompatible_pre_dividend_market_cap"]["eligibility"])
        pre = Decimal("20450.00") * Decimal(7_675_465_855)
        self.assertEqual(format(pre, "f"), profile["incompatible_pre_dividend_market_cap"]["value_vnd"])
        self.assertNotEqual(profile["market_cap_vnd"], profile["incompatible_pre_dividend_market_cap"]["value_vnd"])
        self.assertEqual("VISUAL_REVIEW_RATIO_NOT_ADMITTED", profile["cash_conversion"]["status"])
        self.assertFalse(profile["execution_eligible"])
        self.assertFalse(profile["historical_basis_modified"])

    def test_matching_arithmetic_across_different_columns_cannot_support_a_multiple(self):
        facts = {
            "TOTAL_PROFIT_AFTER_TAX": line("TOTAL_PROFIT_AFTER_TAX", 15),
            "PARENT_PROFIT_AFTER_TAX": line("PARENT_PROFIT_AFTER_TAX", 12),
            "NCI_PROFIT_AFTER_TAX": line("NCI_PROFIT_AFTER_TAX", 3, period="2026-Q2"),
            "TOTAL_EQUITY_INCLUDING_NCI": {
                **line("TOTAL_EQUITY_INCLUDING_NCI", 40), "currency": "USD",
            },
        }
        profile = industrial_research_profile(
            ticker="HPG", price=price(), share_components=components(), facts=facts,
        )
        assert profile["market_cap_vnd"] is not None
        multiples = profile["multiples"]
        assert multiples["price_over_reported_interim_parent_profit"]["value"] is None
        assert multiples["price_over_total_equity_including_nci"]["value"] is None

    def test_share_basis_fails_closed_when_the_filing_does_not_foot(self):
        broken = components()
        broken["eps_denominator_shares"] = 8_442_964_521
        basis = filing_share_basis(broken, price_session="2026-10-13")
        self.assertIsNone(basis["research_shares"])
        self.assertEqual("UNUSABLE", basis["eligibility"])

    def test_price_before_the_quoted_trade_date_does_not_use_the_new_count(self):
        basis = filing_share_basis(components(), price_session="2026-07-01")
        self.assertIsNone(basis["research_shares"])
        self.assertIn("PRICE_SESSION_BEFORE_QUOTED_TRADE_DATE", basis["reason_codes"])

    def test_reported_integer_scale_and_negatives(self):
        self.assertEqual(-1234, parse_reported_integer("(1,234)")["value"])
        self.assertEqual(5_000_000_000, parse_reported_integer("5.000", unit_scale=1_000_000)["value"])
        self.assertIsNone(parse_reported_integer("12.8%")["value"])
        self.assertIsNone(parse_reported_integer("10", unit_scale=100)["value"])

    def test_bank_ev_ebitda_stays_unusable_and_parent_profit_remains_the_research_line(self):
        guard = specialist_research_guard("bank", "EV/EBITDA")
        self.assertEqual("UNUSABLE", guard["eligibility"])
        self.assertEqual("PARENT_PROFIT_AFTER_TAX", guard["replacement_research_line"])
        self.assertEqual("CONDITIONAL_RESEARCH_ESTIMATE", specialist_research_guard("corporate", "P/E")["eligibility"])

    def test_quarter_is_not_added_to_the_nine_month_column(self):
        bridge = scope_and_period_bridge([
            {"scope": "consolidated", "period": "2026-Q3", "identity": "PARENT_PROFIT_AFTER_TAX", "normalized_integer": 10},
            {"scope": "consolidated", "period": "2026-Q3", "identity": "TOTAL_PROFIT_AFTER_TAX", "normalized_integer": 12},
            {"scope": "consolidated", "period": "2026-Q3", "identity": "NCI_PROFIT_AFTER_TAX", "normalized_integer": 2},
            {"scope": "separate", "period": "2026-Q3", "identity": "PROFIT_AFTER_TAX", "normalized_integer": 7},
            {"scope": "consolidated", "period": "2026-9M", "identity": "PARENT_PROFIT_AFTER_TAX", "normalized_integer": 30},
        ])
        names = {item["name"]: item for item in bridge["findings"]}
        self.assertFalse(names["CONSOLIDATED_PARENT_VERSUS_SEPARATE_PROFIT"]["same_number"])
        self.assertIsNone(names["QUARTER_IS_NOT_YEAR_TO_DATE"]["quarter_plus_nine_month"])
        self.assertEqual(0, names["Q3_TOTAL_EQUALS_PARENT_PLUS_NCI"]["residual"])
        self.assertIsNone(bridge["market_cap"])


if __name__ == "__main__":
    unittest.main()
