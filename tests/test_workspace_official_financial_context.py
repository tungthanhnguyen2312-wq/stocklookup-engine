"""Admitted official exact fields reach the Workspace card unchanged, with their use limits."""
from stocklookup_core.decision import investment_decision_workspace_projection as ws
from stocklookup_core.valuation import current_valuation_opportunity_integration as integ

HPG_REVENUE = {
    "canonical_metric": "revenue", "statement_family": "income_statement", "reporting_period": "2025",
    "period_type": "annual", "period_start": "2025-01-01", "period_end": "2025-12-31",
    "normalized_value": 156116094618482, "currency": "VND", "statement_scope": "consolidated",
    "audit_or_review_status": "audited", "temporal_status": "HISTORICAL_OFFICIAL_FACT",
    "context_kind": "AUDITED_ANNUAL_FIELD", "allowed_projection_use": "EXACT_FIELD_CURRENT_RESEARCH_CONTEXT",
    "valuation_use": "NOT_PERMITTED_AUDITED_ANNUAL_CONTEXT", "ttm_derivation": "NOT_PERMITTED",
    "annualization": "NOT_PERMITTED", "factual_status": "qualified", "research_status": "qualified",
    "knowledge_available_at": "2026-10-07T15:33:12Z", "document_sha256": "f38c" * 16,
    "citation_id": "703f" * 16, "source_page": 10, "line_code": "10",
    "assurance_evidence": {"large": "not copied"}, "blockers": [],
}


def test_only_factually_qualified_rows_are_copied_with_use_limits():
    blocked = dict(HPG_REVENUE, factual_status="blocked", canonical_metric="net_income")
    record = {"financial_input": {"official_field_context": [blocked, HPG_REVENUE]}}
    [row] = integ.official_financial_context(record)
    assert row["normalized_value"] == 156116094618482
    assert row["valuation_use"] == "NOT_PERMITTED_AUDITED_ANNUAL_CONTEXT"
    assert row["ttm_derivation"] == row["annualization"] == "NOT_PERMITTED"
    assert set(row) == set(integ.OFFICIAL_FINANCIAL_CONTEXT_FIELDS)
    assert "assurance_evidence" not in row


def test_absent_or_empty_context_adds_nothing():
    assert integ.official_financial_context(None) == []
    assert integ.official_financial_context({"financial_input": {}}) == []
    view = ws._valuation_view({"valuation": {"applicable_methods": {}}})
    assert "official_financial_context" not in view


def test_workspace_valuation_view_passes_context_through_verbatim():
    context = integ.official_financial_context({"financial_input": {"official_field_context": [HPG_REVENUE]}})
    view = ws._valuation_view({"valuation": {"applicable_methods": {}, "official_financial_context": context}})
    assert view["official_financial_context"] == context
    # Never a valuation input: methods/readiness are untouched by the context.
    assert view["method_diagnostics"] == {} and view["usable_relative_method_count"] == 0
