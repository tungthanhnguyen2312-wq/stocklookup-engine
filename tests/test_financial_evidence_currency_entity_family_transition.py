"""Exact HAH-only E6 declaration transition; no admission or release authority."""
import hashlib
import json
from pathlib import Path
import subprocess

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
    active = (ROOT / SOURCE).read_bytes().replace(b"\r\n", b"\n")
    assert (ROOT / ARCHIVE).read_bytes().replace(b"\r\n", b"\n") == original
    assert historical_bytes(ROOT, SOURCE) == original
    assert structure_valid(original, active)
    assert original != active
    assert hashlib.sha256(original).hexdigest() == spec["prior_sha256_lf"]
    assert hashlib.sha256(active).hexdigest() == spec["active_sha256_lf"]
    assert spec["added_tickers"] == ["HAH"]
    assert spec["release_authority"] == "NOT_GRANTED"
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
    else:
        target = ARCHIVE if tamper == "prior_hash" else SOURCE
        path = tmp_path / target
        path.write_bytes(path.read_bytes() + b"# tampered and rebound\n")
        field = "prior_sha256_lf" if tamper == "prior_hash" else "active_sha256_lf"
        spec[field] = hashlib.sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    (tmp_path / MANIFEST).write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(ValueError, match=ERROR + "SCOPE_INVALID"):
        historical_bytes(tmp_path, SOURCE)


@pytest.mark.parametrize("tamper", [
    "extra_key", "existing_family", "hah_family", "duplicate_key", "selector", "missing_hah",
])
def test_hah_transition_refuses_non_allowlisted_structure(tmp_path, tamper):
    _copy_transition(tmp_path)
    path = tmp_path / SOURCE
    active = path.read_bytes().replace(b"\r\n", b"\n")
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
    assert active != path.read_bytes().replace(b"\r\n", b"\n")
    path.write_bytes(active)
    prior = (tmp_path / ARCHIVE).read_bytes().replace(b"\r\n", b"\n")
    assert not structure_valid(prior, active)
    with pytest.raises(ValueError, match=ERROR + "STRUCTURE_INVALID"):
        historical_bytes(tmp_path, SOURCE)


@pytest.mark.parametrize("target", [MANIFEST, ARCHIVE])
def test_hah_transition_refuses_missing_evidence_fixture(tmp_path, target):
    _copy_transition(tmp_path)
    (tmp_path / target).unlink()
    with pytest.raises(FileNotFoundError):
        historical_bytes(tmp_path, SOURCE)
