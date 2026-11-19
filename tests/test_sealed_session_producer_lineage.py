"""A sealed session reuses its Producer lineage or fails before a second identity exists."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import canonical_daily_operation as cdo
import daily_producer_pipeline as producer
from daily_research_session_operations import refuse_competing_sealed_operation
from test_canonical_daily_operation import SESSION, _run

RUN = "ab" * 32
OPERATION = "cd" * 32
SNAPSHOT = "ef" * 32
PRODUCER_HEAD = "5c457bb07055d14550c1cb27c2550cea85379eca"
CONSUMER_HEAD = "97a027884f69ede44e2df8e53d1cbad72766064e"


def _plant(root: Path, session: str = SESSION, *, producer_head=PRODUCER_HEAD, consumer_head=CONSUMER_HEAD,
           operation_head=None, runs=1, indexes=1) -> None:
    operation_head = producer_head if operation_head is None else operation_head
    operation_identity = f"daily_research_session_operation:{OPERATION}"
    for offset in range(runs):
        digest = RUN if offset == 0 else f"{offset:064x}"
        run_dir = root / "operations-review" / "daily-producer-runs-v1" / session / digest
        run_dir.mkdir(parents=True)
        (run_dir / "run_manifest.json").write_text(json.dumps({
            "run_identity": f"daily_producer_run:{digest}",
            "target_market_session": session,
            "producer_head": producer_head,
            "consumer_head": consumer_head,
            "daily_session_operation": {"identity": operation_identity},
        }), encoding="utf-8")
    operation_dir = root / "operations-review" / "daily-research-session-operations-v1" / session / OPERATION
    operation_dir.mkdir(parents=True)
    (operation_dir / "run_manifest.json").write_text(json.dumps({
        "operation_identity": operation_identity,
        "market_session": session,
        "producer_head": operation_head,
        "consumer_head": consumer_head,
    }), encoding="utf-8")
    for offset in range(indexes):
        digest = SNAPSHOT if offset == 0 else f"{offset + 1:064x}"
        index_dir = root / "operations-review" / "prospective-decision-retention-v1" / session / digest
        index_dir.mkdir(parents=True)
        (index_dir / "prospective_t0_seal_index.json").write_text(json.dumps({
            "session": session,
            "operation_identity": operation_identity,
            "snapshot_identity": f"prospective_decision_snapshot:{digest}",
        }), encoding="utf-8")


def _capture(tmp_path, monkeypatch):
    seen = {}

    def produce(*_args, **kwargs):
        seen.update(kwargs)
        raise RuntimeError("CAPTURED")

    monkeypatch.setattr(cdo, "_git_head", lambda _path: "live-head")
    with pytest.raises(RuntimeError, match="CAPTURED"):
        _run(tmp_path, monkeypatch, producer_fn=produce)
    return seen


def test_one_verified_seal_reuses_heads_instead_of_live_git(tmp_path, monkeypatch):
    _plant(tmp_path)
    seen = _capture(tmp_path, monkeypatch)
    assert seen["producer_head"] == PRODUCER_HEAD
    assert seen["consumer_head"] == CONSUMER_HEAD


def test_no_sealed_run_keeps_the_live_git_heads(tmp_path, monkeypatch):
    seen = _capture(tmp_path, monkeypatch)
    assert seen["producer_head"] == "live-head"
    assert seen["consumer_head"] == "live-head"


def test_ambiguous_or_disagreeing_seals_fail_before_producer(tmp_path, monkeypatch):
    def forbidden(*_args, **_kwargs):
        raise AssertionError("producer must not run")

    monkeypatch.setattr(cdo, "_git_head", lambda _path: "live-head")
    _plant(tmp_path, runs=2)
    with pytest.raises(cdo.CanonicalDailyOperationError, match="SEALED_PRODUCER_RUN_AMBIGUOUS"):
        _run(tmp_path, monkeypatch, producer_fn=forbidden)

    other = tmp_path / "other"
    _plant(other, operation_head="different-producer")
    with pytest.raises(cdo.CanonicalDailyOperationError, match="SEALED_SESSION_OPERATION_MISMATCH"):
        cdo._sealed_session_producer_heads(other, SESSION)

    missing_t0 = tmp_path / "missing-t0"
    _plant(missing_t0, indexes=0)
    with pytest.raises(cdo.CanonicalDailyOperationError, match="SEALED_T0_INDEX_COUNT"):
        cdo._sealed_session_producer_heads(missing_t0, SESSION)


def test_operation_and_run_guards_reject_a_second_identity_without_writing(tmp_path):
    session = "2026-11-19"
    operation_root = tmp_path / "operations"
    operation_identity = f"daily_research_session_operation:{OPERATION}"
    operation_dir = operation_root / session / OPERATION
    operation_dir.mkdir(parents=True)
    (operation_dir / "run_manifest.json").write_text(json.dumps({
        "operation_identity": operation_identity,
        "market_session": session,
    }), encoding="utf-8")
    refuse_competing_sealed_operation(operation_root, session, operation_identity)
    with pytest.raises(ValueError, match="SEALED_SESSION_OPERATION_IDENTITY_CONFLICT"):
        refuse_competing_sealed_operation(operation_root, session, "daily_research_session_operation:" + "ff" * 32)
    assert list(operation_root.glob("*/*")) == [operation_dir]

    run_root = tmp_path / "runs"
    run_identity = f"daily_producer_run:{RUN}"
    run_dir = run_root / session / RUN
    run_dir.mkdir(parents=True)
    (run_dir / "run_manifest.json").write_text(json.dumps({
        "run_identity": run_identity,
        "target_market_session": session,
        "daily_session_operation": {"identity": operation_identity},
    }), encoding="utf-8")
    (run_root / "LATEST_COMPLETED_RUN.json").write_text(json.dumps({
        "session": session,
        "run_identity": run_identity,
        "daily_session_operation_identity": operation_identity,
    }), encoding="utf-8")
    producer.refuse_competing_sealed_run(run_root, session, run_identity, operation_identity)
    with pytest.raises(producer.DailyProducerError, match="SEALED_PRODUCER_RUN_IDENTITY_CONFLICT"):
        producer.refuse_competing_sealed_run(run_root, session, "daily_producer_run:" + "11" * 32, operation_identity)
    (run_root / "LATEST_COMPLETED_RUN.json").write_text(json.dumps({
        "session": session,
        "run_identity": "daily_producer_run:" + "11" * 32,
        "daily_session_operation_identity": operation_identity,
    }), encoding="utf-8")
    with pytest.raises(producer.DailyProducerError, match="SEALED_LATEST_COMPLETED_RUN_CONFLICT"):
        producer.refuse_competing_sealed_run(run_root, session, run_identity, operation_identity)
    assert (run_dir / "run_manifest.json").is_file()
    assert json.loads((run_root / "LATEST_COMPLETED_RUN.json").read_text(encoding="utf-8"))["run_identity"] != run_identity
