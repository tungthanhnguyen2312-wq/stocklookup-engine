import json
from copy import deepcopy

import pytest

from stocklookup_core.evidence.record_subtree_codec import (
    CODEC_KEY, REF_KEY, RecordSubtreeCodecError, decode_record, encode_record,
)


def canon(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _record():
    axis = {"status": "AVAILABLE", "facts": [{"metric": f"m{i}", "value": i * 1.5, "note": "Lợi nhuận"} for i in range(40)]}
    return {"ticker": "HPG", "evidence_axes": {"VALUATION": deepcopy(axis), "FUNDAMENTAL": {"inner": deepcopy(axis)}},
            "integrated_decision_v1": {"decision_identity": "decision:HPG:1", "valuation": deepcopy(axis),
                                       "list": [deepcopy(axis), deepcopy(axis)]},
            "small": [{"a": 1}, {"a": 1}]}


def test_round_trip_is_byte_exact_deterministic_and_smaller():
    record = _record()
    saved = deepcopy(record)
    encoded = encode_record(record)
    assert record == saved  # input untouched
    assert encoded[CODEC_KEY] == "record_subtree_refs/v1"
    assert encoded["ticker"] == "HPG"  # scalar lookup keys are never referenced
    assert len(canon(encoded)) < len(canon(record)) / 3
    assert canon(encode_record(deepcopy(record))) == canon(encoded)
    decoded = decode_record(json.loads(canon(encoded)))
    assert canon(decoded) == canon(record)
    assert decoded["small"] == [{"a": 1}, {"a": 1}]  # below threshold: kept inline
    assert REF_KEY not in canon(decoded)


def test_decoded_repeats_are_independent_containers():
    decoded = decode_record(encode_record(_record()))
    decoded["integrated_decision_v1"]["valuation"]["facts"].append("mutation")
    assert decoded["evidence_axes"]["VALUATION"]["facts"][-1] != "mutation"
    assert decoded["integrated_decision_v1"]["list"][0]["facts"][-1] != "mutation"


@pytest.mark.parametrize("other", [1.0, True, "1", None])
def test_scalar_types_never_alias(other):
    base = {"facts": [{"value": 1, "pad": "x" * 30} for _ in range(40)]}
    variant = {"facts": [{"value": other, "pad": "x" * 30} for _ in range(40)]}
    record = {"ticker": "A", "a": base, "b": variant}
    decoded = decode_record(json.loads(canon(encode_record(record))))
    assert canon(decoded) == canon(record)
    assert type(decoded["b"]["facts"][0]["value"]) is type(other)


def test_legacy_and_reserved_key_records_are_not_reinterpreted():
    legacy = _record()
    assert decode_record(legacy) is legacy
    clash = _record() | {"user": {REF_KEY: "/ticker"}}
    encoded = encode_record(clash)
    assert CODEC_KEY not in encoded and encoded == clash
    assert decode_record(encoded) == clash


@pytest.mark.parametrize("tamper", ["missing", "forward", "extra", "version"])
def test_malformed_references_refuse(tamper):
    encoded = json.loads(canon(encode_record(_record())))
    text = canon(encoded)
    if tamper == "version":
        encoded[CODEC_KEY] = "record_subtree_refs/v0"
    else:
        ref = encoded["integrated_decision_v1"]["valuation"]
        assert set(ref) == {REF_KEY}
        if tamper == "missing":
            ref[REF_KEY] = "/nope"
        elif tamper == "forward":
            ref[REF_KEY] = "/small/0"
        else:
            ref["x"] = 1
    with pytest.raises(RecordSubtreeCodecError):
        decode_record(encoded)
    assert text  # original encoded text unaffected


def test_delivery_switch_preserves_every_logical_row_and_hashes_written_bytes(monkeypatch):
    import hashlib
    import ai_research_session_delivery as delivery
    from tests.test_ai_research_session_delivery import _daily_brief_fixture, _integrated_delivery_fixture, _operation
    iid = _integrated_delivery_fixture()
    inputs = {"descriptive": {"records": {"AAA": {}, "BBB": {}}}, "tactical": {"records": {}},
              "fundamental": {"records": {}}, "valuation": {"records": {}},
              "integrated_investment_decision_product": iid, "daily_integrated_decision_brief": _daily_brief_fixture(iid)}
    plain = delivery.build_delivery(_operation(), deepcopy(inputs))
    assert delivery.build_delivery(_operation(), deepcopy(inputs), full_universe_subtree_codec=False) == plain
    real = delivery.encode_record
    monkeypatch.setattr(delivery, "encode_record", lambda record: real(record, min_bytes=32))
    coded = delivery.build_delivery(_operation(), deepcopy(inputs), full_universe_subtree_codec=True)
    assert coded["primary"] == plain["primary"] and coded["projection"] == plain["projection"]
    assert coded["full_universe"] != plain["full_universe"]
    assert REF_KEY.encode() in coded["full_universe"]
    expanded = [canon(decode_record(json.loads(line))) for line in coded["full_universe"].splitlines()]
    assert expanded == [line.decode("utf-8") for line in plain["full_universe"].splitlines()]
    files = json.loads(coded["manifest"])["files"]["ai_research_full_universe.ndjson"]
    assert files["sha256"] == hashlib.sha256(coded["full_universe"]).hexdigest()
    assert files["bytes"] == len(coded["full_universe"])


def test_readers_expand_encoded_rows(tmp_path):
    from stocklookup_core.research.ai_research_ticker_extractor import _lookup_ndjson
    record = _record()
    path = tmp_path / "u.ndjson"
    path.write_text(canon({"ticker": "AAA"}) + "\n" + canon(encode_record(record)) + "\n", encoding="utf-8")
    assert _lookup_ndjson(path, {"HPG"})["HPG"] == record
