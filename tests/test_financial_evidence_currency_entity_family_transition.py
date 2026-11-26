"""Exact HAH family/issuer-locator E6 transition; no release authority."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
from urllib.parse import urlsplit

import pytest

from tools.verify_retention_reader_transition import (
    FINANCIAL_EVIDENCE_CURRENCY_CONTRACT_ARCHIVE as ARCHIVE,
    FINANCIAL_EVIDENCE_CURRENCY_CONTRACT_MANIFEST as MANIFEST,
    FINANCIAL_EVIDENCE_CURRENCY_CONTRACT_SOURCE as SOURCE,
    _financial_evidence_currency_entity_family_structure_valid as structure_valid,
    historical_bytes,
)

ROOT = Path(__file__).resolve().parents[1]
ERROR = "FINANCIAL_EVIDENCE_CURRENCY_CONTRACT_SOURCE_TRANSITION_"


def _copy_transition(root):
    for relative in (SOURCE, ARCHIVE, MANIFEST):
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / relative).read_bytes())
    return json.loads((root / MANIFEST).read_bytes())


def test_hah_transition_reconstructs_exact_e6_baseline():
    spec = json.loads((ROOT / MANIFEST).read_bytes())
    original = subprocess.check_output(
        ["git", "show", spec["base_commit"] + ":" + SOURCE], cwd=ROOT,
    ).replace(b"\r\n", b"\n")
    active = spec["registry_snapshot_transition"]["prior_source_lf"].encode("utf-8")
    assert (ROOT / ARCHIVE).read_bytes().replace(b"\r\n", b"\n") == original
    assert historical_bytes(ROOT, SOURCE) == original
    assert structure_valid(original, active)
    assert original != active
    assert hashlib.sha256(original).hexdigest() == spec["prior_sha256_lf"]
    assert hashlib.sha256(active).hexdigest() == spec["active_sha256_lf"]
    assert spec["added_tickers"] == ["HAH"]
    assert spec["release_authority"] == "NOT_GRANTED"
    assert spec["scope"] == "DECISION2_HAH_CORPORATE_ENTITY_FAMILY_AND_EXACT_ISSUER_LOCATORS"
    prior_declarations = {node.target.id: ast.literal_eval(node.value)
                          for node in ast.parse(original).body
                          if isinstance(node, ast.AnnAssign)
                          and node.target.id in {"DIRECT_TARGET_LOCATORS", "COHORT"}}
    active_declarations = {node.target.id: ast.literal_eval(node.value)
                           for node in ast.parse(active).body
                           if isinstance(node, ast.AnnAssign)
                           and node.target.id in {"DIRECT_TARGET_LOCATORS", "COHORT"}}
    added = spec["added_locators"]
    assert len(added) == 3
    assert [item["period"] for item in added] == ["2025", "2025-H1", "2026-H1"]
    assert all(item["ticker"] == "HAH" for item in added)
    assert [item["document_class"] for item in added] == [
        "audited_annual_financial_statements",
        "reviewed_interim_financial_statements",
        "reviewed_interim_financial_statements",
    ]
    assert {urlsplit(item["url"]).hostname for item in added} == {"haiants.vn"}
    assert active_declarations["DIRECT_TARGET_LOCATORS"] == (
        prior_declarations["DIRECT_TARGET_LOCATORS"] + tuple(added))
    assert "HAH" not in active_declarations["COHORT"]
    profile, manifest = spec["host_evidence_refs"]
    assert profile == {
        "path": "data-landing/gemini-research-20261126/host-ownership-evidence/HAH_hsx_profile.md",
        "sha256": "026201e4f2ee817ee571b186a47d44ed1fe4a2d97b07530edf4b60e9dfd8db00",
        "source_url": "https://www.hsx.vn/en/quan-ly-niem-yet/co-phieu/HAH/2649",
        "declared_website": "www.haiants.vn",
    }
    assert manifest == {
        "path": ("data-landing/official-financial-filings-v1/acquisition-batch3-20261126/"
                 "official_document_acquisition_manifest.json"),
        "sha256": "882204b02bb7932aa7e10e5c8f06e9696621eabce9417d7d61c365e6978955aa",
    }
    assert len(spec["evidence_refs"]) == 3
    for evidence in spec["evidence_refs"]:
        readers = evidence["readers"]
        assert len(readers) == 2
        assert readers[0]["form_reference_literal"] == readers[1]["form_reference_literal"]
        assert readers[0]["form_reference_literal"] in {
            "MẪU SỐ B 02-DN/HN", "MẪU SỐ B 02a-DN/HN",
        }


@pytest.mark.parametrize("target", [SOURCE, ARCHIVE])
def test_hah_transition_rejects_tampered_bytes(tmp_path, target):
    _copy_transition(tmp_path)
    path = tmp_path / target
    path.write_bytes(path.read_bytes() + b"# tampered\n")
    with pytest.raises(ValueError, match=ERROR + "BINDING_INVALID"):
        historical_bytes(tmp_path, SOURCE)


@pytest.mark.parametrize("tamper", [
    "release", "added_tickers", "evidence", "extra_field", "prior_hash", "active_hash",
    "added_locators", "locator_url", "locator_ticker", "host_profile", "host_manifest",
])
def test_hah_transition_rejects_tampered_spec(tmp_path, tamper):
    spec = _copy_transition(tmp_path)
    if tamper == "release":
        spec["release_authority"] = "GRANTED"
    elif tamper == "added_tickers":
        spec["added_tickers"].append("BWE")
    elif tamper == "evidence":
        spec["evidence_refs"][0]["document_sha256"] = "0" * 64
    elif tamper == "extra_field":
        spec["extra"] = True
    elif tamper == "added_locators":
        spec["added_locators"].append(dict(spec["added_locators"][0]))
    elif tamper == "locator_url":
        spec["added_locators"][0]["url"] += "?changed"
    elif tamper == "locator_ticker":
        spec["added_locators"][0]["ticker"] = "BWE"
    elif tamper in {"host_profile", "host_manifest"}:
        spec["host_evidence_refs"][tamper == "host_manifest"]["sha256"] = "0" * 64
    else:
        target = ARCHIVE if tamper == "prior_hash" else SOURCE
        path = tmp_path / target
        path.write_bytes(path.read_bytes() + b"# tampered and rebound\n")
        field = "prior_sha256_lf" if tamper == "prior_hash" else "active_sha256_lf"
        spec[field] = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    (tmp_path / MANIFEST).write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(ValueError, match=ERROR + "(?:SCOPE|BINDING)_INVALID"):
        historical_bytes(tmp_path, SOURCE)


@pytest.mark.parametrize("tamper", [
    "extra_key", "existing_family", "hah_family", "duplicate_key", "selector", "missing_hah",
])
def test_hah_transition_refuses_non_allowlisted_structure(tmp_path, tamper):
    _copy_transition(tmp_path)
    path = tmp_path / SOURCE
    transition = json.loads((tmp_path / MANIFEST).read_bytes())
    active = transition["registry_snapshot_transition"]["prior_source_lf"].encode("utf-8")
    original_successor = active
    hah = b'    "HAH": "corporate",\n'
    if tamper == "extra_key":
        active = active.replace(hah, hah + b'    "BWE": "corporate",\n', 1)
    elif tamper == "existing_family":
        active = active.replace(b'"VCB": "bank"', b'"VCB": "corporate"', 1)
    elif tamper == "hah_family":
        active = active.replace(hah, b'    "HAH": "bank",\n', 1)
    elif tamper == "duplicate_key":
        active = active.replace(hah, hah + hah, 1)
    elif tamper == "selector":
        active = active.replace(b'FINANCIAL_V2_PIN_TICKER_THRESHOLD = 5',
                                b'FINANCIAL_V2_PIN_TICKER_THRESHOLD = 4', 1)
    else:
        active = active.replace(hah, b"", 1)
    assert active != original_successor
    transition["registry_snapshot_transition"]["prior_source_lf"] = active.decode("utf-8")
    (tmp_path / MANIFEST).write_text(json.dumps(transition), encoding="utf-8")
    prior = (tmp_path / ARCHIVE).read_bytes().replace(b"\r\n", b"\n")
    assert not structure_valid(prior, active)
    with pytest.raises(ValueError, match=ERROR + "BINDING_INVALID"):
        historical_bytes(tmp_path, SOURCE)


@pytest.mark.parametrize("tamper", [
    "extra_locator", "changed_url", "other_ticker", "missing_locator", "duplicate_locator",
])
def test_hah_transition_refuses_non_allowlisted_locators(tmp_path, tamper):
    _copy_transition(tmp_path)
    path = tmp_path / SOURCE
    transition = json.loads((tmp_path / MANIFEST).read_bytes())
    tree = ast.parse(transition["registry_snapshot_transition"]["prior_source_lf"])
    locators = next(node.value for node in tree.body
                    if isinstance(node, ast.AnnAssign)
                    and node.target.id == "DIRECT_TARGET_LOCATORS")
    index = next(i for i, node in enumerate(locators.elts)
                 if ast.literal_eval(node)["ticker"] == "HAH")
    locator = ast.literal_eval(locators.elts[index])
    if tamper == "extra_locator":
        locator.update(period="2026-Q3", url="https://haiants.vn/extra.pdf")
        locators.elts.append(ast.parse(repr(locator), mode="eval").body)
    elif tamper == "duplicate_locator":
        locators.elts.append(ast.parse(repr(locator), mode="eval").body)
    elif tamper == "missing_locator":
        del locators.elts[index]
    else:
        if tamper == "changed_url":
            locator["url"] += "?changed"
        else:
            locator["ticker"] = "BWE"
        locators.elts[index] = ast.parse(repr(locator), mode="eval").body
    active = (ast.unparse(tree) + "\n").encode("utf-8")
    path.write_bytes(active)
    prior = (tmp_path / ARCHIVE).read_bytes().replace(b"\r\n", b"\n")
    assert not structure_valid(prior, active)
    with pytest.raises(ValueError, match=ERROR + "BINDING_INVALID"):
        historical_bytes(tmp_path, SOURCE)


@pytest.mark.parametrize("target", [MANIFEST, ARCHIVE])
def test_hah_transition_refuses_missing_evidence_fixture(tmp_path, target):
    _copy_transition(tmp_path)
    (tmp_path / target).unlink()
    with pytest.raises(FileNotFoundError):
        historical_bytes(tmp_path, SOURCE)
