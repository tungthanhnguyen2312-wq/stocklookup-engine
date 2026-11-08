"""D4a peels to the exact origin/main pipeline bytes, keeps E4 v2 unchanged and fails closed on tamper."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tools import qualify_e4_infrastructure as e4
from tools.verify_retention_reader_transition import (
    STORAGE_REUSE_D4A_ARCHIVE, STORAGE_REUSE_D4A_BASE, STORAGE_REUSE_D4A_MANIFEST, STORAGE_REUSE_D4A_SOURCE,
    TPLUS_M1B_MANIFEST, TPLUS_REAL_CORPUS_MANIFEST, _storage_reuse_d4a_prior_bytes, _tplus_real_corpus_prior_bytes,
)

ROOT = Path(__file__).resolve().parents[1]


def _lf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


def test_d4a_peels_to_base_bytes_and_the_real_corpus_active_source():
    spec = json.loads((ROOT / STORAGE_REUSE_D4A_MANIFEST).read_bytes())
    row = spec["sources"][STORAGE_REUSE_D4A_SOURCE]
    prior = _lf((ROOT / STORAGE_REUSE_D4A_ARCHIVE).read_bytes())
    try:
        base = _lf(subprocess.check_output(["git", "show", f"{STORAGE_REUSE_D4A_BASE}:{STORAGE_REUSE_D4A_SOURCE}"], cwd=ROOT))
    except (OSError, subprocess.CalledProcessError):
        base = prior  # shallow clone: the archive SHA binding below still pins the bytes
    assert prior == base
    real = json.loads((ROOT / TPLUS_REAL_CORPUS_MANIFEST).read_bytes())
    assert hashlib.sha256(prior).hexdigest() == row["prior_sha256_lf"] == real["sources"][STORAGE_REUSE_D4A_SOURCE]["active_sha256_lf"]
    live = _lf((ROOT / STORAGE_REUSE_D4A_SOURCE).read_bytes())
    assert hashlib.sha256(live).hexdigest() == row["active_sha256_lf"] != row["prior_sha256_lf"]
    assert _storage_reuse_d4a_prior_bytes(ROOT, STORAGE_REUSE_D4A_SOURCE, live) == prior
    assert _tplus_real_corpus_prior_bytes(ROOT, STORAGE_REUSE_D4A_SOURCE, live) != live


def test_d4a_does_not_change_the_e4_v2_digest():
    spec = json.loads((ROOT / STORAGE_REUSE_D4A_MANIFEST).read_bytes())
    m1b = json.loads((ROOT / TPLUS_M1B_MANIFEST).read_bytes())
    assert spec["previous_e4_v2_digest"] == spec["active_e4_v2_digest"] == m1b["active_e4_v2_digest"]
    root_fix = json.loads((ROOT / "tests/fixtures/thesis_current_technical_root_source_transition_v1.json").read_bytes())
    assert root_fix["previous_e4_v2_digest"] == m1b["active_e4_v2_digest"]
    summary_fp = json.loads((ROOT / "tests/fixtures/tplus_legacy_summary_fingerprint_source_transition_v1.json").read_bytes())
    assert summary_fp["previous_e4_v2_digest"] == root_fix["active_e4_v2_digest"]
    context_fp = json.loads((ROOT / "tests/fixtures/decision_context_premarket_source_transition_v1.json").read_bytes())
    assert context_fp["previous_e4_v2_digest"] == summary_fp["active_e4_v2_digest"]
    assert e4.source_identity(ROOT, version="v2")["code_digest"] == context_fp["active_e4_v2_digest"]


def test_other_sources_pass_through():
    assert _storage_reuse_d4a_prior_bytes(ROOT, "prospective_feedback_streaming.py", b"x") == b"x"


@pytest.mark.parametrize("tamper", ["live", "archive", "scope"])
def test_d4a_successor_rejects_tamper(tmp_path, tamper):
    for relative in (STORAGE_REUSE_D4A_SOURCE, STORAGE_REUSE_D4A_ARCHIVE, STORAGE_REUSE_D4A_MANIFEST,
                     TPLUS_REAL_CORPUS_MANIFEST, "tests/fixtures/tplus_real_t0_corpus_v1_sources/canonical_post_close_pipeline.py.txt"):
        target = tmp_path / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / relative, target)
    live = _lf((tmp_path / STORAGE_REUSE_D4A_SOURCE).read_bytes())
    if tamper == "live":
        live += b"# unqualified\n"  # neither D4a active nor real-corpus active: the older layer refuses
        pattern = "TPLUS_REAL_CORPUS_SOURCE_TRANSITION_BINDING_INVALID"
    elif tamper == "archive":
        (tmp_path / STORAGE_REUSE_D4A_ARCHIVE).write_bytes(b"changed")
        pattern = "STORAGE_REUSE_D4A_SOURCE_TRANSITION_BINDING_INVALID"
    else:
        spec = json.loads((tmp_path / STORAGE_REUSE_D4A_MANIFEST).read_bytes())
        spec["scope"] = "UNBOUNDED"
        (tmp_path / STORAGE_REUSE_D4A_MANIFEST).write_text(json.dumps(spec))
        pattern = "STORAGE_REUSE_D4A_SOURCE_TRANSITION_SCOPE_INVALID"
    with pytest.raises(ValueError, match=pattern):
        _tplus_real_corpus_prior_bytes(tmp_path, STORAGE_REUSE_D4A_SOURCE, live)
