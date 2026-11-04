"""TPLUS_INCREMENTAL_COST_V2: fingerprint-anchored receipts and evaluator-input sidecars.

Part A skips a content hash when volume, file id, size, mtime and NTFS ChangeTime still match a
receipt produced by a full SHA-256 under the current verifier. Part B re-reads that projection
from a rebuildable sidecar. The T0 file stays the only authority.
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

import pytest

import bounded_artifact_stream as bas
import prospective_feedback_streaming as streaming
from stocklookup_core.evidence.source_file_fingerprint import source_file_fingerprint
from tests.test_prospective_feedback_streaming import _add_legacy, _add_modern, _build, _corpus, _legacy_artifact

ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable


def _snapshot_path(root: Path) -> Path:
    found = sorted(root.glob("operations-review/prospective-decision-retention-v1/*/*/prospective_decision_snapshot.json"))
    assert found, "modern snapshot was not written"
    return found[-1]


def _legacy_path(root: Path) -> Path:
    found = sorted(root.glob("operations-review/integrated-artifacts/*/integrated_investment_decision_product_artifact.json"))
    assert found
    return found[-1]


def _inventory(root: Path, path: Path) -> dict:
    relative = str(path.relative_to(root)).replace("\\", "/")
    return {
        "snapshot_path": relative,
        "canonical_handoff_path": "operations-review/canonical-post-close-v1/session/session_handoff_bundle.json",
        "operation_manifest_path": "operations-review/daily-research-session-operations-v1/session/run/run_manifest.json",
        "proof_reason_codes": [],
    }


def _canon_rows(rows) -> list[bytes]:
    return [streaming._canon_bytes(row) for row in rows]


def _shift(monkeypatch, field: str, delta: int):
    real = streaming.source_file_fingerprint

    def shifted(path):
        found = real(path)
        if not found:
            return found
        found = dict(found)
        found[field] = int(found[field]) + delta
        return found

    monkeypatch.setattr(streaming, "source_file_fingerprint", shifted)


# -- fingerprint ----------------------------------------------------------------------------------

def test_fingerprint_hit_does_not_hash(tmp_path, monkeypatch):
    root, state = tmp_path / "evidence", tmp_path / "state"
    _add_modern(root, "2026-02-02", 0)
    path = _snapshot_path(root)
    cold: dict = {}
    first = streaming.load_snapshot_handle(path, state, cold)
    assert first is not None and first.raw_sha256
    assert cold["t0_fingerprint_misses"] == 1
    assert cold["stream_sha256_bytes"] == path.stat().st_size
    calls = {"n": 0}
    real_hash = bas.source_hash

    def counted(target):
        calls["n"] += 1
        return real_hash(target)

    monkeypatch.setattr(bas, "source_hash", counted)
    warm: dict = {}
    second = streaming.load_snapshot_handle(path, state, warm)
    assert calls["n"] == 0
    assert warm["t0_fingerprint_hits"] == 1
    assert warm.get("stream_sha256_bytes", 0) == 0
    assert second.raw_sha256 == first.raw_sha256
    assert second.size == first.size


def test_size_mtime_file_id_change_time_and_volume_force_a_full_hash(tmp_path, monkeypatch):
    root, state = tmp_path / "evidence", tmp_path / "state"
    _add_modern(root, "2026-02-03", 1)
    path = _snapshot_path(root)
    streaming.load_snapshot_handle(path, state, {})
    original = source_file_fingerprint(path)
    assert original is not None

    stamped = path.stat()
    payload = bytearray(path.read_bytes())
    payload[-20] = payload[-20] ^ 0x01
    path.write_bytes(payload)
    os.utime(path, ns=(stamped.st_atime_ns, stamped.st_mtime_ns))
    changed = source_file_fingerprint(path)
    assert changed is not None
    assert changed["mtime_ns"] == original["mtime_ns"]
    assert changed["size"] == original["size"]
    assert changed["change"] != original["change"]
    metrics: dict = {}
    streaming.load_snapshot_handle(path, state, metrics)
    assert metrics["t0_fingerprint_misses"] == 1
    assert metrics["stream_sha256_bytes"] == path.stat().st_size

    path.write_bytes(path.read_bytes() + b"\n")
    metrics = {}
    streaming.load_snapshot_handle(path, state, metrics)
    assert metrics["stream_sha256_bytes"] == path.stat().st_size

    path.write_bytes(payload)
    os.utime(path, ns=(stamped.st_atime_ns, stamped.st_mtime_ns + 10_000_000))
    streaming.load_snapshot_handle(path, state, {})
    metrics = {}
    streaming.load_snapshot_handle(path, state, metrics)
    assert metrics.get("t0_fingerprint_hits", 0) == 1
    os.utime(path, ns=(stamped.st_atime_ns, stamped.st_mtime_ns + 20_000_000))
    metrics = {}
    streaming.load_snapshot_handle(path, state, metrics)
    assert metrics["t0_fingerprint_misses"] == 1 and metrics["stream_sha256_bytes"] == path.stat().st_size

    _shift(monkeypatch, "file_id", 1)
    metrics = {}
    streaming.load_snapshot_handle(path, state, metrics)
    assert metrics["t0_fingerprint_misses"] == 1 and metrics["stream_sha256_bytes"] > 0
    monkeypatch.undo()

    _shift(monkeypatch, "volume", 1)
    metrics = {}
    streaming.load_snapshot_handle(path, state, metrics)
    assert metrics["t0_fingerprint_misses"] == 1 and metrics["stream_sha256_bytes"] > 0


def test_verification_digest_change_and_reparse_force_a_full_hash(tmp_path, monkeypatch):
    root, state = tmp_path / "evidence", tmp_path / "state"
    _add_modern(root, "2026-02-04", 2)
    path = _snapshot_path(root)
    streaming.load_snapshot_handle(path, state, {})
    monkeypatch.setattr(streaming, "_verification_code_digest", lambda: "f" * 64)
    metrics: dict = {}
    streaming.load_snapshot_handle(path, state, metrics)
    assert metrics["t0_fingerprint_misses"] == 1
    assert metrics["stream_sha256_bytes"] == path.stat().st_size
    monkeypatch.undo()

    streaming.load_snapshot_handle(path, state, {})
    import stocklookup_core.evidence.source_file_fingerprint as fingerprint

    monkeypatch.setattr(fingerprint, "path_has_reparse_point", lambda _path: True)
    metrics = {}
    streaming.load_snapshot_handle(path, state, metrics)
    assert metrics["t0_fingerprint_misses"] == 1
    assert metrics["stream_sha256_bytes"] == path.stat().st_size


def test_legacy_fingerprint_hit_does_not_hash(tmp_path, monkeypatch):
    root, state = tmp_path / "evidence", tmp_path / "state"
    _add_legacy(root, "2026-02-05", 0)
    path = _legacy_path(root)
    cold: dict = {}
    first = streaming.scan_legacy_artifact(path, cold, state)
    assert first is not None
    assert cold["legacy_fingerprint_misses"] == 1
    assert cold["stream_sha256_bytes"] == path.stat().st_size
    calls = {"n": 0}
    real_hash = bas.source_hash

    def counted(target):
        calls["n"] += 1
        return real_hash(target)

    monkeypatch.setattr(bas, "source_hash", counted)
    warm: dict = {}
    second = streaming.scan_legacy_artifact(path, warm, state)
    assert calls["n"] == 0
    assert warm["legacy_fingerprint_hits"] == 1
    assert warm.get("stream_sha256_bytes", 0) == 0
    assert second.raw_sha256 == first.raw_sha256


# -- scrub ----------------------------------------------------------------------------------------

def test_scrub_refreshes_verified_at_and_rejects_a_tampered_source(tmp_path):
    root, state = tmp_path / "evidence", tmp_path / "state"
    _corpus(root, legacy=1, modern=1)
    output = tmp_path / "out" / "feedback.json"
    built = _build(root, output, state)
    assert built["outcome"] == streaming.OUTCOME_BUILT
    published = output.read_bytes()
    receipts = list((state / streaming.STATE_DIR / "t0_receipts").glob("*.json"))
    assert receipts
    before = json.loads(receipts[0].read_text(encoding="utf-8"))["verified_at"]
    time.sleep(1.1)
    report = streaming.scrub_sources(root, state)
    assert report["metrics"]["scrub_mismatches"] == 0
    assert report["metrics"]["scrub_clean"] >= 2
    assert report["metrics"]["scrub_bytes"] > 0
    after = json.loads(receipts[0].read_text(encoding="utf-8"))["verified_at"]
    assert after != before
    assert output.read_bytes() == published

    path = _snapshot_path(root)
    payload = bytearray(path.read_bytes())
    payload[-30] ^= 0x01
    stamped = path.stat()
    path.write_bytes(payload)
    os.utime(path, ns=(stamped.st_atime_ns, stamped.st_mtime_ns))
    with pytest.raises(streaming.SourceIntegrityError, match="FEEDBACK_SOURCE_INTEGRITY_FAILED"):
        streaming.scrub_sources(root, state)
    assert output.read_bytes() == published
    assert not (tmp_path / "out" / "other.json").exists()


def test_scrub_command_exits_nonzero_and_does_not_publish(tmp_path):
    root, state = tmp_path / "evidence", tmp_path / "state"
    _add_modern(root, "2026-02-06", 3)
    path = _snapshot_path(root)
    streaming.load_snapshot_handle(path, state, {})
    payload = bytearray(path.read_bytes())
    payload[-15] ^= 0x02
    path.write_bytes(payload)
    destination = tmp_path / "published.json"
    proc = subprocess.run(
        [PYTHON, str(ROOT / "tools" / "run_prospective_decision_outcome_feedback.py"),
         "--scrub-sources", "--root", str(root), "--state-root", str(state), "--output", str(destination)],
        cwd=ROOT, capture_output=True, text=True, check=False,
    )
    assert proc.returncode == 31
    body = json.loads(proc.stdout)
    assert body["status"] == "FAILED"
    assert body["reason_code"] == streaming.REASON_SOURCE_INTEGRITY
    assert "RECEIPT_MISMATCH" in body["detail"] or "FINGERPRINT_SHA_MISMATCH" in body["detail"]
    assert not destination.exists()


def test_scrub_reports_a_reparse_source_without_hashing_it(tmp_path, monkeypatch):
    root, state = tmp_path / "evidence", tmp_path / "state"
    _add_modern(root, "2026-02-07", 4)
    path = _snapshot_path(root)
    streaming.load_snapshot_handle(path, state, {})
    hashed = {"n": 0}
    real_hash = bas.source_hash

    def counted(target):
        hashed["n"] += 1
        return real_hash(target)

    monkeypatch.setattr(bas, "source_hash", counted)
    monkeypatch.setattr(streaming, "path_has_reparse_point", lambda candidate: Path(candidate) == path)
    with pytest.raises(streaming.SourceIntegrityError, match="REPARSE_POINT"):
        streaming.scrub_sources(root, state)
    assert hashed["n"] == 0


# -- sidecar --------------------------------------------------------------------------------------

def test_sidecar_rows_match_the_t0_stream_and_a_corrupt_sidecar_is_rebuilt(tmp_path):
    root, state = tmp_path / "evidence", tmp_path / "state"
    _add_modern(root, "2026-02-08", 5)
    path = _snapshot_path(root)
    handle = streaming.load_snapshot_handle(path, state, {})
    inventory = _inventory(root, path)
    direct = list(streaming._modern_input_rows(handle, inventory))
    assert direct
    metrics: dict = {}
    protected: list[Path] = []
    via = list(streaming._evaluator_inputs(handle, inventory, state, metrics, protected))
    assert _canon_rows(via) == _canon_rows(direct)
    assert metrics["sidecar_misses"] == 1 and metrics["sidecar_bytes_written"] > 0
    data_path, index_path = protected
    again: dict = {}
    second = list(streaming._evaluator_inputs(handle, inventory, state, again, []))
    assert again["sidecar_hits"] == 1
    assert _canon_rows(second) == _canon_rows(direct)

    blob = bytearray(data_path.read_bytes())
    blob[20] ^= 0x04
    data_path.write_bytes(blob)
    rebuilt: dict = {}
    restored = list(streaming._evaluator_inputs(handle, inventory, state, rebuilt, []))
    assert rebuilt["sidecar_corrupt"] == 1 and rebuilt["sidecar_misses"] == 1
    assert _canon_rows(restored) == _canon_rows(direct)

    data_path.write_bytes(data_path.read_bytes()[:40])
    truncated: dict = {}
    restored = list(streaming._evaluator_inputs(handle, inventory, state, truncated, []))
    assert truncated["sidecar_corrupt"] == 1
    assert _canon_rows(restored) == _canon_rows(direct)

    data_path.unlink()
    index_path.unlink()
    missing: dict = {}
    restored = list(streaming._evaluator_inputs(handle, inventory, state, missing, []))
    assert missing["sidecar_misses"] == 1 and missing.get("sidecar_corrupt", 0) == 0
    assert _canon_rows(restored) == _canon_rows(direct)


def test_evaluator_input_store_prune_respects_the_cap_and_refuses_a_reparse(tmp_path, monkeypatch):
    state = tmp_path / "state"
    directory = state / streaming.EVALUATOR_INPUT_DIR
    directory.mkdir(parents=True)
    kept = directory / "kept.jsonl"
    extra = directory / "extra.jsonl"
    kept.write_bytes(b"k" * 40)
    extra.write_bytes(b"e" * 40)
    os.utime(kept, ns=(1, 1))
    os.utime(extra, ns=(2, 2))
    monkeypatch.setattr(streaming, "EVALUATOR_INPUT_MAX_BYTES", 50)
    streaming._prune_evaluator_inputs(state, [kept])
    assert kept.read_bytes() == b"k" * 40
    assert not extra.exists()

    link = directory / "linked"
    target = tmp_path / "outside-file"
    target.write_text("secret", encoding="utf-8")
    created = False
    try:
        os.symlink(target, link)
        created = link.is_symlink()
    except OSError:
        created = False
    if not created:
        link.write_text("placeholder", encoding="utf-8")
        monkeypatch.setattr(streaming, "path_has_reparse_point", lambda candidate: Path(candidate) == link)
    with pytest.raises(streaming.FeedbackStreamError, match="FEEDBACK_REPARSE_POINT_REFUSED"):
        streaming._owned_files(directory)
    if created:
        assert target.read_text(encoding="utf-8") == "secret"


def test_added_session_reuses_sidecars_and_keeps_artifact_identity(tmp_path, monkeypatch):
    root = tmp_path / "evidence"
    state = tmp_path / "state"
    output = tmp_path / "out" / "feedback.json"
    _corpus(root, legacy=0, modern=2)
    calls = {"sources": 0}
    real_iter = streaming.iter_snapshot_records

    def counting(handle):
        calls["sources"] += 1
        yield from real_iter(handle)

    monkeypatch.setattr(streaming, "iter_snapshot_records", counting)
    first = _build(root, output, state)
    assert first["outcome"] == streaming.OUTCOME_BUILT
    assert calls["sources"] == 2
    calls["sources"] = 0
    _add_modern(root, "2026-03-01", 9)
    second = _build(root, tmp_path / "out" / "next.json", state)
    assert second["outcome"] == streaming.OUTCOME_BUILT
    assert second["metrics"].get("sidecar_hits", 0) >= 2
    assert calls["sources"] == 1
    assert second["artifact_identity"] == _legacy_artifact(root)["artifact_identity"]
    warm = _build(root, tmp_path / "out" / "next.json", state)
    assert warm["outcome"] == streaming.OUTCOME_ALREADY_COMPLETE
    assert warm["artifact_identity"] == second["artifact_identity"]
    assert warm["metrics"].get("t0_fingerprint_hits", 0) >= 3
