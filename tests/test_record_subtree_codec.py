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
    assert files["record_encoding"] == "record_subtree_refs/v1"
    assert "record_encoding" not in json.loads(plain["manifest"])["files"]["ai_research_full_universe.ndjson"]


def test_readers_expand_encoded_rows(tmp_path):
    from stocklookup_core.research.ai_research_ticker_extractor import _lookup_ndjson
    record = _record()
    path = tmp_path / "u.ndjson"
    path.write_text(canon({"ticker": "AAA"}) + "\n" + canon(encode_record(record)) + "\n", encoding="utf-8")
    assert _lookup_ndjson(path, {"HPG"})["HPG"] == record


def _m1_delivery(tmp_path, monkeypatch, *, codec):
    from pathlib import Path
    import ai_research_session_delivery as delivery
    from tests.test_ai_research_session_delivery import _accounting_delivery_inputs
    with monkeypatch.context() as isolated:
        isolated.setattr(Path, "home", lambda: tmp_path)
        from tools import run_owner_daily as workflow
    session = "2026-10-15"
    monkeypatch.setattr(delivery, "owner_focus_tickers", lambda: ("AAA",))
    monkeypatch.setattr(delivery, "encode_record", lambda record: encode_record(record, min_bytes=32))
    operation, integrated, brief, inputs = _accounting_delivery_inputs(session)
    result = delivery.build_delivery(operation, inputs, full_universe_subtree_codec=codec)
    root = tmp_path / ("coded" if codec else "plain")
    root.mkdir()
    (root / delivery.PRIMARY_HUMAN_REVIEW_FILENAME).write_bytes(result["primary"])
    (root / delivery.FULL_UNIVERSE_LOOKUP_FILENAME).write_bytes(result["full_universe"])
    overlay = delivery.project_integrated_decision_delivery_overlay(session, integrated, brief)
    authority = {"operation_identity": operation["manifest"]["operation_identity"],
                 "product_identity": operation["product"]["artifact_identity"],
                 "overlay_header": overlay, "projections": overlay.pop("records"),
                 "scoped": ["AAA"], "owner_focus": ["AAA"], "full_universe": ["AAA"]}
    return workflow, root, session, authority, result


def test_owner_daily_m1_verifier_accepts_encoded_rows_and_matches_plain(tmp_path, monkeypatch):
    workflow, plain, session, authority, plain_out = _m1_delivery(tmp_path, monkeypatch, codec=False)
    _, coded, _, _, coded_out = _m1_delivery(tmp_path, monkeypatch, codec=True)
    row = json.loads(coded_out["full_universe"])
    assert CODEC_KEY in row and REF_KEY.encode() in coded_out["full_universe"]
    assert REF_KEY in json.dumps(row["integrated_decision_v1"])  # the verifier really has to decode
    assert canon(decode_record(row)) + "\n" == plain_out["full_universe"].decode("utf-8")
    expected = {"ticker_research_contexts": 1, "owner_focus_research_contexts": 1, "full_universe_rows": 1}
    assert workflow._verify_m1_ai_delivery(plain, session, authority) == expected
    assert workflow._verify_m1_ai_delivery(coded, session, authority) == expected


@pytest.mark.parametrize("damage", ["pointer", "version", "truncated", "extra_ref_key", "marker_type"])
def test_owner_daily_m1_verifier_refuses_damaged_encoded_rows(tmp_path, monkeypatch, damage):
    workflow, _, session, authority, out = _m1_delivery(tmp_path, monkeypatch, codec=True)
    coded = tmp_path / "coded"
    path = coded / "ai_research_full_universe.ndjson"
    text = out["full_universe"].decode("utf-8")
    row = json.loads(text)
    if damage == "truncated":  # interrupted write: a partial final line
        path.write_text(text[: len(text) // 2], encoding="utf-8")
    else:
        if damage == "version":
            row[CODEC_KEY] = "record_subtree_refs/v999"
        elif damage == "marker_type":
            row[CODEC_KEY] = {"version": "record_subtree_refs/v1"}
        else:
            ref = next(v for v in _walk_refs(row))
            if damage == "pointer":
                ref[REF_KEY] = "/does/not/exist"
            else:
                ref["value"] = 1
        path.write_text(canon(row) + "\n", encoding="utf-8")
    with pytest.raises(workflow.OwnerDailyError, match="M1_AI_FULL_UNIVERSE_COMPANION_UNREADABLE"):
        workflow._verify_m1_ai_delivery(coded, session, authority)


def _walk_refs(value):
    if isinstance(value, dict):
        if REF_KEY in value:
            yield value
        for item in value.values():
            yield from _walk_refs(item)
    elif isinstance(value, list):
        for item in value:
            yield from _walk_refs(item)


@pytest.mark.parametrize("tamper", [None, "live", "archive", "scope"])
def test_launcher_decode_transition_conserves_the_exact_prior_source(tmp_path, tamper):
    import hashlib
    import shutil
    from pathlib import Path
    from tools.verify_retention_reader_transition import (
        SUBTREE_CODEC_LAUNCHER_MANIFEST, _subtree_codec_launcher_prior_bytes)
    root = Path(__file__).resolve().parents[1]
    spec = json.loads((root / SUBTREE_CODEC_LAUNCHER_MANIFEST).read_bytes())
    relative = "tools/run_owner_daily.py"
    archive = spec["sources"][relative]["archive"]
    for name in (SUBTREE_CODEC_LAUNCHER_MANIFEST, relative, archive,
                 "tests/fixtures/registry_migration_v1/run_owner_daily_source_transition_v1.json",
                 "tests/fixtures/registry_migration_v1/run_owner_daily.py.txt"):
        (tmp_path / name).parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(root / name, tmp_path / name)
    active = (tmp_path / relative).read_bytes().replace(b"\r\n", b"\n")
    if tamper == "live":
        active += b"# unreviewed\n"
    elif tamper == "archive":
        (tmp_path / archive).write_bytes(b"bad")
    elif tamper == "scope":
        spec["scope"] = "UNBOUNDED"
        (tmp_path / SUBTREE_CODEC_LAUNCHER_MANIFEST).write_text(json.dumps(spec))
    if tamper:
        with pytest.raises(ValueError, match="SUBTREE_CODEC_LAUNCHER_SOURCE_"):
            _subtree_codec_launcher_prior_bytes(tmp_path, relative, active)
        return
    prior = _subtree_codec_launcher_prior_bytes(tmp_path, relative, active)
    assert hashlib.sha256(prior).hexdigest() == spec["sources"][relative]["prior_sha256_lf"]
    assert b"decode_record" not in prior and b"decode_record" in active
    assert _subtree_codec_launcher_prior_bytes(tmp_path, "canonical_daily_operation.py", b"x") == b"x"
