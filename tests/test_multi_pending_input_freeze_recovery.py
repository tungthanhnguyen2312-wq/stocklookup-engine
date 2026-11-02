"""Regression for the 2026-11-02 Daily: several unsealed input freezes, one sealed predecessor.

2026-10-23 is the last sealed Daily. The 2026-10-26 Daily froze its inputs and failed
before sealing. The 2026-11-02 Daily froze its own inputs on top of that, so the registry
diff carried two pending rows, the single-freeze classifier refused it, and pre-seal
selected 2026-10-26 (no operation) as the predecessor:
PRESEAL_PREVIOUS_OPERATION_MISSING_GOVERNED_PREVIOUS_OPERATION:2026-10-26.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

import pytest

import canonical_daily_operation as cdo
import daily_execution_environment as env
import governed_previous_operation as selector
import pending_session_input_freeze as freeze
import stocklookup
from tools import run_owner_daily as workflow


SEALED = "2026-10-23"
FAILED_FREEZE = "2026-10-26"
CURRENT = "2026-11-02"
NEXT = "2026-11-03"
REGISTRY = freeze.REGISTRY_RELATIVE
SEALED_FROZEN = {"descriptive": "descriptive:sealed"}


def _git(path: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(path), *args], check=True, capture_output=True, text=True,
    ).stdout.strip()


def _porcelain(path: Path) -> list[str]:
    out = subprocess.run(["git", "-C", str(path), "status", "--porcelain", "--untracked-files=no"],
                         check=True, capture_output=True, text=True).stdout
    return [line for line in out.splitlines() if line]


def _write_registry(path: Path, registry: dict) -> None:
    path.write_text(json.dumps(registry, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _clone(tmp_path: Path) -> tuple[Path, Path]:
    """A Producer checkout whose origin/main registry ends at the sealed 2026-10-23 session."""
    origin = tmp_path / "stock-core-private.git"
    subprocess.run(["git", "init", "--bare", "-q", "--initial-branch=main", str(origin)], check=True)
    seed = tmp_path / "seed"
    seed.mkdir()
    _git(seed, "init", "-q")
    _git(seed, "config", "user.email", "test@example.com")
    _git(seed, "config", "user.name", "Test")
    (seed / ".gitignore").write_text("operations-review/\n", encoding="utf-8")
    (seed / "config").mkdir()
    _write_registry(seed / REGISTRY, {
        "schema_version": "1.0.0",
        "contract_version": "daily_research_session_input_registry/v1",
        "completed_sessions": {SEALED: {
            "status": "COMPLETED_RETAINED_EVIDENCE", "trading_day_valid": True,
            "frozen_input_identities": SEALED_FROZEN,
        }},
        "sessions": {SEALED: {"descriptive": {
            "path": "operations-review/sealed/descriptive.json", "artifact_identity": "descriptive:sealed",
        }}},
    })
    _git(seed, "add", ".gitignore", REGISTRY)
    _git(seed, "commit", "-qm", "seed")
    _git(seed, "branch", "-M", "main")
    _git(seed, "remote", "add", "origin", str(origin))
    _git(seed, "push", "-q", "-u", "origin", "main")
    root = tmp_path / "stock-core-private"
    subprocess.run(["git", "clone", "-q", str(origin), str(root)], check=True)
    _git(root, "checkout", "-q", "main")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "Test")
    return root, origin


def _freeze(root: Path, session: str, *, identity_suffix: str = "") -> dict[str, str]:
    """Write what ``validate_and_freeze_completed_session`` leaves after a pre-seal failure."""
    identities = {
        key: f"{key}:{session}{identity_suffix}"
        for key in (*freeze.REQUIRED_INPUT_KEYS, *freeze.OPTIONAL_INPUT_KEYS)
    }
    selection = {}
    for key, identity in identities.items():
        relative = f"operations-review/freeze-{session}/{key}.json"
        (root / relative).parent.mkdir(parents=True, exist_ok=True)
        (root / relative).write_text(json.dumps({"artifact_identity": f"{key}:{session}"}), encoding="utf-8")
        selection[key] = {"path": relative, "artifact_identity": identity}
    registry = json.loads((root / REGISTRY).read_text(encoding="utf-8"))
    registry["completed_sessions"][session] = {
        "status": "COMPLETED_RETAINED_EVIDENCE", "trading_day_valid": True,
        "completion_evidence": {"basis": "EXACT_SESSION_UPSTREAM_ARTIFACT_REGISTRY"},
        "frozen_input_identities": identities,
    }
    registry["sessions"][session] = selection
    _write_registry(root / REGISTRY, registry)
    return identities


def _operation(root: Path, session: str, frozen: dict[str, str], name: str = "op") -> tuple[Path, str]:
    directory = root / "operations-review" / "daily-research-session-operations-v1" / session / name
    directory.mkdir(parents=True)
    operation_identity = f"daily_research_session_operation:{session}:{name}"
    product_identity = f"current_daily_decision_research_product:{session}:{name}"
    (directory / "run_manifest.json").write_text(json.dumps({
        "market_session": session, "operation_identity": operation_identity,
        "input_artifacts": {key: {"artifact_identity": value} for key, value in frozen.items()},
        "outputs": {"daily_product": product_identity},
    }), encoding="utf-8")
    (directory / "ai_research_session_bundle.json").write_text(json.dumps({
        "session": session, "operation_identity": operation_identity, "product_identity": product_identity,
    }), encoding="utf-8")
    return directory, operation_identity


def _seal(root: Path, session: str) -> None:
    record = root / "operations-review" / "canonical-daily-operation-v1" / session / "op" / "daily_operation_record.json"
    record.parent.mkdir(parents=True)
    record.write_text(json.dumps({"session": session, "daily_operation_state": "LOCAL_COMPLETE"}), encoding="utf-8")


@pytest.fixture
def november(tmp_path):
    root, origin = _clone(tmp_path)
    sealed_dir, sealed_identity = _operation(root, SEALED, SEALED_FROZEN)
    _freeze(root, FAILED_FREEZE)
    current_frozen = _freeze(root, CURRENT)
    return root, origin, sealed_dir, sealed_identity, current_frozen


def _registry(root: Path) -> dict:
    return json.loads((root / REGISTRY).read_text(encoding="utf-8"))


def test_two_unsealed_freezes_are_admitted_together(november):
    root, *_ = november
    result = freeze.classify_pending_input_freeze(root)
    assert result.admitted is True
    assert result.sessions == (FAILED_FREEZE, CURRENT)
    assert result.session == CURRENT
    release = env.producer_release_qualification(root)
    assert release["qualified"] is True
    assert release["session"] == CURRENT
    assert workflow.preflight_repository(
        root, expected_name="stock-core-private", expected_remote_fragment="stock-core-private",
    )["status"] == "PENDING_INPUT_FREEZE_AT_ORIGIN_MAIN"


def test_every_consumer_selects_the_last_sealed_operation_after_the_current_freeze(november, monkeypatch):
    root, _origin, sealed_dir, sealed_identity, _ = november
    registry = _registry(root)
    # Canonical Daily passes only the retained root; the Daily child's bound profile names the Producer.
    monkeypatch.setattr("runtime_paths.workspace_profile", lambda observer=None: {"paths": {"producer": root}})

    resolved = selector.resolve_governed_previous_operation(CURRENT, registry, root, producer_root=root)
    preflight = next(row for row in env.required_retained_inputs(root, CURRENT)
                     if row["contract"] == "governed_previous_session_bundle")
    preseal = cdo._previous_qualified_operation_source(root, session=CURRENT, registry=registry)

    assert resolved["status"] == selector.AVAILABLE
    assert resolved["previous_session"] == SEALED
    assert resolved["operation_identity"] == sealed_identity
    assert resolved["excluded_pending_input_freeze_sessions"] == [FAILED_FREEZE]
    assert preflight["status"] == "AVAILABLE"
    assert preflight["previous_session"] == SEALED
    assert preseal == (SEALED, sealed_dir)


def test_public_bundle_consumer_uses_the_bound_producer(november, monkeypatch):
    root, _origin, sealed_dir, *_ = november
    monkeypatch.setattr("runtime_paths.workspace_profile", lambda observer=None: {"paths": {"producer": root}})
    assert stocklookup._previous(CURRENT, root) == sealed_dir / "ai_research_session_bundle.json"


def test_one_corrupt_pending_row_rejects_the_whole_diff(november):
    root, *_ = november
    registry = _registry(root)
    registry["sessions"][FAILED_FREEZE]["tactical"]["artifact_identity"] = "tactical:rewritten"
    registry["completed_sessions"][FAILED_FREEZE]["frozen_input_identities"]["tactical"] = "tactical:rewritten"
    _write_registry(root / REGISTRY, registry)
    assert freeze.classify_pending_input_freeze(root).reason_code == "ARTIFACT_IDENTITY_MISMATCH"
    resolved = selector.resolve_governed_previous_operation(CURRENT, registry, root, producer_root=root)
    assert resolved["status"] == selector.MISSING_GOVERNED_PREVIOUS_OPERATION
    assert resolved["previous_session"] == FAILED_FREEZE


def test_a_pending_session_that_is_already_sealed_is_not_a_freeze(november):
    root, *_ = november
    _seal(root, FAILED_FREEZE)
    assert freeze.classify_pending_input_freeze(root).reason_code == "SEALED_OPERATION_PRESENT"


def test_committed_completion_without_operation_still_fails_closed(tmp_path):
    root, _origin = _clone(tmp_path)
    _operation(root, SEALED, SEALED_FROZEN)
    _freeze(root, FAILED_FREEZE)
    _git(root, "commit", "-qam", "commit an unsealed row")
    _freeze(root, CURRENT)
    assert freeze.classify_pending_input_freeze(root).sessions == (CURRENT,)
    resolved = selector.resolve_governed_previous_operation(CURRENT, _registry(root), root, producer_root=root)
    assert resolved["status"] == selector.MISSING_GOVERNED_PREVIOUS_OPERATION
    assert resolved["previous_session"] == FAILED_FREEZE


def test_seal_commits_only_its_own_row_and_the_next_daily_follows_it(november):
    root, origin, *_rest, current_frozen = november
    _operation(root, CURRENT, current_frozen)
    _seal(root, CURRENT)

    result = workflow.commit_daily_state(root, CURRENT)
    assert result["status"] == "COMMITTED"
    assert _git(origin, "rev-parse", "main") == result["sha"]
    committed = json.loads(_git(root, "show", "HEAD:" + REGISTRY))
    assert set(committed["completed_sessions"]) == {SEALED, CURRENT}
    assert set(committed["sessions"]) == {SEALED, CURRENT}
    assert _git(root, "show", "HEAD:" + REGISTRY) + "\n" == (
        json.dumps(committed, ensure_ascii=False, indent=2) + "\n"
    )

    # The failed 2026-10-26 freeze is still an uncommitted lock, nothing else is dirty.
    assert _porcelain(root) == [" M " + REGISTRY]
    remaining = freeze.classify_pending_input_freeze(root)
    assert remaining.admitted is True
    assert remaining.sessions == (FAILED_FREEZE,)
    assert workflow.commit_daily_state(root, CURRENT)["status"] == "NO_CHANGE"

    _freeze(root, NEXT)
    assert freeze.classify_pending_input_freeze(root).sessions == (FAILED_FREEZE, NEXT)
    resolved = selector.resolve_governed_previous_operation(NEXT, _registry(root), root, producer_root=root)
    assert resolved["status"] == selector.AVAILABLE
    assert resolved["previous_session"] == CURRENT
    assert resolved["excluded_pending_input_freeze_sessions"] == [FAILED_FREEZE]


def test_resumed_seal_commit_refuses_a_corrupt_leftover_freeze(november):
    root, _origin, *_rest, current_frozen = november
    _operation(root, CURRENT, current_frozen)
    _seal(root, CURRENT)
    workflow.commit_daily_state(root, CURRENT)
    (root / "operations-review" / f"freeze-{FAILED_FREEZE}" / "tactical.json").unlink()
    head = _git(root, "rev-parse", "HEAD")
    with pytest.raises(workflow.OwnerDailyError, match="REGISTRY_DIFF_NOT_PENDING_INPUT_FREEZES"):
        workflow.commit_daily_state(root, CURRENT)
    assert _git(root, "rev-parse", "HEAD") == head
