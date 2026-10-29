"""Daily input transitions preserve only proven dependencies; parity uses an uncached evaluator."""
import hashlib
import json
from pathlib import Path

import pytest

import prospective_decision_outcome_feedback as feedback
import prospective_feedback_streaming as streaming
from tests.test_prospective_feedback_streaming import (
    _add_legacy, _add_modern, _bind, _build, _corpus, _legacy_artifact, _write, TICKERS,
)


def _parity(root, result, output):
    expected = _legacy_artifact(root)
    actual = json.loads(output.read_bytes())
    assert actual == expected
    assert result["artifact_identity"] == streaming.stream_artifact_identity(output) == expected["artifact_identity"]
    keys = [(r["decision_session"], r["ticker"], r["decision_identity"]) for r in actual["feedback_records"]]
    assert len(keys) == len(set(keys))
    assert len(actual["trigger_invalidation_outcomes"]) == len(keys)


@pytest.fixture
def long_corpus(tmp_path):
    root, state = tmp_path / "evidence", tmp_path / "state"
    sessions = _corpus(root, legacy=24, modern=2)
    output = tmp_path / "first.json"
    first = _build(root, output, state)
    return root, state, sessions, first


def test_append_daily_reuses_terminal_sessions_and_recalculates_newly_mature_windows(long_corpus, tmp_path):
    root, state, sessions, first = long_corpus
    _add_modern(root, "2026-01-28", 26)
    output = tmp_path / "next.json"
    result = _build(root, output, state, prior_summary=first["inputs_summary"])
    assert result["relation"]["relation"] == "INCREMENTAL"
    assert result["metrics"].get("partitions_reused_terminal", 0) + result["metrics"].get("partitions_reused_extension", 0) > 0
    assert result["metrics"]["partitions_invalidated"] > 0
    assert result["metrics"]["partitions_built"] + result["metrics"]["partitions_reused"] == len(sessions) + 1
    _parity(root, result, output)
    before = json.loads((tmp_path / "first.json").read_bytes())["feedback_records"]
    after = json.loads(output.read_bytes())["feedback_records"]
    # T20 for this decision was pending and must mature after the appended observation.
    key = (sessions[6], TICKERS[0])
    a = next(r for r in before if (r["decision_session"], r["ticker"]) == key)
    b = next(r for r in after if (r["decision_session"], r["ticker"]) == key)
    assert a["forward_outcomes"]["horizons"]["forward_close_return_20"]["status"] != "MATURE"
    assert b["forward_outcomes"]["horizons"]["forward_close_return_20"]["status"] == "MATURE"


def test_identical_corpus_new_output_reuses_all_partitions(long_corpus, tmp_path):
    root, state, sessions, first = long_corpus
    output = tmp_path / "again.json"
    result = _build(root, output, state)
    assert result["metrics"]["partitions_reused_exact"] == len(sessions)
    assert result["metrics"].get("rows", 0) == 0
    assert result["artifact_identity"] == first["artifact_identity"]


@pytest.mark.parametrize("change", ["evidence", "authority", "qualification", "price"])
def test_existing_session_changes_invalidate_actual_dependencies(long_corpus, tmp_path, change):
    root, state, sessions, _first = long_corpus
    session = sessions[1]
    if change in {"evidence", "authority"}:
        path = root / "operations-review/integrated-artifacts" / session / "integrated_investment_decision_product_artifact.json"
        artifact = json.loads(path.read_bytes())
        if change == "evidence":
            artifact["records"][TICKERS[0]]["research_action_posture"] = "AVOID"
        else:
            artifact["records"][TICKERS[0]]["source_identities"]["technical_structure_identity"] = "revised-authority:2"
        _write(path, artifact)  # fixture intentionally keeps the artifact label unchanged
    elif change == "qualification":
        path = root / "operations-review/canonical-post-close-v1" / session / "session_handoff_bundle.json"
        value = json.loads(path.read_bytes())
        value["daily_producer"]["status"] = "FAILED"
        _write(path, value)
    else:
        path = root / "operations-review" / f"p3f9b-market-wide-exact-session-scaleout-{session.replace('-', '')}" / "p3f9b_mva_exact_session_snapshot.json"
        value = json.loads(path.read_bytes())
        value["records"][TICKERS[0]]["observations"][1]["close"] += 5
        _write(path, value)
    output = tmp_path / "changed.json"
    result = _build(root, output, state)
    assert result["metrics"].get("partitions_built", 0) > 0
    _parity(root, result, output)


@pytest.mark.parametrize("change", ["code", "contract"])
def test_evaluator_changes_invalidate_partitions_and_contributions(long_corpus, tmp_path, monkeypatch, change):
    root, state, sessions, _ = long_corpus
    if change == "code":
        monkeypatch.setattr(streaming, "code_digest", lambda: "a" * 64)
    else:
        monkeypatch.setattr(feedback, "CONTRACT_VERSION", "prospective_decision_outcome_feedback/fixture-next")
    output = tmp_path / "code.json"
    result = _build(root, output, state)
    assert result["metrics"].get("partitions_reused", 0) == 0
    if change == "code":
        assert result["metrics"].get("settled_hits", 0) == 0
    _parity(root, result, output)


def test_pre_handoff_snapshot_is_not_admitted_until_qualified(long_corpus, tmp_path):
    root, state, _sessions, first = long_corpus
    snapshot = _add_modern(root, "2026-01-28", 26)
    handoff = root / "operations-review/canonical-post-close-v1/2026-01-28/session_handoff_bundle.json"
    handoff.unlink()
    pre_path = tmp_path / "pre.json"
    pre = _build(root, pre_path, state, prior_summary=first["inputs_summary"])
    assert pre["metrics"]["partitions_reused"] == 26
    assert "2026-01-28" not in pre["inputs_summary"]["chain_sessions"]
    _parity(root, pre, pre_path)
    _bind(root, snapshot)
    post_path = tmp_path / "post.json"
    post = _build(root, post_path, state, prior_summary=pre["inputs_summary"])
    assert post["metrics"].get("partitions_reused_terminal", 0) + post["metrics"].get("partitions_reused_extension", 0) > 0
    assert post["record_count"] == pre["record_count"] + len(TICKERS)
    _parity(root, post, post_path)


def test_checkpoint_manifest_tamper_is_only_a_cache_miss(long_corpus, tmp_path):
    root, state, _, first = long_corpus
    path = next((state / streaming.PARTITION_DIR).rglob("*.partition.json"))
    value = json.loads(path.read_bytes())
    value["terminal_proof"] = {"through": "2026-01-02"}
    _write(path, value)
    output = tmp_path / "repair.json"
    result = _build(root, output, state)
    assert result["metrics"]["partitions_corrupt"] == 1
    assert result["artifact_identity"] == first["artifact_identity"]


def test_open_condition_becoming_satisfied_invalidates_an_old_t20_window(long_corpus, tmp_path):
    root, state, sessions, _ = long_corpus
    _add_modern(root, "2026-01-28", -50)  # new observation crosses the retained invalidation level
    output = tmp_path / "event.json"
    result = _build(root, output, state)
    _parity(root, result, output)
    rows = json.loads(output.read_bytes())["feedback_records"]
    row = next(r for r in rows if r["decision_session"] == sessions[0] and r["ticker"] == TICKERS[0])
    assert row["trigger_invalidation_outcome"]["invalidation"]["event_session"] == "2026-01-28"
    assert result["metrics"]["partitions_invalidated"] > 0


def test_derived_storage_budget_preserves_pinned_files_and_refuses_oversized_active_set(tmp_path):
    for n in range(5):
        (tmp_path / str(n)).write_bytes(b"1234")
    pinned = tmp_path / "0"
    streaming._prune_derived(tmp_path, max_bytes=8, max_entries=2, protected=[pinned])
    assert pinned.exists() and sum(p.stat().st_size for p in tmp_path.iterdir()) <= 8
    with pytest.raises(streaming.FeedbackStreamError, match="CHECKPOINT_STORAGE_LIMIT"):
        streaming._prune_derived(tmp_path, max_bytes=1, max_entries=2, protected=[pinned])


def test_strict_future_context_change_never_uses_a_legacy_extension_proof(tmp_path, monkeypatch):
    import prospective_pit_capture_retention as store
    from tests.test_prospective_feedback_streaming import _FutureChain
    root, state = tmp_path / "evidence", tmp_path / "state"
    sessions = _corpus(root)
    marker = sessions[3]
    monkeypatch.setattr(store, "load_marker", lambda r: {"session": marker})
    monkeypatch.setattr(store, "load_chain", lambda r, as_of: _FutureChain(s for s in sessions if s >= marker))
    _build(root, tmp_path / "first.json", state)
    monkeypatch.setattr(streaming, "_future_chain_inputs", lambda *a: {"marker": marker, "calendar": "requalified"})
    output = tmp_path / "changed.json"
    result = _build(root, output, state)
    assert result["metrics"]["partitions_reused_exact"] == 3  # before the marker: no dependency on the future context
    assert result["metrics"]["partitions_built"] == len(sessions) - 3
    assert result["metrics"].get("partitions_reused_extension", 0) == 0
    _parity(root, result, output)
