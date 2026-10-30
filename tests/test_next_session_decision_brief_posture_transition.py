"""Focused, fixture-only tests for next_session_decision_brief/v2's additive posture_transition
section -- no real retained evidence required (unlike tests/test_next_session_decision_brief.py's
real-replay class, which stays skipped outside the primary checkout)."""
from __future__ import annotations

import json
from pathlib import Path

import next_session_decision_brief as nsdb


def _rec(posture: str, phase: str = "TREND_CONTINUATION") -> dict:
    return {"research_action_posture": posture, "tactical_phase": phase, "decision_identity": f"decision:X:{posture}:{phase}"}


class TestClassifyPostureTransition:
    def test_no_longer_available(self):
        assert nsdb._classify_posture_transition(_rec("HOLD"), None) == "NO_LONGER_AVAILABLE"

    def test_newly_available(self):
        assert nsdb._classify_posture_transition(None, _rec("EARLY_WATCH")) == "NEWLY_AVAILABLE"

    def test_posture_unchanged(self):
        assert nsdb._classify_posture_transition(_rec("HOLD"), _rec("HOLD")) == "POSTURE_UNCHANGED"

    def test_wait_to_initiate(self):
        assert nsdb._classify_posture_transition(_rec("WAIT_FOR_CONFIRMATION"), _rec("INITIATE_ON_BREAKOUT")) == "WAIT_TO_INITIATE"

    def test_early_watch_to_initiate(self):
        assert nsdb._classify_posture_transition(_rec("EARLY_WATCH"), _rec("INITIATE_ON_BREAKOUT")) == "EARLY_WATCH_TO_INITIATE"

    def test_generic_new_breakout_from_uncovered_origin(self):
        assert nsdb._classify_posture_transition(_rec("ACCUMULATE_ON_RETEST"), _rec("INITIATE_ON_BREAKOUT")) == "NEW_BREAKOUT"

    def test_new_early_watch(self):
        assert nsdb._classify_posture_transition(_rec("WAIT_FOR_CONFIRMATION"), _rec("EARLY_WATCH")) == "NEW_EARLY_WATCH"

    def test_new_retest_candidate(self):
        assert nsdb._classify_posture_transition(_rec("EARLY_WATCH"), _rec("ACCUMULATE_ON_RETEST")) == "NEW_RETEST_CANDIDATE"

    def test_initiate_to_hold(self):
        assert nsdb._classify_posture_transition(_rec("INITIATE_ON_BREAKOUT"), _rec("HOLD")) == "INITIATE_TO_HOLD"

    def test_initiate_to_extended(self):
        assert nsdb._classify_posture_transition(_rec("INITIATE_ON_BREAKOUT"), _rec("HOLD_DO_NOT_ADD")) == "INITIATE_TO_EXTENDED"

    def test_breakout_failed(self):
        assert nsdb._classify_posture_transition(_rec("INITIATE_ON_BREAKOUT"), _rec("WAIT_FOR_CONFIRMATION")) == "BREAKOUT_FAILED"
        assert nsdb._classify_posture_transition(_rec("INITIATE_ON_BREAKOUT"), _rec("AVOID")) == "BREAKOUT_FAILED"

    def test_avoid_to_recovery_watch(self):
        assert nsdb._classify_posture_transition(_rec("AVOID"), _rec("EARLY_WATCH")) == "AVOID_TO_RECOVERY_WATCH"

    def test_uptrend_to_breakdown_checked_before_posture_pair_rules(self):
        prev = _rec("HOLD", phase="TREND_CONTINUATION")
        curr = _rec("AVOID", phase="BREAKDOWN")
        assert nsdb._classify_posture_transition(prev, curr) == "UPTREND_TO_BREAKDOWN"

    def test_posture_changed_other_fallback(self):
        assert nsdb._classify_posture_transition(_rec("HOLD"), _rec("HOLD_DO_NOT_ADD")) == "POSTURE_CHANGED_OTHER"

    def test_every_label_is_in_the_documented_vocabulary(self):
        pairs = [
            (None, _rec("HOLD")), (_rec("HOLD"), None), (_rec("HOLD"), _rec("HOLD")),
            (_rec("WAIT_FOR_CONFIRMATION"), _rec("INITIATE_ON_BREAKOUT")), (_rec("EARLY_WATCH"), _rec("INITIATE_ON_BREAKOUT")),
            (_rec("INITIATE_ON_BREAKOUT"), _rec("HOLD")), (_rec("INITIATE_ON_BREAKOUT"), _rec("HOLD_DO_NOT_ADD")),
            (_rec("INITIATE_ON_BREAKOUT"), _rec("REDUCE")), (_rec("AVOID"), _rec("WAIT_FOR_CONFIRMATION")),
            (_rec("HOLD"), _rec("REDUCE")),
        ]
        for prev, curr in pairs:
            assert nsdb._classify_posture_transition(prev, curr) in nsdb.POSTURE_TRANSITION_LABELS


class TestResolveIntegratedDecisionArtifact:
    def test_returns_none_when_session_absent(self, tmp_path):
        assert nsdb._resolve_integrated_decision_artifact(tmp_path, None) is None

    def test_returns_none_when_file_missing(self, tmp_path):
        assert nsdb._resolve_integrated_decision_artifact(tmp_path, "2026-08-28") is None

    def test_fails_closed_on_session_mismatch(self, tmp_path):
        import daily_session_level2_package as level2
        path = level2.session_artifact_paths(tmp_path, "2026-08-28")["integrated_investment_decision_product"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"session": "2026-08-27", "records": {}}), encoding="utf-8")
        try:
            nsdb._resolve_integrated_decision_artifact(tmp_path, "2026-08-28")
            assert False, "expected NextSessionDecisionBriefError"
        except nsdb.NextSessionDecisionBriefError as exc:
            assert "INTEGRATED_DECISION_ARTIFACT_SESSION_MISMATCH" in str(exc)

    def test_loads_matching_session_artifact(self, tmp_path):
        import daily_session_level2_package as level2
        path = level2.session_artifact_paths(tmp_path, "2026-08-28")["integrated_investment_decision_product"]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"session": "2026-08-28", "records": {"HPG": {}}}), encoding="utf-8")
        loaded = nsdb._resolve_integrated_decision_artifact(tmp_path, "2026-08-28")
        assert loaded["records"] == {"HPG": {}}


class TestPostureTransitionSection:
    def test_no_current_artifact_is_unavailable(self, tmp_path):
        section = nsdb._posture_transition(root=tmp_path, current_session="2026-08-28", previous_session="2026-08-27")
        assert section["availability"] == "UNAVAILABLE"
        assert "CURRENT_INTEGRATED_DECISION_ARTIFACT_NOT_MATERIALIZED" in section["reason_codes"]

    def test_full_pair_produces_records_and_counts(self, tmp_path):
        import daily_session_level2_package as level2
        prev_path = level2.session_artifact_paths(tmp_path, "2026-08-27")["integrated_investment_decision_product"]
        curr_path = level2.session_artifact_paths(tmp_path, "2026-08-28")["integrated_investment_decision_product"]
        prev_path.parent.mkdir(parents=True, exist_ok=True)
        curr_path.parent.mkdir(parents=True, exist_ok=True)
        prev_path.write_text(json.dumps({"session": "2026-08-27", "artifact_identity": "prev:x", "records": {"HPG": _rec("EARLY_WATCH")}}), encoding="utf-8")
        curr_path.write_text(json.dumps({"session": "2026-08-28", "artifact_identity": "curr:x", "records": {"HPG": _rec("INITIATE_ON_BREAKOUT")}}), encoding="utf-8")
        section = nsdb._posture_transition(root=tmp_path, current_session="2026-08-28", previous_session="2026-08-27")
        assert section["availability"] == "AVAILABLE"
        assert section["records"]["HPG"]["transition"] == "EARLY_WATCH_TO_INITIATE"
        assert section["transition_counts"] == {"EARLY_WATCH_TO_INITIATE": 1}


def _write_artifact(root, session, artifact, *, pretty=False):
    import daily_session_level2_package as level2
    path = level2.session_artifact_paths(root, session)["integrated_investment_decision_product"]
    path.parent.mkdir(parents=True, exist_ok=True)
    if pretty:
        path.write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    else:
        path.write_text(json.dumps(artifact), encoding="utf-8")
    return path


class TestCompactPostureProjection:
    def test_sorted_digest_matches_and_unsorted_digest_is_not_required(self, tmp_path):
        from stocklookup_core.decision.integrated_investment_decision_product import content_identity
        artifact = {
            "session": "2026-08-28",
            "contract_version": "integrated_investment_decision_product/v1",
            "requested_at": "2026-08-28T15:00:00+07:00",
            "research_action_policy_version": "v2",
            "records": {"HPG": {"research_action_posture": "HOLD", "tactical_phase": "TREND_CONTINUATION",
                                "fundamental_state": "STABLE", "fundamental_synthesis": {"signal_policy": "fundamental_signal_consumption/v1", "unused": "x"},
                                "decision_identity": "decision:HPG"}},
        }
        artifact.update(content_identity(artifact))
        path = _write_artifact(tmp_path, "2026-08-28", artifact, pretty=True)
        loaded = nsdb._stream_compact_integrated(path, session="2026-08-28")
        assert loaded["artifact_identity"] == artifact["artifact_identity"]
        assert loaded["records"]["HPG"]["fundamental_synthesis"] == {"signal_policy": "fundamental_signal_consumption/v1"}
        assert "unused" not in loaded["records"]["HPG"]["fundamental_synthesis"]
        artifact["artifact_sha256"] = "0" * 64
        artifact["artifact_identity"] = "integrated_investment_decision_product/v1:" + artifact["artifact_sha256"]
        path.write_text(json.dumps(artifact), encoding="utf-8")
        unsorted = nsdb._stream_compact_integrated(path, session="2026-08-28")
        assert unsorted["records"]["HPG"]["research_action_posture"] == "HOLD"
        path.write_text(json.dumps(artifact, sort_keys=True), encoding="utf-8")
        try:
            nsdb._stream_compact_integrated(path, session="2026-08-28")
            assert False, "sorted digest mismatch must fail closed"
        except nsdb.NextSessionDecisionBriefError as exc:
            assert "IDENTITY_MISMATCH" in str(exc)

    def test_resident_current_skips_full_read_and_streams_previous(self, tmp_path, monkeypatch):
        import daily_session_level2_package as level2
        previous = {"session": "2026-08-27", "artifact_identity": "prev:x", "records": {"HPG": _rec("EARLY_WATCH"), "AAA": _rec("HOLD")}}
        current = {"session": "2026-08-28", "contract_version": "integrated_investment_decision_product/v1",
                   "artifact_identity": "curr:x", "artifact_sha256": "abc",
                   "records": {"HPG": {**_rec("INITIATE_ON_BREAKOUT"), "narrative": "not-compared"}}}
        _write_artifact(tmp_path, "2026-08-27", previous)
        current_path = _write_artifact(tmp_path, "2026-08-28", current, pretty=True)
        current_path.write_bytes(current_path.read_bytes() + b" " * (8 * 1024 * 1024))
        original = Path.read_text
        def refuse_large(self, *args, **kwargs):
            if self == current_path:
                raise AssertionError("resident current artifact was fully read")
            return original(self, *args, **kwargs)
        monkeypatch.setattr(Path, "read_text", refuse_large)
        section = nsdb._posture_transition(root=tmp_path, current_session="2026-08-28", previous_session="2026-08-27", current_integrated=current)
        assert section["availability"] == "AVAILABLE"
        assert section["records"]["HPG"]["transition"] == "EARLY_WATCH_TO_INITIATE"
        assert section["records"]["AAA"]["transition"] == "NO_LONGER_AVAILABLE"
        assert section["source_lineage"] == {
            "previous_integrated_decision_identity": "prev:x",
            "current_integrated_decision_identity": "curr:x",
        }
        assert "narrative" not in section["records"]["HPG"]

    def test_large_file_without_window_session_fails_closed(self, tmp_path):
        current = {"session": "2026-08-28", "contract_version": "integrated_investment_decision_product/v1",
                   "artifact_identity": "curr:x", "records": {"HPG": _rec("HOLD")}}
        path = _write_artifact(tmp_path, "2026-08-28", current, pretty=True)
        text = path.read_text(encoding="utf-8")
        stripped = "\n".join(line for line in text.splitlines() if '"session"' not in line)
        path.write_text(stripped + ("x" * (8 * 1024 * 1024)), encoding="utf-8")
        try:
            nsdb._posture_transition(root=tmp_path, current_session="2026-08-28", previous_session=None, current_integrated=current)
            assert False, "missing window session must not fall back to a full parse"
        except nsdb.NextSessionDecisionBriefError as exc:
            assert "BINDING_UNVERIFIED" in str(exc)

    def test_absent_policy_keys_keep_artifact_fallback(self, tmp_path):
        previous = {"session": "2026-08-27", "artifact_identity": "prev:x", "records": {"HPG": {"research_action_posture": "HOLD", "tactical_phase": "BASE_BUILDING"}}}
        current = {"session": "2026-08-28", "artifact_identity": "curr:x", "research_action_policy_version": "v2",
                   "records": {"HPG": {"research_action_posture": "HOLD", "tactical_phase": "BASE_BUILDING", "research_action_policy_version": "v2"}}}
        _write_artifact(tmp_path, "2026-08-27", previous)
        _write_artifact(tmp_path, "2026-08-28", current)
        section = nsdb._posture_transition(root=tmp_path, current_session="2026-08-28", previous_session="2026-08-27")
        assert section["records"]["HPG"]["transition"] == "NOT_COMPARABLE_POLICY_CHANGE"
        assert section["records"]["HPG"]["previous_research_policy_epoch"] == "v1"
        assert section["records"]["HPG"]["current_research_policy_epoch"] == "v2"

    def test_large_previous_is_streamed_and_not_refused(self, tmp_path):
        previous = {"session": "2026-08-27", "artifact_identity": "prev:x", "records": {"HPG": _rec("EARLY_WATCH")}}
        current = {"session": "2026-08-28", "contract_version": "integrated_investment_decision_product/v1",
                   "artifact_identity": "curr:x", "records": {"HPG": _rec("INITIATE_ON_BREAKOUT")}}
        previous_path = _write_artifact(tmp_path, "2026-08-27", previous)
        previous_path.write_bytes(previous_path.read_bytes() + b" " * (8 * 1024 * 1024))
        _write_artifact(tmp_path, "2026-08-28", current)
        section = nsdb._posture_transition(root=tmp_path, current_session="2026-08-28", previous_session="2026-08-27")
        assert section["availability"] == "AVAILABLE"
        assert section["records"]["HPG"]["transition"] == "EARLY_WATCH_TO_INITIATE"
        assert section["previous_universe_count"] == 1
        assert section["source_lineage"]["previous_integrated_decision_identity"] == "prev:x"
