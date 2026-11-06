import argparse
import json
import subprocess

import pytest

from stocklookup_core.evidence.field_identity import stable_id
from stocklookup_core.tactical import current_session_candlestick_projection as projection
from tests.test_current_session_candlestick_projection import engulfing_series, flat_series, SESSION
from tools import post_daily_candlestick_release as tool

GIB = 1024 ** 3


def real_snapshot(records):
    snap = {"contract_version": projection.SOURCE_CONTRACT, "target_session": SESSION,
            "resolved_completed_session": SESSION, "retained_snapshot_session": SESSION,
            "records": {t: {"observations": o} for t, o in records.items()}}
    digest = stable_id(snap)
    snap["snapshot_sha256"] = digest
    snap["snapshot_identity"] = f"p3f9_exact_session_snapshot:{digest}"
    return snap


@pytest.fixture()
def world(tmp_path, monkeypatch):
    producer = tmp_path / "producer"
    retained = tmp_path / "retained-evidence"
    runtime = tmp_path / "runtime"
    web = tmp_path / "web"
    for p in (producer, runtime / "data", web / "data"):
        p.mkdir(parents=True)
    snap = real_snapshot({"ENG": engulfing_series(), "FLAT": flat_series(), "OLD": flat_series(end="2026-11-04")})
    snap_path = tool.default_snapshot_path(retained, SESSION)
    snap_path.parent.mkdir(parents=True)
    snap_path.write_text(json.dumps(snap), encoding="utf-8")
    op = retained / "operations-review/canonical-daily-operation-v1" / SESSION / "op-1/daily_operation_record.json"
    op.parent.mkdir(parents=True)
    op.write_text(json.dumps({"session": SESSION, "daily_producer_status": "COMPLETED", "operation_identity": "op:1",
                              "acquisition": {"snapshot_identity": snap["snapshot_identity"]}}), encoding="utf-8")
    registry = {"completed_sessions": {SESSION: {"status": tool.COMPLETED}}}

    def fake_git(*args):
        if args[0] == "rev-parse":
            return b"abc\n"
        return json.dumps(registry).encode()

    monkeypatch.setattr(tool, "committed_session",
                        lambda root, session, git=None: _ORIGINAL_COMMITTED(root, session, git=fake_git))
    (web / "data/build_info.json").write_text(json.dumps({"market_session": SESSION}))
    sessions = {"runtime": SESSION}
    # Runtime session comes from the publisher's own release_session_contract (covered by its
    # suite); here only the web half is read from disk.
    monkeypatch.setattr(tool, "release_sessions", lambda runtime_root, web_dir: {
        "runtime": sessions["runtime"],
        "web": json.loads((web_dir / "data/build_info.json").read_text()).get("market_session")})
    (runtime / "data" / tool.SIDECAR_JSON).write_text('{"scan_date":"2026-08-25"}')
    (runtime / "data" / tool.SIDECAR_JS).write_text('window.CANDLESTICK_PATTERNS = {"scan_date":"2026-08-25"};\n')
    return dict(tmp=tmp_path, producer=producer, retained=retained, runtime=runtime, web=web, snap=snap,
                snap_path=snap_path, registry=registry, op=op, sessions=sessions)


_ORIGINAL_COMMITTED = tool.committed_session


def args(w, **extra):
    base = dict(session=SESSION, source_identity=w["snap"]["snapshot_identity"],
                checkpoint_root=str(w["tmp"] / "ckpt"), producer_root=str(w["producer"]),
                retained_root=str(w["retained"]), snapshot=None, runtime_root=str(w["runtime"]),
                web_dir=str(w["web"]), workers=1, min_free_ram_gib=1.0, min_free_disk_gib=0.0,
                stage=False, publish=False, complete_publication=False, rollback=False)
    base.update(extra)
    return argparse.Namespace(**base)


def go(w, publisher=None, rows=lambda: [], ram=lambda: 8 * GIB, **extra):
    return tool.run(args(w, **extra), publisher=publisher, observe_rows=rows, observe_ram=ram)


def test_build_verifies_source_and_is_idempotent(world):
    code, receipt = go(world)
    assert code == tool.EXIT_OK and receipt["status"] == "BUILT", receipt
    cov = receipt["checkpoint"]["coverage"]
    assert cov["candidate_count"] == 3 and cov["scanned_count"] == 2 and cov["exclusion_reasons"]["NO_EXACT_SESSION_BAR"] == 1
    code, again = go(world)
    assert code == tool.EXIT_OK and again["status"] == "REUSED"
    assert again["checkpoint"]["json_sha256"] == receipt["checkpoint"]["json_sha256"]
    # runtime/web untouched by a build-only run
    assert "2026-08-25" in (world["runtime"] / "data" / tool.SIDECAR_JSON).read_text()


def test_skip_on_resources_and_writers_without_any_write(world):
    code, r = go(world, ram=lambda: 1 * GIB, min_free_ram_gib=2.5)
    assert code == tool.EXIT_SKIP and r["reason"].startswith("FREE_RAM_BELOW_BOUND")
    code, r = go(world, rows=lambda: [(4242, "python.exe tools/run_owner_daily.py --live")])
    assert code == tool.EXIT_SKIP and r["reason"].startswith("CONCURRENT_DAILY_OR_RELEASE_WRITER")
    code, r = go(world, rows=lambda: None)
    assert code == tool.EXIT_SKIP and r["reason"] == "WRITER_STATE_UNOBSERVABLE"
    assert not tool.checkpoint_dir(world["tmp"] / "ckpt", SESSION, world["snap"]["snapshot_identity"]).exists()


def test_checkpoint_from_other_engine_code_is_not_reused(world, monkeypatch):
    code, first = go(world)
    assert first["status"] == "BUILT"
    monkeypatch.setattr(tool, "code_digest", lambda: "f" * 64)
    code, second = go(world)
    assert code == tool.EXIT_OK and second["status"] == "BUILT" and second["code_digest"] == "f" * 64


def test_refuses_uncommitted_session_mismatched_identity_and_tampered_snapshot(world):
    world["registry"]["completed_sessions"].pop(SESSION)
    assert go(world)[1]["reason"] == "SESSION_NOT_COMMITTED_COMPLETED"
    world["registry"]["completed_sessions"][SESSION] = {"status": tool.COMPLETED}
    code, r = go(world, source_identity="p3f9_exact_session_snapshot:" + "0" * 64)
    assert code == tool.EXIT_REFUSED and r["reason"] == "SOURCE_IDENTITY_NOT_BOUND_BY_SESSION_OPERATION_RECORD"
    tampered = dict(world["snap"])
    tampered["records"] = dict(tampered["records"], FLAT={"observations": flat_series()[:-1]})
    world["snap_path"].write_text(json.dumps(tampered), encoding="utf-8")
    code, r = go(world)
    assert code == tool.EXIT_REFUSED and r["reason"] == "SOURCE_SNAPSHOT_CONTENT_IDENTITY_MISMATCH"


def test_refuses_wrong_session_snapshot(world):
    snap = dict(world["snap"], retained_snapshot_session="2026-11-04")
    world["snap_path"].write_text(json.dumps(snap), encoding="utf-8")
    code, r = go(world)
    assert code == tool.EXIT_REFUSED and r["reason"].startswith("SOURCE_SESSION_MISMATCH")


def test_schema_tampering_of_checkpoint_is_rebuilt_and_verify_refuses_tamper(world):
    code, r = go(world)
    ckpt = tool.checkpoint_dir(world["tmp"] / "ckpt", SESSION, world["snap"]["snapshot_identity"])
    payload = json.loads((ckpt / tool.SIDECAR_JSON).read_text(encoding="utf-8"))
    payload["coverage"]["scanned_count"] += 1
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    (ckpt / tool.SIDECAR_JSON).write_text(text, encoding="utf-8")
    (ckpt / tool.SIDECAR_JS).write_text(tool.JS_PREFIX + text + ";\n", encoding="utf-8")
    with pytest.raises(tool.Refused, match="SIDECAR_NOT_CURRENT"):
        tool.verify_sidecar(ckpt, SESSION, world["snap"]["snapshot_identity"])
    (ckpt / tool.SIDECAR_JS).write_text("window.CANDLESTICK_PATTERNS = {};\n", encoding="utf-8")
    with pytest.raises(tool.Refused, match="PARITY"):
        tool.verify_sidecar(ckpt, SESSION, world["snap"]["snapshot_identity"])
    code, again = go(world)
    assert code == tool.EXIT_OK and again["status"] == "BUILT"  # torn checkpoint rebuilt, never reused


def _fake_publisher(world, *, fail=False, wrong_identity=False):
    def publish(producer_root, runtime_root, web_dir, session, complete):
        if fail:
            return {"status": "FAILED", "reason": "SMOKE"}
        src = runtime_root / "data" / tool.SIDECAR_JSON
        (web_dir / "data" / tool.SIDECAR_JSON).write_bytes(src.read_bytes())
        payload = json.loads(src.read_text(encoding="utf-8"))
        comp = projection.component_state(payload, session)
        if wrong_identity:
            comp = dict(comp, projection_identity="x")
        info = {"market_session": session, "domains": {"signals": {"status": comp["status"],
                                                                   "components": {"candlestick_patterns": comp}}}}
        (web_dir / "data/build_info.json").write_text(json.dumps(info))
        return {"status": "LOCAL_PUBLISHED"}
    return publish


def test_publish_success_then_rollback_restores_previous_pair(world):
    before = (world["runtime"] / "data" / tool.SIDECAR_JSON).read_bytes()
    code, r = go(world, publisher=_fake_publisher(world), publish=True)
    assert code == tool.EXIT_OK and r["status"] == "PUBLISHED_LOCAL", r
    assert (world["web"] / "data" / tool.SIDECAR_JSON).read_bytes() == \
        (world["runtime"] / "data" / tool.SIDECAR_JSON).read_bytes() != before
    code, rb = go(world, rollback=True)
    assert code == tool.EXIT_OK and rb["status"] == "ROLLED_BACK"
    assert (world["runtime"] / "data" / tool.SIDECAR_JSON).read_bytes() == before


def test_failed_publication_rolls_runtime_back(world):
    before = (world["runtime"] / "data" / tool.SIDECAR_JS).read_bytes()
    code, r = go(world, publisher=_fake_publisher(world, fail=True), publish=True)
    assert code == tool.EXIT_FAILED and r["status"] == "PUBLISH_FAILED_RUNTIME_ROLLED_BACK"
    assert (world["runtime"] / "data" / tool.SIDECAR_JS).read_bytes() == before


def test_released_but_unverified_publication_is_rolled_back_and_republished(world):
    before = (world["runtime"] / "data" / tool.SIDECAR_JSON).read_bytes()
    calls = []
    bad, good = _fake_publisher(world, wrong_identity=True), _fake_publisher(world)

    def publisher(*a):
        calls.append(a)
        return (bad if len(calls) == 1 else good)(*a)
    code, r = go(world, publisher=publisher, publish=True)
    assert code == tool.EXIT_FAILED and r["status"] == "PUBLISH_FAILED_ROLLED_BACK_AND_REPUBLISHED"
    assert len(calls) == 2
    assert (world["runtime"] / "data" / tool.SIDECAR_JSON).read_bytes() == before
    assert (world["web"] / "data" / tool.SIDECAR_JSON).read_bytes() == before


def test_refuses_publish_when_workspace_release_is_other_session(world):
    (world["web"] / "data/build_info.json").write_text(json.dumps({"market_session": "2026-11-04"}))
    called = []
    code, r = go(world, publisher=lambda *a: called.append(a) or {"status": "PUBLISHED"}, publish=True)
    assert code == tool.EXIT_REFUSED and r["reason"] == "WORKSPACE_RELEASE_SESSION_MISMATCH" and not called
    assert "2026-08-25" in (world["runtime"] / "data" / tool.SIDECAR_JSON).read_text()


def test_refuses_publish_when_runtime_release_is_other_session(world):
    world["sessions"]["runtime"] = "2026-11-04"
    code, r = go(world, publisher=lambda *a: {"status": "PUBLISHED"}, publish=True)
    assert code == tool.EXIT_REFUSED and r["reason"] == "WORKSPACE_RELEASE_SESSION_MISMATCH"


def test_instance_lock_skips_second_run(world):
    root = world["tmp"] / "ckpt"
    with tool.instance_lock(root):
        code, r = go(world)
    assert code == tool.EXIT_SKIP and r["reason"].startswith("INSTANCE_LOCK_HELD")


def test_active_writer_matching_ignores_self_and_non_python():
    rows = [(1, "python tools/post_daily_candlestick_release.py"), (2, "notepad run_owner_daily.py"),
            (3, "C:/py/python.exe -u tools/release_orchestrator.py all --live")]
    assert tool.active_writers(rows, own_pid=99) == ["3:release_orchestrator.py"]


def test_cli_refuses_unbounded_workers(capsys):
    assert tool.main(["--session", SESSION, "--source-identity", "x", "--checkpoint-root", ".", "--workers", "4"]) == tool.EXIT_REFUSED


def test_committed_session_reads_head_blob_not_working_tree(tmp_path):
    calls = []

    def git(*a):
        calls.append(a)
        if a[0] == "rev-parse":
            return b"deadbeef\n"
        raise subprocess.CalledProcessError(1, "git")
    with pytest.raises(tool.Refused, match="COMMITTED_REGISTRY_UNREADABLE"):
        _ORIGINAL_COMMITTED(tmp_path, SESSION, git=git)
    assert calls[1] == ("show", f"deadbeef:{tool.REGISTRY}")
