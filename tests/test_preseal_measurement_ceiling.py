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
