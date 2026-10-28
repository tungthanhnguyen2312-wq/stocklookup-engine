"""Capture-only composition of the existing qualified Daily evidence boundaries.

No decision, Producer, runtime publication, registry mutation or T0 generation.
Production invocation is guarded by tools.run_capture_only, not this testable core.
"""
from datetime import datetime
from zoneinfo import ZoneInfo

VN = ZoneInfo("Asia/Ho_Chi_Minh")
TREE_BYTES = 3 * 1024**3  # restrictive capture cap, NOT a Daily qualification
DEADLINE_SECONDS = 1800


def check_window(session, instant):
    from stocklookup_core.evidence.prospective_pit_capture import capture_window
    if instant.tzinfo is None:
        raise ValueError("CAPTURE_CLOCK_MUST_BE_AWARE")
    opened, closed = capture_window(session)
    if not datetime.fromisoformat(opened) <= instant < datetime.fromisoformat(closed):
        raise ValueError("CAPTURE_WINDOW_CLOSED_OR_NOT_OPEN")


def run_capture(ops, session):
    """Seams are for hermetic tests; the CLI always constructs NativeCapture."""
    result = {"session": session, "status": "BLOCKED", "t0_status": "UNAVAILABLE",
              "authority_effect": "NONE / CAPTURE_COMPLETENESS_ONLY", "evidence": {}}
    original = ops.existing(session)
    if original is not None:
        return {**result, "status": "ALREADY_CAPTURED", "completion": original}
    check_window(session, ops.clock())
    calendar = ops.calendar()
    phase_a = ops.attempt(session, calendar, ops.clock())
    if phase_a.get("attempt_gate_status") != "ATTEMPT_ELIGIBLE" or phase_a.get("resolved_session") != session:
        return {**result, "reason": "PHASE_A_NOT_ELIGIBLE", "gate": phase_a}
    check_window(session, ops.clock())
    snapshot = ops.acquire(session)
    result["snapshot_identity"] = snapshot.get("snapshot_identity")
    phase_b = ops.gate(session, calendar, snapshot, ops.clock())
    if phase_b.get("completion_gate_status") != "READY" or phase_b.get("resolved_session") != session:
        return {**result, "status": "PARTIAL", "reason": "PHASE_B_NOT_READY", "gate": phase_b}
    # Preserve source-native clocks/receipts; retain listing before binding.
    check_window(session, ops.clock())
    evidence = result["evidence"]
    evidence["calendar"] = ops.retain_calendar(calendar)
    evidence["listing_sources"] = ops.listing(session)
    evidence["market"] = ops.market(snapshot, session)
    evidence["capture"] = ops.bind(snapshot, session, evidence, ops.clock())
    check_window(session, ops.clock())
    completed = ops.complete(session, phase_b, evidence, ops.clock())
    result.update(status="PASS" if completed.get("status") in {"RETAINED", "ALREADY_CAPTURED"} else "PARTIAL",
                  completion=completed, gate=phase_b)
    return result
