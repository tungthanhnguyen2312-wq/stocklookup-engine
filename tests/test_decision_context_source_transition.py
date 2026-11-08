"""2026-11-08 decision-context successor: the brief's additive fields are a bounded, archived boundary."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tools import qualify_e4_infrastructure as e4
from tools.verify_retention_reader_transition import (
    DECISION_CONTEXT_ARCHIVE, DECISION_CONTEXT_BASE, DECISION_CONTEXT_MANIFEST, DECISION_CONTEXT_SOURCE,
    _decision_context_prior_bytes,
)

ROOT = Path(__file__).resolve().parents[1]


def _lf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def test_archive_is_the_exact_base_source_and_binds_live_bytes():
    base = _lf(subprocess.check_output(["git", "show", DECISION_CONTEXT_BASE + ":" + DECISION_CONTEXT_SOURCE], cwd=ROOT))
    live = _lf((ROOT / DECISION_CONTEXT_SOURCE).read_bytes())
    assert _lf((ROOT / DECISION_CONTEXT_ARCHIVE).read_bytes()) == base != live
    assert _decision_context_prior_bytes(ROOT, DECISION_CONTEXT_SOURCE, live) == base
    spec = json.loads((ROOT / DECISION_CONTEXT_MANIFEST).read_bytes())
    assert spec["release_authority"] == "NOT_GRANTED"
    assert tuple(spec["sources"]) == (DECISION_CONTEXT_SOURCE,)
    assert spec["active_e4_v2_digest"] == e4.source_identity(ROOT, version="v2")["code_digest"]
    assert spec["previous_e4_v2_digest"] != spec["active_e4_v2_digest"]


def test_other_sources_pass_through():
    data = b"unrelated"
    assert _decision_context_prior_bytes(ROOT, "stocklookup_core/evidence/bounded_json.py", data) is data


@pytest.mark.parametrize("tamper", ["live", "archive", "scope", "forged_prior"])
def test_boundary_refuses_tampering(tmp_path, tamper):
    spec = json.loads((ROOT / DECISION_CONTEXT_MANIFEST).read_bytes())
    for path in (DECISION_CONTEXT_MANIFEST, DECISION_CONTEXT_SOURCE, DECISION_CONTEXT_ARCHIVE):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, target)
    if tamper == "live":
        (tmp_path / DECISION_CONTEXT_SOURCE).write_bytes(b"tampered")
    elif tamper in {"archive", "forged_prior"}:
        (tmp_path / DECISION_CONTEXT_ARCHIVE).write_bytes(b"tampered")
        if tamper == "forged_prior":
            spec["sources"][DECISION_CONTEXT_SOURCE]["prior_sha256_lf"] = hashlib.sha256(b"tampered").hexdigest()
    else:
        spec["scope"] = "UNBOUNDED"
    (tmp_path / DECISION_CONTEXT_MANIFEST).write_text(json.dumps(spec), encoding="utf-8")
    with pytest.raises(ValueError, match="DECISION_CONTEXT_SOURCE_TRANSITION_"):
        _decision_context_prior_bytes(tmp_path, DECISION_CONTEXT_SOURCE, _lf((tmp_path / DECISION_CONTEXT_SOURCE).read_bytes()))
