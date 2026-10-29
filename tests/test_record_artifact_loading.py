"""Nested record envelopes keep graph fidelity and the frozen member refusals."""
import io
import json
from pathlib import Path

import pytest

from stocklookup_core.evidence import record_artifact_loading as loader
from stocklookup_core.evidence.artifact_stream import ObjectStream


ENVELOPES = (
    "financial_analysis_product",
    "valuation_balance_sheet_divergence_context",
    "metric_research_context",
)


@pytest.mark.parametrize("envelope", ENVELOPES)
@pytest.mark.parametrize("record_list", [False, True])
def test_nested_universe_exceeding_real_member_limit_is_record_bounded(tmp_path, monkeypatch, envelope, record_list):
    # Same shape as the retained evaluated valuation: a root universe and an
    # independent wrapped universe, each with complete opaque evidence.
    rows = {str(i): {"opaque": "ấ" * 1024**2, "types": [None, False, -0.0, 1e-9]} for i in range(17)}
    wrapped = {"status": "UNKNOWN", "records": list(rows.values()) if record_list else rows,
               "source_identity": "exact-original", "is_actionable": False}
    graph = {"records": {"Z": {"unknown": None}}, envelope: wrapped, "session": "2026-10-26"}
    path = tmp_path / "valuation.json"
    with path.open("w", encoding="utf-8") as target:
        json.dump(graph, target, ensure_ascii=False)
    maxima = []
    class ObservedStream(ObjectStream):
        def fill(self, size=64*1024):
            super().fill(size)
            maxima.append(len(self.buffer))
    monkeypatch.setattr(loader, "ObjectStream", ObservedStream)
    monkeypatch.setattr(Path, "read_text", lambda *a, **k: pytest.fail("whole-file text read"))
    assert loader.load_record_artifact(path) == graph
    assert max(maxima) < 4*1024**2  # independent of either complete universe


@pytest.mark.parametrize("size", [65535, 65536, 65537, 1024**2+1])
def test_nested_records_preserve_escaped_unicode_and_numbers_across_refills(tmp_path, size):
    graph = {"valuation_balance_sheet_divergence_context": {
        "records": {"Z": {"text": 'ấ\\\"\n' * (size//4), "number": -1.234e-12}, "A": {}},
        "after": [True, None]}, "after": "retained"}
    path = tmp_path / "valuation.json"
    path.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
    assert loader.load_record_artifact(path) == graph


@pytest.mark.parametrize("chunk", [1, 5, 13, 64, 65536])
def test_nested_envelope_survives_short_reads_and_number_boundaries(tmp_path, monkeypatch, chunk):
    graph = {"metric_research_context": {"records": [{"n": -1.234e-12}, {"n": 12345}], "x": "Việt"},
             "records": {}, "after": False}
    class ShortReads(io.StringIO):
        def read(self, n=-1):
            assert n >= 0
            return super().read(min(n, chunk))
    monkeypatch.setattr(Path, "open", lambda *a, **k: ShortReads(json.dumps(graph, ensure_ascii=False)))
    assert loader.load_record_artifact(tmp_path / "short.json") == graph


@pytest.mark.parametrize("text", [
    '{"valuation_balance_sheet_divergence_context":{"records":{"A":{},"A":{}}}}',
    '{"valuation_balance_sheet_divergence_context":{"records":{},"records":{}}}',
    '{"metric_research_context":{"records":[{},]}}',
    '{"valuation_balance_sheet_divergence_context":{"records":{"A":{}}}',
    '{"valuation_balance_sheet_divergence_context":{"records":{}}} {}',
    '{"valuation_balance_sheet_divergence_context":{"records":{"A":{bad}}}}',
])
def test_nested_malformed_duplicate_and_trailing_json_refuses(tmp_path, text):
    path = tmp_path / "bad.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        loader.load_record_artifact(path)


@pytest.mark.parametrize("location", ["record", "metadata", "wrapped_metadata", "record_named_envelope"])
def test_large_individual_members_still_refuse(tmp_path, location):
    oversized = "x" * (16*1024**2 + 1)
    if location == "record":
        graph = {"valuation_balance_sheet_divergence_context": {"records": {"A": {"text": oversized}}}}
    elif location == "record_named_envelope":
        graph = {"records": {"valuation_balance_sheet_divergence_context": {"records": {"A": oversized}}}}
    elif location == "wrapped_metadata":
        graph = {"valuation_balance_sheet_divergence_context": {"metadata": {"text": oversized}, "records": {}}}
    else:
        graph = {"metadata": {"text": oversized}, "records": {}}
    path = tmp_path / "large.json"
    with path.open("w", encoding="utf-8") as target:
        json.dump(graph, target)
    with pytest.raises(ValueError, match="ACCEPTANCE_JSON_MEMBER_LIMIT"):
        loader.load_record_artifact(path)


@pytest.mark.parametrize("value", [None, [], [1, "unknown"], "UNKNOWN", False, 2])
def test_non_object_envelopes_keep_their_original_types(tmp_path, value):
    graph = {key: value for key in ENVELOPES}
    path = tmp_path / "types.json"
    path.write_text(json.dumps(graph), encoding="utf-8")
    assert loader.load_record_artifact(path) == graph
