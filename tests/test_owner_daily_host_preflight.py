from __future__ import annotations

import copy
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import sys

import pytest

from tools import check_owner_daily_host_preflight as preflight
from tools import run_owner_daily as owner

GIB = preflight.GIB


def safe_observation():
    return {"available_commit_bytes": 12 * GIB, "available_physical_bytes": 7 * GIB,
            "commit_limit_bytes": 32 * GIB, "committed_bytes": 20 * GIB, "c_free_bytes": 26 * GIB,
            "pagefiles": [{"AllocatedBaseSize": 16000, "CurrentUsage": 1000, "PeakUsage": 2000}],
            "writer_observation": "OBSERVED", "active_writers": [], "largest_processes": [],
            "repository": {"head_sha": "abc", "main_sha": "abc", "writer_state_observed": True,
                           "worktrees": [{"index_lock_present": False, "tracked_dirty": False}]},
            "retained": {"iid": {"file_bytes": int(1.3 * GIB), "session": "2026-10-02"},
                         "t0": {"file_bytes": None}}}


def test_green_ready_and_deterministic_without_t0():
    observation = safe_observation()
    result = preflight.evaluate(observation)
    assert result == preflight.evaluate(copy.deepcopy(observation))
    assert result["classification"] == "READY"
    assert "HOST_PREFLIGHT_READY" in result["reasons"]
    assert result["peak_model"]["peak_basis"] == "MODELED_FROM_RETAINED_CURRENT_MAIN"
    assert result["peak_model"]["monday_measured_peak_bytes"] is None


@pytest.mark.parametrize("field,value,classification,reason", [
    ("available_commit_bytes", 10 * GIB, "AMBER", "COMMIT_HEADROOM_LOW"),
    ("available_physical_bytes", 4 * GIB, "AMBER", "PHYSICAL_HEADROOM_LOW"),
    ("available_physical_bytes", 3 * GIB, "AMBER", "PHYSICAL_HEADROOM_LOW"),
    ("c_free_bytes", 20 * GIB, "AMBER", "DISK_HEADROOM_LOW"),
    ("available_commit_bytes", 8 * GIB, "BLOCKED", "COMMIT_HEADROOM_BLOCKED"),
    ("available_physical_bytes", 2 * GIB, "BLOCKED", "PHYSICAL_HEADROOM_BLOCKED"),
    ("c_free_bytes", 16 * GIB, "BLOCKED", "DISK_HEADROOM_BLOCKED"),
    ("available_commit_bytes", None, "BLOCKED", "COMMIT_HEADROOM_BLOCKED"),
    ("available_physical_bytes", None, "BLOCKED", "PHYSICAL_HEADROOM_BLOCKED"),
    ("c_free_bytes", None, "BLOCKED", "DISK_HEADROOM_BLOCKED"),
])
def test_resource_bands(field, value, classification, reason):
    observation = safe_observation()
    observation[field] = value
    result = preflight.evaluate(observation)
    assert result["classification"] == classification
    assert reason in result["reasons"]


@pytest.mark.parametrize("field,green,floor", [
    ("available_commit_bytes", 12.0, 9.2), ("available_physical_bytes", 6, 2.5), ("c_free_bytes", 25, 17)])
def test_exact_band_boundaries(field, green, floor):
    observation = safe_observation()
    observation[field] = int(green * GIB)
    assert preflight.evaluate(observation)["classification"] == "READY"
    observation[field] = int(green * GIB) - 1
    assert preflight.evaluate(observation)["classification"] == "AMBER"
    observation[field] = int(floor * GIB)
    assert preflight.evaluate(observation)["classification"] == "AMBER"
    observation[field] = int(floor * GIB) - 1
    assert preflight.evaluate(observation)["classification"] == "BLOCKED"


@pytest.mark.parametrize("unknown", ["pagefiles", "model", "main"])
def test_optional_unknowns_require_operator_action(unknown):
    observation = safe_observation()
    reason = {"pagefiles": "PAGEFILE_STATE_UNKNOWN", "model": "SCALE_MODEL_UNAVAILABLE",
              "main": "CURRENT_MAIN_PROVENANCE_UNQUALIFIED"}[unknown]
    if unknown == "model":
        observation["retained"]["iid"]["file_bytes"] = None
    elif unknown == "main":
        observation["repository"]["main_sha"] = None
    else:
        observation[unknown] = None
    result = preflight.evaluate(observation)
    assert result["classification"] == "AMBER"
    assert result["operator_action_required"] is True
    assert reason in result["reasons"]


@pytest.mark.parametrize("cause", ["process", "index_lock", "unknown_process", "unknown_git"])
def test_concurrent_or_unobservable_writer_blocks(cause):
    observation = safe_observation()
    if cause == "process":
        observation["active_writers"] = [{"pid": 32}]
    elif cause == "index_lock":
        observation["repository"]["worktrees"][0]["index_lock_present"] = True
    elif cause == "unknown_process":
        observation["writer_observation"] = "UNKNOWN"
    else:
        observation["repository"]["writer_state_observed"] = False
    assert preflight.evaluate(observation)["classification"] == "BLOCKED"


def test_larger_iid_scales_memory_bands_without_weakening_baseline():
    observation = safe_observation()
    observation["retained"]["iid"]["file_bytes"] = 2 * GIB
    result = preflight.evaluate(observation)
    assert result["peak_model"]["modeled_peak_bytes"] == int(5.05 * 2 * GIB)
    assert result["dimensions"]["commit"]["green_min_bytes"] > 12.0 * GIB
    assert result["classification"] == "BLOCKED"
    observation["retained"]["iid"]["file_bytes"] = 100
    assert preflight.evaluate(observation)["dimensions"]["commit"]["green_min_bytes"] == int(12.0 * GIB)


def test_final_benchmark_provenance_and_other_bands_unchanged():
    result = preflight.evaluate(safe_observation())
    assert result["dimensions"]["physical"]["green_min_bytes"] == 6 * GIB
    assert result["dimensions"]["physical"]["blocked_below_bytes"] == int(2.5 * GIB)
    assert result["dimensions"]["disk"]["green_min_bytes"] == 25 * GIB
    assert result["dimensions"]["disk"]["blocked_below_bytes"] == 17 * GIB
    model = result["peak_model"]
    assert model["revised_daily_child_working_band_bytes"] == [int(6.5 * GIB), 8 * GIB]
    assert model["working_band_high_end_is_floor_not_ceiling"] is True
    assert model["provenance"] == "OWNER_FINAL_REAL_SCALE_RETAINED_BENCHMARK_2026_10_04"
    assert model["monday_measured_peak_bytes"] is None


def test_process_inventory_excludes_own_wrapper_and_never_prints_arguments(tmp_path):
    def process(pid, parent, name, command, memory=100):
        return dict(ProcessId=pid, ParentProcessId=parent, Name=name, CommandLine=command, WorkingSetSize=memory)
    rows = [process(1, 0, "powershell.exe", "run_owner_daily.ps1"),
            process(2, 1, "python.exe", "run_owner_daily.py"),
            process(3, 0, "python.exe", "daily_analysis_pipeline.py --secret DONT_EMIT"),
            process(4, 0, "python.exe", "unrelated.py"),
            process(5, 0, "python.exe", 'tools/check_owner_daily_host_preflight.py'),
            process(6, 0, "python.exe", 'C:/Projects/stock-core-private/tools/writer.py --token DONT_EMIT')]
    result = preflight.process_summary(rows, tmp_path, own_pid=2)
    assert [p["pid"] for p in result["active_writers"]] == [3, 6]
    assert "DONT_EMIT" not in json.dumps(result)
    assert "CommandLine" not in json.dumps(result)


def test_unobservable_runtime_process_is_not_claimed_writer_free(tmp_path):
    result = preflight.process_summary([dict(ProcessId=9, ParentProcessId=0, Name="python.exe",
                                            CommandLine=None, WorkingSetSize=50)], tmp_path, own_pid=2)
    assert result["writer_observation"] == "UNKNOWN"


@pytest.mark.skipif(sys.platform != "win32", reason="Windows local CIM probe")
def test_windows_inventory_real_probe_is_read_only_and_usable():
    result = preflight.windows_inventory()
    assert isinstance(result["processes"], list) and result["processes"]
    assert isinstance(result["pagefiles"], list)


def test_retained_inventory_stats_only_and_chooses_latest_largest(tmp_path, monkeypatch):
    paths = [
        "operations-review/canonical-post-close-v1/2026-10-02/enrichment/integrated_investment_decision_product.json",
        "operations-review/integrated-investment-decision-product-v1-20261002/integrated_investment_decision_product_artifact.json",
        "operations-review/integrated-investment-decision-product-v1-20260903/integrated_investment_decision_product_artifact.json",
        "operations-review/prospective-decision-retention-v1/2026-09-08/hash/prospective_decision_snapshot.json"]
    for p, length in zip(paths, [10, 20, 40, 30]):
        path = tmp_path / p
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'x' * length)
    monkeypatch.setattr(Path, "read_bytes", lambda *a: pytest.fail("must not read artifact"))
    monkeypatch.setattr(Path, "read_text", lambda *a, **k: pytest.fail("must not load artifact"))
    result = preflight.retained_sizes(tmp_path)
    assert result["iid"]["session"] == "2026-10-02"
    assert result["iid"]["file_bytes"] == 20
    assert result["t0"]["file_bytes"] == 30


def test_git_provenance_is_local_read_only(tmp_path):
    subprocess.run(["git", "init", "-q", "-b", "main", str(tmp_path)], check=True)
    subprocess.run(["git", "-C", str(tmp_path), "-c", "user.name=Test", "-c", "user.email=test@example.com",
                    "commit", "--allow-empty", "-qm", "fixture"], check=True)
    result = preflight.repository_observation(tmp_path)
    assert result["main_sha"] == result["head_sha"]
    assert result["ref_basis"] == "LOCAL_REFS_NO_FETCH"
    assert result["writer_state_observed"]


def test_tool_no_network_no_repository_or_evidence_writes(tmp_path, monkeypatch, capsys):
    artifact = tmp_path / "evidence.json"
    artifact.write_bytes(b'protected')
    before = {str(p): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
              for p in tmp_path.rglob('*') if p.is_file()}
    monkeypatch.setattr(preflight, "observe", lambda *a: safe_observation())
    monkeypatch.setattr(socket, "socket", lambda *a, **k: pytest.fail("network forbidden"))
    monkeypatch.setattr(Path, "write_text", lambda *a, **k: pytest.fail("write forbidden"))
    monkeypatch.setattr(Path, "write_bytes", lambda *a, **k: pytest.fail("write forbidden"))
    assert preflight.main(["--root", str(tmp_path)]) == 0
    assert json.loads(capsys.readouterr().out)["contract_version"] == preflight.CONTRACT_VERSION
    assert before == {str(p): (p.stat().st_mtime_ns, hashlib.sha256(p.read_bytes()).hexdigest())
                      for p in tmp_path.rglob('*') if p.is_file()}


@pytest.mark.parametrize("classification", ["BLOCKED", "AMBER"])
def test_launcher_stops_before_child_for_nonready(tmp_path, monkeypatch, classification):
    monkeypatch.setattr(preflight, "check", lambda *a: {"classification": classification, "operator_guidance": preflight.GUIDANCE})
    monkeypatch.setattr(owner.subprocess, "Popen", lambda *a, **k: pytest.fail("must not launch"))
    with pytest.raises(owner.OwnerDailyError, match="OWNER_DAILY_HOST_PREFLIGHT_" + classification):
        owner._run_daily(tmp_path, tmp_path)


def test_ready_preserves_canonical_child_gate_failure(tmp_path, monkeypatch):
    monkeypatch.setattr(preflight, "check", lambda *a: {"classification": "READY"})
    class Process:
        def wait(self):
            return 7  # Existing canonical gate still refuses.
    def launch(argv, **kwargs):
        assert argv[2:] == ["daily_analysis_pipeline.py", "--runtime-root", str(tmp_path), "--canonical-post-close"]
        return Process()
    monkeypatch.setattr(owner.subprocess, "Popen", launch)
    with pytest.raises(owner.OwnerDailyError, match="CANONICAL_DAILY_EXIT_7"):
        owner._run_daily(tmp_path, tmp_path)


def test_nonwindows_standalone_fails_closed_without_network_or_bytecode(tmp_path):
    if sys.platform == "win32":
        pytest.skip("POSIX unsupported-host check")
    result = subprocess.run([sys.executable, str(Path(preflight.__file__)), "--root", str(tmp_path)],
                            capture_output=True, text=True, timeout=30)
    assert result.returncode == 3
    assert json.loads(result.stdout)["classification"] == "BLOCKED"
    assert list(tmp_path.iterdir()) == []


def qualified_observation():
    observation = safe_observation()
    observation.update(available_physical_bytes=10193186816, available_commit_bytes=24732172288,
                       capacity_qualification={"source_matches": True, "profile": "PR195_CURRENT_SCALE_BOUNDED_V1"})
    observation["retained"]["iid"]["file_bytes"] = 2382095742
    return observation


def test_observed_oct27_condition_admits_only_with_compensating_guard():
    observation = qualified_observation()
    result = preflight.evaluate(observation)
    assert result["classification"] == "READY"
    assert result["runtime_capacity_guard_required"] is True
    physical = result["dimensions"]["physical"]
    assert physical["green_min_bytes"] == int(9.25 * GIB)
    assert physical["legacy_green_min_bytes"] == 10311071568
    assert result["dimensions"]["commit"]["green_min_bytes"] == 20622143137
    assert result["peak_model"]["monday_measured_peak_bytes"] is None
    observation["available_physical_bytes"] = physical["green_min_bytes"] - 1
    assert preflight.evaluate(observation)["classification"] == "AMBER"
    observation["available_physical_bytes"] += 1
    assert preflight.evaluate(observation)["classification"] == "READY"


@pytest.mark.parametrize("cause", ["source", "larger", "commit", "writer", "provenance", "disk", "pagefile"])
def test_bounded_admission_never_bypasses_other_guards(cause):
    observation = qualified_observation()
    if cause == "source":
        observation["capacity_qualification"]["source_matches"] = False
    elif cause == "larger":
        observation["retained"]["iid"]["file_bytes"] += 1
    elif cause == "commit":
        observation["available_commit_bytes"] = 20622143136
    elif cause == "writer":
        observation["active_writers"] = [{"pid": 17}]
    elif cause == "provenance":
        observation["repository"]["head_sha"] = "candidate"
    elif cause == "disk":
        observation["c_free_bytes"] = 24 * GIB
    else:
        observation["pagefiles"] = None
    result = preflight.evaluate(observation)
    assert result["classification"] != "READY"
    if cause in {"source", "larger"}:
        assert not result["runtime_capacity_guard_required"]
        assert result["dimensions"]["physical"]["capacity_basis"] == "LEGACY_IID_MODEL"


def test_source_receipt_matches_candidate_and_refuses_tampering(tmp_path, monkeypatch):
    assert preflight.capacity_qualification(preflight.ROOT)["source_matches"]
    (tmp_path / "config").mkdir()
    source = tmp_path / "runtime.py"
    source.write_bytes(b"original\r\n")
    receipt = {"source_sha256": {"runtime.py": hashlib.sha256(b"original\n").hexdigest()}}
    (tmp_path / "config/owner_daily_capacity_qualification.json").write_text(json.dumps(receipt))
    monkeypatch.setattr(preflight, "capacity_source_paths", lambda root: ["runtime.py"])
    assert preflight.capacity_qualification(tmp_path)["source_matches"]
    source.write_bytes(b"changed\n")
    assert not preflight.capacity_qualification(tmp_path)["source_matches"]
    source.unlink()
    assert not preflight.capacity_qualification(tmp_path)["source_matches"]


def test_source_fingerprint_excludes_only_noncode_and_normal_session_registry(monkeypatch, tmp_path):
    monkeypatch.setattr(preflight, "_git", lambda *a: "\n".join([
        "runtime.py", "tools/run_owner_daily.py", "config/policy.json",
        "config/daily_research_session_input_registry.json",
        "config/owner_daily_capacity_qualification.json", "tests/fixture.json", "docs/state.json"]))
    assert preflight.capacity_source_paths(tmp_path) == [
        "config/policy.json", "runtime.py", "tools/run_owner_daily.py"]


def test_bounded_ready_requires_strict_runner_and_propagates_failure(tmp_path, monkeypatch):
    from stocklookup_core.acquisition import feedback_resource_guard as guard
    host = preflight.evaluate(qualified_observation())
    monkeypatch.setattr(preflight, "check", lambda *a: host)
    monkeypatch.setattr(owner.subprocess, "Popen", lambda *a, **k: pytest.fail("no unguarded fallback"))
    def refused(*a, **k):
        assert k["memory_probe"] is preflight.windows_memory
        raise OSError("DAILY_CAPACITY_RESERVE_LOW")
    monkeypatch.setattr(guard, "run_capacity_guarded", refused)
    with pytest.raises(owner.OwnerDailyError, match="OWNER_DAILY_CAPACITY_GUARD"):
        owner._run_daily(tmp_path, tmp_path)


CURRENT_IID_BYTES = 2394768092


def current_scale_host(**updates):
    observation = qualified_observation()
    observation["retained"]["iid"]["file_bytes"] = CURRENT_IID_BYTES
    observation["available_physical_bytes"] = preflight.MEASUREMENT_PHYSICAL_BYTES
    observation["available_commit_bytes"] = preflight.MEASUREMENT_COMMIT_BYTES
    observation.update(updates)
    return preflight.evaluate(observation)


def test_kernel_budget_matches_existing_ceilings_and_reserves():
    tree = 6 * GIB + (3 * GIB) // 4
    assert preflight.MEASUREMENT_TREE_BYTES == tree == 7247757312
    assert preflight.MEASUREMENT_PROCESS_BYTES == 7 * GIB
    assert preflight.MEASUREMENT_PHYSICAL_BYTES == tree + GIB // 4 + GIB == 8 * GIB
    assert preflight.MEASUREMENT_COMMIT_BYTES == tree + 2 * GIB
    assert preflight.QUALIFIED_PHYSICAL_BYTES == int(9.25 * GIB)
    assert preflight.QUALIFIED_IID_BYTES == 2382095742
    host = current_scale_host()
    admission = preflight.producer_seal_measurement_admission(host)
    assert admission["tree_ceiling_bytes"] == tree
    assert admission["process_ceiling_bytes"] == 7 * GIB
    assert admission["physical_reserve_bytes"] == GIB
    assert admission["commit_reserve_bytes"] == 2 * GIB
    assert admission["owner_allowance_bytes"] == GIB // 4
    assert admission["qualified_current_scale"] is False
    assert host["capacity_admission"]["child_tree_commit_ceiling_bytes"] == 8 * GIB
    assert host["capacity_admission"]["child_process_commit_ceiling_bytes"] == 7 * GIB
    assert host["dimensions"]["physical"]["green_min_bytes"] == 10365924740


def test_current_iid_keeps_legacy_ordinary_gate_and_refuses_arithmetic_extension():
    result = current_scale_host(available_physical_bytes=20 * GIB, available_commit_bytes=30 * GIB)
    assert result["classification"] == "READY"
    assert result["capacity_admission"]["qualified_current_scale"] is False
    assert result["runtime_capacity_guard_required"] is False
    assert result["dimensions"]["physical"]["capacity_basis"] == "LEGACY_IID_MODEL"
    assert result["dimensions"]["physical"]["green_min_bytes"] == 10365924740
    assert result["dimensions"]["commit"]["green_min_bytes"] == 20731849481
    admission = preflight.producer_seal_measurement_admission(result)
    assert admission["admitted"] is True
    assert admission["tree_ceiling_bytes"] == preflight.MEASUREMENT_TREE_BYTES
    assert admission["process_ceiling_bytes"] == 7 * GIB
    assert admission["qualified_current_scale"] is False
    assert admission["iid_max_extended"] is False
    assert admission["legacy_delta_bytes"] == 63995367
    assert admission["process_slack_above_measured_peak_bytes"] == 51216384
    assert admission["arithmetic_extension_refused"] is True


def test_measurement_admission_uses_kernel_budget_without_replacing_ordinary_gates():
    short_physical = current_scale_host(available_physical_bytes=preflight.MEASUREMENT_PHYSICAL_BYTES - 1)
    refused = preflight.producer_seal_measurement_admission(short_physical)
    assert refused["admitted"] is False
    assert refused["reasons"] == ["MEASUREMENT_PHYSICAL_BUDGET_LOW"]
    assert short_physical["dimensions"]["physical"]["green_min_bytes"] == 10365924740
    short_commit = current_scale_host(available_commit_bytes=preflight.MEASUREMENT_COMMIT_BYTES - 1)
    assert preflight.producer_seal_measurement_admission(short_commit)["reasons"] == ["MEASUREMENT_COMMIT_BUDGET_LOW"]


@pytest.mark.parametrize("cause", ["source", "writer", "unknown", "provenance"])
def test_measurement_admission_keeps_writer_and_receipt_guards(cause):
    updates = {}
    if cause == "provenance":
        updates["repository"] = {"head_sha": "feature", "main_sha": "main", "writer_state_observed": True,
                                 "worktrees": [{"index_lock_present": False}]}
    host = current_scale_host(**updates)
    if cause == "source":
        host["observations"]["capacity_qualification"]["source_matches"] = False
    elif cause == "writer":
        host["observations"]["active_writers"] = [{"pid": 17}]
    elif cause == "unknown":
        host["observations"]["writer_observation"] = "UNKNOWN"
    admission = preflight.producer_seal_measurement_admission(host)
    if cause == "provenance":
        # Feature-branch provenance and the legacy commit floor do not gate the measurement.
        assert host["classification"] == "BLOCKED"
        assert "CURRENT_MAIN_PROVENANCE_UNQUALIFIED" in host["reasons"]
        assert admission["admitted"] is True
        assert admission["qualified_current_scale"] is False
        return
    assert admission["admitted"] is False
    assert admission["qualified_current_scale"] is False
    expected = {"source": "SOURCE_RECEIPT_MISMATCH", "writer": "CONCURRENT_WRITER_PRESENT",
                "unknown": "WRITER_STATE_UNKNOWN"}[cause]
    assert expected in admission["reasons"]
