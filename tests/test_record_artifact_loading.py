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


def test_repeated_schema_and_lineage_strings_share_storage_without_sharing_mutable_rows(tmp_path):
    key = 'schema_field_' * 12
    label = 'unchanged retained source and research status ' * 7
    graph = {'records': {str(n): {key: {'label': label, 'list': [label, [label]], 'n': -0.0}}
                         for n in range(1500)}, 'metadata': [None, False, 1e-9]}
    path = tmp_path/'repeated.json'
    with path.open('w', encoding='utf-8') as target:
        json.dump(graph, target, ensure_ascii=False)
    loaded = loader.load_record_artifact(path)
    assert loaded == graph
    rows = list(loaded['records'].values())
    assert len({id(next(iter(row))) for row in rows}) == 1
    assert len({id(row[key]['label']) for row in rows}) == 1
    assert rows[0][key]['list'][1][0] is rows[1][key]['label']
    rows[0][key]['list'].append('local mutation')
    rows[0][key]['n'] = 100
    assert rows[1][key] == graph['records']['1'][key]
    # High cardinality and keys outside the sharing bound remain native/exact.
    other = {'records': {'A': {'x'*260+str(n): ['unique'+str(n), n] for n in range(9000)}}}
    with path.open('w', encoding='utf-8') as target:
        json.dump(other, target)
    assert loader.load_record_artifact(path) == other


def test_periodic_semantic_jsonl_uses_the_same_bounded_sharing_without_changing_flow_gate(tmp_path):
    import gzip
    from types import SimpleNamespace
    import canonical_daily_financial_v2_materialization as materialization
    rows = [{'ticker': 'AAA', 'source_lineage': {'provider': 'VCI'},
             'period_semantic_state': 'POINT_IN_TIME_BALANCE_SHEET',
             'unknown': ['retained native lineage '+str(1), [None, False, -0.0, 1e-9]]}
            for _ in range(50)]
    artifact = tmp_path/'semantics.json'
    artifact.write_text('{"artifact_identity":"native-semantic:1"}', encoding='utf-8')
    facts = tmp_path/'facts.jsonl.gz'
    with gzip.open(facts, 'wt', encoding='utf-8') as stream:
        stream.write('\n')
        for row in rows:
            stream.write(json.dumps(row)+'\n')
    authority = SimpleNamespace(semantics_artifact_path=artifact,
        expected_semantics_identity='native-semantic:1', semantics_facts_path=facts)
    actual, header = materialization.load_semantic_rows(authority)
    expected, _ = materialization.scaleout.qualified_flow.gate_kbs_period_alignment(rows)
    assert actual == expected and header == {'artifact_identity': 'native-semantic:1'}
    assert actual[0]['unknown'][0] is actual[1]['unknown'][0]
    actual[0]['unknown'][1].append('local change')
    assert actual[1] == expected[1]


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


def test_selected_records_preserve_metadata_and_all_requested_rows(tmp_path):
    graph = {"records": {"A": {"x": "Việt"}, "B": None}, "cards": {"B": {}},
             "financial_analysis_product": {"artifact_identity": "original", "records": {
                 "A": {"income": [1, None, True]}, "B": {"income": 2}}},
             "coverage": {"count": 2}, "other": {"records": {"B": "metadata"}}}
    path = tmp_path / "selected.json"
    path.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")
    expected = {**graph, "records": {"A": graph["records"]["A"]},
                "financial_analysis_product": {**graph["financial_analysis_product"],
                    "records": {"A": graph["financial_analysis_product"]["records"]["A"]}}}
    assert loader.load_record_artifact(path, record_tickers=["A", "MISSING"]) == expected
    assert loader.load_record_artifact(path) == graph


@pytest.mark.parametrize("text", [
    '{"records":{"A":{},"DROP":{bad}}}',
    '{"records":{"DROP":{},"DROP":{}}}',
    '{"records":{"DROP":{}}} {}',
    '{"financial_analysis_product":{"records":{"DROP":{bad}}}}',
])
def test_discarded_records_are_still_validated(tmp_path, text):
    path = tmp_path / "discarded.json"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError):
        loader.load_record_artifact(path, record_tickers=["A"])


def test_discarded_oversized_record_still_refuses(tmp_path):
    path = tmp_path / "oversized-discarded.json"
    path.write_text('{"records":{"DROP":"' + 'x' * (16*1024**2 + 1) + '"}}', encoding="utf-8")
    with pytest.raises(ValueError, match="ACCEPTANCE_JSON_MEMBER_LIMIT"):
        loader.load_record_artifact(path, record_tickers=[])
