"""Same-day scheduled market capture, independent of Owner Daily.

The capture window closes for good: listing knowledge must belong to the session's own
calendar day and nothing is backfilled. This operator makes the capture attempt on the
session day without waiting for Owner Daily, whose two-hour pipeline, memory preflight,
analysis and Dashboard publication can each stop it for reasons unrelated to capture.

It adds no acquisition logic. Every attempt is one ``tools/run_capture_only.py --execute``
child, which keeps its own admission, Windows Job limits, write scope and the writer lease
it shares with Owner Daily. This file only decides when to attempt, how often, and records
what happened:

* one scheduler instance at a time (kernel lock), and never while another writer holds
  the production lease - a busy lease is an attempt outcome, retried later;
* a bounded number of attempts between the first attempt time and the same-day cutoff;
* an existing complete capture record ends the run without acquiring anything;
* a status file per session under the logs role, rewritten atomically after every attempt.

It publishes nothing, commits nothing, creates no decision and no T0, and never repairs,
re-dates or reconstructs a missed session.
"""
from __future__ import annotations

import argparse
from datetime import datetime, time as wall_time, timedelta
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

FIRST_ATTEMPT = wall_time(15, 35)   # after the 15:30 safety floor of the attempt gate
LAST_ATTEMPT = wall_time(23, 30)    # listing knowledge must be acquired on the session day
INTERVAL_SECONDS = 600
MAX_ATTEMPTS = 12
CHILD_GRACE_SECONDS = 300
STORE_SESSIONS = Path("operations-review/prospective-pit-capture-v1/sessions")
STATUS_CONTRACT = "scheduled_pit_capture_status/v1"

CAPTURED = "CAPTURED"
ALREADY_CAPTURED = "ALREADY_CAPTURED"
NOT_A_SESSION = "NOT_A_MARKET_SESSION"
EXHAUSTED = "ATTEMPTS_EXHAUSTED"
WINDOW_CLOSED = "SAME_DAY_WINDOW_CLOSED"
ALREADY_RUNNING = "SCHEDULER_ALREADY_RUNNING"
TERMINAL_OK = {CAPTURED, ALREADY_CAPTURED, NOT_A_SESSION, ALREADY_RUNNING}


def vn_now() -> datetime:
    from stocklookup_core.evidence.capture_only import VN
    return datetime.now(VN)


def record_path(retained: Path, session: str) -> Path:
    return Path(retained) / STORE_SESSIONS / (session + ".json")


def classify(exit_code: int | None, child: dict | None, stdout: str, stderr: str) -> str:
    """Name one attempt's outcome from the capture child's own evidence."""
    if child and child.get("status") in {"PASS", "ALREADY_CAPTURED"} and exit_code == 0:
        return ALREADY_CAPTURED if child["status"] == "ALREADY_CAPTURED" else CAPTURED
    if exit_code is None:
        return "CHILD_TIMEOUT"
    if child:
        gate = child.get("gate") or {}
        if child.get("reason") == "PHASE_A_NOT_ELIGIBLE":
            status = str(gate.get("attempt_gate_status") or "")
            return NOT_A_SESSION if "NON_WORKING" in status else "PHASE_A_" + (status or "NOT_ELIGIBLE")
        return str(child.get("reason") or child.get("status") or "CHILD_NOT_PASS")
    text = stdout + "\n" + stderr
    for marker in ("NOT_ADMITTED", "FEEDBACK_PUBLICATION_BUSY", "CAPTURE_WINDOW_CLOSED_OR_NOT_OPEN",
                   "CAPTURE_REQUIRES_ACTIVE_PRODUCTION_PROFILE", "CAPTURE_DEADLINE_EXCEEDED"):
        if marker in text:
            return "WRITER_LEASE_BUSY" if marker == "FEEDBACK_PUBLICATION_BUSY" else marker
    return "CHILD_EXIT_%s" % exit_code


def run_child(python: str, session: str, directory: Path, timeout: float) -> tuple[int | None, dict | None, str, str]:
    command = [python, "-B", str(ROOT / "tools/run_capture_only.py"), "--session", session,
               "--execute", "--receipt-dir", str(directory)]
    try:
        done = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                              errors="replace", timeout=timeout,
                              env={**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"})
        code, out, err = done.returncode, done.stdout, done.stderr
    except subprocess.TimeoutExpired as expired:
        code, out, err = None, str(expired.stdout or ""), str(expired.stderr or "")
    child = None
    try:
        child = json.loads((directory / "child-result.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        pass
    return code, child if isinstance(child, dict) else None, out, err


def write_status(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".%d.tmp" % os.getpid())
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temporary, path)


def retain_readiness(root: Path, retained: Path, session: str) -> dict:
    """Publish the session's readiness record through the existing Daily boundary.

    The capture record already exists, so the boundary only reads it back and writes the
    derived readiness artifact. Held under the production writer lease; failure is reported,
    never raised, and never touches the capture record.
    """
    try:
        import prospective_pit_capture_retention as store
        from tools.capture_writer_lease import writer_lease
        with writer_lease(root):
            result = store.daily_boundary(retained, session=session, gate={}, evidence={},
                                          known_at=store.io_known_at(), t0_snapshot_identity=None)
        return {"status": (result.get("readiness") or {}).get("status"),
                "path": (result.get("readiness") or {}).get("path"),
                "complete_session_count": (result.get("readiness") or {}).get("complete_session_count")}
    except BaseException as error:  # noqa: BLE001 - observability only
        return {"status": "UNAVAILABLE", "reason": "%s:%s" % (type(error).__name__, error)}


def run(session: str, *, retained: Path, logs: Path, receipts: Path, python: str,
        clock=vn_now, sleep=time.sleep, child=run_child, readiness=None,
        interval: int = INTERVAL_SECONDS, max_attempts: int = MAX_ATTEMPTS,
        first: wall_time = FIRST_ATTEMPT, last: wall_time = LAST_ATTEMPT, child_timeout: float | None = None) -> dict:
    from stocklookup_core.evidence.capture_only import DEADLINE_SECONDS, VN
    day = datetime.fromisoformat(session).date()
    opens = datetime.combine(day, first, VN)
    closes = datetime.combine(day, last, VN)
    status_path = Path(logs) / ("pit_capture_%s.status.json" % session)
    status = {"contract_version": STATUS_CONTRACT, "session": session, "state": "STARTED",
              "authority_effect": "NONE / CAPTURE_COMPLETENESS_ONLY",
              "first_attempt_not_before": opens.isoformat(), "last_attempt_before": closes.isoformat(),
              "max_attempts": max_attempts, "interval_seconds": interval,
              "started_at": clock().isoformat(), "attempts": [], "capture_record": None}

    def finish(state: str) -> dict:
        target = record_path(retained, session)
        if target.exists():
            status["capture_record"] = {"path": str(target), "bytes": target.stat().st_size}
        status.update(state=state, finished_at=clock().isoformat())
        write_status(status_path, status)
        return status

    if day.weekday() >= 5:
        return finish(NOT_A_SESSION)
    if record_path(retained, session).exists():
        return finish(ALREADY_CAPTURED)
    while len(status["attempts"]) < max_attempts:
        now = clock()
        if now >= closes:
            return finish(WINDOW_CLOSED)
        if now < opens:
            status.update(state="WAITING_FOR_FIRST_ATTEMPT", next_attempt_at=opens.isoformat())
            write_status(status_path, status)
            sleep(min((opens - now).total_seconds(), 300))
            continue
        number = len(status["attempts"]) + 1
        directory = Path(receipts) / session / ("attempt-%02d-%s" % (number, now.strftime("%H%M%S")))
        directory.parent.mkdir(parents=True, exist_ok=True)
        status.update(state="ATTEMPT_RUNNING", next_attempt_at=None)
        write_status(status_path, status)
        code, result, out, err = child(python, session, directory, child_timeout or DEADLINE_SECONDS + CHILD_GRACE_SECONDS)
        outcome = classify(code, result, out, err)
        if outcome in {CAPTURED, ALREADY_CAPTURED} and not record_path(retained, session).exists():
            outcome = "CAPTURE_RECORD_MISSING_AFTER_PASS"
        status["attempts"].append({"number": number, "started_at": now.isoformat(), "finished_at": clock().isoformat(),
                                   "exit_code": code, "outcome": outcome, "receipt_dir": str(directory),
                                   "child_status": (result or {}).get("status"), "stderr_tail": err[-600:]})
        if outcome in {CAPTURED, ALREADY_CAPTURED}:
            if readiness is not None:
                status["readiness"] = readiness(session)
            return finish(outcome)
        if outcome == NOT_A_SESSION:
            return finish(NOT_A_SESSION)
        upcoming = clock() + timedelta(seconds=interval)
        if len(status["attempts"]) >= max_attempts or upcoming >= closes:
            break
        status.update(state="WAITING_TO_RETRY", next_attempt_at=upcoming.isoformat())
        write_status(status_path, status)
        sleep(interval)
    if record_path(retained, session).exists():  # Owner Daily captured it while this run waited
        return finish(ALREADY_CAPTURED)
    return finish(EXHAUSTED if len(status["attempts"]) >= max_attempts else WINDOW_CLOSED)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--session", help="YYYY-MM-DD; default is today's Vietnam date")
    parser.add_argument("--max-attempts", type=int, default=MAX_ATTEMPTS)
    parser.add_argument("--interval-seconds", type=int, default=INTERVAL_SECONDS)
    args = parser.parse_args(argv)
    if not 1 <= args.max_attempts <= MAX_ATTEMPTS or not 60 <= args.interval_seconds <= 3600:
        parser.error("attempts must be 1..%d and interval 60..3600 seconds" % MAX_ATTEMPTS)
    session = args.session or vn_now().date().isoformat()
    datetime.fromisoformat(session)
    from tools.run_capture_only import binding
    paths = binding()
    receipts = Path(paths["logs"]).parent / "capture-receipts"
    if any(receipts.resolve().is_relative_to(Path(paths[role]).resolve()) for role in ("producer", "runtime", "retained", "dashboard")):
        raise ValueError("CAPTURE_RECEIPT_MUST_BE_EXTERNAL")
    receipts.mkdir(parents=True, exist_ok=True)
    from feedback_publication_lock import publication_lock
    try:
        with publication_lock(receipts / ".scheduled-capture", blocking=False):
            status = run(session, retained=Path(paths["retained"]), logs=Path(paths["logs"]), receipts=receipts,
                         python=sys.executable, interval=args.interval_seconds, max_attempts=args.max_attempts,
                         readiness=lambda day: retain_readiness(ROOT, Path(paths["retained"]), day))
    except BlockingIOError:
        status = {"session": session, "state": ALREADY_RUNNING}
    print(json.dumps({key: status.get(key) for key in ("session", "state", "capture_record", "readiness")}, ensure_ascii=False))
    return 0 if status["state"] in TERMINAL_OK else 4


if __name__ == "__main__":
    raise SystemExit(main())
