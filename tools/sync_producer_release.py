"""Explicitly sync approved Producer source while retaining a pending input freeze."""
import argparse
import json
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def sync_producer_release(root: Path, approved_head: str, inventory: dict) -> dict:
    """Explicit operator release sync. Call with the active Production Python/profile."""
    from pending_session_input_freeze import _git, _sync_frozen_checkout
    from runtime_paths import workspace_profile

    root = root.resolve()
    if not os.environ.get("STOCK_LOOKUP_WORKSPACE_PROFILE", "").strip():
        raise ValueError("FREEZE_SYNC_PROFILE_REQUIRED")
    try:
        from tools.run_owner_daily import bind_active_workspace
        bind_active_workspace(root)
        profile = workspace_profile()
    except (ValueError, RuntimeError) as exc:
        raise ValueError("FREEZE_SYNC_PROFILE_REFUSED:" + str(exc)) from exc
    if profile is None or profile["paths"]["producer"] != root:
        raise ValueError("FREEZE_SYNC_WRONG_PROFILE_ROOT")
    if not (Path.home() / ".stocklookup" / "active_workspace.json").is_file():
        raise ValueError("FREEZE_SYNC_ACTIVE_BINDING_REQUIRED")
    from release_checkout_identity import origin_matches_checkout
    from tools.capture_writer_lease import writer_lease
    from tools.post_daily_candlestick_release import observe_command_lines, recheck_writers, target_lock
    from tools.release_orchestrator import SingleInstanceLock

    code, origin = _git(root, "remote", "get-url", "origin")
    if code or not origin_matches_checkout(origin, "stock-core-private"):
        raise ValueError("FREEZE_SYNC_WRONG_ORIGIN")
    with (writer_lease(root), SingleInstanceLock(),
          target_lock("runtime", profile["paths"]["runtime"]),
          target_lock("web", profile["paths"]["dashboard"])):
        return _sync_frozen_checkout(
            root, approved_head, inventory,
            check_writers=lambda: recheck_writers(observe_command_lines, "PRODUCER_RELEASE_SYNC"),
        )


def rebaseline_freeze_inventory(root: Path, original: dict, original_head: str, history: Path) -> dict:
    """Prove an inventory transition without fetching, taking leases or writing files."""
    from hashlib import sha256
    import re

    from pending_session_input_freeze import (REGISTRY_RELATIVE, _git, _pending_sessions,
                                              classify_pending_input_freeze, freeze_byte_inventory)
    from release_checkout_identity import origin_matches_checkout
    from runtime_paths import workspace_path

    def git(repo, *args):
        code, output = _git(repo, *args)
        if code:
            raise ValueError("FREEZE_REBASELINE_GIT_REFUSED:" + args[0])
        return output.strip()

    def registry_at(revision):
        code, raw = _git(history, "show", f"{revision}:{REGISTRY_RELATIVE}")
        if code:
            raise ValueError("FREEZE_REBASELINE_REGISTRY_UNREADABLE")
        body = json.loads(raw)
        if raw != serialize(body):
            raise ValueError("FREEZE_REBASELINE_REGISTRY_FORMAT")
        return body

    def serialize(body):
        return json.dumps(body, ensure_ascii=False, indent=2) + "\n"

    root = root.resolve()
    if not re.fullmatch(r"[0-9a-f]{40}", original_head):
        raise ValueError("FREEZE_REBASELINE_EXACT_ORIGINAL_HEAD_REQUIRED")
    if not origin_matches_checkout(git(root, "remote", "get-url", "origin"), "stock-core-private"):
        raise ValueError("FREEZE_SYNC_WRONG_ORIGIN")
    if git(root, "symbolic-ref", "--short", "HEAD") != "main":
        raise ValueError("FREEZE_SYNC_WRONG_BRANCH")
    head = git(root, "rev-parse", "HEAD")
    remote = git(root, "ls-remote", "--exit-code", "origin", "refs/heads/main").split()
    if len(remote) != 2 or remote[1] != "refs/heads/main" or not re.fullmatch(r"[0-9a-f]{40}", remote[0]):
        raise ValueError("FREEZE_REBASELINE_RELEASE_UNVERIFIED")
    # Require the observed checkout to be released, and the original head to be
    # on its first-parent chain. A merged side branch cannot supply Daily commits.
    if _git(history, "merge-base", "--is-ancestor", head, remote[0])[0]:
        raise ValueError("FREEZE_REBASELINE_RELEASE_UNVERIFIED")
    chain = git(history, "rev-list", "--first-parent", "--reverse", f"{original_head}..{head}").splitlines()
    if not chain or git(history, "rev-parse", chain[0] + "^1") != original_head:
        raise ValueError("FREEZE_REBASELINE_ORIGINAL_HEAD_NOT_ON_LINEAGE")

    current, protected = freeze_byte_inventory(root)
    if set(original) != {"registry_sha256", "sources"} or current["sources"] != original["sources"]:
        raise ValueError("FREEZE_REBASELINE_SOURCE_PIN_MISMATCH")
    raw = (root / REGISTRY_RELATIVE).read_bytes()
    working = json.loads(raw)
    lf = serialize(working).encode("utf-8")
    if raw not in (lf, lf.replace(b"\n", b"\r\n")) or sha256(raw).hexdigest() != current["registry_sha256"]:
        raise ValueError("FREEZE_REBASELINE_REGISTRY_FORMAT")
    separator = b"\r\n" if raw != lf else b"\n"
    previous = registry_at(original_head)
    retained = workspace_path("retained", root)
    advances = []
    for commit in chain:
        before = previous
        previous = registry_at(commit)
        if serialize(before) == serialize(previous):
            continue
        added = _pending_sessions(before, previous)
        if added is None or len(added) != 1:
            raise ValueError("FREEZE_REBASELINE_NONADDITIVE_COMMIT:" + commit)
        (session,) = added
        if (len(git(history, "rev-list", "--parents", "-n", "1", commit).split()) != 2
                or git(history, "show", "-s", "--format=%B", commit) != f"daily: retain {session} completed session"
                or git(history, "diff-tree", "--no-commit-id", "--name-only", "-r", commit) != REGISTRY_RELATIVE):
            raise ValueError("FREEZE_REBASELINE_NOT_DAILY_COMMIT:" + commit)
        for ledger in ("sessions", "completed_sessions"):
            before[ledger][session] = previous[ledger][session]
        if serialize(before) != serialize(previous):
            raise ValueError("FREEZE_REBASELINE_UNEXPECTED_REGISTRY_DIFF:" + commit)

        row = previous["completed_sessions"][session]
        selection = previous["sessions"][session]
        if (row.get("status") != "COMPLETED_RETAINED_EVIDENCE" or row.get("trading_day_valid") is not True
                or row.get("frozen_input_identities") != {k: value["artifact_identity"] for k, value in selection.items()}):
            raise ValueError("FREEZE_REBASELINE_INVALID_DAILY_ROW:" + session)
        records = sorted((retained / "operations-review/canonical-daily-operation-v1" / session)
                         .glob("*/daily_operation_record.json"))
        if len(records) != 1:
            raise ValueError("FREEZE_REBASELINE_DAILY_SEAL_UNVERIFIED:" + session)
        record_bytes = records[0].read_bytes()
        record = json.loads(record_bytes)
        identity = record.get("operation_identity")
        if (record.get("session") != session or record.get("daily_operation_state") != "LOCAL_COMPLETE"
                or record.get("daily_producer_status") != "COMPLETED"
                or record.get("runtime_release_status") != "READY" or record.get("trusted_subset_status") != "READY"
                or (record.get("acquisition") or {}).get("resolved_completed_session") != session
                or (record.get("freeze") or {}).get("frozen_input_identities") != row["frozen_input_identities"]
                or (record.get("registration") or {}).get("selection") != selection
                or not record.get("daily_producer_run_identity") or not record.get("daily_producer_operation_identity")
                or not isinstance(identity, str)
                or not re.fullmatch(r"canonical_daily_operation:[0-9a-f]{64}", identity)
                or records[0].parent.name != "op-" + identity.split(":")[1]):
            raise ValueError("FREEZE_REBASELINE_DAILY_SEAL_UNVERIFIED:" + session)
        advances.append({"session": session, "commit": commit, "operation_identity": identity,
                         "operation_record_sha256": sha256(record_bytes).hexdigest()})

    pending = _pending_sessions(previous, working)
    if not advances or pending is None or pending != classify_pending_input_freeze(root).sessions:
        raise ValueError("FREEZE_REBASELINE_NO_VERIFIED_TRANSITION")
    for advance in advances:
        for ledger in ("sessions", "completed_sessions"):
            del working[ledger][advance["session"]]
    reconstructed = serialize(working).encode("utf-8").replace(b"\n", separator)
    if sha256(reconstructed).hexdigest() != original["registry_sha256"]:
        raise ValueError("FREEZE_REBASELINE_ORIGINAL_PIN_MISMATCH")
    if (git(root, "rev-parse", "HEAD") != head or freeze_byte_inventory(root) != (current, protected)
            or git(root, "ls-remote", "--exit-code", "origin", "refs/heads/main").split() != remote):
        raise ValueError("FREEZE_REBASELINE_CHECKOUT_CHANGED")
    return {"original_head": original_head, "head": head, "observed_main": remote[0],
            "original_inventory": original, "inventory": current, "pending_sessions": list(pending),
            "protected_paths": protected, "daily_advances": advances}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approved-head")
    parser.add_argument("--rebaseline-from", metavar="ORIGINAL_HEAD")
    parser.add_argument("--history-root", type=Path, default=Path.cwd())
    parser.add_argument("--inventory", type=Path, required=True)
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_bytes())
    if bool(args.approved_head) == bool(args.rebaseline_from):
        parser.error("supply exactly one of --approved-head and --rebaseline-from")
    if args.rebaseline_from:
        result = rebaseline_freeze_inventory(Path.cwd(), inventory, args.rebaseline_from, args.history_root)
    else:
        result = sync_producer_release(Path.cwd(), args.approved_head, inventory)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
