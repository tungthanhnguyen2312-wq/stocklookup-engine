"""Exact source/pin binding for Owner Decision 1; no historical receipt adoption."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

import pytest

from tools.qualify_e4_infrastructure import source_identity
from tools.verify_retention_reader_transition import PARENT_PE_MANIFEST, PARENT_PE_SOURCES, _parent_pe_prior_bytes, active_thesis_evidence_identity

ROOT = Path(__file__).resolve().parents[1]


def sha(data):
    return hashlib.sha256(data.replace(b"\r\n", b"\n")).hexdigest()


def test_parent_pe_transition_binds_exact_base_sources_pins_and_digest():
    spec = json.loads((ROOT / PARENT_PE_MANIFEST).read_bytes())
    receipt = json.loads((ROOT / "config/owner_daily_capacity_qualification.json").read_bytes())
    corrective = receipt["parent_attributable_headline_pe_corrective"]
    assert spec["release_authority"] == corrective["release_authority"] == "NOT_GRANTED"
    assert corrective["new_capacity_measurement"] is False and corrective["whole_daily_requalification"] is False
    assert spec["active_e4_v2_digest"] == source_identity(ROOT, version="v2")["code_digest"]
    assert active_thesis_evidence_identity(ROOT)["active_e4_v2_digest"] == spec["active_e4_v2_digest"]
    for relative in corrective["changed_source_paths"]:
        prior = subprocess.check_output(["git", "show", spec["base_commit"] + ":" + relative], cwd=ROOT)
        active = (ROOT / relative).read_bytes().replace(b"\r\n", b"\n")
        assert corrective["prior_source_sha256_lf"][relative] == sha(prior)
        assert receipt["source_sha256"][relative] == sha(active)
        if relative in PARENT_PE_SOURCES:
            assert _parent_pe_prior_bytes(ROOT, relative, active) == prior.replace(b"\r\n", b"\n")
            assert _parent_pe_prior_bytes(ROOT, relative, prior) == prior


@pytest.mark.parametrize("tamper", ["archive", "scope", "forged_prior", "extra_source"])
def test_parent_pe_transition_rejects_tampering(tmp_path, tamper):
    spec = json.loads((ROOT / PARENT_PE_MANIFEST).read_bytes())
    relative = PARENT_PE_SOURCES[0]
    row = spec["sources"][relative]
    archive = tmp_path / row["archive"]
    archive.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / row["archive"], archive)
    if tamper == "archive":
        archive.write_bytes(b"tampered")
    elif tamper == "scope":
        spec["scope"] = "EXPANDED"
    elif tamper == "forged_prior":
        row["prior_sha256_lf"] = "0" * 64
    else:
        spec["sources"]["extra.py"] = dict(row)
    manifest = tmp_path / PARENT_PE_MANIFEST
    manifest.parent.mkdir(parents=True, exist_ok=True)
    manifest.write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(ValueError, match="PARENT_PE_SOURCE_TRANSITION"):
        _parent_pe_prior_bytes(tmp_path, relative, (ROOT / relative).read_bytes().replace(b"\r\n", b"\n"))
