"""Observer-window record release and streamed immutable JSON for the 2026-11-19 capacity failure."""
import hashlib
import json
import tracemalloc
from pathlib import Path

import pytest

from flow_price_divergence_shadow import write_immutable
from tools.verify_retention_reader_transition import (
    OBSERVER_RESIDENT_RELEASE_PRIOR,
    OBSERVER_RESIDENT_RELEASE_SOURCE,
    _evaluated_input_prior_bytes,
    _observer_resident_release_prior_bytes,
)

ROOT = Path(__file__).resolve().parents[1]


def test_observers_release_sealed_records_and_presentation_receives_them(tmp_path, monkeypatch):
    from test_canonical_daily_operation import SESSION, _run

    product = {
        "contract_version": "integrated_investment_decision_product/v1",
        "session": SESSION,
        "artifact_identity": "integrated_investment_decision_product/v1:test",
        "records": {"AAA": {"ticker": "AAA"}},
    }
    sealed = tmp_path / "integrated_investment_decision_product.json"
    sealed.write_text(json.dumps(product), encoding="utf-8")
    seen = {}

    def enrichment(_root, session, **_kwargs):
        assert session == SESSION
        return {"integrated_investment_decision_product": {
            "status": "BUILT", "artifact": product, "path": sealed,
        }}

    def observers(*_args, **_kwargs):
        seen["during"] = "records" not in product
        return {
            "multi_session_signal_velocity": {"status": "UNAVAILABLE"},
            "current_foreign_flow_enrichment": {"status": "UNAVAILABLE"},
            "flow_price_divergence_shadow": {"status": "UNAVAILABLE"},
        }

    def presentation(*_args, **kwargs):
        seen["presented"] = kwargs["integrated_investment_decision_product"]
        return {"status": "UNAVAILABLE"}

    _run(tmp_path, monkeypatch, enrichment_fn=enrichment,
         post_handoff_observers_fn=observers, presentation_projection_fn=presentation)
    assert seen["during"] is True
    assert seen["presented"] is product
    assert product["records"] == {"AAA": {"ticker": "AAA"}}
    assert sealed.read_bytes()  # the sealed file itself is not rewritten


def test_feedback_keeps_records_released_until_presentation(tmp_path, monkeypatch):
    from test_canonical_daily_operation import SESSION, _run

    product = {
        "contract_version": "integrated_investment_decision_product/v1",
        "session": SESSION,
        "artifact_identity": "integrated_investment_decision_product/v1:test",
        "records": {"AAA": {"ticker": "AAA"}},
    }
    sealed = tmp_path / "integrated_investment_decision_product.json"
    sealed.write_text(json.dumps(product), encoding="utf-8")
    seen = {}

    def enrichment(_root, session, **_kwargs):
        return {"integrated_investment_decision_product": {
            "status": "BUILT", "artifact": product, "path": sealed,
        }}

    def observers(*_args, **_kwargs):
        seen["during"] = "records" not in product
        return {"multi_session_signal_velocity": {"status": "UNAVAILABLE"},
                "current_foreign_flow_enrichment": {"status": "UNAVAILABLE"},
                "flow_price_divergence_shadow": {"status": "UNAVAILABLE"}}

    def feedback(*_args, **_kwargs):
        seen["feedback"] = "records" not in product
        return {"status": "UNAVAILABLE"}

    def presentation(*_args, **kwargs):
        seen["presented"] = kwargs["integrated_investment_decision_product"]
        return {"status": "UNAVAILABLE"}

    _run(tmp_path, monkeypatch, enrichment_fn=enrichment,
         post_handoff_observers_fn=observers, post_handoff_feedback_fn=feedback,
         presentation_projection_fn=presentation)
    assert seen == {"during": True, "feedback": True, "presented": product}
    assert product["records"] == {"AAA": {"ticker": "AAA"}}


def test_restore_uses_the_bounded_reader_and_a_smaller_peak(tmp_path, monkeypatch):
    from canonical_daily_operation import _restore_resident_integrated_records

    product = {
        "contract_version": "integrated_investment_decision_product/v1",
        "session": "2026-11-19",
        "artifact_identity": "integrated_investment_decision_product/v1:peak",
        "records": {f"T{index:05d}": {"ticker": f"T{index:05d}", "note": "n" * 60, "n": index} for index in range(12000)},
    }
    path = tmp_path / "integrated_investment_decision_product.json"
    path.write_text(json.dumps(product, ensure_ascii=False), encoding="utf-8")
    text_size = path.stat().st_size
    assert text_size > 1_000_000

    def peak(callback):
        tracemalloc.start()
        callback()
        _current, high = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return high

    def naive():
        payload = json.loads(path.read_text(encoding="utf-8"))
        assert payload["records"]["T00000"]["n"] == 0

    def streamed():
        artifact = {key: value for key, value in product.items() if key != "records"}
        assert _restore_resident_integrated_records(artifact, path)
        assert artifact["records"] == product["records"]

    naive_peak = peak(naive)
    streamed_peak = peak(streamed)
    assert streamed_peak < naive_peak
    assert naive_peak - streamed_peak > text_size // 2

    def refuse_full_text(*_args, **_kwargs):
        raise AssertionError("full-file read_text")

    monkeypatch.setattr(Path, "read_text", refuse_full_text)
    artifact = {key: value for key, value in product.items() if key != "records"}
    assert _restore_resident_integrated_records(artifact, path) is True


def test_identity_mismatch_does_not_present_a_stripped_record_map(tmp_path, monkeypatch):
    from test_canonical_daily_operation import SESSION, _run

    product = {
        "contract_version": "integrated_investment_decision_product/v1",
        "session": SESSION,
        "artifact_identity": "integrated_investment_decision_product/v1:memory",
        "records": {"AAA": {"ticker": "AAA"}},
    }
    sealed = tmp_path / "integrated_investment_decision_product.json"
    sealed.write_text(json.dumps({**product, "artifact_identity": "integrated_investment_decision_product/v1:disk"}), encoding="utf-8")
    seen = {}

    def enrichment(_root, _session, **_kwargs):
        return {"integrated_investment_decision_product": {
            "status": "BUILT", "artifact": product, "path": sealed,
        }}

    def observers(*_args, **_kwargs):
        seen["during"] = "records" not in product
        return {"multi_session_signal_velocity": {"status": "UNAVAILABLE"},
                "current_foreign_flow_enrichment": {"status": "UNAVAILABLE"},
                "flow_price_divergence_shadow": {"status": "UNAVAILABLE"}}

    def presentation(*_args, **kwargs):
        seen["presented"] = kwargs["integrated_investment_decision_product"]
        return {"status": "UNAVAILABLE"}

    _run(tmp_path, monkeypatch, enrichment_fn=enrichment,
         post_handoff_observers_fn=observers, presentation_projection_fn=presentation)
    assert seen["during"] is True
    assert seen["presented"] is None


def test_streamed_immutable_json_matches_write_text_and_replaces_only_an_empty_file(tmp_path, monkeypatch):
    artifact = {"b": 1, "a": "é\n", "nested": {"z": 1, "a": [2, 1]}}
    text = json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    destination = tmp_path / "volume_and_flow_context.json"
    reference = tmp_path / "reference.json"
    reference.write_text(text, encoding="utf-8")
    assert write_immutable(destination, artifact) == destination
    assert destination.read_bytes() == reference.read_bytes()
    assert not destination.with_name(destination.name + ".partial").exists()
    write_immutable(destination, artifact)
    assert destination.read_bytes() == reference.read_bytes()
    destination.write_text(text.replace("1", "9", 1), encoding="utf-8")
    before = destination.read_bytes()
    with pytest.raises(ValueError, match="IMMUTABLE_ARTIFACT_CONFLICT"):
        write_immutable(destination, artifact)
    assert destination.read_bytes() == before
    assert not destination.with_name(destination.name + ".partial").exists()
    destination.write_bytes(b"")
    write_immutable(destination, artifact)
    assert destination.read_bytes() == reference.read_bytes()

    def refuse_full_string(*_args, **_kwargs):
        raise AssertionError("json.dumps must not copy a new artifact")

    monkeypatch.setattr(json, "dumps", refuse_full_string)
    fresh = tmp_path / "fresh.json"
    write_immutable(fresh, artifact)
    assert fresh.read_bytes() == reference.read_bytes()


def test_streamed_write_does_not_allocate_a_second_full_text(tmp_path):
    artifact = {"records": {f"T{index:05d}": {"name": "x" * 40, "n": index} for index in range(20000)}}
    text = json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n"
    assert len(text) > 1_000_000
    tracemalloc.start()
    write_immutable(tmp_path / "large.json", artifact)
    _current, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    assert peak < len(text)
    assert (tmp_path / "large.json").read_text(encoding="utf-8") == text


def test_observer_release_peel_returns_the_velocity_active_source():
    active = (ROOT / OBSERVER_RESIDENT_RELEASE_SOURCE).read_bytes().replace(b"\r\n", b"\n")
    prior = _observer_resident_release_prior_bytes(ROOT, OBSERVER_RESIDENT_RELEASE_SOURCE, active)
    assert hashlib.sha256(prior).hexdigest() == OBSERVER_RESIDENT_RELEASE_PRIOR
    assert hashlib.sha256(active).hexdigest() != OBSERVER_RESIDENT_RELEASE_PRIOR
    assert _observer_resident_release_prior_bytes(ROOT, "flow_price_divergence_shadow.py", active) == active
    assert _observer_resident_release_prior_bytes(ROOT, OBSERVER_RESIDENT_RELEASE_SOURCE, prior) == prior
    from tools.verify_retention_reader_transition import EVALUATED_INPUT_SOURCE
    import subprocess
    expected = subprocess.check_output(["git", "show", "ce188125:" + EVALUATED_INPUT_SOURCE], cwd=ROOT).replace(b"\r\n", b"\n")
    assert _evaluated_input_prior_bytes(ROOT, EVALUATED_INPUT_SOURCE, active) == expected


def test_observer_release_peel_passes_through_without_its_manifest(tmp_path):
    raw = b"older-source\n"
    assert _observer_resident_release_prior_bytes(tmp_path, OBSERVER_RESIDENT_RELEASE_SOURCE, raw) == raw


def test_observer_release_peel_refuses_a_widened_scope(tmp_path):
    manifest = "tests/fixtures/owner_daily_observer_resident_release_v1.json"
    target = tmp_path / manifest
    target.parent.mkdir(parents=True, exist_ok=True)
    spec = json.loads((ROOT / manifest).read_bytes())
    spec["scope"] = "UNBOUNDED"
    target.write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(ValueError, match="OBSERVER_RESIDENT_RELEASE_SOURCE_TRANSITION_SCOPE_INVALID"):
        _observer_resident_release_prior_bytes(tmp_path, OBSERVER_RESIDENT_RELEASE_SOURCE, b"anything\n")
