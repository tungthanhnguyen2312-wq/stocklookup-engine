"""Admit additive pre-Producer session-input freezes. Never mutates the checkout.

Owner Daily and Canonical producer qualification both refuse any tracked change. A
failed Producer can still leave ``config/daily_research_session_input_registry.json``
with a new ``COMPLETED_RETAINED_EVIDENCE`` row after input registration. That row is
an input lock, not a completed Daily. Publication resume requires a ``LOCAL_COMPLETE``
operation and must not be manufactured by relabeling this row.

Freezes accumulate: when the next Daily freezes its own session before sealing, the
uncommitted diff carries one row per unsealed session (2026-10-26 and 2026-11-02).
Each row is admitted only on its own evidence. Only ``commit_daily_state`` commits a
row, and only the row of the session it has just verified as sealed.

This classifier is the only shared admission of that narrower state. It does not
commit, stage, pull, reset, or rewrite frozen identities.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import subprocess

REGISTRY_RELATIVE = "config/daily_research_session_input_registry.json"
_PENDING_STATUS_CODES = frozenset({" M", "M ", "MM"})
_SESSION_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SEALED_OPERATION_STATES = frozenset({"LOCAL_COMPLETE", "PUBLISHED"})

# Kept aligned with canonical_post_close_pipeline.REQUIRED_REGISTRY_KEYS and
# OPTIONAL_REGISTRY_KEYS. The test, not an import of that pipeline, enforces it.
REQUIRED_INPUT_KEYS = (
    "descriptive", "screening", "tactical", "triage",
    "fundamental", "valuation", "catalyst", "corporate_intelligence",
)
OPTIONAL_INPUT_KEYS = ("official_universe", "event_context")
_ALLOWED_INPUT_KEYS = frozenset(REQUIRED_INPUT_KEYS) | frozenset(OPTIONAL_INPUT_KEYS)


@dataclass(frozen=True)
class PendingInputFreeze:
    admitted: bool
    session: str | None
    reason_code: str
    # Every admitted unsealed session, oldest first. ``session`` is the newest.
    sessions: tuple[str, ...] = ()


def _reject(reason: str) -> PendingInputFreeze:
    return PendingInputFreeze(False, None, reason)


def _git(root: Path, *args: str) -> tuple[int, str]:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        capture_output=True, text=True, encoding="utf-8", check=False,
    )
    return result.returncode, result.stdout


def _sole_registry_modification(root: Path) -> bool:
    code, out = _git(root, "status", "--porcelain", "--untracked-files=no")
    if code:
        return False
    lines = [line for line in out.splitlines() if line]
    return bool(lines) and all(
        line[:2] in _PENDING_STATUS_CODES
        and line[3:].replace("\\", "/") == REGISTRY_RELATIVE
        for line in lines
    )


def _load_json_bytes(raw: str) -> dict | None:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return None
    return value if isinstance(value, dict) else None


def _additive_sessions(before: object, after: object) -> tuple[str, ...] | None:
    if not isinstance(before, dict) or not isinstance(after, dict):
        return None
    added = set(after) - set(before)
    removed = set(before) - set(after)
    changed = [key for key in set(before) & set(after) if before[key] != after[key]]
    if removed or changed or not added:
        return None
    if not all(isinstance(session, str) and _SESSION_RE.fullmatch(session) for session in added):
        return None
    return tuple(sorted(added))


def _governed_retained_root(root: Path) -> Path | None:
    """The workspace retained-evidence role, when one is bound (split code/evidence roots)."""
    try:
        from runtime_paths import workspace_path
        configured = os.environ.get("STOCK_LOOKUP_RETAINED_EVIDENCE_ROOT", "").strip()
        retained = workspace_path("retained", configured or root)
    except Exception:  # noqa: BLE001 -- an unqualified profile admits nothing extra
        return None
    return None if Path(retained).resolve() == root.resolve() else Path(retained)


def _within(path: Path, base: Path) -> bool:
    prefix = os.path.normcase(str(base.resolve()) + os.sep)
    return os.path.normcase(str(path)).startswith(prefix)


def _artifact_matches(root: Path, entry: object, identity: object) -> bool:
    if not isinstance(entry, dict) or set(entry) != {"path", "artifact_identity"}:
        return False
    if not isinstance(identity, str) or not identity or entry.get("artifact_identity") != identity:
        return False
    recorded = entry.get("path")
    if not isinstance(recorded, str) or not recorded:
        return False
    if os.path.isabs(recorded):
        # canonical_post_close_pipeline records retained artifacts outside the checkout as
        # absolute paths once code and evidence roots are split (2026-10-19 T: cutover). Admit
        # them only inside the governed retained-evidence root, never anywhere else.
        retained = _governed_retained_root(root)
        path = Path(recorded).resolve()
        if retained is None or ".." in Path(recorded).parts or not _within(path, retained):
            return False
    else:
        parts = Path(recorded).parts
        if ".." in parts or any(part.endswith(":") for part in parts):
            return False
        path = (root / recorded).resolve()
        if not _within(path, root):
            return False
    if not path.is_file():
        return False
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return isinstance(payload, dict) and payload.get("artifact_identity") == identity


def _sealed_operation(root: Path, session: str) -> str | None:
    """Return a refusal reason when this session already has a sealed Daily operation.

    A missing tree is not a seal. An unreadable record under the session directory
    fails closed. Records for other sessions are ignored.
    """
    base = root / "operations-review" / "canonical-daily-operation-v1"
    if not base.is_dir():
        return None
    for path in base.glob("*/*/daily_operation_record.json"):
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            if session in path.parts:
                return "OPERATION_RECORD_UNREADABLE"
            continue
        if not isinstance(record, dict) or record.get("session") != session:
            continue
        if record.get("daily_operation_state") in _SEALED_OPERATION_STATES:
            return "SEALED_OPERATION_PRESENT"
    return None


def _row_rejection(root: Path, work: dict, session: str) -> str | None:
    row = (work.get("completed_sessions") or {}).get(session)
    selection = (work.get("sessions") or {}).get(session)
    if (not isinstance(row, dict) or not isinstance(selection, dict)
            or row.get("status") != "COMPLETED_RETAINED_EVIDENCE"
            or row.get("trading_day_valid") is not True):
        return "FREEZE_ROW_INVALID"
    lock = row.get("frozen_input_identities")
    if not isinstance(lock, dict) or set(selection) != set(lock):
        return "FREEZE_ROW_INVALID"
    if not set(REQUIRED_INPUT_KEYS) <= set(selection) or not set(selection) <= _ALLOWED_INPUT_KEYS:
        return "FREEZE_ROW_INVALID"
    if any(not _artifact_matches(root, selection[key], lock.get(key)) for key in selection):
        return "ARTIFACT_IDENTITY_MISMATCH"
    return _sealed_operation(root, session)


def _head_and_work(root: Path) -> tuple[str, dict, dict] | str:
    code, head_raw = _git(root, "show", f"HEAD:{REGISTRY_RELATIVE}")
    if code:
        return "REGISTRY_UNREADABLE"
    try:
        work_raw = (root / REGISTRY_RELATIVE).read_text(encoding="utf-8")
    except OSError:
        return "REGISTRY_UNREADABLE"
    head = _load_json_bytes(head_raw)
    work = _load_json_bytes(work_raw)
    if head is None or work is None:
        return "NOT_ADDITIVE"
    return head_raw, head, work


def _pending_sessions(head: dict, work: dict) -> tuple[str, ...] | None:
    if set(head) != set(work):
        return None
    for key in head:
        if key not in ("sessions", "completed_sessions") and head[key] != work[key]:
            return None
    sessions = _additive_sessions(head.get("sessions"), work.get("sessions"))
    completed = _additive_sessions(head.get("completed_sessions"), work.get("completed_sessions"))
    return sessions if sessions is not None and sessions == completed else None


def classify_pending_input_freeze(root: Path) -> PendingInputFreeze:
    """Return whether ``root`` contains only faithful pre-Producer input freezes.

    Admitted only when the sole tracked change is an in-place registry modification,
    JSON versus ``HEAD`` adds one or more sessions to both ledgers and changes nothing
    else, every new row is ``COMPLETED_RETAINED_EVIDENCE`` with ``trading_day_valid``
    true, every frozen identity matches the selection and the on-disk artifact, and
    no new session has a ``LOCAL_COMPLETE`` or ``PUBLISHED`` operation record. One bad
    row rejects the whole diff; nothing is admitted partially.
    """
    root = Path(root)
    if not _sole_registry_modification(root):
        return _reject("NOT_SOLE_REGISTRY_DIFF")
    loaded = _head_and_work(root)
    if isinstance(loaded, str):
        return _reject(loaded)
    _head_raw, head, work = loaded
    sessions = _pending_sessions(head, work)
    if sessions is None:
        return _reject("NOT_ADDITIVE")
    for session in sessions:
        reason = _row_rejection(root, work, session)
        if reason:
            return _reject(reason)
    return PendingInputFreeze(True, sessions[-1], "PENDING_INPUT_FREEZE", sessions)


def pending_registry_sessions(root: Path) -> tuple[str, ...] | None:
    """Sessions the working registry adds to ``HEAD``, or ``None`` when the diff is not additive.

    This reads the ledger shape only; it does not admit anything as a freeze.
    """
    loaded = _head_and_work(Path(root))
    return None if isinstance(loaded, str) else _pending_sessions(loaded[1], loaded[2])


def registry_text_committing_session(root: Path, session: str) -> str | None:
    """Return the HEAD registry plus only ``session``'s rows, in the writer's format.

    ``commit_daily_state`` commits this text once ``session`` is verified as sealed.
    Other pending freezes stay in the working tree as uncommitted input locks, so the
    committed ledger never records an unsealed session. ``None`` means the working
    registry is not a set of additive rows that includes ``session``.
    """
    loaded = _head_and_work(Path(root))
    if isinstance(loaded, str):
        return None
    head_raw, head, work = loaded
    sessions = _pending_sessions(head, work)
    if sessions is None or session not in sessions:
        return None
    # The registry writer emits indent=2 JSON; never reformat a HEAD file that differs.
    if head_raw.replace("\r\n", "\n") != json.dumps(head, ensure_ascii=False, indent=2) + "\n":
        return None
    for ledger in ("sessions", "completed_sessions"):
        head[ledger][session] = work[ledger][session]
    return json.dumps(head, ensure_ascii=False, indent=2) + "\n"

def freeze_byte_inventory(root: Path) -> tuple[dict, list[str]]:
    """Bind the existing freeze's selected artifacts and dirty registry to exact bytes."""
    from hashlib import sha256

    if _git(root, "diff", "--cached", "--quiet")[0]:
        raise ValueError("FREEZE_SYNC_INDEX_NOT_CLEAN")
    freeze = classify_pending_input_freeze(root)
    if not freeze.admitted:
        raise ValueError("FREEZE_SYNC_INVALID_FREEZE:" + freeze.reason_code)
    registry_path = root / REGISTRY_RELATIVE
    if registry_path.resolve() != registry_path:
        raise ValueError("FREEZE_SYNC_REDIRECTED_REGISTRY")
    registry = registry_path.read_bytes()
    body = json.loads(registry)
    protected = {REGISTRY_RELATIVE}
    sources = {}
    retained = _governed_retained_root(root)
    for session in freeze.sessions:
        if retained is not None and (reason := _sealed_operation(retained, session)):
            raise ValueError("FREEZE_SYNC_INVALID_FREEZE:" + reason)
        for key, entry in body["sessions"][session].items():
            path = Path(entry["path"])
            if not path.is_absolute():
                path = root / path
            resolved = path.resolve()
            if resolved != path:
                raise ValueError("FREEZE_SYNC_REDIRECTED_SOURCE")
            if path.is_relative_to(root):
                protected.add(path.relative_to(root).as_posix())
            raw = path.read_bytes()
            artifact = json.loads(raw)
            identity = entry["artifact_identity"]
            payload = {k: v for k, v in artifact.items() if k not in ("artifact_sha256", "artifact_identity")}
            canonical = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
            digest = sha256(canonical.encode("utf-8")).hexdigest()
            if (artifact.get("artifact_identity") != identity
                    or artifact.get("artifact_sha256") != digest or not identity.endswith(":" + digest)):
                raise ValueError(f"FREEZE_SYNC_SOURCE_CONTENT_MISMATCH:{session}/{key}")
            sources[f"{session}/{key}"] = sha256(raw).hexdigest()
    return {"registry_sha256": sha256(registry).hexdigest(), "sources": sources}, sorted(protected)


def _sync_frozen_checkout(root: Path, approved_head: str, inventory: dict, *, check_writers) -> dict:
    """Caller owns the canonical writer leases and has bound the Production profile."""
    from stocklookup_core.acquisition.checkout_cleanliness_contract import classify_checkout_cleanliness

    def git(*args):
        code, value = _git(root, *args)
        if code:
            raise ValueError("FREEZE_SYNC_GIT_REFUSED:" + args[0])
        return value.strip()

    if not re.fullmatch(r"[0-9a-f]{40}", approved_head):
        raise ValueError("FREEZE_SYNC_EXACT_RELEASE_REQUIRED")
    if git("symbolic-ref", "--short", "HEAD") != "main":
        raise ValueError("FREEZE_SYNC_WRONG_BRANCH")
    if classify_checkout_cleanliness(root).unsafe_untracked_paths:
        raise ValueError("FREEZE_SYNC_UNSAFE_UNTRACKED")
    head = git("rev-parse", "HEAD")
    before, protected = freeze_byte_inventory(root)
    if before != inventory:
        raise ValueError("FREEZE_SYNC_BYTE_PIN_MISMATCH")

    git("fetch", "origin", "refs/heads/main:refs/remotes/origin/main")
    if git("rev-parse", "refs/remotes/origin/main") != approved_head:
        raise ValueError("FREEZE_SYNC_RELEASE_HEAD_MISMATCH")
    if _git(root, "merge-base", "--is-ancestor", head, approved_head)[0]:
        raise ValueError("FREEZE_SYNC_DIVERGED")
    if _git(root, "diff", "--quiet", "--no-ext-diff", head, approved_head, "--", *protected)[0]:
        raise ValueError("FREEZE_SYNC_TARGET_TOUCHES_PROTECTED_PATH")

    check_writers()
    if git("ls-remote", "--exit-code", "origin", "refs/heads/main").split() != [approved_head, "refs/heads/main"]:
        raise ValueError("FREEZE_SYNC_REMOTE_ADVANCED")
    if (git("rev-parse", "HEAD") != head or git("symbolic-ref", "--short", "HEAD") != "main"
            or classify_checkout_cleanliness(root).unsafe_untracked_paths
            or freeze_byte_inventory(root) != (before, protected)):
        raise ValueError("FREEZE_SYNC_CHECKOUT_CHANGED")
    if head != approved_head:
        git("merge", "--ff-only", "--no-autostash", "--no-overwrite-ignore", approved_head)
    if git("rev-parse", "HEAD") != approved_head or freeze_byte_inventory(root) != (before, protected):
        raise ValueError("FREEZE_SYNC_POSTCONDITION_FAILED")
    return {
        "status": "FREEZE_PRESERVED_AT_APPROVED_HEAD" if head == approved_head else "FAST_FORWARDED_FREEZE_PRESERVED",
        "previous_head": head, "head": approved_head, **before,
    }
