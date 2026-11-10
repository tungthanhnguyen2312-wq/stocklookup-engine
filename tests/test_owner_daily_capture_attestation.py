"""Owner Daily states whether the session entered the capture chain; PASS is never silent about it."""
import json
import os
from pathlib import Path
import subprocess
import sys

import pytest

from test_owner_daily_launcher import FIXTURE, LAUNCHER, POWERSHELL, windows_powershell

SESSION = "2026-09-24"  # the session the shared "pass" fixture reports


def _host():
    sys.path.insert(0, str(LAUNCHER.parent))
    try:
        import owner_daily_host
    finally:
        sys.path.remove(str(LAUNCHER.parent))
    return owner_daily_host


def _record(root: Path, day: str, **fields) -> Path:
    path = root / "operations-review/prospective-pit-capture-v1/sessions" / (day + ".json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"contract_version": "prospective_capture_complete_session/v1", "session": day,
                                "completion_known_at": day + "T15:41:00+07:00", "artifact_identity": "capture:x",
                                "t0_decision_snapshot_identity": None, **fields}), encoding="utf-8")
    return path


def test_attestation_reads_the_record_and_never_writes(tmp_path):
    host = _host()
    assert host.pit_capture_attestation(str(tmp_path), SESSION)["status"] == "MISSING"
    assert not list(tmp_path.iterdir())
    path = _record(tmp_path, SESSION)
    before = path.read_bytes()
    found = host.pit_capture_attestation(str(tmp_path), SESSION)
    assert found["status"] == "COMPLETE" and found["t0_binding"] == "CAPTURE_ONLY_ORIGIN"
    assert found["completion_known_at"] == SESSION + "T15:41:00+07:00" and path.read_bytes() == before
    _record(tmp_path, SESSION, t0_decision_snapshot_identity="prospective_decision_snapshot:y")
    assert host.pit_capture_attestation(str(tmp_path), SESSION)["t0_binding"] == "BOUND_BY_DAILY"


@pytest.mark.parametrize("damage", ["other_session", "other_contract", "not_json", "not_object"])
def test_a_record_that_is_not_this_sessions_capture_is_not_complete(tmp_path, damage):
    path = _record(tmp_path, SESSION)
    if damage == "other_session":
        _record(tmp_path, SESSION, session="2026-09-23")
    elif damage == "other_contract":
        _record(tmp_path, SESSION, contract_version="something/else")
    elif damage == "not_json":
        path.write_text("{", encoding="utf-8")
    else:
        path.write_text("[]", encoding="utf-8")
    assert _host().pit_capture_attestation(str(tmp_path), SESSION)["status"] == "UNREADABLE"


def _launch(tmp_path: Path, capture_root: Path | None):
    entry = tmp_path / "fixture_pass.py"
    entry.write_text(FIXTURE.replace("MODE", repr("pass")).replace("REPO_ROOT", repr(str(LAUNCHER.parent.parent))), encoding="utf-8")
    logs = tmp_path / "logs"
    environment = {k: v for k, v in os.environ.items() if k != "STOCK_LOOKUP_PIT_CAPTURE_ROOT"}
    if capture_root is not None:
        environment["STOCK_LOOKUP_PIT_CAPTURE_ROOT"] = str(capture_root)
    completed = subprocess.run(
        [POWERSHELL, "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(LAUNCHER),
         "-EntryScript", str(entry), "-LogDirectory", str(logs), "-NoPause", "-Diagnostic"],
        capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=180, env=environment)
    return completed, json.loads(next(logs.glob("*.result.json")).read_text(encoding="utf-8"))


@windows_powershell
def test_pass_without_a_capture_record_is_reported_partial(tmp_path):
    completed, result = _launch(tmp_path, tmp_path / "evidence")
    assert completed.returncode == 1, completed.stdout + completed.stderr
    assert result["status"] == "PARTIAL" and result["reason"] == "PIT_CAPTURE_NOT_COMPLETE"
    assert result["pit_capture"]["status"] == "MISSING" and result["daily_status"] == "COMPLETED"
    assert "PIT_CAPTURE_NOT_COMPLETE" in completed.stdout and "Trạng thái: PASS" not in completed.stdout


@windows_powershell
def test_pass_with_a_capture_record_stays_pass_and_says_so(tmp_path):
    _record(tmp_path / "evidence", SESSION)
    completed, result = _launch(tmp_path, tmp_path / "evidence")
    assert completed.returncode == 0, completed.stdout + completed.stderr
    assert result["status"] == "PASS" and result["pit_capture"]["status"] == "COMPLETE"
    assert "Capture PIT: XONG" in completed.stdout


@windows_powershell
def test_entry_seam_without_an_evidence_root_is_left_untouched(tmp_path):
    completed, result = _launch(tmp_path, None)
    assert completed.returncode == 0 and result == {"status": "PASS", "session": SESSION, "daily_status": "COMPLETED"}
