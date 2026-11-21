"""TPLUS_INCREMENTAL_COST_V2 retry integrity: legitimate same-session retries are terminal reuse,
changed observable inputs are never accepted as equivalent unless the rebuilt bytes prove it, and
the Pre-handoff boundary is independent of whether this session's own handoff already exists.

Regression for the 2026-11-20 second Daily attempt, where both feedback stages failed with
FEEDBACK_IMMUTABLE_OUTPUT_CONFLICT although each path held a valid COMPLETE artifact.
"""
import json
from pathlib import Path

import pytest

import prospective_decision_retention as retention
import prospective_feedback_streaming as streaming
from governed_session_chain import CalendarCoverage, GovernedSessionChain
from tests.test_prospective_feedback_streaming import (
    TICKERS, _FutureChain, _add_modern, _bind, _build, _corpus, _legacy_artifact, _write,
)


def _manifest(output: Path) -> dict:
    return json.loads(streaming.completion_manifest_path(output).read_bytes())


@pytest.fixture()
def retained(tmp_path):
    root, state = tmp_path / "evidence", tmp_path / "state"
    sessions = _corpus(root)
    output = tmp_path / "out" / "prospective_decision_feedback_artifact.json"
    first = _build(root, output, state)
    return root, state, sessions, output, first


def _future(monkeypatch, sessions, marker_index=3, extra=()):
    import prospective_pit_capture_retention as store
    marker = sessions[marker_index]
    chain = _FutureChain([s for s in sessions if s >= marker] + list(extra))
    monkeypatch.setattr(store, "load_marker", lambda r: {"session": marker})
    monkeypatch.setattr(store, "load_chain", lambda r, as_of: chain)
    return marker


# -- legitimate same-session retries -------------------------------------------------------------------

def test_same_session_retry_reuses_the_completed_output_without_touching_bytes_or_lineage(retained):
    root, state, _sessions, output, first = retained
    raw, manifest = output.read_bytes(), _manifest(output)
    again = _build(root, output, state)
    assert again["outcome"] == streaming.OUTCOME_ALREADY_COMPLETE
    assert again["artifact_identity"] == first["artifact_identity"] and again["input_digest"] == first["input_digest"]
    assert output.read_bytes() == raw and _manifest(output) == manifest


def test_retry_with_a_new_calendar_revision_log_entry_is_terminal_reuse(tmp_path, monkeypatch):
    """Every Daily attempt writes calendar-revisions/<sha>.json; the chain never reads it."""
    import prospective_pit_capture_retention as store
    root, state = tmp_path / "evidence", tmp_path / "state"
    sessions = _corpus(root)
    _future(monkeypatch, sessions)
    output = tmp_path / "out" / "feedback.json"
    first = _build(root, output, state)
    _write(root / store.STORE / "calendar-revisions" / ("ab" * 32 + ".json"),
           {"contract_version": "prospective_calendar_revision/v1", "known_at": "2026-11-20T15:04:59+00:00",
            "receipt_identity": "dnse_working_dates_calendar_receipt:" + "cd" * 32, "overlap_disagreements": []})
    again = _build(root, output, state)
    assert again["outcome"] == streaming.OUTCOME_ALREADY_COMPLETE
    assert again["input_digest"] == first["input_digest"]


# -- semantic calendar identity --------------------------------------------------------------------------

def _chain(days, *, identity="legacy_governed_calendar:a", as_of="2026-11-20T10:00:00+00:00"):
    calendar = CalendarCoverage((), cutoff=as_of, base_sessions=days, base_identity=identity)
    return GovernedSessionChain((), calendar=calendar, as_of=as_of, first_complete_capture_session=days[0])


def test_equal_calendar_content_from_a_different_receipt_has_the_same_identity():
    days = ["2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20"]
    marker, as_of = {"session": days[0]}, "2026-11-20T10:00:00+00:00"
    a = streaming._future_chain_inputs(_chain(days, identity="receipt:first"), marker, as_of)
    b = streaming._future_chain_inputs(_chain(days, identity="receipt:retry"), marker, as_of)
    assert a == b
    assert "receipt:first" not in json.dumps(a)


def test_actual_calendar_change_changes_the_identity():
    days = ["2026-11-17", "2026-11-18", "2026-11-19", "2026-11-20"]
    marker, as_of = {"session": days[0]}, "2026-11-20T10:00:00+00:00"
    base = streaming._future_chain_inputs(_chain(days), marker, as_of)
    assert streaming._future_chain_inputs(_chain(days[:-1]), marker, as_of) != base       # session removed
    assert streaming._future_chain_inputs(_chain(days + ["2026-11-21"]), marker, as_of) != base  # session added
    assert streaming._future_chain_inputs(_chain(days), {"session": days[1]}, as_of) != base  # marker


def test_identity_uses_the_vietnamese_civil_date_that_missed_sessions_read():
    days = ["2026-11-17", "2026-11-18"]
    marker = {"session": days[0]}
    same_vn_day = [streaming._future_chain_inputs(_chain(days), marker, t) for t in
                   ("2026-11-20T01:00:00+00:00", "2026-11-20T16:59:00+00:00")]
    assert same_vn_day[0] == same_vn_day[1]
    # 17:00 UTC is 00:00 the next day in Vietnam: same UTC date, different civil date.
    assert streaming._future_chain_inputs(_chain(days), marker, "2026-11-20T17:00:00+00:00") != same_vn_day[0]


# -- changed inputs ----------------------------------------------------------------------------------------

def test_changed_identity_with_byte_equal_output_keeps_original_lineage_and_records_the_proof(retained, monkeypatch):
    root, state, _sessions, output, first = retained
    original = _manifest(output)
    real = streaming._future_chain_inputs
    monkeypatch.setattr(streaming, "_future_chain_inputs", lambda c, m, a: {**real(c, m, a), "probe": "retry"})
    rebuilt = _build(root, output, state)
    assert rebuilt["outcome"] == streaming.OUTCOME_ALREADY_RETAINED_EQUAL
    assert rebuilt["input_digest"] != first["input_digest"]
    after = _manifest(output)
    assert after["input_digest"] == original["input_digest"] and after["inputs_summary"] == original["inputs_summary"]
    assert [e["input_digest"] for e in after["equivalent_inputs"]] == [rebuilt["input_digest"]]
    assert _build(root, output, state)["outcome"] == streaming.OUTCOME_ALREADY_COMPLETE  # now terminal


def test_changed_substantive_input_is_a_genuine_conflict_and_the_completed_artifact_survives(retained):
    root, state, sessions, output, first = retained
    raw, manifest = output.read_bytes(), _manifest(output)
    session = sessions[1]
    path = root / "operations-review" / f"p3f9b-market-wide-exact-session-scaleout-{session.replace('-', '')}" / "p3f9b_mva_exact_session_snapshot.json"
    value = json.loads(path.read_bytes())
    value["records"][TICKERS[0]]["observations"][1]["close"] += 5
    _write(path, value)
    with pytest.raises(streaming.ImmutableOutputConflict, match="IMMUTABLE_ARTIFACT_CONFLICT"):
        _build(root, output, state)
    assert output.read_bytes() == raw and _manifest(output) == manifest


def test_calendar_change_that_changes_rows_is_never_accepted_as_equivalent(tmp_path, monkeypatch):
    root, state = tmp_path / "evidence", tmp_path / "state"
    sessions = _corpus(root)
    _future(monkeypatch, sessions)
    output = tmp_path / "out" / "feedback.json"
    _build(root, output, state)
    raw = output.read_bytes()
    _future(monkeypatch, sessions, extra=["2026-01-31"])  # a calendar revision adds a realized session
    with pytest.raises(streaming.ImmutableOutputConflict):
        _build(root, output, state)
    assert output.read_bytes() == raw


# -- Pre/Post handoff boundary ----------------------------------------------------------------------------

def test_pre_handoff_retry_after_its_own_handoff_reuses_the_pre_handoff_artifact(retained, tmp_path):
    root, state, _sessions, _output, first = retained
    session = "2026-01-28"
    snapshot = _add_modern(root, session, 26)
    handoff = root / "operations-review/canonical-post-close-v1" / session / "session_handoff_bundle.json"
    handoff.unlink()  # attempt 1, K15: this session's handoff does not exist yet
    pre = tmp_path / "pre" / "feedback.json"
    k15 = _build(root, pre, state, pre_handoff_session=session)
    assert session not in k15["inputs_summary"]["chain_sessions"]
    _bind(root, snapshot)  # attempt 1, K18 writes the handoff
    post = tmp_path / "post" / "feedback.json"
    k19 = _build(root, post, state, prior_summary=k15["inputs_summary"])
    assert session in k19["inputs_summary"]["chain_sessions"]
    assert k19["record_count"] == k15["record_count"] + len(TICKERS)  # the new T0 is credited after handoff
    raw_pre, raw_post = pre.read_bytes(), post.read_bytes()
    # Attempt 2 reruns both stages against the same retained evidence.
    retry_pre = _build(root, pre, state, pre_handoff_session=session)
    retry_post = _build(root, post, state)
    assert retry_pre["outcome"] == retry_post["outcome"] == streaming.OUTCOME_ALREADY_COMPLETE
    assert retry_pre["artifact_identity"] == k15["artifact_identity"] and retry_post["artifact_identity"] == k19["artifact_identity"]
    assert pre.read_bytes() == raw_pre and post.read_bytes() == raw_post
    # Without the boundary the retried K15 would see 49 instead of 48 sessions: the 2026-11-20 failure.
    with pytest.raises(streaming.ImmutableOutputConflict):
        _build(root, pre, state)


def test_pre_handoff_boundary_is_scoped_and_hides_only_that_sessions_handoff(retained):
    root, _state, sessions, _output, _first = retained
    target = sessions[-1]
    full = retention.discover_snapshots(root)
    with retention.pre_handoff_boundary(target):
        bounded = retention.discover_snapshots(root)
    assert retention._EXCLUDED_HANDOFF_SESSIONS.get() == frozenset()
    full_sessions = sorted(r["snapshot"]["session"] for r in full["genuine_snapshots"])
    bounded_sessions = sorted(r["snapshot"]["session"] for r in bounded["genuine_snapshots"])
    assert bounded_sessions == [s for s in full_sessions if s != target]
    assert all(r["session"] != target for r in bounded["handoff_snapshot_inventory"])


def test_pre_and_post_handoff_identities_are_distinct_even_on_identical_evidence(retained, tmp_path):
    root, state, sessions, _output, first = retained
    bounded = _build(root, tmp_path / "pre.json", state, pre_handoff_session="2026-02-28")  # no such handoff
    assert bounded["artifact_identity"] == first["artifact_identity"]  # nothing hidden: same content
    assert bounded["input_digest"] != first["input_digest"]  # but the boundary is part of its identity


# -- orchestration ---------------------------------------------------------------------------------------

def test_only_the_pre_handoff_stage_passes_its_session_boundary(tmp_path, monkeypatch):
    import canonical_post_close_pipeline as pipeline
    import stocklookup_core.acquisition.feedback_resource_guard as guard
    commands = []

    def fake_run(command, **kwargs):
        commands.append(command)
        return {"outcome": "COMPLETED", "reaped": True, "wall_seconds": 0.0,
                "child_result": {"status": "COMPLETED", "artifact_identity": "x", "outcome": "ALREADY_COMPLETE"}}

    monkeypatch.setattr(guard, "run_bounded", fake_run)
    monkeypatch.setattr(guard, "admit", lambda *a, **k: {"admitted": True})
    for stage in (pipeline.FEEDBACK_STAGE_PRE_HANDOFF, pipeline.FEEDBACK_STAGE_POST_HANDOFF):
        result = pipeline.run_bounded_prospective_feedback(tmp_path, "2026-11-20", output=tmp_path / stage / "f.json", stage=stage)
        assert result["status"] == "COLLECTED"
    pre, post = commands
    assert pre[pre.index("--pre-handoff-session") + 1] == "2026-11-20"
    assert "--pre-handoff-session" not in post


def test_reuse_proof_cache_is_positive_only_and_bound_to_its_full_key(tmp_path):
    cache = streaming._ReuseProofCache(tmp_path, {})
    key = {"snapshot_raw_sha256": "a" * 64, "decision_count": 3}
    assert cache.get(key) is None
    cache.put(key, {"verified_record_count": 3})
    assert cache.get(key) == {"verified_record_count": 3}
    assert cache.get({**key, "snapshot_raw_sha256": "b" * 64}) is None
    path = cache._path(key)
    stored = json.loads(path.read_bytes())
    stored["key"]["decision_count"] = 4  # a tampered body no longer matches its own key
    path.write_text(json.dumps(stored), encoding="utf-8")
    assert cache.get(key) is None


# -- strict-partition replay proofs ------------------------------------------------------------------------

def test_strict_partition_replay_is_invalidated_by_a_price_revision_it_read(tmp_path, monkeypatch):
    from tests.test_prospective_feedback_incremental import _parity
    root, state = tmp_path / "evidence", tmp_path / "state"
    sessions = _corpus(root)
    _future(monkeypatch, sessions, marker_index=1)  # strict partitions from sessions[1]
    _build(root, tmp_path / "first.json", state)
    relabel = streaming._future_chain_inputs
    monkeypatch.setattr(streaming, "_future_chain_inputs", lambda c, m, a: {**relabel(c, m, a), "relabel": 1})
    replayed = _build(root, tmp_path / "replayed.json", state)
    assert replayed["metrics"]["partitions_reused_replay"] == len(sessions) - 1
    revised = sessions[2]  # a legacy-priced session the strict sessions[1] partition reads
    path = root / "operations-review" / f"p3f9b-market-wide-exact-session-scaleout-{revised.replace('-', '')}" / "p3f9b_mva_exact_session_snapshot.json"
    value = json.loads(path.read_bytes())
    value["records"][TICKERS[0]]["observations"][1]["close"] += 7
    _write(path, value)
    monkeypatch.setattr(streaming, "_future_chain_inputs", lambda c, m, a: {**relabel(c, m, a), "relabel": 2})
    output = tmp_path / "revised.json"
    result = _build(root, output, state)
    assert result["metrics"].get("partitions_reused_replay", 0) < len(sessions) - 1
    assert result["metrics"]["partitions_built"] >= 1
    _parity(root, result, output)


def test_recording_views_mark_enumeration_unreplayable():
    log = streaming._ReplayLog()
    view = streaming._RecordingSnapshots({"2026-01-02": {"x": 1}}, log)
    assert view.get("2026-01-02") == {"x": 1} and "2026-01-03" not in view
    assert log.sessions == {"2026-01-02", "2026-01-03"} and log.unreplayable is None
    list(view.items())
    assert log.unreplayable == "enumerated_keys"
    chain_log = streaming._ReplayLog()
    chain = streaming._RecordingChain(_FutureChain(["2026-01-02", "2026-01-05"]), chain_log)
    assert chain[0:5] == ["2026-01-02", "2026-01-05"] and chain.index("2026-01-05") == 1
    with pytest.raises(ValueError):
        chain.index("2026-01-09")
    assert any(entry[0] == "index" for entry in chain_log.chain.values())
    with pytest.raises(AttributeError):
        chain.window_ending  # an unrecorded surface
    assert chain_log.unreplayable == "attribute:window_ending"


# -- settled partition packs -------------------------------------------------------------------------------

def test_rebuilt_legacy_partitions_reuse_settled_entries_from_their_pack(tmp_path):
    from tests.test_prospective_feedback_incremental import _parity
    root, state = tmp_path / "evidence", tmp_path / "state"
    _corpus(root, legacy=24, modern=2)
    _build(root, tmp_path / "first.json", state)
    packs = list((state / streaming.PARTITION_DIR).rglob(streaming.SETTLED_PACK_NAME))
    assert packs
    _add_modern(root, "2026-01-28", -50)  # crosses a retained invalidation level: old partitions rebuild
    output = tmp_path / "next.json"
    result = _build(root, output, state)
    assert result["metrics"].get("settled_pack_hits", 0) > 0 and result["metrics"].get("settled_hits", 0) > 0
    _parity(root, result, output)


def test_a_torn_or_foreign_settled_pack_is_only_a_miss(tmp_path):
    store = streaming._DiskSettledStore(tmp_path / "store", {})
    pack = tmp_path / streaming.SETTLED_PACK_NAME
    metrics = {}
    for body in (b"torn", b'["k", 1]\n', b'{"k": {}}\n'):
        pack.write_bytes(body)
        store.begin_partition(pack, metrics)
        assert store.get("k") is None
        store.end_partition()
    assert metrics["settled_pack_corrupt"] == 3
    store.begin_partition(pack, metrics)
    store["k"] = {"entry": 1}  # retained during the partition, written once at its end
    assert not (tmp_path / "store").exists()
    store.end_partition()
    store.begin_partition(pack, metrics)
    assert store.get("k") == {"entry": 1} and metrics["settled_pack_hits"] == 1
    store.end_partition()


def test_a_genuine_conflict_names_the_retained_prior_attempt_artifact(retained, monkeypatch):
    import canonical_post_close_pipeline as pipeline
    import stocklookup_core.acquisition.feedback_resource_guard as guard
    _root, _state, _sessions, output, first = retained
    monkeypatch.setattr(guard, "admit", lambda *a, **k: {"admitted": True})
    monkeypatch.setattr(guard, "run_bounded", lambda command, **k: {
        "outcome": "COMPLETED", "reaped": True, "wall_seconds": 1.0, "reason_code": guard.IMMUTABLE_CONFLICT,
        "child_result": {"status": "FAILED", "reason_code": guard.IMMUTABLE_CONFLICT}})
    result = pipeline.run_bounded_prospective_feedback(output.parent, "2026-01-09", output=output,
                                                       stage=pipeline.FEEDBACK_STAGE_POST_HANDOFF)
    assert result["status"] == "UNAVAILABLE" and result["reason_code"] == guard.IMMUTABLE_CONFLICT
    assert result["retained_complete_artifact"]["artifact_identity"] == first["artifact_identity"]
