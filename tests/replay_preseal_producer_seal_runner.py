"""Isolated Canonical Daily through Producer sealing for session 2026-10-26.

This is a retained-evidence regression under the unchanged 7 GiB process ceiling and
a measurement-only 6.75 GiB Windows job ceiling. Ordinary Daily keeps its 8 GiB tree.
It is not a production Daily, not a publication, and not a T0 capture. The production
registry, the retained 2026-10-26 integrated decision artifact, and every production
path outside the experiment are write-refused.
"""
from __future__ import annotations

from datetime import date, datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
import traceback

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SESSION = "2026-10-26"
PRODUCTION_CODE = Path(r"T:\StockLookup\production-v1\stock-core-private")
PRODUCTION_RETAINED = Path(r"T:\StockLookup\production-v1\retained-evidence")
PRODUCTION_REGISTRY = Path(
    r"T:\StockLookup\production-v1\stock-core-private\config\daily_research_session_input_registry.json")
PRODUCTION_IID = (PRODUCTION_RETAINED / "operations-review"
                  / "integrated-investment-decision-product-v1-20261026"
                  / "integrated_investment_decision_product_artifact.json")
WRITE_CONTAINERS = {
    "daily-producer-runs-v1",
    "daily-research-session-operations-v1",
    "daily-session-shadow-recommendation-v1",
    "canonical-post-close-v1",
}
PROTECTED = (
    PRODUCTION_RETAINED,
    Path(r"T:\StockLookup\production-v1\stock-core-private"),
    Path(r"T:\StockLookup\production-v1\dashboard-runtime"),
    ROOT,
)
EXPERIMENT = Path(r"T:\StockLookup\scratch\preseal-producer-seal-20261026-r10")


def production_identity_of(iid: Path, registry: Path) -> dict:
    return {
        "production_iid_sha256": file_digest(iid),
        "production_iid_bytes": iid.stat().st_size,
        "production_registry_sha256": file_digest(registry),
        "production_registry_bytes": registry.stat().st_size,
    }


def same_production_identity(before: dict, after: dict) -> bool:
    return (before["production_iid_sha256"] == after["production_iid_sha256"]
            and before["production_registry_sha256"] == after["production_registry_sha256"])


def experiment_directory_allowed(experiment: Path) -> None:
    resolved = experiment.resolve()
    for protected in PROTECTED:
        protected_resolved = protected.resolve()
        if resolved == protected_resolved or resolved.is_relative_to(protected_resolved):
            raise SystemExit("EXPERIMENT_INSIDE_PROTECTED_ROOT")
    if experiment.exists():
        raise SystemExit("EXPERIMENT_ALREADY_EXISTS")


def measurement_tree_ceiling(admission: dict) -> int:
    """Return the tree maximum only when admission was computed from it."""
    from tools.check_owner_daily_host_preflight import (
        MEASUREMENT_COMMIT_BYTES, MEASUREMENT_COMMIT_RESERVE_BYTES, MEASUREMENT_OWNER_ALLOWANCE_BYTES,
        MEASUREMENT_PHYSICAL_BYTES, MEASUREMENT_PHYSICAL_RESERVE_BYTES, MEASUREMENT_PROCESS_BYTES,
        MEASUREMENT_TREE_BYTES)
    if (admission.get("tree_ceiling_bytes") != MEASUREMENT_TREE_BYTES
            or admission.get("process_ceiling_bytes") != MEASUREMENT_PROCESS_BYTES
            or admission.get("physical_reserve_bytes") != MEASUREMENT_PHYSICAL_RESERVE_BYTES
            or admission.get("commit_reserve_bytes") != MEASUREMENT_COMMIT_RESERVE_BYTES
            or admission.get("owner_allowance_bytes") != MEASUREMENT_OWNER_ALLOWANCE_BYTES
            or admission.get("physical_budget_bytes") != MEASUREMENT_PHYSICAL_BYTES
            or admission.get("commit_budget_bytes") != MEASUREMENT_COMMIT_BYTES
            or admission.get("qualified_current_scale") is not False
            or admission.get("iid_max_extended") is not False):
        raise OSError("MEASUREMENT_CEILING_NOT_THE_ENFORCED_BUDGET")
    return MEASUREMENT_TREE_BYTES


def file_digest(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


CATALOG_FILE = "config/retained_evidence_cold_catalog.json"
_REPARSE = 0x400
_SESSION_TOUCH_DAY = date(2026, 10, 27)
_MUTABLE_COPY_LIMIT = 32 * 1024 * 1024


def junction(link: Path, target: Path) -> None:
    subprocess.check_call(["cmd", "/c", "mklink", "/J", str(link), str(target)], stdout=subprocess.DEVNULL)


def _reparse(path: Path) -> bool:
    return bool(path.exists() and (
        getattr(path, "is_junction", lambda: False)() or path.is_symlink()
        or (getattr(path.stat(), "st_file_attributes", 0) & _REPARSE)))


def catalog_required_relatives() -> set[str]:
    """Paths load() passes to safe_path. Ancestors must be real directories."""
    catalog = json.loads((PRODUCTION_RETAINED / CATALOG_FILE).read_text(encoding="utf-8"))
    required = {CATALOG_FILE}
    for entry in catalog["entries"]:
        required.add(entry["relative_path"])
        vault = entry.get("vault")
        if isinstance(vault, dict):
            for key in ("manifest_path", "object_path"):
                value = vault.get(key)
                if isinstance(value, str):
                    required.add(value)
    return required


def _covers(relative: str, required: set[str]) -> bool:
    prefix = relative.rstrip("/") + "/"
    return any(item == relative or item.startswith(prefix) for item in required)


def _touched_today(path: Path) -> bool:
    return datetime.fromtimestamp(path.stat().st_mtime).date() == _SESSION_TOUCH_DAY


def materialize_writable(source: Path, destination: Path, copied: list[str]) -> None:
    """Real directory for a tree this session writes. Older children stay junctions."""
    if _reparse(source):
        raise RuntimeError("WRITABLE_SOURCE_IS_REPARSE:" + str(source))
    destination.mkdir()
    for nested in source.iterdir():
        target = destination / nested.name
        if nested.is_dir():
            if _touched_today(nested):
                materialize_writable(nested, target, copied)
            else:
                junction(target, nested)
            continue
        if nested.stat().st_size <= _MUTABLE_COPY_LIMIT:
            shutil.copy2(nested, target)
            copied.append(str(target))


def _place_directory(source: Path, destination: Path, copied: list[str]) -> None:
    if _touched_today(source):
        materialize_writable(source, destination, copied)
    else:
        junction(destination, source)


def place_tree(source: Path, destination: Path, relative: str, required: set[str], copied: list[str]) -> None:
    """Copy catalog files through real directories. Junction only non-ancestor siblings."""
    if source.is_dir():
        if _reparse(source):
            raise RuntimeError("CATALOG_ANCESTOR_SOURCE_IS_REPARSE:" + relative)
        destination.mkdir()
        for nested in source.iterdir():
            child_rel = relative + "/" + nested.name
            if nested.is_dir() and _covers(child_rel, required):
                place_tree(nested, destination / nested.name, child_rel, required, copied)
            elif nested.is_dir():
                _place_directory(nested, destination / nested.name, copied)
            elif child_rel in required or ( _touched_today(nested) and nested.stat().st_size <= _MUTABLE_COPY_LIMIT):
                shutil.copy2(nested, destination / nested.name)
                copied.append(child_rel)
        return
    if relative in required:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(relative)


def assert_catalog_paths_real(sandbox: Path, required: set[str]) -> None:
    sandbox = sandbox.absolute()
    for relative in sorted(required):
        target = sandbox.joinpath(*relative.split("/"))
        node = target
        while True:
            if node.exists() and _reparse(node):
                raise RuntimeError("SANDBOX_CATALOG_REPARSE:" + str(node))
            if node == sandbox:
                break
            node = node.parent
        if not target.is_file():
            raise RuntimeError("SANDBOX_CATALOG_FILE_MISSING:" + relative)


def build_sandbox(sandbox: Path) -> list[str]:
    required = catalog_required_relatives()
    copied: list[str] = []
    config_src = PRODUCTION_RETAINED / "config"
    config_dst = sandbox / "config"
    config_dst.mkdir(parents=True)
    for nested in config_src.iterdir():
        relative = "config/" + nested.name
        if nested.is_dir() and _covers(relative, required):
            place_tree(nested, config_dst / nested.name, relative, required, copied)
        elif nested.is_dir():
            junction(config_dst / nested.name, nested)
        else:
            shutil.copy2(nested, config_dst / nested.name)
            copied.append(relative)
    receipts = PRODUCTION_RETAINED / "storage-location-receipts"
    if receipts.exists():
        if _covers("storage-location-receipts", required):
            place_tree(receipts, sandbox / "storage-location-receipts", "storage-location-receipts", required, copied)
        else:
            junction(sandbox / "storage-location-receipts", receipts)
    ops = sandbox / "operations-review"
    ops.mkdir()
    for child in (PRODUCTION_RETAINED / "operations-review").iterdir():
        destination = ops / child.name
        relative = "operations-review/" + child.name
        if child.is_dir() and _covers(relative, required):
            place_tree(child, destination, relative, required, copied)
            continue
        if child.name in WRITE_CONTAINERS and child.is_dir():
            destination.mkdir()
            for nested in child.iterdir():
                if nested.is_dir():
                    _place_directory(nested, destination / nested.name, copied)
                elif nested.is_file() and nested.stat().st_size <= _MUTABLE_COPY_LIMIT:
                    shutil.copy2(nested, destination / nested.name)
                    copied.append(relative + "/" + nested.name)
            continue
        if "20261026" in child.name and child.is_dir():
            shutil.copytree(child, destination, ignore=shutil.ignore_patterns(
                "integrated_investment_decision_product_artifact.json"))
            continue
        if child.is_dir():
            _place_directory(child, destination, copied)
        elif child.is_file():
            shutil.copy2(child, destination)
    (sandbox / "runtime").mkdir()
    assert_catalog_paths_real(sandbox, required)
    return copied


def link_producer_static(experiment: Path) -> list[str]:
    """Expose production-checkout static inputs without copying them into the worktree."""
    manifest = json.loads((ROOT / "config" / "daily_static_inputs.json").read_text(encoding="utf-8"))
    linked: list[str] = []
    seen: set[Path] = set()
    for entry in manifest["inputs"]:
        if entry.get("role") != "producer":
            continue
        relative = Path(entry["path"])
        holder = relative.parts[1] if relative.parts[0] == "operations-review" else relative.parts[0]
        link = ROOT / relative.parts[0] / holder if relative.parts[0] == "operations-review" else ROOT / relative.parts[0]
        target = PRODUCTION_CODE / link.relative_to(ROOT)
        if link in seen:
            continue
        seen.add(link)
        if link.exists():
            continue
        link.parent.mkdir(parents=True, exist_ok=True)
        junction(link, target)
        linked.append(str(link))
    (experiment / "producer-links.json").write_text(json.dumps(linked, indent=2), encoding="utf-8")
    return linked


def link_frozen_registry_inputs(experiment: Path) -> list[str]:
    """Copy relative completed-session inputs onto the code root.

    The frozen 2026-10-26 rows for official universe and event context are
    code-root paths. Junctioning that directory would let a later write resolve
    into the production checkout, so these small files are real copies.
    """
    registry = json.loads(PRODUCTION_REGISTRY.read_text(encoding="utf-8"))
    selected = (registry.get("sessions") or {}).get(SESSION) or {}
    copied: list[str] = []
    for entry in selected.values():
        if not isinstance(entry, dict):
            continue
        relative = entry.get("path")
        if not isinstance(relative, str) or ":" in relative or relative.startswith(("/", "\\")):
            continue
        destination = ROOT.joinpath(*relative.split("/"))
        source = PRODUCTION_CODE.joinpath(*relative.split("/"))
        if destination.exists() or not source.is_file():
            continue
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
        copied.append(str(destination))
    (experiment / "frozen-input-copies.json").write_text(json.dumps(copied, indent=2), encoding="utf-8")
    return copied


def remove_frozen_copies(experiment: Path) -> None:
    path = experiment / "frozen-input-copies.json"
    if not path.is_file():
        return
    holder = (ROOT / "operations-review" / "corporate-daily-frozen-inputs-v1").resolve()
    for raw in json.loads(path.read_text(encoding="utf-8")):
        file = Path(raw)
        if file.is_file() and not _reparse(file):
            file.unlink()
        parent = file.parent
        while parent.exists() and parent.resolve() != holder and holder in parent.resolve().parents:
            try:
                parent.rmdir()
            except OSError:
                break
            parent = parent.parent
    if holder.exists():
        try:
            holder.rmdir()
        except OSError:
            pass


def remove_producer_links(experiment: Path) -> None:
    path = experiment / "producer-links.json"
    if not path.is_file():
        return
    for raw in json.loads(path.read_text(encoding="utf-8")):
        link = Path(raw)
        if link.exists():
            subprocess.check_call(["cmd", "/c", "rmdir", str(link)], stdout=subprocess.DEVNULL)


def prepare_registry(experiment: Path) -> None:
    destination = ROOT / "config" / "daily_research_session_input_registry.json"
    shutil.copy2(PRODUCTION_REGISTRY, destination)
    (experiment / "registry-copied-from-production.sha256").write_text(
        file_digest(destination) + "\n", encoding="utf-8")


def restore_registry() -> None:
    subprocess.check_call(
        ["git", "-C", str(ROOT), "checkout", "--", "config/daily_research_session_input_registry.json"],
        stdout=subprocess.DEVNULL)


def child(experiment: Path) -> int:
    import canonical_daily_operation as daily
    from datetime import datetime, timedelta, timezone
    from completed_market_session_gate import CompletedSessionGateError
    import tests.preseal_consumer_dependency as consumer_dependency

    try:
        consumer_dependency.assert_relocated_binding(ROOT)
    except consumer_dependency.ConsumerDependencyError as exc:
        (experiment / "child-result.json").write_text(json.dumps({
            "seal_boundary": "FAILED", "stage": "CONSUMER_DEPENDENCY", "error": str(exc),
        }, indent=2), encoding="utf-8")
        return 1

    sandbox = experiment / "sandbox"
    copied = build_sandbox(sandbox)
    (experiment / "catalog-materialized.json").write_text(
        json.dumps({"copied_count": len(copied), "copied": copied}, indent=2), encoding="utf-8")
    link_producer_static(experiment)
    link_frozen_registry_inputs(experiment)
    prepare_registry(experiment)
    before = production_identity_of(PRODUCTION_IID, PRODUCTION_REGISTRY)
    (experiment / "production-before.json").write_text(json.dumps(before, indent=2), encoding="utf-8")
    violations: list[str] = []
    auditing = False

    def refuse(reason: str) -> None:
        nonlocal auditing
        violations.append(reason)
        auditing = True
        try:
            (experiment / "offline-violations.json").write_text(json.dumps(violations), encoding="utf-8")
        finally:
            auditing = False
        raise RuntimeError(reason)

    registry_path = (ROOT / "config" / "daily_research_session_input_registry.json").resolve()

    def audit(event, values):
        nonlocal auditing
        if auditing:
            return
        if event in {"socket.connect", "socket.getaddrinfo", "subprocess.Popen", "os.system"}:
            refuse("SANDBOX_FORBIDDEN:" + event)
        if event == "open" and isinstance(values[0], (str, bytes, os.PathLike)):
            path = Path(os.fsdecode(values[0])).resolve()
            mode = values[1] if len(values) > 1 else ""
            flags = values[2] if len(values) > 2 and isinstance(values[2], int) else 0
            writing = any(mark in str(mode) for mark in ("w", "a", "+")) or bool(
                flags & (os.O_WRONLY | os.O_RDWR | os.O_CREAT | os.O_TRUNC | os.O_APPEND))
            allowed = path.is_relative_to(experiment.resolve()) or path == registry_path
            if writing and not allowed:
                refuse("SANDBOX_WRITE_OUTSIDE_EXPERIMENT:" + str(path))
        if event in {"os.remove", "os.mkdir", "os.rmdir", "os.rename", "os.replace"}:
            for value in values[:2]:
                if isinstance(value, (str, bytes, os.PathLike)):
                    path = Path(os.fsdecode(value)).resolve()
                    if not path.is_relative_to(experiment.resolve()) and path != registry_path:
                        refuse("SANDBOX_MUTATION_OUTSIDE_EXPERIMENT:" + str(path))

    sys.addaudithook(audit)
    snapshot_path = sandbox / "operations-review" / "p3f9b-market-wide-exact-session-scaleout-20261026" / "p3f9b_mva_exact_session_snapshot.json"
    envelope = json.loads(snapshot_path.read_text(encoding="utf-8"))
    envelope.pop("records", None)
    import gc
    gc.collect()
    instant = datetime(2026, 10, 27, 14, 16, 29, tzinfo=timezone(timedelta(hours=7)))
    trace = (experiment / "stages.jsonl").open("w", encoding="utf-8", buffering=1)

    def progress(value):
        trace.write(json.dumps({"at": time.time(), "subtask": value.get("subtask"), "status": value.get("status")}) + "\n")

    def stop_after_seal(*_args, **_kwargs):
        raise daily.CanonicalRuntimeReleaseError("SANDBOX_STOP_AFTER_PRODUCER_SEAL")

    def macro_refresh(_root, _runtime):
        return {"status": "FAILED", "reason_code": "SANDBOX_MACRO_REFRESH_NOT_RUN"}

    outcome = {"session": SESSION, "operating_mode": daily.OPERATING_MODE_ORDINARY_DAILY}
    try:
        daily.run_canonical_daily_operation(
            ROOT, sandbox / "runtime", SESSION,
            now=instant, workers=12, complete_publication=False,
            exact_session_evidence=envelope, allow_provider_probe=False,
            retained_evidence_root=sandbox, operation_output_root=sandbox,
            no_new_provider_acquisition=True,
            operating_mode=daily.OPERATING_MODE_ORDINARY_DAILY,
            runtime_fn=stop_after_seal, macro_refresh_fn=macro_refresh,
            progress_callback=progress,
        )
        outcome["seal_boundary"] = "RETURNED_WITHOUT_RUNTIME_STOP"
    except daily.CanonicalDailyOperationError as exc:
        outcome["stage"] = exc.stage
        outcome["error"] = str(exc)
        outcome["seal_boundary"] = "STOPPED_AFTER_PRODUCER" if "SANDBOX_STOP_AFTER_PRODUCER_SEAL" in str(exc) else "FAILED"
    except (OSError, RuntimeError, CompletedSessionGateError, ValueError) as exc:
        outcome["stage"] = type(exc).__name__
        outcome["error"] = str(exc)
        outcome["seal_boundary"] = "FAILED"
    except Exception as exc:
        outcome["stage"] = type(exc).__name__
        outcome["error"] = str(exc)
        outcome["traceback"] = traceback.format_exc()
        outcome["seal_boundary"] = "FAILED"
    finally:
        trace.close()
    manifests = sorted((sandbox / "operations-review" / "daily-producer-runs-v1").glob("*/run_manifest.json"))
    # A junctioned historical manifest is not this run. Keep manifests whose path does not resolve into production.
    fresh = [path for path in manifests if not path.resolve().is_relative_to(PRODUCTION_RETAINED.resolve())]
    producer_manifest = None
    if fresh:
        producer_manifest = json.loads(fresh[-1].read_text(encoding="utf-8"))
        outcome["producer_manifest"] = {
            "path": str(fresh[-1]),
            "status": producer_manifest.get("status"),
            "session": producer_manifest.get("session") or producer_manifest.get("market_session"),
        }
    current_iid = (sandbox / "operations-review" / "integrated-investment-decision-product-v1-20261026"
                   / "integrated_investment_decision_product_artifact.json")
    if current_iid.is_file() and not current_iid.resolve().is_relative_to(PRODUCTION_RETAINED.resolve()):
        import next_session_decision_brief as brief
        outcome["sandbox_iid"] = {
            "bytes": current_iid.stat().st_size,
            "window": brief._window_header(current_iid),
        }
        if outcome.get("seal_boundary") == "STOPPED_AFTER_PRODUCER":
            try:
                outcome["sandbox_t0"] = _sandbox_streamed_t0(experiment, current_iid, producer_manifest, SESSION)
            except Exception as exc:
                outcome["sandbox_t0"] = {"status": "FAILED", "error": type(exc).__name__ + ":" + str(exc)}
    previous = (sandbox / "operations-review" / "integrated-investment-decision-product-v1-20261023"
                / "integrated_investment_decision_product_artifact.json")
    outcome["previous_iid_bytes"] = previous.stat().st_size if previous.is_file() else None
    after = production_identity_of(PRODUCTION_IID, PRODUCTION_REGISTRY)
    outcome["production_unchanged"] = same_production_identity(before, after)
    outcome["production_before"] = before
    outcome["violations"] = violations
    (experiment / "child-result.json").write_text(json.dumps(outcome, indent=2), encoding="utf-8")
    sealed = outcome.get("seal_boundary") == "STOPPED_AFTER_PRODUCER" and (outcome.get("producer_manifest") or {}).get("status") == "COMPLETED"
    t0_verified = outcome.get("sandbox_t0", {}).get("status") == "VERIFIED"
    return 0 if sealed and t0_verified and outcome["production_unchanged"] and not violations else 1


def _private_commit():
    if os.name != "nt":
        return None
    import ctypes
    from ctypes import wintypes

    class Counters(ctypes.Structure):
        _fields_ = [("cb", wintypes.DWORD), ("PageFaultCount", wintypes.DWORD),
                    ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                    ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                    ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t), ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                    ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t),
                    ("PrivateUsage", ctypes.c_size_t)]
    counters = Counters(cb=ctypes.sizeof(Counters))
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        psapi = ctypes.WinDLL("psapi", use_last_error=True)
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE
        psapi.GetProcessMemoryInfo.argtypes = [wintypes.HANDLE, ctypes.POINTER(Counters), wintypes.DWORD]
        psapi.GetProcessMemoryInfo.restype = wintypes.BOOL
        process = kernel32.GetCurrentProcess()
        if not psapi.GetProcessMemoryInfo(process, ctypes.byref(counters), counters.cb):
            return None
    except (OSError, AttributeError, ValueError):
        return None
    return {"private_bytes": int(counters.PrivateUsage), "peak_pagefile_bytes": int(counters.PeakPagefileUsage)}


def _sandbox_streamed_t0(experiment, iid_path, manifest, session):
    """One streamed T0 under the experiment directory. It is not retained evidence."""
    from prospective_decision_retention import build_snapshot, write_immutable_snapshot
    from prospective_t0_seal_index import recover
    from stocklookup_core.evidence.record_artifact_loading import IndexedRecordMapping
    if not isinstance(manifest, dict):
        raise RuntimeError("SANDBOX_T0_PRODUCER_MANIFEST_MISSING")
    operation_identity = ((manifest.get("daily_session_operation") or {}).get("identity"))
    before = _private_commit()
    store, header = IndexedRecordMapping.from_file(iid_path)
    snapshot = build_snapshot(
        session=session, operation_identity=operation_identity,
        producer_run_identity=manifest.get("run_identity"),
        integrated_artifact={**header, "records": store}, scratch_dir=experiment / "t0-scratch")
    path = write_immutable_snapshot(experiment / "sandbox-t0", snapshot)
    recovered = recover(path, created_at="2026-10-28T00:00:00+07:00", diagnostic=True)
    return {"status": "VERIFIED", "path": str(path), "bytes": path.stat().st_size, "reads": store.reads,
            "commit_before": before, "commit_after": _private_commit(),
            "index_identity": recovered.get("artifact_identity"),
            "production_t0_equivalent": False,
            "qualification": "RECOVERED_STREAMING_MECHANICS_ONLY",
            "missing_production_inputs": ["exact_session_snapshot"]}


LOG_TAIL_BYTES = 4096


def bounded_log_tail(path: Path, limit: int = LOG_TAIL_BYTES) -> str:
    """Read only the last ``limit`` bytes. The full log stays on disk."""
    try:
        with path.open("rb") as handle:
            handle.seek(0, os.SEEK_END)
            size = handle.tell()
            handle.seek(max(0, size - limit))
            return handle.read(limit).decode("utf-8", errors="replace")
    except OSError:
        return ""


def last_completed_stage(path: Path) -> str | None:
    tail = bounded_log_tail(path, 8192).strip()
    if not tail:
        return None
    line = tail.splitlines()[-1]
    try:
        row = json.loads(line)
    except ValueError:
        return None
    if not isinstance(row, dict):
        return None
    return row.get("subtask") or row.get("status")


def write_child_exception_receipt(experiment: Path, exc: BaseException) -> None:
    payload = {
        "status": "CHILD_EXCEPTION",
        "seal_boundary": "FAILED",
        "stage": "CHILD_UNCAUGHT",
        "error": type(exc).__name__ + ":" + str(exc),
        "traceback": traceback.format_exc(),
    }
    (experiment / "child-result.json").write_text(json.dumps(payload, indent=2), encoding="utf-8")


def persist_uncaught_child(experiment: Path, exc: BaseException) -> None:
    """Write the traceback to the retained stderr stream before the receipt.

    ``traceback.print_exc`` writes to the stderr handle the parent already
    opened. It does not accumulate the log in RAM. If the receipt write fails,
    that stderr traceback remains and no child receipt is invented.
    """
    traceback.print_exc()
    try:
        sys.stderr.flush()
    except Exception:
        pass
    try:
        write_child_exception_receipt(experiment, exc)
    except OSError:
        pass


def observe_child_outcome(experiment: Path, *, returncode, guard_reason, guard_diagnostics) -> dict:
    """Classify a finished child without inventing a successful child receipt."""
    child_path = experiment / "child-result.json"
    stdout_log = experiment / "child-stdout.log"
    stderr_log = experiment / "child-stderr.log"
    child_present = child_path.is_file()
    child_payload = None
    if child_present:
        try:
            loaded = json.loads(child_path.read_text(encoding="utf-8"))
            child_payload = loaded if isinstance(loaded, dict) else None
        except (OSError, ValueError, UnicodeError):
            child_payload = None
    reason = None if guard_reason is None else str(guard_reason)
    stderr_tail = bounded_log_tail(stderr_log)
    if reason and "DAILY_CAPACITY_MEMORY_LIMIT" in reason:
        kind = "MEMORY_LIMIT"
    elif reason:
        kind = "GUARD_FAILURE"
    elif child_payload and child_payload.get("status") == "CHILD_EXCEPTION":
        kind = "CHILD_EXCEPTION"
    elif child_present:
        kind = "CHILD_RESULT"
    elif "ImportError" in stderr_tail or "ModuleNotFoundError" in stderr_tail:
        kind = "IMPORT_FAILURE"
    else:
        kind = "CHILD_EXIT_WITHOUT_RESULT"
    stage = None
    if child_payload:
        stage = child_payload.get("stage") or child_payload.get("seal_boundary")
    if stage is None:
        stage = last_completed_stage(experiment / "stages.jsonl")
    parent_path = experiment / "parent-observed-failure.json"
    parent_written = False
    if not child_present:
        parent = {
            "status": "PARENT_OBSERVED_FAILURE",
            "kind": kind,
            "returncode": returncode,
            "reason": reason,
            "guard_diagnostics": guard_diagnostics if isinstance(guard_diagnostics, dict) else {},
            "last_completed_stage": stage,
            "stdout_log": str(stdout_log),
            "stderr_log": str(stderr_log),
            "child_result_present": False,
        }
        parent_path.write_text(json.dumps(parent, indent=2), encoding="utf-8")
        parent_written = True
    return {
        "returncode": returncode,
        "outcome_kind": kind,
        "last_completed_stage": stage,
        "guard_reason": reason,
        "guard_diagnostics": guard_diagnostics if isinstance(guard_diagnostics, dict) else {},
        "stdout_tail": bounded_log_tail(stdout_log),
        "stderr_tail": stderr_tail,
        "evidence": {
            "stdout_log": str(stdout_log),
            "stderr_log": str(stderr_log),
            "child_result": str(child_path) if child_present else None,
            "parent_observed_failure": str(parent_path) if parent_written else None,
            "guard_result": str(experiment / "guard-result.json"),
            "stages": str(experiment / "stages.jsonl"),
        },
    }


def main() -> None:
    experiment = EXPERIMENT
    import tests.preseal_consumer_dependency as consumer_dependency
    if "--child" not in sys.argv:
        try:
            dependency = consumer_dependency.preflight_producer_seal_consumer(ROOT)
        except consumer_dependency.ConsumerDependencyError as exc:
            print("DEPENDENCY_PREFLIGHT_FAILED:" + str(exc), flush=True)
            raise SystemExit(2) from exc
        preflight_path = Path(r"T:\StockLookup\scratch\preseal-consumer-dependency-preflight.json")
        preflight_path.write_text(json.dumps(dependency, indent=2), encoding="utf-8")
        print(json.dumps({"dependency_preflight": dependency["status"], "consumer_head": dependency["qualified"]["head"]}),
              flush=True)
        from tools.check_owner_daily_host_preflight import check, producer_seal_measurement_admission
        host = check(ROOT, PRODUCTION_RETAINED)
        admission = producer_seal_measurement_admission(host)
        report = experiment.with_name(experiment.name + "-admission.json")
        report.write_text(json.dumps({"admission": admission, "classification": host.get("classification"),
                                      "dependency_preflight": dependency["status"]}, indent=2),
                          encoding="utf-8")
        print(json.dumps(admission), flush=True)
        if not admission["admitted"]:
            raise SystemExit(3)
        enforced_tree = measurement_tree_ceiling(admission)
    experiment_directory_allowed(experiment)
    qualified_consumer = Path(consumer_dependency.qualify_consumer()["consumer"])
    consumer_dependency.bind_relocated_consumer(ROOT, qualified_consumer)
    diagnostics: dict = {}
    started = time.perf_counter()
    try:
        experiment.mkdir(parents=True)
        from stocklookup_core.acquisition import feedback_resource_guard as guard
        from tools.check_owner_daily_host_preflight import windows_memory

        def probe():
            if time.perf_counter() - started > 7200:
                raise OSError("PRESEAL_SEAL_REGRESSION_DEADLINE_7200_SECONDS")
            return windows_memory()

        command = [sys.executable, "-B", "-u", str(Path(__file__).resolve()), "--child", str(experiment)]
        stdout_log = experiment / "child-stdout.log"
        stderr_log = experiment / "child-stderr.log"
        returncode = None
        guard_reason = None
        try:
            returncode = guard.run_capacity_guarded(
                command, cwd=ROOT, env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1"},
                memory_probe=probe, on_diagnostics=diagnostics.update,
                tree_ceiling_bytes=enforced_tree,
                stdout_path=stdout_log, stderr_path=stderr_log)
            diagnostics.update(returncode=returncode)
        except OSError as exc:
            guard_reason = str(exc)
            diagnostics.update(reason=guard_reason, returncode=1, guard_diagnostics=getattr(exc, "diagnostics", {}))
            returncode = 1
        diagnostics.update(observe_child_outcome(
            experiment, returncode=returncode, guard_reason=guard_reason,
            guard_diagnostics=diagnostics.get("guard_diagnostics") or {}))
        if diagnostics.get("job_memory_limit_bytes") != enforced_tree:
            diagnostics["ceiling_mismatch"] = {
                "enforced_tree_bytes": enforced_tree,
                "observed_tree_bytes": diagnostics.get("job_memory_limit_bytes"),
            }
            diagnostics["returncode"] = 1
    finally:
        diagnostics["wall_seconds"] = round(time.perf_counter() - started, 3)
        try:
            consumer_dependency.unbind_relocated_consumer(ROOT, qualified_consumer)
        except consumer_dependency.ConsumerDependencyError as exc:
            diagnostics["consumer_unbind"] = str(exc)
            diagnostics["returncode"] = 1
        if experiment.exists():
            remove_producer_links(experiment)
            remove_frozen_copies(experiment)
        restore_registry()
        if experiment.exists():
            (experiment / "guard-result.json").write_text(json.dumps(diagnostics, indent=2), encoding="utf-8")
        print(json.dumps(diagnostics), flush=True)
    raise SystemExit(diagnostics.get("returncode", 1))


def _diagnostic_fixture(mode: str, experiment: Path) -> int:
    """Small child fixtures for the diagnostic contract. Not a Producer seal."""
    experiment.mkdir(parents=True, exist_ok=True)
    if mode == "raise":
        print("child-stdout-marker", flush=True)
        print("child-stderr-marker", file=sys.stderr, flush=True)
        raise RuntimeError("fixture-child-exception")
    if mode == "silent-exit":
        print("silent-stdout", flush=True)
        print("silent-stderr", file=sys.stderr, flush=True)
        return 7
    raise SystemExit("UNKNOWN_DIAGNOSTIC_FIXTURE")


if __name__ == "__main__":
    if "--diagnostic-fixture" in sys.argv:
        fixture = sys.argv[sys.argv.index("--diagnostic-fixture") + 1]
        target = Path(sys.argv[-1])
        try:
            code = _diagnostic_fixture(fixture, target)
        except BaseException as exc:
            if not isinstance(exc, SystemExit):
                persist_uncaught_child(target, exc)
                code = 1
            else:
                raise
        raise SystemExit(code)
    if "--child" in sys.argv:
        target = Path(sys.argv[-1])
        try:
            code = child(target)
        except BaseException as exc:
            if isinstance(exc, SystemExit):
                raise
            persist_uncaught_child(target, exc)
            raise SystemExit(1) from exc
        raise SystemExit(code)
    main()
