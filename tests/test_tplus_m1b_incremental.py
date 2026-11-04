"""M1b levers: verifier split, price fingerprints, minimal projection, row reuse, scrub scope."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import bounded_artifact_stream as bas
import prospective_feedback_streaming as streaming
from stocklookup_core.evidence import source_verifier
from tests.test_prospective_feedback_streaming import _add_modern, _build, _corpus, _legacy_artifact
from tests.test_tplus_incremental_cost_v2 import _snapshot_path

ROOT = Path(__file__).resolve().parents[1]


def test_verifier_digest_ignores_the_streaming_evaluator_and_rejects_a_verifier_change(tmp_path, monkeypatch):
    assert "prospective_feedback_streaming" not in "".join(source_verifier.verification_units())
    assert any(name.endswith("source_verifier") for name in source_verifier.verification_units())
    assert any(name.endswith("source_file_fingerprint") for name in source_verifier.verification_units())
    root, state = tmp_path / "evidence", tmp_path / "state"
    _add_modern(root, "2026-04-01", 0)
    path = _snapshot_path(root)
    streaming.load_snapshot_handle(path, state, {})
    calls = {"n": 0}
    real_hash = bas.source_hash

    def counted(target):
        calls["n"] += 1
        return real_hash(target)

    monkeypatch.setattr(bas, "source_hash", counted)
    warm: dict = {}
    streaming.load_snapshot_handle(path, state, warm)
    assert calls["n"] == 0
    assert warm["t0_fingerprint_hits"] == 1

    monkeypatch.setattr(source_verifier, "verification_code_digest", lambda: "ab" * 32)
    changed: dict = {}
    streaming.load_snapshot_handle(path, state, changed)
    assert changed["t0_fingerprint_misses"] == 1
    assert changed["stream_sha256_bytes"] == path.stat().st_size


def test_price_fingerprint_hit_does_not_hash(tmp_path, monkeypatch):
    root, state = tmp_path / "evidence", tmp_path / "state"
    output = tmp_path / "out" / "feedback.json"
    _corpus(root, legacy=1, modern=0)
    first = _build(root, output, state)
    assert first["outcome"] == streaming.OUTCOME_BUILT
    assert first["metrics"].get("price_fingerprint_misses", 0) >= 1
    hashed: list[Path] = []
    real_hash = bas.source_hash

    def counted(target):
        hashed.append(Path(target))
        return real_hash(target)

    monkeypatch.setattr(bas, "source_hash", counted)
    warm = _build(root, output, state)
    assert warm["outcome"] == streaming.OUTCOME_ALREADY_COMPLETE
    assert warm["metrics"].get("price_fingerprint_hits", 0) >= 1
    assert warm["metrics"].get("price_hash_bytes", 0) == 0
    assert hashed == [output]


def test_projection_keeps_artifact_identity_and_stores_only_the_read_fields(tmp_path):
    root, state = tmp_path / "evidence", tmp_path / "state"
    output = tmp_path / "out" / "feedback.json"
    _corpus(root, legacy=1, modern=2)
    built = _build(root, output, state)
    expected = _legacy_artifact(root)
    assert built["artifact_identity"] == expected["artifact_identity"]
    assert built["record_count"] == len(expected["feedback_records"])
    sidecar = next((state / streaming.EVALUATOR_INPUT_DIR).rglob("*.jsonl"))
    stored = json.loads(sidecar.read_text(encoding="utf-8").splitlines()[0])
    assert set(stored["t0_snapshot_record"]) <= set(streaming._SNAPSHOT_RECORD_KEEP)
    record = stored["t0_snapshot_record"]["integrated_decision_at_t0"]
    assert set(record) <= set(streaming._RECORD_KEEP) | set(streaming._RECORD_NESTED) | {"evidence_axes"}
    assert "trigger" in record and "invalidation" in record


def test_row_reuse_inside_a_rebuilt_partition_keeps_identity(tmp_path, monkeypatch):
    root, state = tmp_path / "evidence", tmp_path / "state"
    for index in range(22):
        _add_modern(root, f"2026-05-{index + 1:02d}", index)
    output = tmp_path / "out" / "feedback.json"
    first = _build(root, output, state)
    assert first["outcome"] == streaming.OUTCOME_BUILT
    expected = _legacy_artifact(root)["artifact_identity"]
    assert first["artifact_identity"] == expected
    monkeypatch.setattr(streaming._Partitions, "manifest", lambda self, position, session: None)
    second = _build(root, tmp_path / "out" / "rebuilt.json", state)
    assert second["outcome"] == streaming.OUTCOME_BUILT
    assert second["artifact_identity"] == expected
    assert second["metrics"].get("rows_reused_inside_partition", 0) > 0
    assert second["metrics"].get("rows_reevaluated", 0) > 0


def test_scrub_out_of_scope_missing_receipt_and_mismatch(tmp_path):
    root, state = tmp_path / "evidence", tmp_path / "state"
    _corpus(root, legacy=1, modern=1)
    output = tmp_path / "out" / "feedback.json"
    assert _build(root, output, state)["outcome"] == streaming.OUTCOME_BUILT
    published = output.read_bytes()
    genuine = _snapshot_path(root)
    extra = root / "operations-review" / "prospective-decision-retention-v1" / "2026-09-01" / "not-genuine" / "prospective_decision_snapshot.json"
    extra.parent.mkdir(parents=True)
    extra.write_text("{}\n", encoding="utf-8")
    report = streaming.scrub_sources(root, state)
    assert report["metrics"]["scrub_mismatches"] == 0
    assert report["metrics"]["scrub_out_of_scope"] >= 1
    assert any(row["status"] == "scrub_out_of_scope" for row in report["out_of_scope"])
    assert output.read_bytes() == published

    for directory in ("t0_receipts", "t0_fingerprint"):
        target = state / streaming.STATE_DIR / directory
        if target.exists():
            for child in target.glob("*.json"):
                child.unlink()
    with pytest.raises(streaming.SourceIntegrityError, match="RECEIPT_MISSING") as missing:
        streaming.scrub_sources(root, state)
    assert "RECEIPT_MISMATCH" not in str(missing.value)
    assert output.read_bytes() == published

    assert _build(root, tmp_path / "out" / "again.json", state)["outcome"] == streaming.OUTCOME_BUILT
    path = genuine
    payload = bytearray(path.read_bytes())
    assert len(payload) > 12
    payload[-12] ^= 0x07
    path.write_bytes(payload)
    with pytest.raises(streaming.SourceIntegrityError, match="RECEIPT_MISMATCH") as mismatched:
        streaming.scrub_sources(root, state)
    assert "RECEIPT_MISSING" not in str(mismatched.value)


def test_fixture_profile_records_the_phase_split(tmp_path):
    root, state = tmp_path / "evidence", tmp_path / "state"
    output = tmp_path / "out" / "feedback.json"
    _corpus(root, legacy=1, modern=3)
    cold = _build(root, output, state)
    phases = cold["phases_seconds"]
    for key in ("discovery_s", "discovery_legacy_s", "discovery_t0_s", "price_index_s", "evaluate_s", "aggregate_s", "assemble_s"):
        assert key in phases
    metrics = cold["metrics"]
    assert "discovery_legacy_other_s" in metrics and "discovery_t0_other_s" in metrics
    assert "partition_evaluate_s" in metrics
    assert metrics.get("rows_reevaluated", 0) > 0
    assert "sidecar_json_decode_s" in metrics
    assert metrics.get("sidecar_decoded_bytes", 0) > 0
