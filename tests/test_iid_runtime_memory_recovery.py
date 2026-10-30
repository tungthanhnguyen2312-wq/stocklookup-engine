import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest


def test_financial_materialization_identity_streams_exact_stdlib_bytes(monkeypatch):
    import canonical_daily_financial_v2_materialization as materialization
    payload = {'records': {'Z': {'text': 'Việt Nam', 'values': [None, False, -0.0, 1e-9]}, 'A': {}},
               'valuation_balance_sheet_divergence_context': {'records': {'Z': {'value': 123}}},
               'metadata': {'z': 1, 'a': 2}}
    expected = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
        separators=(',', ':'), allow_nan=False).encode('utf-8')).hexdigest()
    monkeypatch.setattr(materialization, '_canonical', lambda *a: pytest.fail('whole-universe Unicode identity buffer'))
    assert materialization._identity({**payload, 'artifact_identity': 'ignored',
        'artifact_sha256': 'ignored', 'requested_at': 'excluded'}) == {
            'artifact_sha256': expected,
            'artifact_identity': materialization.CONTRACT_VERSION + ':' + expected}
    with pytest.raises(ValueError):
        materialization._identity({'records': {'A': {'value': float('nan')}}})


@pytest.mark.parametrize("records", [{}, {"Z": {"text": "Việt Nam", "n": -0.0}, "A": [None, False, 1e-9]}])
def test_history_identity_preserves_original_bytes_and_exclusions(records):
    import market_wide_historical_research_context as history
    payload = {"records": records, "requested_at": "included-in-history-identity", "z": {"unknown": None}}
    expected = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    assert history.content_identity(dict(payload, artifact_identity="ignored", artifact_sha256="ignored")) == {
        "artifact_sha256": expected, "artifact_identity": "market_wide_historical_research_context:" + expected}


def test_history_identity_retains_nonfinite_refusal():
    import market_wide_historical_research_context as history
    with pytest.raises(ValueError):
        history.content_identity({"records": {"A": {"value": float("nan")}}})


@pytest.mark.parametrize("records", [{}, {"Z": {"text": "Việt Nam", "n": -0.0}, "A": [None, False, 1e-9]}])
def test_valuation_verification_identity_preserves_original_bytes(records):
    from stocklookup_core.valuation.current_research_valuation_context import _research_identity
    body = {"records": records, "metadata": {"unknown": None}, "divergence": {"records": {"Z": {}}}}
    expected = hashlib.sha256(json.dumps(body, ensure_ascii=False, sort_keys=True,
        separators=(",", ":"), allow_nan=False).encode("utf-8")).hexdigest()
    assert _research_identity({**body, "requested_at": "excluded", "artifact_identity": "excluded"}, "valuation") == {
        "artifact_identity": "valuation:" + expected, "artifact_sha256": expected}
    with pytest.raises(ValueError):
        _research_identity({"records": {"A": float("inf")}}, "valuation")


def test_pipeline_uses_existing_bounded_loader_without_dropping_input_fields(tmp_path, monkeypatch):
    import canonical_post_close_pipeline as pipeline
    value = {"records": {str(i): {"opaque": "x" * 1024**2, "nested": [None, False, -0.0]}
                         for i in range(18)}, "other": "Việt Nam"}
    path = tmp_path / "source.json"
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(Path, "read_text", lambda *a, **k: pytest.fail("whole-file Unicode buffer"))
    assert pipeline._load(path) == value


def test_capacity_stage_tail_uses_only_this_runs_child_and_tolerates_partial_line(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    from tools.run_owner_daily import _last_capacity_stage
    path = tmp_path / "progress.jsonl"
    def row(run, role, subtask):
        return json.dumps({"run_id": run, "writer_role": role, "subtask": subtask, "session": "2026-10-26"}) + "\n"
    path.write_text("x" * 300000 + "\n" + row("old", "DAILY_CHILD", "old-stage") +
        row("current", "DAILY_CHILD", "enrichment:integrated_investment_decision_product") +
        row("current", "OWNER_PARENT", "failure") + '{"unfinished":', encoding="utf-8")
    stage = _last_capacity_stage(SimpleNamespace(progress_path=path, run_id="current"))
    assert stage["subtask"] == "enrichment:integrated_investment_decision_product"
    assert stage["session"] == "2026-10-26"
    assert _last_capacity_stage(SimpleNamespace(progress_path=path, run_id="absent")) is None


def test_owner_preserves_native_diagnostics_through_capacity_error(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    from tools import run_owner_daily as owner
    from stocklookup_core.acquisition import feedback_resource_guard as guard
    native = {"limit_scope": "PROCESS", "peak_process_committed_bytes": 6123456789,
              "peak_job_committed_bytes": 6123456789}
    def refuse(*args, **kwargs):
        raise guard.DailyCapacityError("DAILY_CAPACITY_MEMORY_LIMIT", native)
    monkeypatch.setattr(guard, "run_capacity_guarded", refuse)
    with pytest.raises(owner.OwnerDailyError) as failure:
        owner._run_daily(tmp_path, tmp_path, host_ready={"classification": "READY", "runtime_capacity_guard_required": True})
    assert failure.value.hint == "DAILY_CAPACITY_MEMORY_LIMIT"
    assert failure.value.capacity_diagnostics == {**native, "last_child_stage": None}


def test_owner_result_retains_capacity_diagnostics_and_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    from tools import run_owner_daily as owner
    diagnostics = {"limit_scope": "JOB", "peak_job_committed_bytes": 7123456789,
                   "last_child_stage": {"subtask": "enrichment:integrated_investment_decision_product"}}
    def refuse(**kwargs):
        raise owner.OwnerDailyError("Canonical Daily", "OWNER_DAILY_CAPACITY_GUARD", "DAILY_CAPACITY_MEMORY_LIMIT",
                                   capacity_diagnostics=diagnostics)
    monkeypatch.setattr(owner, "run_workflow", refuse)
    monkeypatch.setattr(owner, "_auto_resumable_session", lambda *args, **kwargs: None)
    destination = tmp_path / "result.json"
    assert owner.main(["--result-path", str(destination)]) == 1
    result = json.loads(destination.read_text(encoding="utf-8"))
    assert result["status"] == "FAILED" and result["resume_completed_session"] is False
    assert result["capacity_diagnostics"] == diagnostics
