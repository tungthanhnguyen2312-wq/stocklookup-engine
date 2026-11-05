"""Offline session closure qualification, including native split-workspace paths."""
import json
from pathlib import Path
import subprocess

import pytest

from tools import vault_boundary_emit as e
from tools import vault_snapshot as v
from tools.vault_post_daily_adapter import qualified_boundary, native_reference

SESSION = "2026-11-04"


def write(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(v.canonical(value))
    return path


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), *args], capture_output=True, check=True).stdout


@pytest.fixture
def completed(tmp_path, request):
    from daily_research_session_operations import _identity
    from daily_producer_pipeline import _run_identity
    from prospective_t0_seal_index import publish
    import prospective_decision_retention as retention

    source = tmp_path / "source"
    repo, retained = source / "repo", source / "retained"
    repo.mkdir(parents=True)
    git(repo, "init", "-b", "main")
    git(repo, "config", "user.email", "fixture@example.invalid")
    git(repo, "config", "user.name", "Offline fixture")
    input_doc = dict(records={"ABC": {"value": 1}})
    digest = v.digest(v.canonical(input_doc))
    input_id = "input:" + digest
    input_path = write(repo / f"operations-review/frozen/{SESSION}/input.json",
                       dict(input_doc, artifact_identity=input_id, artifact_sha256=digest))
    from pending_session_input_freeze import REQUIRED_INPUT_KEYS
    input_ref = input_path.relative_to(repo).as_posix()
    selection = {key: dict(path=input_ref, artifact_identity=input_id) for key in REQUIRED_INPUT_KEYS}
    registry = dict(sessions={SESSION: selection}, completed_sessions={SESSION: dict(
        status="COMPLETED_RETAINED_EVIDENCE", trading_day_valid=True,
        frozen_input_identities={key: input_id for key in selection})})
    write(repo/e.REGISTRY, registry)
    git(repo, "add", ".")
    git(repo, "commit", "-m", "Committed session")
    operation = dict(market_session=SESSION, input_artifacts={key: dict(artifact_identity=input_id) for key in selection})
    if getattr(request, "param", False):
        operation["input_artifacts"]["macro"] = dict(artifact_identity=input_id)
    operation["operation_identity"] = op = _identity(operation)
    op_path = write(retained/f"{e.OPERATIONS}/{SESSION}/{op.split(':')[-1]}/run_manifest.json", operation)
    write(op_path.parent/"product.json", {"immutable": "product"})
    if "macro" in operation["input_artifacts"]:
        write(op_path.parent/"current_macro_regime_artifact.json", dict(input_doc, artifact_identity=input_id, artifact_sha256=digest))
    plan = dict(items=[dict(input_class=key, artifact_path=input_ref, artifact_identity=input_id) for key in selection])
    if "macro" in operation["input_artifacts"]:
        plan["items"].append(dict(input_class="macro", artifact_identity=input_id))
    run = _run_identity(SESSION, "producer", "consumer", plan, op)
    producer_path = write(retained/f"{e.RUNS}/{SESSION}/{run.split(':')[-1]}/run_manifest.json", dict(
        target_market_session=SESSION, run_identity=run, producer_head="producer", consumer_head="consumer",
        source_plan=plan, daily_session_operation=dict(identity=op)))
    for base in (op_path.parent, producer_path.parent):
        projection = write(base / ("dashboard/" if base == producer_path.parent else "") /
                           "current_decision_cockpit_projection.json", dict(session=SESSION))
        write(base/"ai_research_bundle_manifest.json", dict(files={"current_decision_cockpit_projection.json":
            dict(bytes=projection.stat().st_size, sha256=v.sha(projection))}))
    record = dict(session=SESSION, daily_operation_state="LOCAL_COMPLETE", daily_producer_status="COMPLETED",
                  runtime_release_status="READY", trusted_subset_status="READY",
                  acquisition=dict(resolved_completed_session=SESSION),
                  daily_producer_operation_identity=op, daily_producer_run_identity=run,
                  requested_at="2026-11-04T15:00:00+07:00")
    record_path = write(retained/f"operations-review/canonical-daily-operation-v1/{SESSION}/op-canonical/daily_operation_record.json", record)
    t0_path = write(retained/f"operations-review/prospective-decision-retention-v1/{SESSION}/original/prospective_decision_snapshot.json",
                    dict(requested_at="2026-11-04T15:00:00+07:00", records={"ABC": {"value": "original"}}))
    ref = publish(t0_path, dict(contract_version=retention.CONTRACT_VERSION, decision_count=1,
        snapshot_identity="prospective_decision_snapshot:original", session=SESSION,
        source_integrated_decision_artifact=dict(artifact_identity="iid:original"),
        daily_session_operation_identity=op), {}, created_at="2026-11-04T15:00:00+07:00", file_sha256=v.sha(t0_path))
    handoff = dict(daily_producer=dict(status="COMPLETED", operation_identity=op, run_identity=run),
                   market_session_proof=dict(resolved_completed_session=SESSION),
                   prospective_decision_snapshot=dict(status="RETAINED", identity="prospective_decision_snapshot:original",
                       path=str(t0_path), seal_index={**ref, "status": "RETAINED"}))
    h = write(retained/f"operations-review/canonical-post-close-v1/{SESSION}/session_handoff_bundle.json", handoff)
    for name in ("opportunity_research_bundle.json", "full_universe_bundle_index.json", "dashboard_release_set_index.json"):
        write(h.parent/name, {"session": SESSION})
    return dict(source=source, repo=repo, retained=retained, out=tmp_path/"out",
                t0=t0_path, operation=op_path, producer=producer_path, record=record_path, input=input_path)


def run(fixture, session=SESSION):
    return e.emit(*(fixture[k] for k in ("source", "repo", "retained")), session, fixture["out"])


def test_emit_passes_unchanged_qualifier_and_preserves_every_source_byte(completed):
    before = {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in completed["retained"].rglob("*") if p.is_file()}
    result = run(completed)
    with qualified_boundary(completed["source"], Path(result["boundary"]), result["boundary_sha256"], max_bytes=64*v.CHUNK):
        pass
    boundary = json.loads(Path(result["boundary"]).read_bytes())
    assert boundary["cutoff"] == "2026-11-04T15:00:00+07:00"
    included = {x["relative_path"] for x in boundary["files"]}
    assert all(completed[k].relative_to(completed["source"]).as_posix() in included
               for k in ("t0", "operation", "producer", "record", "input"))
    assert {p: (p.read_bytes(), p.stat().st_mtime_ns) for p in before} == before
    assert run(completed) == result


@pytest.mark.parametrize("completed", [True], indirect=True)
def test_attached_macro_uses_original_materialized_copy(completed):
    result = run(completed)
    boundary = json.loads(Path(result["boundary"]).read_bytes())
    assert any(x["relative_path"].endswith("current_macro_regime_artifact.json") for x in boundary["files"])


def test_uncommitted_session_refused_even_if_working_registry_claims_complete(completed):
    registry_path = completed["repo"]/e.REGISTRY
    doc = json.loads(registry_path.read_bytes())
    for key in ("sessions", "completed_sessions"):
        doc[key]["2026-10-26"] = doc[key][SESSION]
    write(registry_path, doc)
    with pytest.raises(v.Refused, match="absent from committed"):
        run(completed, "2026-10-26")
    assert not completed["out"].exists()


def test_tampered_operation_hash_refused(completed):
    operation = json.loads(completed["operation"].read_bytes())
    operation["injected"] = True
    write(completed["operation"], operation)
    with pytest.raises(v.Refused, match="manifest hash mismatch"):
        run(completed)


def test_tampered_t0_native_hash_refused(completed):
    # Preserve valid JSON and the original inode so native seal/hash checks govern.
    write(completed["t0"], dict(requested_at="2026-11-04T15:00:00+07:00", records={"ABC": {"value": "tampered"}}))
    with pytest.raises(v.Refused, match="T0 native hash"):
        run(completed)


def test_tampered_frozen_artifact_content_hash_refused(completed):
    doc = json.loads(completed["input"].read_bytes())
    doc["records"]["ABC"]["value"] = 2
    write(completed["input"], doc)
    with pytest.raises(v.Refused, match="artifact content hash"):
        run(completed)


@pytest.mark.parametrize("status,identity,admitted", [("UNAVAILABLE", None, True),
                                                     ("READY", None, False),
                                                     ("UNAVAILABLE", "feedback:claimed", False)])
def test_missing_feedback_requires_original_unavailable_proof(completed, status, identity, admitted):
    handoff_path = completed["retained"]/f"operations-review/canonical-post-close-v1/{SESSION}/session_handoff_bundle.json"
    handoff = json.loads(handoff_path.read_bytes())
    missing = str(completed["retained"]/f"operations-review/feedback/{SESSION}/missing.json")
    handoff.update(prospective_decision_feedback_identity=identity,
                   deeper_bundles=dict(prospective_decision_feedback=missing))
    write(handoff_path, handoff)
    write(handoff_path.parent/"opportunity_research_bundle.json", dict(session=SESSION,
          prospective_decision_feedback=dict(path=missing, identity=identity,
                                            status=status, reason_code="FEEDBACK_COMPUTATION_ERROR")))
    if admitted:
        result = run(completed)
        boundary = json.loads(Path(result["boundary"]).read_bytes())
        assert boundary["unavailable_optional_refs"][0]["status"] == "UNAVAILABLE"
        assert not any(x["relative_path"].endswith("missing.json") for x in boundary["files"])
    else:
        with pytest.raises(v.Refused, match="closure file missing"):
            run(completed)


def test_mutable_closure_member_refused(completed):
    write(completed["operation"].parent/"journal.json", {"mutable": True})
    with pytest.raises(v.Refused, match="mutable/ineligible"):
        run(completed)


def test_mutable_selected_row_refused(completed):
    p = completed["repo"]/e.REGISTRY
    doc = json.loads(p.read_bytes())
    doc["completed_sessions"][SESSION]["trading_day_valid"] = False
    write(p, doc)
    with pytest.raises(v.Refused, match="working registry differs"):
        run(completed)


@pytest.mark.parametrize("value", ["../escape", "config/../../escape"])
def test_native_reference_traversal_refused(completed, value):
    with pytest.raises(v.Refused):
        native_reference(completed["source"], value)


def test_native_reference_outside_source_refused(completed):
    with pytest.raises(v.Refused, match="outside source"):
        native_reference(completed["source"], str(completed["out"] / "outside.json"))


def test_output_inside_source_refused(completed):
    completed["out"] = completed["retained"]/"output"
    with pytest.raises(v.Refused, match="disjoint"):
        run(completed)


@pytest.mark.parametrize("records", [{}, [], [{"value": 1}, {"value": 2}], {"ABC": {"value": 1}}])
def test_mapping_and_list_record_hashes_match_existing_canonical_bytes(tmp_path, records):
    payload = dict(contract_version="fixture/v1", records=records)
    expected = v.digest(v.canonical(payload))
    path = write(tmp_path/"artifact.json", dict(payload, artifact_identity="fixture:"+expected,
                                               artifact_sha256=expected))
    meta, digest = e.artifact_digest(path)
    assert digest == expected and meta["artifact_identity"] == "fixture:"+expected
