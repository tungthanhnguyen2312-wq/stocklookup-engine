"""Replay the private compact consumer over a bound, contradictory pair of research lenses."""
import hashlib
import json

from tools import build_owner_compact_research as compact


def test_compact_replay_preserves_disagreeing_lenses_and_missing_posture(tmp_path):
    session = "2026-11-13"
    integrated_id = "integrated_investment_decision_product/v1:fixture"
    posture = {"ticker": "HPG", "research_action_posture": "WAIT_FOR_CONFIRMATION",
               "posture_condition_class": "PENDING_DEFINED_CONFIRMATION",
               "research_action_policy_version": "v2", "evidence_currency": "SAME_SESSION"}
    tactical = {"entry_action": "EARLY_ENTRY", "entry_state": "EARLY_REVERSAL_CANDIDATE",
                "horizon": "SHORT_TERM_FEW_SESSIONS", "is_actionable": False}
    card = {"current_decision_state": tactical, "trigger": {"level": 27},
            "invalidation": {"level": 24}, "valuation_context": {"status": "UNQUALIFIED"}}
    brief = {
        "session": session, "decision_surface_index": {"rows": [posture]},
        "watchlist": {"records": [{"ticker": "HPG", "trigger_level": 28,
                                  "invalidation_level": 23}]},
        "market_summary": {}, "coverage": {}, "risk_summary": {}, "authority_boundary": {},
        "sector_summary": {"sectors": [], "authority_boundary": {}},
        "opportunity_sets": {key: [] for key in ("top_current_opportunities", "top_early_setups",
                                                "highest_risk_names", "ordering_method", "set_counts")},
    }
    brief.update(compact.brief_identity(brief))
    product = {"session": session, "risk_data_gap_panel": {},
               "detailed_research_cards": {"HPG": card, "PAN": card}}
    product.update(compact.product_identity(product))
    run = {"market_session": session, "session_coherence": {"session": session},
           "outputs": {"daily_integrated_decision_brief": brief["artifact_identity"],
                       "daily_product": product["artifact_identity"],
                       "integrated_investment_decision_product": integrated_id},
           "warnings": []}
    run["operation_identity"] = compact.operation_identity(run)
    envelope = {"session": session, "daily_operation_identity": run["operation_identity"],
                "integrated_investment_decision_product_identity": integrated_id,
                "daily_integrated_decision_brief": brief}
    envelope.update(compact.brief_retention_identity(envelope))
    delivery = {"session": session, "operation_identity": run["operation_identity"],
                "integrated_investment_decision_product_identity": integrated_id,
                "daily_integrated_decision_brief_identity": brief["artifact_identity"],
                "source_artifact_identities": {},
                "files": {"ai_research_session_bundle.json": {"sha256": "manifest-claim"}}}
    inputs = {"run_manifest.json": run, "daily_integrated_decision_brief_artifact.json": envelope,
              "current_daily_decision_research_product_artifact.json": product,
              "ai_research_bundle_manifest.json": delivery}
    for name, value in inputs.items():
        (tmp_path / name).write_bytes(json.dumps(value).encode())

    result = compact.build(tmp_path, session, ["ZZZ", "PAN", "HPG"])
    hpg, pan, missing = (result["ticker_briefs"][ticker] for ticker in ("HPG", "PAN", "ZZZ"))
    assert result["is_actionable"] is False
    assert hpg["integrated_decision"] == posture
    assert hpg["entry_boundaries"] == {"trigger_level": 28, "invalidation_level": 23}
    assert hpg["research_card"]["current_decision_state"] == tactical
    assert hpg["research_card"]["trigger"] == card["trigger"]
    assert hpg["research_card"]["invalidation"] == card["invalidation"]
    assert hpg["valuation"]["valuation_context"] == {"status": "UNQUALIFIED"}
    sources = result["market_summary"]["sources"]
    for name in inputs:
        assert sources[name]["sha256"] == hashlib.sha256((tmp_path / name).read_bytes()).hexdigest()
    markdown = compact.render_ticker(session, hpg, None, sources)
    integrated_md, tactical_md = markdown.split("## Independent tactical research card", 1)
    assert "WAIT_FOR_CONFIRMATION" in integrated_md and "EARLY_ENTRY" not in integrated_md
    assert "EARLY_ENTRY" in tactical_md and "tactical classifier state" in tactical_md
    assert "current decision state" not in tactical_md
    assert pan["integrated_decision"] is None
    assert "does not supply a substitute" in pan["research_card"]["decision_scope"]
    assert not missing["research_card"] and not missing["availability"]["research_card"]
    assert result == compact.build(tmp_path, session, ["HPG", "PAN", "ZZZ"])
