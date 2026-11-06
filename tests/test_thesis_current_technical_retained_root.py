import pytest

from stocklookup_core.research import thesis_evidence_production as thesis

SESSION = "2026-11-06"
REL = ("operations-review", "canonical-post-close-v1", SESSION, "enrichment", "historical_context.json")


def place(base, data=b"{}"):
    path = base.joinpath(*REL)
    path.parent.mkdir(parents=True)
    path.write_bytes(data)
    return path


def test_finds_batch_under_retained_root_not_only_producer_checkout(tmp_path, monkeypatch):
    monkeypatch.delenv("STOCK_LOOKUP_RETAINED_EVIDENCE_ROOT", raising=False)
    monkeypatch.delenv("STOCK_LOOKUP_OPERATION_OUTPUT_ROOT", raising=False)
    producer, retained = tmp_path / "stock-core-private", tmp_path / "retained-evidence"
    producer.mkdir()
    expected = place(retained)
    # 2026-11-06 production layout: the old lookup returned None here.
    assert thesis.enrichment_historical_context_path(producer, SESSION) is None
    assert thesis.enrichment_historical_context_path(producer, SESSION, retained) == expected
    monkeypatch.setenv("STOCK_LOOKUP_RETAINED_EVIDENCE_ROOT", str(retained))
    assert thesis.enrichment_historical_context_path(producer, SESSION).resolve() == expected.resolve()


def test_two_different_copies_refuse_and_identical_copies_resolve(tmp_path, monkeypatch):
    monkeypatch.delenv("STOCK_LOOKUP_RETAINED_EVIDENCE_ROOT", raising=False)
    producer, retained = tmp_path / "p", tmp_path / "r"
    first = place(producer, b'{"a":1}')
    place(retained, b'{"a":1}')
    assert thesis.enrichment_historical_context_path(producer, SESSION, retained) == first
    retained.joinpath(*REL).write_bytes(b'{"a":2}')
    with pytest.raises(ValueError, match="THESIS_ENRICHMENT_CONTEXT_AMBIGUOUS"):
        thesis.enrichment_historical_context_path(producer, SESSION, retained)


def _successor_copy(tmp_path):
    import shutil
    from pathlib import Path
    from tools import verify_retention_reader_transition as v
    repo = Path(__file__).resolve().parents[1]
    for rel in (v.THESIS_SOURCE, v.THESIS_ARCHIVE, v.THESIS_MANIFEST, v.THESIS_ROOT_MANIFEST, v.THESIS_ROOT_ARCHIVE,
                "tests/fixtures/e2e3_frozen_sources.json"):
        target = tmp_path / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(repo / rel, target)
    return v


def test_successor_peels_live_bytes_back_to_prior_active_pin(tmp_path):
    v = _successor_copy(tmp_path)
    import hashlib
    prior = v.historical_bytes(tmp_path, v.THESIS_SOURCE)
    assert hashlib.sha256(prior).hexdigest() == "10aea634a50e83d5e8db4951155c5a7b6f753e3f091305bf7bee1ecadc463367"


def test_successor_refuses_tampered_live_source_or_scope(tmp_path):
    import json
    v = _successor_copy(tmp_path)
    live = tmp_path / v.THESIS_SOURCE
    live.write_bytes(live.read_bytes() + b"\n# drift\n")
    with pytest.raises(ValueError, match="THESIS_ROOT_SOURCE_TRANSITION_BINDING_INVALID"):
        v.historical_bytes(tmp_path, v.THESIS_SOURCE)
    manifest = tmp_path / v.THESIS_ROOT_MANIFEST
    spec = json.loads(manifest.read_bytes())
    spec["release_authority"] = "GRANTED"
    manifest.write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(ValueError, match="THESIS_ROOT_SOURCE_TRANSITION_SCOPE_INVALID"):
        v.historical_bytes(tmp_path, v.THESIS_SOURCE)
