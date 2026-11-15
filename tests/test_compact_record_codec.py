import copy
import json
import random

import pytest

from bounded_artifact_stream import canonical_bytes
from stocklookup_core.evidence import compact_record_codec as codec


def _context(seed: int, width: int = 120) -> dict:
    rng = random.Random(seed)
    return {"lineage": {"source_artifact_identity": f"artifact:{seed:064x}"},
            "rows": [{"metric": f"m{index}", "value": rng.random(), "note": None, "flags": [index, str(index)]}
                     for index in range(width)]}


def _record() -> dict:
    valuation, fundamental = _context(1), _context(2)
    return {
        "ticker": "AAA",
        "evidence_axes": {"VALUATION": {"state": "X", "context": valuation},
                          "FUNDAMENTAL": {"state": None, "context": fundamental}},
        "current_research_decision_input": {"dimensions": {"VALUATION": copy.deepcopy(valuation),
                                                           "FUNDAMENTAL": copy.deepcopy(fundamental)}},
        "valuation_context": copy.deepcopy(valuation),
        "history": [copy.deepcopy(fundamental), {"unique": _context(3)}],
        "small": {"a": 1},
        "explicit_null": None,
    }


def test_round_trip_is_canonically_byte_equal_and_smaller():
    record = _record()
    before = canonical_bytes(record)
    envelope = codec.encode_record(record)
    assert canonical_bytes(record) == before  # input untouched
    wire = canonical_bytes(envelope)
    assert len(wire) < 0.55 * len(before)
    decoded = codec.decode_record(json.loads(wire))
    assert canonical_bytes(decoded) == before
    assert codec.logical_sha256(envelope) == codec.logical_sha256(record)
    assert len(envelope["blocks"]) == 2 and len(envelope["refs"]) == 6


def test_encoding_is_deterministic_under_key_order():
    record = _record()
    shuffled = json.loads(json.dumps(record, sort_keys=True))
    assert canonical_bytes(codec.encode_record(record)) == canonical_bytes(codec.encode_record(shuffled))


def test_expanded_blocks_are_independent_objects():
    decoded = codec.decode_record(codec.encode_record(_record()))
    decoded["valuation_context"]["rows"][0]["metric"] = "changed"
    assert decoded["evidence_axes"]["VALUATION"]["context"]["rows"][0]["metric"] == "m0"


def test_record_without_repetition_and_inline_reader_compatibility():
    record = {"ticker": "BBB", "only": _context(9), "explicit_null": None}
    envelope = codec.encode_record(record)
    assert envelope["refs"] == [] and envelope["blocks"] == []
    assert codec.decode_record(envelope) == record
    assert codec.expand_record(record) is record  # historical inline form passes through
    lookalike = {"compact_record": "something else", "literal": 1, "refs": [], "blocks": []}
    assert codec.expand_record(lookalike) is lookalike


def test_nested_repetition_keeps_only_the_outermost_reference():
    inner = _context(4)
    outer = {"inner_a": inner, "pad": _context(5)}
    record = {"x": copy.deepcopy(outer), "y": copy.deepcopy(outer), "z": copy.deepcopy(inner)}
    envelope = codec.encode_record(record)
    paths = [tuple(path) for path, _ in envelope["refs"]]
    assert ("x",) in paths and ("y",) in paths
    assert not any(path[:1] in {("x",), ("y",)} and len(path) > 1 for path in paths)
    assert canonical_bytes(codec.decode_record(envelope)) == canonical_bytes(record)


@pytest.mark.parametrize("mutate, reason", [
    (lambda e: e["refs"].append([["a"], 0]), "REFERENCE_DUPLICATE_OR_OVERLAPPING"),
    (lambda e: e["refs"].append([["a", "rows"], 0]), "REFERENCE_DUPLICATE_OR_OVERLAPPING"),
    (lambda e: e["refs"].__setitem__(0, [e["refs"][0][0], 99]), "REFERENCE_BLOCK_OUT_OF_RANGE"),
    (lambda e: e["refs"].__setitem__(0, [e["refs"][0][0], True]), "REFERENCE_SHAPE_INVALID"),
    (lambda e: e["refs"].__setitem__(0, [["missing", "path"], 0]), "REFERENCE_PATH_NOT_IN_LITERAL"),
    (lambda e: e["refs"].__setitem__(0, [["ticker"], 0]), "REFERENCE_PLACEHOLDER_INVALID"),
    (lambda e: e["refs"].__setitem__(0, [["history", "0"], 0]), "REFERENCE_PATH_NOT_IN_LITERAL"),
    (lambda e: e["blocks"].append({"orphan": 1}), "BLOCK_NOT_SHARED"),
    (lambda e: e["blocks"].__setitem__(0, "text"), "BLOCK_NOT_A_CONTAINER"),
    (lambda e: e["refs"].pop(), "BLOCK_NOT_SHARED"),
])
def test_malformed_envelopes_are_refused(mutate, reason):
    record = {"a": _context(1), "b": _context(1), "ticker": "AAA", "history": [None]}
    envelope = codec.encode_record(record)
    assert len(envelope["refs"]) == 2
    mutate(envelope)
    with pytest.raises(codec.CompactRecordError, match=reason):
        codec.decode_record(envelope)


def test_non_envelopes_and_double_encoding_are_refused():
    with pytest.raises(codec.CompactRecordError, match="NOT_A_COMPACT_RECORD"):
        codec.decode_record({"compact_record": codec.VERSION, "literal": {}, "refs": [], "blocks": [], "extra": 1})
    envelope = codec.encode_record(_record())
    with pytest.raises(codec.CompactRecordError, match="RECORD_ALREADY_COMPACT"):
        codec.encode_record(envelope)


def test_dropping_a_reference_changes_the_logical_hash():
    record = {"a": _context(1), "b": _context(1), "c": _context(1)}
    envelope = codec.encode_record(record)
    envelope["refs"].pop()
    # Still structurally valid (two uses), but the unexpanded placeholder stays null,
    # so the caller's existing identity check over the expanded record fails.
    assert codec.logical_sha256(envelope) != codec.logical_sha256(record)
