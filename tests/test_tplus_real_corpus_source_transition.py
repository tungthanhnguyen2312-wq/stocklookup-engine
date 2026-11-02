"""The 2026-11-03 T+ evidence-root successor binds exactly two sources and conserves every older pin."""
import hashlib
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from tools.verify_retention_reader_transition import (
    TPLUS_DAILY_MANIFEST, TPLUS_REAL_CORPUS_BASE, TPLUS_REAL_CORPUS_MANIFEST, TPLUS_REAL_CORPUS_SOURCES,
    TPLUS_RESUME_SOURCE, _iid_runtime_prior_bytes, _tplus_real_corpus_prior_bytes, historical_bytes,
)

ROOT = Path(__file__).resolve().parents[1]


def _lf(data: bytes) -> bytes:
    return data.replace(b"\r\n", b"\n")


@pytest.mark.parametrize("relative", TPLUS_REAL_CORPUS_SOURCES)
def test_successor_binds_the_merged_base_and_the_live_source(relative):
    row = json.loads((ROOT / TPLUS_REAL_CORPUS_MANIFEST).read_bytes())["sources"][relative]
    prior = _lf((ROOT / row["archive"]).read_bytes())
    assert prior == _lf(subprocess.check_output(["git", "show", f"{TPLUS_REAL_CORPUS_BASE}:{relative}"], cwd=ROOT))
    live = _lf((ROOT / relative).read_bytes())
    assert hashlib.sha256(live).hexdigest() == row["active_sha256_lf"] != row["prior_sha256_lf"]
    assert _tplus_real_corpus_prior_bytes(ROOT, relative, live) == prior
    historical_bytes(ROOT, relative)  # every older layer still verifies through the new peel


def test_streaming_prior_is_the_daily_incremental_active_source_and_pipeline_peels_before_iid():
    daily = json.loads((ROOT / TPLUS_DAILY_MANIFEST).read_bytes())["sources"][TPLUS_RESUME_SOURCE]
    row = json.loads((ROOT / TPLUS_REAL_CORPUS_MANIFEST).read_bytes())["sources"][TPLUS_RESUME_SOURCE]
    assert row["prior_sha256_lf"] == daily["active_sha256_lf"]
    live = _lf((ROOT / "canonical_post_close_pipeline.py").read_bytes())
    # The IID runtime layer receives the real-corpus prior, never the new live bytes.
    _iid_runtime_prior_bytes(ROOT, "canonical_post_close_pipeline.py", live)


@pytest.mark.parametrize("tamper", ["live", "archive", "scope", "extra_source"])
def test_successor_rejects_tamper(tmp_path, tamper):
    spec = json.loads((ROOT / TPLUS_REAL_CORPUS_MANIFEST).read_bytes())
    relative = TPLUS_RESUME_SOURCE
    for path in (relative, spec["sources"][relative]["archive"], TPLUS_REAL_CORPUS_MANIFEST):
        target = tmp_path / path
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / path, target)
    if tamper == "live":
        (tmp_path / relative).write_bytes(b"changed")
    elif tamper == "archive":
        (tmp_path / spec["sources"][relative]["archive"]).write_bytes(b"changed")
    else:
        if tamper == "scope":
            spec["scope"] = "UNBOUNDED"
        else:
            spec["sources"]["daily_analysis_pipeline.py"] = spec["sources"][relative]
        (tmp_path / TPLUS_REAL_CORPUS_MANIFEST).write_text(json.dumps(spec))
    with pytest.raises(ValueError, match="TPLUS_REAL_CORPUS_SOURCE_TRANSITION_"):
        _tplus_real_corpus_prior_bytes(tmp_path, relative, _lf((tmp_path / relative).read_bytes()))
