"""Post-Daily current-session candlestick release: opt-in, foreground, idempotent.

Runs only AFTER a completed Owner Daily, never inside it, and never as a scheduler, daemon or
watcher. One invocation does, in order, and stops at the first gate that does not hold:

1. preflight   -- no Daily / release-orchestrator writer, no second instance, free RAM and disk
                  above explicit bounds. Not enough resources -> ``SKIP`` (exit 3) with a reason;
                  nothing is staged or published, so there is never a half-published state.
2. source      -- the explicit ``--session`` is a COMPLETED row of the *committed* session
                  registry; the explicit ``--source-identity`` is the P3F9B snapshot bound by that
                  session's retained canonical Daily operation record; the retained snapshot's own
                  content identity is recomputed and must equal it; its file bytes must not change
                  while the scan runs. Any mismatch -> ``REFUSED`` (exit 2).
3. build       -- ``current_session_candlestick_projection`` over that snapshot only (no provider
                  call, no database). Output goes to a checkpoint keyed by session + source digest;
                  a verified checkpoint is reused (``REUSED``), a torn one is rebuilt. Sealed Daily
                  files are only read.
4. verify      -- schema, recomputed projection identity, session identity, source identity,
                  per-ticker completeness/source session, JSON/JS pair parity and content hashes.
5. stage       -- only with ``--stage`` or ``--publish``: copy the verified pair into
                  ``<runtime-root>/data/`` with a transaction backup of the previous pair.
6. publish     -- only with ``--publish``: refuse unless the runtime release and the Dashboard
                  checkout are both on ``--session``; then call the EXISTING governed Dashboard
                  release (``tools.run_owner_daily.publish_dashboard_release``, the same adapter
                  Daily uses). On any failure the runtime pair is rolled back; the orchestrator
                  restores its own web-checkout transaction. A sidecar that is absent or not
                  CURRENT only removes/annotates ``domains.signals`` -- the normal Dashboard and
                  AI handoff are never altered by this tool.

``--rollback`` restores the runtime pair recorded by the latest transaction for the session and,
with ``--publish``, republishes through the same governed path.
"""
from __future__ import annotations

import argparse
import contextlib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CONTRACT_VERSION = "post_daily_candlestick_release/v1"
EXIT_OK, EXIT_FAILED, EXIT_REFUSED, EXIT_SKIP = 0, 1, 2, 3
REGISTRY = "config/daily_research_session_input_registry.json"
COMPLETED = "COMPLETED_RETAINED_EVIDENCE"
SIDECAR_JSON = "candlestick_patterns.json"
SIDECAR_JS = "candlestick_patterns.js"
COMPONENT = "candlestick_patterns.component.json"
JS_PREFIX = "window.CANDLESTICK_PATTERNS = "
WRITER_MARKERS = ("run_owner_daily.py", "owner_daily_host.py", "stock_lookup_daily", "release_orchestrator.py")
GIB = 1024 ** 3
PUBLISHED_STATES = ("PUBLISHED", "READY", "PASS", "NO_CHANGE", "LOCAL_PUBLISHED")


class Refused(Exception):
    """A source/identity/session gate failed: never build or publish."""


class Skip(Exception):
    """Resources or concurrency do not allow a safe run now; retry later."""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(8 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
    os.replace(tmp, path)


# ---------------------------------------------------------------- host observation (injectable)
def observe_command_lines() -> list[tuple[int, str]] | None:
    try:
        import psutil  # optional; Windows CIM fallback below
        rows = []
        for proc in psutil.process_iter(["pid", "cmdline"]):
            cmd = proc.info.get("cmdline") or []
            rows.append((proc.info["pid"], " ".join(cmd)))
        return rows
    except ImportError:
        pass
    except Exception:  # noqa: BLE001 - observation failure is reported as unknown, never as clear
        return None
    if os.name != "nt":
        return None
    try:
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command",
             "Get-CimInstance Win32_Process | Select-Object ProcessId,CommandLine | ConvertTo-Json -Compress"],
            capture_output=True, text=True, check=True, timeout=60).stdout
        rows = json.loads(out or "[]")
        rows = [rows] if isinstance(rows, dict) else rows
        return [(int(r.get("ProcessId") or 0), r.get("CommandLine") or "") for r in rows]
    except (OSError, subprocess.SubprocessError, ValueError):
        return None


def observe_available_ram() -> int | None:
    try:
        import psutil
        return int(psutil.virtual_memory().available)
    except ImportError:
        pass
    if os.name == "nt":
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        status = MEMORYSTATUSEX()
        status.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return int(status.ullAvailPhys)
    return None


def peak_rss_bytes() -> int | None:
    try:
        import psutil
        info = psutil.Process().memory_info()
        return int(getattr(info, "peak_wset", 0) or getattr(info, "rss", 0)) or None
    except ImportError:
        pass
    try:
        import resource
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss) * 1024
    except (ImportError, OSError):
        return None


def active_writers(rows: Iterable[tuple[int, str]], own_pid: int) -> list[str]:
    found = []
    for pid, cmd in rows:
        if pid == own_pid or "post_daily_candlestick_release" in cmd:
            continue
        if any(marker in cmd for marker in WRITER_MARKERS) and "python" in cmd.lower():
            found.append(f"{pid}:{next(m for m in WRITER_MARKERS if m in cmd)}")
    return found


def preflight(*, checkpoint_root: Path, runtime_root: Path | None, min_free_ram: int, min_free_disk: int,
              observe_rows: Callable[[], list[tuple[int, str]] | None] = observe_command_lines,
              observe_ram: Callable[[], int | None] = observe_available_ram) -> dict[str, Any]:
    rows = observe_rows()
    if rows is None:
        raise Skip("WRITER_STATE_UNOBSERVABLE")
    writers = active_writers(rows, os.getpid())
    if writers:
        raise Skip("CONCURRENT_DAILY_OR_RELEASE_WRITER:" + ",".join(writers))
    ram = observe_ram()
    if ram is None:
        raise Skip("FREE_RAM_UNOBSERVABLE")
    if ram < min_free_ram:
        raise Skip(f"FREE_RAM_BELOW_BOUND:{ram}<{min_free_ram}")
    checkpoint_root.mkdir(parents=True, exist_ok=True)
    disks = {"checkpoint": shutil.disk_usage(checkpoint_root).free}
    if runtime_root is not None and runtime_root.is_dir():
        disks["runtime"] = shutil.disk_usage(runtime_root).free
    low = {k: v for k, v in disks.items() if v < min_free_disk}
    if low:
        raise Skip("FREE_DISK_BELOW_BOUND:" + ",".join(f"{k}={v}" for k, v in low.items()))
    return {"free_ram_bytes": ram, "free_disk_bytes": disks, "writers": []}


@contextlib.contextmanager
def instance_lock(checkpoint_root: Path):
    lock = checkpoint_root / ".post_daily_candlestick_release.lock"
    checkpoint_root.mkdir(parents=True, exist_ok=True)
    try:
        fd = os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise Skip(f"INSTANCE_LOCK_HELD:{lock}") from None
    try:
        os.write(fd, str(os.getpid()).encode())
        os.close(fd)
        yield
    finally:
        with contextlib.suppress(OSError):
            lock.unlink()


# ---------------------------------------------------------------- source gates
def committed_session(producer_root: Path, session: str, *, git: Callable[..., bytes] | None = None) -> dict[str, Any]:
    git = git or (lambda *a: subprocess.check_output(["git", "-C", str(producer_root), *a]))
    try:
        head = git("rev-parse", "HEAD").decode().strip()
        registry = json.loads(git("show", f"{head}:{REGISTRY}"))
    except (subprocess.CalledProcessError, OSError, ValueError) as exc:
        raise Refused(f"COMMITTED_REGISTRY_UNREADABLE:{exc}") from exc
    row = (registry.get("completed_sessions") or {}).get(session)
    if not isinstance(row, Mapping) or row.get("status") != COMPLETED:
        raise Refused("SESSION_NOT_COMMITTED_COMPLETED")
    return {"producer_head": head, "registry_status": row["status"]}


def operation_binding(retained_root: Path, session: str, source_identity: str) -> dict[str, Any]:
    base = retained_root / "operations-review" / "canonical-daily-operation-v1" / session
    bound = []
    for record_path in sorted(base.glob("op-*/daily_operation_record.json")):
        record = json.loads(record_path.read_text(encoding="utf-8"))
        if record.get("session") != session:
            continue
        if (record.get("acquisition") or {}).get("snapshot_identity") == source_identity:
            bound.append((record_path, record))
    if not bound:
        raise Refused("SOURCE_IDENTITY_NOT_BOUND_BY_SESSION_OPERATION_RECORD")
    if len(bound) > 1:
        raise Refused("AMBIGUOUS_SESSION_OPERATION_RECORDS")
    path, record = bound[0]
    if record.get("daily_producer_status") != "COMPLETED":
        raise Refused("SESSION_OPERATION_NOT_COMPLETED")
    return {"operation_record": str(path), "operation_record_sha256": _sha256_file(path),
            "operation_identity": record.get("operation_identity")}


def default_snapshot_path(retained_root: Path, session: str) -> Path:
    return (retained_root / "operations-review" /
            f"p3f9b-market-wide-exact-session-scaleout-{session.replace('-', '')}" /
            "p3f9b_mva_exact_session_snapshot.json")


def load_verified_snapshot(path: Path, session: str, source_identity: str) -> tuple[dict[str, Any], str]:
    from stocklookup_core.evidence.field_identity import stable_id
    from stocklookup_core.tactical import current_session_candlestick_projection as projection
    if not path.is_file():
        raise Refused("SOURCE_SNAPSHOT_MISSING")
    file_sha = _sha256_file(path)
    snapshot = json.loads(path.read_text(encoding="utf-8"))
    try:
        projection.verify_source(snapshot, session)
    except projection.CandlestickProjectionError as exc:
        raise Refused(str(exc)) from exc
    body = {k: v for k, v in snapshot.items() if k not in ("snapshot_sha256", "snapshot_identity")}
    digest = stable_id(body)
    if digest != snapshot.get("snapshot_sha256") or snapshot.get("snapshot_identity") != f"p3f9_exact_session_snapshot:{digest}":
        raise Refused("SOURCE_SNAPSHOT_CONTENT_IDENTITY_MISMATCH")
    if snapshot["snapshot_identity"] != source_identity:
        raise Refused("SOURCE_IDENTITY_MISMATCH")
    return snapshot, file_sha


def code_digest() -> str:
    """Identity of the code that produces the sidecar: a checkpoint built by other projection or
    detector code is never reused (LF-normalized like the capacity source pins)."""
    digest = hashlib.sha256()
    for rel in ("stocklookup_core/tactical/current_session_candlestick_projection.py",
                "stocklookup_core/tactical/candlestick_patterns.py"):
        digest.update(rel.encode() + b"\0" + (ROOT / rel).read_bytes().replace(b"\r\n", b"\n"))
    return digest.hexdigest()


def checkpoint_dir(checkpoint_root: Path, session: str, source_identity: str) -> Path:
    return checkpoint_root / session / f"{source_identity.rsplit(':', 1)[-1][:16]}-{code_digest()[:12]}"


# ---------------------------------------------------------------- verification
def verify_sidecar(directory: Path, session: str, source_identity: str,
                   expected_candidates: int | None = None) -> dict[str, Any]:
    from stocklookup_core.tactical import current_session_candlestick_projection as projection
    json_path, js_path = directory / SIDECAR_JSON, directory / SIDECAR_JS
    if not (json_path.is_file() and js_path.is_file()):
        raise Refused("SIDECAR_PAIR_MISSING")
    text = json_path.read_text(encoding="utf-8")
    js = js_path.read_text(encoding="utf-8")
    if js != JS_PREFIX + text + ";\n":
        raise Refused("SIDECAR_JS_JSON_PARITY_MISMATCH")
    payload = json.loads(text)
    component = projection.component_state(payload, session)
    if component["status"] != "CURRENT":
        raise Refused("SIDECAR_NOT_CURRENT:" + ",".join(component.get("reason_codes") or [component["status"]]))
    if (payload.get("source") or {}).get("snapshot_identity") != source_identity:
        raise Refused("SIDECAR_SOURCE_IDENTITY_MISMATCH")
    for key in ("coverage", "tickers", "patterns", "summary", "authority_boundary", "limitations"):
        if key not in payload:
            raise Refused(f"SIDECAR_SCHEMA_MISSING:{key}")
    coverage, tickers = payload["coverage"], payload["tickers"]
    scanned = {t for t, row in tickers.items() if row.get("status") != "EXCLUDED"}
    if coverage["scanned_count"] + coverage["excluded_count"] != coverage["candidate_count"] or \
            coverage["candidate_count"] != len(tickers) or len(scanned) != coverage["scanned_count"]:
        raise Refused("SIDECAR_COVERAGE_INCOMPLETE")
    if expected_candidates is not None and coverage["candidate_count"] != expected_candidates:
        raise Refused("SIDECAR_CANDIDATE_COUNT_NOT_SOURCE_DENOMINATOR")
    for ticker in scanned:
        row = tickers[ticker]
        if row.get("latest_bar_session") != session or not row.get("price_basis"):
            raise Refused(f"SIDECAR_TICKER_SOURCE_NOT_SESSION:{ticker}")
    for pattern in payload["patterns"]:
        if pattern.get("ticker") not in scanned:
            raise Refused("SIDECAR_PATTERN_TICKER_NOT_SCANNED")
    return {"component": component, "json_sha256": _sha256_file(json_path), "js_sha256": _sha256_file(js_path),
            "coverage": coverage, "patterns": len(payload["patterns"])}


# ---------------------------------------------------------------- build (checkpointed)
def build_checkpoint(snapshot: Mapping[str, Any], *, session: str, source_identity: str, ckpt: Path,
                     workers: int) -> dict[str, Any]:
    from stocklookup_core.tactical import candlestick_patterns as engine
    from stocklookup_core.tactical import current_session_candlestick_projection as projection
    candidates = len(snapshot["records"])
    if ckpt.is_dir():
        try:
            verified = verify_sidecar(ckpt, session, source_identity, candidates)
            return {"state": "REUSED", **verified}
        except (Refused, OSError, ValueError):
            shutil.rmtree(ckpt)  # only this tool's own checkpoint; rebuilt below
    partial = ckpt.with_name(ckpt.name + f".partial-{os.getpid()}")
    if partial.exists():
        shutil.rmtree(partial)
    started = time.perf_counter()
    payload = projection.build_projection(snapshot, session=session, workers=workers)
    partial.mkdir(parents=True)
    engine.atomic_write_snapshot(payload, partial / SIDECAR_JSON, partial / SIDECAR_JS)
    _write_json(partial / COMPONENT, projection.component_state(payload, session))
    elapsed = time.perf_counter() - started
    verified = verify_sidecar(partial, session, source_identity, candidates)
    ckpt.parent.mkdir(parents=True, exist_ok=True)
    os.replace(partial, ckpt)
    return {"state": "BUILT", "build_seconds": round(elapsed, 1), **verified}


# ---------------------------------------------------------------- stage / publish / rollback
def _copy_atomic(src: Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    tmp = dst.with_name(dst.name + f".{os.getpid()}.tmp")
    shutil.copyfile(src, tmp)
    os.replace(tmp, dst)


def stage_runtime(ckpt: Path, runtime_root: Path, txn: Path) -> dict[str, Any]:
    data = runtime_root / "data"
    previous = txn / "previous"
    previous.mkdir(parents=True, exist_ok=True)
    record = {}
    for name in (SIDECAR_JSON, SIDECAR_JS):
        current = data / name
        if current.is_file():
            shutil.copyfile(current, previous / name)
            record[name] = _sha256_file(previous / name)
        else:
            record[name] = None
    _write_json(txn / "previous.json", record)
    for name in (SIDECAR_JSON, SIDECAR_JS):
        _copy_atomic(ckpt / name, data / name)
        if _sha256_file(data / name) != _sha256_file(ckpt / name):
            raise RuntimeError(f"STAGE_HASH_MISMATCH:{name}")
    return {"runtime_data": str(data), "previous": record}


def restore_runtime(runtime_root: Path, txn: Path) -> dict[str, Any]:
    record = json.loads((txn / "previous.json").read_text(encoding="utf-8"))
    data = runtime_root / "data"
    for name, sha in record.items():
        if sha is None:
            with contextlib.suppress(FileNotFoundError):
                (data / name).unlink()
        else:
            _copy_atomic(txn / "previous" / name, data / name)
            if _sha256_file(data / name) != sha:
                raise RuntimeError(f"ROLLBACK_HASH_MISMATCH:{name}")
    return {"restored": record}


def release_sessions(runtime_root: Path, web_dir: Path) -> dict[str, Any]:
    """Runtime session via the publisher's own release-session contract; web via build_info."""
    import release_session_contract
    required = ["screen_snapshot.csv", "market_breadth.csv", "analysis_latest.json"]
    required += [n for n in ("screen_snapshot_live.csv",) if (runtime_root / n).is_file()]
    try:
        report = release_session_contract.resolve_release_session(runtime_root, required)
        runtime = report.session if report.ready else None
    except (OSError, ValueError):
        runtime = None
    try:
        web = json.loads((web_dir / "data" / "build_info.json").read_text(encoding="utf-8")).get("market_session")
    except (OSError, ValueError):
        web = None
    return {"runtime": runtime, "web": web}


def governed_publisher(producer_root: Path, runtime_root: Path, web_dir: Path, session: str,
                       complete_publication: bool) -> dict[str, Any]:
    from tools.run_owner_daily import publish_dashboard_release
    return publish_dashboard_release(producer_root, runtime_root, session, web_dir=web_dir,
                                     complete_publication=complete_publication)


def verify_published(web_dir: Path, session: str, verified: Mapping[str, Any]) -> list[str]:
    problems = []
    try:
        info = json.loads((web_dir / "data" / "build_info.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ["WEB_BUILD_INFO_UNREADABLE"]
    if info.get("market_session") != session:
        problems.append("WEB_SESSION_MISMATCH")
    comp = (((info.get("domains") or {}).get("signals") or {}).get("components") or {}).get("candlestick_patterns") or {}
    if comp.get("status") != "CURRENT" or comp.get("projection_identity") != verified["component"]["projection_identity"]:
        problems.append("WEB_SIGNALS_DOMAIN_NOT_CURRENT_FOR_SIDECAR")
    web_json = web_dir / "data" / SIDECAR_JSON
    if not web_json.is_file() or _sha256_file(web_json) != verified["json_sha256"]:
        problems.append("WEB_SIDECAR_BYTES_MISMATCH")
    return problems


def latest_transaction(ckpt: Path) -> Path | None:
    txns = sorted((ckpt / "transactions").glob("*/previous.json"))
    return txns[-1].parent if txns else None


# ---------------------------------------------------------------- entry
def run(args: argparse.Namespace, *, publisher: Callable[..., Mapping[str, Any]] | None = None,
        observe_rows=observe_command_lines, observe_ram=observe_available_ram) -> tuple[int, dict[str, Any]]:
    started = time.perf_counter()
    producer_root = Path(args.producer_root).resolve()
    retained_root = Path(args.retained_root).resolve() if args.retained_root else producer_root.parent / "retained-evidence"
    checkpoint_root = Path(args.checkpoint_root).resolve()
    runtime_root = Path(args.runtime_root).resolve() if args.runtime_root else None
    web_dir = Path(args.web_dir).resolve() if args.web_dir else None
    receipt: dict[str, Any] = {"contract_version": CONTRACT_VERSION, "session": args.session,
                               "code_digest": code_digest(),
                               "source_identity": args.source_identity, "started_at": _now(),
                               "mode": "rollback" if args.rollback else ("publish" if args.publish else
                                                                          "stage" if args.stage else "build")}
    ckpt = checkpoint_dir(checkpoint_root, args.session, args.source_identity)
    code = EXIT_OK
    try:
        if (args.stage or args.publish or args.rollback) and runtime_root is None:
            raise Refused("RUNTIME_ROOT_REQUIRED")
        if (args.publish or args.rollback) and web_dir is None and args.publish:
            raise Refused("WEB_DIR_REQUIRED")
        receipt["preflight"] = preflight(checkpoint_root=checkpoint_root, runtime_root=runtime_root,
                                         min_free_ram=int(args.min_free_ram_gib * GIB),
                                         min_free_disk=int(args.min_free_disk_gib * GIB),
                                         observe_rows=observe_rows, observe_ram=observe_ram)
        with instance_lock(checkpoint_root):
            receipt["registry"] = committed_session(producer_root, args.session)
            receipt["operation"] = operation_binding(retained_root, args.session, args.source_identity)
            if args.rollback:
                txn = latest_transaction(ckpt)
                if txn is None:
                    raise Refused("NO_TRANSACTION_TO_ROLL_BACK")
                receipt["rollback"] = restore_runtime(runtime_root, txn)
                if args.publish:
                    result = (publisher or governed_publisher)(producer_root, runtime_root, web_dir, args.session,
                                                               args.complete_publication)
                    receipt["publication"] = dict(result)
                    if result.get("status") not in PUBLISHED_STATES:
                        code = EXIT_FAILED
                receipt["status"] = "ROLLED_BACK" if code == EXIT_OK else "ROLLBACK_PUBLISH_FAILED"
                return code, receipt
            snap_path = Path(args.snapshot) if args.snapshot else default_snapshot_path(retained_root, args.session)
            snapshot, file_sha = load_verified_snapshot(snap_path, args.session, args.source_identity)
            receipt["source"] = {"snapshot": str(snap_path), "file_sha256": file_sha,
                                 "candidate_count": len(snapshot["records"])}
            built = build_checkpoint(snapshot, session=args.session, source_identity=args.source_identity,
                                     ckpt=ckpt, workers=args.workers)
            del snapshot
            if _sha256_file(snap_path) != file_sha:
                raise Refused("SOURCE_SNAPSHOT_CHANGED_DURING_BUILD")
            receipt["checkpoint"] = {"dir": str(ckpt), **built}
            receipt["status"] = built["state"]
            if not (args.stage or args.publish):
                return code, receipt
            if args.publish:
                sessions = release_sessions(runtime_root, web_dir)
                receipt["release_sessions"] = sessions
                if sessions["runtime"] != args.session or sessions["web"] != args.session:
                    raise Refused("WORKSPACE_RELEASE_SESSION_MISMATCH")
            txn = ckpt / "transactions" / datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
            receipt["stage"] = stage_runtime(ckpt, runtime_root, txn)
            receipt["transaction"] = str(txn)
            receipt["status"] = "STAGED"
            if not args.publish:
                return code, receipt
            try:
                result = (publisher or governed_publisher)(producer_root, runtime_root, web_dir, args.session,
                                                           args.complete_publication)
            except Exception as exc:  # noqa: BLE001 - any publisher failure rolls the runtime pair back
                result = {"status": "FAILED", "reason": f"{type(exc).__name__}:{exc}"}
            receipt["publication"] = dict(result)
            ok = result.get("status") in PUBLISHED_STATES
            problems = verify_published(web_dir, args.session, built) if ok else ["PUBLISHER_FAILED"]
            receipt["publication_checks"] = problems
            if problems:
                receipt["rollback"] = restore_runtime(runtime_root, txn)
                receipt["status"] = "PUBLISH_FAILED_RUNTIME_ROLLED_BACK"
                code = EXIT_FAILED
                if ok:
                    # The publisher already released bytes that failed verification: release the
                    # restored previous pair through the same path so the public state converges
                    # back instead of staying half-published.
                    try:
                        again = (publisher or governed_publisher)(producer_root, runtime_root, web_dir, args.session,
                                                                  args.complete_publication)
                    except Exception as exc:  # noqa: BLE001
                        again = {"status": "FAILED", "reason": f"{type(exc).__name__}:{exc}"}
                    receipt["rollback_publication"] = dict(again)
                    receipt["status"] = ("PUBLISH_FAILED_ROLLED_BACK_AND_REPUBLISHED"
                                         if again.get("status") in PUBLISHED_STATES
                                         else "PUBLISH_FAILED_ROLLBACK_REPUBLISH_FAILED")
            else:
                receipt["status"] = "PUBLISHED" if result.get("status") == "PUBLISHED" else "PUBLISHED_LOCAL"
            return code, receipt
    except Skip as exc:
        receipt.update(status="SKIP", reason=str(exc))
        return EXIT_SKIP, receipt
    except Refused as exc:
        receipt.update(status="REFUSED", reason=str(exc))
        return EXIT_REFUSED, receipt
    finally:
        receipt["elapsed_seconds"] = round(time.perf_counter() - started, 1)
        receipt["peak_rss_bytes"] = peak_rss_bytes()
        receipt["finished_at"] = _now()
        with contextlib.suppress(OSError):
            _write_json(checkpoint_root / args.session / "runs" /
                        f"{receipt['started_at'].replace(':', '')}-{receipt['mode']}.json", receipt)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--session", required=True)
    parser.add_argument("--source-identity", required=True,
                        help="p3f9_exact_session_snapshot:<sha256> bound by the session's Daily operation record")
    parser.add_argument("--checkpoint-root", required=True)
    parser.add_argument("--producer-root", default=str(ROOT))
    parser.add_argument("--retained-root", default=None)
    parser.add_argument("--snapshot", default=None)
    parser.add_argument("--runtime-root", default=None)
    parser.add_argument("--web-dir", default=None)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--min-free-ram-gib", type=float, default=2.5)
    parser.add_argument("--min-free-disk-gib", type=float, default=2.0)
    parser.add_argument("--stage", action="store_true", help="copy the verified pair into <runtime-root>/data")
    parser.add_argument("--publish", action="store_true", help="stage + governed Dashboard release (Owner-gated)")
    parser.add_argument("--complete-publication", action="store_true",
                        help="require Dashboard CI/Pages/public-byte proof (as Daily does)")
    parser.add_argument("--rollback", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.workers < 1 or args.workers > 2:
        print(json.dumps({"status": "REFUSED", "reason": "WORKERS_OUT_OF_16GB_BOUND"}))
        return EXIT_REFUSED
    code, receipt = run(args)
    summary = {k: receipt.get(k) for k in ("status", "reason", "session", "mode", "elapsed_seconds", "peak_rss_bytes")}
    if "checkpoint" in receipt:
        summary["coverage"] = receipt["checkpoint"].get("coverage")
        summary["projection_identity"] = receipt["checkpoint"]["component"].get("projection_identity")
    print(json.dumps(summary, ensure_ascii=False, default=str))
    return code


if __name__ == "__main__":
    raise SystemExit(main())
