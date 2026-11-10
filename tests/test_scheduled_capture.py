"""Scheduled same-day capture: when to attempt, how often, and what is recorded."""
from datetime import datetime, timedelta
import json
from pathlib import Path
import sys

import pytest

from stocklookup_core.evidence.capture_only import VN
from tools import run_scheduled_capture as scheduled

DAY = "2026-11-11"  # Wednesday
LAUNCHER = Path(scheduled.__file__).with_suffix(".cmd")


class Clock:
    def __init__(self, text):
        self.now = datetime.fromisoformat(text).replace(tzinfo=VN)
        self.slept = []

    def __call__(self):
        return self.now

    def sleep(self, seconds):
        self.slept.append(seconds)
        self.now += timedelta(seconds=seconds)


def _run(tmp_path, clock, outcomes, **kwargs):
    retained, calls = tmp_path / "retained", []

    def child(python, session, directory, timeout):
        calls.append(directory.name)
        outcome = outcomes[min(len(calls), len(outcomes)) - 1]
        if outcome == "PASS":
            target = scheduled.record_path(retained, session)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("{}")
            return 0, {"status": "PASS"}, "", ""
        if outcome == "DAILY_CAPTURES":  # Owner Daily holds the lease and completes the capture itself
            target = scheduled.record_path(retained, session)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text("{}")
            return 1, None, "", "BlockingIOError: FEEDBACK_PUBLICATION_BUSY"
        return outcome

    status = scheduled.run(DAY, retained=retained, logs=tmp_path / "logs", receipts=tmp_path / "receipts",
                           python=sys.executable, clock=clock, sleep=clock.sleep, child=child, **kwargs)
    written = json.loads((tmp_path / "logs" / f"pit_capture_{DAY}.status.json").read_text(encoding="utf-8"))
    assert written == status and not list((tmp_path / "logs").glob("*.tmp"))
    return status, calls


def test_first_attempt_waits_for_the_safety_floor_then_captures_once(tmp_path):
    clock = Clock(DAY + "T15:20:00")
    status, calls = _run(tmp_path, clock, ["PASS"], readiness=lambda day: {"status": "DEPTH_PENDING"})
    assert status["state"] == scheduled.CAPTURED and len(calls) == 1
    assert status["attempts"][0]["started_at"] >= DAY + "T15:35:00"
    assert status["readiness"] == {"status": "DEPTH_PENDING"} and status["capture_record"]["path"].endswith(DAY + ".json")


def test_existing_record_ends_the_run_without_any_child(tmp_path):
    target = scheduled.record_path(tmp_path / "retained", DAY)
    target.parent.mkdir(parents=True)
    target.write_text("{}")
    status, calls = _run(tmp_path, Clock(DAY + "T16:00:00"), ["PASS"])
    assert status["state"] == scheduled.ALREADY_CAPTURED and calls == [] and status["attempts"] == []


def test_refused_admission_and_busy_lease_are_retried_within_bounds(tmp_path):
    clock = Clock(DAY + "T15:40:00")
    refused = (3, None, '{"status": "NOT_ADMITTED"}', "")
    busy = (1, None, "", "BlockingIOError: FEEDBACK_PUBLICATION_BUSY")
    status, calls = _run(tmp_path, clock, [refused, busy, "PASS"])
    assert [a["outcome"] for a in status["attempts"]] == ["NOT_ADMITTED", "WRITER_LEASE_BUSY", scheduled.CAPTURED]
    assert clock.slept == [scheduled.INTERVAL_SECONDS] * 2 and len(set(calls)) == 3


def test_attempts_are_finite_and_exhaustion_is_reported_not_hidden(tmp_path):
    clock = Clock(DAY + "T15:40:00")
    status, calls = _run(tmp_path, clock, [(3, None, "NOT_ADMITTED", "")], max_attempts=3)
    assert status["state"] == scheduled.EXHAUSTED and len(calls) == 3 and status["capture_record"] is None


def test_no_attempt_after_the_same_day_cutoff(tmp_path):
    late, calls = _run(tmp_path, Clock(DAY + "T23:31:00"), ["PASS"])
    assert late["state"] == scheduled.WINDOW_CLOSED and calls == []
    clock = Clock(DAY + "T23:10:00")
    status, calls = _run(tmp_path, clock, [(3, None, "NOT_ADMITTED", "")], interval=900)
    assert status["state"] == scheduled.WINDOW_CLOSED and len(calls) == 2
    assert clock.now < datetime.fromisoformat(DAY + "T23:59:00").replace(tzinfo=VN)


def test_daily_capturing_while_the_scheduler_waits_counts_as_captured(tmp_path):
    status, calls = _run(tmp_path, Clock(DAY + "T15:40:00"), ["DAILY_CAPTURES"], max_attempts=1)
    assert status["state"] == scheduled.ALREADY_CAPTURED and len(calls) == 1


def test_non_sessions_never_acquire(tmp_path):
    retained = tmp_path / "retained"
    weekend = scheduled.run("2026-11-14", retained=retained, logs=tmp_path / "logs", receipts=tmp_path / "r",
                            python=sys.executable, clock=Clock("2026-11-14T16:00:00"), child=None)
    assert weekend["state"] == scheduled.NOT_A_SESSION
    holiday = (1, {"status": "BLOCKED", "reason": "PHASE_A_NOT_ELIGIBLE",
                   "gate": {"attempt_gate_status": "NON_WORKING_DATE"}}, "", "")
    status, calls = _run(tmp_path, Clock(DAY + "T15:40:00"), [holiday])
    assert status["state"] == scheduled.NOT_A_SESSION and len(calls) == 1


def test_pass_without_a_capture_record_is_not_accepted(tmp_path):
    status, _ = _run(tmp_path, Clock(DAY + "T15:40:00"), [(0, {"status": "PASS"}, "", "")], max_attempts=1)
    assert status["attempts"][0]["outcome"] == "CAPTURE_RECORD_MISSING_AFTER_PASS" and status["state"] == scheduled.EXHAUSTED


@pytest.mark.parametrize("code,child,expected", [
    (0, {"status": "ALREADY_CAPTURED"}, scheduled.ALREADY_CAPTURED),
    (None, None, "CHILD_TIMEOUT"),
    (1, {"status": "PARTIAL", "reason": "PHASE_B_NOT_READY"}, "PHASE_B_NOT_READY"),
    (1, {"status": "BLOCKED", "reason": "PHASE_A_NOT_ELIGIBLE", "gate": {"attempt_gate_status": "TOO_EARLY"}}, "PHASE_A_TOO_EARLY"),
    (1, {"status": "BLOCKED", "reason": "CAPTURE_SOURCE_OR_INTEGRITY_FAILURE"}, "CAPTURE_SOURCE_OR_INTEGRITY_FAILURE"),
    (7, None, "CHILD_EXIT_7"),
])
def test_outcomes_come_from_the_capture_child_evidence(code, child, expected):
    assert scheduled.classify(code, child, "", "") == expected


def test_child_is_the_existing_guarded_capture_operator_and_nothing_else():
    source = Path(scheduled.__file__).read_text(encoding="utf-8")
    assert '"tools/run_capture_only.py"' in source and '"--execute", "--receipt-dir"' in source
    for forbidden in ("git", "release_orchestrator", "run_owner_daily.py", "retain_prospective_decision_snapshot",
                      "unlink", "rmtree", "os.remove"):
        assert forbidden not in source.split('"""', 2)[2], forbidden
    command = LAUNCHER.read_text(encoding="utf-8")
    assert '-X utf8 -B "%~dp0run_scheduled_capture.py" %*' in command and "exit /b %errorlevel%" in command
