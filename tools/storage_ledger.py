"""Read-only storage ledger. No locks, no deletes, no Production writes.

Hashing is bounded by a byte budget and resumes from the state file. A Daily
guard refuses the walk when a Daily is running, or when the local clock is in
the 15:00–20:00 window and today's Daily result is not already PASS.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import statistics
import subprocess
import sys
import time
from datetime import datetime

SCHEMA = "stocklookup_storage_ledger/v1"
AUTHORITY_EFFECT = "NONE_OPERATIONAL_OBSERVABILITY_ONLY"
FLOOR_BYTES = 160 * 1024 ** 3
_COMPACT_DAY = r"20\d{2}(?:0[1-9]|1[0-2])(?:0[1-9]|[12]\d|3[01])"
_DASHED_DAY = r"20\d{2}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])"
# A date counts only when it is not a slice of a longer hex or digit run.
# Hash fragments such as 20000198 are not sessions.
DATE_RE = re.compile(rf"(?<![0-9A-Fa-f])(?P<compact>{_COMPACT_DAY})(?![0-9A-Fa-f])")
DASHED_RE = re.compile(rf"(?<![0-9A-Fa-f])(?P<dashed>{_DASHED_DAY})(?![0-9A-Fa-f])")
CHUNK = 1024 * 1024


def calendar_day(token: str | None) -> str | None:
    """Return YYYYMMDD when token is a real calendar day, otherwise None."""
    if not isinstance(token, str):
        return None
    compact = token.replace("-", "")
    if len(compact) != 8 or not compact.isdigit():
        return None
    try:
        datetime.strptime(compact, "%Y%m%d")
    except ValueError:
        return None
    return compact


def dates_in(part: str) -> list[str]:
    """Calendar dates in one path component, dashed and compact, in order."""
    found: list[str] = []
    occupied: list[tuple[int, int]] = []
    for match in DASHED_RE.finditer(part):
        day = calendar_day(match.group("dashed"))
        if day is None:
            continue
        found.append(day)
        occupied.append(match.span())
    for match in DATE_RE.finditer(part):
        if any(start <= match.start() < end for start, end in occupied):
            continue
        day = calendar_day(match.group("compact"))
        if day is not None:
            found.append(day)
    return found


def _under(path: Path, root: Path | None) -> bool:
    if root is None:
        return False
    try:
        path.resolve().relative_to(root.resolve())
    except (OSError, ValueError):
        return False
    return True


def assign_group(path: Path, roots: dict[str, Path]) -> str:
    parts = [part.lower() for part in path.parts]
    blob = "\\".join(parts)
    if any(part == "iid" or part.startswith("iid-") or "iid-runtime" in part for part in parts):
        return "iid"
    if any(token in blob for token in ("prospective-decision", "prospective_decision", "outcome-feedback", "tplus")):
        return "tplus_sidecars" if "sidecar" in blob else "tplus_store"
    for name in ("recovery_checkpoints", "worktree_archives", "scratch", "retained_evidence"):
        if _under(path, roots.get(name)):
            return name
    return "other"


def family_and_session(path: Path, retained: Path | None) -> tuple[str | None, str | None]:
    rel = None
    if retained is not None:
        try:
            rel = path.resolve().relative_to(retained.resolve())
        except (OSError, ValueError):
            rel = None
    parts = rel.parts if rel is not None and rel.parts else path.parts
    session = None
    for part in parts:
        found = dates_in(part)
        if found:
            session = found[-1]
    family = None
    if rel is not None and rel.parts:
        top = rel.parts[0]
        if dates_in(top):
            family = DASHED_RE.sub("", top)
            family = DATE_RE.sub("", family)
            family = family.replace("-session", "").strip("-")
        else:
            family = top
    return family or None, session


def runway(session_bytes: list[int], session_ids: list[str], free_bytes: int, *, floor: int = FLOOR_BYTES,
          as_of: str | None = None) -> dict:
    """Median of the last five real session days. Dates after as_of are horizon labels, not sessions."""
    cutoff = calendar_day(as_of) if as_of else None
    paired = [(day, size) for day, size in zip(session_ids, session_bytes) if calendar_day(day) and (cutoff is None or day <= cutoff)]
    session_ids = [day for day, _size in paired]
    session_bytes = [size for _day, size in paired]
    recent = [size for size in session_bytes[-5:] if size > 0]
    per = int(statistics.median(recent)) if recent else None
    headroom = free_bytes - floor
    sessions = (headroom / per) if per else None
    span_days = None
    ordered = sorted(day for day in (calendar_day(item) for item in session_ids) if day)
    if len(ordered) >= 2:
        start = datetime.strptime(ordered[0], "%Y%m%d")
        end = datetime.strptime(ordered[-1], "%Y%m%d")
        span_days = max((end - start).days, 1)
    per_day = (len(session_ids) / span_days) if span_days and per else (1.0 if per else None)
    def horizon(days: int) -> int | None:
        if per is None or per_day is None:
            return None
        return int(per * per_day * days)
    level = None
    if sessions is not None:
        level = "CRITICAL" if sessions < 5 else "WARNING" if sessions < 10 else None
    return {
        "floor_bytes": floor,
        "bytes_per_session": per,
        "sessions": sessions,
        "sessions_per_day": per_day,
        "bytes_30d": horizon(30),
        "bytes_90d": horizon(90),
        "headroom_bytes": headroom,
        "warning": level,
        "as_of": cutoff,
        "sample_sessions": session_ids[-5:],
    }


def artifact_class(row: dict) -> str | None:
    """Classify the three forward-dedupe candidates. The first match wins."""
    if row.get("group") == "iid":
        return "iid"
    blob = f"{row.get('path') or ''} {row.get('family') or ''}".lower()
    if "iid-runtime" in blob or "\\iid\\" in blob or "/iid/" in blob:
        return "iid"
    if "full-universe" in blob or "full_universe" in blob:
        return "full_universe"
    if "valuation" in blob:
        return "valuation"
    return None


def artifact_physical(records: list[dict], physical_seen: dict[tuple, int]) -> dict:
    """Physical bytes of IID, full-universe, and valuation, once per file id and session."""
    owner: dict[tuple, tuple[str, str | None]] = {}
    for row in records:
        name = artifact_class(row)
        if name is None:
            continue
        identity = (row["dev"], row["ino"])
        owner.setdefault(identity, (name, calendar_day(row.get("session"))))
    totals = {
        name: {"physical_bytes": 0, "logical_bytes": 0, "by_session": {}}
        for name in ("iid", "full_universe", "valuation")
    }
    for row in records:
        name = artifact_class(row)
        if name is None:
            continue
        totals[name]["logical_bytes"] += int(row["size"])
    for identity, (name, session) in owner.items():
        size = physical_seen.get(identity, 0)
        totals[name]["physical_bytes"] += size
        if session is not None:
            bucket = totals[name]["by_session"]
            row = bucket.setdefault(session, {"physical_bytes": 0, "logical_bytes": 0})
            row["physical_bytes"] += size
    for row in records:
        name = artifact_class(row)
        session = calendar_day(row.get("session"))
        if name is None or session is None:
            continue
        bucket = totals[name]["by_session"].setdefault(session, {"physical_bytes": 0, "logical_bytes": 0})
        bucket["logical_bytes"] += int(row["size"])
    published = {}
    for name, payload in totals.items():
        by_session = [
            {"session": session, "physical_bytes": sizes["physical_bytes"], "logical_bytes": sizes["logical_bytes"]}
            for session, sizes in sorted(payload["by_session"].items())
        ]
        recent = [row["physical_bytes"] for row in by_session[-5:] if row["physical_bytes"] > 0]
        published[name] = {
            "physical_bytes": payload["physical_bytes"],
            "logical_bytes": payload["logical_bytes"],
            "bytes_per_session_median": int(statistics.median(recent)) if recent else None,
            "by_session": by_session,
        }
    return published


def build_report(records: list[dict], *, volume_total: int, volume_used: int, volume_free: int,
                 hash_budget: int, hashed_bytes: int, as_of: str | None = None) -> dict:
    physical_seen: dict[tuple, int] = {}
    groups: dict[str, dict] = {}
    families: dict[str, dict] = {}
    logical = 0
    for row in records:
        logical += int(row["size"])
        identity = (row["dev"], row["ino"])
        physical_seen.setdefault(identity, int(row["size"]))
        bucket = groups.setdefault(row["group"], {"files": 0, "logical_bytes": 0, "identities": set()})
        bucket["files"] += 1
        bucket["logical_bytes"] += int(row["size"])
        bucket["identities"].add(identity)
        if row.get("family"):
            fam = families.setdefault(row["family"], {"files": 0, "logical_bytes": 0, "identities": set()})
            fam["files"] += 1
            fam["logical_bytes"] += int(row["size"])
            fam["identities"].add(identity)
    session_owner: dict[tuple, str] = {}
    session_bytes: dict[str, int] = {}
    for row in records:
        session = calendar_day(row.get("session"))
        if session is None:
            continue
        identity = (row["dev"], row["ino"])
        session_owner.setdefault(identity, session)
    for identity, size in physical_seen.items():
        session = session_owner.get(identity)
        if session:
            session_bytes[session] = session_bytes.get(session, 0) + size
    by_sha: dict[str, list] = {}
    for row in records:
        digest = row.get("sha256")
        if not digest:
            continue
        by_sha.setdefault(digest, []).append(row)
    excess = 0
    duplicate_groups = 0
    for rows in by_sha.values():
        identities = {(row["dev"], row["ino"]) for row in rows}
        if len(identities) < 2:
            continue
        duplicate_groups += 1
        size = int(rows[0]["size"])
        excess += size * (len(identities) - 1)
    hardlink_files = sum(1 for row in records if int(row.get("nlink") or 1) > 1)
    scanned = sum(physical_seen.values())
    ratio = (scanned / volume_used) if volume_used else None
    agreement = ratio is not None and abs(ratio - 1) <= 0.02
    ordered_sessions = sorted(session_bytes)
    growth = []
    previous = None
    for session in ordered_sessions:
        current = session_bytes[session]
        growth.append({
            "session": session,
            "physical_bytes": current,
            "growth_bytes": None if previous is None else current - previous,
        })
        previous = current
    def public_group(bucket: dict) -> dict:
        return {
            "files": bucket["files"],
            "logical_bytes": bucket["logical_bytes"],
            "physical_bytes": sum(physical_seen[identity] for identity in bucket["identities"]),
        }
    return {
        "schema": SCHEMA,
        "authority_effect": AUTHORITY_EFFECT,
        "volume": {"total_bytes": volume_total, "used_bytes": volume_used, "free_bytes": volume_free},
        "scanned_logical_bytes": logical,
        "scanned_physical_bytes": scanned,
        "volume_used_agreement_ratio": ratio,
        "volume_agreement_within_2_percent": agreement,
        "groups": {name: public_group(bucket) for name, bucket in sorted(groups.items())},
        "retained_families": {name: public_group(bucket) for name, bucket in sorted(families.items())},
        "per_session": growth,
        "physical_duplicates": {
            "hardlink_file_rows": hardlink_files,
            "content_duplicate_groups": duplicate_groups,
            "content_duplicate_excess_bytes": excess,
        },
        "runway": runway(
            [row["physical_bytes"] for row in growth], ordered_sessions, volume_free,
            as_of=as_of or datetime.now().strftime("%Y%m%d")),
        "artifact_physical": artifact_physical(records, physical_seen),
        "hash": {"budget_bytes": hash_budget, "hashed_bytes": hashed_bytes, "resumable": True, "locks": False},
    }


def _record(path: Path, group: str, family: str | None, session: str | None) -> dict | None:
    try:
        st = path.stat()
    except OSError:
        return None
    if not path.is_file():
        return None
    return {
        "path": str(path),
        "size": int(st.st_size),
        "dev": int(st.st_dev),
        "ino": int(st.st_ino),
        "nlink": int(getattr(st, "st_nlink", 1) or 1),
        "mtime_ns": int(getattr(st, "st_mtime_ns", 0) or 0),
        "group": group,
        "family": family,
        "session": session,
        "sha256": None,
    }


def scan(root: Path, roots: dict[str, Path], state_path: Path, *, guard, max_files: int | None = None) -> dict:
    """Resumable metadata scan. Completed directories are skipped on the next call."""
    state = {"version": 1, "done_dirs": [], "files": str(state_path.with_suffix(".files.jsonl"))}
    if state_path.is_file():
        state.update(json.loads(state_path.read_text(encoding="utf-8")))
    done = set(state.get("done_dirs") or [])
    files_path = Path(state["files"])
    files_path.parent.mkdir(parents=True, exist_ok=True)
    added = 0
    stopped = None
    with files_path.open("a", encoding="utf-8") as handle:
        stack = [root]
        entered: set[str] = set()
        while stack:
            current = stack.pop()
            key = str(current)
            if key in done:
                continue
            if key in entered:
                done.add(key)
                continue
            reason = guard()
            if reason:
                stopped = reason
                break
            entered.add(key)
            stack.append(current)
            try:
                children = list(os.scandir(current))
            except OSError:
                continue
            dirs = []
            for child in children:
                try:
                    if child.is_dir(follow_symlinks=False):
                        dirs.append(child.path)
                        continue
                    if not child.is_file(follow_symlinks=False):
                        continue
                except OSError:
                    continue
                path = Path(child.path)
                family, session = family_and_session(path, roots.get("retained_evidence"))
                row = _record(path, assign_group(path, roots), family, session)
                if row is None:
                    continue
                handle.write(json.dumps(row, ensure_ascii=False) + "\n")
                added += 1
                if max_files is not None and added >= max_files:
                    stopped = "MAX_FILES"
                    break
            if stopped:
                break
            for directory in reversed(dirs):
                if directory not in done:
                    stack.append(Path(directory))
    state["done_dirs"] = sorted(done)
    state["stopped"] = stopped
    state_path.write_text(json.dumps(state), encoding="utf-8")
    return state


def load_records(files_path: Path) -> list[dict]:
    if not files_path.is_file():
        return []
    latest: dict[str, dict] = {}
    for line in files_path.read_text(encoding="utf-8").splitlines():
        if line:
            row = json.loads(line)
            latest[row["path"]] = row
    return list(latest.values())


def hash_pending(records: list[dict], *, budget: int, guard, prefer: tuple[str, ...] = ("iid", "full-universe", "valuation")) -> int:
    """Hash unhashed rows until the budget is spent. Caller persists the rows."""
    hashed = 0

    def rank(row: dict) -> tuple:
        blob = (row.get("path") or "").lower()
        preferred = 0 if any(token in blob for token in prefer) else 1
        return (preferred, -int(row["size"]))

    for row in sorted(records, key=rank):
        if row.get("sha256") or hashed >= budget:
            continue
        if int(row["size"]) > budget - hashed:
            continue
        reason = guard()
        if reason:
            break
        digest = hashlib.sha256()
        with open(row["path"], "rb") as handle:
            while True:
                chunk = handle.read(CHUNK)
                if not chunk:
                    break
                digest.update(chunk)
        row["sha256"] = digest.hexdigest()
        hashed += int(row["size"])
    return hashed


def daily_block_reason(*, now: datetime, run_logs: Path, command_lines: list[str], self_pid: int | None = None) -> str | None:
    for line in command_lines:
        if "run_owner_daily" in line or "owner_daily" in line:
            return "DAILY_PROCESS"
    if run_logs.is_dir():
        for dirpath, _dirs, names in os.walk(run_logs):
            for name in names:
                if "lock" in name.lower():
                    return "DAILY_LOCK"
            if dirpath != str(run_logs):
                break
    if 15 <= now.hour < 20:
        stamp = now.strftime("%Y%m%d")
        proved = False
        if run_logs.is_dir():
            for path in run_logs.glob(f"stock_lookup_daily_{stamp}*.result.json"):
                try:
                    payload = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, ValueError):
                    continue
                if payload.get("status") == "PASS":
                    proved = True
                    break
        if not proved:
            return "DAILY_WINDOW_UNPROVEN"
    return None


def live_command_lines() -> list[str]:
    completed = subprocess.run(
        ["powershell", "-NoProfile", "-Command",
         "Get-CimInstance Win32_Process | ForEach-Object { $_.ProcessId.ToString() + ' ' + $_.CommandLine }"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=120,
    )
    me = str(os.getpid())
    lines = []
    for line in (completed.stdout or "").splitlines():
        if line.startswith(me + " "):
            continue
        lines.append(line)
    return lines


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--volume", type=Path, required=True)
    parser.add_argument("--state", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--retained-evidence", type=Path)
    parser.add_argument("--scratch", type=Path)
    parser.add_argument("--recovery-checkpoints", type=Path)
    parser.add_argument("--worktree-archives", type=Path)
    parser.add_argument("--run-logs", type=Path, default=Path(r"T:\StockLookup\production-v1\run-logs"))
    parser.add_argument("--hash-budget-bytes", type=int, default=2 * 1024 ** 3)
    parser.add_argument("--max-files", type=int)
    parser.add_argument("--skip-guard", action="store_true")
    args = parser.parse_args(argv)
    roots = {
        "retained_evidence": args.retained_evidence,
        "scratch": args.scratch,
        "recovery_checkpoints": args.recovery_checkpoints,
        "worktree_archives": args.worktree_archives,
    }

    cached = {"at": 0.0, "reason": None}

    def guard() -> str | None:
        if args.skip_guard:
            return None
        now = time.monotonic()
        if now - cached["at"] < 15:
            return cached["reason"]
        cached["at"] = now
        cached["reason"] = daily_block_reason(
            now=datetime.now(), run_logs=args.run_logs, command_lines=live_command_lines())
        return cached["reason"]

    reason = guard()
    if reason:
        print(json.dumps({"status": "STOPPED", "reason": reason}))
        return 2
    usage = shutil.disk_usage(args.volume)
    state = scan(args.volume, roots, args.state, guard=guard, max_files=args.max_files)
    records = load_records(Path(state["files"]))
    hashed = hash_pending(records, budget=args.hash_budget_bytes, guard=guard)
    Path(state["files"]).write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in records), encoding="utf-8")
    report = build_report(
        records, volume_total=int(usage.total), volume_used=int(usage.used), volume_free=int(usage.free),
        hash_budget=args.hash_budget_bytes, hashed_bytes=hashed,
    )
    report["scan_stopped"] = state.get("stopped")
    report["state"] = str(args.state)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(str(args.output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
