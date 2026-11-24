from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import roadmap_execution_state as res
from stocklookup_core.acquisition.subprocess_capture import run_utf8

_TOOLS_PARENT = Path(__file__).resolve().parents[1]
if str(_TOOLS_PARENT) not in sys.path:
    sys.path.insert(0, str(_TOOLS_PARENT))
import tools.stocklookup_roadmap as cli  # noqa: E402


def _git(cwd: Path, *args: str) -> str:
    code, out, err = run_utf8(["git", "-C", str(cwd), *args])
    assert code == 0, f"git {args} failed: {err}"
    return out


def _init_repo(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    _git(path, "init", "-q")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "user.name", "Test")
    return path


def _commit_all(path: Path, message: str) -> str:
    _git(path, "add", "-A")
    _git(path, "commit", "-q", "-m", message)
    return _git(path, "rev-parse", "HEAD").strip()


@pytest.fixture
def git_repo(tmp_path):
    """A throwaway Git repository under tmp_path -- never a real project worktree."""
    repo = tmp_path / "repo"
    _init_repo(repo)
    (repo / "README.md").write_text("root\n", encoding="utf-8")
    sha = _commit_all(repo, "initial")
    return repo, sha


def _milestone(mid: str, state: str, **overrides) -> dict:
    entry = {
        "milestone_id": mid,
        "state": state,
        "checkpoint": None,
        "dependencies": [],
        "unlocks": [],
        "authority_effect": "NONE",
        "state_history": [],
        "owner_override": None,
    }
    entry.update(overrides)
    return entry


def _state(milestones, *, current=None, queued_next=None, lineage_head=None, allowlist=None) -> dict:
    return {
        "schema_version": res.SCHEMA_VERSION,
        "roadmap_id": "test",
        "roadmap_version": "0.0.1",
        "implementation_lineage_head": lineage_head,
        "known_operational_diff_allowlist": allowlist or [],
        "current": current or {},
        "queued_next": queued_next or [],
        "milestones": milestones,
        "blocked_capabilities": [],
    }


# ---------------------------------------------------------------------------
# Pure structural validation (no Git needed)
# ---------------------------------------------------------------------------

def test_valid_roadmap_state_passes():
    state = _state(
        [
            _milestone("A", "COMPLETE", checkpoint="deadbeef"),
            _milestone("B", "NEXT", dependencies=["A"]),
        ],
        current={"milestone": "A", "state": "COMPLETE"},
        queued_next=["B"],
    )
    report = res.evaluate(state)
    assert report.overall == res.OVERALL_GIT_NOT_CHECKED
    assert report.git_verification == res.GIT_VERIFICATION_SKIPPED
    assert report.category_status("git/worktree consistency") == "SKIPPED"
    assert not report.has_fail()


def test_two_active_milestones_fail():
    state = _state([_milestone("A", "ACTIVE"), _milestone("B", "ACTIVE")])
    report = res.evaluate(state)
    assert report.overall == "DRIFT_DETECTED"
    assert "ROADMAP_MULTIPLE_ACTIVE_MILESTONES" in {f.code for f in report.findings}


def test_active_with_unsatisfied_dependency_fails():
    state = _state([_milestone("A", "NEXT"), _milestone("B", "ACTIVE", dependencies=["A"])])
    report = res.evaluate(state)
    assert report.overall == "DRIFT_DETECTED"
    assert "ROADMAP_ACTIVE_NOT_ALLOWED_BY_DEPENDENCIES" in {f.code for f in report.findings}


def test_next_depending_on_blocked_fails():
    state = _state(
        [_milestone("A", "BLOCKED"), _milestone("B", "NEXT", dependencies=["A"])],
        queued_next=["B"],
    )
    report = res.evaluate(state)
    assert "ROADMAP_NEXT_DEPENDENCY_UNSATISFIED" in {f.code for f in report.findings}


def test_completed_checkpoint_missing_fails():
    state = _state([_milestone("A", "COMPLETE", checkpoint=None)])
    report = res.evaluate(state)
    assert "ROADMAP_CHECKPOINT_MISSING" in {f.code for f in report.findings}
    assert report.overall == "DRIFT_DETECTED"


def test_closed_milestone_reopened_fails_without_override():
    state = _state([_milestone("A", "ACTIVE", state_history=["COMPLETE"])])
    report = res.evaluate(state)
    assert "ROADMAP_CLOSED_MILESTONE_REOPENED" in {f.code for f in report.findings}


def test_owner_override_allows_reopen():
    state = _state(
        [
            _milestone(
                "A",
                "ACTIVE",
                state_history=["COMPLETE"],
                owner_override={"allows_reopen": True, "approved_by": "owner", "reason": "test", "at": "2026-08-30"},
            )
        ]
    )
    report = res.evaluate(state)
    assert "ROADMAP_CLOSED_MILESTONE_REOPENED" not in {f.code for f in report.findings}


def test_stale_next_pointer_not_in_queue():
    state = _state([_milestone("A", "NEXT")], queued_next=[])
    report = res.evaluate(state)
    assert "ROADMAP_STALE_NEXT_POINTER" in {f.code for f in report.findings}


def test_stale_next_pointer_mismatched_queue_head():
    state = _state([_milestone("A", "NEXT")], queued_next=["B_DOES_NOT_MATCH"])
    report = res.evaluate(state)
    codes = {f.code for f in report.findings}
    assert "ROADMAP_UNKNOWN_MILESTONE" in codes
    assert "ROADMAP_STALE_NEXT_POINTER" in codes


def test_unknown_milestone_reference_fails():
    state = _state([_milestone("A", "COMPLETE", checkpoint="x", unlocks=["GHOST"])])
    report = res.evaluate(state)
    assert "ROADMAP_UNKNOWN_MILESTONE" in {f.code for f in report.findings}


def test_can_start_allowed_when_next_and_satisfied():
    state = _state(
        [_milestone("A", "COMPLETE", checkpoint="x"), _milestone("B", "NEXT", dependencies=["A"])],
        queued_next=["B"],
    )
    allowed, reasons = res.can_start(state, "B")
    assert allowed
    assert reasons == []


def test_can_start_blocked_unsatisfied_dependency():
    state = _state(
        [_milestone("A", "NEXT"), _milestone("B", "NEXT", dependencies=["A"])],
        queued_next=["A"],
    )
    allowed, reasons = res.can_start(state, "B")
    assert not allowed
    assert any("UNSATISFIED_DEPENDENCIES" in r for r in reasons)


def test_can_start_blocked_conflicting_active_writer():
    state = _state([_milestone("A", "ACTIVE"), _milestone("B", "NEXT")])
    allowed, reasons = res.can_start(state, "B")
    assert not allowed
    assert any("CONFLICTING_ACTIVE_WRITER" in r for r in reasons)


def test_can_start_unknown_milestone():
    state = _state([_milestone("A", "NEXT")])
    allowed, reasons = res.can_start(state, "GHOST")
    assert not allowed
    assert reasons == ["ROADMAP_UNKNOWN_MILESTONE:GHOST"]


def test_deterministic_output_ordering():
    state = _state(
        [
            _milestone("A", "ACTIVE"),
            _milestone("B", "ACTIVE"),
            _milestone("C", "COMPLETE", checkpoint=None),
        ]
    )
    first = res.evaluate(state)
    second = res.evaluate(state)
    assert [(f.code, f.severity, f.message) for f in first.findings] == [
        (f.code, f.severity, f.message) for f in second.findings
    ]


def test_deterministic_content_identity():
    state = _state([_milestone("A", "COMPLETE", checkpoint="x")])
    first = res.evaluate(state)
    second = res.evaluate(state)
    assert first.content_identity == second.content_identity
    mutated = _state([_milestone("A", "COMPLETE", checkpoint="y")])
    third = res.evaluate(mutated)
    assert third.content_identity != first.content_identity


# ---------------------------------------------------------------------------
# Git-backed checks (temporary repos only; never touch real project worktrees)
# ---------------------------------------------------------------------------

def test_checkpoint_resolves_against_real_commit(git_repo):
    repo, sha = git_repo
    state = _state([_milestone("A", "COMPLETE", checkpoint=sha)], lineage_head=sha)
    report = res.evaluate(state, repo=repo)
    assert "ROADMAP_CHECKPOINT_NOT_IN_GIT" not in {f.code for f in report.findings}


def test_checkpoint_not_in_git_fails(git_repo):
    repo, sha = git_repo
    fake = "f" * 40
    state = _state([_milestone("A", "COMPLETE", checkpoint=fake)], lineage_head=sha)
    report = res.evaluate(state, repo=repo)
    assert "ROADMAP_CHECKPOINT_NOT_IN_GIT" in {f.code for f in report.findings}
    assert report.overall == "DRIFT_DETECTED"
    assert report.git_verification == res.GIT_VERIFICATION_MISMATCH


def test_head_sentinel_resolves_live(git_repo):
    repo, sha = git_repo
    state = _state([_milestone("A", "COMPLETE", checkpoint="HEAD")], lineage_head="HEAD")
    report = res.evaluate(state, repo=repo)
    assert "ROADMAP_CHECKPOINT_NOT_IN_GIT" not in {f.code for f in report.findings}
    assert "ROADMAP_RECORDED_HEAD_DIVERGENCE" not in {f.code for f in report.findings if f.severity == res.FAIL}


def test_recorded_head_divergence_when_repo_reset_behind(git_repo):
    repo, sha = git_repo
    (repo / "second.txt").write_text("x\n", encoding="utf-8")
    forward_sha = _commit_all(repo, "second")
    state = _state([_milestone("A", "COMPLETE", checkpoint=forward_sha)], lineage_head=forward_sha)
    _git(repo, "reset", "--hard", sha)
    report = res.evaluate(state, repo=repo)
    assert "ROADMAP_RECORDED_HEAD_DIVERGENCE" in {f.code for f in report.findings if f.severity == res.FAIL}
    assert report.git_verification == res.GIT_VERIFICATION_MISMATCH


def test_known_operational_diff_is_info_not_fatal(git_repo):
    repo, sha = git_repo
    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    state = _state([_milestone("A", "COMPLETE", checkpoint=sha)], lineage_head=sha, allowlist=["README.md"])
    report = res.evaluate(state, repo=repo)
    dirty = [f for f in report.findings if f.code == "ROADMAP_DIRTY_WORKTREE"]
    assert dirty and all(f.severity == res.INFO for f in dirty)
    assert report.overall == "ON_TRACK"


def test_unallowlisted_dirty_file_is_warning_not_fatal(git_repo):
    repo, sha = git_repo
    (repo / "README.md").write_text("changed\n", encoding="utf-8")
    state = _state([_milestone("A", "COMPLETE", checkpoint=sha)], lineage_head=sha, allowlist=[])
    report = res.evaluate(state, repo=repo)
    dirty = [f for f in report.findings if f.code == "ROADMAP_DIRTY_WORKTREE"]
    assert dirty and all(f.severity == res.WARNING for f in dirty)
    assert report.overall == "ON_TRACK"


def test_multiple_source_writers_detected(git_repo):
    repo, sha = git_repo
    _git(repo, "branch", "feature/shared-milestone-v1-a")
    _git(repo, "branch", "feature/shared-milestone-v1-b")
    wt_a = repo.parent / "wt-a"
    wt_b = repo.parent / "wt-b"
    _git(repo, "worktree", "add", str(wt_a), "feature/shared-milestone-v1-a")
    _git(repo, "worktree", "add", str(wt_b), "feature/shared-milestone-v1-b")
    (wt_a / "a.txt").write_text("a\n", encoding="utf-8")
    _commit_all(wt_a, "a work")
    (wt_b / "b.txt").write_text("b\n", encoding="utf-8")
    _commit_all(wt_b, "b work")

    state = _state([_milestone("SHARED_MILESTONE_V1", "ACTIVE")], lineage_head=sha)
    report = res.evaluate(state, repo=repo)
    fail_findings = [
        f for f in report.findings if f.code == "ROADMAP_MULTIPLE_SOURCE_WRITERS" and f.severity == res.FAIL
    ]
    assert fail_findings, [f.message for f in report.findings]


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _write_state(path: Path, state: dict) -> None:
    path.write_text(json.dumps(state), encoding="utf-8")


def test_cli_json_mode_emits_parseable_report(tmp_path, capsys):
    state_path = tmp_path / "roadmap_state.json"
    _write_state(
        state_path,
        _state([_milestone("A", "COMPLETE", checkpoint="x")], current={"milestone": "A", "state": "COMPLETE"}),
    )
    code = cli.main(["--state-file", str(state_path), "--repo", str(tmp_path / "does-not-exist"), "--json"])
    assert code == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["overall"] == res.OVERALL_GIT_NOT_CHECKED
    assert payload["git_verification"] == res.GIT_VERIFICATION_SKIPPED
    assert payload["checks"]["git/worktree consistency"] == "SKIPPED"
    assert payload["schema_version"] == res.SCHEMA_VERSION


def test_cli_check_exit_code_nonzero_on_drift(tmp_path, capsys):
    state_path = tmp_path / "roadmap_state.json"
    _write_state(state_path, _state([_milestone("A", "ACTIVE"), _milestone("B", "ACTIVE")]))
    code = cli.main(["--state-file", str(state_path), "--repo", str(tmp_path / "does-not-exist"), "--check"])
    capsys.readouterr()
    assert code == 1


def test_cli_check_exit_code_nonzero_when_git_skipped(tmp_path, capsys):
    state_path = tmp_path / "roadmap_state.json"
    _write_state(
        state_path,
        _state([_milestone("A", "COMPLETE", checkpoint="x")], current={"milestone": "A", "state": "COMPLETE"}),
    )
    code = cli.main(["--state-file", str(state_path), "--repo", str(tmp_path / "does-not-exist"), "--check"])
    capsys.readouterr()
    assert code == 1


def test_cli_can_start_allowed(tmp_path, capsys):
    state_path = tmp_path / "roadmap_state.json"
    _write_state(
        state_path,
        _state(
            [_milestone("A", "COMPLETE", checkpoint="x"), _milestone("B", "NEXT", dependencies=["A"])],
            queued_next=["B"],
        ),
    )
    code = cli.main(["--state-file", str(state_path), "--repo", str(tmp_path / "does-not-exist"), "--can-start", "B"])
    out = capsys.readouterr().out
    assert code == 0
    assert out.startswith("ALLOWED")


def test_cli_can_start_blocked(tmp_path, capsys):
    state_path = tmp_path / "roadmap_state.json"
    _write_state(state_path, _state([_milestone("A", "NEXT", dependencies=["MISSING"])]))
    code = cli.main(["--state-file", str(state_path), "--repo", str(tmp_path / "does-not-exist"), "--can-start", "A"])
    out = capsys.readouterr().out
    assert code == 1
    assert out.startswith("BLOCKED")


def test_cli_check_exit_zero_when_live_git_matches(git_repo, capsys):
    repo, sha = git_repo
    state_path = repo / "state.json"
    _write_state(
        state_path,
        _state(
            [_milestone("A", "COMPLETE", checkpoint=sha)],
            current={"milestone": "A", "state": "COMPLETE"},
            lineage_head=sha,
        ),
    )
    code = cli.main(["--state-file", str(state_path), "--repo", str(repo), "--check", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["overall"] == "ON_TRACK"
    assert payload["git_verification"] == res.GIT_VERIFICATION_VERIFIED
    assert payload["checks"]["git/worktree consistency"] == "PASS"
    assert payload["bootstrap"]["focused_selection_count"] == "UNKNOWN"
    assert "path" not in payload["bootstrap"]["worktrees"]
    assert len(payload["bootstrap"]["local_fast"]) == 5


def test_cli_git_unavailable_directory_is_not_on_track(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    state_path = tmp_path / "roadmap_state.json"
    _write_state(
        state_path,
        _state([_milestone("A", "COMPLETE", checkpoint="x")], current={"milestone": "A", "state": "COMPLETE"}),
    )
    code = cli.main(["--state-file", str(state_path), "--repo", str(empty), "--check", "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert code == 1
    assert payload["overall"] == res.OVERALL_GIT_NOT_CHECKED
    assert payload["git_verification"] == res.GIT_VERIFICATION_UNAVAILABLE
    assert payload["checks"]["git/worktree consistency"] == "UNAVAILABLE"


def test_detached_matching_head_stays_verified(git_repo):
    repo, sha = git_repo
    _git(repo, "checkout", "--detach", sha)
    state = _state([_milestone("A", "COMPLETE", checkpoint=sha)], lineage_head=sha)
    first = res.evaluate(state, repo=repo)
    second = res.evaluate(state, repo=repo)
    assert res.git_branch(repo) in ("", None)
    assert first.git_verification == res.GIT_VERIFICATION_VERIFIED
    assert first.overall == "ON_TRACK"
    assert [(f.code, f.severity, f.message) for f in first.findings] == [
        (f.code, f.severity, f.message) for f in second.findings
    ]


def test_worktree_classification_keeps_unmerged_and_ancestor(git_repo):
    repo, sha = git_repo
    _git(repo, "branch", "feature/keep-unmerged")
    ancestor = repo.parent / "wt-ancestor"
    unmerged = repo.parent / "wt-unmerged"
    _git(repo, "worktree", "add", "--detach", str(ancestor), sha)
    _git(repo, "worktree", "add", str(unmerged), "feature/keep-unmerged")
    (unmerged / "ahead.txt").write_text("ahead\n", encoding="utf-8")
    _commit_all(unmerged, "unmerged work")
    classified = res.classify_worktrees(repo)
    counts = classified["counts"]
    assert counts["ancestor_of_head"] >= 1
    assert counts["tracked_clean"] >= 1
    assert counts["unmerged"] >= 1
    assert "path" not in json.dumps(counts)
    classes = {row["class"] for row in classified["rows"]}
    assert "ANCESTOR_TRACKED_CLEAN" in classes
    assert "UNMERGED" in classes


def test_real_workflow_focused_selection_count_is_an_integer():
    count = res.focused_selection_count(res.REPO_ROOT)
    assert isinstance(count, int) and count >= 1


# ---------------------------------------------------------------------------
# Real bootstrap file sanity (read-only against this actual worktree)
# ---------------------------------------------------------------------------

def test_real_bootstrap_roadmap_state_is_on_track():
    state = res.load_state()
    report = res.evaluate(state, repo=res.REPO_ROOT)
    assert report.git_verification == res.GIT_VERIFICATION_VERIFIED
    assert report.overall == "ON_TRACK"
    assert not report.has_fail(), [(f.code, f.message) for f in report.findings if f.severity == res.FAIL]


# ---------------------------------------------------------------------------
# Authoritative-vs-historical checkpoint reconciliation
# (ROADMAP_REMOTE_CHECKPOINT_RECONCILIATION_AND_HOSTED_CI_CLOSEOUT_V1)
#
# A checkpoint resolving against *this* worktree's local Git object store is
# not sufficient: this worktree also holds many local-only feature branches
# that a fresh clone of origin/main never sees. The real regression is a
# COMPLETE milestone whose checkpoint only resolves because the object
# happens to exist locally, not because it is reachable from shared mainline
# history. `git_is_ancestor(repo, checkpoint, HEAD)` is the offline-provable
# proxy for "would also resolve in a fresh clone of the branch HEAD sits on".
# ---------------------------------------------------------------------------

def test_completed_milestone_checkpoints_are_ancestors_of_head():
    """Every COMPLETE milestone's checkpoint must be reachable from live HEAD.

    A local-only feature-branch commit can satisfy ``git cat-file -t`` in this
    worktree (the object exists) while being unreachable from any commit a
    fresh clone of the pushed branch would ever see. Ancestry of HEAD is the
    offline-checkable stand-in for "resolvable from shared Git history".
    """
    state = res.load_state()
    head = res.git_head(res.REPO_ROOT)
    assert head, "expected a resolvable HEAD in this worktree"
    milestones = res._milestones_by_id(state)
    non_ancestor = []
    for mid, m in milestones.items():
        if m.get("state") != "COMPLETE":
            continue
        checkpoint = m.get("checkpoint")
        if not checkpoint or checkpoint == res.HEAD_SENTINEL:
            continue
        if not res.git_is_ancestor(res.REPO_ROOT, checkpoint, head):
            non_ancestor.append((mid, checkpoint))
    assert not non_ancestor, non_ancestor


def test_notes_may_reference_unmerged_sha_without_effect(git_repo):
    """Descriptive lineage may name a SHA that was never merged anywhere;
    only the machine-readable `checkpoint` field is validated."""
    repo, sha = git_repo
    never_merged = "b" * 40
    state = _state(
        [
            _milestone(
                "A",
                "COMPLETE",
                checkpoint=sha,
                notes=f"historical local execution checkpoint {never_merged}, never merged to origin/main",
            )
        ],
        lineage_head=sha,
    )
    report = res.evaluate(state, repo=repo)
    assert not report.has_fail()


def test_retained_unmerged_milestone_keeps_terminal_status_without_claiming_merge(git_repo):
    """A RETAINED_UNMERGED-style milestone stays COMPLETE/ON_TRACK as long as
    its authoritative `checkpoint` is a real shared commit -- it must not need
    to (and must not) claim its own unmerged feature branch was ever merged."""
    repo, sha = git_repo
    unmerged_feature_sha = "c" * 40
    state = _state(
        [
            _milestone(
                "RETAINED_UNMERGED_EXAMPLE_V1",
                "COMPLETE",
                checkpoint=sha,
                narrative_disposition="PARTIAL_BY_EVIDENCE / RETAINED_UNMERGED",
                notes=f"Historical local execution checkpoint {unmerged_feature_sha} was never merged to origin/main.",
            )
        ],
        lineage_head=sha,
    )
    report = res.evaluate(state, repo=repo)
    assert not report.has_fail()
    assert "ROADMAP_CHECKPOINT_NOT_IN_GIT" not in {f.code for f in report.findings}


def test_hnx_and_text_native_authority_effects_unchanged_by_reconciliation():
    """The checkpoint-field correction must not change what either milestone
    is recorded as having actually done (authority effect, terminal state,
    RETAINED_UNMERGED disposition)."""
    state = res.load_state()
    milestones = res._milestones_by_id(state)
    hnx = milestones["HNX_PERIODIC_FINANCIAL_DOCUMENT_ROUTE_ACTIVATION_AND_RAW_ACQUISITION_V1"]
    text_native = milestones["TEXT_NATIVE_OFFICIAL_FINANCIAL_TABLE_EXTRACTION_SCALEOUT_V1"]

    assert hnx["state"] == "COMPLETE"
    assert hnx["authority_effect"] == (
        "RAW_DOCUMENT_ROUTE_AUTHORITY_PROMOTED_WITHIN_OWNER_APPROVED_SCOPE / FINANCIAL_FACT_AUTHORITY_UNCHANGED"
    )

    assert text_native["state"] == "COMPLETE"
    assert text_native["authority_effect"] == "NONE / FINANCIAL_FACT_AUTHORITY_UNCHANGED"
    assert "RETAINED_UNMERGED" in text_native["narrative_disposition"]

    # The corrected authoritative checkpoint is shared between both entries
    # (the single governance rebaseline commit that recorded both
    # dispositions) and differs from each entry's historical, unmerged
    # implementation SHA, which now lives only in `notes`.
    assert hnx["checkpoint"] == text_native["checkpoint"]
    assert hnx["checkpoint"] != "a0fcf8957c6e2d1bb541b93c136ce65b6d4223a2"
    assert text_native["checkpoint"] != "2507c86a3a8b07f6c09133097e799c5bd194f063"
    assert "a0fcf8957c6e2d1bb541b93c136ce65b6d4223a2" in hnx["notes"]
    assert "2507c86a3a8b07f6c09133097e799c5bd194f063" in text_native["notes"]


def test_truly_nonexistent_authoritative_checkpoint_still_fails(git_repo):
    repo, sha = git_repo
    state = _state([_milestone("A", "COMPLETE", checkpoint="d" * 40)], lineage_head=sha)
    report = res.evaluate(state, repo=repo)
    assert "ROADMAP_CHECKPOINT_NOT_IN_GIT" in {f.code for f in report.findings}
    assert report.overall == "DRIFT_DETECTED"


def test_no_milestone_specific_checkpoint_bypass_in_checker_source():
    """The checkpoint-existence check must stay milestone-agnostic: no
    hardcoded exemption for the two milestones this reconciliation fixed."""
    source = Path(res.__file__).read_text(encoding="utf-8")
    assert "HNX_PERIODIC_FINANCIAL_DOCUMENT_ROUTE_ACTIVATION_AND_RAW_ACQUISITION_V1" not in source
    assert "TEXT_NATIVE_OFFICIAL_FINANCIAL_TABLE_EXTRACTION_SCALEOUT_V1" not in source
    assert "ROADMAP_CHECKPOINT_NOT_IN_GIT" in source


def test_owner_admission_releases_only_current_and_preserves_history(git_repo, tmp_path):
    repo, sha = git_repo
    historical = _milestone("OLD", "COMPLETE", checkpoint=sha,
                            notes="Immutable lá»‹ch sá»­", state_history=["ACTIVE", "COMPLETE"])
    current = _milestone("CAPACITY", "ACTIVE", notes="Owner continuation", state_history=["ACTIVE"])
    state = _state([current, historical], current={"milestone": "CAPACITY", "state": "ACTIVE"}, lineage_head=sha)
    path = tmp_path / "roadmap.json"
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    original = path.read_text(encoding="utf-8")
    args = ["--state-file", str(path), "--repo", str(repo), "--admit-scope",
            "CONDITIONAL_RESEARCH_POSTURE_V2", "--owner-override", "--release-current-at", sha,
            "--scope-note", "Owner authorized implementation/CI/PR only"]
    assert cli.main(args) == 0
    updated = json.loads(path.read_text(encoding="utf-8"))
    assert updated["current"] == {"milestone": "CONDITIONAL_RESEARCH_POSTURE_V2", "state": "ACTIVE"}
    assert updated["milestones"][1]["checkpoint"] == sha
    assert updated["milestones"][1]["terminal_disposition"] == "IMPLEMENTATION_RELEASED_NO_PRODUCTION_ACTIVATION"
    assert updated["milestones"][2] == historical
    # Unrelated raw JSON, including Unicode, is preserved exactly.
    old_block = original[original.index('    {\n      "milestone_id": "OLD"'):]
    assert path.read_text(encoding="utf-8").endswith(old_block)
    stable = path.read_bytes()
    with pytest.raises(SystemExit):
        cli.main(args)
    assert path.read_bytes() == stable


def test_admission_requires_explicit_owner_and_exact_release(git_repo, tmp_path):
    repo, sha = git_repo
    state = _state([_milestone("CAPACITY", "ACTIVE", notes="Scope")],
                   current={"milestone": "CAPACITY", "state": "ACTIVE"}, lineage_head=sha)
    path = tmp_path / "roadmap.json"
    path.write_text(json.dumps(state, indent=2), encoding="utf-8")
    stable = path.read_bytes()
    base = ["--state-file", str(path), "--repo", str(repo), "--admit-scope", "CONDITIONAL_RESEARCH_POSTURE_V2",
            "--scope-note", "Owner scope", "--release-current-at", sha]
    with pytest.raises(SystemExit):
        cli.main(base)
    with pytest.raises(SystemExit):
        cli.main(base[:-1] + ["does-not-exist", "--owner-override"])
    assert path.read_bytes() == stable


def test_admission_after_complete_preserves_exact_predecessor_bytes(git_repo, tmp_path):
    repo, prior_sha = git_repo
    (repo / "README.md").write_text("verified release closure\n", encoding="utf-8")
    live_sha = _commit_all(repo, "release documentation")
    prior = _milestone("PRIOR", "COMPLETE", checkpoint=prior_sha,
                       notes="Preserved completion â€” lá»‹ch sá»­", state_history=["ACTIVE", "COMPLETE"])
    state = _state([prior], current={"milestone": "PRIOR", "state": "COMPLETE"}, lineage_head=prior_sha)
    path = tmp_path / "roadmap.json"
    path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    original = path.read_text(encoding="utf-8")
    args = ["--state-file", str(path), "--repo", str(repo), "--admit-scope", "FINANCIAL_RESEARCH_PACKAGE_V1",
            "--owner-override", "--release-current-at", live_sha, "--scope-note", "Standing owner delegation; bounded source layout"]
    assert cli.main(args) == 0
    updated_text = path.read_text(encoding="utf-8")
    updated = json.loads(updated_text)
    assert updated["milestones"][1] == prior
    assert updated_text.endswith(original[original.index('    {\n      "milestone_id": "PRIOR"'):])
    assert updated["current"] == {"milestone": "FINANCIAL_RESEARCH_PACKAGE_V1", "state": "ACTIVE"}
    assert updated["queued_next"] == []
    assert updated["milestones"][0]["starting_checkpoint"] == live_sha
    assert updated["milestones"][0]["owner_override"] == args[-1]


def test_admission_after_complete_refuses_unreachable_checkpoint(git_repo, tmp_path):
    repo, root_sha = git_repo
    _git(repo, "switch", "-c", "unmerged")
    (repo / "README.md").write_text("unmerged\n", encoding="utf-8")
    unmerged_sha = _commit_all(repo, "unmerged predecessor")
    _git(repo, "switch", "--detach", root_sha)
    prior = _milestone("PRIOR", "COMPLETE", checkpoint=unmerged_sha)
    path = tmp_path / "roadmap.json"
    _write_state(path, _state([prior], current={"milestone": "PRIOR", "state": "COMPLETE"}, lineage_head=root_sha))
    original = path.read_bytes()
    with pytest.raises(SystemExit):
        cli.main(["--state-file", str(path), "--repo", str(repo), "--admit-scope", "NEW",
                  "--owner-override", "--release-current-at", root_sha, "--scope-note", "Owner scope"])
    assert path.read_bytes() == original



def test_owner_local_closeout_preserves_history_and_does_not_admit_successor(git_repo, tmp_path):
    repo, sha = git_repo
    historical = _milestone('OLD', 'COMPLETE', checkpoint=sha, notes='Immutable lịch sử')
    state = _state([_milestone('E0', 'ACTIVE', notes='Bounded scope'), historical],
                   current={'milestone':'E0','state':'ACTIVE'}, lineage_head=sha)
    path = tmp_path / 'local-closeout.json'
    path.write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
    old = path.read_text(encoding='utf-8')
    args = ['--state-file',str(path),'--repo',str(repo),'--complete-local-scope','E0',
            '--owner-override','--checkpoint-at',sha,'--scope-note','Owner local release only']
    assert cli.main(args) == 0
    changed = res.load_state(path)
    assert changed['current'] == {'milestone':'E0','state':'COMPLETE'}
    assert changed['queued_next'] == []
    assert changed['milestones'][0]['checkpoint'] == sha
    assert changed['milestones'][0]['terminal_disposition'] == 'LOCAL_IMPLEMENTATION_COMPLETE_NOT_PROMOTED'
    assert path.read_text(encoding='utf-8').endswith(old[old.index('    {\n      "milestone_id": "OLD"'):])
    assert res.evaluate(changed,repo=repo).overall == 'ON_TRACK'
    stable = path.read_bytes()
    with pytest.raises(SystemExit): cli.main(args)
    assert path.read_bytes() == stable


@pytest.mark.parametrize('failure',['owner','head','dirty','queue','wrong-current','offline'])
def test_local_closeout_refuses_invalid_gate_without_writing(git_repo,tmp_path,failure):
    repo, sha = git_repo
    state = _state([_milestone('E0','ACTIVE',notes='Bounded scope')],
                   current={'milestone':'E0','state':'ACTIVE'},lineage_head=sha)
    if failure == 'queue': state['queued_next'] = ['NEXT']
    path = tmp_path/'local-closeout.json'
    path.write_text(json.dumps(state,indent=2),encoding='utf-8')
    stable = path.read_bytes()
    args = ['--state-file',str(path),'--repo',str(repo),'--complete-local-scope',
            'OTHER' if failure == 'wrong-current' else 'E0', '--checkpoint-at',
            'HEAD' if failure == 'head' else sha, '--scope-note','Owner scope']
    if failure != 'owner': args.append('--owner-override')
    if failure == 'dirty': (repo/'README.md').write_text('uncommitted')
    if failure == 'offline': args[3] = str(tmp_path/'missing')
    with pytest.raises(SystemExit): cli.main(args)
    assert path.read_bytes() == stable


# ---------------------------------------------------------------------------
# Exact CAS-guarded lane scope amendment
# ---------------------------------------------------------------------------

def _lane_world(tmp_path):
    """Hermetic coordinator repo with initialized native development_control."""
    coord = tmp_path / "coordinator"
    _init_repo(coord)
    _git(coord, "checkout", "-q", "-b", "main")
    (coord / "README.md").write_text("root\n", encoding="utf-8")
    base_sha = _commit_all(coord, "initial main")
    state_path = coord / "docs" / "ROADMAP_STATE.json"
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state = _state([], current={}, queued_next=[], lineage_head=base_sha)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    def run(*cli_args):
        return cli.main(["--repo", str(coord), "--state-file", str(state_path), "--json", *cli_args])

    assert run("--init-lanes", "--owner-override", "--scope-note", "init coordinator", "--agent", "Claude") == 0
    return coord, base_sha, state_path, run


def _admit_lane(world, mid, allowed_paths, *, agent="Claude", shared_paths=None, lease_note=None, base_sha=None):
    coord, default_base, _, run = world
    base = base_sha or default_base
    wt = coord.parent / mid
    _git(coord, "worktree", "add", "-q", "-b", "feature/" + mid, str(wt), base)
    spec = {
        "milestone_id": mid,
        "responsible_agent": agent,
        "branch": "feature/" + mid,
        "worktree": str(wt),
        "base_sha": base,
        "domain": mid,
        "mode": "IMPLEMENTATION",
        "allowed_paths": list(allowed_paths),
        "shared_paths": list(shared_paths or []),
        "dependencies": [],
        "provides": {},
        "consumes": {},
        "required_checks": ["unit-tests"],
    }
    if lease_note is not None:
        spec["lease_note"] = lease_note
    spec_file = coord.parent / f"{mid}-spec.json"
    spec_file.write_text(json.dumps(spec), encoding="utf-8")
    rc = run("--admit-lane", mid, "--lane-spec", str(spec_file),
             "--owner-override", "--scope-note", f"admit {mid}", "--agent", "Claude")
    return wt, rc


def _scope_spec(world, mid, *, after_base=None, after_allowed=None, after_shared=None):
    coord, _, state_path, _ = world
    state = res.load_state(state_path)
    control = state["development_control"]
    lane = res.lane_by_id(state, mid)
    wt = Path(lane["worktree"])
    before = {
        "base_sha": lane["base_sha"],
        "allowed_paths": list(lane["allowed_paths"]),
        "shared_paths": list(lane["shared_paths"]),
    }
    after = {
        "base_sha": after_base if after_base is not None else before["base_sha"],
        "allowed_paths": list(after_allowed) if after_allowed is not None else list(before["allowed_paths"]),
        "shared_paths": list(after_shared) if after_shared is not None else list(before["shared_paths"]),
    }
    return {
        "schema": "stocklookup_lane_scope_amendment/1",
        "expected_revision": control["revision"],
        "coordinator_head": _git(coord, "rev-parse", "HEAD").strip(),
        "milestone_id": mid,
        "lane_head": _git(wt, "rev-parse", "HEAD").strip(),
        "before": before,
        "after": after,
    }


def _amend_scope(world, spec, *, agent="Claude", owner=True, note="Owner exact scope correction"):
    coord, _, _, run = world
    spec_file = coord.parent / "scope-amendment.json"
    spec_file.write_text(json.dumps(spec), encoding="utf-8")
    extra = ["--owner-override"] if owner else []
    return run("--amend-lane-scope", "--scope-spec", str(spec_file),
               "--agent", agent, "--scope-note", note, *extra)


def test_lane_scope_amendment_shrink_frees_lease_for_second_lane(tmp_path, capsys):
    world = _lane_world(tmp_path)
    coord, base_sha, state_path, run = world
    wt_a, rc = _admit_lane(
        world, "LANE_A",
        ["stocklookup_core/alpha/", "config/shared_a.json"],
        agent="Claude",
        shared_paths=["config/shared_a.json"],
        lease_note="Owner exact temporary lease",
    )
    assert rc == 0
    assert run("--transition-lane", "LANE_A", "--lane-state", "ACTIVE",
               "--owner-override", "--scope-note", "activate A", "--agent", "Claude") == 0

    # A second lane requesting config/shared_a.json is blocked by overlap before shrinking LANE_A.
    wt_b = coord.parent / "LANE_B"
    _git(coord, "worktree", "add", "-q", "-b", "feature/LANE_B", str(wt_b), base_sha)
    lane_b_spec = {
        "milestone_id": "LANE_B", "responsible_agent": "Claude",
        "branch": "feature/LANE_B", "worktree": str(wt_b), "base_sha": base_sha,
        "domain": "LANE_B", "mode": "IMPLEMENTATION",
        "allowed_paths": ["config/shared_a.json"], "shared_paths": ["config/shared_a.json"],
        "lease_note": "Owner exact lease for B",
        "dependencies": [], "provides": {}, "consumes": {}, "required_checks": ["unit-tests"],
    }
    lane_b_file = coord.parent / "LANE_B-spec.json"
    lane_b_file.write_text(json.dumps(lane_b_spec), encoding="utf-8")
    capsys.readouterr()
    assert run("--admit-lane", "LANE_B", "--lane-spec", str(lane_b_file),
               "--owner-override", "--scope-note", "admit B", "--agent", "Claude") == 2
    assert "LANE_OWNERSHIP_OVERLAP" in capsys.readouterr().err

    # Shrink LANE_A to release config/shared_a.json.
    before_bytes = state_path.read_bytes()
    before_state = res.load_state(state_path)
    spec = _scope_spec(world, "LANE_A", after_allowed=["stocklookup_core/alpha/"], after_shared=[])
    capsys.readouterr()
    assert _amend_scope(world, spec, note="Release unused shared lease") == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["authority_effect"] == "NONE"
    assert payload["merge_authorized"] is False
    assert payload["runtime_authorized"] is False
    assert payload["operation"]["operation"] == "LANE_SCOPE_AMENDMENT"

    after_state = res.load_state(state_path)
    old_ctrl, new_ctrl = before_state["development_control"], after_state["development_control"]
    assert new_ctrl["revision"] == old_ctrl["revision"] + 1
    assert new_ctrl["history"][:-1] == old_ctrl["history"]
    assert new_ctrl["history"][-1]["operation"] == "LANE_SCOPE_AMENDMENT"
    assert new_ctrl["history"][-1]["owner_note"] == "Release unused shared lease"
    assert new_ctrl["history"][-1]["before"] == spec["before"]
    assert new_ctrl["history"][-1]["after"] == spec["after"]
    assert new_ctrl["history"][-1]["coordinator_head"] == spec["coordinator_head"]
    assert new_ctrl["history"][-1]["lane_head"] == spec["lane_head"]

    old_lane = res.lane_by_id(before_state, "LANE_A")
    new_lane = res.lane_by_id(after_state, "LANE_A")
    assert new_lane["allowed_paths"] == ["stocklookup_core/alpha/"]
    assert new_lane["shared_paths"] == []
    assert new_lane["history"][:-1] == old_lane["history"]
    assert new_lane["history"][-1]["operation"] == "LANE_SCOPE_AMENDMENT"
    assert new_lane["history"][-1]["owner_note"] == "Release unused shared lease"
    for unchanged in ("responsible_agent", "state", "checkpoint", "dependencies",
                      "provides", "consumes", "required_checks", "branch", "worktree", "domain", "mode"):
        assert new_lane[unchanged] == old_lane[unchanged]
    marker = b'  "development_control": '
    assert before_bytes.split(marker)[0] == state_path.read_bytes().split(marker)[0]

    # Now LANE_B admission succeeds because the lease was freed.
    assert run("--admit-lane", "LANE_B", "--lane-spec", str(lane_b_file),
               "--owner-override", "--scope-note", "admit B", "--agent", "Claude") == 0
    assert res.evaluate(res.load_state(state_path), repo=coord).overall == "ON_TRACK"


def test_lane_scope_amendment_advances_base_after_merging_new_main(tmp_path):
    world = _lane_world(tmp_path)
    coord, _, state_path, run = world
    wt, rc = _admit_lane(world, "LANE_MAIN", ["stocklookup_core/beta/"])
    assert rc == 0
    assert run("--transition-lane", "LANE_MAIN", "--lane-state", "ACTIVE",
               "--owner-override", "--scope-note", "activate", "--agent", "Claude") == 0

    # Lane makes an in-scope commit.
    (wt / "stocklookup_core" / "beta").mkdir(parents=True, exist_ok=True)
    (wt / "stocklookup_core" / "beta" / "work.py").write_text("x = 1\n", encoding="utf-8")
    _commit_all(wt, "lane work")

    # Main advances with an unrelated commit (e.g. merged PR) and lane merges main.
    (coord / "docs" / "other_pr.md").write_text("merged PR\n", encoding="utf-8")
    _git(coord, "add", "docs/other_pr.md")
    _git(coord, "commit", "-q", "-m", "PR merged on main")
    new_main = _git(coord, "rev-parse", "HEAD").strip()
    _git(wt, "merge", "--no-edit", new_main)

    # Before amendment, check_lane fails because docs/other_pr.md is in old_base..HEAD.
    pre_check = res.check_lane(res.load_state(state_path), "LANE_MAIN", repo=coord)
    assert any("LANE_PROHIBITED_CHANGE:docs/other_pr.md" in e for e in pre_check["errors"])

    # Amend base_sha forward to new_main.
    spec = _scope_spec(world, "LANE_MAIN", after_base=new_main)
    assert _amend_scope(world, spec, note="Advance base_sha after merging new main") == 0

    post_state = res.load_state(state_path)
    post_check = res.check_lane(post_state, "LANE_MAIN", repo=coord)
    assert post_check["errors"] == []
    assert post_check["paths"] == ["stocklookup_core/beta/work.py"]
    assert res.evaluate(post_state, repo=coord).overall == "ON_TRACK"


def test_lane_scope_amendment_refusals(tmp_path):
    world = _lane_world(tmp_path)
    coord, base_sha, state_path, run = world
    wt_a, rc = _admit_lane(
        world, "LANE_A",
        ["stocklookup_core/alpha/", "stocklookup_core/extra/"],
        agent="Claude",
        lease_note="Owner lease note",
    )
    assert rc == 0
    assert run("--transition-lane", "LANE_A", "--lane-state", "ACTIVE",
               "--owner-override", "--scope-note", "activate A", "--agent", "Claude") == 0
    wt_b, rc_b = _admit_lane(world, "LANE_B", ["stocklookup_core/gamma/"], agent="Codex")
    assert rc_b == 0
    assert run("--transition-lane", "LANE_B", "--lane-state", "ACTIVE",
               "--owner-override", "--scope-note", "activate B", "--agent", "Claude") == 0

    # Create a real change in LANE_A under stocklookup_core/alpha/.
    (wt_a / "stocklookup_core" / "alpha").mkdir(parents=True, exist_ok=True)
    (wt_a / "stocklookup_core" / "alpha" / "mod.py").write_text("v = 1\n", encoding="utf-8")
    lane_a_head = _commit_all(wt_a, "alpha change")

    # Create an unrelated root commit (not a descendant of base_sha) without touching coord's worktree.
    tree_sha = _git(coord, "rev-parse", "HEAD^{tree}").strip()
    orphan_sha = _git(coord, "commit-tree", tree_sha, "-m", "unrelated orphan commit").strip()

    # Advance main by one commit (add only main_step.txt so docs/ROADMAP_STATE.json stays untracked),
    # merge into LANE_A, then amend base_sha forward so we can test backward base_sha.
    (coord / "main_step.txt").write_text("step\n", encoding="utf-8")
    _git(coord, "add", "main_step.txt")
    _git(coord, "commit", "-q", "-m", "main step")
    main_step = _git(coord, "rev-parse", "HEAD").strip()
    _git(wt_a, "merge", "--no-edit", main_step)
    assert _amend_scope(world, _scope_spec(world, "LANE_A", after_base=main_step)) == 0

    state = res.load_state(state_path)
    valid_spec = _scope_spec(world, "LANE_A", after_allowed=["stocklookup_core/alpha/"])
    snapshot = state_path.read_bytes()

    # 1. Stale revision
    bad = json.loads(json.dumps(valid_spec))
    bad["expected_revision"] -= 1
    with pytest.raises(res.RoadmapStateError, match="LANE_SCOPE_AMENDMENT_REVISION_CHANGED"):
        res.prepare_lane_scope_amendment(state, bad, repo=coord, agent="Claude")

    # 2. Wrong agent
    with pytest.raises(res.RoadmapStateError, match="LANE_SCOPE_AMENDMENT_INTEGRATION_OWNER_REQUIRED"):
        res.prepare_lane_scope_amendment(state, valid_spec, repo=coord, agent="Codex")

    # 3. Different coordinator head
    bad = json.loads(json.dumps(valid_spec))
    bad["coordinator_head"] = base_sha
    with pytest.raises(res.RoadmapStateError, match="LANE_SCOPE_AMENDMENT_EXACT_CLEAN_COORDINATOR_HEAD_REQUIRED"):
        res.prepare_lane_scope_amendment(state, bad, repo=coord, agent="Claude")

    # 3b. Dirty coordinator worktree
    (coord / "README.md").write_text("dirty\n", encoding="utf-8")
    try:
        with pytest.raises(res.RoadmapStateError, match="LANE_SCOPE_AMENDMENT_EXACT_CLEAN_COORDINATOR_HEAD_REQUIRED"):
            res.prepare_lane_scope_amendment(state, valid_spec, repo=coord, agent="Claude")
    finally:
        _git(coord, "checkout", "--", "README.md")

    # 4. Before mismatch (including order-sensitive list check)
    bad = json.loads(json.dumps(valid_spec))
    bad["before"]["allowed_paths"] = list(reversed(bad["before"]["allowed_paths"]))
    with pytest.raises(res.RoadmapStateError, match="LANE_SCOPE_AMENDMENT_BEFORE_MISMATCH"):
        res.prepare_lane_scope_amendment(state, bad, repo=coord, agent="Claude")

    # 5a. Backward base_sha (base_sha is an ancestor of current main_step, not descendant)
    bad = json.loads(json.dumps(valid_spec))
    bad["after"]["base_sha"] = base_sha
    with pytest.raises(res.RoadmapStateError, match="LANE_SCOPE_AMENDMENT_BASE_NOT_FORWARD"):
        res.prepare_lane_scope_amendment(state, bad, repo=coord, agent="Claude")

    # 5b. Unrelated base_sha
    bad = json.loads(json.dumps(valid_spec))
    bad["after"]["base_sha"] = orphan_sha
    with pytest.raises(res.RoadmapStateError, match="LANE_SCOPE_AMENDMENT_BASE_NOT_FORWARD"):
        res.prepare_lane_scope_amendment(state, bad, repo=coord, agent="Claude")

    # 6. Base is forward of before.base_sha but not an ancestor of live lane HEAD
    (coord / "unmerged_main.txt").write_text("unmerged\n", encoding="utf-8")
    _git(coord, "add", "unmerged_main.txt")
    _git(coord, "commit", "-q", "-m", "unmerged main")
    unmerged_main = _git(coord, "rev-parse", "HEAD").strip()
    bad = _scope_spec(world, "LANE_A", after_base=unmerged_main)
    with pytest.raises(res.RoadmapStateError, match="LANE_SCOPE_AMENDMENT_BASE_NOT_ANCESTOR_OF_HEAD"):
        res.prepare_lane_scope_amendment(state, bad, repo=coord, agent="Claude")

    # 7. lane_head mismatch
    bad = _scope_spec(world, "LANE_A", after_allowed=["stocklookup_core/alpha/"])
    bad["lane_head"] = lane_a_head  # pre-merge head
    with pytest.raises(res.RoadmapStateError, match="LANE_SCOPE_AMENDMENT_LANE_HEAD_MISMATCH"):
        res.prepare_lane_scope_amendment(state, bad, repo=coord, agent="Claude")

    # 8. Protected path
    bad = _scope_spec(world, "LANE_A", after_allowed=["stocklookup_core/alpha/", "data/"])
    with pytest.raises(res.RoadmapStateError, match="LANE_SCOPE_AMENDMENT_PROTECTED_PATH"):
        res.prepare_lane_scope_amendment(state, bad, repo=coord, agent="Claude")

    # 9. shared_paths not subset of allowed_paths
    bad = _scope_spec(world, "LANE_A", after_allowed=["stocklookup_core/alpha/"], after_shared=["config/x.json"])
    with pytest.raises(res.RoadmapStateError, match="LANE_SCOPE_AMENDMENT_SHARED_NOT_IN_ALLOWED"):
        res.prepare_lane_scope_amendment(state, bad, repo=coord, agent="Claude")

    # 10. Overlap with another active lane (LANE_B owns stocklookup_core/gamma/)
    bad = _scope_spec(world, "LANE_A", after_allowed=["stocklookup_core/alpha/", "stocklookup_core/gamma/sub.py"])
    with pytest.raises(res.RoadmapStateError, match="LANE_SCOPE_AMENDMENT_VALIDATION_FAILED:.*LANE_OWNERSHIP_OVERLAP"):
        res.prepare_lane_scope_amendment(state, bad, repo=coord, agent="Claude")

    # 11. Lane's real changes outside new scope (LANE_A modified stocklookup_core/alpha/mod.py)
    bad = _scope_spec(world, "LANE_A", after_allowed=["stocklookup_core/extra/"])
    with pytest.raises(res.RoadmapStateError, match="LANE_SCOPE_AMENDMENT_CHECK_LANE_FAILED:.*LANE_PROHIBITED_CHANGE"):
        res.prepare_lane_scope_amendment(state, bad, repo=coord, agent="Claude")

    # 12. Extra / missing spec keys
    bad_extra = _scope_spec(world, "LANE_A", after_allowed=["stocklookup_core/alpha/"])
    bad_extra["extra_key"] = True
    with pytest.raises(res.RoadmapStateError, match="LANE_SCOPE_AMENDMENT_EXACT_SPEC_REQUIRED"):
        res.prepare_lane_scope_amendment(state, bad_extra, repo=coord, agent="Claude")
    bad_missing = _scope_spec(world, "LANE_A", after_allowed=["stocklookup_core/alpha/"])
    del bad_missing["lane_head"]
    with pytest.raises(res.RoadmapStateError, match="LANE_SCOPE_AMENDMENT_EXACT_SPEC_REQUIRED"):
        res.prepare_lane_scope_amendment(state, bad_missing, repo=coord, agent="Claude")

    # 12b. Duplicate paths, no-op amendment, and missing lease_note for shared_paths
    bad_dup = _scope_spec(world, "LANE_A", after_allowed=["stocklookup_core/alpha/", "stocklookup_core/alpha/"])
    with pytest.raises(res.RoadmapStateError, match="LANE_SCOPE_AMENDMENT_DUPLICATE_ALLOWED_PATHS"):
        res.prepare_lane_scope_amendment(state, bad_dup, repo=coord, agent="Claude")
    bad_noop = _scope_spec(world, "LANE_A")
    with pytest.raises(res.RoadmapStateError, match="LANE_SCOPE_AMENDMENT_NO_CHANGE"):
        res.prepare_lane_scope_amendment(state, bad_noop, repo=coord, agent="Claude")
    bad_lease = _scope_spec(world, "LANE_B", after_allowed=["stocklookup_core/gamma/", "config/new.json"],
                            after_shared=["config/new.json"])
    with pytest.raises(res.RoadmapStateError, match="LANE_SCOPE_AMENDMENT_LEASE_NOTE_REQUIRED"):
        res.prepare_lane_scope_amendment(state, bad_lease, repo=coord, agent="Claude")

    # 13. Non-amendable states: COMPLETE_LOCAL and ABANDONED (terminal)
    wt_a_head = _git(wt_a, "rev-parse", "HEAD").strip()
    assert run("--transition-lane", "LANE_A", "--lane-state", "REVIEW_READY",
               "--checkpoint-at", wt_a_head, "--owner-override", "--scope-note", "review", "--agent", "Claude") == 0
    assert run("--transition-lane", "LANE_A", "--lane-state", "COMPLETE_LOCAL",
               "--checkpoint-at", wt_a_head, "--owner-override", "--scope-note", "complete", "--agent", "Claude") == 0
    complete_spec = _scope_spec(world, "LANE_A", after_allowed=["stocklookup_core/alpha/"])
    with pytest.raises(res.RoadmapStateError, match="LANE_SCOPE_AMENDMENT_STATE_NOT_AMENDABLE:LANE_A:COMPLETE_LOCAL"):
        res.prepare_lane_scope_amendment(res.load_state(state_path), complete_spec, repo=coord, agent="Claude")
    assert _amend_scope(world, complete_spec) == 2

    assert run("--transition-lane", "LANE_B", "--lane-state", "ABANDONED",
               "--owner-override", "--scope-note", "abandon B", "--agent", "Claude") == 0
    abandoned_spec = _scope_spec(world, "LANE_B", after_allowed=["stocklookup_core/gamma/", "stocklookup_core/delta/"])
    with pytest.raises(res.RoadmapStateError, match="LANE_SCOPE_AMENDMENT_STATE_NOT_AMENDABLE:LANE_B:ABANDONED"):
        res.prepare_lane_scope_amendment(res.load_state(state_path), abandoned_spec, repo=coord, agent="Claude")

    # Confirm CLI refusal leaves disk unchanged and requires --owner-override.
    frozen = state_path.read_bytes()
    assert _amend_scope(world, abandoned_spec) == 2
    assert _amend_scope(world, abandoned_spec, owner=False) == 2
    assert state_path.read_bytes() == frozen
    assert snapshot != b""

