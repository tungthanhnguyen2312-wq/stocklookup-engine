import unittest

from stocklookup_core.decision import indicator_metric_availability as availability
from stocklookup_core.decision import indicator_metric_display_state as display


def method(state, status, value=None, codes=()):
    return {"availability_state": state, "status": status, "value": value, "blocker_reason_codes": list(codes)}


def card(methods, entity_class="corporate"):
    return {"ticker": "HPG", "as_of_session": "2026-11-05",
            "valuation": {"entity_class": entity_class, "method_diagnostics": methods}}


BLOCKED = method("NOT_AVAILABLE", "INPUT_BLOCKED", codes=["X"])


class ValuationDisplayResearchUsableTest(unittest.TestCase):
    def show(self, methods, entity_class="corporate"):
        return display.build_ticker_display_metrics("HPG", card(methods, entity_class), cohort_tickers=frozenset())

    def test_available_qualified_is_ready(self):
        self.assertEqual(availability._status_to_state("AVAILABLE_QUALIFIED"), "READY")
        out = self.show({"EV/Sales": method("AVAILABLE_QUALIFIED", "RESEARCH_USABLE", 1.855)})
        self.assertEqual(out["ev_sales"], {"display_state": "AVAILABLE", "value": 1.855})

    def test_pb_primary_wins_without_proxy_label(self):
        out = self.show({"P/B": method("AVAILABLE_QUALIFIED", "RESEARCH_USABLE", 1.58),
                         "P/B_CURRENT_RESEARCH": method("AVAILABLE_QUALIFIED", "RESEARCH_USABLE", 1.30)})
        self.assertEqual(out["pb"], {"display_state": "AVAILABLE", "value": 1.58})

    def test_pb_falls_back_to_current_research_with_label(self):
        out = self.show({"P/B": BLOCKED,
                         "P/B_CURRENT_RESEARCH": method("AVAILABLE_REFERENCE_ONLY", "RESEARCH_USABLE", 0.447)})
        self.assertEqual(out["pb"], {"display_state": "AVAILABLE", "value": 0.447, "basis": "RESEARCH_PROXY"})

    def test_both_blocked_stays_insufficient(self):
        out = self.show({"P/B": BLOCKED, "P/B_CURRENT_RESEARCH": BLOCKED})
        self.assertEqual(out["pb"], {"display_state": "INSUFFICIENT_DATA", "value": None})

    def test_not_applicable_primary_is_not_overridden(self):
        out = self.show({"P/B": method("NOT_AVAILABLE", "NOT_APPLICABLE"),
                         "P/B_CURRENT_RESEARCH": method("AVAILABLE_QUALIFIED", "RESEARCH_USABLE", 0.9)})
        self.assertEqual(out["pb"]["display_state"], "NOT_APPLICABLE")
        self.assertNotIn("basis", out["pb"])

    def test_unmapped_status_still_fails_closed(self):
        self.assertEqual(availability._status_to_state("SOME_NEW_UNMAPPED_STATUS"), "INSUFFICIENT_DATA")


if __name__ == "__main__":
    unittest.main()
