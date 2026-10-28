"""Disk-resident sorted record artifact: bytes, digest, and one-record lifetime."""
import hashlib
import json
import os

import pytest

from stocklookup_core.evidence.bounded_json import record_mapping_digest
from stocklookup_core.evidence.record_artifact_loading import (
    IndexedRecordMapping,
    RecordArtifactError,
    SortedRecordArtifactWriter,
)


def _identity(digest):
    return {"artifact_sha256": digest, "artifact_identity": "record-store:" + digest}


def _write(path, header, records, excluded=("artifact_sha256", "artifact_identity", "requested_at")):
    writer = SortedRecordArtifactWriter(path, newline="\n")
    for key in sorted(records):
        writer.add(key, records[key])
    identity, receipt, index = writer.finish(header, _identity, excluded=excluded)
    return identity, receipt, index


def test_pretty_bytes_and_digest_match_stdlib(tmp_path):
    header = {
        "session": "2026-08-28",
        "requested_at": "2026-09-02T00:00:00Z",
        "coverage": {"n": 2, "note": "Á"},
        "empty_member": {},
    }
    records = {
        "AAA": {"ticker": "AAA", "name": "Á", "n": 1.5, "rows": [1, {"b": True}]},
        "BBB": {"ticker": "BBB", "nested": {"z": 1, "a": [1, 2]}},
    }
    path = tmp_path / "artifact.json"
    identity, receipt, index = _write(path, header, records)
    full = {**header, **identity, "records": records}
    expected = (json.dumps(full, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    assert path.read_bytes() == expected
    assert receipt.size == len(expected)
    assert receipt.serialized_sha256 == hashlib.sha256(expected).hexdigest()
    payload = {key: value for key, value in full.items() if key not in {"artifact_sha256", "artifact_identity", "requested_at"}}
    assert identity["artifact_sha256"] == record_mapping_digest(payload)
    store = IndexedRecordMapping(path, receipt, index)
    assert list(store) == ["AAA", "BBB"]
    assert len(store) == 2 and "AAA" in store and "CCC" not in store
    assert store["BBB"] == records["BBB"]
    header_for_digest = {key: value for key, value in payload.items() if key != "records"}
    assert store.canonical_digest(header_for_digest) == identity["artifact_sha256"]
    reindexed, reheader = IndexedRecordMapping.from_file(path)
    assert reindexed["AAA"] == records["AAA"]
    assert reheader["session"] == "2026-08-28"
    assert reindexed.canonical_digest({key: value for key, value in reheader.items()
                                       if key not in {"artifact_sha256", "artifact_identity", "requested_at"}}) == identity["artifact_sha256"]


def test_empty_records_match_stdlib(tmp_path):
    path = tmp_path / "empty.json"
    header = {"session": "2026-08-28"}
    identity, receipt, index = _write(path, header, {})
    full = {**header, **identity, "records": {}}
    expected = (json.dumps(full, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    assert path.read_bytes() == expected
    assert len(IndexedRecordMapping(path, receipt, index)) == 0


def test_writer_refuses_unsorted_non_string_and_nan(tmp_path):
    path = tmp_path / "bad.json"
    writer = SortedRecordArtifactWriter(path, newline="\n")
    with pytest.raises(RecordArtifactError):
        writer.add(1, {"a": 1})
    writer = SortedRecordArtifactWriter(path, newline="\n")
    with pytest.raises(RecordArtifactError):
        writer.add("A", {"value": float("nan")})
    writer = SortedRecordArtifactWriter(path, newline="\n")
    writer.add("B", {"a": 1})
    with pytest.raises(RecordArtifactError):
        writer.add("A", {"a": 1})
    assert not path.exists()


def test_store_refuses_tampering(tmp_path):
    path = tmp_path / "artifact.json"
    identity, receipt, index = _write(path, {"session": "2026-08-28"}, {"AAA": {"ticker": "AAA", "n": 1}})
    store = IndexedRecordMapping(path, receipt, index)
    original = path.read_bytes()
    start, end, _digest = index["AAA"]
    flipped = bytearray(original)
    flipped[start + 1] = flipped[start + 1] ^ 1
    path.write_bytes(flipped)
    os.utime(path, ns=(receipt.mtime_ns, receipt.mtime_ns))
    with pytest.raises(RecordArtifactError, match="SLICE_MISMATCH"):
        store["AAA"]
    path.write_bytes(original + b" ")
    with pytest.raises(RecordArtifactError, match="STAT_MISMATCH"):
        store["AAA"]
    path.write_bytes(original)
    os.utime(path, ns=(receipt.mtime_ns, receipt.mtime_ns))
    with pytest.raises(KeyError):
        store["MISSING"]


def test_streamed_iid_matches_resident_artifact(tmp_path):
    import stocklookup_core.decision.integrated_investment_decision_product as iidp
    from tests.test_integrated_investment_decision_product import _sample_financial_record, _sample_tactical_record
    tactical = {"artifact_identity": "technical_structure_context/v2:fake", "records": {
        "AAA": _sample_tactical_record(), "BBB": _sample_tactical_record(eligible=False)}}
    financial = {"artifact_identity": "financial_analysis_product_integration/v1:fake", "records": {
        "AAA": _sample_financial_record()}}
    kwargs = dict(session="2026-08-28", requested_at="2026-09-02T00:00:00Z",
                  technical_structure_artifact=tactical, financial_analysis_artifact=financial)
    resident = iidp.build_artifact(**kwargs)
    path = tmp_path / "integrated_investment_decision_product_artifact.json"
    streamed = iidp.build_artifact(**kwargs, record_writer=SortedRecordArtifactWriter(path, newline="\n"))
    assert isinstance(streamed["records"], IndexedRecordMapping)
    expected = (json.dumps(resident, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")
    assert path.read_bytes() == expected
    assert streamed["artifact_identity"] == resident["artifact_identity"]
    assert streamed["artifact_sha256"] == resident["artifact_sha256"]
    assert streamed["coverage"] == resident["coverage"]
    assert set(streamed["records"]) == set(resident["records"])
    assert streamed["records"]["AAA"]["decision_identity"] == resident["records"]["AAA"]["decision_identity"]
    assert iidp.content_identity(streamed)["artifact_sha256"] == streamed["artifact_sha256"]


def test_delivery_brief_scenario_and_t0_match_on_the_store(tmp_path):
    import ai_research_session_delivery as delivery
    import stocklookup_core.decision.integrated_investment_decision_product as iidp
    from current_evidence_bound_scenario import bind_integrated_scenarios
    from prospective_decision_retention import _json_bytes, build_snapshot, validate_snapshot, write_immutable_snapshot
    from prospective_t0_seal_index import recover
    from stocklookup_core.decision.daily_integrated_decision_brief import build_opportunity_sets
    from tests.test_integrated_investment_decision_product import _sample_financial_record, _sample_tactical_record
    tactical = {"artifact_identity": "technical_structure_context/v2:fake", "records": {
        "AAA": _sample_tactical_record(), "BBB": _sample_tactical_record(eligible=False)}}
    financial = {"artifact_identity": "financial_analysis_product_integration/v1:fake", "records": {
        "AAA": _sample_financial_record(), "BBB": _sample_financial_record()}}
    kwargs = dict(session="2026-08-28", requested_at="2026-09-02T00:00:00Z",
                  technical_structure_artifact=tactical, financial_analysis_artifact=financial)
    resident = iidp.build_artifact(**kwargs)
    path = tmp_path / "iid.json"
    streamed = iidp.build_artifact(**kwargs, record_writer=SortedRecordArtifactWriter(path, newline="\n"))
    resident_overlay = delivery.project_integrated_decision_delivery_overlay("2026-08-28", resident, None)
    streamed_overlay = delivery.project_integrated_decision_delivery_overlay("2026-08-28", streamed, None)
    assert json.dumps(streamed_overlay, sort_keys=True) == json.dumps(resident_overlay, sort_keys=True)
    assert build_opportunity_sets(streamed["records"], None) == build_opportunity_sets(resident["records"], None)
    binding = bind_integrated_scenarios(session="2026-08-28", integrated_decision=streamed, tickers=["AAA"])
    resident_binding = bind_integrated_scenarios(session="2026-08-28", integrated_decision=resident, tickers=["AAA"])
    assert binding is not None and binding["artifact_identity"] == resident_binding["artifact_identity"]
    common = dict(session="2026-08-28", operation_identity="operation:fixture", producer_run_identity="run:fixture")
    resident_t0 = build_snapshot(integrated_artifact=resident, **common)
    streamed_t0 = build_snapshot(integrated_artifact=streamed, scratch_dir=tmp_path / "scratch", **common)
    published = write_immutable_snapshot(tmp_path / "t0", streamed_t0)
    assert published.read_bytes() == b"".join(_json_bytes(resident_t0, pretty=True))
    assert validate_snapshot(streamed_t0) is True
    assert validate_snapshot(resident_t0) is True
    recovered = recover(published, created_at="2026-10-28T00:00:00+07:00", diagnostic=True)
    assert recovered["artifact_identity"]
