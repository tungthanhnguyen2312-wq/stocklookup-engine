"""Per-session checkpoints: a stopped build resumes from completed sessions and publishes the identical artifact."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

import prospective_feedback_streaming as streaming
from tests.test_prospective_feedback_streaming import _add_modern, _build, _corpus, _legacy_artifact, TICKERS


@pytest.fixture()
def corpus(tmp_path):
    root = tmp_path / "evidence"
    sessions = _corpus(root)
    return root, sessions, tmp_path / "state", tmp_path / "out" / "feedback.json"


def _stop_in_session(monkeypatch, stop_at: int):
    """Raise when the ``stop_at``-th session (0-based) starts emitting, like a deadline kill mid-session."""
    original = streaming._iter_session_rows
    seen = {"sessions": 0}

    def stopping(*args, **kwargs):
        index = seen["sessions"]
        seen["sessions"] += 1
        for position, row in enumerate(original(*args, **kwargs)):
            if index == stop_at and position == 1:
                raise KeyboardInterrupt("deadline")
            yield row
    monkeypatch.setattr(streaming, "_iter_session_rows", stopping)
    return original


def _manifests(state: Path) -> list[Path]:
    return sorted((state / streaming.PARTITION_DIR).rglob("*.partition.json"))


def _evidence_digest(root: Path) -> dict[str, str]:
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(root.rglob("*")) if p.is_file()}


def test_stopped_build_resumes_from_completed_sessions_with_identical_output(corpus, tmp_path, monkeypatch):
    root, sessions, state, output = corpus
    clean_output = tmp_path / "clean" / "feedback.json"
    clean = _build(root, clean_output, tmp_path / "clean-state")
    evidence = _evidence_digest(root)

    original = _stop_in_session(monkeypatch, stop_at=5)
    with pytest.raises(KeyboardInterrupt):
        _build(root, output, state)
    assert not output.exists() and len(_manifests(state)) == 5  # sessions 0-4 checkpointed, 5 discarded
    monkeypatch.setattr(streaming, "_iter_session_rows", original)

    resumed = _build(root, output, state)
    assert resumed["metrics"]["partitions_reused"] == 5
    assert resumed["metrics"]["rows_reused"] == 5 * len(TICKERS)
    assert resumed["metrics"]["rows"] == (len(sessions) - 5) * len(TICKERS)  # only the remaining work is evaluated
    assert resumed["artifact_identity"] == clean["artifact_identity"] == _legacy_artifact(root)["artifact_identity"]
    assert output.read_bytes() == clean_output.read_bytes()
    records = json.loads(output.read_text(encoding="utf-8"))["feedback_records"]
    identities = [r["feedback_identity"] for r in records]
    assert len(identities) == len(set(identities)) == len(sessions) * len(TICKERS)  # no duplicate or missing rows
    assert _evidence_digest(root) == evidence  # retained cohorts/T0 untouched


def test_repeated_stops_make_forward_progress_and_never_publish_partially(corpus, monkeypatch):
    root, sessions, state, output = corpus
    original = streaming._iter_session_rows
    for stop_at in (2, 3, 5):
        _stop_in_session(monkeypatch, stop_at - len(_manifests(state)))
        with pytest.raises(KeyboardInterrupt):
            _build(root, output, state)
        assert not output.exists() and len(_manifests(state)) == stop_at
        monkeypatch.setattr(streaming, "_iter_session_rows", original)
    assert _build(root, output, state)["artifact_identity"] == _legacy_artifact(root)["artifact_identity"]


def test_crash_between_partition_data_and_manifest_rebuilds_that_session(corpus, monkeypatch):
    root, _sessions, state, output = corpus
    real = streaming._atomic_write_json
    writes = {"n": 0}

    def crashing(path, value, **kwargs):
        if path.name.endswith(".partition.json"):
            writes["n"] += 1
            if writes["n"] == 3:
                raise OSError("power loss while writing the manifest")
        return real(path, value, **kwargs)
    monkeypatch.setattr(streaming, "_atomic_write_json", crashing)
    with pytest.raises(OSError):
        _build(root, output, state)
    assert len(_manifests(state)) == 2 and not output.exists()
    monkeypatch.setattr(streaming, "_atomic_write_json", real)
    result = _build(root, output, state)
    assert result["metrics"]["partitions_reused"] == 2
    assert result["artifact_identity"] == _legacy_artifact(root)["artifact_identity"]


def test_tampered_partition_fails_closed_then_is_rebuilt(corpus, monkeypatch):
    root, _sessions, state, output = corpus
    original = _stop_in_session(monkeypatch, stop_at=4)
    with pytest.raises(KeyboardInterrupt):
        _build(root, output, state)
    monkeypatch.setattr(streaming, "_iter_session_rows", original)
    rows = sorted((state / streaming.PARTITION_DIR).rglob("*.rows"))[1]
    data = bytearray(rows.read_bytes())
    data[data.index(b'"ticker":"') + 10] ^= 1  # same size, different bytes
    rows.write_bytes(bytes(data))
    with pytest.raises(streaming.FeedbackStreamError, match="FEEDBACK_PARTITION_INTEGRITY"):
        _build(root, output, state)
    assert not output.exists()
    assert _build(root, output, state)["artifact_identity"] == _legacy_artifact(root)["artifact_identity"]


def test_changed_source_or_code_never_reuses_checkpoints(corpus, monkeypatch):
    root, sessions, state, output = corpus
    original = _stop_in_session(monkeypatch, stop_at=4)
    with pytest.raises(KeyboardInterrupt):
        _build(root, output, state)
    monkeypatch.setattr(streaming, "_iter_session_rows", original)
    stale_runs = {p.name for p in (state / streaming.PARTITION_DIR).iterdir()}

    monkeypatch.setattr(streaming, "code_digest", lambda: "0" * 64)
    changed_code = _build(root, output, state)
    assert changed_code["metrics"].get("partitions_reused", 0) == 0
    assert not stale_runs & {p.name for p in (state / streaming.PARTITION_DIR).iterdir()}  # incompatible runs pruned

    _add_modern(root, "2026-01-20", 18)
    new_output = output.with_name("feedback-2.json")
    changed_source = _build(root, new_output, state)
    assert changed_source["metrics"].get("partitions_reused", 0) == 0
    assert changed_source["artifact_identity"] == _legacy_artifact(root)["artifact_identity"]


def test_settled_contributions_persist_per_entry_and_are_reused_across_run_identities(tmp_path, monkeypatch):
    root, state, output = tmp_path / "evidence", tmp_path / "state", tmp_path / "out" / "feedback.json"
    _corpus(root, legacy=24, modern=2)  # longer than the 20-session horizon, so early rows settle
    first = _build(root, output, state)
    store = state / streaming.SETTLED_STORE_DIR
    persisted = sorted(store.rglob("*.json"))
    assert persisted and not (state / "operations-review/prospective-decision-outcome-feedback-v1/_settled_cache.json").exists()
    monkeypatch.setattr(streaming, "code_digest", lambda: "1" * 64)  # forces a new run identity; rows are re-evaluated
    second = _build(root, output.with_name("again.json"), state)
    assert second["metrics"]["settled_hits"] == len(persisted)
    assert second["artifact_identity"] == first["artifact_identity"]
    persisted[0].write_bytes(b"{torn")  # an unreadable entry is only a miss
    third = _build(root, output.with_name("third.json"), state, )
    assert third["artifact_identity"] == first["artifact_identity"]


def test_oversized_partition_fails_closed(corpus, monkeypatch):
    root, _sessions, state, output = corpus
    monkeypatch.setattr(streaming, "PARTITION_MAX_BYTES", 64)
    with pytest.raises(streaming.FeedbackStreamError, match="FEEDBACK_PARTITION_SIZE_LIMIT"):
        _build(root, output, state)
    assert not output.exists() and _manifests(state) == []
