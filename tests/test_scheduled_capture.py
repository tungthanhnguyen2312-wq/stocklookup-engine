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
    failed = (1, {"status": "BLOCKED", "reason": "CAPTURE_SOURCE_OR_INTEGRITY_FAILURE"}, "", "")
    status, calls = _run(tmp_path, Clock(DAY + "T15:40:00"), [failed], max_attempts=3)
    assert status["state"] == scheduled.EXHAUSTED and len(calls) == 3 and status["capture_record"] is None
    status, calls = _run(tmp_path / "refusals", Clock(DAY + "T15:40:00"), [(3, None, "NOT_ADMITTED", "")], max_refusals=3)
    assert status["state"] == scheduled.EXHAUSTED and len(calls) == 3 and status["capture_record"] is None


def test_refusal_budget_is_finite_within_the_same_day_window(tmp_path):
    clock = Clock(DAY + "T15:35:00")
    status, calls = _run(tmp_path, clock, [(3, None, "NOT_ADMITTED", "")])
    # Ten-minute spacing fits 48 probes between 15:35 and 23:30; the 48th ends the run.
    assert status["state"] == scheduled.EXHAUSTED and len(calls) == scheduled.MAX_REFUSALS
    assert all(a["outcome"] == "NOT_ADMITTED" for a in status["attempts"])
    assert max(a["started_at"] for a in status["attempts"]) < DAY + "T23:30:00"


def test_owner_daily_holding_the_lease_does_not_use_up_capture_attempts(tmp_path):
    busy = (1, None, "", "BlockingIOError: FEEDBACK_PUBLICATION_BUSY")
    # Owner Daily holds the writer lease for about two and a half hours, then fails without capturing.
    clock = Clock(DAY + "T15:40:00")
    status, calls = _run(tmp_path, clock, [busy] * 15 + ["PASS"])
    assert status["state"] == scheduled.CAPTURED and len(calls) == 16
    assert [a["outcome"] for a in status["attempts"]].count("WRITER_LEASE_BUSY") == 15
    assert scheduled.MAX_ATTEMPTS < 15


def test_refusal_keeps_the_admission_reasons_and_points_at_no_missing_receipt(tmp_path):
    refused = json.dumps({"status": "NOT_ADMITTED",
                          "admission": {"admitted": False, "reasons": ["AVAILABLE_PHYSICAL_BYTES_LOW"]},
                          "host": {"observations": {"available_physical_bytes": 3 * 1024**3,
                                                    "available_commit_bytes": 9 * 1024**3, "active_writers": []}}})
    status, _ = _run(tmp_path, Clock(DAY + "T15:40:00"), [(3, None, refused + "\n", ""), "PASS"])
    first = status["attempts"][0]
    assert first["outcome"] == "NOT_ADMITTED" and first["receipt_dir"] is None
    assert first["admission"] == {"reasons": ["AVAILABLE_PHYSICAL_BYTES_LOW"], "available_physical_bytes": 3 * 1024**3,
                                  "available_commit_bytes": 9 * 1024**3, "active_writer_count": 0}
    unexplained, _ = _run(tmp_path / "other", Clock(DAY + "T15:40:00"), [(1, None, "launcher said no", ""), "PASS"])
    assert unexplained["attempts"][0]["stdout_tail"] == "launcher said no"


def test_daily_capture_during_a_wait_is_seen_before_the_next_child(tmp_path):
    retained, calls = tmp_path / "retained", []

    def child(python, session, directory, timeout):
        calls.append(directory.name)
        return 1, None, "", "BlockingIOError: FEEDBACK_PUBLICATION_BUSY"

    def sleep(seconds):  # Owner Daily completes the capture while the scheduler waits
        clock.sleep(seconds)
        target = scheduled.record_path(retained, DAY)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}")

    clock = Clock(DAY + "T15:40:00")
    status = scheduled.run(DAY, retained=retained, logs=tmp_path / "logs", receipts=tmp_path / "r",
                           python=sys.executable, clock=clock, sleep=sleep, child=child)
    assert status["state"] == scheduled.ALREADY_CAPTURED and len(calls) == 1


def test_catch_up_start_long_before_the_window_ends_without_waiting(tmp_path):
    # Task Scheduler starts a missed run when the host resumes the next morning.
    clock = Clock(DAY + "T08:10:00")
    status, calls = _run(tmp_path, clock, ["PASS"])
    assert status["state"] == scheduled.BEFORE_WINDOW and calls == [] and clock.slept == []
    assert status["next_attempt_at"] == DAY + "T15:35:00+07:00" and scheduled.BEFORE_WINDOW in scheduled.TERMINAL_OK
    # The session's own 15:35 trigger then runs normally and keeps the earlier run's evidence.
    status, calls = _run(tmp_path, Clock(DAY + "T15:35:00"), ["PASS"])
    assert status["state"] == scheduled.CAPTURED and len(calls) == 1
    assert [run["state"] for run in status["prior_runs"]] == [scheduled.BEFORE_WINDOW]


def test_worst_case_run_fits_the_task_execution_time_limit():
    start = datetime.combine(datetime.fromisoformat(DAY).date(), scheduled.FIRST_ATTEMPT) \
        - timedelta(seconds=scheduled.EARLY_START_SECONDS)
    from stocklookup_core.evidence.capture_only import DEADLINE_SECONDS
    end = datetime.combine(datetime.fromisoformat(DAY).date(), scheduled.LAST_ATTEMPT) \
        + timedelta(seconds=DEADLINE_SECONDS + scheduled.CHILD_GRACE_SECONDS)
    assert end - start < timedelta(hours=9)  # the registered task's ExecutionTimeLimit is PT9H


def test_missed_session_is_not_attempted_on_a_later_day(tmp_path):
    # The host slept through Wednesday's run; Thursday's run captures Thursday only.
    calls = []

    def child(python, session, directory, timeout):
        calls.append(session)
        target = scheduled.record_path(tmp_path / "retained", session)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text("{}")
        return 0, {"status": "PASS"}, "", ""

    thursday = "2026-11-12"
    status = scheduled.run(thursday, retained=tmp_path / "retained", logs=tmp_path / "logs", receipts=tmp_path / "r",
                           python=sys.executable, clock=Clock(thursday + "T15:36:00"), child=child)
    assert status["state"] == scheduled.CAPTURED and calls == [thursday]
    assert not scheduled.record_path(tmp_path / "retained", DAY).exists()
    late = scheduled.run(DAY, retained=tmp_path / "retained", logs=tmp_path / "logs", receipts=tmp_path / "r",
                         python=sys.executable, clock=Clock(thursday + "T15:36:00"), child=child)
    assert late["state"] == scheduled.WINDOW_CLOSED and calls == [thursday]


def test_repeated_invocation_acquires_nothing_and_keeps_earlier_attempts(tmp_path):
    refused = (3, None, '{"status": "NOT_ADMITTED"}', "")
    first, calls = _run(tmp_path, Clock(DAY + "T15:35:00"), [refused, "PASS"])
    assert first["state"] == scheduled.CAPTURED and len(calls) == 2
    for _ in range(2):
        again, calls = _run(tmp_path, Clock(DAY + "T19:00:00"), ["PASS"])
        assert again["state"] == scheduled.ALREADY_CAPTURED and calls == [] and again["attempts"] == []
    assert [run["state"] for run in again["prior_runs"]] == [scheduled.CAPTURED, scheduled.ALREADY_CAPTURED]
    assert [a["outcome"] for a in again["prior_runs"][0]["attempts"]] == ["NOT_ADMITTED", scheduled.CAPTURED]


def test_interrupted_run_is_recorded_by_the_next_run(tmp_path):
    def child(python, session, directory, timeout):
        raise KeyboardInterrupt  # task stopped or host shut down while the child ran

    with pytest.raises(KeyboardInterrupt):
        scheduled.run(DAY, retained=tmp_path / "retained", logs=tmp_path / "logs", receipts=tmp_path / "r",
                      python=sys.executable, clock=Clock(DAY + "T15:40:00"), child=child)
    status, calls = _run(tmp_path, Clock(DAY + "T16:00:00"), ["PASS"])
    assert status["state"] == scheduled.CAPTURED and status["prior_runs"][0]["state"] == "ATTEMPT_RUNNING"


def test_child_timeout_is_a_bounded_capture_attempt(tmp_path):
    status, calls = _run(tmp_path, Clock(DAY + "T15:40:00"), [(None, None, "", ""), "PASS"])
    assert [a["outcome"] for a in status["attempts"]] == ["CHILD_TIMEOUT", scheduled.CAPTURED]
    timeouts = []

    def child(python, session, directory, timeout):
        timeouts.append(timeout)
        return None, None, "", ""

    scheduled.run(DAY, retained=tmp_path / "t", logs=tmp_path / "t-logs", receipts=tmp_path / "t-r", python=sys.executable,
                  clock=Clock(DAY + "T15:40:00"), sleep=lambda s: None, child=child, max_attempts=2)
    from stocklookup_core.evidence.capture_only import DEADLINE_SECONDS
    assert timeouts == [DEADLINE_SECONDS + scheduled.CHILD_GRACE_SECONDS] * 2


def _main_with(monkeypatch, tmp_path, binding):
    import tools.run_capture_only as operator
    monkeypatch.setattr(operator, "binding", binding)
    monkeypatch.setattr(scheduled, "vn_now", lambda: datetime.fromisoformat(DAY + "T08:00:00").replace(tzinfo=VN))
    return scheduled.main(["--session", DAY])


def _paths(tmp_path):
    return {role: tmp_path / role for role in ("producer", "runtime", "retained", "dashboard")} | {"logs": tmp_path / "logs" / "run-logs"}


def test_wrapper_failure_is_reported_with_its_own_exit_code(monkeypatch, tmp_path, capsys):
    def refused():
        raise ValueError("CAPTURE_REQUIRES_ACTIVE_PRODUCTION_PROFILE")

    assert _main_with(monkeypatch, tmp_path, refused) == 5
    assert json.loads(capsys.readouterr().out)["state"] == scheduled.WRAPPER_FAILED
    paths = _paths(tmp_path)
    monkeypatch.setattr(scheduled, "run", lambda *a, **k: (_ for _ in ()).throw(OSError("T: not mounted")))
    assert _main_with(monkeypatch, tmp_path, lambda: paths) == 5
    written = json.loads((paths["logs"] / f"pit_capture_{DAY}.status.json").read_text(encoding="utf-8"))
    assert written["state"] == scheduled.WRAPPER_FAILED and "T: not mounted" in written["error"]


def test_second_scheduler_instance_is_refused_by_the_kernel_lock(monkeypatch, tmp_path, capsys):
    import threading
    from feedback_publication_lock import publication_lock
    paths = _paths(tmp_path)
    receipts = paths["logs"].parent / "capture-receipts"
    receipts.mkdir(parents=True)
    held, release = threading.Event(), threading.Event()

    def holder():
        with publication_lock(receipts / ".scheduled-capture", blocking=False):
            held.set()
            release.wait(10)

    thread = threading.Thread(target=holder)
    thread.start()
    try:
        assert held.wait(10)
        monkeypatch.setattr(scheduled, "run", lambda *a, **k: pytest.fail("second instance must not run"))
        assert _main_with(monkeypatch, tmp_path, lambda: paths) == 0
        assert json.loads(capsys.readouterr().out)["state"] == scheduled.ALREADY_RUNNING
    finally:
        release.set()
        thread.join()


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


@pytest.mark.parametrize("weekend", ["2026-11-14", "2026-11-15"])  # Saturday, Sunday
def test_weekends_make_no_acquisition_at_any_hour(tmp_path, weekend):
    for hour in ("08:00", "15:35", "16:00", "23:00"):
        status = scheduled.run(weekend, retained=tmp_path / "retained", logs=tmp_path / "logs", receipts=tmp_path / "r",
                               python=sys.executable, clock=Clock(weekend + "T" + hour), child=None, sleep=None)
        assert status["state"] == scheduled.NOT_A_SESSION and status["attempts"] == []
    assert not (tmp_path / "r").exists() and not (tmp_path / "retained").exists()


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
