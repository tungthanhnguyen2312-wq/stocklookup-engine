"""D4a peels to the exact origin/main pipeline bytes, keeps E4 v2 unchanged and fails closed on tamper."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tools import qualify_e4_infrastructure as e4
from tools.verify_retention_reader_transition import (
    _velocity_projection_prior_bytes,
    STORAGE_REUSE_D4A_ARCHIVE, STORAGE_REUSE_D4A_BASE, STORAGE_REUSE_D4A_MANIFEST, STORAGE_REUSE_D4A_SOURCE,
    TPLUS_FEEDBACK_IO_MANIFEST, TPLUS_M1B_MANIFEST, TPLUS_REAL_CORPUS_MANIFEST, _storage_reuse_d4a_prior_bytes, _tplus_real_corpus_prior_bytes,
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
    d4a_live = _velocity_projection_prior_bytes(ROOT, STORAGE_REUSE_D4A_SOURCE, live)
    assert hashlib.sha256(d4a_live).hexdigest() == row["active_sha256_lf"] != row["prior_sha256_lf"]
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
    feedback_io = json.loads((ROOT / TPLUS_FEEDBACK_IO_MANIFEST).read_bytes())
    assert feedback_io["previous_e4_v2_digest"] == context_fp["active_e4_v2_digest"]
    retry = json.loads((ROOT / "tests/fixtures/tplus_retry_integrity_source_transition_v1.json").read_bytes())
    assert retry["previous_e4_v2_digest"] == feedback_io["active_e4_v2_digest"]
    truthfulness = json.loads((ROOT / "tests/fixtures/valuation_output_truthfulness_source_transition_v1.json").read_bytes())
    assert truthfulness["previous_e4_v2_digest"] == retry["active_e4_v2_digest"]
    direction = json.loads((ROOT / "tests/fixtures/tplus_taxonomy_direction_source_transition_v1.json").read_bytes())
    assert direction["previous_e4_v2_digest"] == truthfulness["active_e4_v2_digest"]
    parent_pe = json.loads((ROOT / "tests/fixtures/parent_attributable_pe_source_transition_v1.json").read_bytes())
    assert parent_pe["previous_e4_v2_digest"] == direction["active_e4_v2_digest"]
    assert e4.source_identity(ROOT, version="v2")["code_digest"] == parent_pe["active_e4_v2_digest"]


def test_other_sources_pass_through():
    assert _storage_reuse_d4a_prior_bytes(ROOT, "prospective_feedback_streaming.py", b"x") == b"x"


@pytest.mark.parametrize("tamper", ["live", "archive", "scope"])
def test_d4a_successor_rejects_tamper(tmp_path, tamper):
    for relative in (STORAGE_REUSE_D4A_SOURCE, STORAGE_REUSE_D4A_ARCHIVE, STORAGE_REUSE_D4A_MANIFEST,
                     TPLUS_REAL_CORPUS_MANIFEST, "tests/fixtures/tplus_real_t0_corpus_v1_sources/canonical_post_close_pipeline.py.txt",
                     "tests/fixtures/velocity_projection_and_producer_timing_v1.json",
                     "tests/fixtures/velocity_projection_and_producer_timing_v1_sources/canonical_post_close_pipeline.py.txt",
                     "tests/fixtures/tplus_retry_integrity_source_transition_v1.json",
                     "tests/fixtures/tplus_retry_integrity_v1_sources/canonical_post_close_pipeline.py.txt"):
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


@pytest.mark.parametrize("tamper", [None, "live", "archive", "scope"])
def test_canonical_dispatch_transition_conserves_exact_prior_source(tmp_path, tamper):
    from tools.verify_retention_reader_transition import D4A_CANONICAL_MANIFEST, _d4a_canonical_prior_bytes
    spec = json.loads((ROOT / D4A_CANONICAL_MANIFEST).read_bytes())
    relative = "canonical_daily_operation.py"
    archive = spec["sources"][relative]["archive"]
    predecessor = "tests/fixtures/velocity_projection_and_producer_timing_v1_sources/canonical_daily_operation.py.txt"
    for name in (D4A_CANONICAL_MANIFEST, archive, predecessor):
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / name, target)
    active = _lf((tmp_path / predecessor).read_bytes())
    if tamper == "live":
        active += b"# unreviewed\n"
    elif tamper == "archive":
        (tmp_path / archive).write_bytes(b"bad")
    elif tamper == "scope":
        spec["scope"] = "UNBOUNDED"
        (tmp_path / D4A_CANONICAL_MANIFEST).write_text(json.dumps(spec))
    if tamper:
        with pytest.raises(ValueError, match="D4A_CANONICAL_SOURCE_"):
            _d4a_canonical_prior_bytes(tmp_path, relative, active)
    else:
        prior = _d4a_canonical_prior_bytes(tmp_path, relative, active)
        assert prior == _lf((ROOT / archive).read_bytes())
        assert hashlib.sha256(prior).hexdigest() == spec["sources"][relative]["prior_sha256_lf"]
