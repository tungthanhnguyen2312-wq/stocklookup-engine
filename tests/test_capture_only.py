from datetime import datetime
import json
from pathlib import Path
import subprocess
import sys

import pytest

from stocklookup_core.evidence import capture_only as capture
from tools.run_capture_only import admission, NativeCapture
from tools.capture_writer_lease import writer_lease

DAY = '2026-10-28'
NOW = datetime.fromisoformat(DAY + 'T19:30:00+07:00')


class Ops:
    def __init__(self):
        self.calls=[]
        self.original=None
        self.ready=True
        self.now=NOW
    def clock(self): return self.now
    def existing(self, session): return self.original
    def calendar(self): self.calls.append('calendar'); return {}
    def attempt(self, session, calendar, now): return {'attempt_gate_status':'ATTEMPT_ELIGIBLE','resolved_session':session}
    def acquire(self, session): self.calls.append('acquire'); return {'snapshot_identity':'snapshot:real-fixture'}
    def gate(self, session, calendar, snapshot, now): return {'completion_gate_status':'READY' if self.ready else 'BLOCKED','resolved_session':session}
    def retain_calendar(self, calendar): self.calls.append('retain_calendar'); return {}
    def listing(self, session): self.calls.append('listing'); return {}
    def market(self, snapshot, session): self.calls.append('market'); return {}
    def bind(self, snapshot, session, evidence, now): self.calls.append('bind'); return {}
    def complete(self, session, gate, evidence, now): self.calls.append('complete'); return {'status':'RETAINED'}


def test_capture_excludes_decisions_and_preserves_t0_unavailable():
    ops=Ops()
    result=capture.run_capture(ops,DAY)
    assert result['status']=='PASS' and result['t0_status']=='UNAVAILABLE'
    assert ops.calls==['calendar','acquire','retain_calendar','listing','market','bind','complete']


def test_partial_market_never_completes():
    ops=Ops(); ops.ready=False
    assert capture.run_capture(ops,DAY)['status']=='PARTIAL'
    assert ops.calls==['calendar','acquire']


def test_expiry_refuses_network_but_original_reuse_preserves_identity():
    ops=Ops(); ops.now=datetime.fromisoformat('2026-10-29T09:00:00+07:00')
    with pytest.raises(ValueError,match='WINDOW_CLOSED'): capture.run_capture(ops,DAY)
    assert not ops.calls
    ops.original={'artifact_identity':'original:proof','completion_known_at':NOW.isoformat()}
    assert capture.run_capture(ops,DAY)['completion']==ops.original
    assert not ops.calls


def test_late_listing_cannot_complete(monkeypatch):
    ops=Ops()
    def bind(*args):
        ops.now=datetime.fromisoformat('2026-10-29T09:00:00+07:00')
        return {}
    ops.bind=bind
    with pytest.raises(ValueError,match='WINDOW_CLOSED'): capture.run_capture(ops,DAY)
    assert 'complete' not in ops.calls


def test_genuine_retention_and_completion_without_t0(tmp_path):
    from tests.test_prospective_pit_capture import snapshot
    import prospective_market_evidence_retention as retained
    import prospective_pit_capture_retention as store
    import prospective_market_snapshot_contract as market
    import prospective_pit_capture as core
    class Fixtures(NativeCapture):
        @staticmethod
        def clock(): return NOW
        def calendar(self): return {'workingDates':[DAY],'raw_bytes':market.canonical({'workingDates':[DAY]}),'retrieved_at':DAY+'T04:00:00Z'}
        def acquire(self, session): return snapshot(session)
        def listing(self, session):
            value=core.identified({'contract_version':retained.CONTRACT_VERSION,'source_identity':'fixture:official',
                'records':[{'source_observation':{'ticker':'AAA','exchange_or_market':'HOSE','official_source':'hose_public_stock_master/v1',
                    'official_source_row_identity':'row:AAA','official_observed_at':DAY+'T02:00:00Z'}}]},'prospective_universe_observations')
            path=tmp_path/'listing-source.json'; path.write_bytes(market.canonical(value))
            # Same source contract fallback as the existing Daily capture boundary.
            return {'path':str(path),'artifact_identity':value['artifact_identity']}
        def bind(self, snapshot, session, evidence, instant):
            evidence['universe']=evidence.pop('listing_sources')
            return super().bind(snapshot,session,evidence,instant)
    ops=Fixtures(tmp_path,tmp_path,tmp_path/'read-only-runtime')
    result=capture.run_capture(ops,DAY)
    assert result['status']=='PASS'
    path=Path(result['completion']['path'])
    original=path.read_bytes()
    value=json.loads(original)
    assert value['session']==DAY and value['t0_decision_snapshot_identity'] is None
    assert value['completion_known_at']==NOW.isoformat()
    assert store.verify_complete_session(tmp_path,value)
    assert capture.run_capture(ops,DAY)['status']=='ALREADY_CAPTURED'
    assert path.read_bytes()==original
    assert not (tmp_path/'operations-review/prospective-decision-retention-v1').exists()


def test_admission_keeps_reserves_writer_and_receipt_guards():
    physical=capture.TREE_BYTES+1024**3+1024**3//4
    commit=capture.TREE_BYTES+2*1024**3
    host={'observations':{'available_physical_bytes':physical,'available_commit_bytes':commit,
        'writer_observation':'OBSERVED','active_writers':[],'repository':{'writer_state_observed':True,'worktrees':[]},
        'capacity_qualification':{'source_matches':True}}}
    assert admission(host)['admitted']
    for key,value in [('available_physical_bytes',physical-1),('available_commit_bytes',commit-1),('writer_observation','UNKNOWN'),('active_writers',[{'pid':1}])]:
        old=host['observations'][key]; host['observations'][key]=value
        assert not admission(host)['admitted']
        host['observations'][key]=old


def test_kernel_writer_lease_excludes_another_process_and_releases(tmp_path):
    code='from tools.capture_writer_lease import writer_lease;from pathlib import Path;import sys\nwith writer_lease(Path(sys.argv[1])): print("acquired")'
    with writer_lease(tmp_path):
        result=subprocess.run([sys.executable,'-B','-c',code,str(tmp_path)],capture_output=True,text=True)
        assert result.returncode!=0
    assert subprocess.run([sys.executable,'-B','-c',code,str(tmp_path)],capture_output=True).returncode==0


def test_worker_refuses_uncontained_entry():
    code='from tools.run_capture_only import require_capture_job;require_capture_job()'
    result=subprocess.run([sys.executable,'-B','-c',code],capture_output=True,text=True)
    assert result.returncode!=0 and 'CAPTURE_' in result.stderr


@pytest.mark.skipif(sys.platform!='win32', reason='Windows Job enforcement')
def test_worker_requires_the_real_constrained_job_and_tree_is_reaped(tmp_path):
    # A fresh controller keeps the real 0.25-GiB Owner allowance intact even
    # when the pytest process has imported large historical fixture modules.
    code = r"""
import json,os,sys,uuid
from pathlib import Path
from stocklookup_core.acquisition.feedback_resource_guard import run_capacity_guarded
from stocklookup_core.evidence.capture_only import TREE_BYTES
from tools.check_owner_daily_host_preflight import windows_memory
out=Path(sys.argv[1]); name='Global\\StockLookupCapture_'+uuid.uuid4().hex
command=[sys.executable,'-B','-c','from tools.run_capture_only import require_capture_job;require_capture_job();print("constrained")']
diag={}
rc=run_capacity_guarded(command,cwd=Path.cwd(),env={**os.environ,'STOCKLOOKUP_CAPTURE_JOB':name},job_name=name,
    memory_probe=windows_memory,tree_ceiling_bytes=TREE_BYTES,on_diagnostics=diag.update,
    stdout_path=out/'out',stderr_path=out/'err')
(out/'diagnostics.json').write_text(json.dumps(diag))
raise SystemExit(rc)
"""
    result=subprocess.run([sys.executable,'-B','-c',code,str(tmp_path)],capture_output=True,text=True)
    assert result.returncode==0, result.stderr + (tmp_path/'err').read_text() if (tmp_path/'err').exists() else result.stderr
    diagnostics=json.loads((tmp_path/'diagnostics.json').read_text())
    assert (tmp_path/'out').read_text().strip()=='constrained'
    assert diagnostics['job_memory_limit_bytes']==capture.TREE_BYTES
    assert diagnostics['tree_termination_confirmed'] and diagnostics['immediate_child_reaped']


def test_atomic_retention_failure_does_not_publish_or_destroy_originals(tmp_path,monkeypatch):
    import stocklookup_core.acquisition.artifact_io as io
    target=tmp_path/'record.json'
    original=tmp_path/'original'; original.write_bytes(b'protected')
    real=io.os.link
    monkeypatch.setattr(io.os,'link',lambda *args: (_ for _ in ()).throw(OSError('fixture-publication-failure')))
    with pytest.raises(OSError): io.retain_immutable_bytes(target,b'complete')
    assert not target.exists() and not list(tmp_path.glob('.immutable-*'))
    assert original.read_bytes()==b'protected'
    monkeypatch.setattr(io.os,'link',real)
    assert io.retain_immutable_bytes(target,b'complete') is False
    assert io.retain_immutable_bytes(target,b'complete') is True
    with pytest.raises(io.AtomicWriteError): io.retain_immutable_bytes(target,b'conflict')


def test_native_route_has_no_heavy_stage_calls():
    import inspect
    source=inspect.getsource(NativeCapture)
    for name in ['run_canonical_daily_operation(', 'build_enrichment_components(', 'run_daily_producer(',
                 'retain_prospective_decision_snapshot(', 'register_session_inputs(', 'materialize_independent_components(']:
        assert name not in source


def test_snapshot_bytes_and_immutable_atomic_publication(tmp_path,monkeypatch):
    import os
    import mva_exact_session_snapshot as snapshotter
    import stocklookup_core.acquisition.artifact_io as io
    path=tmp_path/'snapshot.json'
    value={'session':DAY,'records':{'AAA':{'close':42}}}
    expected=(json.dumps(value,ensure_ascii=False,sort_keys=True,indent=2)+'\n').replace('\n',os.linesep).encode('utf-8')
    real=io.os.link
    monkeypatch.setattr(io.os,'link',lambda *args: (_ for _ in ()).throw(OSError('fixture-interruption')))
    with pytest.raises(OSError): snapshotter.write_snapshot(value,path)
    assert not path.exists()
    monkeypatch.setattr(io.os,'link',real)
    snapshotter.write_snapshot(value,path)
    assert path.read_bytes()==expected
    with pytest.raises(FileExistsError): snapshotter.write_snapshot(value,path)


def test_native_acquisition_uses_the_qualified_snapshot_boundary_only(tmp_path,monkeypatch):
    import daily_session_level2_package as level2
    import canonical_post_close_pipeline as pipeline
    calls=[]
    target=tmp_path/'snapshot.json'
    target.write_text(json.dumps({'snapshot_identity':'snapshot:fixture'}))
    monkeypatch.setattr(pipeline,'resolve_acquisition_root',lambda *args,**kwargs:(tmp_path,{}))
    def acquire(*args,**kwargs): calls.append('qualified-acquisition'); return target
    def qualify(*args,**kwargs): calls.append('post-close-and-quality-check')
    def excluded(*args,**kwargs): raise AssertionError('heavy Daily stage invoked')
    monkeypatch.setattr(level2,'ensure_exact_session_snapshot',acquire)
    monkeypatch.setattr(pipeline,'assert_post_close_eligible',qualify)
    monkeypatch.setattr(pipeline,'build_enrichment_components',excluded)
    monkeypatch.setattr(level2,'materialize_independent_components',excluded)
    assert NativeCapture(tmp_path,tmp_path,tmp_path).acquire(DAY)['snapshot_identity']=='snapshot:fixture'
    assert calls==['qualified-acquisition','post-close-and-quality-check']


def test_describe_does_not_execute_or_require_live_credentials(monkeypatch,capsys):
    import tools.run_capture_only as operator
    monkeypatch.setattr(operator.NativeCapture,'clock',staticmethod(lambda:NOW))
    monkeypatch.setattr(operator,'binding',lambda:(_ for _ in ()).throw(AssertionError('describe must not bind or acquire')))
    monkeypatch.setattr(sys,'argv',['run_capture_only.py','--session',DAY])
    assert operator.main()==0
    assert json.loads(capsys.readouterr().out)['status']=='DEPLOYMENT_AND_EXECUTION_APPROVAL_REQUIRED'


def test_overnight_listing_requires_original_session_receipts(tmp_path,monkeypatch):
    import official_corporate_event_incremental_acquisition as acquisition
    import prospective_market_evidence_retention as retained
    import corporate_currency_rollforward as rollforward
    seen=[]
    class Overnight(NativeCapture):
        @staticmethod
        def clock(): return datetime.fromisoformat('2026-10-29T08:00:00+07:00')
    monkeypatch.setattr(rollforward,'rollforward',lambda *a,**kw: (_ for _ in ()).throw(AssertionError('must not acquire later listing')))
    monkeypatch.setattr(acquisition,'verify_successful_acquisition',lambda root,day: seen.append(day))
    monkeypatch.setattr(retained,'retain_selected_listing_sources',lambda retained_root,**kw: {'selected':kw['acquisition_session']})
    assert Overnight(tmp_path,tmp_path,tmp_path).listing(DAY)=={'selected':DAY}
    assert seen==[DAY]


def test_candidate_database_reads_leave_original_bytes_unchanged(tmp_path):
    import sqlite3
    from mva_exact_session_snapshot import canonical_candidates
    from multi_source_exact_session_resolver import read_candidate_metadata
    database=tmp_path/'vn_stock.db'
    with sqlite3.connect(database) as connection:
        connection.execute('CREATE TABLE metadata(ticker TEXT, exchange TEXT, market_cap REAL)')
        connection.execute("INSERT INTO metadata VALUES ('AAA','HOSE',100)")
    before=database.read_bytes()
    assert canonical_candidates(tmp_path)==['AAA']
    assert read_candidate_metadata(tmp_path)['AAA']['exchange']=='HOSE'
    assert database.read_bytes()==before


def test_worker_write_scope_refuses_protected_and_decision_paths(tmp_path):
    code=r'''
from pathlib import Path
import sys
from tools.run_capture_only import install_write_scope
root=Path(sys.argv[1]); retained=root/'retained'; receipts=root/'receipts'
retained.mkdir(); receipts.mkdir()
protected=root/'registry.json'; protected.write_bytes(b'original')
install_write_scope(retained,receipts)
(retained/'real-source-receipt.json').write_bytes(b'evidence')
(receipts/'backup.json').write_bytes(b'backup')
for path in [protected,retained/'vn_stock.db',retained/'operations-review/prospective-decision-retention-v1/t0.json',
             retained/'operations-review/prospective-research-cohort-collection-v1/cohort.json']:
    try:
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_bytes(b'forbidden')
    except PermissionError:
        continue
    raise AssertionError('scope did not refuse '+str(path))
assert protected.read_bytes()==b'original'
'''
    result=subprocess.run([sys.executable,'-B','-c',code,str(tmp_path)],capture_output=True,text=True)
    assert result.returncode==0,result.stderr


@pytest.mark.parametrize('disk_ok',[True,False])
def test_source_backup_is_bounded_and_hash_verified(tmp_path,monkeypatch,disk_ok):
    from tools.run_capture_only import backup_sources,sha
    import daily_session_level2_package as level2
    retained=tmp_path/'retained'; current=retained/'current-session'; current.mkdir(parents=True)
    original=current/'snapshot.json'; original.write_bytes(b'original-qualified-input')
    historical=retained/'older-session'; historical.mkdir(); (historical/'original').write_bytes(b'untouched')
    receipts=tmp_path/'receipts'; receipts.mkdir()
    monkeypatch.setattr(level2,'session_artifact_paths',lambda root,session:{
        key:current/'snapshot.json' for key in ('exact_session_snapshot','dnse_only_exact_session_snapshot','multi_source_market_evidence')})
    monkeypatch.setattr(NativeCapture,'clock',staticmethod(lambda:NOW))
    if not disk_ok:
        import shutil
        from types import SimpleNamespace
        monkeypatch.setattr(shutil,'disk_usage',lambda path:SimpleNamespace(free=0))
        with pytest.raises(OSError,match='RETAINED_DISK_LOW'):
            backup_sources({'retained':retained},DAY,receipts)
        assert not (receipts/'backup.json').exists()
        assert original.read_bytes()==b'original-qualified-input'
        return
    backup_sources({'retained':retained},DAY,receipts)
    rows=json.loads((receipts/'backup.json').read_bytes())
    assert len(rows)==1 and rows[0]['path']==str(original)
    assert sha(Path(rows[0]['backup']))==rows[0]['sha256']==sha(original)
    assert not (receipts/'before/older-session').exists()
    # A later adapter failure leaves the verified backup and prior original intact.
    assert original.read_bytes()==b'original-qualified-input'
