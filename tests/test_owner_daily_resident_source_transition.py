"""Resident preseal changes preserve historical bytes and the deployed T+ reuse domain."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.verify_retention_reader_transition import (
    RESIDENT_MANIFEST, RESIDENT_SOURCES, _resident_prior_bytes,
    active_thesis_evidence_identity, legacy_source_identity,
)
from tools.qualify_e4_infrastructure import V1_SOURCES

ROOT = Path(__file__).resolve().parents[1]
BASE = "b9c4ff102f74bc41f4cb863f43a875a93e07cd9d"


def test_exact_merged_archives_and_feedback_dependencies():
    spec = json.loads((ROOT / RESIDENT_MANIFEST).read_bytes())
    for relative in RESIDENT_SOURCES:
        prior = subprocess.check_output(["git", "show", BASE + ":" + relative], cwd=ROOT).replace(b"\r\n", b"\n")
        live = (ROOT / relative).read_bytes().replace(b"\r\n", b"\n")
        assert _resident_prior_bytes(ROOT, relative, live) == prior != live
    for _, relative in V1_SOURCES:
        deployed = subprocess.check_output(["git", "show", BASE + ":" + relative], cwd=ROOT).replace(b"\r\n", b"\n")
        assert (ROOT / relative).read_bytes().replace(b"\r\n", b"\n") == deployed
    for relative in ("retained_evidence_catalog.py", "stocklookup_core/evidence/storage_portability.py"):
        deployed = subprocess.check_output(["git", "show", BASE + ":" + relative], cwd=ROOT).replace(b"\r\n", b"\n")
        assert (ROOT / relative).read_bytes().replace(b"\r\n", b"\n") == deployed
    assert legacy_source_identity(ROOT, version="v1")["code_digest"] == "fa79baadcca197493b9ca70067fbd153f5e8bb7f50dfb6dbc6da53f253483d46"
    assert active_thesis_evidence_identity(ROOT)["active_e4_v2_digest"] == spec["active_e4_v2_digest"]


@pytest.mark.parametrize("tamper", ["live", "archive", "scope", "forged_prior"])
def test_resident_boundary_refuses_tampering(tmp_path, tamper):
    spec = json.loads((ROOT / RESIDENT_MANIFEST).read_bytes())
    relative = RESIDENT_SOURCES[0]
    for path in (RESIDENT_MANIFEST, relative, spec["sources"][relative]["archive"]):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, target)
    if tamper == "live":
        (tmp_path / relative).write_bytes(b"tampered")
    elif tamper in {"archive", "forged_prior"}:
        (tmp_path / spec["sources"][relative]["archive"]).write_bytes(b"tampered")
        if tamper == "forged_prior":
            spec["sources"][relative]["prior_sha256_lf"] = hashlib.sha256(b"tampered").hexdigest()
    else:
        spec["scope"] = "UNBOUNDED"
    (tmp_path / RESIDENT_MANIFEST).write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(ValueError, match="RESIDENT_IID_SOURCE_TRANSITION_"):
        _resident_prior_bytes(tmp_path, relative, (tmp_path / relative).read_bytes().replace(b"\r\n", b"\n"))
