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
