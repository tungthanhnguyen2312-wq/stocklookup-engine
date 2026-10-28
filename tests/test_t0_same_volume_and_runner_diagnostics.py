"""C1 same-volume T0 staging and C2 runner failure receipts. No historical T0 writes."""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

import prospective_decision_retention as retention
from canonical_post_close_pipeline import CanonicalPostCloseError, retain_prospective_decision_snapshot
from tests.replay_preseal_producer_seal_runner import (
    observe_child_outcome,
    write_child_exception_receipt,
)


RUNNER = Path(__file__).resolve().parents[1] / "tests" / "replay_preseal_producer_seal_runner.py"


def _streamed_artifact(tmp_path):
    import stocklookup_core.decision.integrated_investment_decision_product as iidp
    from stocklookup_core.evidence.record_artifact_loading import SortedRecordArtifactWriter
    from tests.test_integrated_investment_decision_product import _sample_financial_record, _sample_tactical_record
    tactical = {"artifact_identity": "technical_structure_context/v2:fake", "records": {
        "AAA": _sample_tactical_record()}}
    financial = {"artifact_identity": "financial_analysis_product_integration/v1:fake", "records": {
        "AAA": _sample_financial_record()}}
    path = tmp_path / "iid.json"
    return iidp.build_artifact(
        session="2026-08-28", requested_at="2026-09-02T00:00:00Z",
        technical_structure_artifact=tactical, financial_analysis_artifact=financial,
        record_writer=SortedRecordArtifactWriter(path, newline="\n"))


def _retain(tmp_path, artifact):
    return retain_prospective_decision_snapshot(
        tmp_path, "2026-08-28",
        producer_result={"operation": {"manifest": {"operation_identity": "operation:fixture"}},
                         "run_identity": "run:fixture"},
        enrichment={"integrated_investment_decision_product": {"artifact": artifact}})


def test_production_scratch_and_destination_share_a_volume():
    root = Path("T:/StockLookup/not-created-retained-root")
    scratch = retention.streaming_scratch_dir(root)
    destination = retention.snapshot_path(root, {
        "session": "2026-08-28",
        "snapshot_identity": retention.SNAPSHOT_PREFIX + ("a" * 64),
    })
    assert os.path.splitdrive(str(scratch))[0] == os.path.splitdrive(str(destination))[0] == "T:"
    assert scratch.name == ".streaming"
    assert ".streaming" in destination.parts or scratch.parent == destination.parents[2]
    assert Path(os.environ.get("TEMP", "")) not in scratch.parents


def test_streamed_publish_stays_on_the_destination_volume_and_cleans_staging(tmp_path):
    artifact = _streamed_artifact(tmp_path)
    sealed = tmp_path / "already-sealed" / "prospective_decision_snapshot.json"
    sealed.parent.mkdir()
    sealed.write_bytes(b"do-not-touch")
    result = _retain(tmp_path, artifact)
    published = Path(result["path"])
    scratch = retention.streaming_scratch_dir(tmp_path)
    assert result["status"] == "RETAINED"
    assert published.is_file()
    assert retention._same_volume(scratch, published)
    assert list(scratch.glob("prospective-t0-*")) == []
    assert sealed.read_bytes() == b"do-not-touch"


def test_cross_volume_publish_is_refused_and_cleans_only_staging(tmp_path, monkeypatch):
    artifact = _streamed_artifact(tmp_path)
    sealed = tmp_path / "already-sealed" / "prospective_decision_snapshot.json"
    sealed.parent.mkdir()
    sealed.write_bytes(b"do-not-touch")
    monkeypatch.setattr(retention, "_same_volume", lambda *_args: False)
    with pytest.raises(CanonicalPostCloseError, match="STREAMED_SNAPSHOT_CROSS_VOLUME") as caught:
        _retain(tmp_path, artifact)
    assert "T0_PUBLICATION_FAILED" in str(caught.value)
    assert "RETAINED" not in str(caught.value).split("T0_PUBLICATION_FAILED")[0]
    scratch = retention.streaming_scratch_dir(tmp_path)
    assert list(scratch.glob("prospective-t0-*")) == []
    assert sealed.read_bytes() == b"do-not-touch"
    assert not list((tmp_path / "operations-review" / "prospective-decision-retention-v1").glob("*/*/prospective_decision_snapshot.json"))


def test_replace_across_drives_is_not_a_retained_daily(tmp_path, monkeypatch):
    artifact = _streamed_artifact(tmp_path)
    sealed = tmp_path / "already-sealed" / "prospective_decision_snapshot.json"
    sealed.parent.mkdir()
    sealed.write_bytes(b"do-not-touch")

    def fail(*_args):
        error = OSError(17, "The system cannot move the file to a different disk drive")
        error.winerror = 17
        raise error

    monkeypatch.setattr(retention.os, "replace", fail)
    with pytest.raises(CanonicalPostCloseError, match="WinError 17|Errno 17|cannot move the file") as caught:
        _retain(tmp_path, artifact)
    text = str(caught.value)
    assert text.startswith("REFUSE_CANONICAL_POST_CLOSE:T0_PUBLICATION_FAILED:")
    assert "PROSPECTIVE_SNAPSHOT_RETENTION_FAILED" in text
    assert list(retention.streaming_scratch_dir(tmp_path).glob("prospective-t0-*")) == []
    assert sealed.read_bytes() == b"do-not-touch"


def test_streamed_snapshot_refuses_system_temp(tmp_path, monkeypatch):
    artifact = _streamed_artifact(tmp_path)

    def refuse_default(*_args, **kwargs):
        if kwargs.get("dir") is None:
            raise AssertionError("TEMP_FALLBACK")
        raise AssertionError("mkdtemp should not run")

    monkeypatch.setattr(retention.tempfile, "mkdtemp", refuse_default)
    with pytest.raises(retention.ProspectiveDecisionRetentionError, match="STREAMED_SNAPSHOT_SCRATCH_REQUIRED"):
        retention.build_snapshot(
            session="2026-08-28", operation_identity="operation:fixture", producer_run_identity="run:fixture",
            integrated_artifact=artifact, scratch_dir=None)


def test_child_exception_receipt_is_retained(tmp_path):
    experiment = tmp_path / "raise"
    experiment.mkdir()
    stdout = open(experiment / "child-stdout.log", "wb")
    stderr = open(experiment / "child-stderr.log", "wb")
    try:
        completed = subprocess.run(
            [sys.executable, "-B", "-u", str(RUNNER), "--diagnostic-fixture", "raise", str(experiment)],
            stdout=stdout, stderr=stderr, check=False)
    finally:
        stdout.close()
        stderr.close()
    assert completed.returncode == 1
    receipt = json.loads((experiment / "child-result.json").read_text(encoding="utf-8"))
    assert receipt["status"] == "CHILD_EXCEPTION"
    assert "fixture-child-exception" in receipt["traceback"]
    assert "child-stdout-marker" in (experiment / "child-stdout.log").read_text(encoding="utf-8")
    assert "child-stderr-marker" in (experiment / "child-stderr.log").read_text(encoding="utf-8")
    observed = observe_child_outcome(experiment, returncode=1, guard_reason=None, guard_diagnostics={})
    assert observed["outcome_kind"] == "CHILD_EXCEPTION"
    assert observed["evidence"]["child_result"]
    assert observed["evidence"]["parent_observed_failure"] is None
    assert not (experiment / "parent-observed-failure.json").exists()


def test_child_exit_without_result_is_a_parent_failure(tmp_path):
    experiment = tmp_path / "silent"
    experiment.mkdir()
    stdout = open(experiment / "child-stdout.log", "wb")
    stderr = open(experiment / "child-stderr.log", "wb")
    try:
        completed = subprocess.run(
            [sys.executable, "-B", "-u", str(RUNNER), "--diagnostic-fixture", "silent-exit", str(experiment)],
            stdout=stdout, stderr=stderr, check=False)
    finally:
        stdout.close()
        stderr.close()
    assert completed.returncode == 7
    assert not (experiment / "child-result.json").exists()
    observed = observe_child_outcome(experiment, returncode=7, guard_reason=None, guard_diagnostics={"limit_scope": "NONE"})
    assert observed["outcome_kind"] == "CHILD_EXIT_WITHOUT_RESULT"
    assert observed["returncode"] == 7
    parent = json.loads((experiment / "parent-observed-failure.json").read_text(encoding="utf-8"))
    assert parent["status"] == "PARENT_OBSERVED_FAILURE"
    assert parent["child_result_present"] is False
    assert "silent-stdout" in (experiment / "child-stdout.log").read_text(encoding="utf-8")
    assert not (experiment / "child-result.json").exists()


def test_guard_failures_stay_distinct_and_do_not_invent_a_child_receipt(tmp_path):
    memory = tmp_path / "memory"
    memory.mkdir()
    (memory / "stages.jsonl").write_text(json.dumps({"subtask": "integrated_investment_decision_product", "status": "END"}) + "\n", encoding="utf-8")
    observed = observe_child_outcome(
        memory, returncode=1, guard_reason="DAILY_CAPACITY_MEMORY_LIMIT", guard_diagnostics={"peak_job_committed_bytes": 5})
    assert observed["outcome_kind"] == "MEMORY_LIMIT"
    assert observed["last_completed_stage"] == "integrated_investment_decision_product"
    assert not (memory / "child-result.json").exists()
    guard = tmp_path / "guard"
    guard.mkdir()
    (guard / "child-stderr.log").write_text("ModuleNotFoundError: missing\n", encoding="utf-8")
    imported = observe_child_outcome(guard, returncode=1, guard_reason=None, guard_diagnostics={})
    assert imported["outcome_kind"] == "IMPORT_FAILURE"
    assert not (guard / "child-result.json").exists()
    other = tmp_path / "other"
    other.mkdir()
    refused = observe_child_outcome(
        other, returncode=1, guard_reason="DAILY_CAPACITY_RESERVE_LOW:available_physical_bytes", guard_diagnostics={})
    assert refused["outcome_kind"] == "GUARD_FAILURE"
    assert not (other / "child-result.json").exists()
    write_child_exception_receipt(other, RuntimeError("late"))
    assert json.loads((other / "child-result.json").read_text(encoding="utf-8"))["status"] == "CHILD_EXCEPTION"
