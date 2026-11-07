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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--approved-head", required=True)
    parser.add_argument("--inventory", type=Path, required=True)
    args = parser.parse_args()
    inventory = json.loads(args.inventory.read_bytes())
    print(json.dumps(sync_producer_release(Path.cwd(), args.approved_head, inventory), sort_keys=True))


if __name__ == "__main__":
    main()
