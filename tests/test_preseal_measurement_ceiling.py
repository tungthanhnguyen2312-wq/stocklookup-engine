"""Measurement-only 6.75 GiB ceiling, production identity, and experiment cleanup."""
import json
from pathlib import Path
import subprocess

import pytest

import tests.replay_preseal_producer_seal_runner as runner
from tools import check_owner_daily_host_preflight as preflight


def _admission(**updates):
    host = {
        "tree_ceiling_bytes": preflight.MEASUREMENT_TREE_BYTES,
        "process_ceiling_bytes": preflight.MEASUREMENT_PROCESS_BYTES,
        "physical_reserve_bytes": preflight.MEASUREMENT_PHYSICAL_RESERVE_BYTES,
        "commit_reserve_bytes": preflight.MEASUREMENT_COMMIT_RESERVE_BYTES,
        "owner_allowance_bytes": preflight.MEASUREMENT_OWNER_ALLOWANCE_BYTES,
        "physical_budget_bytes": preflight.MEASUREMENT_PHYSICAL_BYTES,
        "commit_budget_bytes": preflight.MEASUREMENT_COMMIT_BYTES,
        "qualified_current_scale": False,
        "iid_max_extended": False,
    }
    host.update(updates)
    return host


def test_measurement_launch_uses_the_admission_ceiling_only():
    assert runner.measurement_tree_ceiling(_admission()) == preflight.MEASUREMENT_TREE_BYTES
    assert runner.EXPERIMENT.name == "preseal-producer-seal-20261026-r10"
    for changed in (
        {"tree_ceiling_bytes": 8 * preflight.GIB},
        {"process_ceiling_bytes": 6 * preflight.GIB},
        {"physical_reserve_bytes": 0},
        {"commit_reserve_bytes": preflight.GIB},
        {"owner_allowance_bytes": 0},
        {"qualified_current_scale": True},
        {"iid_max_extended": True},
        {"physical_budget_bytes": preflight.MEASUREMENT_PHYSICAL_BYTES - 1},
    ):
        with pytest.raises(OSError, match="MEASUREMENT_CEILING_NOT_THE_ENFORCED_BUDGET"):
            runner.measurement_tree_ceiling(_admission(**changed))


def test_production_identity_detects_a_byte_change(tmp_path):
    iid = tmp_path / "iid.json"
    registry = tmp_path / "registry.json"
    iid.write_bytes(b"iid-v1")
    registry.write_bytes(b"registry-v1")
    before = runner.production_identity_of(iid, registry)
    assert runner.same_production_identity(before, runner.production_identity_of(iid, registry))
    iid.write_bytes(b"iid-v2")
    assert runner.same_production_identity(before, runner.production_identity_of(iid, registry)) is False


def test_sandbox_git_provenance_is_captured_before_subprocess_refusal(tmp_path):
    calls = []
    def reader(path):
        calls.append(path)
        return "a" * 40
    frozen = runner.frozen_git_head_reader([tmp_path], reader)
    assert frozen(tmp_path) == "a" * 40
    assert frozen(tmp_path / "unqualified") is None
    assert calls == [tmp_path]


def test_listing_namespace_has_real_writable_directories_without_source_mutation(tmp_path):
    source = tmp_path / "source"
    (source / "listing-sources").mkdir(parents=True)
    (source / "digest").mkdir()
    original = source / "digest" / "proof.json"
    original.write_bytes(b"original")
    destination = tmp_path / "copy"
    runner.copy_listing_namespace(source, destination)
    for relative in ("listing-sources", "digest"):
        target = destination / relative
        assert target.resolve().is_relative_to(destination.resolve())
        assert not target.is_junction()
        target.mkdir(parents=True, exist_ok=True)
    (destination / "digest" / "proof.json").write_bytes(b"sandbox")
    assert original.read_bytes() == b"original"


def test_screen_fixture_uses_canonical_projection_and_preserves_missing_observations(tmp_path, monkeypatch):
    import canonical_dashboard_runtime_release as runtime
    session = runner.SESSION
    sources = {"descriptive": (tmp_path, {"artifact_identity": "descriptive:fixture", "records": {"AAA": {}, "BBB": {}}}),
               "tactical": (tmp_path, {"records": {}}), "official_universe": (tmp_path, {"records": {}})}
    snapshot = {"snapshot_identity": "snapshot:fixture", "records": {"AAA": {"observations": [{"session": session, "close": 42}]}}}
    monkeypatch.setattr(runtime, "_source_paths", lambda *args: (sources, {}))
    monkeypatch.setattr(runtime, "_p3_snapshot", lambda *args: snapshot)
    (tmp_path / "runtime").mkdir()
    result = runner.prepare_screen_fixture(tmp_path)
    import csv
    with Path(result["path"]).open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    assert [row["ticker"] for row in rows] == ["AAA", "BBB"]
    assert rows[0]["close"] == "42" and rows[0]["date"] == session
    assert rows[1]["close"] == "" and rows[1]["canonical_observation_status"] == "UNAVAILABLE_NO_EXACT_SESSION_OBSERVATION"
    assert result["snapshot_identity"] == "snapshot:fixture"
    assert not list((tmp_path / "runtime").glob("*.tmp"))
    with pytest.raises(RuntimeError, match="ALREADY_EXISTS"):
        runner.prepare_screen_fixture(tmp_path)
    snapshot["records"]["AAA"]["observations"].append({"session": session, "close": 43})
    with pytest.raises(runtime.CanonicalRuntimeReleaseError, match="MULTIPLE_EXACT_OBSERVATIONS"):
        runtime.screen_snapshot_rows(session, sources, snapshot)


def test_manifest_discovery_uses_session_and_digest_and_validates_bindings(tmp_path):
    session = "2026-10-26"
    digest = "a" * 64
    identity = "daily_producer_run:" + digest
    base = tmp_path / "operations-review" / "daily-producer-runs-v1"
    path = base / session / digest / "run_manifest.json"
    path.parent.mkdir(parents=True)
    manifest = {"run_identity": identity, "target_market_session": session,
                "daily_session_operation": {"identity": "operation:fixture"},
                "self_verification": {"status": "PASS"}, "ai_dashboard_parity": {"status": "PASS"}}
    pointer = {"run_identity": identity, "session": session, "daily_session_operation_identity": "operation:fixture"}
    path.write_text(json.dumps(manifest))
    pointer_path = base / "LATEST_COMPLETED_RUN.json"
    pointer_path.write_text(json.dumps(pointer))
    assert runner.completed_producer_manifest(tmp_path, session) == (path, manifest)
    pointer["daily_session_operation_identity"] = "wrong"
    pointer_path.write_text(json.dumps(pointer))
    with pytest.raises(RuntimeError, match="BINDING_FAILED"):
        runner.completed_producer_manifest(tmp_path, session)
    with pytest.raises(RuntimeError, match="MANIFEST_COUNT"):
        runner.completed_producer_manifest(tmp_path, "2026-10-27")


def test_acceptance_refuses_core_only_or_unverified_sandbox_output():
    manifest = {"current_product_projections": {"status": "MATERIALIZED"}}
    outcome = {"seal_boundary": "STOPPED_AFTER_PRODUCER", "iid_reference_parity": True,
               "sandbox_t0": {"status": "VERIFIED"}, "production_unchanged": True, "violations": []}
    assert runner.full_scale_acceptance_ready(outcome, manifest)
    assert not runner.full_scale_acceptance_ready(outcome, {"current_product_projections": {"status": "SKIPPED"}})
    assert not runner.full_scale_acceptance_ready({**outcome, "sandbox_t0": {"status": "FAILED"}}, manifest)
    assert not runner.full_scale_acceptance_ready({**outcome, "violations": ["blocked write"]}, manifest)
    assert not runner.full_scale_acceptance_ready(outcome, None)


def test_experiment_directory_refuses_protected_and_existing_paths(tmp_path):
    with pytest.raises(SystemExit, match="EXPERIMENT_INSIDE_PROTECTED_ROOT"):
        runner.experiment_directory_allowed(runner.PRODUCTION_RETAINED / "new-experiment")
    with pytest.raises(SystemExit, match="EXPERIMENT_INSIDE_PROTECTED_ROOT"):
        runner.experiment_directory_allowed(runner.ROOT / "inside-worktree")
    existing = tmp_path / "already"
    existing.mkdir()
    with pytest.raises(SystemExit, match="EXPERIMENT_ALREADY_EXISTS"):
        runner.experiment_directory_allowed(existing)
    runner.experiment_directory_allowed(tmp_path / "unused-r10")


def test_producer_link_cleanup_removes_the_junction_only(tmp_path):
    target = tmp_path / "target"
    target.mkdir()
    kept = target / "kept.txt"
    kept.write_text("retain", encoding="utf-8")
    link = tmp_path / "link"
    subprocess.check_call(["cmd", "/c", "mklink", "/J", str(link), str(target)], stdout=subprocess.DEVNULL)
    experiment = tmp_path / "experiment"
    experiment.mkdir()
    (experiment / "producer-links.json").write_text(json.dumps([str(link)]), encoding="utf-8")
    runner.remove_producer_links(experiment)
    assert not link.exists()
    assert kept.read_text(encoding="utf-8") == "retain"
