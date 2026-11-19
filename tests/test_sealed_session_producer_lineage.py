"""A sealed session reuses its Producer lineage or fails before a second identity exists."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import canonical_daily_operation as cdo
import daily_producer_pipeline as producer
from daily_research_session_operations import refuse_competing_sealed_operation
from flow_price_divergence_shadow import write_immutable
from test_canonical_daily_operation import (
    POST_CLOSE, SESSION, _acquired, _patch_downstream, _run, _working_dates, _write_runtime,
)

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


def _plant_verified(root: Path, session: str, *, plan=None, product_identity=None,
                    macro_identity=None, packet_identity=None, iid_identity=None,
                    producer_head=PRODUCER_HEAD, consumer_head=CONSUMER_HEAD):
    """Plant one seal whose run identity is the real hash of its stored plan."""
    plan = json.loads(json.dumps(plan or {
        "schema_version": "acquisition-plan-test", "target_session": session, "items": [],
    }))
    product_identity = product_identity or ("current_daily_decision_research_product:" + "a1" * 32)
    operation_identity = f"daily_research_session_operation:{OPERATION}"
    run_identity = producer._run_identity(session, producer_head, consumer_head, plan, operation_identity)
    run_digest = run_identity.split(":", 1)[1]
    run_dir = root / "operations-review" / "daily-producer-runs-v1" / session / run_digest
    operation_dir = root / "operations-review" / "daily-research-session-operations-v1" / session / OPERATION
    run_dir.mkdir(parents=True)
    operation_dir.mkdir(parents=True)
    outputs = {"daily_product": product_identity}
    if packet_identity:
        outputs["canonical_decision_packet"] = packet_identity
    if iid_identity:
        outputs["integrated_investment_decision_product"] = iid_identity
    inputs = {}
    if macro_identity:
        inputs["macro"] = {"artifact_identity": macro_identity}
        (operation_dir / "current_macro_regime_artifact.json").write_text(json.dumps({
            "artifact_identity": macro_identity, "retrieved_at": "2026-11-19T10:15:00Z",
        }), encoding="utf-8")
    (operation_dir / "current_daily_decision_research_product_artifact.json").write_text(json.dumps({
        "artifact_identity": product_identity,
        "market_brief": {"coverage": {"same_session_technical_feature_available_count": 1}},
        "high_priority_full_universe_review_set": {"count": 1},
    }), encoding="utf-8")
    (operation_dir / "run_manifest.json").write_text(json.dumps({
        "operation_identity": operation_identity,
        "market_session": session,
        "producer_head": producer_head,
        "consumer_head": consumer_head,
        "input_artifacts": inputs,
        "outputs": outputs,
    }), encoding="utf-8")
    (run_dir / "run_manifest.json").write_text(json.dumps({
        "run_identity": run_identity,
        "target_market_session": session,
        "producer_head": producer_head,
        "consumer_head": consumer_head,
        "source_plan": plan,
        "daily_product_identity": product_identity,
        "daily_session_operation": {"identity": operation_identity},
        "daily_session_shadow_recommendation": {"session": session, "artifact_identity": "daily_session_shadow_recommendation:test"},
    }), encoding="utf-8")
    index_dir = root / "operations-review" / "prospective-decision-retention-v1" / session / SNAPSHOT
    index_dir.mkdir(parents=True)
    (index_dir / "prospective_t0_seal_index.json").write_text(json.dumps({
        "session": session,
        "operation_identity": operation_identity,
        "snapshot_identity": f"prospective_decision_snapshot:{SNAPSHOT}",
    }), encoding="utf-8")
    runs_root = root / "operations-review" / "daily-producer-runs-v1"
    (runs_root / "LATEST_COMPLETED_RUN.json").write_text(json.dumps({
        "session": session,
        "run_identity": run_identity,
        "daily_session_operation_identity": operation_identity,
    }), encoding="utf-8")
    return {"run_identity": run_identity, "operation_identity": operation_identity, "run_dir": run_dir, "operation_dir": operation_dir}


def test_verified_seal_is_reused_and_a_different_payload_fails_closed(tmp_path):
    session = "2026-11-19"
    macro_identity = "current_macro_regime:" + "53" * 32
    planted = _plant_verified(tmp_path, session, macro_identity=macro_identity,
                              packet_identity="current_research_decision_packet:" + "4d" * 32)
    before = {
        path: path.read_bytes()
        for path in planted["operation_dir"].rglob("*") if path.is_file()
    }
    before[planted["run_dir"] / "run_manifest.json"] = (planted["run_dir"] / "run_manifest.json").read_bytes()
    loaded = producer.load_verified_sealed_producer(tmp_path, session)
    assert loaded["reused_sealed_producer"] is True
    assert loaded["run_identity"] == planted["run_identity"]
    assert loaded["operation"]["canonical_decision_packet"] is None
    assert loaded["operation"]["product"]["artifact_identity"].endswith("a1" * 32)
    assert [path for path in (tmp_path / "operations-review" / "daily-producer-runs-v1" / session).iterdir()] == [planted["run_dir"]]
    for path, payload in before.items():
        assert path.read_bytes() == payload

    competing = tmp_path / "competing"
    _plant_verified(competing, session, plan={"schema_version": "acquisition-plan-test", "target_session": session, "items": ["fresh-macro"]})
    manifest_path = next((competing / "operations-review" / "daily-producer-runs-v1" / session).glob("*/run_manifest.json"))
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["source_plan"] = {"schema_version": "acquisition-plan-test", "target_session": session, "items": ["other-cutoff"]}
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    with pytest.raises(producer.DailyProducerError, match="SEALED_PRODUCER_RUN_RECOMPUTE_MISMATCH"):
        producer.load_verified_sealed_producer(competing, session)
    assert len(list((competing / "operations-review" / "daily-producer-runs-v1" / session).iterdir())) == 1


def test_production_recovery_skips_macro_acquire_and_keeps_the_sealed_packet(tmp_path, monkeypatch):
    _patch_downstream(monkeypatch, tmp_path)
    packet_calls = {"n": 0}

    def forbidden_packet(*_args, **_kwargs):
        packet_calls["n"] += 1
        raise AssertionError("sealed packet must not be rebuilt")

    def forbidden_refresh(*_args, **_kwargs):
        raise AssertionError("macro refresh")

    def forbidden_producer(*_args, **_kwargs):
        raise AssertionError("producer rebuild")

    monkeypatch.setattr(cdo, "build_decision_packet", forbidden_packet)
    monkeypatch.setattr(cdo, "refresh_macro_snapshot", forbidden_refresh)
    monkeypatch.setattr(cdo, "run_daily_producer", forbidden_producer)
    packet_identity = "current_research_decision_packet:sealed"
    planted = _plant_verified(
        tmp_path, SESSION,
        macro_identity="current_macro_regime:" + "53" * 32,
        packet_identity=packet_identity,
        iid_identity="integrated_investment_decision_product/v1:test",
    )
    original_runs = sorted(path.name for path in (tmp_path / "operations-review" / "daily-producer-runs-v1" / SESSION).iterdir())
    runtime = tmp_path / "runtime"
    _write_runtime(runtime, SESSION)
    record = cdo.run_canonical_daily_operation(
        tmp_path, runtime, SESSION, now=POST_CLOSE, include_tactical_shadow=False,
        working_dates_evidence=_working_dates(SESSION, "2026-08-27"),
        acquire_fn=lambda *_args, **_kwargs: _acquired(tmp_path, SESSION),
        producer_fn=None,
        runtime_fn=lambda *_args, **_kwargs: {"session": SESSION, "live_count": 889},
        trusted_fn=lambda *_args, **_kwargs: {"session": SESSION, "trusted_subset_ready": True, "records_fingerprint": "fp"},
        out_dir=tmp_path / "operations-review",
    )
    assert record["daily_producer_run_identity"] == planted["run_identity"]
    assert record["decision_packet_identity"] == packet_identity
    assert record["macro_refresh"]["status"] == "SKIPPED_SEALED_PRODUCER_REUSE"
    assert packet_calls["n"] == 0
    assert sorted(path.name for path in (tmp_path / "operations-review" / "daily-producer-runs-v1" / SESSION).iterdir()) == original_runs


def test_empty_volume_context_is_replaced_and_a_real_file_stays_immutable(tmp_path):
    destination = tmp_path / "volume_and_flow_context.json"
    destination.write_bytes(b"")
    artifact = {"artifact_identity": "volume_and_flow_context:recovered", "rows": [1]}
    write_immutable(destination, artifact)
    assert destination.stat().st_size > 0
    assert json.loads(destination.read_text(encoding="utf-8"))["artifact_identity"] == artifact["artifact_identity"]
    with pytest.raises(ValueError, match="IMMUTABLE_ARTIFACT_CONFLICT"):
        write_immutable(destination, {"artifact_identity": "volume_and_flow_context:different"})
    assert json.loads(destination.read_text(encoding="utf-8"))["artifact_identity"] == artifact["artifact_identity"]


RETAINED_NOV19 = Path(r"T:\StockLookup\production-v1\retained-evidence")
NOV19_RUN = "daily_producer_run:fd24ada5d07aaf8b403a2c414a55684739d58b1999e69e2d44bef3229a67ee0c"
NOV19_OPERATION = "daily_research_session_operation:b4f9d43502399d59d92f9fd21c1ef6d4b44a515c308f906d42a417a115921dee"


@pytest.mark.skipif(
    not (RETAINED_NOV19 / "operations-review" / "daily-producer-runs-v1" / "2026-11-19").is_dir(),
    reason="retained 2026-11-19 Producer seal is on the production volume",
)
def test_retained_nov19_seal_recomputes_to_the_original_run_identity():
    loaded = producer.load_verified_sealed_producer(RETAINED_NOV19, "2026-11-19")
    assert loaded["run_identity"] == NOV19_RUN
    assert loaded["operation"]["manifest"]["operation_identity"] == NOV19_OPERATION
    assert loaded["operation"]["product"]["artifact_identity"] == (
        "current_daily_decision_research_product:e37c42dfc98650f793883cf606c9580121f08089e9f9b6d0f84ae1fdadac410a"
    )
    assert loaded["sealed_decision_packet_identity"] == (
        "current_research_decision_packet:4dc8d3f53b0c9c6d4da5ab1c8c269d5eaacfa75d28b0bf1f88b07397e1baaa11"
    )
    assert loaded["operation"]["canonical_decision_packet"] is None
