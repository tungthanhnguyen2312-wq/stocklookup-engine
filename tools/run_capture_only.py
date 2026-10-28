"""Foreground capture-only operator. Deployment/execution require separate Owner approval."""
import argparse
from datetime import datetime, time as wall_time
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
import traceback

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from stocklookup_core.evidence.capture_only import (run_capture, check_window, TREE_BYTES, DEADLINE_SECONDS, VN)
from tools.capture_writer_lease import writer_lease


class NativeCapture:
    def __init__(self, root, retained, runtime):
        self.root, self.retained, self.runtime = map(Path, (root, retained, runtime))

    @staticmethod
    def clock():
        return datetime.now(VN)

    def existing(self, session):
        import prospective_pit_capture_retention as store
        path = self.retained / store.STORE / "sessions" / (session + ".json")
        if path.exists():
            return store.verify_complete_session(self.retained, store._read(path))
        return None

    def calendar(self):
        from canonical_daily_operation import _working_dates_probe
        return _working_dates_probe()

    @staticmethod
    def attempt(session, calendar, instant):
        from completed_market_session_gate import evaluate_attempt_eligibility
        return evaluate_attempt_eligibility(requested_at=instant, requested_session=session,
            safety_floor=wall_time(15, 30), working_dates_evidence=calendar, allow_provider_probe=False,
            allow_historical_target_session_acquisition=True)

    def acquire(self, session):
        import daily_session_level2_package as level2
        from canonical_post_close_pipeline import resolve_acquisition_root, assert_post_close_eligible
        import json
        artifact_root, _ = resolve_acquisition_root(self.retained, session, now=self.clock())
        path = level2.ensure_exact_session_snapshot(artifact_root, session, self.runtime,
            workers=12, now=self.clock(), execution_root=self.root)
        self.snapshot_path = Path(path)
        snapshot = json.loads(Path(path).read_bytes())
        assert_post_close_eligible(snapshot, session, now=self.clock(), artifact_root=artifact_root)
        return snapshot

    @staticmethod
    def gate(session, calendar, snapshot, instant):
        from completed_market_session_gate import evaluate_completed_market_session_gate
        return evaluate_completed_market_session_gate(requested_at=instant, requested_session=session,
            safety_floor=wall_time(15, 30), working_dates_evidence=calendar, exact_session_evidence=snapshot,
            allow_provider_probe=False)

    def retain_calendar(self, calendar):
        from prospective_pit_capture_retention import retain_existing_calendar_probe
        return retain_existing_calendar_probe(calendar, root=self.retained)

    def listing(self, session):
        from corporate_currency_rollforward import rollforward
        from prospective_market_evidence_retention import retain_selected_listing_sources
        if self.clock().date().isoformat() != session:
            # The outer window extends overnight, but positive listing presence
            # must have genuine same-session knowledge. Never relabel today's rows.
            from official_corporate_event_incremental_acquisition import verify_successful_acquisition
            verify_successful_acquisition(self.retained, session)
            return retain_selected_listing_sources(self.retained, acquisition_session=session, root=self.retained)
        result = rollforward(self.retained, target_market_session=session, observed_at=self.clock(), allow_acquisition=True)
        selected = result.receipt().get("selected_acquisition_session")
        if not selected:
            raise ValueError("QUALIFIED_LISTING_ACQUISITION_UNAVAILABLE")
        return retain_selected_listing_sources(self.retained, acquisition_session=selected, root=self.retained)

    def market(self, snapshot, session):
        from prospective_market_evidence_retention import retain_market
        return retain_market(snapshot, session=session, root=self.retained)

    def bind(self, snapshot, session, evidence, instant):
        from prospective_pit_capture_retention import retain_capture_bindings
        return retain_capture_bindings(snapshot, session=session, evidence=evidence,
            root=self.retained, created_at=instant.isoformat())

    def complete(self, session, gate, evidence, instant):
        import prospective_pit_capture_retention as store
        result = store.complete_capture_session(self.retained, session=session, gate=gate,
            evidence=evidence, completion_known_at=instant.isoformat(), t0_snapshot_identity=None)
        if result.get("status") in {"RETAINED", "ALREADY_CAPTURED"}:
            store.verify_complete_session(self.retained, store._read(result["path"]))
        return result


def sha(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            value.update(block)
    return value.hexdigest()


def admission(host):
    observations = host.get('observations') or {}
    repo = observations.get('repository') or {}
    reasons = []
    if observations.get('writer_observation') != 'OBSERVED' or repo.get('writer_state_observed') is not True:
        reasons.append('WRITER_STATE_UNKNOWN')
    if observations.get('active_writers') or any(row.get('index_lock_present') for row in repo.get('worktrees') or []):
        reasons.append('CONCURRENT_WRITER_PRESENT')
    if (observations.get('capacity_qualification') or {}).get('source_matches') is not True:
        reasons.append('SOURCE_RECEIPT_MISMATCH')
    for key, floor in [('available_physical_bytes', TREE_BYTES + 1024**3 + 1024**3//4),
                       ('available_commit_bytes', TREE_BYTES + 2*1024**3)]:
        value = observations.get(key)
        if type(value) is not int or value < floor:
            reasons.append(key.upper() + '_LOW')
    return {'admitted': not reasons, 'reasons': reasons, 'tree_bytes': TREE_BYTES,
            'ordinary_daily_qualification': False}


def binding():
    # Active-binding validation explicitly refuses an undeployed worktree and wrong Python.
    from tools.run_owner_daily import bind_active_workspace
    from runtime_paths import workspace_profile, workspace_environment
    bind_active_workspace(ROOT)
    profile = workspace_profile()
    if not profile or profile['paths']['producer'] != ROOT.resolve():
        raise ValueError('CAPTURE_REQUIRES_ACTIVE_PRODUCTION_PROFILE')
    os.environ.update(workspace_environment())
    return profile['paths']


def backup_sources(paths, session, destination):
    """Copy bounded current source families only; immutable history is never rolled back."""
    import daily_session_level2_package as level2
    import official_corporate_event_incremental_acquisition as official
    root = paths['retained']
    targets = level2.session_artifact_paths(root, session)
    selected = [targets[key].parent for key in ('exact_session_snapshot', 'dnse_only_exact_session_snapshot', 'multi_source_market_evidence')]
    selected += [root / official.SESSIONS_RELATIVE / NativeCapture.clock().date().isoformat()]
    files = set()
    for directory in selected:
        if directory.exists():
            if not directory.resolve().is_relative_to(root.resolve()):
                raise ValueError('BACKUP_SOURCE_REDIRECTED')
            files.update(path for path in directory.rglob('*') if path.is_file())
    total = sum(path.stat().st_size for path in files)
    if shutil.disk_usage(root).free < 4*1024**3:
        raise OSError('CAPTURE_RETAINED_DISK_LOW')
    if shutil.disk_usage(destination).free < total + 4*1024**3:
        raise OSError('CAPTURE_BACKUP_DISK_LOW')
    rows = []
    for source in sorted(files):
        if not source.resolve().is_relative_to(root.resolve()):
            raise ValueError('BACKUP_SOURCE_REDIRECTED')
        copy = destination / 'before' / source.relative_to(root)
        copy.parent.mkdir(parents=True, exist_ok=True)
        expected = sha(source)
        shutil.copy2(source, copy)
        if sha(copy) != expected:
            raise ValueError('CAPTURE_BACKUP_HASH_MISMATCH')
        rows.append({'path': str(source), 'backup': str(copy), 'sha256': expected})
    (destination / 'backup.json').write_text(json.dumps(rows, indent=2), encoding='utf-8')


def install_write_scope(retained, directory):
    retained = Path(retained).resolve()
    forbidden = ('prospective-decision-retention-v1', 'prospective-research-cohort-collection-v1',
                 'prospective-decision-outcome-feedback-v1', 'thesis-evidence-t0-v1')
    def allowed(raw):
        path = Path(os.fsdecode(raw)).resolve()
        if path.is_relative_to(directory.resolve()):
            return
        if (not path.is_relative_to(retained) or any(name in path.parts for name in forbidden)
                or path.name.lower().startswith('vn_stock.db')):
            raise PermissionError('CAPTURE_WRITE_SCOPE_REFUSED:' + str(path))
    def audit(event, values):
        if event == 'open' and isinstance(values[0], (str, bytes, os.PathLike)):
            mode = values[1] if len(values) > 1 else ''
            flags = values[2] if len(values) > 2 and isinstance(values[2], int) else 0
            if any(x in str(mode) for x in ('w', 'a', '+')) or flags & (os.O_CREAT | os.O_WRONLY | os.O_RDWR):
                allowed(values[0])
        if event in ('os.remove', 'os.mkdir', 'os.rmdir', 'os.rename', 'os.link'):
            for value in values[:2]:
                if isinstance(value, (str, bytes, os.PathLike)): allowed(value)
    sys.addaudithook(audit)


def worker(session, directory):
    require_capture_job()
    paths = binding()
    registry = ROOT / 'config/daily_research_session_input_registry.json'
    before = sha(registry)
    retained = paths['retained'].resolve()
    install_write_scope(retained, directory)
    try:
        backup_sources(paths, session, directory)
        operation = NativeCapture(ROOT, retained, paths['runtime'])
        result = run_capture(operation, session)
        references = dict(result.get('evidence') or {})
        if hasattr(operation, 'snapshot_path'):
            references['exact_session_snapshot'] = {'path': str(operation.snapshot_path)}
        if result.get('completion'):
            references['completion'] = result['completion']
        result['retained_file_hashes'] = {}
        for name, ref in references.items():
            if isinstance(ref, dict) and ref.get('path'):
                path = Path(ref['path'])
                result['retained_file_hashes'][name] = {'path': str(path), 'sha256': sha(path), 'bytes': path.stat().st_size}
        result['registry_unchanged'] = sha(registry) == before
        if not result['registry_unchanged']:
            raise ValueError('CAPTURE_PROTECTED_REGISTRY_CHANGED')
        from stocklookup_core.acquisition.artifact_io import atomic_write_json
        atomic_write_json(directory / 'child-result.json', result)
        return 0 if result['status'] in {'PASS', 'ALREADY_CAPTURED'} else 1
    except BaseException:
        traceback.print_exc()
        sys.stderr.flush()
        from stocklookup_core.acquisition.artifact_io import atomic_write_json
        atomic_write_json(directory / 'child-result.json', {'status': 'BLOCKED', 'session': session,
            'reason': 'CAPTURE_SOURCE_OR_INTEGRITY_FAILURE', 'traceback': traceback.format_exc(),
            'registry_unchanged': sha(registry) == before, 't0_status': 'UNAVAILABLE',
            'recovery': 'PRESERVE_PARTIAL_RAW_AND_IMMUTABLE_RECEIPTS; DO_NOT_DELETE_OR_REDATE'})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--session', required=True)
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--receipt-dir', type=Path)
    parser.add_argument('--worker', action='store_true', help=argparse.SUPPRESS)
    args = parser.parse_args()
    check_window(args.session, NativeCapture.clock())
    if not args.execute:
        print(json.dumps({'status': 'DEPLOYMENT_AND_EXECUTION_APPROVAL_REQUIRED', 'session': args.session,
            'tree_bytes': TREE_BYTES, 'deadline_seconds': DEADLINE_SECONDS, 'creates_t0': False,
            'writes': 'profile retained evidence source/capture namespaces only; external receipt/backup directory',
            'changes_database_or_registry': False}))
        return 0
    paths = binding()
    directory = args.receipt_dir
    if directory is None or not directory.is_absolute() or any(directory.resolve().is_relative_to(paths[role]) for role in ('producer', 'runtime', 'retained', 'dashboard')):
        raise ValueError('CAPTURE_RECEIPT_MUST_BE_EXTERNAL')
    if args.worker:
        return worker(args.session, directory)
    from tools.check_owner_daily_host_preflight import check, windows_memory
    from stocklookup_core.acquisition.feedback_resource_guard import run_capacity_guarded
    with writer_lease(ROOT):
        host = check(ROOT, paths['retained'])
        admitted = admission(host)
        if not admitted['admitted']:
            print(json.dumps({'status': 'NOT_ADMITTED', 'admission': admitted, 'host': host}))
            return 3
        directory.mkdir(parents=True, exist_ok=False)
        (directory / 'host.json').write_text(json.dumps(host, indent=2), encoding='utf-8')
        started = time.monotonic()
        def probe():
            if time.monotonic() - started >= DEADLINE_SECONDS:
                raise OSError('CAPTURE_DEADLINE_EXCEEDED')
            check_window(args.session, NativeCapture.clock())
            return windows_memory()
        diagnostics = {}
        import uuid
        job_name = 'Global\\StockLookupCapture_' + uuid.uuid4().hex
        try:
            code = run_capacity_guarded([sys.executable, '-B', str(Path(__file__).resolve()), '--execute', '--worker',
                '--session', args.session, '--receipt-dir', str(directory)], cwd=ROOT,
                env={**os.environ, 'PYTHONDONTWRITEBYTECODE': '1', 'STOCKLOOKUP_CAPTURE_JOB': job_name}, memory_probe=probe,
                job_name=job_name,
                tree_ceiling_bytes=TREE_BYTES, on_diagnostics=diagnostics.update,
                stdout_path=directory / 'stdout.log', stderr_path=directory / 'stderr.log')
        finally:
            (directory / 'guard.json').write_text(json.dumps(diagnostics, indent=2), encoding='utf-8')
        print(json.dumps({'status': 'PASS' if code == 0 else 'FAILED', 'receipt_dir': str(directory)}))
        return code


def require_capture_job():
    """The internal worker cannot be used as an uncontained alternate CLI."""
    import ctypes
    from stocklookup_core.acquisition.feedback_resource_guard import _Job
    if os.name != 'nt':
        raise OSError('CAPTURE_WINDOWS_JOB_REQUIRED')
    query = _Job(None)
    handle = None
    try:
        from ctypes import wintypes
        name = os.environ.get('STOCKLOOKUP_CAPTURE_JOB', '')
        if not name.startswith('Global\\StockLookupCapture_'):
            raise OSError('CAPTURE_NAMED_JOB_REQUIRED')
        query.kernel.OpenJobObjectW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        query.kernel.OpenJobObjectW.restype = wintypes.HANDLE
        handle = query.kernel.OpenJobObjectW(4, False, name)
        if not handle:
            raise OSError('CAPTURE_NAMED_JOB_UNAVAILABLE')
        query.kernel.GetCurrentProcess.restype = wintypes.HANDLE
        query.kernel.IsProcessInJob.argtypes = [wintypes.HANDLE, wintypes.HANDLE, ctypes.POINTER(wintypes.BOOL)]
        member = wintypes.BOOL()
        if not query.kernel.IsProcessInJob(query.kernel.GetCurrentProcess(), handle, ctypes.byref(member)) or not member.value:
            raise OSError('CAPTURE_WORKER_NOT_IN_EXPECTED_JOB')
        info = query.EXTENDED()
        if not query.kernel.QueryInformationJobObject(handle, 9, ctypes.byref(info), ctypes.sizeof(info), None):
            raise OSError('CAPTURE_JOB_QUERY_FAILED')
        flags = info.BasicLimitInformation.LimitFlags
        if (info.JobMemoryLimit != TREE_BYTES or info.ProcessMemoryLimit != 7*1024**3
                or flags & 0x2300 != 0x2300 or flags & 0x1800):
            raise OSError('CAPTURE_JOB_LIMITS_NOT_ENFORCED')
    finally:
        if handle:
            query.kernel.CloseHandle(handle)
        query.close()


if __name__ == '__main__':
    raise SystemExit(main())
