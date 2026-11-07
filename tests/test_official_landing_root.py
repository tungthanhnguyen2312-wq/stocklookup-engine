"""Profiled Production resolves retained official-filing landing evidence under its own
retained role and never falls back to the legacy (C:) default or the runtime root."""
import json
from pathlib import Path

import pytest

import runtime_paths
from financial_evidence_currency_contract import DEFAULT_LANDING_ROOT, LANDING_DOMAIN
from tests.test_official_financial_source_integrity import proved_fixture


def _profile(monkeypatch, retained: Path):
    monkeypatch.setattr(runtime_paths, "workspace_profile",
                        lambda **_k: {"paths": {"retained": retained, "runtime": retained.parent / "runtime"}})


def test_profile_resolves_under_retained_role(monkeypatch, tmp_path):
    _profile(monkeypatch, tmp_path / "retained-evidence")
    root = runtime_paths.official_landing_root(LANDING_DOMAIN, DEFAULT_LANDING_ROOT)
    assert root == (tmp_path / "retained-evidence" / "data-landing" / LANDING_DOMAIN).resolve()


def test_unprofiled_keeps_legacy_default_and_never_uses_runtime_root(monkeypatch, tmp_path):
    monkeypatch.setattr(runtime_paths, "workspace_profile", lambda **_k: None)
    monkeypatch.setenv(runtime_paths.RUNTIME_ROOT_ENV, str(tmp_path / "dashboard-runtime"))
    legacy = tmp_path / "legacy" / LANDING_DOMAIN
    assert runtime_paths.official_landing_root(LANDING_DOMAIN, legacy) == legacy.resolve()


@pytest.mark.parametrize("domain", ["", "a/b", "..", "a\\b"])
def test_domain_must_be_one_segment(monkeypatch, domain):
    monkeypatch.setattr(runtime_paths, "workspace_profile", lambda **_k: None)
    with pytest.raises(ValueError):
        runtime_paths.official_landing_root(domain, "x")


def _write_landing(root: Path, context):
    root.mkdir(parents=True)
    (root / "fixture.pdf").write_bytes(context["retained_bytes"])
    (root / "official_document_acquisition_manifest.json").write_text(
        json.dumps({"records": [context["source_record"]]}), encoding="utf8")


def test_profiled_admission_replays_from_retained_landing_only(monkeypatch, tmp_path):
    from stocklookup_core.evidence import official_document_qualification as odq
    row, context = proved_fixture("2026-H1", native_pdf=True)
    explicit = tmp_path / "explicit"
    _write_landing(explicit, context)
    expected = odq.admit_retained_financial_fact(row, evidence_root=explicit, registry=context["registry"])

    retained = tmp_path / "retained-evidence"
    _write_landing(retained / "data-landing" / LANDING_DOMAIN, context)
    _profile(monkeypatch, retained)
    got = odq.admit_retained_financial_fact(row, registry=context["registry"])
    assert got == expected
    assert "RETAINED_SOURCE_PROOF_UNAVAILABLE" not in got.get("reason_codes", [])


def test_profiled_admission_does_not_fall_back_to_legacy_or_runtime(monkeypatch, tmp_path):
    """Evidence present only at the legacy or runtime location stays unproved under a profile."""
    import financial_evidence_currency_contract as contract
    from stocklookup_core.evidence import official_document_qualification as odq
    row, context = proved_fixture("2026-H1", native_pdf=True)
    legacy = tmp_path / "legacy" / LANDING_DOMAIN
    _write_landing(legacy, context)
    _write_landing(tmp_path / "runtime", context)
    monkeypatch.setattr(contract, "DEFAULT_LANDING_ROOT", str(legacy))
    _profile(monkeypatch, tmp_path / "retained-evidence")
    got = odq.admit_retained_financial_fact(row, registry=context["registry"])
    assert got["state"] != "ADMITTED"
    assert "RETAINED_SOURCE_PROOF_UNAVAILABLE" in got["reason_codes"]
