"""A2 integrity-only fixtures. Never launch Daily or inspect the active workspace.

Owner functions are compiled from their real AST with explicit fixture dependencies;
the import-time active-workspace binding is never executed or patched in production.
Approval references below are synthetic parser fixtures, never release evidence.
"""
from __future__ import annotations

import argparse
import ast
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import traceback
import types
from typing import Any, Mapping

import pytest

from stocklookup_core.acquisition import owner_daily_journal as journal
from stocklookup_core.evidence import official_ocr_layout_proof as registry

ROOT = Path(__file__).resolve().parents[1]
DAILY = "tools/run_owner_daily.py"


def _sha(raw):
    return hashlib.sha256(raw.replace(b"\r\n", b"\n")).hexdigest()


def _receipt(root):
    return json.loads((root / registry.CAPACITY_RECEIPT).read_bytes())


def _save_receipt(root, receipt):
    (root / registry.CAPACITY_RECEIPT).write_bytes(json.dumps(receipt).encode())


@pytest.fixture
def registry_root(tmp_path):
    selectors, anchors = {}, {}
    for role, relative in (("layouts", registry.LAYOUT_SNAPSHOT), ("issuers", registry.ISSUER_SNAPSHOT)):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / relative).read_bytes())
        anchors[relative] = _sha(path.read_bytes())
        selectors[role] = {"role": role, "path": relative, "revision": 1,
                           "approval_reference": "TEST_ONLY_APPROVAL_FIXTURE",
                           "approved_at": "2026-11-26T10:00:00+07:00"}
    _save_receipt(tmp_path, {"schema": "owner_daily_capacity_qualification/v1",
        "source_byte_normalization": "CRLF_TO_LF", "source_sha256": anchors,
        "financial_registry_inputs": selectors})
    return tmp_path


def test_flag_free_gate_preserves_payloads_and_lf_convention(registry_root, monkeypatch):
    root = registry_root
    monkeypatch.setenv("STOCK_LOOKUP_ENABLE_FINANCIAL_REGISTRY_GATE", "0")
    expected, snapshots = registry.verify_financial_registry_inputs(root)
    for role in ("layouts", "issuers"):
        path = root / expected[role]["path"]
        path.write_bytes(path.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    actual, again = registry.verify_financial_registry_inputs(root)
    assert actual == expected and again == snapshots
    assert actual["capacity_receipt_sha256_lf"] == _sha((root / registry.CAPACITY_RECEIPT).read_bytes())
    # Callers cannot poison the digest-keyed parse cache.
    snapshots["layouts"]["entries"].clear()
    assert registry.verify_financial_registry_inputs(root)[1]["layouts"]["entries"]


@pytest.mark.parametrize("case", ["missing_selectors", "missing_role", "role", "extra", "revision_type",
    "missing_approval", "pending_approval", "blank_approval", "missing_time", "naive_time", "time_type",
    "escape", "absolute", "drive", "backslash", "wrong_directory", "mutable_name", "revision_conflict",
    "missing_anchor", "anchor_type", "hash", "receipt_schema", "normalization", "duplicate", "oversize"])
def test_selector_and_anchor_refusals(registry_root, case):
    root = registry_root
    receipt = _receipt(root)
    selector = receipt["financial_registry_inputs"]["layouts"]
    if case == "missing_selectors":
        del receipt["financial_registry_inputs"]
    elif case == "missing_role":
        del receipt["financial_registry_inputs"]["issuers"]
    elif case == "role":
        selector["role"] = "issuers"
    elif case == "extra":
        selector["unexpected"] = True
    elif case == "revision_type":
        selector["revision"] = True
    elif case == "missing_approval":
        del selector["approval_reference"]
    elif case == "pending_approval":
        selector["approval_reference"] = "UNAPPROVED"
    elif case == "blank_approval":
        selector["approval_reference"] = " "
    elif case == "missing_time":
        selector["approved_at"] = None
    elif case == "naive_time":
        selector["approved_at"] = "2026-11-26T10:00:00"
    elif case == "time_type":
        selector["approved_at"] = False
    elif case in {"escape", "absolute", "drive", "backslash", "wrong_directory", "mutable_name"}:
        selector["path"] = {"escape": "../r0001.json", "absolute": "/r0001.json", "drive": "C:/r0001.json",
            "backslash": "config\\official_financial_layouts\\r0001.json",
            "wrong_directory": registry.ISSUER_SNAPSHOT,
            "mutable_name": "config/official_financial_layouts/latest.json"}[case]
    elif case == "revision_conflict":
        selector["revision"] = 2
    elif case == "missing_anchor":
        del receipt["source_sha256"][registry.LAYOUT_SNAPSHOT]
    elif case == "anchor_type":
        receipt["source_sha256"][registry.LAYOUT_SNAPSHOT] = 0
    elif case == "hash":
        receipt["source_sha256"][registry.LAYOUT_SNAPSHOT] = "0" * 64
    elif case == "receipt_schema":
        receipt["schema"] = "unknown/v2"
    elif case == "normalization":
        receipt["source_byte_normalization"] = "RAW"
    _save_receipt(root, receipt)
    path = root / registry.CAPACITY_RECEIPT
    if case == "duplicate":
        path.write_bytes(path.read_bytes().replace(b"{", b'{"schema":"duplicate",', 1))
    elif case == "oversize":
        path.write_bytes(b" " * (registry.REGISTRY_LIMIT + 1))
    with pytest.raises(ValueError):
        registry.verify_financial_registry_inputs(root)


@pytest.mark.parametrize("role", ["layouts", "issuers"])
@pytest.mark.parametrize("case", ["tamper", "missing", "oversize", "duplicate", "schema", "extra", "type",
                                  "nested_extra", "conflict", "revision"])
def test_selected_snapshot_refusals_even_with_updated_anchor(registry_root, role, case):
    root = registry_root
    receipt = _receipt(root)
    relative = receipt["financial_registry_inputs"][role]["path"]
    path = root / relative
    value = json.loads(path.read_bytes())
    if case == "schema":
        value["schema_version"] = 2
    elif case == "extra":
        value["unexpected"] = True
    elif case == "type":
        value["revision"] = True
    elif case == "revision":
        value["revision"] = 2
    elif case == "nested_extra":
        group = "entries" if role == "layouts" else "entity_families"
        next(iter(value[group].values()))["unexpected"] = 1
    elif case == "conflict":
        if role == "layouts":
            next(iter(value["entries"].values()))["payload"]["statement_pages"] = [1, 1]
        else:
            names = list(value["issuer_legal_names"].values())
            names[0]["folded"] = names[1]["folded"] = ["CONFLICTING NAME"]
    raw = json.dumps(value).encode()
    if case == "duplicate":
        raw = raw.replace(b"{", b'{"revision":1,', 1)
    elif case == "oversize":
        raw = b" " * (registry.REGISTRY_LIMIT + 1)
    elif case == "tamper":
        raw += b" "
    path.write_bytes(raw)
    if case != "tamper":
        receipt["source_sha256"][relative] = _sha(raw)
        _save_receipt(root, receipt)
    if case == "missing":
        path.unlink()
    with pytest.raises((ValueError, OSError)):
        registry.verify_financial_registry_inputs(root)


def test_redirected_snapshot_is_refused(registry_root):
    path = registry_root / registry.LAYOUT_SNAPSHOT
    original = path.with_name("retained.json")
    path.rename(original)
    try:
        path.symlink_to(original)
    except OSError:
        pytest.skip("Host does not permit fixture symlinks")
    with pytest.raises(ValueError, match="PATH_ESCAPE"):
        registry.verify_financial_registry_inputs(registry_root)


def test_verified_consumers_use_detached_cached_snapshot(registry_root, monkeypatch):
    monkeypatch.setattr(registry, "_BOUND_REGISTRIES", None)
    for name in ("LAYOUT_PROOFS", "EXACT_REGISTERED_ISSUER_NAMES", "REGISTERED_ISSUER_FOLD", "_ENTITY_FAMILIES"):
        monkeypatch.setattr(registry, name, deepcopy(getattr(registry, name)))
    currency = sys.modules.get("financial_evidence_currency_contract")
    if currency is not None:
        monkeypatch.setattr(currency, "ENTITY_FAMILY", deepcopy(currency.ENTITY_FAMILY))
    bindings = registry.bind_financial_registry_inputs(registry_root)
    original = registry.load_registry_snapshot("layouts")
    (registry_root / registry.LAYOUT_SNAPSHOT).write_bytes(b"tampered after gate")
    assert registry.load_registry_snapshot("layouts") == original
    registry.load_registry_snapshot("layouts")["entries"].clear()
    assert registry.load_registry_snapshot("layouts") == original
    with pytest.raises(ValueError, match="HASH_MISMATCH"):
        registry.verify_financial_registry_inputs(registry_root, expected=bindings)
    with pytest.raises(ValueError, match="BOUND_INPUT_CONFLICT"):
        registry.load_registry_snapshot("layouts", expected_sha256_lf="0" * 64)


def test_initial_durable_write_is_additive_and_already_bound(registry_root, monkeypatch):
    bindings, _ = registry.verify_financial_registry_inputs(registry_root)
    writes = []
    monkeypatch.setattr(journal, "_atomic_write", lambda path, value: writes.append(deepcopy(value)))
    monkeypatch.setattr(journal, "_now_iso", lambda: "2026-11-26T03:00:00+00:00")
    monkeypatch.setattr(journal.uuid, "uuid4", lambda: types.SimpleNamespace(hex="a" * 32))
    legacy = journal.start_run(registry_root)
    bound = journal.start_run(registry_root, financial_registry_inputs=bindings)
    assert writes[-1]["financial_registry_inputs"] == bindings
    assert {k: v for k, v in bound.items() if k != "financial_registry_inputs"} == legacy


@pytest.mark.parametrize("case", ["missing", "direct", "descendant", "unrelated", "mismatch", "duplicate", "extra", "type", "malformed", "shape", "encoding"])
def test_optional_child_attestations_remain_strict_and_run_bound(registry_root, monkeypatch, case):
    root = registry_root
    bindings, _ = registry.verify_financial_registry_inputs(root)
    owner_pid = os.getpid()
    env = journal.registry_child_environment(root, bindings)
    run_id = env[registry.REGISTRY_RUN_ENV]
    if case == "missing":
        assert journal.registry_child_attestations(root, run_id, bindings) == {
            "pids": [], "status": "REGISTRY_NOT_LOADED_BY_CHILD"}
        return
    monkeypatch.setattr(journal.os, "getpid", lambda: 12345)
    ancestors = [54321, owner_pid] if case == "descendant" else [owner_pid]
    monkeypatch.setattr(journal, "_registry_ancestor_pids", lambda: ancestors)
    journal.attest_registry_child(root, run_id, bindings)
    directory = journal._registry_child_directory(root, run_id)
    path = directory / "12345.json"
    row = json.loads(path.read_bytes())
    if case in {"direct", "descendant"}:
        assert journal.verify_registry_children(root, run_id, bindings, owner_pid=owner_pid) == [12345]
        with pytest.raises(ValueError, match="ATTESTATION_EXISTS"):
            journal.attest_registry_child(root, run_id, bindings)
        return
    if case == "unrelated":
        row["ancestor_pids"] = [54321]
    elif case == "mismatch":
        row["financial_registry_inputs"]["capacity_receipt_sha256_lf"] = "0" * 64
    elif case == "extra":
        row["financial_registry_inputs"]["unexpected"] = 1
    elif case == "type":
        row["financial_registry_inputs"]["layouts"]["revision"] = True
    path.write_bytes(json.dumps(row).encode())
    if case == "duplicate":
        path.write_bytes(path.read_bytes().replace(b"{", b'{"pid":1,', 1))
    elif case == "malformed":
        path.write_bytes(b"{")
    elif case == "shape":
        path.write_bytes(b"[]")
    elif case == "encoding":
        path.write_bytes(b"\xff")
    expected = ("REGISTRY_CHILD_ATTESTATION_INVALID" if case in
                {"duplicate", "extra", "type", "malformed", "shape", "encoding"} else "REGISTRY_")
    with pytest.raises(ValueError, match=expected):
        journal.verify_registry_children(root, run_id, bindings, owner_pid=owner_pid)
    with pytest.raises(ValueError, match="RUN_ID_INVALID"):
        journal.verify_registry_children(root, "../escape", bindings)


def test_child_cannot_attest_outside_owner_lineage(registry_root, monkeypatch):
    bindings, _ = registry.verify_financial_registry_inputs(registry_root)
    env = journal.registry_child_environment(registry_root, bindings)
    # The current process is the owner, not its own descendant.
    monkeypatch.setenv("STOCKLOOKUP_FINANCIAL_REGISTRY_OWNER_PID", str(os.getpid()))
    with pytest.raises(ValueError, match="PID_NOT_DESCENDANT"):
        journal.attest_registry_child(registry_root, env[registry.REGISTRY_RUN_ENV], bindings)


@pytest.mark.parametrize("mismatch", [False, True])
def test_isolated_consumer_import_verifies_and_attests_without_daily(registry_root, mismatch):
    root = registry_root
    # This child imports only the two owners in a fixture checkout; no Daily entrypoint.
    for relative in ("stocklookup_core/evidence/official_ocr_layout_proof.py",
                     "stocklookup_core/acquisition/owner_daily_journal.py"):
        path = root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / relative).read_bytes())
    for package in ("stocklookup_core", "stocklookup_core/evidence", "stocklookup_core/acquisition"):
        (root / package / "__init__.py").write_bytes(b"")
    bindings, _ = registry.verify_financial_registry_inputs(root)
    env = os.environ.copy()
    env.pop("PYTHONPATH", None)
    env.update(journal.registry_child_environment(root, bindings))
    if mismatch:
        receipt = _receipt(root)
        receipt["unrelated_capacity_history"] = "changed receipt digest"
        _save_receipt(root, receipt)
    code = '''
import json, os
from stocklookup_core.evidence import official_ocr_layout_proof as r
before = r.load_registry_snapshot("layouts")
(r.REGISTRY_ROOT / r.LAYOUT_SNAPSHOT).write_bytes(b"changed after verification")
assert r.load_registry_snapshot("layouts") == before
print(json.dumps({"pid": os.getpid(), "bindings": r._BOUND_REGISTRIES[1]}))
'''
    child = subprocess.run([sys.executable, "-B", "-c", code], cwd=root, env=env,
                           capture_output=True, text=True, timeout=30)
    if mismatch:
        assert child.returncode != 0 and "REGISTRY_CHILD_BINDING_MISMATCH" in child.stderr
        assert not list(journal._registry_child_directory(root, env[registry.REGISTRY_RUN_ENV]).iterdir())
    else:
        assert child.returncode == 0, child.stderr
        row = json.loads(child.stdout)
        assert row["bindings"] == bindings
        assert journal.verify_registry_children(root, env[registry.REGISTRY_RUN_ENV], bindings,
                                                owner_pid=os.getpid()) == [row["pid"]]


@pytest.fixture
def daily_functions(registry_root, monkeypatch):
    """Compile owner functions with fixture-only paths and explicit side-effect stubs."""
    tree = ast.parse((ROOT / DAILY).read_bytes())
    names = {"OwnerDailyError", "ProducerCodeAdvanced", "_require_financial_registry_inputs", "_run_daily",
             "_journal_start", "_journal_advance", "_journal_advance_strict", "run_workflow", "main",
             "_load_strict_json", "_reject_duplicate_keys"}
    body = [ast.ImportFrom(module="__future__", names=[ast.alias(name="annotations")], level=0)]
    body += [node for node in tree.body if isinstance(node, (ast.FunctionDef, ast.ClassDef)) and node.name in names]
    root = registry_root
    scope = dict(__name__="financial_registry_daily_fixture", __doc__="Fixture only", Path=Path,
                 os=os, sys=sys, json=json, subprocess=subprocess, argparse=argparse, traceback=traceback,
                 journal=journal, Any=Any, Mapping=Mapping, ROOT=root, DEFAULT_RUNTIME=root / "runtime", DEFAULT_HANDOFF_REPO=root / "handoff",
                 DEFAULT_WEB_DIR=root / "dashboard", OwnerDailyProgress=object, WORKFLOW_CORE_AI="CORE_AI",
                 WORKFLOW_FULL_PUBLISH="FULL_PUBLISH", CODE_HEAD_ENV="TEST_ONLY_CODE_HEAD", _NOT_REQUESTED="NOT_REQUESTED",
                 exclusive_writer=lambda function: function)
    exec(compile(ast.fix_missing_locations(ast.Module(body=body, type_ignores=[])), str(ROOT / DAILY), "exec"), scope)
    scope.update(bind_active_workspace=lambda root: None, workspace_profile=lambda: None,
                 _resolve_intended_session=lambda: "2026-11-26", _auto_resumable_session=lambda *a, **kw: None,
                 _require_financial_registry_inputs=lambda root, **kw: registry.verify_financial_registry_inputs(root, **kw)[0])
    for key in (registry.REGISTRY_BINDINGS_ENV, registry.REGISTRY_RUN_ENV,
                "STOCKLOOKUP_FINANCIAL_REGISTRY_OWNER_PID", "TEST_ONLY_CODE_HEAD"):
        monkeypatch.delenv(key, raising=False)
    return scope


def test_gate_precedes_initial_journal_and_all_material_work(registry_root, daily_functions):
    scope = daily_functions
    receipt = _receipt(registry_root)
    del receipt["financial_registry_inputs"]
    _save_receipt(registry_root, receipt)
    def forbidden(*args, **kwargs):
        pytest.fail("Material work must not run after gate refusal")
    scope.update(preflight_repository=forbidden, _journal_start=forbidden, _run_daily=forbidden)
    with pytest.raises(ValueError):
        scope["run_workflow"]()
    assert not journal.journal_path(registry_root).exists()


@pytest.mark.parametrize("guarded", [False, True])
@pytest.mark.parametrize("attestation", ["valid", "missing", "mismatch", "malformed", "unrelated"])
def test_daily_child_registry_load_is_optional_but_attestations_must_match(registry_root, daily_functions, monkeypatch,
                                                                    guarded, attestation):
    scope = daily_functions
    expected, _ = registry.verify_financial_registry_inputs(registry_root)
    scope["_require_host_ready"] = lambda root: pytest.fail("Fixture already supplies READY; no host observation")
    scope["PROGRESS_PATH_ENV"] = "TEST_ONLY_PROGRESS"
    captured = []
    owner_pid = os.getpid()
    def child(command, **kwargs):
        captured.append(command)
        env = kwargs["env"]
        assert json.loads(env[registry.REGISTRY_BINDINGS_ENV]) == expected
        if attestation != "missing":
            binding = deepcopy(expected)
            if attestation == "mismatch":
                binding["issuers"]["sha256_lf"] = "0" * 64
            monkeypatch.setattr(journal, "_registry_ancestor_pids", lambda: [owner_pid])
            with monkeypatch.context() as child_patch:
                child_patch.setattr(journal.os, "getpid", lambda: 12345)
                journal.attest_registry_child(registry_root, env[registry.REGISTRY_RUN_ENV], binding)
            path = journal._registry_child_directory(registry_root, env[registry.REGISTRY_RUN_ENV]) / "12345.json"
            if attestation == "malformed":
                path.write_bytes(b"{")
            elif attestation == "unrelated":
                row = json.loads(path.read_bytes()); row["ancestor_pids"] = [owner_pid + 1]
                path.write_bytes(json.dumps(row).encode())
        return types.SimpleNamespace(pid=12345, wait=lambda: 0)
    monkeypatch.setattr(subprocess, "Popen", child)
    if guarded:
        guard_module = types.ModuleType("stocklookup_core.acquisition.feedback_resource_guard")
        def guard(command, **kwargs):
            process = child(command, **kwargs)
            kwargs["on_start"](process.pid)
            return process.wait()
        guard_module.run_capacity_guarded = guard
        preflight_module = types.ModuleType("tools.check_owner_daily_host_preflight")
        preflight_module.windows_memory = lambda: pytest.fail("No host observation permitted")
        monkeypatch.setitem(sys.modules, guard_module.__name__, guard_module)
        monkeypatch.setitem(sys.modules, preflight_module.__name__, preflight_module)
    call = lambda: scope["_run_daily"](registry_root, registry_root / "runtime",
                host_ready={"classification": "READY", "runtime_capacity_guard_required": guarded},
                financial_registry_inputs=expected)
    if attestation in {"valid", "missing"}:
        assert call() == {"pids": [12345] if attestation == "valid" else [],
                          "status": "BOUND" if attestation == "valid" else "REGISTRY_NOT_LOADED_BY_CHILD"}
    else:
        with pytest.raises(scope["OwnerDailyError"], match="REGISTRY_"):
            call()
    assert captured[0][1:3] == ["-u", "daily_analysis_pipeline.py"]


@pytest.mark.parametrize("kind", ["known", "unexpected", "interrupt"])
def test_failure_journal_and_external_receipt_keep_bindings(registry_root, daily_functions, monkeypatch, kind):
    scope = daily_functions
    expected, _ = registry.verify_financial_registry_inputs(registry_root)
    def fail(*args, **kwargs):
        if kind == "known":
            raise scope["OwnerDailyError"]("Repository preflight", "TEST_ONLY_FAILURE")
        if kind == "interrupt":
            raise KeyboardInterrupt()
        raise RuntimeError("TEST_ONLY_FAILURE")
    scope["preflight_repository"] = fail
    class Telemetry:
        active_phase = 1
        session = None
        def __init__(self, *args, **kwargs): pass
        def set_workflow(self, *args): pass
        def start_view(self, *args): pass
        def emit(self, *args, **kwargs): pass
        def summary(self): return {"status": "TEST_ONLY"}
    scope.update(OwnerDailyProgress=Telemetry, validate_result_path=lambda path, **kw: path,
                 safe_progress_path=lambda path, **kw: None, recent_phase_estimates=lambda path: {}, PHASES={1: "Repository preflight"})
    result_path = registry_root / "test-only-result.json"
    call = lambda: scope["main"](["--result-path", str(result_path)])
    if kind == "interrupt":
        with pytest.raises(KeyboardInterrupt):
            call()
    else:
        assert call() == (1 if kind == "known" else 2)
    result = json.loads(result_path.read_bytes())
    assert result["financial_registry_inputs"] == expected
    assert result["financial_registry_child_attestations"] == {"pids": [], "status": "REGISTRY_NOT_LOADED_BY_CHILD"}
    state = journal.read_journal(registry_root)
    assert state["financial_registry_inputs"] == expected
    assert state["failure"]["detail"]["financial_registry_inputs"] == expected
    assert state["failure"]["detail"]["financial_registry_child_attestations"] == result["financial_registry_child_attestations"]
    assert registry.REGISTRY_BINDINGS_ENV not in os.environ and registry.REGISTRY_RUN_ENV not in os.environ


@pytest.mark.parametrize("case", ["missing_pair", "duplicate", "bool_revision", "mismatch"])
def test_direct_child_rejects_corrupt_inherited_environment_before_launch(registry_root, daily_functions, monkeypatch, case):
    bindings, _ = registry.verify_financial_registry_inputs(registry_root)
    env = journal.registry_child_environment(registry_root, bindings)
    if case == "missing_pair":
        del env[registry.REGISTRY_RUN_ENV]
    elif case == "duplicate":
        env[registry.REGISTRY_BINDINGS_ENV] = env[registry.REGISTRY_BINDINGS_ENV].replace("{", '{"layouts":{},', 1)
    else:
        value = deepcopy(bindings)
        if case == "bool_revision":
            value["layouts"]["revision"] = True
        else:
            value["layouts"]["sha256_lf"] = "0" * 64
        env[registry.REGISTRY_BINDINGS_ENV] = json.dumps(value)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    daily_functions["_require_host_ready"] = lambda root: pytest.fail("Registry refusal must precede host observation")
    with pytest.raises(daily_functions["OwnerDailyError"]):
        daily_functions["_run_daily"](registry_root, registry_root / "runtime", financial_registry_inputs=bindings)


def test_terminal_receipt_keeps_identical_binding(registry_root, daily_functions, monkeypatch):
    scope = daily_functions
    expected, _ = registry.verify_financial_registry_inputs(registry_root)
    # All analytical, host and external publication operations are explicit pure stubs.
    scope.update(preflight_repository=lambda *a, **kw: {"status": "UNCHANGED"},
        consumer_root_for=lambda root: root / "consumer", preflight_consumer_repository=lambda *a, **kw: {},
        _require_host_ready=lambda root: {"classification": "READY"}, _run_daily=lambda *a, **kw: None,
        verify_daily_completion=lambda *a, **kw: {"session": "2026-11-26", "record": {}},
        commit_daily_state=lambda *a: {"status": "NO_CHANGE"}, _presentation_bound_state=lambda *a: "BOUND",
        _dashboard_not_requested=lambda *a: {"status": "NOT_REQUESTED"},
        _verify_ai_handoff_published=lambda *a: None, publish_ai_handoff=lambda *a: {"remote": {}},
        _require_remote_handoff_attestation=lambda *a, **kw: None,
        _workflow_completion=lambda *a: {}, _t0_snapshot_attestation=lambda *a: {},
        _dashboard_complete_attestation=lambda *a: {})
    presentation = types.ModuleType("stocklookup_core.decision.post_handoff_presentation_attestation")
    presentation.read_attestation = lambda *args: {}
    monkeypatch.setitem(sys.modules, presentation.__name__, presentation)
    result = scope["run_workflow"](workflow_mode="CORE_AI")
    assert result["status"] == "PASS" and result["financial_registry_inputs"] == expected
    state = journal.read_journal(registry_root)
    assert state["attestation"]["financial_registry_inputs"] == expected
    assert result["financial_registry_child_attestations"] == {"pids": [], "status": "REGISTRY_NOT_LOADED_BY_CHILD"}
    assert state["attestation"]["financial_registry_child_attestations"] == result["financial_registry_child_attestations"]
    assert state["financial_registry_inputs"] == expected


@pytest.mark.parametrize("target", ["source", "archive", "manifest", "coedited_hashes", "duplicate", "extra", "missing"])
def test_e6_daily_transition_refusals(tmp_path, target):
    from tools import verify_retention_reader_transition as transition
    manifest_path = transition.REGISTRY_DAILY_GATE_TRANSITION
    spec = json.loads((ROOT / manifest_path).read_bytes())
    for relative in (DAILY, spec["archive"], manifest_path):
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes((ROOT / relative).read_bytes())
    active = (tmp_path / DAILY).read_bytes().replace(b"\r\n", b"\n")
    assert transition._registry_daily_gate_prior_bytes(tmp_path, DAILY, active) == (ROOT / spec["archive"]).read_bytes().replace(b"\r\n", b"\n")
    path = tmp_path / {"source": DAILY, "archive": spec["archive"], "manifest": manifest_path,
                       "coedited_hashes": manifest_path, "duplicate": manifest_path,
                       "extra": manifest_path, "missing": manifest_path}[target]
    if target == "missing":
        path.unlink()
    elif target == "manifest":
        spec["release_authority"] = "GRANTED"
        path.write_bytes(json.dumps(spec).encode())
    elif target == "coedited_hashes":
        source = tmp_path / DAILY
        source.write_bytes(source.read_bytes() + b"# tampered\n")
        spec["active_sha256_lf"] = _sha(source.read_bytes())
        path.write_bytes(json.dumps(spec).encode())
    elif target == "duplicate":
        path.write_bytes(path.read_bytes().replace(b"{", b'{"release_authority":"NOT_GRANTED",', 1))
    elif target == "extra":
        spec["unexpected"] = True
        path.write_bytes(json.dumps(spec).encode())
    else:
        path.write_bytes(path.read_bytes() + b"# tampered\n")
    with pytest.raises((ValueError, OSError)):
        transition._registry_daily_gate_prior_bytes(tmp_path, DAILY, (tmp_path / DAILY).read_bytes().replace(b"\r\n", b"\n"))


@pytest.mark.parametrize("target", ["inline_prior", "scope", "active_hash", "prior_type"])
def test_layout_outer_transition_refuses_unreviewed_successor(tmp_path, target):
    from tools import verify_retention_reader_transition as transition
    relative = "stocklookup_core/evidence/official_ocr_layout_proof.py"
    spec = json.loads((ROOT / transition.REGISTRY_LAYOUT_TRANSITION).read_bytes())
    for path in (relative, spec["archive"], transition.REGISTRY_LAYOUT_TRANSITION):
        destination = tmp_path / path
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_bytes((ROOT / path).read_bytes())
    row = spec["daily_gate_transition"]
    if target == "inline_prior":
        row["prior_source_lf"] += "# tampered\n"
    elif target == "scope":
        row["scope"] = "UNREVIEWED_SCOPE"
    elif target == "active_hash":
        source = tmp_path / relative
        source.write_bytes(source.read_bytes() + b"# tampered\n")
        row["active_sha256_lf"] = _sha(source.read_bytes())
    else:
        row["prior_source_lf"] = 1
    (tmp_path / transition.REGISTRY_LAYOUT_TRANSITION).write_bytes(json.dumps(spec).encode())
    with pytest.raises(ValueError, match="REGISTRY_SNAPSHOT_SOURCE_TRANSITION_"):
        transition.historical_bytes(tmp_path, relative)


def test_e6_chain_and_import_time_workspace_binding_are_conserved():
    from tools import verify_retention_reader_transition as transition
    archive = "tests/fixtures/registry_migration_v1/run_owner_daily.py.txt"
    before = ast.parse((ROOT / archive).read_bytes())
    after = ast.parse((ROOT / DAILY).read_bytes())
    def workspace_nodes(tree):
        return [ast.dump(n, include_attributes=False) for n in tree.body
                if (isinstance(n, ast.FunctionDef) and n.name == "bind_active_workspace")
                or (isinstance(n, ast.Expr) and isinstance(n.value, ast.Call)
                    and isinstance(n.value.func, ast.Name) and n.value.func.id == "bind_active_workspace")]
    assert workspace_nodes(before) == workspace_nodes(after)
    assert len(workspace_nodes(after)) == 2
    # Both successors must peel to the original protected bytes through the existing chain.
    pins = json.loads((ROOT / "tests/fixtures/e2e3_frozen_sources.json").read_bytes())["source_sha256_lf"]
    assert _sha(transition.historical_bytes(ROOT, DAILY)) == pins[DAILY]
    relative = "stocklookup_core/evidence/official_ocr_layout_proof.py"
    assert _sha(transition.historical_bytes(ROOT, relative)) == transition.REGISTRY_SNAPSHOT_TRANSITIONS[relative]["prior_sha256_lf"]
