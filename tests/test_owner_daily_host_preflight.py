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
    assert physical["green_min_bytes"] == preflight.QUALIFIED_PHYSICAL_BYTES
    assert physical["legacy_green_min_bytes"] == 10311071568
    assert result["dimensions"]["commit"]["green_min_bytes"] == preflight.QUALIFIED_COMMIT_BYTES
    assert result["dimensions"]["commit"]["blocked_below_bytes"] < preflight.QUALIFIED_COMMIT_BYTES
    assert result["peak_model"]["monday_measured_peak_bytes"] is None
    observation["available_physical_bytes"] = physical["green_min_bytes"] - 1
    assert preflight.evaluate(observation)["classification"] == "AMBER"
    observation["available_physical_bytes"] += 1
    assert preflight.evaluate(observation)["classification"] == "READY"


def test_physical_green_is_measured_peak_not_job_ceiling():
    # Measured qualified-stage private peak + Owner allowance + the reserve the runtime guard enforces.
    assert preflight.QUALIFIED_PHYSICAL_BYTES == 7464976384 + GIB // 4 + GIB == 8807153664
    assert preflight.QUALIFIED_PHYSICAL_BYTES < preflight.SUPERSEDED_CEILING_PHYSICAL_BYTES
    assert preflight.MEASURED_MAX_RSS_BYTES <= preflight.MEASURED_MAX_PRIVATE_BYTES < 7 * GIB
    guard = (preflight.ROOT / "stocklookup_core/acquisition/feedback_resource_guard.py").read_text(encoding="utf-8")
    assert '("available_physical_bytes", GIB)' in guard  # runtime floor == PHYSICAL_RESERVE_BYTES
    assert "ORDINARY_PROCESS_CEILING_BYTES = 7 * GIB" in guard and "ORDINARY_TREE_CEILING_BYTES = 8 * GIB" in guard
    admission = preflight.evaluate(qualified_observation())["capacity_admission"]
    assert admission["physical_green_basis"] == "MEASURED_MAX_PRIVATE_PLUS_OWNER_ALLOWANCE_PLUS_RUNTIME_ENFORCED_RESERVE"
    assert admission["runtime_physical_floor_bytes"] == preflight.PHYSICAL_RESERVE_BYTES


def test_observed_nov02_clean_desktop_admits_and_busy_desktop_does_not():
    observation = qualified_observation()
    observation["retained"]["iid"]["file_bytes"] = 2392834443
    observation["available_physical_bytes"] = 9700884480  # 2026-11-02 19:46, 9.035 GiB
    result = preflight.evaluate(observation)
    assert result["classification"] == "READY"
    assert result["runtime_capacity_guard_required"] is True
    observation["available_physical_bytes"] = 8383889408  # 7.808 GiB with an agent desktop app open
    assert preflight.evaluate(observation)["classification"] == "AMBER"


@pytest.mark.parametrize("cause", ["source", "larger", "commit", "writer", "provenance", "disk", "pagefile"])
def test_bounded_admission_never_bypasses_other_guards(cause):
    observation = qualified_observation()
    if cause == "source":
        observation["capacity_qualification"]["source_matches"] = False
    elif cause == "larger":
        observation["retained"]["iid"]["file_bytes"] = preflight.QUALIFIED_IID_BYTES + 1
    elif cause == "commit":
        observation["available_commit_bytes"] = preflight.evaluate(observation)["dimensions"]["commit"]["green_min_bytes"] - 1
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
    receipt = json.loads((preflight.ROOT / "config/owner_daily_capacity_qualification.json").read_text(encoding="utf-8"))
    assert receipt["iid_max_bytes"] == preflight.QUALIFIED_IID_BYTES
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


def _live_entry(**overrides):
    entry = {"status": preflight.LIVE_REQUALIFICATION_STATUS, "iid_bytes": 2395425950,
             "iid_raw_sha256": "fc073f46c4e48a98c7e9222b00a7f9e83de1c7d97c05049054d19183c4d5adb1",
             "peak_observed_single_process_rss_bytes": 5473955840}
    entry.update(overrides)
    return entry


def test_live_requalification_extends_bound_only_by_measured_margin_and_cap():
    assert preflight.live_requalified_iid_bytes(None) == preflight.QUALIFIED_IID_BYTES
    assert preflight.live_requalified_iid_bytes([_live_entry()]) == preflight.LIVE_REQUALIFICATION_MAX_IID_BYTES
    tight = _live_entry(peak_observed_single_process_rss_bytes=preflight.MEASURED_MAX_RSS_BYTES - 505)
    assert preflight.live_requalified_iid_bytes([tight]) == 2395425950 + 100
    for bad in (_live_entry(status="OFFLINE"), _live_entry(peak_observed_single_process_rss_bytes=preflight.MEASURED_MAX_RSS_BYTES + 1),
                _live_entry(iid_bytes=True), _live_entry(iid_bytes="2395425950"), _live_entry(iid_raw_sha256=None),
                _live_entry(peak_observed_single_process_rss_bytes=0), "entry"):
        assert preflight.live_requalified_iid_bytes([bad]) == preflight.QUALIFIED_IID_BYTES
    assert preflight.live_requalified_iid_bytes({"a": _live_entry()}) == preflight.QUALIFIED_IID_BYTES


def test_november5_owner_refusal_is_ready_with_live_requalified_receipt():
    observation = qualified_observation()
    # 2026-11-05 21:22 Owner run after reboot: the 11-04 IID is 657,858 bytes above the offline bound.
    observation["retained"]["iid"]["file_bytes"] = 2395425950
    observation.update(available_physical_bytes=10303209472, available_commit_bytes=20162985984)
    legacy = preflight.evaluate(observation)
    assert legacy["classification"] == "AMBER"
    assert legacy["dimensions"]["physical"]["capacity_basis"] == "LEGACY_IID_MODEL"
    observation["capacity_qualification"]["iid_max_bytes"] = preflight.capacity_qualification(preflight.ROOT)["iid_max_bytes"]
    result = preflight.evaluate(observation)
    assert result["classification"] == "READY"
    assert result["runtime_capacity_guard_required"] is True
    assert result["dimensions"]["physical"]["green_min_bytes"] == preflight.QUALIFIED_PHYSICAL_BYTES
    assert result["dimensions"]["commit"]["green_min_bytes"] == preflight.QUALIFIED_COMMIT_BYTES
    assert result["capacity_admission"]["qualified_iid_max_bytes"] == preflight.LIVE_REQUALIFICATION_MAX_IID_BYTES
    observation["available_physical_bytes"] = preflight.QUALIFIED_PHYSICAL_BYTES - 1
    assert preflight.evaluate(observation)["classification"] == "AMBER"


def test_forged_iid_bound_never_exceeds_live_cap_or_bypasses_source_match():
    observation = qualified_observation()
    observation["capacity_qualification"]["iid_max_bytes"] = 10 ** 12
    observation["retained"]["iid"]["file_bytes"] = preflight.LIVE_REQUALIFICATION_MAX_IID_BYTES + 1
    result = preflight.evaluate(observation)
    assert result["capacity_admission"]["qualified_current_scale"] is False
    assert result["dimensions"]["physical"]["capacity_basis"] == "LEGACY_IID_MODEL"
    observation["retained"]["iid"]["file_bytes"] = 2395425950
    observation["capacity_qualification"]["source_matches"] = False
    assert preflight.evaluate(observation)["capacity_admission"]["qualified_current_scale"] is False


def test_receipt_live_requalifications_are_measured_and_capped():
    receipt = json.loads((preflight.ROOT / "config/owner_daily_capacity_qualification.json").read_text(encoding="utf-8"))
    entries = receipt["live_daily_requalifications"]
    assert {e["session"] for e in entries} == {"2026-11-03", "2026-11-04"}
    assert all(e["peak_observed_single_process_rss_bytes"] < preflight.MEASURED_MAX_RSS_BYTES for e in entries)
    assert preflight.capacity_qualification(preflight.ROOT)["iid_max_bytes"] == preflight.LIVE_REQUALIFICATION_MAX_IID_BYTES

def test_offline_financial_capacity_transition_preserves_the_qualified_daily_source():
    import ast
    import re

    from test_daily_lazy_import_closure import daily_reachable
    from tools.check_architecture import module_name

    root = preflight.ROOT
    spec = json.loads((root / "tests/fixtures/offline_financial_capacity_source_transition_v1.json").read_bytes())
    assert spec["scope"] == "EXACT_OFFLINE_FINANCIAL_SOURCE_ENUMERATION_ONLY"
    assert spec["new_capacity_measurement"] is False
    relative = spec["source_path"]
    assert relative == "tools/check_owner_daily_host_preflight.py"
    archive = (root / spec["archive"]).read_bytes().replace(b"\r\n", b"\n")
    active = (root / relative).read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(archive).hexdigest() == spec["prior_sha256_lf"]
    assert hashlib.sha256(active).hexdigest() == spec["active_sha256_lf"]

    prior_tree, active_tree = ast.parse(archive), ast.parse(active)
    scope_name = "OFFLINE_CONDITIONAL_RESEARCH_SOURCES"
    (scope,) = [node for node in active_tree.body if isinstance(node, ast.Assign)
                and any(isinstance(target, ast.Name) and target.id == scope_name for target in node.targets)]
    assert ast.unparse(scope.value.func) == "frozenset"
    assert len(scope.value.args) == 1 and not scope.value.keywords
    assert ast.literal_eval(scope.value.args[0]) == set(spec["offline_paths"])
    active_tree.body.remove(scope)
    (source_paths,) = [node for node in active_tree.body if isinstance(node, ast.FunctionDef)
                       and node.name == "capacity_source_paths"]
    (filter_expr,) = [node for node in ast.walk(source_paths) if isinstance(node, ast.BoolOp)]
    (exclusion,) = [node for node in filter_expr.values if ast.unparse(node) == f"p not in {scope_name}"]
    filter_expr.values.remove(exclusion)
    assert ast.dump(active_tree) == ast.dump(prior_tree)

    def git_blob(path):
        return subprocess.check_output(["git", "show", f"{spec['base_commit']}:{path}"], cwd=root)

    receipt_path = "config/owner_daily_capacity_qualification.json"
    prior_receipt = json.loads(git_blob(receipt_path))
    assert prior_receipt["source_sha256"][relative] == spec["prior_sha256_lf"]
    prior_receipt["source_sha256"][relative] = spec["active_sha256_lf"]
    # Rebuild the current receipt using only the enumerated successor paths.
    live_receipt = json.loads((root / receipt_path).read_bytes())
    corrective = live_receipt["core_ai_fast_path_corrective"]
    assert corrective["new_capacity_measurement"] is False
    assert corrective["changed_source_paths"] == [
        "config/daily_path_launchers.json", "owner_daily_progress.py", "tools/owner_daily_host.py",
        "tools/run_owner_daily.ps1", "tools/run_owner_daily.py", "tools/verify_retention_reader_transition.py"]
    for path in corrective["changed_source_paths"]:
        assert live_receipt["source_sha256"][path] != prior_receipt["source_sha256"][path]
        prior_receipt["source_sha256"][path] = live_receipt["source_sha256"][path]
    prior_receipt["core_ai_fast_path_corrective"] = corrective
    tactical_shadow = live_receipt["tactical_shadow_deferral_corrective"]
    assert tactical_shadow["new_capacity_measurement"] is False
    assert tactical_shadow["owner_decision"].startswith("Approved 2026-11-14: defer the non-voting")
    assert tactical_shadow["changed_source_paths"] == [
        "canonical_daily_operation.py", "config/daily_path_launchers.json", "daily_analysis_pipeline.py",
        "tools/build_owner_compact_research.py", "tools/run_owner_daily.py",
        "tools/verify_retention_reader_transition.py",
    ]
    for path in tactical_shadow["changed_source_paths"]:
        prior_receipt["source_sha256"][path] = live_receipt["source_sha256"][path]
    prior_receipt["tactical_shadow_deferral_corrective"] = tactical_shadow
    hnx = live_receipt["hnx_listed_listing_presence_corrective"]
    assert hnx["base_commit"] == "8b60f92ce7f7576c4b58a7c8c3454495bf995d88"
    assert hnx["scope"] == "HNX_LISTED_CANONICAL_EXCHANGE_FOR_PROSPECTIVE_LISTING_PRESENCE_ONLY"
    assert hnx["stage_qualification"] == "WINDOWS_JOB_GUARDED_RETAINED_CAPTURE_AND_TPLUS1_PRICE_HORIZON_PARITY"
    assert hnx["new_capacity_measurement"] is True
    assert hnx["whole_daily_requalification"] is False
    assert "owner_decision" not in hnx
    capture_path = "stocklookup_core/evidence/prospective_pit_capture.py"
    assert hnx["changed_source_paths"] == [capture_path]
    assert hnx["prior_source_sha256_lf"] == prior_receipt["source_sha256"][capture_path]
    current = (root / capture_path).read_bytes().replace(b"\r\n", b"\n")
    token_mapping = b'    if exchange == "HNX_LISTED":\n        exchange = "HNX"\n'
    assert current.count(token_mapping) == 1
    previous = current.replace(token_mapping, b"")
    assert hashlib.sha256(previous).hexdigest() == hnx["prior_source_sha256_lf"]
    prior_receipt["source_sha256"][capture_path] = hashlib.sha256(current).hexdigest()

    replay = hnx["retained_replay"]
    assert replay["baseline"]["positive_listings"] < replay["candidate"]["positive_listings"] <= replay["listing_rows"]
    assert replay["baseline"]["capture_complete"] < replay["candidate"]["capture_complete"] <= replay["capture_rows"]
    assert replay["tplus1_horizon_rows"] == replay["capture_rows"]
    for run in (replay["baseline"], replay["candidate"]):
        assert 0 < run["peak_job_private_bytes"] < preflight.MEASURED_MAX_RSS_BYTES
        assert 0 < run["guard_wall_seconds"] < 120
    prior_receipt["hnx_listed_listing_presence_corrective"] = hnx
    rebaseline = live_receipt["freeze_inventory_rebaseline_corrective"]
    sync_path = "tools/sync_producer_release.py"
    assert rebaseline["changed_source_paths"] == [sync_path]
    assert rebaseline["scope"] == "EXPLICIT_OFFLINE_FREEZE_INVENTORY_REBASELINE_ONLY"
    assert rebaseline["new_capacity_measurement"] is False
    assert rebaseline["prior_source_sha256_lf"] == prior_receipt["source_sha256"][sync_path]
    old_sync = subprocess.check_output(["git", "show", f"7d2c6915a84a9576c5783336ddca13995aaeb13f:{sync_path}"], cwd=root)
    new_sync = (root / sync_path).read_bytes().replace(b"\r\n", b"\n")
    assert hashlib.sha256(old_sync).hexdigest() == rebaseline["prior_source_sha256_lf"]

    def sync_body(raw):
        return next(node for node in ast.parse(raw).body
                    if isinstance(node, ast.FunctionDef) and node.name == "sync_producer_release")

    assert ast.dump(sync_body(old_sync)) == ast.dump(sync_body(new_sync))
    assert module_name(sync_path) not in daily_reachable(root)
    for path in preflight.capacity_source_paths(root):
        if path != sync_path and path.endswith((".py", ".cmd", ".ps1", ".bat")):
            assert b"sync_producer_release" not in (root / path).read_bytes()
    prior_receipt["source_sha256"][sync_path] = hashlib.sha256(new_sync).hexdigest()
    prior_receipt["freeze_inventory_rebaseline_corrective"] = rebaseline

    assert live_receipt == prior_receipt
    assert archive == git_blob(relative)

    offline = set(spec["offline_paths"])
    assert offline == preflight.OFFLINE_CONDITIONAL_RESEARCH_SOURCES
    assert all((root / path).is_file() for path in offline)
    assert not offline.intersection(preflight.capacity_source_paths(root))
    assert not {module_name(path) for path in offline}.intersection(daily_reachable(root))
    # Cover string-based import and launch registrations, including basename-only
    # dispatch. The compact research command is independently checked as offline-only.
    compact_command = "tools/build_owner_compact_research.py"
    assert module_name(compact_command) not in daily_reachable(root)
    names = re.compile(rb"\b(?:" + b"|".join(re.escape(Path(path).stem.encode()) for path in sorted(offline)) + rb")\b")
    for path in preflight.capacity_source_paths(root):
        if path not in (relative, compact_command):
            assert not names.search((root / path).read_bytes()), path


def test_offline_edits_keep_receipt_but_runtime_import_or_new_runtime_file_invalidates_it(tmp_path, monkeypatch):
    offline = "tools/build_conditional_research_cases.py"
    runtime = "daily_analysis_pipeline.py"
    (tmp_path / "tools").mkdir()
    (tmp_path / "config").mkdir()
    (tmp_path / offline).write_bytes(b"# offline case builder\n")
    protected = tmp_path / runtime
    protected.write_bytes(b"# qualified daily\n")
    receipt = {"source_sha256": {runtime: hashlib.sha256(protected.read_bytes()).hexdigest()}}
    (tmp_path / "config/owner_daily_capacity_qualification.json").write_text(json.dumps(receipt), encoding="utf-8")
    tracked = [runtime, offline]
    monkeypatch.setattr(preflight, "_git", lambda *_: "\n".join(tracked))
    assert preflight.capacity_qualification(tmp_path)["source_matches"]
    (tmp_path / offline).write_bytes(b"raise RuntimeError('offline only')\n")
    assert preflight.capacity_qualification(tmp_path)["source_matches"]
    protected.write_bytes(b"from tools import build_conditional_research_cases\n")
    assert not preflight.capacity_qualification(tmp_path)["source_matches"]
    protected.write_bytes(b"# qualified daily\n")
    tracked.append("tools/other_offline_tool.py")
    (tmp_path / tracked[-1]).write_bytes(b"# still needs review\n")
    assert not preflight.capacity_qualification(tmp_path)["source_matches"]
